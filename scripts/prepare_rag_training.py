"""Prepare source-backed RAG task examples and freeze the client's 24 tests.

This is an offline file operation, not model training or a quality evaluation.
The test questions were previously exposed; changing their role cannot make
them unseen. Draft semantic references never become gold automatically.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from prepare_content_generalization import article_groups, normalized_tokens
from prepare_content_review import (
    csv_bytes,
    digest,
    encoded,
    normalize_records,
    read_json,
    validate_database_identities,
    validate_questions,
)

from observatory.segmentation import sentence_spans_with_status

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "rag-task-split-v2"
DEFAULT_SNAPSHOT = ROOT / ".runtime/content_source_refresh_20261006/content_review/source_snapshot.json"
DEFAULT_QUESTIONS = ROOT / "eval/customer_metrics/content_questions.v1.json"
DEFAULT_VARIANTS = ROOT / ".runtime/decision_followup_20261006/evaluation/generalization_v2/preparation.json"
POLICY = {
    "minimum_candidates": 240,
    "minimum_families_with_6_cases": 8,
    "minimum_article_groups": 40,
    "minimum_deterministic_candidates": 160,
    "maximum_per_family": 40,
    "policy_status": "engineering_preparation_threshold_not_performance_guarantee",
}


def source_ref(record: dict, groups: dict) -> dict:
    payload = record["payload"]
    return {"record_id": record["record_id"], "version_id": record["version_id"],
            "body_sha256": record["body_sha256"], "payload_sha256": record["payload_sha256"],
            "article_group_id": groups[record["record_id"]], "dataset": record["dataset"],
            "title": payload.get("title"), "url": payload.get("url"),
            "countable": payload["countable"], "retrievable": payload["retrievable"],
            "extraction_completeness": record["extraction_completeness"]}


def assert_question_separation(cases: list[dict], questions: list[dict], variants: list[dict]) -> None:
    """Keep supplied tests and exposed content variants out of training prompts.

    This conservative wording check is not a semantic paraphrase detector.
    A human must also review the task families before using demonstrations.
    Source documents remain searchable; their text is not a test answer label.
    """
    excluded = [q["question_exact"] for q in questions] + [v["question"] for v in variants]
    normalized = [" ".join(normalized_tokens(text)) for text in excluded]
    for case in cases:
        wording = " ".join(normalized_tokens(case["question"]))
        for other in normalized:
            if wording == other or difflib.SequenceMatcher(None, wording, other).ratio() >= .82:
                raise ValueError("training_question_overlaps_client_test_or_seen_variant")
        if case["split"] != "train_development_candidate" or case["human_gold_approved"]:
            raise ValueError("invalid_training_role_or_approval")


def candidate_cases(records: list[dict], groups: dict) -> list[dict]:
    """Build different operations, not copies of the 24 content questions."""
    cases = []
    active = [r for r in records if r["active"]]
    countable = [r for r in active if r["payload"]["countable"]]
    lookup = {r["record_id"]: r for r in active}

    def add(family, question, operation, arguments, reference, members, *, span=None, semantic=False):
        sources = [source_ref(lookup[rid], groups) for rid in sorted(set(members))]
        identity = {"family": family, "operation": operation, "arguments": arguments,
                    "records": [s["record_id"] for s in sources]}
        case = {"case_id": "TR-" + digest(encoded(identity))[:20], "task_family": family,
                "question": question, "operation": operation, "arguments": arguments,
                "split": "train_development_candidate", "previously_exposed": True,
                "reference_status": "semantic_draft_requires_review" if semantic else "computed_from_snapshot",
                "human_gold_approved": False, "review_status": "pending_named_review",
                "reviewer": None, "reviewed_at": None,
                "runtime_enabled": False, "permitted_in_runtime_prompt": False, "reference": reference,
                "source_records": sources, "source_span": span,
                "scope_note": "Frozen retained native records; not current combined/social scope or complete original pages."}
        cases.append(case)

    for record in active:
        payload, rid = record["payload"], record["record_id"]
        title = str(payload.get("title") or rid)
        arguments = {"record_id": rid}
        add("source_identity", f'Retrieve the original source and frozen version for “{title}”.',
            "read_source_identity", arguments,
            {k: payload.get(k) for k in ("url", "archive_url", "title", "publisher")}, [rid])
        add("collection_term_vs_sponsor", f'For “{title}”, report the stored sponsor and collection search term separately.',
            "read_sponsor_and_collection_term", arguments,
            {"sponsor": payload.get("sponsor"), "collection_search_term": payload.get("keyword"),
             "interpretation": "Stored fields only; a collection search term does not establish sponsorship."}, [rid])
        add("date_missingness", f'What publication date is stored for “{title}”? Keep a missing date unknown.',
            "read_publication_date", arguments,
            {"published_at": payload.get("published_at"), "date_state": "known" if payload.get("published_at") else "unknown"}, [rid])
        add("countable_vs_retrievable", f'Can “{title}” be counted, and is retained body text eligible for search? Explain the two flags separately.',
            "read_admission_flags", arguments,
            {"countable": payload["countable"], "retrievable": payload["retrievable"],
             "retained_body_characters": len(record["body"]), "extraction_completeness": record["extraction_completeness"]}, [rid])
        add("archive_availability", f'For “{title}”, is an archive URL supplied in the frozen record? Do not infer that an original URL is currently reachable.',
            "read_archive_availability", arguments,
            {"archive_url": payload.get("archive_url"), "archive_supplied": bool(payload.get("archive_url")),
             "network_checked": False}, [rid])
        add("record_quality_limits", f'List the stored extraction issues for “{title}”; do not invent causes or completed repairs.',
            "read_quality_issues", arguments, {"issues": payload.get("issues", []),
                                               "extraction_completeness": record["extraction_completeness"]}, [rid])
        if not payload["retrievable"] or not record["body"].strip():
            add("unavailable_body_handling", f'How should an answer handle unavailable retained text for “{title}”?',
                "handle_unavailable_retained_text", arguments,
                {"body_search_permitted": False, "content_state": "unknown",
                 "reason": "retrievable_false_or_empty_retained_body", "must_not_claim": "no relevant claim in the original advertisement"}, [rid])
            continue
        # Existing offset-preserving segmenter is reused. Fallback intervals
        # are retained by the application but not represented as true sentences.
        segmentation = sentence_spans_with_status(record["body"], coverage_fallback=True)
        fallback_spans = {(f.start, f.end) for f in segmentation.fallbacks}
        sentences = [(a, b) for a, b in segmentation.spans
                     if (a, b) not in fallback_spans and 45 <= b - a <= 700
                     and any(left <= a < b <= right for left, right in record["retrieval_ranges"])]
        if not sentences:
            continue
        a, b = sentences[len(sentences) // 2]
        quote = record["body"][a:b]
        span = {"start": a, "end": b, "quote": quote, "offset_unit": "unicode_codepoints"}
        add("exact_quote_location", f'In “{title}”, return the exact retained text at characters {a}–{b} and its source version.',
            "read_exact_source_range", {**arguments, "start": a, "end": b},
            {"quote": quote, "version_id": record["version_id"], "body_sha256": record["body_sha256"]}, [rid], span=span)
        for family, pattern, instruction in (
            ("speaker_attribution", r"\b(?:said|says|according to|explains|notes|we|our)\b",
             "Identify who is speaking, distinguish the sponsor from another quoted actor, and explain unresolved attribution using surrounding context."),
            ("negation_scope", r"\b(?:not|never|no longer|cannot|without|however|although)\b",
             "Explain what is negated or qualified; distinguish a limitation from a complete rejection and cite the relevant context."),
            ("planned_vs_achieved", r"\b(?:plans?|aims?|expects?|will|could|by 20\d\d|has reduced|already)\b",
             "Distinguish plans, conditional forecasts and reported achieved results; do not treat a future target as an accomplished result."),
        ):
            match = next(((left, right) for left, right in sentences
                          if re.search(pattern, record["body"][left:right], re.I)), None)
            if match:
                left, right = match
                quote = record["body"][left:right]
                context_start, context_end = max(0, left - 500), min(len(record["body"]), right + 500)
                add(family, f'For the located passage in “{title}”: {instruction}',
                    "review_context_boundary", {**arguments, "start": left, "end": right},
                    {"judgment": None, "speaker": None, "treatment": None,
                     "context_start": context_start, "context_end": context_end,
                     "context": record["body"][context_start:context_end],
                     "reason": "Actual source passage; no semantic judgment has been approved."}, [rid],
                    span={"start": left, "end": right, "quote": quote, "offset_unit": "unicode_codepoints"}, semantic=True)

    for field, family, operation in (
        ("publisher", "outlet_volume", "count_outlet_records"),
        ("sponsor", "company_volume", "count_sponsor_records"),
        ("published_at", "date_exact_volume", "count_records_on_date"),
    ):
        values = sorted({r["payload"].get(field) for r in countable if r["payload"].get(field)})
        for value in values:
            members = [r for r in countable if r["payload"].get(field) == value]
            add(family, f'Count active, countable native records with stored {field} = “{value}” in the frozen collection.',
                operation, {"dataset": "native", field: value, "active": True, "countable": True},
                {"count": len(members), "unit": "distinct_record_id", "unknown_dates_included": field != "published_at"},
                [r["record_id"] for r in members])
    for sponsor in sorted({r["payload"].get("sponsor") for r in countable if r["payload"].get("sponsor")}):
        members = [r for r in countable if r["payload"].get("sponsor") == sponsor]
        distribution = Counter(r["payload"].get("publisher") or "Unknown publisher" for r in members)
        add("company_outlet_relationships", f'List every stored publisher for sponsor “{sponsor}”, with native-record counts and source membership.',
            "group_sponsor_records_by_publisher", {"sponsor": sponsor, "dataset": "native"},
            {"groups": [{"publisher": key, "count": value} for key, value in sorted(distribution.items())],
             "total": len(members), "unit": "distinct_record_id"}, [r["record_id"] for r in members])
        year_counts = Counter(str(r["payload"]["published_at"])[:4] if r["payload"].get("published_at") else "Unknown date"
                              for r in members)
        add("yearly_counts", f'Group sponsor “{sponsor}” native records by stored publication year, keeping unknown dates in a separate bucket.',
            "group_sponsor_records_by_year", {"sponsor": sponsor, "dataset": "native"},
            {"groups": [{"year": year, "count": n} for year, n in sorted(year_counts.items())],
             "total": len(members), "inferred_dates_used": False}, [r["record_id"] for r in members])
        known_years = sorted({str(r["payload"]["published_at"])[:4] for r in members if r["payload"].get("published_at")})
        if len(known_years) >= 2:
            years = [known_years[0], known_years[-1]]
            add("two_period_comparison", f'Compare sponsor “{sponsor}” in the two stored calendar years {years[0]} and {years[1]}; report the signed count difference and excluded unknown-date records.',
                "compare_two_calendar_years", {"sponsor": sponsor, "years": years},
                {"period_counts": [{"year": y, "count": year_counts[y]} for y in years],
                 "difference_second_minus_first": year_counts[years[1]] - year_counts[years[0]],
                 "unknown_date_count": year_counts["Unknown date"], "inferred_dates_used": False},
                [r["record_id"] for r in members])
    for publisher in sorted({r["payload"].get("publisher") for r in countable if r["payload"].get("publisher")}):
        members = [r for r in countable if r["payload"].get("publisher") == publisher]
        sponsors = Counter(r["payload"].get("sponsor") or "Unknown sponsor" for r in members)
        largest = max(sponsors.values())
        add("tied_highest_count", f'At stored publisher “{publisher}”, identify all sponsors tied for the highest native-record count; do not discard ties.',
            "find_all_tied_top_sponsors", {"publisher": publisher, "dataset": "native"},
            {"top_count": largest, "sponsors": sorted(key for key, n in sponsors.items() if n == largest),
             "counts": dict(sorted(sponsors.items()))}, [r["record_id"] for r in members])
    # Cap by distinct article group / operation arguments, then deterministic
    # hashed order. This avoids taking dozens of copies of one long article.
    selected = []
    for family in sorted({c["task_family"] for c in cases}):
        family_cases = sorted((c for c in cases if c["task_family"] == family), key=lambda c: c["case_id"])
        seen = set()
        for case in family_cases:
            key = (tuple(sorted({s["article_group_id"] for s in case["source_records"]})),
                   json.dumps(case["arguments"], sort_keys=True) if len(case["source_records"]) != 1 else "one_record")
            if key in seen:
                continue
            seen.add(key)
            selected.append(case)
            if len(seen) >= POLICY["maximum_per_family"]:
                break
    return selected


def verify_references(cases: list[dict], records: list[dict]) -> None:
    by_id = {r["record_id"]: r for r in records}
    for case in cases:
        for ref in case["source_records"]:
            record = by_id[ref["record_id"]]
            for field in ("version_id", "body_sha256", "payload_sha256"):
                if ref[field] != record[field]:
                    raise ValueError("candidate_source_identity_mismatch")
        if span := case.get("source_span"):
            record = by_id[case["arguments"]["record_id"]]
            if (type(span["start"]) is not int or type(span["end"]) is not int
                    or not 0 <= span["start"] < span["end"] <= len(record["body"])
                    or record["body"][span["start"]:span["end"]] != span["quote"]):
                raise ValueError("candidate_quote_location_mismatch")
        if case["reference_status"] == "semantic_draft_requires_review" and case["reference"]["judgment"] is not None:
            raise ValueError("unapproved_semantic_judgment")
        if case["reference_status"] == "computed_from_snapshot":
            expected, members = recompute_reference(case, records)
            if (case["reference"] != expected
                    or sorted(s["record_id"] for s in case["source_records"]) != members):
                raise ValueError("computed_reference_or_membership_mismatch")
    if len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("duplicate_candidate_case_id")


def recompute_reference(case: dict, records: list[dict]) -> tuple[dict, list[str]]:
    """Recalculate deterministic targets from input fields, never a model answer."""
    operation, args = case["operation"], case["arguments"]
    active = [r for r in records if r["active"] and r["dataset"] == "native"]
    if rid := args.get("record_id"):
        record = next(r for r in active if r["record_id"] == rid)
        p = record["payload"]
        targets = {
            "read_source_identity": {k: p.get(k) for k in ("url", "archive_url", "title", "publisher")},
            "read_sponsor_and_collection_term": {"sponsor": p.get("sponsor"), "collection_search_term": p.get("keyword"),
                                                "interpretation": "Stored fields only; a collection search term does not establish sponsorship."},
            "read_publication_date": {"published_at": p.get("published_at"), "date_state": "known" if p.get("published_at") else "unknown"},
            "read_admission_flags": {"countable": p["countable"], "retrievable": p["retrievable"],
                                     "retained_body_characters": len(record["body"]), "extraction_completeness": record["extraction_completeness"]},
            "read_archive_availability": {"archive_url": p.get("archive_url"), "archive_supplied": bool(p.get("archive_url")), "network_checked": False},
            "read_quality_issues": {"issues": p.get("issues", []), "extraction_completeness": record["extraction_completeness"]},
            "handle_unavailable_retained_text": {"body_search_permitted": False, "content_state": "unknown",
                                                 "reason": "retrievable_false_or_empty_retained_body", "must_not_claim": "no relevant claim in the original advertisement"},
        }
        if operation == "read_exact_source_range":
            result = {"quote": record["body"][args["start"]:args["end"]], "version_id": record["version_id"], "body_sha256": record["body_sha256"]}
        else:
            result = targets[operation]
        return result, [rid]
    members = [r for r in active if r["payload"]["countable"]]
    for field in ("sponsor", "publisher", "published_at"):
        if field in args:
            members = [r for r in members if r["payload"].get(field) == args[field]]
    if operation in {"count_outlet_records", "count_sponsor_records", "count_records_on_date"}:
        result = {"count": len(members), "unit": "distinct_record_id", "unknown_dates_included": operation != "count_records_on_date"}
    elif operation == "group_sponsor_records_by_publisher":
        counts = Counter(r["payload"].get("publisher") or "Unknown publisher" for r in members)
        result = {"groups": [{"publisher": key, "count": n} for key, n in sorted(counts.items())],
                  "total": len(members), "unit": "distinct_record_id"}
    elif operation in {"group_sponsor_records_by_year", "compare_two_calendar_years"}:
        counts = Counter(str(r["payload"]["published_at"])[:4] if r["payload"].get("published_at") else "Unknown date" for r in members)
        if operation == "group_sponsor_records_by_year":
            result = {"groups": [{"year": year, "count": n} for year, n in sorted(counts.items())], "total": len(members), "inferred_dates_used": False}
        else:
            years = args["years"]
            result = {"period_counts": [{"year": year, "count": counts[year]} for year in years],
                      "difference_second_minus_first": counts[years[1]] - counts[years[0]],
                      "unknown_date_count": counts["Unknown date"], "inferred_dates_used": False}
    elif operation == "find_all_tied_top_sponsors":
        counts = Counter(r["payload"].get("sponsor") or "Unknown sponsor" for r in members)
        largest = max(counts.values())
        result = {"top_count": largest, "sponsors": sorted(key for key, n in counts.items() if n == largest), "counts": dict(sorted(counts.items()))}
    else:
        raise ValueError("unknown_deterministic_operation")
    return result, sorted(r["record_id"] for r in members)


def prepare(snapshot: Path, questions: Path, variants: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("output_already_exists_preserve_prior_bytes")
    raw_snapshot, snapshot_bytes = read_json(snapshot)
    definitions, question_bytes = read_json(questions)
    old_preparation, variants_bytes = read_json(variants)
    records = normalize_records(raw_snapshot)
    validate_database_identities(records)
    original_questions = validate_questions(definitions)
    old_variants = old_preparation.get("development_variants")
    if (not isinstance(old_variants, list) or len(old_variants) != 18
            or any(v.get("split") != "development" or v.get("previously_exposed") is not True
                   or v.get("human_gold_approved") is not False for v in old_variants)):
        raise ValueError("expected_18_exposed_unapproved_development_variants")
    active_native = [r for r in records if r["active"] and r["dataset"] == "native"]
    if not active_native:
        raise ValueError("no_active_native_training_sources")
    groups, edges = article_groups([{"record_id": r["record_id"], "url": r["payload"].get("url") or "",
                                     "body": r["body"]} for r in active_native])
    cases = candidate_cases(active_native, groups)
    assert_question_separation(cases, original_questions, old_variants)
    verify_references(cases, records)
    by_family = Counter(c["task_family"] for c in cases)
    deterministic = sum(c["reference_status"] == "computed_from_snapshot" for c in cases)
    represented_groups = {s["article_group_id"] for c in cases for s in c["source_records"]}
    checks = {"candidate_count": len(cases) >= POLICY["minimum_candidates"],
              "task_family_coverage": sum(n >= 6 for n in by_family.values()) >= POLICY["minimum_families_with_6_cases"],
              "article_group_coverage": len(represented_groups) >= POLICY["minimum_article_groups"],
              "deterministic_candidates": deterministic >= POLICY["minimum_deterministic_candidates"]}
    summary = {"training_candidates": len(cases), "computed_from_snapshot": deterministic,
               "semantic_drafts": len(cases) - deterministic, "human_approved_training_examples": 0,
               "families": dict(sorted(by_family.items())), "families_with_6_or_more_cases": sum(n >= 6 for n in by_family.values()),
               "represented_article_groups": len(represented_groups), "client_task_test_questions": 24,
               "exposed_development_variants": 18, "independent_unseen_test_questions": 0,
               "semantic_performance_scores": None}
    manifest = {"schema_version": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                "preparer_sha256": digest(Path(__file__).read_bytes()),
                "status": "prepared_not_trained_or_human_approved", "source_snapshot_path": str(snapshot.resolve()),
                "source_snapshot_sha256": digest(snapshot_bytes), "source_snapshot_record_count": len(records),
                "source_active_native_count": len(active_native),
                "source_countable_native_count": sum(r["payload"]["countable"] for r in active_native),
                "source_snapshot_observation": raw_snapshot.get("observation"),
                "client_questions_path": str(questions.resolve()), "client_questions_sha256": digest(question_bytes),
                "previous_development_preparation_sha256": digest(variants_bytes),
                "policy": POLICY, "coverage_checks": checks, "coverage_threshold_met": all(checks.values()),
                "summary": summary, "model_calls": 0, "paid_calls": 0, "fine_tuning_performed": False,
                "client_test_policy": {"role": "client_task_test", "previously_exposed": True,
                                       "independent_unseen": False, "permitted_in_prompts_or_training_examples": False,
                                       "formal_unseen_evaluator_compatible": False,
                                       "reference_status": "awaiting_named_full_context_review",
                                       "run_rule": "Freeze code, prompts and source before running; any change after results makes the next run a regression run."},
                "training_policy": {"candidate_use": "review_and_development_preparation",
                                    "runtime_demonstration_insertion": "disabled_until_review",
                                    "approved_semantic_gold_count": 0,
                                    "test_source_overlap": "Training source groups may overlap the fixed263 native test corpus; declared task-test reuse, not independent document holdout.",
                                    "article_groups": "Heuristic duplicate groups, pending source review; all remain exposed development.",
                                    "retrieval_corpus": "Source articles can be indexed and searched for the test; test questions/answers/gold cannot enter parameter or demonstration training."},
                "gaps": ["No social sources in this historical native snapshot.",
                         "Semantic judgments and full 24-by-263 membership require named review.",
                         "No independent unseen holdout or model performance has been established.",
                         "Question-wording checks are conservative, not proof of semantic non-overlap."],
                "grouping_edges": edges}
    test_cases = [{"case_id": q["question_id"], "question_exact": q["question_exact"],
                   "source_ref": q["source_ref"], "question_source_sha256": digest(question_bytes),
                   "split": "client_task_test", "previously_exposed": True,
                   "independent_unseen": False, "permitted_in_prompts_or_training_examples": False,
                   "human_gold_approved": False, "reference_status": "awaiting_named_full_context_review"}
                  for q in original_questions]
    files = {"inputs/source_snapshot.json": snapshot_bytes,
             "inputs/client_questions.original.json": question_bytes,
             "inputs/previous_development_preparation.json": variants_bytes,
             "training_candidates.jsonl": b"".join((json.dumps(c, ensure_ascii=False) + "\n").encode("utf-8") for c in cases),
             "client_task_test.json": encoded(test_cases),
             "development_variants.json": encoded(old_variants),
             "review.csv": csv_bytes([{"case_id": c["case_id"], "task_family": c["task_family"],
                                       "question": c["question"], "reference_status": c["reference_status"],
                                       "source_titles": " | ".join(s["title"] or s["record_id"] for s in c["source_records"]),
                                       "review_status": c["review_status"], "reviewer": "", "decision": "", "notes": ""}
                                      for c in cases], ["case_id", "task_family", "question", "reference_status", "source_titles",
                                                       "review_status", "reviewer", "decision", "notes"]),
             "summary.json": encoded(summary)}
    manifest["files"] = [{"path": name, "sha256": digest(data), "bytes": len(data)} for name, data in sorted(files.items())]
    files["manifest.json"] = encoded(manifest)
    out.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    print(json.dumps({"out": str(out), "coverage_threshold_met": manifest["coverage_threshold_met"], **summary}, ensure_ascii=False))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--variants", type=Path, default=DEFAULT_VARIANTS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.snapshot, args.questions, args.variants, args.out)


if __name__ == "__main__":
    main()
