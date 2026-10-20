"""Prepare private full-context review material, never labels, gold or scores.

The 24 supplied questions are development material. Literal search hints order
human work only; every selected record/question pair starts as unreviewed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from observatory.chunking import retrieval_spans
from observatory.evaluate import canonical_digest, strict_json_loads

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "eval/customer_metrics/content_questions.v1.json"
MAX_INPUT_BYTES = 64 * 1024 * 1024
FORMAT = "content-review-preparation-v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("input_too_large")
    return strict_json_loads(data), data


def validate_questions(value):
    if not isinstance(value, dict) or value.get("status") != "draft_requires_client_confirmation":
        raise ValueError("question_definitions_must_be_unapproved_draft")
    questions = value.get("questions")
    if (not isinstance(questions, list) or len(questions) != 24
            or {q.get("question_id") for q in questions if isinstance(q, dict)}
            != {f"Q{i:02d}" for i in range(1, 25)}):
        raise ValueError("exact_24_question_ids_required")
    for question in questions:
        for field in ("question_exact", "query_question", "source_ref", "source_paragraph_exact"):
            if not isinstance(question.get(field), str) or not question[field].strip():
                raise ValueError("question_source_or_text_missing")
        terms = question.get("candidate_search_terms")
        if (not isinstance(terms, list) or any(not isinstance(t, str) or not t.strip() for t in terms)
                or len(terms) > 50 or any(len(t) > 120 for t in terms)):
            raise ValueError("invalid_candidate_search_terms")
    return sorted(questions, key=lambda q: q["question_id"])


def normalize_records(value):
    rows = value.get("records") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows or len(rows) > 20000:
        raise ValueError("full_source_records_required")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_source_record")
        payload = row.get("payload", row)
        if not isinstance(payload, dict):
            raise ValueError("invalid_source_payload")
        rid, version = row.get("record_id"), row.get("version_id")
        body = row.get("body", payload.get("body"))
        dataset = row.get("dataset", payload.get("dataset"))
        if (not isinstance(rid, str) or not rid.strip() or rid in seen
                or not isinstance(version, str) or not version.strip()
                or dataset not in {"native", "social"} or not isinstance(body, str)):
            raise ValueError("missing_duplicate_or_invalid_source_identity")
        seen.add(rid)
        body_sha256 = digest(body.encode("utf-8"))
        declared = row.get("body_hash", row.get("body_sha256"))
        if declared is not None and declared != body_sha256:
            raise ValueError("source_body_hash_mismatch")
        if type(payload.get("countable")) is not bool or type(payload.get("retrievable")) is not bool:
            raise ValueError("explicit_admission_flags_required")
        active = row.get("active", True)
        if type(active) is not bool:
            raise ValueError("invalid_active_flag")
        ranges = retrieval_spans(body, retrieval_ranges=payload.get("retrieval_ranges"),
                                 retrieval_end=payload.get("retrieval_end"))
        # Known searchable ranges do not certify complete extraction of the page.
        result.append({"record_id": rid, "version_id": version, "dataset": dataset,
                       "active": active, "body": body, "body_sha256": body_sha256,
                       "payload_sha256": canonical_digest(payload),
                       "retrieval_ranges": [list(pair) for pair in ranges],
                       "payload": payload, "extraction_completeness": "not_verified_by_this_preparer"})
    return sorted(result, key=lambda r: r["record_id"])


def validate_database_identities(records):
    for record in records:
        payload = record["payload"]
        if (canonical_digest(payload) != record["version_id"] or payload.get("body") != record["body"]
                or payload.get("record_id") != record["record_id"] or payload.get("dataset") != record["dataset"]):
            raise ValueError("database_payload_version_or_identity_mismatch")


def acquire_database():
    """Reuse the evaluator snapshot reader on enforced read-only connections."""
    from check_statistics_reference import ReadOnlyDatabase, state_guard

    from observatory.config import Settings
    from observatory.evaluate import load_snapshot, snapshot_identity

    db = ReadOnlyDatabase(Settings.from_env().database_url)
    before = {"health": snapshot_identity(db.health()), "ledger": state_guard(db)}
    records = normalize_records(list(load_snapshot(db).values()))
    validate_database_identities(records)
    with db.connect() as conn:
        hashes = conn.execute("SELECT r.record_id,v.version_id,v.body_hash FROM records r "
                              "JOIN record_versions v ON r.current_version=v.version_id WHERE r.active").fetchall()
    if {(r["record_id"], r["version_id"], r["body_sha256"]) for r in records} != {
            (r["record_id"], r["version_id"], r["body_hash"]) for r in hashes}:
        raise ValueError("stored_source_body_identity_mismatch")
    after = {"health": snapshot_identity(db.health()), "ledger": state_guard(db)}
    if before != after:
        raise ValueError("source_index_or_ledger_changed_during_capture")
    return records, {"mode": "read_only_database_observation", "before": before, "after": after,
                     "limits": "Separate read-only snapshots; not a global lock or semantic review."}


def hint_matches(body, terms):
    matches = []
    for term in dict.fromkeys(terms):
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in term.split()) + r"(?!\w)"
        for match in re.finditer(pattern, body, re.IGNORECASE):
            start, end = match.span()
            left, right = max(0, start - 160), min(len(body), end + 160)
            matches.append({"term": term, "start": start, "end": end, "quote": body[start:end],
                            "context_start": left, "context_end": right, "context": body[left:right]})
    return sorted(matches, key=lambda m: (m["start"], m["end"], m["term"]))


def article_name(record):
    return digest(record["record_id"].encode("utf-8")) + ".html"


def safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        return value if parts.scheme in {"http", "https"} and parts.hostname and not parts.username else None
    except ValueError:
        return None


def page(title, body):
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            f"<title>{html.escape(title)}</title><style>body{{font:17px/1.6 system-ui;max-width:1100px;"
            "margin:40px auto;padding:0 24px;color:#183049;background:#f5f7fa}"
            "a{color:#145b83}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}"
            "table{border-collapse:collapse;width:100%}td,th{text-align:left;vertical-align:top;"
            "padding:10px;border-bottom:1px solid #d9e0e6}code{overflow-wrap:anywhere}"
            "details{margin:20px 0}small{color:#536679}</style><body>" + body + "</body></html>")


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        # CSV is intended for spreadsheets; source-derived cells are inert text.
        writer.writerow({key: "'" + str(value) if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                         else value for key, value in row.items()})
    return stream.getvalue().encode("utf-8-sig")


def build_files(records, definitions, question_bytes, observation):
    questions = validate_questions(definitions)
    selected = [r for r in records if r["active"] and r["dataset"] == "native" and r["payload"]["countable"]]
    if not selected:
        raise ValueError("no_active_countable_native_records")
    files, units, hints, summary = {}, [], [], []
    snapshot = {"records": records, "observation": observation}
    files["source_snapshot.json"] = encoded(snapshot)
    files["question_definitions.json"] = question_bytes
    question_sha = digest(question_bytes)
    groups = []
    for record in selected:
        payload = record["payload"]
        link = article_name(record)
        source_links = " ".join(f"<a href='{html.escape(url, quote=True)}'>{label}</a>"
                                for label, value in (("Original", payload.get("url")), ("Archive", payload.get("archive_url")))
                                if (url := safe_url(value)))
        title = payload.get("title") or record["record_id"]
        details = {k: v for k, v in record.items() if k != "body"}
        details["payload"] = {k: v for k, v in payload.items() if k != "body"}
        body = (f"<a href='../index.html'>Review index</a><h1>{html.escape(str(title))}</h1>"
                f"<p>{html.escape(str(payload.get('sponsor', '')))} · {html.escape(str(payload.get('publisher', '')))}"
                f" · {html.escape(str(payload.get('published_at') or 'Unknown date'))}</p>{source_links}"
                "<p><strong>Unreviewed source.</strong> The complete retained body is below."
                " Retained text is not proof of a complete original page. Read extraction issues and"
                " surrounding context before making a judgment.</p>"
                f"<details><summary>Source identity and extraction limits</summary><pre>{html.escape(json.dumps(details, ensure_ascii=False, indent=2))}</pre></details>"
                f"<h2>Retained body ({len(record['body'])} Unicode characters)</h2><pre>{html.escape(record['body'])}</pre>")
        files["articles/" + link] = page(str(title), body).encode("utf-8")
        exact_hash = digest(" ".join(record["body"].casefold().split()).encode("utf-8")) if record["body"].strip() else None
        groups.append({"record_id": record["record_id"], "version_id": record["version_id"],
                       "exact_body_group_hint": exact_hash or "empty:" + record["record_id"],
                       "near_duplicate_review": "pending", "split": "development_current_corpus"})
    for question in questions:
        qid = question["question_id"]
        found = []
        for record in selected:
            matches = hint_matches(record["body"], question["candidate_search_terms"])
            unit = {"question_id": qid, "record_id": record["record_id"], "dataset": "native",
                    "version_id": record["version_id"], "body_sha256": record["body_sha256"],
                    "question_definitions_sha256": question_sha, "review_status": "unreviewed",
                    "membership": "unknown", "body_completeness": "not_reviewed",
                    "hint_occurrences": len(matches), "article_file": "articles/" + article_name(record),
                    "support_start": "", "support_end": "", "support_quote": "",
                    "limitation_start": "", "limitation_end": "", "limitation_quote": "",
                    "speaker": "", "article_treatment": "", "consensus_subcode": "",
                    "reason_or_exclusion": "", "reviewer": "", "reviewed_at": ""}
            units.append(unit)
            hints.extend({"question_id": qid, "record_id": record["record_id"], "version_id": record["version_id"],
                          "body_sha256": record["body_sha256"], **m} for m in matches)
            if matches:
                found.append((record, matches))
        found.sort(key=lambda pair: (-len(pair[1]), pair[0]["record_id"]))
        summary.append({"question_id": qid, "records_to_review": len(selected),
                        "records_with_literal_hints": len(found), "unreviewed_records": len(selected),
                        "complete_gold": False, "precision": None, "recall": None})
        rows = "".join(f"<tr><td><a href='../articles/{article_name(r)}'>{html.escape(str(r['payload'].get('title') or r['record_id']))}</a></td>"
                       f"<td>{len(ms)}</td><td>{html.escape(ms[0]['context'])}</td></tr>" for r, ms in found)
        unmatched = "".join(f"<li><a href='../articles/{article_name(r)}'>{html.escape(str(r['payload'].get('title') or r['record_id']))}</a></li>"
                            for r in selected if not hint_matches(r["body"], question["candidate_search_terms"]))
        body = (f"<a href='../index.html'>Review index</a><h1>{html.escape(question['query_question'])}</h1>"
                "<p>Literal hints prioritize review only. All selected records remain unreviewed,"
                " including records below without a hint. No scores or approved labels are present.</p>"
                f"<details><summary>Original question and draft judgment rules</summary><pre>{html.escape(json.dumps(question, ensure_ascii=False, indent=2))}</pre></details>"
                f"<h2>{len(found)} records with literal hints</h2><table><tr><th>Advertisement</th><th>Hint count</th><th>First hint context, not evidence judgment</th></tr>{rows}</table>"
                f"<details><summary>{len(selected)-len(found)} records without these hints — still awaiting full-context review</summary><ul>{unmatched}</ul></details>")
        files["questions/" + qid + ".html"] = page(qid, body).encode("utf-8")
    files["review_units.csv"] = csv_bytes(units, list(units[0]))
    files["article_groups.draft.csv"] = csv_bytes(groups, list(groups[0]))
    files["hint_spans.jsonl"] = b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8") for r in hints)
    rows = "".join(f"<tr><td><a href='questions/{q['question_id']}.html'>{q['question_id']}</a></td>"
                   f"<td>{html.escape(q['query_question'])}</td><td>{s['records_with_literal_hints']}</td>"
                   f"<td>{s['records_to_review']}</td></tr>" for q, s in zip(questions, summary, strict=True))
    files["index.html"] = page("Client content review", "<h1>Client content review</h1>"
        "<p>Current-corpus development preparation. Definitions, source identities and lexical"
        " hints are supplied; all membership decisions await full-context human review.</p>"
        f"<p>{len(selected)} selected native records × 24 questions = {len(units)} unreviewed pairs."
        " Social and cross-collection evaluation are not included.</p>"
        "<p><a href='review_units.csv'>Download blank review table</a> · <a href='review_guide.md'>Review guide</a></p>"
        "<table><tr><th>Question</th><th>Client task</th><th>Records with literal hints</th><th>Records awaiting review</th></tr>"
        + rows + "</table>").encode("utf-8")
    files["review_guide.md"] = ("# 内容审查说明\n\n"
        "这是当前语料的开发审查材料，不是金标准、独立留出测试或客户批准。\n\n"
        "1. 先确认 question_definitions.json 的纳入/排除草案，记录审核人和批准版本。\n"
        "2. 可按文章一次阅读全文，再逐题填写 review_units.csv；候选词只帮助排序。未命中也必须审查。\n"
        "3. 未审为 unknown；完整上下文足够时由人判 relevant/irrelevant，材料不足保留 unknown。\n"
        "4. 支持与限制引文使用原文 Unicode 字符的 [start,end)；原文不得改写。记录主体、处理方式，Q15共识子码另判。\n"
        "5. disclosure 还需原页面/截图；缺正文标识不能判页面没有。原始链接和归档在本轮未联网核验。\n"
        "6. 保存双方独立审查与分歧，不直接覆盖原始包。源版本、定义或范围变化时重新生成新目录。\n"
        "7. article_groups.draft.csv 仅按保留正文建议精确重复组，尚未检查转载或近重复，不可标为独立留出。\n"
        "8. 全范围逐篇审定后，另建完整成员参考；实际运行答案和逐条审查绑定后，才可接入 metric_report。\n\n"
        "CSV 带 UTF-8 BOM，来源文本可能以单引号防止表格公式执行；source_snapshot.json 保留原字节含义。\n"
        "现有 prepare_client_review.py 专用于独立验收冻结，本包不得伪装未调参输入直接送入。\n").encode("utf-8")
    files["preparation_summary.json"] = encoded({"format_version": FORMAT,
        "built_at_utc": datetime.now(timezone.utc).isoformat(), "status": "awaiting_definition_and_source_review",
        "source_records": len(records), "selected_records": len(selected), "question_count": len(questions),
        "review_units": len(units), "reviewed_units": 0, "relevant_units": None, "quality_scores": None,
        "source_snapshot_sha256": digest(files["source_snapshot.json"]), "questions": summary,
        "extraction_completeness": dict(Counter(r["extraction_completeness"] for r in selected)),
        "retrievable_records": sum(r["payload"]["retrievable"] for r in selected),
        "customer_approved": False, "semantic_gold": False, "unseen_test": False,
        "selection": {"dataset": "native", "active": True, "countable": True, "unit": "source_record_id"},
        "selection_sha256": canonical_digest([{k: r[k] for k in ("record_id", "version_id", "body_sha256")} for r in selected])})
    return files


def prepare(source, question_path, output, *, database=False):
    if output.exists():
        raise ValueError("output_directory_already_exists")
    definitions, question_bytes = read_json(question_path)
    validate_questions(definitions)
    if database:
        records, observation = acquire_database()
    else:
        value, source_bytes = read_json(source)
        records = normalize_records(value)
        observation = {"mode": "supplied_snapshot", "input_sha256": digest(source_bytes),
                       "source_identity_authenticated": False}
    files = build_files(records, definitions, question_bytes, observation)
    manifest = {"format_version": FORMAT, "status": "unreviewed_development_preparation",
                "script_sha256": digest(Path(__file__).read_bytes()),
                "input_sha256": {name: digest(data) for name, data in files.items()},
                "customer_approved": False, "semantic_gold": False, "quality_scores": None}
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (output / "manifest.json").write_bytes(encoded(manifest))
    summary = strict_json_loads(files["preparation_summary.json"])
    return {k: summary[k] for k in ("status", "source_records", "selected_records", "question_count", "review_units", "reviewed_units", "quality_scores")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Full snapshot JSON with exact bodies and version IDs")
    source.add_argument("--database", action="store_true", help="Read-only capture; no model or vector calls")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, required=True, help="New private directory; never overwrite")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.input, args.questions, args.output, database=args.database)
    except Exception as exc:
        # Driver messages and paths may contain private connection information.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
