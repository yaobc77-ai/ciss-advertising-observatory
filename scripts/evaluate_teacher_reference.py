"""Score frozen answer fields; keep AI agreement separate from accuracy."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from prepare_content_review import (
    digest,
    encoded,
    normalize_records,
    validate_database_identities,
)
from prepare_teacher_reference import located_evidence, read_lines, source_bindings

UNORDERED = {"groups", "sponsors", "speaker_names", "issues"}


def comparable(value, field=None):
    if isinstance(value, dict):
        return {key: comparable(item, key) for key, item in sorted(value.items())}
    if isinstance(value, list):
        items = [comparable(item, field) for item in value]
        if field in UNORDERED:
            return sorted(items, key=encoded)
        return items
    if isinstance(value, str) and field == "speaker_names":
        return " ".join(value.split()).casefold()
    return value


def exact_fields(actual, expected):
    # JSON distinguishes True from1 and1.0 from1, unlike Python equality.
    return isinstance(actual, dict) and encoded(comparable(actual)) == encoded(comparable(expected))


def metric(correct, denominator, *, executed):
    return {"numerator": correct if executed else None, "denominator": denominator,
            "rate": correct / denominator if executed and denominator else None}


def load_reference_set(directory):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference_path = directory / "references.jsonl"
    if (manifest.get("schema_version") != "teacher-reference-v1"
            or manifest.get("human_gold_approved") is not False
            or manifest.get("runtime_enabled") is not False
            or digest(reference_path.read_bytes()) != manifest.get("references_sha256")):
        raise ValueError("reference_manifest_or_hash_mismatch")
    snapshot = Path(manifest["source_snapshot_path"])
    if digest(snapshot.read_bytes()) != manifest["source_snapshot_sha256"]:
        raise ValueError("source_snapshot_changed")
    records = normalize_records(json.loads(snapshot.read_text(encoding="utf-8")))
    validate_database_identities(records)
    references = read_lines(reference_path)
    sources = {row["record_id"]: row for row in records}
    if len({row["case_id"] for row in references}) != len(references):
        raise ValueError("duplicate_reference_id")
    for row in references:
        if (row.get("purpose") != "evaluation_reference_only" or row.get("human_gold_approved") is not False
                or row.get("runtime_enabled") is not False or row.get("permitted_in_training_or_prompts") is not False
                or row.get("status") not in {"resolved", "unresolved"}
                or row.get("reference_kind") not in {"source_computed_objective", "ai_teacher_semantic"}
                or (row["status"] == "resolved" and not isinstance(row.get("expected_fields"), dict))
                or (row["status"] == "unresolved" and row.get("expected_fields") is not None)):
            raise ValueError("invalid_reference_status_or_authority")
        source_bindings(row, sources)
        for evidence in row.get("evidence", []):
            if not citation_valid(evidence, row, sources):
                raise ValueError("invalid_reference_evidence")
        if row["reference_kind"] == "ai_teacher_semantic":
            focal = row.get("focal_span")
            if (not isinstance(focal, dict) or not any(evidence["start"] == focal.get("start")
                    and evidence["end"] == focal.get("end") and evidence["quote"] == focal.get("quote")
                    for evidence in row.get("evidence", []))):
                raise ValueError("reference_focal_quote_required")
    return manifest, digest(manifest_path.read_bytes()), references, sources


def citation_valid(citation, case, sources):
    if not isinstance(citation, dict):
        return False
    allowed = {source["record_id"] for source in case["source_records"]}
    source = sources.get(citation.get("record_id"))
    if not source or source["record_id"] not in allowed:
        return False
    try:
        located = located_evidence(source, citation)
    except (ValueError, TypeError, AttributeError):
        return False
    return all(citation.get(key) == located[key] for key in ("version_id", "body_sha256", "start", "end", "quote", "offset_unit"))


def evaluate(references, predictions, sources, *, executed=False, fixture=False):
    by_id = {row["case_id"]: row for row in references}
    provided = {}
    for prediction in predictions:
        if (not isinstance(prediction, dict) or prediction.get("case_id") not in by_id
                or prediction["case_id"] in provided):
            raise ValueError("unknown_or_duplicate_prediction_id")
        if prediction.get("status") not in {"answered", "unknown", "failed"}:
            raise ValueError("invalid_prediction_status")
        if prediction["status"] != "answered" and prediction.get("fields") not in (None, {}):
            raise ValueError("abstention_must_not_carry_answer_fields")
        if not isinstance(prediction.get("evidence", []), list):
            raise ValueError("evidence_list_required")
        provided[prediction["case_id"]] = prediction
    if not executed and predictions:
        raise ValueError("unexecuted_run_contains_predictions")
    executed = executed and bool(predictions)
    buckets, family_counts, rows = defaultdict(Counter), defaultdict(Counter), []
    quote_count = valid_quotes = supported_focals = 0
    for case in references:
        predicted = provided.get(case["case_id"])
        state = predicted["status"] if predicted else "missing"
        group = case["reference_kind"]
        if case["status"] == "unresolved":
            rows.append({"case_id": case["case_id"], "status": "reference_unresolved_not_scored", "prediction_status": state})
            continue
        bucket, family = buckets[group], family_counts[case["task_family"]]
        for item in (bucket, family):
            item["reference_cases"] += 1
            item["provided"] += predicted is not None
            item[state] += 1
        correct = False
        if predicted and state == "answered":
            correct = exact_fields(predicted.get("fields"), case["expected_fields"])
            bucket["correct"] += correct
            family["correct"] += correct
        citations = predicted.get("evidence", []) if predicted else []
        validity = [citation_valid(item, case, sources) for item in citations]
        quote_count += len(citations)
        valid_quotes += sum(validity)
        focal = case.get("focal_span")
        covers = any(valid and focal and item["start"] <= focal["start"] < focal["end"] <= item["end"]
                     for item, valid in zip(citations, validity, strict=True))
        if group == "ai_teacher_semantic" and state == "answered":
            supported_focals += covers
        rows.append({"case_id": case["case_id"], "reference_kind": group, "prediction_status": state,
                     "exact_fields_match": correct if executed else None,
                     "source_quotes_valid": all(validity) if citations else None,
                     "full_focal_citation_present": bool(covers) if focal else None})
    metrics = {}
    names = {"source_computed_objective": "objective", "ai_teacher_semantic": "ai_reference"}
    for group, label in names.items():
        counts = buckets[group]
        metrics[label] = {
            "strict_task_match": metric(counts["correct"], counts["reference_cases"], executed=executed),
            "answered_only_match": metric(counts["correct"], counts["answered"], executed=executed),
            "prediction_coverage": metric(counts["provided"], counts["reference_cases"], executed=executed),
            "answered_coverage": metric(counts["answered"], counts["reference_cases"], executed=executed),
            "unknown": counts["unknown"] if executed else None,
            "failed": counts["failed"] if executed else None,
            "missing": counts["missing"] if executed else None,
        }
    per_family = {name: {"reference_kind": by_id[next(row["case_id"] for row in references if row["task_family"] == name)]["reference_kind"],
                         "strict_task_match": metric(c["correct"], c["reference_cases"], executed=executed),
                         "answered_only_match": metric(c["correct"], c["answered"], executed=executed),
                         "answered_coverage": metric(c["answered"], c["reference_cases"], executed=executed)}
                  for name, c in sorted(family_counts.items())}
    macro = {}
    for group, label in names.items():
        rates = [item["strict_task_match"]["rate"] for item in per_family.values()
                 if item["reference_kind"] == group and item["strict_task_match"]["rate"] is not None]
        macro[label] = sum(rates) / len(rates) if rates else None
    return {"schema_version": "teacher-evaluation-report-v1", "status": "fixture_not_system_score" if fixture and executed else "evaluated" if executed else "not_run",
            "metrics": metrics, "macro_average_by_task_family": macro,
            "source_quote_locator_validity": metric(valid_quotes, quote_count, executed=executed),
            "semantic_full_focal_citation_coverage": metric(supported_focals, buckets["ai_teacher_semantic"]["answered"], executed=executed),
            "reference_cases": len(references), "unresolved_references_excluded": sum(row["status"] == "unresolved" for row in references),
            "system_predictions": len(predictions) if executed else 0, "human_verified_accuracy": None,
            "client24_test_score": None, "overall_mixed_accuracy": None,
            "notes": ["Objective scores compare stored source facts; they do not validate external facts or business approval.",
                      "AI-reference agreement is not human-verified semantic accuracy. Unresolved references are excluded explicitly.",
                      "Strict task match includes missing/unknown/failed answers as failures; answered-only match must be read with coverage.",
                      "Exact source quotes and focal coverage do not prove semantic entailment or readable answer quality.",
                      "No overall accuracy combines objective and AI-semantic reference scores; no client24 score is inferred."],
            "cases": rows}


def score_files(reference_dir, prediction_path):
    manifest, manifest_hash, references, sources = load_reference_set(reference_dir)
    data = json.loads(Path(prediction_path).read_text(encoding="utf-8"))
    if (data.get("schema_version") != "teacher-predictions-v1"
            or data.get("reference_manifest_sha256") != manifest_hash
            or data.get("source_snapshot_sha256") != manifest["source_snapshot_sha256"]):
        raise ValueError("prediction_reference_binding_mismatch")
    run = data.get("run")
    if not isinstance(run, dict) or type(run.get("executed")) is not bool or run.get("kind") not in {"system_output", "fixture"}:
        raise ValueError("explicit_prediction_run_required")
    if run["executed"] and (not isinstance(run.get("model"), str) or not run["model"].strip()
                            or not re.fullmatch(r"[0-9a-f]{64}", str(run.get("prompt_sha256")))):
        raise ValueError("executed_model_and_prompt_hash_required")
    predictions = data.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("predictions_list_required")
    report = evaluate(references, predictions, sources, executed=run["executed"], fixture=run["kind"] == "fixture")
    return report | {"at_utc": datetime.now(timezone.utc).isoformat(), "run": run,
                     "reference_manifest_sha256": manifest_hash, "source_snapshot_sha256": manifest["source_snapshot_sha256"],
                     "prediction_file_sha256": digest(Path(prediction_path).read_bytes()),
                     "scorer_sha256": digest(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("output_file_already_exists")
    report = score_files(args.references, args.predictions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as stream:
        stream.write(encoded(report))
    print(json.dumps({key: report[key] for key in ("status", "metrics", "system_predictions", "unresolved_references_excluded")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
