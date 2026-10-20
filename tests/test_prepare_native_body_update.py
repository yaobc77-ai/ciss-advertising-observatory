"""Synthetic review/update checks; no real source decisions, models or databases."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_prepare_native_body_review as body_tests
from pydantic import ValidationError

from observatory.models import RecordInput
from observatory.quality import body_hash

SPEC = importlib.util.spec_from_file_location(
    "prepare_native_body_update_tests",
    Path(__file__).parents[1] / "scripts/prepare_native_body_update.py",
)
review = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    item = body_tests.inputs.__wrapped__(tmp_path, monkeypatch)
    raw = (body_tests.source_tests.PARAGRAPH + "\r\n\r\n") * 4 + "Footer\r\n"
    item.raw = raw.encode("utf-8")
    item.manual_zip.write_bytes(body_tests.source_tests.source_zip(
        body_tests.source_tests.workbook_bytes(body_tests.source_tests.metadata_rows()), {
            "0.txt": item.raw,
            "1.txt": (body_tests.source_tests.OTHER + "\r\n").encode("utf-8"),
        },
    ))
    item.cleaned_csv.write_bytes(body_tests.source_tests.csv_data(
        ["id", "text"], [["0", item.canonical]] * 4 + [["1", body_tests.source_tests.OTHER]],
    ))
    item.input_csv.write_bytes(body_tests.source_tests.csv_data(
        ["id", "article_id", "text"], [[str(i), "0", item.canonical] for i in range(1, 5)],
    ))
    old_body = "Old article text contains its own original character positions."
    item.payload = RecordInput(
        record_id="current-record", dataset="native", url="https://example.org/original",
        publisher="Current Outlet", title="Current title", published_at="2020-05-06",
        sponsor="Current Sponsor", keyword="Different collection term", platform="",
        account="", body=old_body, disclosure="Paid by the current sponsor",
        archive_url="https://example.org/archived-original", countable=True, retrievable=False,
        retrieval_end=8, retrieval_ranges=[(0, 8)],
        raw={"baseline": {"article": old_body, "notes": "Original baseline retained"},
             "metadata": {"original_field": "Preserve this"}, "body_sha256": body_hash(old_body),
             "date_precision": "day", "date_source": "baseline.csv",
             "body_review": {"retained_ranges": [[0, 8]], "body_sha256": body_hash(old_body)},
             "body_recovery": {"coverage": "partial", "extracted_text_sha256": body_hash(old_body)},
             "body_update": {"review_id": "previous-review", "old": True}},
        annotations=[{"version": "claims-calibrated", "labels": ["prior_label"],
                      "body_sha256": body_hash(old_body), "start": 0, "end": 3}],
        provenance=[{"source": "baseline.csv", "sha256": "b" * 64, "role": "baseline", "row": 2}],
        issues=[{"code": "body_video_placeholder", "severity": "review", "detail": "Prior body signal"},
                {"code": "date_missing", "severity": "review", "detail": "Metadata signal retained"}],
    ).model_dump(mode="json")
    item.review_file = tmp_path / "body-update-review.json"
    item.plan_output = tmp_path / "body-update-plan"
    return item


def make_packets(inputs):
    snapshot = {"records": [body_tests.bind_row(inputs.payload)], "observation": {"synthetic": True}}
    inputs.current_snapshot.write_bytes(review.original.encoded(snapshot))
    body_tests.source_tests.prepare(inputs)
    review.body_review.write_packet(inputs.output, inputs.body_output)
    result = review.write_review_template(inputs.output, inputs.body_output, inputs.review_file)
    assert result["pending_decisions"] == 1
    return inputs


@pytest.fixture
def packets(inputs):
    return make_packets(inputs)


@pytest.fixture
def explicit_packets(inputs):
    article_ids = body_tests.prepare_six_sources(inputs, payload_template=inputs.payload)
    review.body_review.write_packet(inputs.output, inputs.body_output, article_ids=list(reversed(article_ids)))
    result = review.write_review_template(inputs.output, inputs.body_output, inputs.review_file)
    assert result["pending_decisions"] == 6
    return inputs


def read_json(path):
    return json.loads(path.read_bytes())


def update_review(inputs, **changes):
    value = read_json(inputs.review_file)
    value["review_id"] = "synthetic-review-1"
    key = next(iter(value["decisions"]))
    decision = {
        "decision": "adopt", "source_identity": "confirmed", "retrieval": "disable",
        "retained_ranges": None, "original_page_completeness": "unknown",
        "reviewer_type": "human", "reviewer": "Synthetic reviewer",
        "reviewed_at": "2026-10-06T05:00:00-04:00", "note": "Synthetic fixture decision only",
        "evidence_refs": ["original/0.txt", "source_workbook.xlsx:Sheet1:2"],
    }
    decision.update(changes)
    value["decisions"][key] = decision
    inputs.review_file.write_bytes(review.original.encoded(value))
    return value


def prepare(inputs):
    return review.prepare_updates(inputs.output, inputs.body_output, inputs.review_file)


def resign_body(inputs, name, value):
    body_tests.resign(inputs.body_output, name, value)


def prevent_settings_and_db(monkeypatch):
    def fail(*_args, **_kwargs):
        pytest.fail("Settings or database touched by an offline path")

    monkeypatch.setitem(sys.modules, "observatory.config", SimpleNamespace(
        Settings=SimpleNamespace(from_env=fail),
    ))
    monkeypatch.setitem(sys.modules, "observatory.db", SimpleNamespace(Database=fail))


def cli_args(inputs, command, *, out=None, with_review=True):
    args = ["prepare_native_body_update.py", command,
            "--source-packet", str(inputs.output), "--body-packet", str(inputs.body_output),
            "--out", str(inputs.plan_output if out is None else out)]
    if with_review:
        args += ["--review", str(inputs.review_file)]
    return args


def test_all_pending_template_and_plan_do_not_create_updates_or_approval(packets):
    value = read_json(packets.review_file)
    assert value["schema_version"] == review.REVIEW_FORMAT
    assert value["review_id"] is None
    assert value["source_packet_manifest_sha256"] == review.original.digest(
        (packets.output / "packet_manifest.json").read_bytes(),
    )
    assert value["body_packet_manifest_sha256"] == review.original.digest(
        (packets.body_output / "packet_manifest.json").read_bytes(),
    )
    decision = next(iter(value["decisions"].values()))
    assert decision == {
        "decision": "pending", "source_identity": "pending", "retrieval": "pending",
        "retained_ranges": None, "original_page_completeness": "unknown",
        "reviewer_type": None, "reviewer": None, "reviewed_at": None, "note": None,
        "evidence_refs": [],
    }
    prepared = prepare(packets)
    assert prepared.batch.records == [] and prepared.expected_current == {}
    assert prepared.summary["decision_counts"] == {"pending": 1}
    assert prepared.summary["prepared_updates"] == prepared.summary["retrievable_updates"] == 0
    assert prepared.summary["publication_applied"] is False
    assert prepared.summary["classification_results_published"] == 0
    assert prepared.summary["model_calls"] == prepared.summary["network_calls"] == prepared.summary["database_writes"] == 0
    review.write_plan(prepared, packets.plan_output)
    plan = read_json(packets.plan_output / "update_plan.json")
    assert plan["updates"] == [] and plan["importable_as_generic_jsonl"] is False


def test_adopt_disable_preserves_metadata_and_moves_old_evidence_to_history(packets):
    old = deepcopy(packets.payload)
    update_review(packets)
    prepared = prepare(packets)
    assert packets.payload == old
    current = prepared.batch.records[0].model_dump(mode="json")
    replaced = {"body", "retrievable", "retrieval_end", "retrieval_ranges", "raw", "provenance", "issues", "annotations"}
    assert {k: v for k, v in current.items() if k not in replaced} == {
        k: v for k, v in old.items() if k not in replaced
    }
    assert current["body"].encode("utf-8") == packets.raw
    assert current["body"] != old["body"]
    assert current["retrievable"] is False and current["retrieval_end"] == 0
    assert current["retrieval_ranges"] is None and current["annotations"] == []
    assert current["raw"]["baseline"] == old["raw"]["baseline"]
    assert current["raw"]["metadata"] == old["raw"]["metadata"]
    assert current["raw"]["previous_body"] == old["body"]
    assert current["raw"]["previous_body_annotations"] == old["annotations"]
    assert current["raw"]["previous_body_reviews"] == {
        key: old["raw"][key] for key in ("body_review", "body_recovery", "body_update")
    }
    assert "body_review" not in current["raw"] and "body_recovery" not in current["raw"]
    assert current["raw"]["body_sha256"] == body_hash(current["body"])
    update = current["raw"]["body_update"]
    assert update["previous_retrieval_end"] == old["retrieval_end"]
    assert update["previous_retrieval_ranges"] == old["retrieval_ranges"]
    assert update["provided_metadata"]["values"]["publisher"] == "Original Outlet"
    assert current["publisher"] == "Current Outlet"
    assert current["provenance"][:-1] == old["provenance"]
    assert current["provenance"][-1]["role"] == "reviewed_saved_text_update"
    codes = {i["code"] for i in current["issues"]}
    assert "date_missing" in codes and "historical_annotations_prior_body" in codes
    assert "body_video_placeholder" not in codes
    assert "body_source_completeness_unestablished" in codes
    assert "body_saved_text_reviewed" in codes
    assert "body_navigation_intervals_reviewed" not in codes
    assert prepared.expected_current == {old["record_id"]: {
        "version_id": review.original.canonical_digest(old), "body_sha256": body_hash(old["body"]),
        "url": old["url"], "dataset": "native",
    }}


@pytest.mark.parametrize("reviewer_type", ["human", "ai"])
def test_adopt_enable_requires_new_ranges_and_records_reviewer_assertion(packets, reviewer_type):
    text = packets.raw.decode("utf-8")
    end = text.index("Footer")
    update_review(packets, retrieval="enable", retained_ranges=[[0, end]], reviewer_type=reviewer_type)
    prepared = prepare(packets)
    record = prepared.batch.records[0]
    assert record.retrievable is True
    assert record.retrieval_ranges == [(0, end)] and record.retrieval_end is None
    assert record.annotations == []
    assert record.raw["body_update"]["review"]["reviewer_type"] == reviewer_type
    assert record.provenance[-1]["coverage"] == "unknown"
    notes = {issue.code: issue.detail for issue in record.issues}
    assert "body_navigation_intervals_reviewed" in notes
    assert notes["body_saved_text_reviewed"].startswith(f"{reviewer_type} engineering review")
    assert prepared.summary["retrievable_updates"] == 1
    assert prepared.summary["reviewer_identity"] == "asserted_in_review_file_not_independently_authenticated"
    assert prepared.summary["classification_results_published"] == 0


@pytest.mark.parametrize("completeness,code", [
    ("unknown", "body_source_completeness_unestablished"), ("partial", "body_source_partial"),
    ("complete", None),
])
def test_completeness_is_explicit_review_assertion_not_implied_by_matching(packets, completeness, code):
    update_review(packets, original_page_completeness=completeness)
    record = prepare(packets).batch.records[0]
    codes = {i.code for i in record.issues}
    assert record.raw["body_update"]["review"]["original_page_completeness"] == completeness
    assert record.provenance[-1]["coverage"] == completeness
    if code:
        assert code in codes
    else:
        assert not codes & {"body_source_partial", "body_source_completeness_unestablished"}
    assert record.retrievable is False


def test_version_and_plan_bytes_are_deterministic_across_repeated_preparation(packets):
    update_review(packets)
    first, second = prepare(packets), prepare(packets)
    assert first.batch.model_dump(mode="json") == second.batch.model_dump(mode="json")
    assert first.expected_current == second.expected_current and first.summary == second.summary
    assert first.summary["target_versions"]["current-record"] == review.original.canonical_digest(
        first.batch.records[0].model_dump(mode="json"),
    )
    destination = packets.plan_output.with_name("another-plan")
    review.write_plan(first, packets.plan_output)
    review.write_plan(second, destination)
    assert {p.name: p.read_bytes() for p in packets.plan_output.iterdir()} == {
        p.name: p.read_bytes() for p in destination.iterdir()
    }
    assert len(first.batch.records[0].provenance) == len(packets.payload["provenance"]) + 1
    assert not any(p.get("role") == "canonical_import" for p in first.batch.records[0].provenance)


def test_rejected_source_does_not_create_positive_or_negative_labels(packets):
    update_review(packets, decision="reject", source_identity="rejected")
    prepared = prepare(packets)
    assert prepared.batch.records == [] and prepared.expected_current == {}
    assert prepared.summary["decision_counts"] == {"reject": 1}
    assert prepared.summary["classification_results_published"] == 0


@pytest.mark.parametrize("field,value", [
    ("source_identity", "confirmed"), ("retrieval", "disable"), ("retained_ranges", [[0, 1]]),
    ("original_page_completeness", "complete"), ("reviewer_type", "ai"),
    ("reviewer", "Someone"), ("reviewed_at", "2026-10-06T00:00:00Z"),
    ("note", "Already checked"), ("evidence_refs", ["source"]),
])
def test_pending_decision_cannot_smuggle_completed_review_fields(packets, field, value):
    document = read_json(packets.review_file)
    next(iter(document["decisions"].values()))[field] = value
    packets.review_file.write_bytes(review.original.encoded(document))
    with pytest.raises(ValueError, match="Invalid body update review"):
        prepare(packets)


@pytest.mark.parametrize("change", [
    {"reviewer": None}, {"reviewer": "  "}, {"reviewer_type": None}, {"reviewer_type": "review-bot"},
    {"reviewed_at": "2026-10-06T05:00:00"}, {"reviewed_at": "not-a-date"},
    {"note": " "}, {"evidence_refs": []}, {"evidence_refs": [" "]},
    {"source_identity": "pending"}, {"retrieval": "pending"},
    {"retained_ranges": [[0, 2]]},
])
def test_adoption_requires_explicit_complete_review_fields(packets, change):
    update_review(packets, **change)
    with pytest.raises(ValueError, match="Invalid body update review"):
        prepare(packets)


@pytest.mark.parametrize("ranges", [[], [[True, 8]], [[0, "8"]], [[2, 1]],
                                    [[0, 999999]], [[0, 10], [9, 20]]])
def test_enabled_ranges_must_be_explicit_valid_new_body_offsets(packets, ranges):
    update_review(packets, retrieval="enable", retained_ranges=ranges)
    with pytest.raises((ValueError, ValidationError)):
        prepare(packets)


@pytest.mark.parametrize("change", [
    {"countable": False}, {"raw": {"admission_review": {"body_mode": "metadata_only"}}},
])
def test_enable_does_not_bypass_existing_counting_or_metadata_only_admission(inputs, change):
    inputs.payload.update(change)
    make_packets(inputs)
    update_review(inputs, retrieval="enable", retained_ranges=[[0, len(inputs.raw.decode("utf-8"))]])
    with pytest.raises(ValueError, match="conflicts with current counting/admission"):
        prepare(inputs)


def test_short_selected_text_cannot_be_enabled_by_review_alone(packets):
    update_review(packets, retrieval="enable", retained_ranges=[[0, len(body_tests.source_tests.PARAGRAPH)]])
    with pytest.raises(ValueError, match="selected-text quality"):
        prepare(packets)


def test_empty_old_annotations_do_not_create_historical_label_warning(inputs):
    inputs.payload["annotations"] = []
    make_packets(inputs)
    update_review(inputs)
    record = prepare(inputs).batch.records[0]
    assert record.raw["previous_body_annotations"] == []
    assert "historical_annotations_prior_body" not in {i.code for i in record.issues}


def test_old_duplicate_body_markers_do_not_describe_replacement_text(inputs):
    inputs.payload["raw"]["duplicate_body_record_ids"] = ["current-record", "another-old-record"]
    inputs.payload["issues"].append({"code": "duplicate_body", "severity": "info", "detail": "Old body duplicate"})
    make_packets(inputs)
    update_review(inputs)
    record = prepare(inputs).batch.records[0]
    assert "duplicate_body" not in {i.code for i in record.issues}
    assert "duplicate_body_record_ids" not in record.raw
    assert record.raw["previous_body"] == inputs.payload["body"]
    assert record.raw["previous_body_duplicate_record_ids"] == ["current-record", "another-old-record"]
    assert any(issue["code"] == "duplicate_body" for issue in record.raw["previous_body_issues"])


@pytest.mark.parametrize("mutation", ["source_hash", "body_hash", "missing_decision", "extra_decision", "review_id"])
def test_review_exact_packet_scope_and_completed_review_id_required(packets, mutation):
    value = update_review(packets)
    if mutation == "source_hash":
        value["source_packet_manifest_sha256"] = "0" * 64
    elif mutation == "body_hash":
        value["body_packet_manifest_sha256"] = "0" * 64
    elif mutation == "missing_decision":
        value["decisions"] = {}
    elif mutation == "extra_decision":
        value["decisions"]["not-a-proposal"] = deepcopy(next(iter(value["decisions"].values())))
    else:
        value["review_id"] = None
    packets.review_file.write_bytes(review.original.encoded(value))
    with pytest.raises(ValueError):
        prepare(packets)


@pytest.mark.parametrize("where", ["review", "decision"])
def test_unknown_review_fields_rejected_instead_of_ignored(packets, where):
    value = read_json(packets.review_file)
    target = value if where == "review" else next(iter(value["decisions"].values()))
    target["annotations"] = [{"label": "unreviewed"}]
    packets.review_file.write_bytes(review.original.encoded(value))
    with pytest.raises(ValueError, match="Invalid body update review"):
        prepare(packets)


def test_duplicate_json_review_keys_rejected(packets):
    data = packets.review_file.read_bytes()
    packets.review_file.write_bytes(b'{"review_id":null,' + data[1:])
    with pytest.raises(ValueError, match="Invalid body update review"):
        prepare(packets)


@pytest.mark.parametrize("name", ["body_comparisons.json", "pending_body_proposals.json", "original/0.txt",
                                  "current/0.txt", "inputs/source_packet_manifest.json"])
def test_any_body_packet_artifact_change_rejected_without_resigning(packets, name):
    path = packets.body_output / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Body packet artifact changed"):
        prepare(packets)


@pytest.mark.parametrize("field,value", [
    ("complete", False), ("importable", True), ("source_associations_approved", True),
    ("labels_published", True), ("source_packet_manifest_sha256", "0" * 64),
])
def test_body_manifest_must_remain_complete_pending_and_bound(packets, field, value):
    manifest = read_json(packets.body_output / "packet_manifest.json")
    manifest[field] = value
    (packets.body_output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="Matching complete pending body packet required"):
        prepare(packets)


@pytest.mark.parametrize("path", ["../escape.txt", "original\\0.txt", "C:/escape.txt", "/escape.txt"])
def test_body_manifest_unsafe_paths_rejected(packets, path):
    manifest = read_json(packets.body_output / "packet_manifest.json")
    manifest["artifacts"][path] = "0" * 64
    (packets.body_output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="unsafe_packet_artifact_path"):
        prepare(packets)


def test_duplicate_body_manifest_keys_rejected(packets):
    path = packets.body_output / "packet_manifest.json"
    path.write_bytes(b'{"complete":true,' + path.read_bytes()[1:])
    with pytest.raises(ValueError, match="(?i)duplicate"):
        prepare(packets)


@pytest.mark.parametrize("mutation", ["previous_payload", "target_binding", "candidate_text", "duplicate"])
def test_rehashed_proposals_are_recomputed_against_original_frozen_source(packets, mutation):
    proposals = read_json(packets.body_output / "pending_body_proposals.json")
    if mutation == "duplicate":
        proposals.append(deepcopy(proposals[0]))
    elif mutation == "previous_payload":
        proposals[0][mutation]["publisher"] = "Wrong publisher"
    elif mutation == "target_binding":
        proposals[0][mutation]["expected_current_version_id"] = "0" * 64
    else:
        proposals[0][mutation]["body"] += " Fabricated text"
    resign_body(packets, "pending_body_proposals.json", proposals)
    with pytest.raises(ValueError, match="comparisons or proposals differ"):
        review.load_packets(packets.output, packets.body_output)


def test_rehashed_comparison_cannot_assert_source_approval(packets):
    comparisons = read_json(packets.body_output / "body_comparisons.json")
    comparisons[0]["source_identity"] = "confirmed"
    resign_body(packets, "body_comparisons.json", comparisons)
    with pytest.raises(ValueError, match="comparisons or proposals differ"):
        review.load_packets(packets.output, packets.body_output)


@pytest.mark.parametrize("name", ["original/0.txt", "current/0.txt", "inputs/source_packet_manifest.json",
                                  "inputs/source_workbook.xlsx"])
def test_rehashed_body_packet_files_must_still_match_frozen_inputs(packets, name):
    path = packets.body_output / name
    resign_body(packets, name, path.read_bytes() + b" Edited after freezing")
    with pytest.raises(ValueError, match="differs|differ"):
        review.load_packets(packets.output, packets.body_output)


def test_source_packet_drift_invalidates_review_even_without_body_packet_changes(packets):
    path = packets.output / "original/0.txt"
    path.write_bytes(path.read_bytes() + b" Source drift")
    with pytest.raises(ValueError, match="source_packet_artifact_changed"):
        prepare(packets)


@pytest.mark.parametrize("source", ["review", "source", "body"])
def test_inputs_changed_after_preparation_prevent_plan_publication(packets, source):
    prepared = prepare(packets)
    path = {"review": packets.review_file, "source": packets.output / "original/0.txt",
            "body": packets.body_output / "original/0.txt"}[source]
    path.write_bytes(path.read_bytes() + b" Drift")
    with pytest.raises(ValueError, match="Reviewed inputs changed"):
        review.write_plan(prepared, packets.plan_output)
    assert not packets.plan_output.exists()


@pytest.mark.parametrize("output_kind", ["source", "body"])
def test_output_may_not_be_created_inside_either_input_packet(packets, output_kind):
    prepared = prepare(packets)
    root = packets.output if output_kind == "source" else packets.body_output
    target = root / "new-plan"
    with pytest.raises(ValueError, match="Output must not modify input packets"):
        review.write_plan(prepared, target)
    assert not target.exists()
    with pytest.raises(ValueError, match="Output must not modify input packets"):
        review.write_review_template(packets.output, packets.body_output, root / "new-review.json")


def test_existing_plan_or_review_output_is_never_overwritten(packets):
    prepared = prepare(packets)
    packets.plan_output.mkdir()
    marker = packets.plan_output / "keep.txt"
    marker.write_bytes(b"Keep existing work")
    with pytest.raises(ValueError, match="New private output required"):
        review.write_plan(prepared, packets.plan_output)
    with pytest.raises(ValueError, match="New private output required"):
        review.write_review_template(packets.output, packets.body_output, packets.review_file)
    assert marker.read_bytes() == b"Keep existing work"


def test_plan_manifest_binds_every_output_and_original_review_bytes(packets):
    update_review(packets)
    prepared = prepare(packets)
    review.write_plan(prepared, packets.plan_output)
    manifest = read_json(packets.plan_output / "plan_manifest.json")
    assert manifest["complete"] is True and manifest["publication_applied"] is False
    assert manifest["artifacts"] == {
        p.name: review.original.digest(p.read_bytes()) for p in packets.plan_output.iterdir()
        if p.name != "plan_manifest.json"
    }
    assert (packets.plan_output / "review.json").read_bytes() == packets.review_file.read_bytes()
    plan = read_json(packets.plan_output / "update_plan.json")
    row = plan["updates"][0]
    assert row["expected_current"] == prepared.expected_current["current-record"]
    assert row["target_version_id"] == review.original.canonical_digest(row["record_payload"])
    assert row["record_payload"]["annotations"] == []


def test_all_pending_apply_stops_before_settings_database_or_output(packets, monkeypatch):
    prevent_settings_and_db(monkeypatch)
    monkeypatch.setattr(sys, "argv", cli_args(packets, "apply"))
    with pytest.raises(ValueError, match="No adopted updates; database access is not needed"):
        review.main()
    assert not packets.plan_output.exists()


def test_cli_plan_is_offline_and_prints_only_preparation_result(packets, monkeypatch, capsys):
    prevent_settings_and_db(monkeypatch)
    monkeypatch.setattr(sys, "argv", cli_args(packets, "plan"))
    review.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["prepared_updates"] == 0 and summary["publication_applied"] is False
    assert summary["database_writes"] == 0


@pytest.mark.parametrize("command", ["plan", "apply"])
def test_cli_requires_review_file_before_any_work(packets, monkeypatch, command):
    prevent_settings_and_db(monkeypatch)
    monkeypatch.setattr(sys, "argv", cli_args(packets, command, with_review=False))
    with pytest.raises(SystemExit) as caught:
        review.main()
    assert caught.value.code == 2 and not packets.plan_output.exists()


def test_cli_template_rejects_existing_review_argument(packets, monkeypatch):
    prevent_settings_and_db(monkeypatch)
    monkeypatch.setattr(sys, "argv", cli_args(packets, "review-template"))
    with pytest.raises(SystemExit) as caught:
        review.main()
    assert caught.value.code == 2


def test_failed_plan_write_does_not_leave_complete_manifest(packets, monkeypatch):
    prepared = prepare(packets)
    original = Path.write_bytes

    def fail_plan(path, data):
        if path.name == "update_plan.json":
            raise OSError("Synthetic write failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_plan)
    with pytest.raises(OSError, match="Synthetic write failure"):
        review.write_plan(prepared, packets.plan_output)
    assert not (packets.plan_output / "plan_manifest.json").exists()


@pytest.mark.parametrize("mutation", ["body", "annotations", "expected_binding", "target_version", "removed_record"])
def test_prepared_mutable_payload_binding_or_target_drift_rejected_before_plan(packets, mutation):
    update_review(packets)
    prepared = prepare(packets)
    if mutation == "body":
        prepared.batch.records[0].body += " Changed after review"
    elif mutation == "annotations":
        prepared.batch.records[0].annotations.append({"label": "injected"})
    elif mutation == "expected_binding":
        prepared.expected_current["current-record"]["url"] = "https://example.org/wrong-source"
    elif mutation == "target_version":
        prepared.summary["target_versions"]["current-record"] = "0" * 64
    else:
        prepared.batch.records = []
    with pytest.raises(ValueError):
        review.write_plan(prepared, packets.plan_output)
    assert not packets.plan_output.exists()


@pytest.mark.parametrize("shape", [None, [], "not-an-object", 1, True])
def test_invalid_body_manifest_top_level_shape_rejected(packets, shape):
    (packets.body_output / "packet_manifest.json").write_bytes(review.original.encoded(shape))
    with pytest.raises(ValueError):
        review.load_packets(packets.output, packets.body_output)


@pytest.mark.parametrize("shape", [None, [], "not-an-object", 1, True])
def test_invalid_body_manifest_artifact_shape_rejected(packets, shape):
    manifest = read_json(packets.body_output / "packet_manifest.json")
    manifest["artifacts"] = shape
    (packets.body_output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError):
        review.load_packets(packets.output, packets.body_output)


@pytest.mark.parametrize("shape", [None, [], "not-an-object", 1, True])
def test_invalid_review_top_level_shape_rejected(packets, shape):
    packets.review_file.write_bytes(review.original.encoded(shape))
    with pytest.raises(ValueError, match="Invalid body update review"):
        prepare(packets)


def test_explicit_six_source_pending_plan_does_not_invent_history_or_approval(explicit_packets):
    loaded = review.load_packets(explicit_packets.output, explicit_packets.body_output)
    assert set(loaded["source"]["groups"]) == {"124", "125"}
    assert [p["upstream_article_id"] for p in loaded["proposals"]] == ["116", "121", "122", "123", "124", "125"]
    prepared = prepare(explicit_packets)
    assert prepared.batch.records == [] and prepared.expected_current == {}
    assert prepared.summary["decision_counts"] == {"pending": 6}
    decisions = read_json(explicit_packets.review_file)["decisions"]
    assert all(d["reviewer"] is None and d["evidence_refs"] == [] for d in decisions.values())


def test_unsampled_adoption_uses_same_metadata_annotation_and_version_protection(explicit_packets):
    update_review(explicit_packets, evidence_refs=["original/116.txt", "source_workbook.xlsx:Sheet1:2"])
    prepared = prepare(explicit_packets)
    record = prepared.batch.records[0]
    source = review.body_review.load_source_packet(explicit_packets.output)
    old = next(r for r in source["snapshot"]["records"] if r["record_id"] == "current-116")
    assert len(prepared.batch.records) == 1 and record.record_id == "current-116"
    assert record.body == source["sources"]["116"]["text"]
    assert record.title == old["payload"]["title"] and record.sponsor == old["payload"]["sponsor"]
    assert record.annotations == [] and record.retrievable is False
    assert record.raw["previous_body_annotations"] == old["payload"]["annotations"]
    assert record.raw["body_update"]["provided_metadata"]["values"]["title"] == "Supplied title 116"
    assert record.raw["body_update"]["review"]["evidence_refs"] == ["original/116.txt", "source_workbook.xlsx:Sheet1:2"]
    assert "paragraphs" not in record.raw["body_update"]
    assert prepared.expected_current[record.record_id] == {
        "version_id": old["version_id"], "body_sha256": old["body_sha256"],
        "url": old["payload"]["url"], "dataset": "native",
    }
    assert prepared.summary["decision_counts"] == {"adopt": 1, "pending": 5}


@pytest.mark.parametrize("article_ids", [[], None, [116], ["missing"], ["116", "116"],
                                        ["125", "124", "123", "122", "121", "116"]])
def test_rewritten_manifest_invalid_or_noncanonical_scope_rejected(explicit_packets, article_ids):
    path = explicit_packets.body_output / "packet_manifest.json"
    manifest = read_json(path)
    manifest["selected_article_ids"] = article_ids
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="selected_article|selection"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


@pytest.mark.parametrize("field,value", [("source_articles_with_retained_input", 6),
                                        ("source_articles_without_retained_input", 0),
                                        ("source_articles_with_retained_input", True)])
def test_rewritten_manifest_input_counts_must_come_from_frozen_inputs(explicit_packets, field, value):
    path = explicit_packets.body_output / "packet_manifest.json"
    manifest = read_json(path)
    manifest[field] = value
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="selection is not canonical or counts differ"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


@pytest.mark.parametrize("field,value", [("source_articles_with_retained_input", 6),
                                        ("source_articles_without_retained_input", 0),
                                        ("selected_input_paragraphs", 0), ("selected_groups", 50),
                                        ("selected_article_ids", ["116"]),
                                        ("all_retained_in_order_current_groups", 4),
                                        ("all_usable_retained_in_order_current_groups", 4)])
def test_rehashed_selection_summary_cannot_change_scope_or_claim_empty_coverage(explicit_packets, field, value):
    summary = read_json(explicit_packets.body_output / "preparation_summary.json")
    summary[field] = value
    resign_body(explicit_packets, "preparation_summary.json", summary)
    with pytest.raises(ValueError, match="summary differs"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


def test_canonical_scope_change_still_recomputes_each_comparison_and_proposal(explicit_packets):
    selected = ["116", "121", "122", "123", "124"]
    scope = {"selected_article_ids": selected, "source_articles_with_retained_input": 1,
             "source_articles_without_retained_input": 4}
    summary = read_json(explicit_packets.body_output / "preparation_summary.json")
    summary.update(scope, selected_groups=5, selected_input_paragraphs=22)
    resign_body(explicit_packets, "preparation_summary.json", summary)
    path = explicit_packets.body_output / "packet_manifest.json"
    manifest = read_json(path)
    manifest.update(scope)
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="comparisons or proposals differ"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


def test_removing_scope_fields_does_not_turn_explicit_packet_into_legacy_scope(explicit_packets):
    keys = ("selected_article_ids", "source_articles_with_retained_input", "source_articles_without_retained_input")
    summary = read_json(explicit_packets.body_output / "preparation_summary.json")
    for key in keys:
        del summary[key]
    resign_body(explicit_packets, "preparation_summary.json", summary)
    path = explicit_packets.body_output / "packet_manifest.json"
    manifest = read_json(path)
    for key in keys:
        del manifest[key]
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="comparisons or proposals differ"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


def test_scope_changes_in_body_manifest_invalidate_existing_review_binding(explicit_packets):
    path = explicit_packets.body_output / "packet_manifest.json"
    manifest = read_json(path)
    manifest["prepared_scope_note"] = "Even an internally valid change requires a newly bound review"
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="Review scope or packet fingerprints differ"):
        prepare(explicit_packets)


def test_rehashed_unsampled_comparison_cannot_turn_empty_inputs_into_full_coverage(explicit_packets):
    comparisons = read_json(explicit_packets.body_output / "body_comparisons.json")
    assert comparisons[0]["upstream_article_id"] == "116"
    comparisons[0]["current_all_retained_in_order"] = True
    comparisons[0]["current_all_usable_retained_in_order"] = True
    resign_body(explicit_packets, "body_comparisons.json", comparisons)
    with pytest.raises(ValueError, match="comparisons or proposals differ"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


def test_rehashed_unsampled_txt_cannot_substitute_archive_source(explicit_packets):
    path = explicit_packets.body_output / "original/116.txt"
    resign_body(explicit_packets, "original/116.txt", path.read_bytes() + b" Invented new text")
    with pytest.raises(ValueError, match="Candidate TXT differs"):
        review.load_packets(explicit_packets.output, explicit_packets.body_output)


def test_update_loader_rejects_manifest_expansion_to_duplicate_current_target(inputs):
    body_tests.prepare_six_sources(inputs, payload_template=inputs.payload, shared_url=True)
    review.body_review.write_packet(inputs.output, inputs.body_output, article_ids=["124"])
    selected = ["124", "125"]
    scope = {"selected_article_ids": selected, "source_articles_with_retained_input": 2,
             "source_articles_without_retained_input": 0}
    summary = read_json(inputs.body_output / "preparation_summary.json")
    summary.update(scope, selected_groups=2, selected_input_paragraphs=48)
    resign_body(inputs, "preparation_summary.json", summary)
    path = inputs.body_output / "packet_manifest.json"
    manifest = read_json(path)
    manifest.update(scope)
    path.write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="duplicate_selected_target_record"):
        review.load_packets(inputs.output, inputs.body_output)


def test_legacy_packets_without_selection_fields_remain_compatible(packets):
    manifest = read_json(packets.body_output / "packet_manifest.json")
    assert "selected_article_ids" not in manifest
    loaded = review.load_packets(packets.output, packets.body_output)
    assert len(loaded["proposals"]) == 1 and loaded["proposals"][0]["upstream_article_id"] == "0"
    assert prepare(packets).summary["prepared_updates"] == 0
