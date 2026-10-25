"""Compile source-bound teacher references for evaluation, without training."""
from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from prepare_content_review import (
    csv_bytes,
    digest,
    encoded,
    normalize_records,
    page,
    safe_url,
    validate_database_identities,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / ".runtime/rag_training_split_20261006/prepared_v2/training_candidates.jsonl"
DEFAULT_SNAPSHOT = ROOT / ".runtime/content_source_refresh_20261006/content_review/source_snapshot.json"
DEFAULT_ANNOTATIONS = ROOT / ".runtime/teacher_reference_20261006"
FAMILIES = {
    "speaker_attribution": {
        "directory": "teacher_speaker_v2",
        "labels": {
            "speaker_role": ["sponsor_representative", "sponsor_corporate_voice", "other_named_actor", "article_narrator", "multiple_voices", "unknown"],
            "presentation": ["direct_quote", "reported_statement", "narrative", "mixed", "unclear"],
        },
    },
    "negation_scope": {
        "directory": "teacher_negation_v2",
        "labels": {
            "negation_function": ["limitation", "contrast", "conditional_qualification", "rhetorical_emphasis",
                                  "plain_negation", "no_semantic_negation", "mixed", "unknown"],
            "rejection_extent": ["partial_or_scoped", "whole_proposition", "none", "unclear"],
        },
    },
    "planned_vs_achieved": {
        "directory": "teacher_temporal",
        "labels": {
            "temporal_status": ["reported_past_or_current", "future_plan_or_target", "conditional_forecast",
                                "general_capability", "mixed", "unknown"],
            "achievement_asserted": ["yes", "no", "unclear"],
        },
    },
}


def read_lines(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("object_rows_required")
    return rows


def source_bindings(case, sources):
    declared = case.get("source_records")
    if not isinstance(declared, list) or not declared:
        raise ValueError("source_records_required")
    ids = []
    for binding in declared:
        if not isinstance(binding, dict):
            raise ValueError("source_binding_object_required")
        record = sources.get(binding.get("record_id"))
        if not record or not record["active"]:
            raise ValueError("unknown_or_inactive_source")
        for field in ("version_id", "body_sha256", "payload_sha256", "dataset"):
            if binding.get(field) != record[field]:
                raise ValueError("stale_source_binding")
        if binding.get("title") != record["payload"].get("title") or binding.get("url") != record["payload"].get("url"):
            raise ValueError("source_title_or_url_mismatch")
        if any(binding.get(key) != record["payload"].get(key) for key in ("countable", "retrievable")):
            raise ValueError("source_admission_binding_mismatch")
        ids.append(record["record_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_source_member")
    return set(ids)


def located_evidence(source, interval):
    start, end = interval.get("start"), interval.get("end")
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["body"])
            or not any(left <= start < end <= right for left, right in source["retrieval_ranges"])
            or not source["payload"]["retrievable"]):
        raise ValueError("evidence_outside_permitted_saved_text")
    return {"record_id": source["record_id"], "version_id": source["version_id"],
            "body_sha256": source["body_sha256"], "start": start, "end": end,
            "offset_unit": "unicode_codepoints", "quote": source["body"][start:end]}


def objective_reference(case, sources):
    """Re-enumerate records; never trust a stored count or inferred date."""
    operation, arguments = case["operation"], case["arguments"]
    members = [row for row in sources.values() if row["active"] and row["dataset"] == "native"
               and row["payload"]["countable"]]
    source = sources.get(arguments.get("record_id"))
    payload = source["payload"] if source else {}
    if operation == "read_source_identity":
        value = {key: payload.get(key) for key in ("url", "archive_url", "title", "publisher")}
    elif operation == "read_sponsor_and_collection_term":
        value = {"sponsor": payload.get("sponsor"), "collection_search_term": payload.get("keyword"),
                 "interpretation": "Stored fields only; a collection search term does not establish sponsorship."}
    elif operation == "read_publication_date":
        value = {"published_at": payload.get("published_at"), "date_state": "known" if payload.get("published_at") else "unknown"}
    elif operation == "read_admission_flags":
        value = {"countable": payload["countable"], "retrievable": payload["retrievable"],
                 "retained_body_characters": len(source["body"]), "extraction_completeness": source["extraction_completeness"]}
    elif operation == "read_archive_availability":
        value = {"archive_url": payload.get("archive_url"), "archive_supplied": bool(payload.get("archive_url")), "network_checked": False}
    elif operation == "read_quality_issues":
        value = {"issues": payload.get("issues", []), "extraction_completeness": source["extraction_completeness"]}
    elif operation == "handle_unavailable_retained_text":
        if payload["retrievable"] and source["body"].strip():
            raise ValueError("available_text_cannot_be_unavailable_reference")
        value = {"body_search_permitted": False, "content_state": "unknown", "reason": "retrievable_false_or_empty_retained_body",
                 "must_not_claim": "no relevant claim in the original advertisement"}
    elif operation == "read_exact_source_range":
        evidence = located_evidence(source, arguments)
        value = {"quote": evidence["quote"], "version_id": source["version_id"], "body_sha256": source["body_sha256"]}
    else:
        if operation in {"count_outlet_records", "find_all_tied_top_sponsors"}:
            field = "publisher"
        elif operation == "count_records_on_date":
            field = "published_at"
        elif operation in {"count_sponsor_records", "group_sponsor_records_by_publisher", "group_sponsor_records_by_year", "compare_two_calendar_years"}:
            field = "sponsor"
        else:
            raise ValueError("unsupported_objective_operation")
        members = [row for row in members if row["payload"].get(field) == arguments[field]]
        if operation.startswith("count_"):
            value = {"count": len(members), "unit": "distinct_record_id", "unknown_dates_included": field != "published_at"}
        elif operation == "group_sponsor_records_by_publisher":
            counts = Counter(row["payload"].get("publisher") or "Unknown publisher" for row in members)
            value = {"groups": [{"publisher": name, "count": count} for name, count in sorted(counts.items())],
                     "total": len(members), "unit": "distinct_record_id"}
        elif operation in {"group_sponsor_records_by_year", "compare_two_calendar_years"}:
            counts = Counter(str(row["payload"]["published_at"])[:4] if row["payload"].get("published_at") else "Unknown date" for row in members)
            if operation == "group_sponsor_records_by_year":
                value = {"groups": [{"year": year, "count": count} for year, count in sorted(counts.items())],
                         "total": len(members), "inferred_dates_used": False}
            else:
                first, second = arguments["years"]
                value = {"period_counts": [{"year": year, "count": counts[year]} for year in (first, second)],
                         "difference_second_minus_first": counts[second] - counts[first],
                         "unknown_date_count": counts["Unknown date"], "inferred_dates_used": False}
        else:
            counts = Counter(row["payload"].get("sponsor") or "Unknown sponsor" for row in members)
            top = max(counts.values())
            value = {"top_count": top, "sponsors": sorted(name for name, count in counts.items() if count == top),
                     "counts": dict(sorted(counts.items()))}
        if {row["record_id"] for row in members} != source_bindings(case, sources):
            raise ValueError("statistical_member_set_mismatch")
    if source and source_bindings(case, sources) != {source["record_id"]}:
        raise ValueError("single_source_member_set_mismatch")
    if encoded(value) != encoded(case["reference"]):
        raise ValueError("objective_reference_changed")
    return value


def scoring_fields(value):
    """Grade answer facts, not wording of fixed policy/explanation strings."""
    explanatory = {"interpretation", "extraction_completeness", "reason", "must_not_claim"}
    return {key: item for key, item in value.items() if key not in explanatory}


def validate_teacher(case, annotation, source):
    family = case["task_family"]
    if annotation.get("case_id") != case["case_id"] or annotation.get("status") not in {"resolved", "unresolved"}:
        raise ValueError("invalid_teacher_identity_or_status")
    if any(not isinstance(annotation.get(key), str) or not annotation[key].strip() for key in ("answer_zh", "rationale_zh")):
        raise ValueError("teacher_natural_language_answer_required")
    labels = annotation.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("teacher_labels_required")
    if annotation["status"] == "unresolved":
        if labels:
            raise ValueError("unresolved_teacher_must_not_supply_labels")
    else:
        allowed = FAMILIES[family]["labels"]
        if set(labels) != set(allowed) or any(labels[key] not in values for key, values in allowed.items()):
            raise ValueError("unsupported_teacher_label")
    names = annotation.get("speaker_names", [])
    if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("invalid_speaker_names")
    if len({" ".join(name.split()).casefold() for name in names}) != len(names):
        raise ValueError("duplicate_speaker_name")
    if family == "speaker_attribution":
        body = " ".join(source["body"].split()).casefold()
        if any(" ".join(name.split()).casefold() not in body for name in names):
            raise ValueError("speaker_name_not_in_saved_body")
    intervals = annotation.get("evidence_intervals")
    if not isinstance(intervals, list) or not 1 <= len(intervals) <= 3:
        raise ValueError("one_to_three_teacher_intervals_required")
    evidence = []
    for interval in intervals:
        if not isinstance(interval, dict) or not isinstance(interval.get("reason_zh"), str) or not interval["reason_zh"].strip():
            raise ValueError("evidence_reason_required")
        item = located_evidence(source, interval)
        if item["end"] - item["start"] > 1500:
            raise ValueError("teacher_evidence_interval_too_large")
        evidence.append(item | {"reason_zh": interval["reason_zh"]})
    target = case["source_span"]
    located = located_evidence(source, target)
    if target.get("quote") != located["quote"] or target.get("offset_unit") != "unicode_codepoints":
        raise ValueError("focal_source_quote_or_unit_mismatch")
    if not any(item["start"] == target["start"] and item["end"] == target["end"] for item in evidence):
        raise ValueError("focal_teacher_evidence_required")
    limits = annotation.get("limitations")
    if not isinstance(limits, list) or any(not isinstance(item, str) or not item.strip() for item in limits):
        raise ValueError("teacher_limitations_list_required")
    expected = dict(labels)
    if family == "speaker_attribution" and annotation["status"] == "resolved":
        expected["speaker_names"] = names
    return expected if annotation["status"] == "resolved" else None, evidence


def objective_answer_zh(case, value):
    family = case["task_family"]
    if "count" in value:
        return f"按题目指定的冻结字段精确筛选，共{value['count']}条可计数原生记录；单位是记录ID。"
    if family == "company_outlet_relationships":
        groups = "；".join(f"{row['publisher']}：{row['count']}篇" for row in value["groups"])
        return f"对应媒体及篇数：{groups}。合计{value['total']}篇。"
    if family == "yearly_counts":
        groups = "；".join(f"{row['year']}：{row['count']}篇" for row in value["groups"])
        return f"按存储年份分组：{groups}。未知日期单列，不使用推断日期。"
    if family == "two_period_comparison":
        first, second = value["period_counts"]
        return f"{first['year']}年{first['count']}篇，{second['year']}年{second['count']}篇；后期减前期为{value['difference_second_minus_first']}篇。未知日期{value['unknown_date_count']}篇，不放入任一期。"
    if family == "tied_highest_count":
        return f"并列最高为{'、'.join(value['sponsors'])}，各{value['top_count']}篇；所有并列对象保留。"
    if family == "archive_availability":
        return f"冻结记录{'提供归档链接：' + value['archive_url'] if value['archive_supplied'] else '未提供归档链接'}。未检查链接当前是否可打开。"
    if family == "date_missingness":
        return f"存储发布日期为{value['published_at']}。" if value["date_state"] == "known" else "记录未提供发布日期，保持未知。"
    if family == "collection_term_vs_sponsor":
        return f"存储赞助方：{value['sponsor'] or '未知'}；收集搜索词：{value['collection_search_term'] or '未知'}。搜索词不证明赞助身份。"
    if family == "source_identity":
        return f"文章：{value['title']}；媒体：{value['publisher'] or '未知'}；原始链接：{value['url'] or '未提供'}。版本见来源记录。"
    if family == "countable_vs_retrievable":
        return f"可计数：{value['countable']}；可检索：{value['retrievable']}；保留正文{value['retained_body_characters']}字符。这些标志不证明全文抽取完整。"
    if family == "record_quality_limits":
        issues = [str(item.get('detail') or item.get('code') or json.dumps(item, ensure_ascii=False))
                  if isinstance(item, dict) else str(item) for item in value['issues']]
        return f"存储的抽取问题：{'；'.join(issues) or '没有列出问题'}。没有列出不代表已确认全文完整，也没有推断修复状态。"
    if family == "unavailable_body_handling":
        return "保存正文未允许检索或为空，内容判断保持未知，不能回答原广告没有相关主张。"
    return f"指定区间的原文为：{value['quote']}；来源版本和正文哈希另附。"


def compile_references(cases, records, annotations):
    sources = {record["record_id"]: record for record in records}
    output, seen, used = [], set(), set()
    for case in cases:
        identifier = case.get("case_id")
        if not isinstance(identifier, str) or identifier in seen:
            raise ValueError("duplicate_or_invalid_candidate_id")
        seen.add(identifier)
        if (case.get("split") != "train_development_candidate" or case.get("human_gold_approved") is not False
                or case.get("runtime_enabled") is not False or case.get("permitted_in_runtime_prompt") is not False):
            raise ValueError("original_candidate_role_or_approval_changed")
        source_bindings(case, sources)
        span = case.get("source_span")
        if span is not None:
            focal_source = sources.get(case.get("arguments", {}).get("record_id"))
            if focal_source is None or len(case["source_records"]) != 1:
                raise ValueError("focal_single_source_required")
            located = located_evidence(focal_source, span)
            if span.get("quote") != located["quote"] or span.get("offset_unit") != "unicode_codepoints":
                raise ValueError("focal_source_quote_or_unit_mismatch")
        family = case["task_family"]
        if family in FAMILIES:
            annotation = annotations.get(identifier)
            if not annotation or len(case["source_records"]) != 1:
                raise ValueError("teacher_reference_missing_or_multiple_sources")
            source = sources[case["source_records"][0]["record_id"]]
            expected, evidence = validate_teacher(case, annotation, source)
            used.add(identifier)
            kind, answer = "ai_teacher_semantic", annotation["answer_zh"]
            rationale, limitations = annotation["rationale_zh"], annotation["limitations"]
            status = annotation["status"]
        else:
            value = objective_reference(case, sources)
            expected, kind, status = scoring_fields(value), "source_computed_objective", "resolved"
            answer, rationale = objective_answer_zh(case, value), "依据冻结字段、完整成员或精确原文区间复算；未用模型补写事实。"
            evidence = []
            if family == "exact_quote_location":
                evidence = [located_evidence(sources[case["arguments"]["record_id"]], case["arguments"])]
            limitations = ["仅证明冻结存储内容和字段，不证明原始网页完整性、外部真实性或客户统计口径已获批准。"]
        output.append({"case_id": identifier, "task_family": family, "question": case["question"],
                       "case_sha256": digest(encoded(case)), "purpose": "evaluation_reference_only",
                       "reference_kind": kind, "status": status, "expected_fields": expected,
                       "answer_zh": answer, "rationale_zh": rationale, "limitations": limitations,
                       "source_records": case["source_records"], "focal_span": case["source_span"], "evidence": evidence,
                       "teacher_model": "gpt-6.1-sol" if kind == "ai_teacher_semantic" else None,
                       "human_gold_approved": False, "runtime_enabled": False,
                       "permitted_in_training_or_prompts": False})
    if set(annotations) != used:
        raise ValueError("extra_teacher_reference_id")
    return output


def prepare(candidates, snapshot, annotation_root, out):
    out = Path(out)
    if out.exists():
        raise ValueError("output_directory_already_exists")
    cases = read_lines(candidates)
    records = normalize_records(json.loads(Path(snapshot).read_text(encoding="utf-8")))
    validate_database_identities(records)
    annotations, receipts, input_files = {}, [], [Path(candidates), Path(snapshot)]
    for family, config in FAMILIES.items():
        folder = Path(annotation_root) / config["directory"]
        annotation_file, receipt_file = folder / "references.jsonl", folder / "receipt.json"
        rows = read_lines(annotation_file)
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        full_input = Path(annotation_root) / "root/inputs" / f"{family}.jsonl"
        expected_ids = {case["case_id"] for case in cases if case["task_family"] == family}
        if (receipt.get("model") != "gpt-6.1-sol" or receipt.get("input_sha256") != digest(full_input.read_bytes())
                or set(receipt.get("full_context_read_case_ids", [])) != expected_ids
                or receipt.get("references_sha256") != digest(annotation_file.read_bytes())
                or receipt.get("human_approved") is not False):
            raise ValueError("teacher_receipt_model_input_or_read_coverage_mismatch")
        inputs = read_lines(full_input)
        if {row.get("case_id") for row in inputs} != expected_ids or len(inputs) != len(expected_ids):
            raise ValueError("teacher_input_family_membership_mismatch")
        by_case = {case["case_id"]: case for case in cases}
        by_source = {record["record_id"]: record for record in records}
        for row in inputs:
            case = by_case[row["case_id"]]
            source = by_source[case["source_records"][0]["record_id"]]
            if (row.get("question") != case["question"] or row.get("task_family") != family
                    or row.get("focal_span") != case["source_span"] or row.get("source") != case["source_records"][0]
                    or row.get("full_saved_body") != source["body"] or row.get("retrieval_ranges") != source["retrieval_ranges"]):
                raise ValueError("teacher_full_input_source_or_task_mismatch")
        if {row.get("case_id") for row in rows} != expected_ids or len(rows) != len(expected_ids):
            raise ValueError("teacher_family_membership_mismatch")
        for row in rows:
            if row["case_id"] in annotations:
                raise ValueError("duplicate_teacher_id")
            annotations[row["case_id"]] = row
        receipts.append(receipt)
        input_files.extend((annotation_file, receipt_file, full_input))
    references = compile_references(cases, records, annotations)
    summary = {"reference_cases": len(references), "source_computed_objective": sum(row["reference_kind"] == "source_computed_objective" for row in references),
               "ai_teacher_semantic": len(annotations), "semantic_resolved": sum(row["reference_kind"] == "ai_teacher_semantic" and row["status"] == "resolved" for row in references),
               "semantic_unresolved": sum(row["status"] == "unresolved" for row in references),
               "human_approved": 0, "model_fine_tuning_runs": 0, "external_api_calls": 0,
               "codex_teacher_agents": 3, "codex_initial_annotation_turns": 3,
               "codex_codebook_revision_turns": 2, "system_predictions_evaluated": 0, "accuracy": None,
               "scope": "Frozen native candidate tasks, not client24 test results or social/cross-collection performance"}
    manifest = {"schema_version": "teacher-reference-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "purpose": "evaluation_reference_only", "requested_teacher_model": "gpt-6.1-sol",
                "teacher_execution": "Three explicitly configured Codex conversation subagents; no external API dispatch or provider-model response metadata",
                "source_snapshot_sha256": digest(Path(snapshot).read_bytes()), "candidates_sha256": digest(Path(candidates).read_bytes()),
                "source_snapshot_path": str(Path(snapshot).resolve()), "input_files_sha256": {str(path.resolve()): digest(path.read_bytes()) for path in input_files},
                "rubric": FAMILIES, "summary": summary, "script_sha256": digest(Path(__file__).read_bytes()),
                "rubric_version": "teacher-task-codebook-v2",
                "rubric_review": "Before any system predictions: distinguish named sponsor people from institutional sponsor voice; classify the literal focal passage even when it is navigation/disclosure, with its non-advertising role stated separately. Original v1 annotations and compilation are preserved.",
                "client24_reference_answers_used": False, "human_gold_approved": False, "runtime_enabled": False,
                "fit_parameters_or_prompts": False, "independent_unseen": False,
                "codex_usage_cost_usd": None, "cost_note": "Conversation/account usage was not metered as an external API bill. External API count0 does not mean zero compute or account usage."}
    out.mkdir(parents=True, exist_ok=False)
    payload = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False,
                                  separators=(",", ":")).encode("utf-8") + b"\n" for row in references)
    (out / "references.jsonl").write_bytes(payload)
    manifest["references_sha256"] = digest(payload)
    (out / "manifest.json").write_bytes(encoded(manifest))
    (out / "summary.json").write_bytes(encoded(summary))
    review_rows = [{"case_id": row["case_id"], "task_family": row["task_family"], "question": row["question"],
                    "article_title": "；".join(dict.fromkeys(str(source.get("title")) for source in row["source_records"])),
                    "reference_kind": row["reference_kind"], "status": row["status"], "answer_zh": row["answer_zh"],
                    "expected_fields": json.dumps(row["expected_fields"], ensure_ascii=False),
                    "rationale_zh": row["rationale_zh"], "limitations": "；".join(row["limitations"]),
                    "human_decision": "", "reviewer": "", "review_notes": ""} for row in references]
    (out / "review.csv").write_bytes(csv_bytes(review_rows, list(review_rows[0])))
    parts = [f"<h1>AI参考集审核</h1><p>{len(references)}条参考仅用于内部评价。客观题按冻结资料复算；{len(annotations)}条语义题由gpt-6.1-sol阅读完整保存正文后判断，尚未人工审定。没有系统预测或准确率成绩。</p>"]
    family_titles = {"speaker_attribution": "谁在表达这段话", "negation_scope": "这段话否定或限制了什么",
                     "planned_vs_achieved": "这是计划、能力还是已实现结果"}
    for row in references:
        if row["reference_kind"] != "ai_teacher_semantic":
            continue
        source = row["source_records"][0]
        title, url = str(source.get("title")), safe_url(source.get("url"))
        link = f"<a href='{html.escape(url, quote=True)}'>{html.escape(title)}</a>" if url else html.escape(title)
        state = "AI局部参考，待人审" if row["status"] == "resolved" else "无法判定，待补资料"
        parts.append(f"<details><summary>{link} · {family_titles[row['task_family']]} · {state}</summary><p>{html.escape(row['question'])}</p><p><b>参考回答：</b>{html.escape(row['answer_zh'])}</p><p><b>判断理由：</b>{html.escape(row['rationale_zh'])}</p>")
        for i, evidence in enumerate(row["evidence"], 1):
            parts.append(f"<p>[{i}] 原文字符{evidence['start']}–{evidence['end']}：{html.escape(evidence.get('reason_zh', ''))}</p><pre>{html.escape(evidence['quote'])}</pre>")
        full_body = next(record["body"] for record in records if record["record_id"] == source["record_id"])
        parts.append(f"<p><b>局限：</b>{html.escape('；'.join(row['limitations']) or '保存正文及外部真实性仍未人工核验。')}</p><details><summary>查看本次判断读取的完整保存正文</summary><pre>{html.escape(full_body)}</pre></details><details><summary>评分字段与来源版本</summary><pre>{html.escape(json.dumps(row['expected_fields'], ensure_ascii=False, indent=2))}</pre><small>{html.escape(row['case_id'])} · {html.escape(source['version_id'])}</small></details></details>")
    (out / "review.html").write_text(page("AI参考集审核", "".join(parts)), encoding="utf-8")
    template = {"schema_version": "teacher-predictions-v1", "reference_manifest_sha256": digest((out / "manifest.json").read_bytes()),
                "source_snapshot_sha256": manifest["source_snapshot_sha256"],
                "run": {"kind": "system_output", "model": "TO_BE_FILLED", "prompt_sha256": "TO_BE_FILLED", "executed": False},
                "predictions": [], "note": "Populate from an actual system run. Never copy teacher expected_fields as predictions."}
    (out / "predictions.template.json").write_bytes(encoded(template))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.candidates, args.snapshot, args.annotations, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
