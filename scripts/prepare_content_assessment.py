"""Prepare and replay private full-article draft assessments, without model calls.

Every active, countable native record is retained, including missing bodies.
External replay responses are unverified inputs, never customer-approved gold.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import prepare_content_review as original
from prepare_native_body_review import packet_path

from observatory import content_assessment as mechanism
from observatory.evaluate import EvaluationInvalid, canonical_digest, strict_json_loads

PREPARED_FORMAT = "content-assessment-preparation-v1"
REPLAY_FORMAT = "content-assessment-replay-v1"
MAX_PACKET_BYTES = 256 * 1024 * 1024
MAX_ARTIFACTS = 5000
INPUT_NAMES = ("source_snapshot.json", "question_definitions.json", "preparation_summary.json")
PENDING_FLAGS = {"customer_approved": False, "semantic_gold": False, "quality_scores": None}
NO_ACTIONS = {"model_calls": 0, "database_writes": 0, "source_adoptions": 0, "publications": 0}


def read_bytes(path):
    with Path(path).open("rb") as stream:
        data = stream.read(original.MAX_INPUT_BYTES + 1)
    if len(data) > original.MAX_INPUT_BYTES:
        raise ValueError("assessment_artifact_too_large")
    return data


def parse_json(data):
    try:
        return strict_json_loads(data)
    except EvaluationInvalid as exc:
        raise ValueError("invalid_assessment_json") from exc


def require_flags(document):
    if not isinstance(document, dict) or any(
        key not in document or document[key] is not value for key, value in PENDING_FLAGS.items()
    ):
        raise ValueError("unapproved_assessment_material_required")


def read_declared_files(root, hashes, required):
    if (not isinstance(hashes, dict) or len(hashes) > MAX_ARTIFACTS
            or not set(required) <= set(hashes) or "manifest.json" in hashes):
        raise ValueError("complete_assessment_artifacts_required")
    files, total = {}, 0
    for name, fingerprint in hashes.items():
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("invalid_assessment_artifact_sha256")
        data = read_bytes(packet_path(root, name))
        total += len(data)
        if total > MAX_PACKET_BYTES:
            raise ValueError("assessment_packet_too_large")
        if original.digest(data) != fingerprint:
            raise ValueError("assessment_artifact_changed")
        files[name] = data
    return files


def select_records(records):
    return [r for r in records if r["active"] and r["dataset"] == "native" and r["payload"]["countable"]]


def load_content_packet(packet):
    """Validate all declared source files and the full selected-record scope."""
    root = Path(packet)
    try:
        manifest_bytes = read_bytes(packet_path(root, "manifest.json"))
        manifest = parse_json(manifest_bytes)
        require_flags(manifest)
        if (manifest.get("format_version") != original.FORMAT
                or manifest.get("status") != "unreviewed_development_preparation"):
            raise ValueError("unreviewed_content_packet_required")
        files = read_declared_files(root, manifest.get("input_sha256"), INPUT_NAMES)
        snapshot = parse_json(files["source_snapshot.json"])
        definitions = parse_json(files["question_definitions.json"])
        questions = original.validate_questions(definitions)
        records = original.normalize_records(snapshot)
        original.validate_database_identities(records)
        # Convenience fields must describe the bound payload, not a second body.
        raw_rows = snapshot.get("records") if isinstance(snapshot, dict) else snapshot
        for raw, normalized in zip(sorted(raw_rows, key=lambda r: r["record_id"]), records, strict=True):
            for field in ("body_sha256", "payload_sha256", "retrieval_ranges", "extraction_completeness"):
                if field in raw and raw[field] != normalized[field]:
                    raise ValueError("source_convenience_fields_differ")
        selected = select_records(records)
        if not selected:
            raise ValueError("no_active_countable_native_records")
        summary = parse_json(files["preparation_summary.json"])
        require_flags(summary)
        expected = {
            "format_version": original.FORMAT,
            "status": "awaiting_definition_and_source_review",
            "source_records": len(records), "selected_records": len(selected),
            "question_count": 24, "review_units": len(selected) * 24,
            "reviewed_units": 0, "relevant_units": None, "unseen_test": False,
            "source_snapshot_sha256": original.digest(files["source_snapshot.json"]),
            "selection": {"dataset": "native", "active": True, "countable": True, "unit": "source_record_id"},
            "selection_sha256": canonical_digest([
                {k: r[k] for k in ("record_id", "version_id", "body_sha256")} for r in selected
            ]),
            "retrievable_records": sum(r["payload"]["retrievable"] for r in selected),
            "extraction_completeness": dict(Counter(r["extraction_completeness"] for r in selected)),
        }
        if any(key not in summary or summary[key] != value for key, value in expected.items()):
            raise ValueError("content_summary_scope_or_binding_differs")
        rows = summary.get("questions")
        if not isinstance(rows, list) or len(rows) != 24:
            raise ValueError("content_summary_questions_differ")
        expected_questions = []
        for question in questions:
            expected_questions.append({
                "question_id": question["question_id"], "records_to_review": len(selected),
                "records_with_literal_hints": sum(bool(original.hint_matches(r["body"], question["candidate_search_terms"])) for r in selected),
                "unreviewed_records": len(selected), "complete_gold": False, "precision": None, "recall": None,
            })
        if rows != expected_questions:
            raise ValueError("content_summary_questions_differ")
        return {"files": files, "manifest_bytes": manifest_bytes,
                "manifest_sha256": original.digest(manifest_bytes), "records": records,
                "selected": selected, "definitions": definitions, "summary": summary}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid_content_packet_structure") from exc


def max_tokens(value):
    if type(value) is not int or value < 1 or value > 1_000_000:
        raise ValueError("positive_bounded_input_token_budget_required")
    return value


def code_fingerprints():
    return {"cli_sha256": original.digest(Path(__file__).read_bytes()),
            "mechanism_sha256": original.digest(Path(mechanism.__file__).read_bytes()),
            "source_preparer_sha256": original.digest(Path(original.__file__).read_bytes())}


def build_requests(source, token_budget):
    token_budget = max_tokens(token_budget)
    wrappers = []
    for record in source["selected"]:
        request = mechanism.build_article_request(record, source["definitions"], max_input_tokens=token_budget)
        if request.get("status") not in {"ready", "not_requested"}:
            raise ValueError("unknown_article_request_status")
        wrappers.append({"request_id": canonical_digest(request), "request": request})
    if len({w["request_id"] for w in wrappers}) != len(wrappers):
        raise ValueError("duplicate_article_request_identity")
    return wrappers


def jsonl_bytes(rows):
    return b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows)


def preparation_summary(source, requests, token_budget):
    counts = dict(Counter(row["request"]["status"] for row in requests))
    return {"format_version": PREPARED_FORMAT, "status": "prepared",
            "scope": "frozen_active_countable_native_source_records", "question_count": 24,
            "source_records": len(source["records"]), "selected_records": len(requests),
            "judgment_slots": len(requests) * 24, "ready_records": counts.get("ready", 0),
            "not_requested_records": counts.get("not_requested", 0), "request_status_counts": counts,
            "not_requested_reasons": dict(Counter(row["request"].get("reason") for row in requests if row["request"]["status"] == "not_requested")),
            "max_input_tokens": token_budget, "code_fingerprints": code_fingerprints(),
            "source_manifest_sha256": source["manifest_sha256"],
            "source_input_sha256": {name: original.digest(source["files"][name]) for name in INPUT_NAMES},
            "selection_sha256": source["summary"]["selection_sha256"],
            "request_ids_sha256": canonical_digest([row["request_id"] for row in requests]),
            "response_origin": "not_obtained", "response_origin_verified": False,
            "classifications": 0, "review_required": True, "publication_status": "hold",
            **PENDING_FLAGS, **NO_ACTIONS}


def require_new_output(output, *inputs):
    output = Path(output)
    if output.exists():
        raise ValueError("new_output_directory_required")
    resolved = output.resolve()
    if any(resolved.is_relative_to(Path(root).resolve()) for root in inputs):
        raise ValueError("output_inside_input_packet")
    return output


def write_bundle(output, files, manifest):
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = packet_path(output, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    hashes = {name: original.digest(data) for name, data in files.items()}
    if any(original.digest(read_bytes(packet_path(output, name))) != fingerprint for name, fingerprint in hashes.items()):
        raise ValueError("written_assessment_artifact_changed")
    with (output / "manifest.json").open("xb") as stream:
        stream.write(original.encoded({**manifest, "complete": True, "artifacts": hashes}))


def prepare(packet, output, *, max_input_tokens=24000):
    output = require_new_output(output, packet)
    source = load_content_packet(packet)
    token_budget = max_tokens(max_input_tokens)
    requests = build_requests(source, token_budget)
    summary = preparation_summary(source, requests, token_budget)
    files = {"inputs/source_manifest.json": source["manifest_bytes"],
             **{f"inputs/{name}": source["files"][name] for name in INPUT_NAMES},
             "requests.jsonl": jsonl_bytes(requests), "preparation_summary.json": original.encoded(summary)}
    write_bundle(output, files, {"format_version": PREPARED_FORMAT, "status": "prepared",
                                "source_manifest_sha256": source["manifest_sha256"],
                                "code_fingerprints": code_fingerprints(), **PENDING_FLAGS, **NO_ACTIONS})
    return summary


def parse_jsonl(data):
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_assessment_jsonl_encoding") from exc
    if any(not line.strip() for line in lines):
        raise ValueError("blank_assessment_request_line")
    return [parse_json(line) for line in lines]


def load_prepared(prepared, source):
    root = Path(prepared)
    try:
        manifest_bytes = read_bytes(packet_path(root, "manifest.json"))
        manifest = parse_json(manifest_bytes)
        require_flags(manifest)
        if (manifest.get("format_version") != PREPARED_FORMAT or manifest.get("status") != "prepared"
                or manifest.get("complete") is not True
                or any(manifest.get(k) != v for k, v in NO_ACTIONS.items())):
            raise ValueError("unexecuted_prepared_packet_required")
        required = {"requests.jsonl", "preparation_summary.json", "inputs/source_manifest.json"} | {f"inputs/{name}" for name in INPUT_NAMES}
        files = read_declared_files(root, manifest.get("artifacts"), required)
        if set(files) != required:
            raise ValueError("unexpected_prepared_artifacts")
        if (files["inputs/source_manifest.json"] != source["manifest_bytes"]
                or manifest.get("source_manifest_sha256") != source["manifest_sha256"]
                or any(files[f"inputs/{name}"] != source["files"][name] for name in INPUT_NAMES)):
            raise ValueError("prepared_source_binding_changed")
        if manifest.get("code_fingerprints") != code_fingerprints():
            raise ValueError("prepared_mechanism_code_changed")
        summary = parse_json(files["preparation_summary.json"])
        if not isinstance(summary, dict):
            raise ValueError("prepared_summary_required")
        budget = max_tokens(summary.get("max_input_tokens"))
        expected = build_requests(source, budget)
        saved = parse_jsonl(files["requests.jsonl"])
        if saved != expected:
            raise ValueError("prepared_requests_differ_from_rebuilt_scope")
        if summary != preparation_summary(source, expected, budget):
            raise ValueError("prepared_summary_differ_from_rebuilt_scope")
        return {"files": files, "manifest_bytes": manifest_bytes,
                "manifest_sha256": original.digest(manifest_bytes), "summary": summary, "requests": expected}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid_prepared_packet_structure") from exc


def load_responses(path, requests):
    data = read_bytes(path)
    responses = parse_json(data)
    if not isinstance(responses, list) or len(responses) > len(requests):
        raise ValueError("response_rows_required")
    known = {row["request_id"]: row["request"] for row in requests}
    found = {}
    for row in responses:
        if not isinstance(row, dict) or set(row) != {"request_id", "response"}:
            raise ValueError("response_id_and_response_only")
        identifier = row["request_id"]
        if not isinstance(identifier, str) or identifier not in known or identifier in found:
            raise ValueError("duplicate_or_unknown_response_id")
        if known[identifier]["status"] != "ready":
            raise ValueError("response_for_not_requested_record")
        found[identifier] = row["response"]
    return found, data


def replay(packet, prepared, responses, output):
    output = require_new_output(output, packet, prepared)
    source = load_content_packet(packet)
    frozen = load_prepared(prepared, source)
    provided, response_bytes = load_responses(responses, frozen["requests"])
    results = []
    for wrapper in frozen["requests"]:
        identifier, request = wrapper["request_id"], wrapper["request"]
        error_type = None
        if identifier not in provided:
            assessment = mechanism.materialize_assessment(request, None)
            processing_status = "not_requested" if request["status"] == "not_requested" else "not_processed"
            origin = "not_provided"
        else:
            origin = "external_replay_unverified"
            try:
                if not isinstance(provided[identifier], dict):
                    raise ValueError("response_object_required")
                assessment = mechanism.materialize_assessment(request, provided[identifier])
                processing_status = "processed"
            except (ValueError, TypeError, KeyError) as exc:
                assessment = mechanism.materialize_assessment(request, None)
                processing_status, error_type = "validation_failed", type(exc).__name__
                assessment.update(processing_status="validation_failed", reason="invalid_external_response",
                                  response_received=True, validation_error_type=error_type)
        if not isinstance(assessment, dict) or len(assessment.get("judgments", [])) != 24:
            raise ValueError("assessment_must_retain_24_judgments")
        results.append({"request_id": identifier, "record_id": request["record_id"],
                        "version_id": request["version_id"], "body_sha256": request["body_sha256"],
                        "payload_sha256": request["payload_sha256"], "definitions_sha256": request["definitions_sha256"],
                        "request_sha256": request["request_sha256"], "processing_status": processing_status,
                        "response_origin": origin, "response_origin_verified": False,
                        "validation_error_type": error_type, "assessment": assessment})
    counts = dict(Counter(row["processing_status"] for row in results))
    judgment_counts = dict(Counter(j["membership"] for row in results for j in row["assessment"]["judgments"]))
    summary = {"format_version": REPLAY_FORMAT, "status": "draft_ai_unreviewed",
               "scope": "frozen_active_countable_native_source_records", "question_count": 24,
               "selected_records": len(results), "judgment_slots": len(results) * 24,
               "processing_status_counts": counts, "responses_provided": len(provided),
               "judgment_membership_counts": judgment_counts, "reviewed_units": 0,
               "article_negative_units": 0,
               "source_manifest_sha256": source["manifest_sha256"],
               "prepared_manifest_sha256": frozen["manifest_sha256"],
               "responses_sha256": original.digest(response_bytes),
               "selection_sha256": source["summary"]["selection_sha256"],
               "request_ids_sha256": frozen["summary"]["request_ids_sha256"],
               "code_fingerprints": code_fingerprints(), "response_origin": "external_replay_unverified",
               "response_origin_verified": False, "review_required": True, "publication_status": "hold",
               **PENDING_FLAGS, **NO_ACTIONS}
    files = {"results.jsonl": jsonl_bytes(results), "coverage_summary.json": original.encoded(summary),
             "inputs/responses.json": response_bytes, "inputs/prepared_manifest.json": frozen["manifest_bytes"],
             "inputs/source_manifest.json": source["manifest_bytes"], "inputs/requests.jsonl": frozen["files"]["requests.jsonl"],
             **{f"inputs/{name}": source["files"][name] for name in INPUT_NAMES}}
    write_bundle(output, files, {"format_version": REPLAY_FORMAT, "status": "draft_ai_unreviewed",
                                "source_manifest_sha256": source["manifest_sha256"],
                                "prepared_manifest_sha256": frozen["manifest_sha256"],
                                "responses_sha256": original.digest(response_bytes),
                                "response_origin": "external_replay_unverified", "response_origin_verified": False,
                                "review_required": True, "publication_status": "hold", **PENDING_FLAGS, **NO_ACTIONS})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    first = actions.add_parser("prepare", help="Prepare deterministic requests for every selected record")
    first.add_argument("--packet", type=Path, required=True)
    first.add_argument("--out", type=Path, required=True)
    first.add_argument("--max-input-tokens", type=int, default=24000)
    second = actions.add_parser("replay", help="Validate external responses; missing and invalid replies remain unknown")
    second.add_argument("--packet", type=Path, required=True)
    second.add_argument("--prepared", type=Path, required=True)
    second.add_argument("--responses", type=Path, required=True)
    second.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (prepare(args.packet, args.out, max_input_tokens=args.max_input_tokens)
                  if args.action == "prepare" else replay(args.packet, args.prepared, args.responses, args.out))
    except Exception as exc:
        # Do not echo exception messages, source text, paths or credentials.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
