"""Compare saved native-ad bodies with original CLAIMS input, without importing.

This is a private, offline preparation step. Matching text, longer text and a
clean quality check do not approve a source, complete page or classification.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import prepare_claims_input_review as original

from observatory.chunking import retrieval_spans
from observatory.claims_linkage import load_input_bytes, validate_retained_input_bytes
from observatory.evaluate import EvaluationInvalid, canonical_digest, strict_json_loads
from observatory.quality import inspect_body

FORMAT = "native-body-review-preparation-v1"
MAX_PACKET_BYTES = 256 * 1024 * 1024
ESSENTIAL_INPUTS = (
    "source_archive.zip", "source_workbook.xlsx", "input_paragraphs.csv",
    "cleaned_paragraphs.csv", "cleaning_notebook.ipynb", "source_inventory.json",
    "article_lineage.json", "current_source_snapshot.json", "preparation_summary.json",
)
METADATA_FIELDS = (
    "record_id", "dataset", "url", "publisher", "title", "published_at", "sponsor",
    "keyword", "platform", "account", "disclosure", "archive_url", "countable",
)
PRIORITY_LABELS = {
    0: "视频占位文本", 1: "已有截断标记", 2: "保留段落未完整定位",
    3: "当前记录不可检索", 4: "保留输入均可定位", 5: "没有唯一当前 URL 记录",
    6: "无历史保留输入（覆盖不适用）",
}


def packet_path(root, name):
    """Accept only relative manifest paths that remain inside this packet."""
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or name.startswith("/") or any(p in {"", ".", ".."} for p in name.split("/"))):
        raise ValueError("unsafe_packet_artifact_path")
    path = root.joinpath(*PurePosixPath(name).parts)
    if any(p.is_symlink() for p in (path, *path.parents) if p == root or root in p.parents):
        raise ValueError("symlink_packet_artifact")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("packet_artifact_outside_root")
    return path


def _unique_rows(rows, key):
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError("packet_rows_required")
    values = [r.get(key) for r in rows]
    if any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
        raise ValueError("unique_packet_row_ids_required")
    return {r[key]: r for r in rows}


def load_source_packet(source_packet):
    try:
        return _load_source_packet(source_packet)
    except EvaluationInvalid as exc:
        raise ValueError(str(exc)) from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid_source_packet_structure") from exc


def _load_source_packet(source_packet):
    """Check hashes and underlying joins, then use only the frozen bytes."""
    root = Path(source_packet)
    manifest_path = packet_path(root, "packet_manifest.json")
    manifest_bytes = original.read_bytes(manifest_path)
    manifest = strict_json_loads(manifest_bytes)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != original.FORMAT or manifest.get("complete") is not True
            or manifest.get("source_associations_approved") is not False
            or manifest.get("labels_published") is not False):
        raise ValueError("complete_pending_source_packet_required")
    hashes = manifest.get("artifacts")
    if (not isinstance(hashes, dict) or len(hashes) > 5000 or "packet_manifest.json" in hashes
            or not set(ESSENTIAL_INPUTS) <= set(hashes)):
        raise ValueError("complete_source_packet_artifacts_required")
    files, paths, total = {}, {}, 0
    for name, fingerprint in hashes.items():
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("invalid_packet_artifact_sha256")
        path = packet_path(root, name)
        data = original.read_bytes(path)
        total += len(data)
        if total > MAX_PACKET_BYTES:
            raise ValueError("source_packet_too_large")
        if original.digest(data) != fingerprint:
            raise ValueError("source_packet_artifact_changed")
        files[name], paths[name] = data, path

    workbook, sources, _ = original.read_manual_archive(files["source_archive.zip"])
    if workbook != files["source_workbook.xlsx"]:
        raise ValueError("workbook_differs_from_source_archive")
    _, metadata = original.read_metadata(workbook)
    if set(metadata) != set(sources):
        raise ValueError("article_filename_and_metadata_id_sets_differ")
    settings = original.notebook_settings(files["cleaning_notebook.ipynb"])
    paragraphs = load_input_bytes(files["input_paragraphs.csv"])
    validate_retained_input_bytes(paragraphs, files["cleaned_paragraphs.csv"])
    selected, cleaned = defaultdict(list), defaultdict(list)
    for paragraph in paragraphs:
        selected[paragraph.article_id].append(paragraph)
    for row in csv.DictReader(io.StringIO(files["cleaned_paragraphs.csv"].decode("utf-8-sig"), newline="")):
        cleaned[row["id"]].append(row["text"])
    if not set(selected) <= set(sources) or not set(cleaned) <= set(sources):
        raise ValueError("input_article_not_in_source_archive")
    inventory = _unique_rows(strict_json_loads(files["source_inventory.json"]), "upstream_article_id")
    groups = _unique_rows(strict_json_loads(files["article_lineage.json"]), "upstream_article_id")
    if set(inventory) != set(sources) or set(groups) != set(selected):
        raise ValueError("source_inventory_or_selected_groups_differ")
    current_by_url = original.load_current_snapshot(files["current_source_snapshot.json"])
    snapshot = strict_json_loads(files["current_source_snapshot.json"])
    # The previous loader checks body/version identity. This check also binds
    # optional convenience fields to the payload instead of trusting both.
    for row in snapshot["records"]:
        payload = row["payload"]
        if any(type(payload.get(k)) is not bool for k in ("countable", "retrievable")) or type(row["active"]) is not bool:
            raise ValueError("explicit_current_eligibility_required")
        allowed = retrieval_spans(payload["body"], retrieval_ranges=payload.get("retrieval_ranges"),
                                  retrieval_end=payload.get("retrieval_end"))
        if ("retrieval_ranges" in row and row["retrieval_ranges"] != [list(span) for span in allowed]
                or "payload_sha256" in row and row["payload_sha256"] != canonical_digest(payload)):
            raise ValueError("snapshot_convenience_fields_differ")

    for article_id, source in sources.items():
        raw_paragraphs, kept = original.historical_cleaning(source["text"], settings)
        expected = {
            "upstream_article_id": article_id, "member": source["member"],
            "raw_bytes_sha256": original.digest(source["bytes"]), "encoding": "utf-8",
            "decoded_text_sha256": original.digest(source["text"].encode("utf-8")),
            "source_nonempty_paragraphs": len(raw_paragraphs), "historical_kept_paragraphs": len(kept),
            "reproduces_cleaned_sequence": kept == cleaned.get(article_id, []),
            "provided_metadata": metadata[article_id],
        }
        if inventory[article_id] != expected or not expected["reproduces_cleaned_sequence"]:
            raise ValueError("inventory_differs_from_frozen_source_recipe")
        if article_id not in groups:
            continue
        group = groups[article_id]
        if any(group.get(k) != v for k, v in expected.items()):
            raise ValueError("lineage_differs_from_source_inventory")
        if files.get(f"original/{article_id}.txt") != source["bytes"]:
            raise ValueError("original_text_differs_from_source_archive")
        locations, in_order = original.source_locations(source["text"], selected[article_id])
        if (group.get("paragraphs") != locations or group.get("supplied_paragraphs") != len(locations)
                or group.get("all_retained_paragraphs_in_order") is not in_order
                or group.get("located_paragraphs") != sum(bool(p["locations"]) for p in locations)):
            raise ValueError("lineage_paragraphs_or_positions_differ")
        values = metadata[article_id]["values"]
        candidates = (current_by_url.get(values["url"], []) if isinstance(values["url"], str)
                      and "url" not in metadata[article_id]["formula_fields"] else [])
        if group.get("current_exact_url_candidates") != candidates:
            raise ValueError("lineage_current_url_candidates_differ")
        if (group.get("url_identity_review") != "pending" or group.get("source_association_approved") is not False
                or group.get("publication_status") != "hold" or group.get("classification_semantic_review") != "pending"
                or group.get("original_page_completeness") != "unknown"
                or group.get("input_is_complete_original_article") is not False):
            raise ValueError("pending_source_decisions_required")
    preparation = strict_json_loads(files["preparation_summary.json"])
    source_names = ("source_archive.zip", "input_paragraphs.csv", "cleaned_paragraphs.csv",
                    "cleaning_notebook.ipynb", "current_source_snapshot.json")
    if (preparation.get("source_file_sha256") != {name: original.digest(files[name]) for name in source_names}
            or preparation.get("cleaning_settings") != settings
            or preparation.get("projection_contract") != original.projection_contract()
            or preparation.get("workbook_sha256") != original.digest(workbook)
            or preparation.get("source_articles") != len(sources)
            or preparation.get("metadata_records") != len(metadata)
            or preparation.get("selected_article_groups") != len(groups)
            or preparation.get("selected_input_paragraphs") != len(paragraphs)):
        raise ValueError("preparation_summary_differs_from_frozen_inputs")
    return {"files": files, "paths": paths, "manifest_bytes": manifest_bytes,
            "manifest_sha256": original.digest(manifest_bytes), "snapshot": snapshot,
            "groups": groups, "inventory": inventory, "sources": sources, "paragraphs": selected,
            "manifest_path": manifest_path}


def select_article_ids(packet, article_ids=None):
    """Validate an explicit source scope without inventing sampled CLAIMS groups."""
    if article_ids is None:
        return sorted(packet["groups"], key=int)
    if (not isinstance(article_ids, list) or not article_ids
            or any(not isinstance(aid, str) or aid not in packet["inventory"] for aid in article_ids)):
        raise ValueError("selected_article_ids_must_name_verified_sources")
    if len(set(article_ids)) != len(article_ids):
        raise ValueError("duplicate_selected_article_id")
    return sorted(article_ids, key=int)


def selection_fields(packet, article_ids):
    with_input = sum(bool(packet["paragraphs"].get(aid)) for aid in article_ids)
    return {"selected_article_ids": article_ids,
            "source_articles_with_retained_input": with_input,
            "source_articles_without_retained_input": len(article_ids) - with_input}


def validate_comparison_targets(comparisons):
    """One source proposal per current record; do not silently choose between texts."""
    record_ids = [c["current_record"]["record_id"] for c in comparisons if c["current_record"] is not None]
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("duplicate_selected_target_record")


def ordered_coverage_counts(comparisons):
    matched = [c for c in comparisons if c["current_record"] is not None]
    complete = [c for c in matched if c["supplied_paragraphs"] and c["current_all_retained_in_order"] is True]
    retrievable = [c for c in complete if c["current_record"]["payload"]["retrievable"]]
    usable = [c for c in matched if c["supplied_paragraphs"] and c["current_all_usable_retained_in_order"] is True]
    return {"all_retained_in_order_current_groups": len(complete),
            "all_retained_in_order_retrievable_groups": len(retrievable),
            "all_retained_in_order_retrievable_paragraphs": sum(c["supplied_paragraphs"] for c in retrievable),
            "all_usable_retained_in_order_current_groups": len(usable),
            "all_usable_retained_in_order_current_paragraphs": sum(c["supplied_paragraphs"] for c in usable)}


def compare_group(packet, article_id, current_by_url):
    group, source = packet["inventory"][article_id], packet["sources"][article_id]
    inputs = packet["paragraphs"].get(article_id, [])
    lineage = packet["groups"].get(article_id)
    url = group["provided_metadata"]["values"]["url"]
    candidates = current_by_url.get(url, []) if isinstance(url, str) and "url" not in group["provided_metadata"]["formula_fields"] else []
    current = candidates[0] if len(candidates) == 1 else None
    rows, ordered, ranges = [], None, []
    payload = current["payload"] if current is not None else None
    if current is not None:
        if inputs:
            rows, ordered = original.source_locations(current["body"], inputs)
        ranges = retrieval_spans(current["body"], retrieval_ranges=payload.get("retrieval_ranges"),
                                 retrieval_end=payload.get("retrieval_end"))
        for paragraph in rows:
            for span in paragraph["locations"]:
                inside = any(start <= span["start"] < span["end"] <= end for start, end in ranges)
                span["inside_declared_retrieval_range"] = inside
                span["usable_under_current_retrieval"] = payload["retrievable"] and inside
    usable_in_order = original._ordered_occurrences([
        [SimpleNamespace(start=s["start"], end=s["end"]) for s in p["locations"]
         if s["usable_under_current_retrieval"]] for p in rows
    ]) if current and inputs else None
    candidate_issues = [i.model_dump(mode="json") for i in inspect_body(source["text"])]
    current_issues = [i.model_dump(mode="json") for i in inspect_body(current["body"])] if current else []
    stored_issues = payload.get("issues", []) if payload else []
    codes = {i["code"] for i in current_issues + stored_issues}
    unlocated = [p["input_id"] for p in rows if not p["locations"]]
    differences = []
    if payload is not None:
        for field in ("publisher", "title", "sponsor"):
            supplied = group["provided_metadata"]["values"].get(field)
            if supplied != payload.get(field):
                differences.append({"field": field, "current": payload.get(field), "supplied": supplied,
                                    "resolution": "pending_no_metadata_override"})
    flags = []
    if "body_video_placeholder" in codes:
        flags.append("current_video_placeholder")
    if "body_truncated_suspected" in codes:
        flags.append("current_truncation_flag")
    if unlocated:
        flags.append("retained_paragraphs_not_located")
    if payload is not None and not payload["retrievable"]:
        flags.append("current_retrieval_disabled")
    if differences:
        flags.append("metadata_differs")
    if any(len(p["locations"]) > 1 for p in rows):
        flags.append("repeated_locations_in_current")
    if candidate_issues:
        flags.append("candidate_quality_signal")
    if current is None:
        flags.append("no_unique_current_url_record")
    priority = (5 if current is None else 0 if "current_video_placeholder" in flags
                else 1 if "current_truncation_flag" in flags else 2 if unlocated
                else 3 if not payload["retrievable"] else 4 if inputs else 6)
    comparison = {
        "upstream_article_id": article_id,
        "current_match_status": "unique_exact_url" if current else "no_current_url" if not candidates else "ambiguous_current_url",
        "current_url_candidates": [{k: r[k] for k in ("record_id", "version_id", "body_sha256")} for r in candidates],
        "current_record": current, "provided_metadata": group["provided_metadata"],
        "source_member": source["member"], "candidate_body_sha256": original.digest(source["bytes"]),
        "candidate_body_characters": len(source["text"]),
        "original_locations": lineage["paragraphs"] if lineage else [], "current_locations": rows,
        "current_all_retained_in_order": ordered if current else None,
        "current_all_usable_retained_in_order": usable_in_order,
        "current_declared_retrieval_ranges": ranges,
        "unlocated_current_input_ids": unlocated,
        "supplied_paragraphs": len(inputs), "metadata_differences": differences,
        "quality_signals": {"current_stored": stored_issues, "current_inspection": current_issues,
                            "candidate_inspection": candidate_issues},
        "review_flags": flags, "review_priority": priority,
        "source_identity": "pending", "original_page_completeness": "unknown",
        "interpretation": "Unlocated means no complete retained-paragraph match; it does not prove that all of its content is missing.",
    }
    if not inputs:
        comparison["retained_input_coverage_status"] = "not_applicable_no_retained_input"
    return comparison


def body_proposal(packet, comparison):
    current = comparison["current_record"]
    if current is None:
        return None
    article_id = comparison["upstream_article_id"]
    source = packet["sources"][article_id]
    payload = current["payload"]
    binding = {"record_id": current["record_id"], "url": payload["url"],
               "expected_current_version_id": current["version_id"],
               "expected_current_body_sha256": current["body_sha256"]}
    source_binding = {
        "source_packet_manifest_sha256": packet["manifest_sha256"],
        "source_archive_sha256": original.digest(packet["files"]["source_archive.zip"]),
        "source_workbook_sha256": original.digest(packet["files"]["source_workbook.xlsx"]),
        "source_member": source["member"], "source_text_sha256": original.digest(source["bytes"]),
        "metadata_sheet": comparison["provided_metadata"]["sheet"],
        "metadata_row": comparison["provided_metadata"]["source_row"],
    }
    return {
        "proposal_id": canonical_digest({"target": binding, "source": source_binding, "article_id": article_id}),
        "upstream_article_id": article_id, "target_binding": binding, "source_binding": source_binding,
        "previous_payload": payload, "retained_metadata": {k: payload.get(k) for k in METADATA_FIELDS},
        "provided_metadata": comparison["provided_metadata"],
        "candidate_text": {"body": source["text"], "body_sha256": original.digest(source["bytes"]),
                           "encoding": "utf-8", "annotations": [], "retrievable": False,
                           "retrieval_ranges": None, "retrieval_end": None},
        "review": {"source_identity": "pending", "body_content": "pending",
                   "original_page_completeness": "unknown", "retrieval": "pending", "publication": "hold",
                   "reviewer": None, "reviewed_at": None, "decision": None},
        "importable": False,
        "limits": ["Current metadata is retained; the workbook is a separate source assertion.",
                   "Old annotations and body-review coordinates stay with the previous payload.",
                   "No retrieval eligibility or original-page completeness is inferred.",
                   "A later approved update must recheck the expected current version and rerun the normal source audit."],
    }


def article_markdown(comparison, source_text, output):
    article_id = comparison["upstream_article_id"]
    current = comparison["current_record"]
    heading = "旧文章组" if comparison["supplied_paragraphs"] else "来源文章"
    lines = [f"# 正文审查：{heading} {article_id}", "", "来源、正文采用、完整性及发布均待审；不提供分类或事实结论。", "",
             f"审查顺序：{PRIORITY_LABELS[comparison['review_priority']]}。", "",
             "## 当前记录与原表", "", "| 字段 | 当前值 | 原表值（待审） |", "| --- | --- | --- |"]
    values = comparison["provided_metadata"]["values"]
    payload = current["payload"] if current else {}
    for field in ("title", "publisher", "sponsor", "url"):
        lines.append(f"| {field} | {original.table_text(payload.get(field, '无唯一对应'))} | {original.table_text(values.get(field))} |")
    lines += ["", f"原表备注：{original.table_text(values.get('notes'))}", "",
              "元数据差异单独呈现，原表不会自动覆盖当前字段。URL 相同只是对应候选，不表示两份正文同一版本。", "",
              "## 文本对照", "", original.file_link("原始保存 TXT", output / "original" / f"{article_id}.txt")]
    if current is not None:
        located = sum(bool(p["locations"]) for p in comparison["current_locations"])
        lines += [original.file_link("当前保存正文", output / "current" / f"{article_id}.txt"), "",
                  f"当前 {len(current['body'])} 字符；原始 TXT {len(source_text)} 字符。长度不决定采用哪个版本。"]
        if comparison["supplied_paragraphs"]:
            lines += [
                  f"保留输入完整定位 {located}/{comparison['supplied_paragraphs']}；存在完整有序序列：{comparison['current_all_retained_in_order']}。",
                  f"全部保留输入具有当前可用的有序位置：{comparison['current_all_usable_retained_in_order']}。"]
        else:
            lines += ["没有历史 CLAIMS 保留输入；保留输入覆盖不适用，不能以空输入证明正文完整。"]
        lines += [f"当前记录可检索：{payload['retrievable']}。定位范围和可检索资格分别核对。"]
    else:
        lines += ["", "无唯一当前 URL 记录，未生成替换提案；不得用另一篇共享文字代替来源。"]
    lines += ["", "### 原始保存文本", "", original.code_block(source_text), "", "### 当前保存文本", "",
              original.code_block(current["body"]) if current else "当前唯一正文不可用。",
              "", "## 质量与范围提示", "", original.code_block(original.encoded(comparison["quality_signals"]).decode("utf-8")), "",
              "视频占位、截断标记与完整段落未定位是不同情况。全段未定位也可能来自字符黏连、插入导航、标点或图表差异；不能一律叫正文缺失。",
              "即使所有保留段落均定位，也不能证明网页、图表、视频全部保存。", "",
              "## 保留输入与对应位置", "", "坐标为各自 TXT 的 Python Unicode 半开区间；两份文本的坐标不可互换。"]
    current_rows = {p["input_id"]: p for p in comparison["current_locations"]}
    if not comparison["supplied_paragraphs"]:
        lines += ["", "未计算：本来源没有历史 CLAIMS 保留输入；来源文字与当前记录仍分别待审。"]
    for paragraph in comparison["original_locations"]:
        lines += ["", f"### 输入 {paragraph['input_id']}", "", original.code_block(paragraph["input_text"])]
        for span in paragraph["locations"]:
            lines += ["", f"原始 TXT [{span['start']}, {span['end']})；{span['match_method']}；lossy={span['lossy']}。"]
        matched = current_rows.get(paragraph["input_id"])
        if current is None:
            lines += ["", "未比较：无唯一当前 URL 记录，不能判断当前位置。"]
        elif not matched or not matched["locations"]:
            lines += ["", "当前正文未完整定位，原因待审；不是标签阴性或网页未提及的证据。"]
        for span in matched["locations"] if matched else []:
            lines += ["", f"当前 TXT [{span['start']}, {span['end']})；{span['match_method']}；lossy={span['lossy']}；"
                      f"在声明检索范围：{span['inside_declared_retrieval_range']}；当前检索可用：{span['usable_under_current_retrieval']}。", "",
                      original.code_block(span["context_before"] + span["quote"] + span["context_after"])]
    lines += ["", "## 版本与提案信息", "", original.code_block(original.encoded({
        "current_url_candidates": comparison["current_url_candidates"], "source_member": comparison["source_member"],
        "candidate_body_sha256": comparison["candidate_body_sha256"], "review_flags": comparison["review_flags"],
        "source_identity": "pending", "original_page_completeness": "unknown", "publication": "hold",
    }).decode("utf-8")), "", "旧 annotations 留在 previous_payload，新正文候选不继承它们，也不继承旧检索字符范围。审核人待定。"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_packet(source_packet, output, *, article_ids=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("new_private_output_directory_required")
    if output.resolve().is_relative_to(Path(source_packet).resolve()):
        raise ValueError("output_must_not_modify_source_packet")
    packet = load_source_packet(source_packet)
    selected_ids = select_article_ids(packet, article_ids)
    scope = selection_fields(packet, selected_ids) if article_ids is not None else {}
    current_by_url = defaultdict(list)
    for row in packet["snapshot"]["records"]:
        if row["dataset"] == "native" and row["active"] is True:
            current_by_url[row["payload"]["url"]].append(row)
    comparisons = [compare_group(packet, article_id, current_by_url) for article_id in selected_ids]
    validate_comparison_targets(comparisons)
    proposals = [p for c in comparisons if (p := body_proposal(packet, c)) is not None]
    matched = [c for c in comparisons if c["current_record"] is not None]
    paragraphs = [p for c in matched for p in c["current_locations"]]
    summary = {
        "schema_version": FORMAT, "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_manifest_sha256": packet["manifest_sha256"],
        "source_snapshot_sha256": original.digest(packet["files"]["current_source_snapshot.json"]),
        "source_snapshot_scope": "supplied_frozen_file_not_live_database",
        "selected_groups": len(comparisons), "selected_input_paragraphs": sum(c["supplied_paragraphs"] for c in comparisons),
        "unique_current_url_groups": len(matched),
        "paragraphs_without_unique_current_source": sum(c["supplied_paragraphs"] for c in comparisons if c["current_record"] is None),
        "paragraphs_located_current_strict": sum(any(s["match_method"] in {"exact", "whitespace_normalized"} for s in p["locations"]) for p in paragraphs),
        "paragraphs_located_current": sum(bool(p["locations"]) for p in paragraphs),
        "paragraphs_unlocated_current": sum(not p["locations"] for p in paragraphs),
        "groups_with_unlocated_current_paragraphs": sum(bool(c["unlocated_current_input_ids"]) for c in matched),
        "paragraphs_located_in_retrievable_records": sum(bool(p["locations"]) for c in matched if c["current_record"]["payload"]["retrievable"] for p in c["current_locations"]),
        "paragraphs_with_usable_current_location": sum(any(s["usable_under_current_retrieval"] for s in p["locations"]) for p in paragraphs),
        "paragraphs_located_only_outside_declared_ranges": sum(bool(p["locations"]) and not any(s["inside_declared_retrieval_range"] for s in p["locations"]) for p in paragraphs),
        **ordered_coverage_counts(comparisons),
        "current_video_placeholder_groups": sum("current_video_placeholder" in c["review_flags"] for c in matched),
        "current_truncation_flag_groups": sum("current_truncation_flag" in c["review_flags"] for c in matched),
        "pending_body_proposals": len(proposals), "reviewer": None,
        "model_calls": 0, "network_calls": 0, "database_writes": 0, "corpus_updates": 0,
        "source_associations_approved": 0, "classification_results_published": 0,
        "semantic_quality_scores": None,
        "limits": ["Unlocated full paragraphs do not prove all corresponding content is missing.",
                   "This exact-URL comparison is distinct from prior cross-version source and classification audits.",
                   "Matching and quality checks do not establish identity, full-page completeness or semantic accuracy."],
    }
    summary.update(scope)
    artifacts = {f"inputs/{name}": packet["files"][name] for name in ESSENTIAL_INPUTS}
    artifacts["inputs/source_packet_manifest.json"] = packet["manifest_bytes"]
    artifacts["body_comparisons.json"] = original.encoded(comparisons)
    artifacts["pending_body_proposals.json"] = original.encoded(proposals)
    artifacts["preparation_summary.json"] = original.encoded(summary)
    csv_rows = []
    intro = ["# 当前正文与原始输入的审查目录", "", "审核人待定；所有来源与正文采用决定待审，提案不启用检索。", "",
             f"{len(comparisons)} 组、{summary['selected_input_paragraphs']} 个保留输入段落；"
             f"{summary['paragraphs_located_current']} 段可在同 URL 当前正文定位，"
             f"{summary['paragraphs_unlocated_current']} 段未完整定位；"
             f"{summary['paragraphs_without_unique_current_source']} 段因无唯一当前 URL 未比较。", "",
             "未完整定位不等于内容全部缺失：逐篇查看视频占位、截断标记、字符或结构差异。",
             "完整保留输入覆盖不等于完整网页。正文定位数量不能当作可发布分类数量。", "",
             f"| 审查顺序 | {'来源 ID' if scope else '旧组'} | 当前标题 | 当前定位 / 保留输入 | 当前可检索 | 详情 |",
             "| --- | --- | --- | ---: | --- | --- |"]
    if scope:
        intro[4:4] = [f"显式选择 {len(selected_ids)} 个来源；{scope['source_articles_with_retained_input']} 个有历史保留输入，"
                      f"{scope['source_articles_without_retained_input']} 个没有。无输入覆盖不适用，不计为完整覆盖。", ""]
    for comparison in sorted(comparisons, key=lambda c: (c["review_priority"], int(c["upstream_article_id"]))):
        article_id = comparison["upstream_article_id"]
        current = comparison["current_record"]
        original_bytes = packet["sources"][article_id]["bytes"]
        artifacts[f"original/{article_id}.txt"] = original_bytes
        artifacts[f"articles/{article_id}.md"] = article_markdown(comparison, original_bytes.decode("utf-8"), output)
        if current:
            artifacts[f"current/{article_id}.txt"] = current["body"].encode("utf-8")
        title = current["payload"]["title"] if current else comparison["provided_metadata"]["values"]["title"]
        located = sum(bool(p["locations"]) for p in comparison["current_locations"])
        retrievable = current["payload"]["retrievable"] if current else "无唯一对应"
        coverage = (f"{located if current else '未比较'}/{comparison['supplied_paragraphs']}"
                    if comparison["supplied_paragraphs"] else "不适用（无历史输入）")
        intro.append(f"| {PRIORITY_LABELS[comparison['review_priority']]} | {article_id} | {original.table_text(title)} | "
                     f"{coverage} | {retrievable} | "
                     f"{original.file_link('正文对照', output / 'articles' / f'{article_id}.md')} |")
        csv_rows.append({"upstream_article_id": article_id, "review_priority": PRIORITY_LABELS[comparison["review_priority"]],
                         "record_id": current["record_id"] if current else "", "url_as_supplied": comparison["provided_metadata"]["values"]["url"],
                         "expected_current_version_id": current["version_id"] if current else "",
                         "candidate_body_sha256": comparison["candidate_body_sha256"],
                         "located_current_paragraphs": located if current and comparison["supplied_paragraphs"] else "", "retained_paragraphs": comparison["supplied_paragraphs"],
                         "source_identity": "pending", "body_decision": "pending", "original_page_completeness": "unknown",
                         "retrieval_decision": "pending", "reviewer": "", "reviewed_at": "", "notes": "", "publication": "hold"})
    artifacts["pending_body_review.csv"] = original.csv_bytes(csv_rows)
    intro += ["", original.file_link("待审清单", output / "pending_body_review.csv"), "",
              "清单和提案不是导入批准文件。审定后仍需核对预期旧版本、重新选择正文范围与标签位置，再执行正常导入和索引流程。"]
    artifacts["index.md"] = ("\n".join(intro) + "\n").encode("utf-8")
    # Recheck supplied files before writing; never reread an unverified byte
    # snapshot into the generated proposal. A completed manifest is written last.
    if (original.read_bytes(packet["manifest_path"]) != packet["manifest_bytes"]
            or any(original.read_bytes(path) != packet["files"][name] for name, path in packet["paths"].items())):
        raise ValueError("source_packet_changed_during_preparation")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in artifacts.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (output / "packet_manifest.json").write_bytes(original.encoded({
        "schema_version": FORMAT, "complete": True,
        "artifacts": {name: original.digest(data) for name, data in artifacts.items()},
        "source_packet_manifest_sha256": packet["manifest_sha256"],
        "importable": False, "source_associations_approved": False, "labels_published": False,
        **scope,
    }))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--article-ids", nargs="+", help="Explicit original source IDs; default: sampled CLAIMS groups")
    args = parser.parse_args()
    print(original.encoded(write_packet(args.source_packet, args.output, article_ids=args.article_ids)).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
