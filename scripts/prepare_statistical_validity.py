"""Answer source-backed tasks first, then freeze a bounded evaluation selection."""
from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from prepare_content_review import (
    csv_bytes,
    digest,
    encoded,
    normalize_records,
    page,
    validate_database_identities,
)
from prepare_teacher_reference import read_lines

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".runtime/statistical_validity_20261007"
SNAPSHOT = ROOT / ".runtime/content_source_refresh_20261006/content_review/source_snapshot.json"
OLD = ROOT / ".runtime/teacher_reference_20261006/root/prepared_02/references.jsonl"
CLIENT = ROOT / "eval/customer_metrics/content_questions.v1.json"
MISSING = {"", "unknown", "none", "null", "nan", "n/a", "na", "tbd", "-", "—", "not available"}
NATIVE_TASKS = {
    "disclosure_language": (["disclosure language"], "disclosure_language", "广告“{title}”用什么文字披露其广告身份？按原Excel逐字给出。", "client24:Q01"),
    "disclosure_location": (["disclosure description"], "disclosure_location", "原Excel怎样描述广告“{title}”披露文字的位置？", "client24:Q01-adaptation"),
    "sponsor_publisher": (["sponsor", "publisher"], None, "广告“{title}”记录的赞助方和媒体分别是谁？按原Excel字段回答。", "client-email:outlet-sponsors/RQ2"),
    "publication_date": (["date"], "excel_publication_date", "原Excel记录广告“{title}”的发布日期是什么？", "PD:RQ3"),
    "original_source": (["url"], "original_url", "广告“{title}”的原始网址是什么？按原Excel给出链接。", "PD:RQ6-source-access"),
    "collection_search_term": (["keyword"], "collection_search_term", "收集广告“{title}”时使用的搜索词是什么？它不等同于赞助方。", "user:collection-filters/data-method-extension"),
}


def substantive(value):
    return isinstance(value, str) and value.strip().casefold() not in MISSING


def name(value):
    return value.casefold() if isinstance(value, str) and value else "Unknown"


def record_year(record):
    date = record.get("published_at")
    return date[:4] if date else "Unknown date"


def groups(records, field):
    counts = Counter((record_year(r) if field == "year" else r.get(field) or "Unknown") for r in records)
    return [{field: key, "count": value} for key, value in sorted(counts.items())]


def members_digest(records):
    ids = [r["record_id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_member_identity")
    return digest(encoded(sorted(ids)))


def verify_excel_export(rows, root=ROOT):
    """Read original cells again; an exported URL alone is not answer evidence."""
    import openpyxl

    by_file = {}
    for row in rows:
        path = root / row["file"]
        if path not in by_file:
            by_file[path] = (digest(path.read_bytes()), openpyxl.load_workbook(path, read_only=True, data_only=True))
        file_hash, workbook = by_file[path]
        if file_hash != row["sha256"]:
            raise ValueError("original_excel_changed")
        sheet = workbook[row["sheet"]]
        values = next(sheet.iter_rows(min_row=row["row"], max_row=row["row"], values_only=True))
        for cell in row["cells"].values():
            from openpyxl.utils.cell import (
                column_index_from_string,
                coordinate_from_string,
            )
            col, line = coordinate_from_string(cell["coordinate"])
            actual = values[column_index_from_string(col) - 1]
            if line != row["row"] or json.loads(json.dumps(actual, default=str)) != cell["value"]:
                raise ValueError("excel_cell_export_mismatch")
    for _, workbook in by_file.values():
        workbook.close()


def native_pool(excel_rows, native):
    by_url = {}
    for row in excel_rows:
        key = row["url"].strip()
        if key in by_url:
            raise ValueError("ambiguous_excel_url")
        by_url[key] = row
    pool = []
    for record in native:
        row = by_url.get(record["url"])
        for family, (fields, output_key, wording, origin) in NATIVE_TASKS.items():
            identifier = "SV-N-" + digest(encoded([family, record["record_id"]]))[:20]
            cells = {field: row["cells"].get(field) for field in fields} if row else {}
            available = bool(row) and all(cell and substantive(cell["value"]) for cell in cells.values())
            expected = None
            if available:
                values = {field: cells[field]["value"] for field in fields}
                expected = {output_key: values[fields[0]]} if output_key else values
            pool.append({"case_id": identifier, "task_family": family, "dataset_scope": "native",
                         "question": wording.format(title=record["title"]), "provenance": origin,
                         "source_group": record["record_id"], "reference_kind": "source_computed_objective",
                         "answer_status": "available" if available else "no_substantive_excel_answer",
                         "expected_fields": expected, "substantive_excel_answer": available,
                         "source_evidence": [{"file": row["file"], "sha256": row["sha256"], "sheet": row["sheet"],
                                              "row": row["row"], "cells": cells}] if row else [],
                         "member_ids": [record["record_id"]], "human_gold_approved": False,
                         "reference_scope": "Original Excel metadata; does not independently verify a current webpage."})
    return pool


def verify_social_export(records, info):
    """Compare every exported observation and group with the uploaded JSON."""
    source = Path(info["source"])
    if digest(source.read_bytes()) != info["source_zip_sha256"]:
        raise ValueError("original_social_source_changed")
    with ZipFile(source) as archive:
        raw = archive.read(info["source_member"])
    if digest(raw) != info["source_member_sha256"]:
        raise ValueError("original_social_member_changed")
    original = json.loads(raw)
    seen, urls = set(), set()
    for record in records:
        url = record["url"]
        identity = "social-post:" + digest(("twitter\n" + url).encode())
        if url in urls or record["record_id"] != identity:
            raise ValueError("social_group_identity_mismatch")
        urls.add(url)
        for observation in record["observations"]:
            number = observation["source_row"]
            if number in seen or not 1 <= number <= len(original):
                raise ValueError("social_observation_identity_mismatch")
            seen.add(number)
            row = original[number - 1]
            supplied_urls = row["urls"]["post_url"]
            supplied_urls = [supplied_urls] if isinstance(supplied_urls, str) else supplied_urls
            canonical = set()
            for supplied in supplied_urls:
                parsed = urlsplit(supplied)
                match = re.fullmatch(r"/([A-Za-z0-9_]+)/status/(\d+)/?", parsed.path)
                if (match and parsed.hostname in {"twitter.com", "www.twitter.com", "x.com", "www.x.com"}
                        and not parsed.query and not parsed.fragment):
                    canonical.add("https://twitter.com/" + match[1].lower() + "/status/" + match[2])
            if canonical != {url}:
                raise ValueError("social_source_url_membership_mismatch")
            timestamp, date = row.get("date_time", {}).get("published_at"), None
            try:
                parsed_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed_date.tzinfo is not None:
                    date = parsed_date.astimezone(timezone.utc).date().isoformat()
            except (AttributeError, TypeError, ValueError):
                pass
            channel = row.get("channel") or {}
            expected = {"source_record_id": "junkipedia:" + row["id"], "source_row": number,
                        "raw_filename": info["source_member"], "company": row.get("parent_entity") or "",
                        "account": channel.get("name") or "", "username": channel.get("username") or "",
                        "account_url": channel.get("url") or "", "published_at": date,
                        "raw_publication_timestamp": timestamp, "body": row["post_text"],
                        "body_sha256": digest(row["post_text"].encode()), "original_urls": supplied_urls}
            if observation != expected:
                raise ValueError("social_source_observation_mismatch")
        if not record["observations"]:
            raise ValueError("empty_social_source_group")
        values = {field: sorted({o[field] for o in record["observations"]}, key=lambda v: "" if v is None else v)
                  for field in ("company", "account", "published_at", "body_sha256", "username")}
        flags = [field for field, variants in values.items() if len(variants) > 1]
        if values != record["observed_values"] or flags != record["conflicting_fields"]:
            raise ValueError("social_source_variants_mismatch")
        for field in ("company", "account", "published_at"):
            projected = values[field][0] if len(values[field]) == 1 else None
            if field != "published_at":
                projected = projected or "Unknown"
            if record[field] != projected:
                raise ValueError("social_conflict_projection_mismatch")
    if (seen != set(range(1, len(original) + 1)) or len(original) != info["raw_observations"]
            or len(records) != info["unique_posts"]):
        raise ValueError("social_source_membership_mismatch")


def select_excel(pool, each=12):
    if (len({c["case_id"] for c in pool}) != len(pool)
            or len({(c["task_family"], c["source_group"]) for c in pool}) != len(pool)):
        raise ValueError("duplicate_native_candidate_identity")
    selected, used = [], set()
    for family in NATIVE_TASKS:
        eligible = sorted((c for c in pool if c["task_family"] == family and c["answer_status"] == "available"), key=lambda c: c["case_id"])
        chosen = [c for c in eligible if c["source_group"] not in used][:each]
        if len(chosen) != each:
            raise ValueError("insufficient_distinct_source_excel_answers")
        selected.extend(chosen)
        used.update(c["source_group"] for c in chosen)
    return selected


def source_case(family, scope, question, expected, records, provenance, arguments=None):
    members_digest(records)
    args = arguments or {}
    return {"case_id": "SV-" + digest(encoded([family, scope, args, question]))[:20], "task_family": family,
            "dataset_scope": scope, "question": question, "provenance": provenance,
            "reference_kind": "source_computed_objective", "answer_status": "available",
            "expected_fields": expected, "substantive_excel_answer": False,
            "source_group": str(args), "member_ids": sorted(r["record_id"] for r in records),
            "arguments": args, "human_gold_approved": False,
            "reference_scope": "Frozen complete selected membership; company posts are not verified paid ads."}


def social_cases(social, each=8):
    companies = sorted({name(r["company"]) for r in social if substantive(r.get("company"))})
    years = sorted({record_year(r) for r in social if r.get("published_at")})
    if len(companies) < each or len(years) < each:
        raise ValueError("insufficient_social_strata")
    selected_companies = sorted(companies, key=lambda c: digest(c.encode()))[:each]
    selected_years = sorted(years, key=lambda c: digest(c.encode()))[:each]
    result = []
    for company in selected_companies:
        records = [r for r in social if name(r.get("company")) == company]
        display = next(r["company"] for r in records)
        result.append(source_case("social_company_count", "social", f"资料中{display}有多少个唯一社交帖子？", {"unique_company_posts": len(records)}, records, "PD:RQ5/RQ6-count-adaptation", {"company_casefold": company}))
        result.append(source_case("social_accounts", "social", f"资料中{display}有哪些账号？每个账号各有多少个唯一帖子？", {"accounts": groups(records, "account"), "total_unique_posts": len(records)}, records, "PD:RQ5-account-exploration", {"company_casefold": company}))
        company_years = sorted({record_year(r) for r in records if r.get("published_at")})
        if len(company_years) < 2:
            raise ValueError("two_distinct_social_periods_required")
        first, last = company_years[0], company_years[-1]
        counts = Counter(record_year(r) for r in records)
        result.append(source_case("social_period_comparison", "social", f"比较{display}在{first}年和{last}年的唯一帖子数量，分别是多少，后期比前期多多少？", {"period_counts": [{"year": y, "count": counts[y]} for y in (first, last)], "difference_second_minus_first": counts[last] - counts[first]}, records, "PD:RQ3-method-adapted-to-RQ5", {"company_casefold": company, "years": [first, last]}))
    for year in selected_years:
        records = [r for r in social if record_year(r) == year]
        result.append(source_case("social_year_count", "social", f"资料中{year}年有多少个唯一公司社交帖子？", {"year": year, "unique_company_posts": len(records)}, records, "PD:RQ5-date-filter", {"year": year}))
    return result


def combined_cases(native, social):
    common = sorted({name(r["company"]) for r in native if r.get("company")} & {name(r["company"]) for r in social if r.get("company")})
    if len(common) < 7:
        raise ValueError("insufficient_cross_collection_companies")
    result = []
    for company in common[:7]:
        nr = [r for r in native if name(r.get("company")) == company]
        sr = [r for r in social if name(r.get("company")) == company]
        display = next(r["company"] for r in sr)
        args = {"company_casefold": company}
        result.append(source_case("combined_company_counts", "combined", f"{display}分别有多少条可计数原生广告和多少个唯一社交帖子？分开报告。", {"native_ads": len(nr), "unique_company_posts": len(sr)}, nr + sr, "user:unified-collections/PD:RQ1,RQ6", args))
        result.append(source_case("combined_relationships", "combined", f"{display}的原生广告出现在哪些媒体，社交帖子来自哪些账号？分别列出数量。", {"native_publishers": groups(nr, "publisher"), "social_accounts": groups(sr, "account"), "native_ads": len(nr), "unique_company_posts": len(sr)}, nr + sr, "client-email:company-publishers/PD:RQ2,RQ5,RQ6", args))
        result.append(source_case("combined_years", "combined", f"按年份分别统计{display}的原生广告与社交帖子；原生未知日期另列。", {"native_years": groups(nr, "year"), "social_years": groups(sr, "year"), "native_unknown_dates": sum(not r["published_at"] for r in nr)}, nr + sr, "PD:RQ3/RQ6-and-user:unified-collections", args))
    result.append(source_case("combined_collection_counts", "combined", "当前冻结资料包含多少条可计数原生广告和多少个唯一公司社交帖子？分别报告，不合成付费广告总数。", {"native_ads": len(native), "unique_company_posts": len(social)}, native + social, "user:unified-collections/PD:RQ6"))
    for company in ("exxonmobil", "shell"):
        if company not in common:
            raise ValueError("requested_comparison_company_missing")
        nr = [r for r in native if name(r.get("company")) == company]
        sr = [r for r in social if name(r.get("company")) == company]
        years = ["2020", "2024"]
        nc, sc = Counter(record_year(r) for r in nr), Counter(record_year(r) for r in sr)
        result.append(source_case("combined_period_comparison", "combined", f"比较{company}在2020年与2024年的原生广告及社交帖子数量；分类型报告，两期差值是多少？", {"native_period_counts": [{"year": y, "count": nc[y]} for y in years], "social_period_counts": [{"year": y, "count": sc[y]} for y in years], "native_difference": nc[years[1]] - nc[years[0]], "social_difference": sc[years[1]] - sc[years[0]], "native_unknown_dates": sum(not r["published_at"] for r in nr)}, nr + sr, "PD:RQ3/RQ6-and-user:two-period-comparison", {"company_casefold": company, "years": years}))
    return result


def controls(native_all, social):
    result = []
    unavailable = [r for r in native_all if not r["payload"]["retrievable"] or not r["body"].strip()][:2]
    if len(unavailable) != 2:
        raise ValueError("unavailable_text_control_missing")
    for row in unavailable:
        record = {"record_id": row["record_id"]}
        result.append(source_case("unavailable_text", "native", f"保存资料能否判断“{row['payload']['title']}”是否包含相关减排主张？", {"content_status": "unknown", "must_infer_absence": False}, [record], "user:missing-information/RQ6", {"record_id": record["record_id"]}))
    for field, task, question, expected in (
        ("published_at", "unknown_stored_date", "当前冻结记录中的发布日期是否已知？", {"stored_date_status": "unknown"}),
        ("archive_url", "missing_archive", "当前冻结记录是否提供归档网址？未提供能否断言网上没有归档？", {"archive_supplied": False, "absence_on_internet_verified": False}),
    ):
        row = next(r for r in native_all if r["active"] and not r["payload"].get(field))
        result.append(source_case(task, "native", row["payload"]["title"] + "：" + question, expected, [{"record_id": row["record_id"]}], "user:missing-information/source-access", {"record_id": row["record_id"]}))
    for field in ("company", "account", "body_sha256"):
        row = next(r for r in social if field in r["conflicting_fields"])
        expected = {"field": field, "source_disagreement": True, "adjudicated": False, "source_observations": len(row["observations"])}
        result.append(source_case("source_disagreement", "social", f"原帖{row['url']}的{field}来源值有冲突时，是否可以任选一个作为已确认答案？", expected, [row], "user:preserve-source-differences/RQ6", {"record_id": row["record_id"], "field": field}))
    row = social[0]
    result.append(source_case("paid_ad_identity", "social", "这些收集的公司社交帖子是否已被验证全部属于付费广告？", {"paid_ad_status": "unknown", "all_posts_verified_paid_ads": False}, [row], "client:RQ5-scope/user:post-identity"))
    return result


def write_lines(path, rows):
    path.write_bytes(b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode() + b"\n" for row in rows))


def readable_answer(case):
    labels = {"disclosure_language": "披露广告身份的文字", "disclosure_location": "披露文字的位置说明",
              "sponsor": "赞助方", "publisher": "媒体", "excel_publication_date": "原Excel发布日期",
              "original_url": "原始网址", "collection_search_term": "收集搜索词",
              "unique_company_posts": "唯一公司帖子数", "total_unique_posts": "唯一帖子总数",
              "native_ads": "冻结名单内可计数原生广告数", "year": "年份", "accounts": "账号及帖子数",
              "native_publishers": "原生广告媒体及篇数", "social_accounts": "社交账号及帖子数",
              "native_years": "原生广告逐年篇数", "social_years": "社交帖子逐年数量",
              "native_unknown_dates": "原生广告日期未知篇数", "period_counts": "两期帖子数量",
              "native_period_counts": "两期原生广告篇数", "social_period_counts": "两期社交帖子数量",
              "difference_second_minus_first": "后期减前期的帖子差值", "native_difference": "原生篇数后期减前期",
              "social_difference": "帖子数后期减前期", "content_status": "保存正文能否判断内容",
              "must_infer_absence": "能否据此断言主张不存在", "stored_date_status": "冻结记录日期状态",
              "archive_supplied": "保存记录是否提供归档", "absence_on_internet_verified": "是否已核查网上无归档",
              "field": "有冲突的字段", "source_disagreement": "原观察是否存在差异",
              "adjudicated": "是否已经裁决", "source_observations": "保留的原观察份数",
              "paid_ad_status": "付费广告身份", "all_posts_verified_paid_ads": "是否全部核实为付费广告"}
    parts = []
    for field, value in case["expected_fields"].items():
        if isinstance(value, list):
            rendered = "；".join(" / ".join(str(v) for k, v in row.items() if k != "count") + f"：{row['count']}" for row in value)
        elif type(value) is bool:
            rendered = "是" if value else "否"
        elif value == "unknown":
            rendered = "未知，不能由现有资料确定"
        elif field == "field":
            rendered = {"company": "公司归属", "account": "账号名称", "body_sha256": "保存正文版本"}.get(value, value)
        else:
            rendered = str(value)
        parts.append(labels.get(field, field) + "：" + rendered)
    return "\n".join(parts)


def prepare(out, base=BASE, root=ROOT):
    out = Path(out)
    if out.exists():
        raise ValueError("output_already_exists")
    rows = read_lines(base / "excel/native_excel_rows.jsonl")
    verify_excel_export(rows, root)
    social = read_lines(base / "social/social_records.jsonl")
    social_info = json.loads((base / "social/social_summary.json").read_text(encoding="utf-8"))
    verify_social_export(social, social_info)
    snapshot = root / SNAPSHOT.relative_to(ROOT)
    old_path, client = root / OLD.relative_to(ROOT), root / CLIENT.relative_to(ROOT)
    records = normalize_records(json.loads(snapshot.read_text(encoding="utf-8")))
    validate_database_identities(records)
    native = [{"record_id": r["record_id"], "url": r["payload"]["url"], "title": r["payload"]["title"],
               "company": r["payload"].get("sponsor"), "publisher": r["payload"].get("publisher"),
               "published_at": r["payload"].get("published_at")} for r in records if r["active"] and r["payload"]["countable"]]
    pool = native_pool(rows, native)
    main = select_excel(pool) + social_cases(social) + combined_cases(native, social)
    control = controls(records, social)
    if len(main) != 128 or len(control) != 8 or sum(c["substantive_excel_answer"] for c in main) != 72:
        raise ValueError("declared_strata_quota_not_met")
    if sum(c["substantive_excel_answer"] for c in main) * 2 < len(main) + len(control):
        raise ValueError("half_excel_rule_not_met_including_controls")
    old = read_lines(old_path)
    selection = json.loads((base / "semantic/selection.json").read_text(encoding="utf-8"))
    if (selection["parent_sha256"] != digest(old_path.read_bytes())
            or selection["parent_total_membership"] != [row["case_id"] for row in old]):
        raise ValueError("semantic_selection_parent_mismatch")
    selected_rows = selection["selection"]
    selected_by_id = {c["case_id"]: c for c in selected_rows}
    if len(selected_by_id) != len(selected_rows):
        raise ValueError("duplicate_semantic_selection")
    sem_main, sem_control, sem_pending, history = [], [], [], []
    for row in old:
        if row["reference_kind"] == "source_computed_objective":
            role, reason = "extended_regression", "原生字段／位置／统计回归保留；不占新的双集合用户主任务分母。"
        else:
            chosen = selected_by_id[row["case_id"]]
            if chosen["case_sha256"] != row["case_sha256"]:
                raise ValueError("semantic_selection_case_mismatch")
            role, reason = chosen["selection"], chosen["reason_zh"]
            {"keep_main": sem_main, "control_non_article": sem_control, "unresolved_pending": sem_pending}[role].append(row)
        history.append({"case_id": row["case_id"], "question": row["question"], "new_role": role, "reason": reason})
    if len(selected_by_id) != 120 or (len(sem_main), len(sem_control), len(sem_pending)) != (113, 5, 2):
        raise ValueError("semantic_scope_selection_mismatch")
    out.mkdir(parents=True, exist_ok=False)
    (out / "members").mkdir()
    for case in main + control:
        ids = case.pop("member_ids")
        path = f"members/{case['case_id']}.json"
        payload = encoded(ids)
        (out / path).write_bytes(payload)
        case["member_evidence"] = {"path": path, "count": len(ids), "sha256": digest(payload)}
        case["runtime_enabled"] = False
        case["purpose"] = "evaluation_reference_only"
        case["reference_answer_zh"] = readable_answer(case)
    write_lines(out / "objective_answers.jsonl", main)
    write_lines(out / "objective_controls.jsonl", control)
    write_lines(out / "native_candidate_answers.jsonl", pool)
    write_lines(out / "semantic_main.jsonl", sem_main)
    write_lines(out / "semantic_controls.jsonl", sem_control)
    write_lines(out / "pending.jsonl", sem_pending)
    write_lines(out / "old547_selection.jsonl", history)
    review = [{"case_id": c["case_id"], "scope": c["dataset_scope"], "task": c["task_family"],
               "question": c["question"], "answer": c["reference_answer_zh"],
               "excel_substantive": c["substantive_excel_answer"], "origin": c["provenance"],
               "source": json.dumps(c.get("source_evidence") or c["member_evidence"], ensure_ascii=False),
               "human_decision": "", "reviewer": ""} for c in main + control]
    (out / "review.csv").write_bytes(csv_bytes(review, list(review[0])))
    body = ["<h1>统计有效性：题目与已答参考</h1><p>128条客观主任务＋113条AI语义主任务。8条客观控制、5条语言控制另列，2条参考暂停。没有真实系统准确率。</p>"]
    for heading, cases in (("客观主任务：资料已答", main), ("缺失／冲突控制：不计入主任务分母", control)):
        body.append(f"<h2>{heading}（{len(cases)}题）</h2>")
        for c in cases:
            cells = json.dumps(c.get("source_evidence") or c["member_evidence"], ensure_ascii=False, indent=2)
            body.append(f"<details><summary>{html.escape(c['question'])}</summary><p>来源任务：{html.escape(c['provenance'])}</p><p>范围：{html.escape(c['dataset_scope'])}；原Excel实质答案：{c['substantive_excel_answer']}</p><pre>{html.escape(c['reference_answer_zh'])}</pre><details><summary>原单元格或完整成员证据</summary><pre>{html.escape(cells)}</pre></details></details>")
    for heading, cases in (("语义主任务：AI参考，未人审", sem_main), ("语言控制：单列", sem_control), ("参考暂停：不计主任务，原问题保留", sem_pending)):
        body.append(f"<h2>{heading}（{len(cases)}题）</h2>")
        for c in cases:
            title = c["source_records"][0]["title"]
            task = {"negation_scope": "判断否定或限制的具体对象", "time_status": "区分计划、正在进行与已实现", "speaker_attribution": "判断谁在表达这段话"}.get(c["task_family"], c["question"])
            body.append(f"<details><summary>{html.escape(title + '：' + task)}</summary><p>{html.escape(c['question'])}</p><blockquote>{html.escape(c['focal_span']['quote'])}</blockquote><p>{html.escape(c['answer_zh'])}</p><p>判断理由：{html.escape(c['rationale_zh'])}</p><details><summary>保存原文证据及范围限制</summary>")
            for evidence in c["evidence"]:
                body.append(f"<blockquote>{html.escape(evidence['quote'])}</blockquote>")
            body.append(f"<p>{html.escape('；'.join(c['limitations']))}</p></details></details>")
    (out / "review.html").write_text(page("统计有效性答题审核", "".join(body)), encoding="utf-8")
    summary = {"objective_main": len(main), "native_excel_main": 72, "social_main": 32, "combined_main": 24,
               "objective_controls": len(control), "excel_share_objective_main": 72 / 128,
               "excel_share_including_objective_controls": 72 / 136, "semantic_main": len(sem_main),
               "semantic_controls": len(sem_control), "reference_pending": len(sem_pending),
               "total_main": len(main) + len(sem_main), "human_approved": 0,
               "native_pool_answer_status": dict(Counter(c["answer_status"] for c in pool)),
               "native_record_population": len(native), "social_unique_posts": len(social),
               "social_observations": social_info["raw_observations"],
               "system_predictions": 0, "system_accuracy": None, "external_api_calls": 0,
               "inference_supported": "Descriptive source-backed task packet, not independent generalization or client acceptance"}
    (out / "summary.json").write_bytes(encoded(summary))
    inputs = [base / "excel/native_excel_rows.jsonl", base / "excel/summary.json", base / "social/social_records.jsonl",
              base / "social/social_summary.json", base / "semantic/selection.json", snapshot, old_path, client]
    manifest = {"schema_version": "statistical-validity-packet-v1", "summary": summary,
                "source_inputs_sha256": {str(p.resolve()): digest(p.read_bytes()) for p in inputs},
                "script_sha256": digest(Path(__file__).read_bytes()), "selection_uses_system_predictions": False,
                "runtime_enabled": False, "training_performed": False,
                "client24_unchanged_sha256": digest(client.read_bytes()),
                "selected_scope": "Native workbook metadata plus frozen accepted native roster; raw social JSON unique-post policy; existing AI language references separated.",
                "files_sha256": {p.relative_to(out).as_posix(): digest(p.read_bytes()) for p in out.rglob('*') if p.is_file()}}
    (out / "manifest.json").write_bytes(encoded(manifest))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
