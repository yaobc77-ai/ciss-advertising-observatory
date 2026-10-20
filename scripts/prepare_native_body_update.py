"""Prepare reviewed saved-text updates; apply only with explicit review and guards.

Preparation is offline. No review is invented, metadata is not replaced from the
original workbook, and old annotations never become labels of the new body.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import prepare_native_body_review as body_review
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from observatory.chunking import retrieval_spans
from observatory.evaluate import EvaluationInvalid, canonical_digest, strict_json_loads
from observatory.import_records import CanonicalRecord
from observatory.models import ImportBatch, Issue
from observatory.quality import body_hash, inspect_body

original = body_review.original
REVIEW_FORMAT = "native-body-update-review-v1"
PLAN_FORMAT = "native-body-update-plan-v1"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["pending", "adopt", "reject"]
    source_identity: Literal["pending", "confirmed", "rejected"]
    retrieval: Literal["pending", "enable", "disable"]
    retained_ranges: list[tuple[int, int]] | None
    original_page_completeness: Literal["unknown", "partial", "complete"]
    reviewer_type: Literal["human", "ai"] | None
    reviewer: str | None
    reviewed_at: str | None
    note: str | None
    evidence_refs: list[str]

    @model_validator(mode="after")
    def check_decision(self):
        if self.decision == "pending":
            if (self.source_identity != "pending" or self.retrieval != "pending"
                    or self.retained_ranges is not None or self.original_page_completeness != "unknown"
                    or any(v is not None for v in (self.reviewer_type, self.reviewer, self.reviewed_at, self.note))
                    or self.evidence_refs):
                raise ValueError("Pending decisions must not contain approval assertions")
            return self
        if not self.reviewer_type or any(not isinstance(v, str) or not v.strip() for v in (self.reviewer, self.reviewed_at, self.note)):
            raise ValueError("A completed decision needs reviewer type, reviewer, timestamp and note")
        timestamp = datetime.fromisoformat(self.reviewed_at)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Review timestamp must include a timezone")
        if not self.evidence_refs or any(not r.strip() for r in self.evidence_refs):
            raise ValueError("A completed decision needs source evidence references")
        if self.decision == "adopt" and (self.source_identity != "confirmed" or self.retrieval == "pending"):
            raise ValueError("Adoption requires confirmed source identity and an explicit retrieval decision")
        if self.decision == "reject" and (self.retrieval != "disable" or self.retained_ranges is not None):
            raise ValueError("A rejected candidate cannot enable retrieval or retain ranges")
        if self.retrieval == "disable" and self.retained_ranges is not None:
            raise ValueError("Disabled retrieval must not contain retained ranges")
        if self.retrieval == "enable" and not self.retained_ranges:
            raise ValueError("Enabled retrieval requires explicit retained ranges")
        return self


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["native-body-update-review-v1"]
    review_id: str | None
    source_packet_manifest_sha256: str
    body_packet_manifest_sha256: str
    decisions: dict[str, Decision]

    @model_validator(mode="after")
    def named_completed_review(self):
        if any(d.decision != "pending" for d in self.decisions.values()) and (not self.review_id or not self.review_id.strip()):
            raise ValueError("Completed decisions require a review_id")
        return self


def load_packets(source_packet, body_packet):
    source = body_review.load_source_packet(source_packet)
    root = Path(body_packet)
    manifest_path = body_review.packet_path(root, "packet_manifest.json")
    data = original.read_bytes(manifest_path)
    try:
        manifest = strict_json_loads(data)
    except EvaluationInvalid as exc:
        raise ValueError(str(exc)) from exc
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != body_review.FORMAT
            or manifest.get("complete") is not True or manifest.get("importable") is not False
            or manifest.get("source_associations_approved") is not False or manifest.get("labels_published") is not False
            or manifest.get("source_packet_manifest_sha256") != source["manifest_sha256"]):
        raise ValueError("Matching complete pending body packet required")
    hashes = manifest.get("artifacts")
    if not isinstance(hashes, dict) or len(hashes) > 5000 or "packet_manifest.json" in hashes:
        raise ValueError("Body packet artifact manifest required")
    files, paths, total = {}, {}, 0
    for name, fingerprint in hashes.items():
        path = body_review.packet_path(root, name)
        content = original.read_bytes(path)
        total += len(content)
        if total > body_review.MAX_PACKET_BYTES:
            raise ValueError("Body packet too large")
        if original.digest(content) != fingerprint:
            raise ValueError("Body packet artifact changed")
        files[name], paths[name] = content, path
    if any(files.get(f"inputs/{name}") != source["files"][name] for name in body_review.ESSENTIAL_INPUTS):
        raise ValueError("Body packet copied inputs differ from source packet")
    if files.get("inputs/source_packet_manifest.json") != source["manifest_bytes"]:
        raise ValueError("Body packet copied source manifest differs")
    scope_keys = {"selected_article_ids", "source_articles_with_retained_input", "source_articles_without_retained_input"}
    explicit_scope = "selected_article_ids" in manifest
    if not explicit_scope and scope_keys & set(manifest):
        raise ValueError("Body packet selection fields require selected_article_ids")
    selected_ids = body_review.select_article_ids(source, manifest["selected_article_ids"] if explicit_scope else None)
    if explicit_scope:
        scope = body_review.selection_fields(source, selected_ids)
        if canonical_digest({key: manifest.get(key) for key in scope}) != canonical_digest(scope):
            raise ValueError("Body packet selection is not canonical or counts differ")
        summary = strict_json_loads(files.get("preparation_summary.json", b"null"))
        expected_summary = {**scope, "selected_groups": len(selected_ids),
                            "selected_input_paragraphs": sum(len(source["paragraphs"].get(aid, [])) for aid in selected_ids)}
        if (not isinstance(summary, dict)
                or canonical_digest({key: summary.get(key) for key in expected_summary}) != canonical_digest(expected_summary)):
            raise ValueError("Body packet selection summary differs from frozen sources")
    elif isinstance(summary := strict_json_loads(files.get("preparation_summary.json", b"null")), dict) and scope_keys & set(summary):
        raise ValueError("Body packet selection summary lacks manifest scope")
    by_url = defaultdict(list)
    for row in source["snapshot"]["records"]:
        if row["dataset"] == "native" and row["active"] is True:
            by_url[row["payload"]["url"]].append(row)
    comparisons = [body_review.compare_group(source, article_id, by_url)
                   for article_id in selected_ids]
    body_review.validate_comparison_targets(comparisons)
    if explicit_scope:
        coverage = body_review.ordered_coverage_counts(comparisons)
        if canonical_digest({key: summary.get(key) for key in coverage}) != canonical_digest(coverage):
            raise ValueError("Body packet ordered coverage summary differs from retained inputs")
    proposals = [p for c in comparisons if (p := body_review.body_proposal(source, c)) is not None]
    try:
        if (strict_json_loads(files.get("body_comparisons.json", b"null")) != strict_json_loads(original.encoded(comparisons))
                or strict_json_loads(files.get("pending_body_proposals.json", b"null")) != strict_json_loads(original.encoded(proposals))):
            raise ValueError("Body comparisons or proposals differ from frozen source")
    except EvaluationInvalid as exc:
        raise ValueError(str(exc)) from exc
    for comparison in comparisons:
        article_id = comparison["upstream_article_id"]
        if files.get(f"original/{article_id}.txt") != source["sources"][article_id]["bytes"]:
            raise ValueError("Candidate TXT differs from original source")
        current = comparison["current_record"]
        if current and files.get(f"current/{article_id}.txt") != current["body"].encode("utf-8"):
            raise ValueError("Current TXT differs from frozen snapshot")
    return {"source": source, "body_files": files, "body_paths": paths,
            "body_manifest_path": manifest_path, "body_manifest_bytes": data,
            "body_manifest_sha256": original.digest(data), "proposals": proposals}


def verify_unchanged(packet, review_path=None, review_bytes=None):
    source = packet["source"]
    pairs = [(source["manifest_path"], source["manifest_bytes"]),
             (packet["body_manifest_path"], packet["body_manifest_bytes"])]
    pairs += [(p, source["files"][name]) for name, p in source["paths"].items()]
    pairs += [(p, packet["body_files"][name]) for name, p in packet["body_paths"].items()]
    if review_path is not None:
        pairs.append((Path(review_path), review_bytes))
    if any(original.read_bytes(path) != data for path, data in pairs):
        raise ValueError("Reviewed inputs changed during preparation")


def new_output(path, packet):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError("New private output required")
    inputs = [packet["source"]["manifest_path"].parent, packet["body_manifest_path"].parent]
    if any(path.resolve().is_relative_to(root.resolve()) for root in inputs):
        raise ValueError("Output must not modify input packets")
    return path


def write_review_template(source_packet, body_packet, out_file):
    packet = load_packets(source_packet, body_packet)
    path = new_output(out_file, packet)
    decision = {"decision": "pending", "source_identity": "pending", "retrieval": "pending",
                "retained_ranges": None, "original_page_completeness": "unknown",
                "reviewer_type": None, "reviewer": None, "reviewed_at": None, "note": None, "evidence_refs": []}
    value = {"schema_version": REVIEW_FORMAT, "review_id": None,
             "source_packet_manifest_sha256": packet["source"]["manifest_sha256"],
             "body_packet_manifest_sha256": packet["body_manifest_sha256"],
             "decisions": {p["proposal_id"]: deepcopy(decision) for p in packet["proposals"]}}
    verify_unchanged(packet)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(original.encoded(value))
    return {"review_template": str(path), "pending_decisions": len(value["decisions"]),
            "reviewer": None, "model_calls": 0, "database_writes": 0}


def reviewed_record(proposal, decision, review, review_sha256):
    payload = deepcopy(proposal["previous_payload"])
    candidate = proposal["candidate_text"]
    text = candidate["body"]
    retained = decision.retained_ranges if decision.retrieval == "enable" else None
    if retained is not None:
        retrieval_spans(text, retrieval_ranges=retained)
    selected = "\n\n".join(text[start:end] for start, end in retained) if retained else text
    quality = inspect_body(selected)
    if decision.retrieval == "enable" and (
        not payload["countable"] or payload["raw"].get("admission_review", {}).get("body_mode") == "metadata_only"
        or any(i.severity != "info" for i in quality)
    ):
        raise ValueError("Enabled retrieval conflicts with current counting/admission or selected-text quality")
    source_name = "saved-txt:" + proposal["source_binding"]["source_text_sha256"]
    for issue in quality:
        issue.source = source_name
    previous_body_issues = [deepcopy(i) for i in payload.get("issues", [])
                            if i["code"].startswith("body_") or i["code"] in (
                                "duplicate_body", "historical_annotations_prior_body")]
    issues = [Issue.model_validate(i) for i in payload.get("issues", [])
              if not i["code"].startswith("body_") and i["code"] not in (
                  "duplicate_body", "historical_annotations_prior_body")]
    issues.extend(quality)
    issues.append(Issue(
        code="body_saved_text_reviewed", severity="info", source=source_name,
        detail=f"{decision.reviewer_type} engineering review {review.review_id}: adopted the unchanged supplied TXT. "
               "This does not verify the original webpage, OCR accuracy, video or advertiser claims.",
    ))
    if retained:
        issues.append(Issue(
            code="body_navigation_intervals_reviewed", severity="info", source=source_name,
            detail="Retrieval uses only the explicitly reviewed character intervals; the complete supplied TXT remains stored unchanged.",
        ))
    if decision.original_page_completeness != "complete":
        issues.append(Issue(code=("body_source_partial" if decision.original_page_completeness == "partial"
                                  else "body_source_completeness_unestablished"), severity="info", source=source_name,
                            detail="Reviewed saved TXT is not established as a complete original webpage; absence claims remain unsupported."))
    if payload.get("annotations"):
        issues.append(Issue(code="historical_annotations_prior_body", severity="info", source=source_name,
                            detail="Old annotations remain with the previous version; they do not label the new TXT body."))
    raw = payload["raw"]
    raw["previous_body"] = payload["body"]
    raw["previous_body_annotations"] = payload.get("annotations", [])
    raw["previous_body_issues"] = previous_body_issues
    if "duplicate_body_record_ids" in raw:
        raw["previous_body_duplicate_record_ids"] = raw.pop("duplicate_body_record_ids")
    old_body_reviews = {key: raw.pop(key) for key in ("body_review", "body_recovery", "body_update") if key in raw}
    if old_body_reviews:
        raw["previous_body_reviews"] = old_body_reviews
    raw["body_sha256"] = candidate["body_sha256"]
    raw["body_update"] = {
        "schema_version": REVIEW_FORMAT, "review_id": review.review_id, "review_sha256": review_sha256,
        "proposal_id": proposal["proposal_id"], "previous_binding": proposal["target_binding"],
        "previous_retrieval_end": payload.get("retrieval_end"), "previous_retrieval_ranges": payload.get("retrieval_ranges"),
        "source_binding": proposal["source_binding"], "provided_metadata": proposal["provided_metadata"],
        "review": decision.model_dump(mode="json"),
    }
    payload.update({"body": text, "annotations": [], "retrievable": decision.retrieval == "enable",
                    "retrieval_end": None if retained else 0, "retrieval_ranges": retained,
                    "issues": [i.model_dump(mode="json") for i in issues], "raw": raw})
    payload["provenance"].append({"source": source_name, "sha256": candidate["body_sha256"],
                                  "source_asset_id": "sha256:" + candidate["body_sha256"],
                                  "role": "reviewed_saved_text_update", "review_id": review.review_id,
                                  "review_sha256": review_sha256, "reviewer_type": decision.reviewer_type,
                                  "source_binding": proposal["source_binding"],
                                  "coverage": decision.original_page_completeness})
    # Use the standard strict record schema without a JSONL provenance append
    # that would change the target version on each plan export.
    record = CanonicalRecord.model_validate_json(original.encoded(payload))
    if body_hash(record.body) != candidate["body_sha256"]:
        raise ValueError("Candidate body hash differs after record validation")
    return record


@dataclass(frozen=True)
class PreparedBodyUpdates:
    batch: ImportBatch
    expected_current: dict
    summary: dict
    packet: dict
    review_path: Path
    review_bytes: bytes
    prepared_sha256: str


def preparation_digest(batch, expected_current, summary):
    return canonical_digest({"batch": batch.model_dump(mode="json"),
                             "expected_current": expected_current, "summary": summary})


def verify_prepared(prepared):
    if preparation_digest(prepared.batch, prepared.expected_current, prepared.summary) != prepared.prepared_sha256:
        raise ValueError("Prepared update changed after review validation")


def prepare_updates(source_packet, body_packet, review_file):
    packet = load_packets(source_packet, body_packet)
    review_bytes = original.read_bytes(review_file)
    try:
        strict_json_loads(review_bytes)
        review = Review.model_validate_json(review_bytes)
    except (EvaluationInvalid, ValidationError) as exc:
        raise ValueError("Invalid body update review") from exc
    if (review.source_packet_manifest_sha256 != packet["source"]["manifest_sha256"]
            or review.body_packet_manifest_sha256 != packet["body_manifest_sha256"]
            or set(review.decisions) != {p["proposal_id"] for p in packet["proposals"]}):
        raise ValueError("Review scope or packet fingerprints differ")
    review_sha = original.digest(review_bytes)
    records, expected = [], {}
    for proposal in packet["proposals"]:
        decision = review.decisions[proposal["proposal_id"]]
        if decision.decision != "adopt":
            continue
        record = reviewed_record(proposal, decision, review, review_sha)
        records.append(record)
        binding = proposal["target_binding"]
        expected[record.record_id] = {"version_id": binding["expected_current_version_id"],
                                      "body_sha256": binding["expected_current_body_sha256"],
                                      "url": binding["url"], "dataset": "native"}
    hashes = {"source_packet_manifest": packet["source"]["manifest_sha256"],
              "body_packet_manifest": packet["body_manifest_sha256"], "body_update_review": review_sha}
    states = Counter(d.decision for d in review.decisions.values())
    summary = {"schema_version": PLAN_FORMAT, "review_id": review.review_id,
               "source_hashes": hashes, "decision_counts": dict(states), "prepared_updates": len(records),
               "target_versions": {r.record_id: canonical_digest(r.model_dump(mode="json")) for r in records},
               "retrievable_updates": sum(r.retrievable for r in records),
               "publication_applied": False, "model_calls": 0, "network_calls": 0, "database_writes": 0,
               "reviewer_identity": "asserted_in_review_file_not_independently_authenticated",
               "classification_results_published": 0,
               "limits": "Preparation validates a recorded decision; it does not create source approval, gold labels or customer acceptance."}
    verify_unchanged(packet, review_file, review_bytes)
    batch = ImportBatch(records=records, source_hashes=hashes)
    return PreparedBodyUpdates(batch, expected, summary, packet, Path(review_file), review_bytes,
                               preparation_digest(batch, expected, summary))


def write_plan(prepared, out_dir):
    verify_prepared(prepared)
    output = new_output(out_dir, prepared.packet)
    if prepared.review_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("Output must not contain the input review")
    verify_unchanged(prepared.packet, prepared.review_path, prepared.review_bytes)
    plan = {"schema_version": PLAN_FORMAT, "summary": prepared.summary,
            "updates": [{"record_payload": r.model_dump(mode="json"),
                         "expected_current": prepared.expected_current[r.record_id],
                         "target_version_id": prepared.summary["target_versions"][r.record_id]}
                        for r in prepared.batch.records], "importable_as_generic_jsonl": False}
    files = {"review.json": prepared.review_bytes, "update_plan.json": original.encoded(plan),
             "preparation_summary.json": original.encoded(prepared.summary)}
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (output / name).write_bytes(content)
    (output / "plan_manifest.json").write_bytes(original.encoded({
        "schema_version": PLAN_FORMAT, "complete": True,
        "artifacts": {name: original.digest(data) for name, data in files.items()},
        "publication_applied": False,
    }))
    return prepared.summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("review-template", "plan", "apply"))
    parser.add_argument("--source-packet", required=True, type=Path)
    parser.add_argument("--body-packet", required=True, type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "review-template":
        if args.review:
            parser.error("review-template does not accept --review")
        result = write_review_template(args.source_packet, args.body_packet, args.out)
    else:
        if not args.review:
            parser.error("plan and apply require --review")
        prepared = prepare_updates(args.source_packet, args.body_packet, args.review)
        if args.command == "apply" and not prepared.batch.records:
            raise ValueError("No adopted updates; database access is not needed")
        result = write_plan(prepared, args.out)
        if args.command == "apply":
            # Explicit apply is a local maintenance operation. It never requests
            # embeddings, and review assertions do not authorize remote writes.
            from observatory.config import Settings
            from observatory.db import Database

            verify_unchanged(prepared.packet, prepared.review_path, prepared.review_bytes)
            verify_prepared(prepared)
            db = Database(Settings.from_env().database_url)
            imported = db.import_batch(prepared.batch, expected_current=prepared.expected_current)
            result = {**result, "publication_applied": True, "import_report": imported}
            (args.out / "apply_receipt.json").write_bytes(original.encoded(result))
    print(original.encoded(result).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
