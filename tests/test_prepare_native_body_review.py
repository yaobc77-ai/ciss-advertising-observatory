"""Offline, synthetic checks for body proposals; these do not approve content."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import test_prepare_claims_input_review as source_tests

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "prepare_native_body_review_tests",
    Path(__file__).parents[1] / "scripts/prepare_native_body_review.py",
)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    item = source_tests.inputs.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(
        review.original, "UPSTREAM_NOTEBOOK_SHA256",
        review.original.digest(item.notebook.read_bytes()),
    )
    item.body_output = tmp_path / "body-packet"
    return item


def bind_row(payload, *, active=True):
    return {
        "record_id": payload["record_id"], "dataset": payload["dataset"],
        "active": active, "payload": deepcopy(payload), "body": payload["body"],
        "body_sha256": review.original.digest(payload["body"].encode("utf-8")),
        "version_id": review.original.canonical_digest(payload),
    }


def set_current(inputs, *, body=None, retrievable=False, ranges=None, end=None,
                url="https://example.org/original", active=True, dataset="native"):
    payload = source_tests.current_snapshot(url=url, dataset=dataset)["records"][0]["payload"]
    payload.update({
        "body": inputs.raw.decode("utf-8") if body is None else body,
        "retrievable": retrievable,
        "published_at": "2021-04-02",
        "keyword": "Search term is not sponsor",
        "platform": None,
        "account": None,
        "disclosure": "Paid content",
        "archive_url": "https://example.org/archive",
        "annotations": [{"label": "historical", "start": 0, "end": 4}],
        "issues": [],
        "provenance": {"review": "historical-only"},
    })
    if ranges is not None:
        payload["retrieval_ranges"] = ranges
    if end is not None:
        payload["retrieval_end"] = end
    value = {"records": [bind_row(payload, active=active)], "observation": {"synthetic": True}}
    inputs.current_snapshot.write_bytes(review.original.encoded(value))
    return value


def prepare_source(inputs, **current):
    snapshot = set_current(inputs, **current)
    source_tests.prepare(inputs)
    return snapshot


def read_json(root, name):
    return json.loads((root / name).read_bytes())


def resign(root, name, data):
    """Change a frozen artifact and its envelope, to test underlying joins."""
    raw = data if isinstance(data, bytes) else review.original.encoded(data)
    (root / name).write_bytes(raw)
    manifest = read_json(root, "packet_manifest.json")
    manifest["artifacts"][name] = review.original.digest(raw)
    (root / "packet_manifest.json").write_bytes(review.original.encoded(manifest))


def run(inputs, *, article_ids=None):
    summary = review.write_packet(inputs.output, inputs.body_output, article_ids=article_ids)
    return (
        summary, read_json(inputs.body_output, "body_comparisons.json"),
        read_json(inputs.body_output, "pending_body_proposals.json"),
    )


def prepare_six_sources(inputs, *, source_current=False, retrievable=False, payload_template=None, shared_url=False):
    """Synthetic original inventory has six texts but only two sampled groups."""
    article_ids = ["116", "121", "122", "123", "124", "125"]
    settings = review.original.notebook_settings(inputs.notebook.read_bytes())
    sources, metadata, cleaned, selected, rows = {}, [], [], [], []
    for aid in article_ids:
        count = {"124": 22, "125": 26}.get(aid, 2)
        text = (source_tests.PARAGRAPH + "\r\n\r\n") * count + "Footer\r\n"
        sources[f"{aid}.txt"] = text.encode("utf-8")
        url = f"https://example.org/source/{'124' if shared_url and aid == '125' else aid}"
        metadata.append([int(aid), url, "Supplied outlet", f"Supplied title {aid}", "Supplied company", "Synthetic notes", None])
        _, kept = review.original.historical_cleaning(text, settings)
        cleaned.extend([[aid, paragraph] for paragraph in kept])
        if aid in {"124", "125"}:
            first_id = len(selected) + 1
            selected.extend([[str(first_id + index), aid, paragraph] for index, paragraph in enumerate(kept)])
        if shared_url and aid == "125":
            continue
        payload = deepcopy(payload_template or source_tests.current_snapshot()["records"][0]["payload"])
        payload.update(record_id=f"current-{aid}", url=url, title=f"Current title {aid}",
                       body=text if source_current else "video", countable=True, retrievable=retrievable,
                       retrieval_ranges=None, retrieval_end=None)
        if "raw" in payload:
            payload["raw"]["body_sha256"] = review.original.digest(payload["body"].encode("utf-8"))
        rows.append(bind_row(payload))
    inputs.manual_zip.write_bytes(source_tests.source_zip(source_tests.workbook_bytes(metadata), sources))
    inputs.cleaned_csv.write_bytes(source_tests.csv_data(["id", "text"], cleaned))
    inputs.input_csv.write_bytes(source_tests.csv_data(["id", "article_id", "text"], selected))
    inputs.current_snapshot.write_bytes(review.original.encoded({"records": rows, "observation": {"synthetic": True}}))
    source_tests.prepare(inputs)
    return article_ids


def test_valid_frozen_packet_preserves_bytes_metadata_and_previous_payload(inputs):
    snapshot = prepare_source(inputs)
    loaded = review.load_source_packet(inputs.output)
    assert loaded["snapshot"] == snapshot
    assert loaded["sources"]["0"]["bytes"] == inputs.raw
    summary, comparisons, proposals = run(inputs)
    current = snapshot["records"][0]
    comparison, proposal = comparisons[0], proposals[0]
    assert comparison["current_record"] == current
    assert comparison["current_match_status"] == "unique_exact_url"
    assert proposal["previous_payload"] == current["payload"]
    assert proposal["target_binding"] == {
        "record_id": current["record_id"], "url": current["payload"]["url"],
        "expected_current_version_id": current["version_id"],
        "expected_current_body_sha256": current["body_sha256"],
    }
    assert proposal["candidate_text"]["body"].encode("utf-8") == inputs.raw
    assert proposal["candidate_text"]["body_sha256"] == review.original.digest(inputs.raw)
    assert (inputs.body_output / "original/0.txt").read_bytes() == inputs.raw
    assert (inputs.body_output / "current/0.txt").read_bytes() == inputs.raw
    assert proposal["provided_metadata"]["values"]["publisher"] == "Original Outlet"
    assert proposal["retained_metadata"]["publisher"] == "Current outlet"
    assert proposal["retained_metadata"]["disclosure"] == "Paid content"
    assert proposal["retained_metadata"]["archive_url"] == "https://example.org/archive"
    assert proposal["retained_metadata"]["keyword"] == "Search term is not sponsor"
    assert {row["field"] for row in comparison["metadata_differences"]} == {
        "publisher", "title", "sponsor",
    }
    assert all(row["resolution"] == "pending_no_metadata_override"
               for row in comparison["metadata_differences"])
    assert summary["source_snapshot_scope"] == "supplied_frozen_file_not_live_database"


def test_full_matching_never_inherits_annotations_or_retrieval_approval(inputs):
    prepare_source(inputs, retrievable=True, ranges=[[0, len(inputs.raw.decode("utf-8"))]])
    summary, comparisons, proposals = run(inputs)
    proposal = proposals[0]
    assert comparisons[0]["current_all_retained_in_order"] is True
    assert comparisons[0]["current_all_usable_retained_in_order"] is True
    assert summary["all_usable_retained_in_order_current_groups"] == 1
    assert summary["all_usable_retained_in_order_current_paragraphs"] == 2
    assert proposal["candidate_text"]["annotations"] == []
    assert proposal["previous_payload"]["annotations"] == [
        {"label": "historical", "start": 0, "end": 4},
    ]
    assert proposal["candidate_text"]["retrievable"] is False
    assert proposal["candidate_text"]["retrieval_ranges"] is None
    assert proposal["candidate_text"]["retrieval_end"] is None
    assert proposal["importable"] is False
    assert proposal["review"] == {
        "source_identity": "pending", "body_content": "pending",
        "original_page_completeness": "unknown", "retrieval": "pending",
        "publication": "hold", "reviewer": None, "reviewed_at": None, "decision": None,
    }
    assert comparisons[0]["source_identity"] == "pending"
    assert comparisons[0]["original_page_completeness"] == "unknown"
    assert summary["source_associations_approved"] == summary["classification_results_published"] == 0
    assert summary["semantic_quality_scores"] is None and summary["reviewer"] is None
    assert summary["model_calls"] == summary["network_calls"] == summary["database_writes"] == 0
    assert summary["corpus_updates"] == 0
    assert not list(inputs.body_output.rglob("*.jsonl"))


def test_all_repeated_occurrences_have_original_offsets_and_separate_eligibility(inputs):
    text = inputs.raw.decode("utf-8")
    first_end = len(source_tests.PARAGRAPH)
    prepare_source(inputs, retrievable=False, ranges=[[0, first_end]])
    summary, comparisons, _ = run(inputs)
    rows = comparisons[0]["current_locations"]
    assert summary["paragraphs_located_current"] == 2
    assert summary["paragraphs_located_current_strict"] == 0
    assert summary["paragraphs_located_in_retrievable_records"] == 0
    assert summary["paragraphs_with_usable_current_location"] == 0
    assert comparisons[0]["current_all_retained_in_order"] is True
    assert comparisons[0]["current_all_usable_retained_in_order"] is False
    for row in rows:
        assert len(row["locations"]) == 2
        a, b = row["locations"]
        assert a["start"] == 0 and b["start"] > a["end"]
        assert a["inside_declared_retrieval_range"] is True
        assert b["inside_declared_retrieval_range"] is False
        assert a["usable_under_current_retrieval"] is b["usable_under_current_retrieval"] is False
        assert all(span["lossy"] for span in row["locations"])
        assert all(text[span["start"]:span["end"]] == span["quote"] for span in row["locations"])


def test_located_text_outside_declared_range_is_not_retrieval_evidence(inputs):
    text = inputs.raw.decode("utf-8")
    start = text.index("Footer")
    prepare_source(inputs, retrievable=True, ranges=[[start, len(text)]])
    summary, comparisons, _ = run(inputs)
    assert summary["paragraphs_located_in_retrievable_records"] == 2
    assert summary["paragraphs_located_only_outside_declared_ranges"] == 2
    assert summary["paragraphs_with_usable_current_location"] == 0
    assert comparisons[0]["current_all_usable_retained_in_order"] is False
    assert summary["all_usable_retained_in_order_current_groups"] == 0
    assert all(not span["inside_declared_retrieval_range"]
               for row in comparisons[0]["current_locations"] for span in row["locations"])


def test_single_occurrence_does_not_satisfy_two_distinct_retained_paragraphs(inputs):
    prepare_source(inputs, body=source_tests.PARAGRAPH, retrievable=True)
    summary, comparisons, _ = run(inputs)
    assert all(len(row["locations"]) == 1 for row in comparisons[0]["current_locations"])
    assert comparisons[0]["current_all_retained_in_order"] is False
    assert comparisons[0]["current_all_usable_retained_in_order"] is False
    assert summary["all_retained_in_order_current_groups"] == 0
    assert summary["paragraphs_located_current"] == 2
    assert summary["paragraphs_unlocated_current"] == 0


def test_unlocated_text_remains_unknown_not_negative_or_complete(inputs):
    prepare_source(inputs, body="video")
    summary, comparisons, proposals = run(inputs)
    comparison = comparisons[0]
    assert summary["paragraphs_unlocated_current"] == 2
    assert summary["current_video_placeholder_groups"] == 1
    assert comparison["unlocated_current_input_ids"] == ["1", "2"]
    assert comparison["review_priority"] == 0
    assert "current_video_placeholder" in comparison["review_flags"]
    assert "does not prove" in comparison["interpretation"]
    assert comparison["original_page_completeness"] == "unknown"
    assert proposals[0]["candidate_text"]["annotations"] == []
    assert proposals[0]["review"]["body_content"] == "pending"
    assert "不是标签阴性" in (inputs.body_output / "articles/0.md").read_text(encoding="utf-8")


def test_stored_truncation_flag_kept_as_signal_without_claiming_missing_content(inputs):
    snapshot = set_current(inputs)
    payload = snapshot["records"][0]["payload"]
    payload["issues"] = [{"code": "body_truncated_suspected", "detail": "Historical signal"}]
    snapshot["records"] = [bind_row(payload)]
    inputs.current_snapshot.write_bytes(review.original.encoded(snapshot))
    source_tests.prepare(inputs)
    summary, comparisons, _ = run(inputs)
    assert summary["current_truncation_flag_groups"] == 1
    assert comparisons[0]["review_priority"] == 1
    assert comparisons[0]["quality_signals"]["current_stored"] == payload["issues"]
    assert comparisons[0]["original_page_completeness"] == "unknown"


@pytest.mark.parametrize("change", [{"url": "https://example.org/different"},
                                     {"active": False}, {"dataset": "social"}])
def test_no_active_same_url_native_record_produces_no_replacement(inputs, change):
    prepare_source(inputs, **change)
    summary, comparisons, proposals = run(inputs)
    assert proposals == []
    assert summary["unique_current_url_groups"] == summary["pending_body_proposals"] == 0
    assert summary["paragraphs_without_unique_current_source"] == 2
    assert summary["paragraphs_unlocated_current"] == 0
    assert comparisons[0]["current_match_status"] == "no_current_url"
    assert comparisons[0]["current_record"] is None
    assert comparisons[0]["current_all_retained_in_order"] is None
    assert comparisons[0]["current_all_usable_retained_in_order"] is None
    assert comparisons[0]["source_identity"] == "pending"
    detail = (inputs.body_output / "articles/0.md").read_text(encoding="utf-8")
    assert "未比较：无唯一当前 URL" in detail


def test_two_active_records_with_same_url_remain_ambiguous_not_first_match(inputs):
    snapshot = set_current(inputs)
    second = deepcopy(snapshot["records"][0]["payload"])
    second.update(record_id="second-current", body="Another saved version.", publisher="Another publisher")
    snapshot["records"].append(bind_row(second))
    inputs.current_snapshot.write_bytes(review.original.encoded(snapshot))
    source_tests.prepare(inputs)
    summary, comparisons, proposals = run(inputs)
    assert proposals == [] and summary["unique_current_url_groups"] == 0
    assert comparisons[0]["current_match_status"] == "ambiguous_current_url"
    assert {r["record_id"] for r in comparisons[0]["current_url_candidates"]} == {
        "current-record", "second-current",
    }
    assert comparisons[0]["current_record"] is None
    assert comparisons[0]["current_all_usable_retained_in_order"] is None
    assert summary["paragraphs_unlocated_current"] == 0


def test_manifest_covers_written_artifacts_and_input_manifest_binding(inputs):
    prepare_source(inputs)
    summary, _, proposals = run(inputs)
    manifest = read_json(inputs.body_output, "packet_manifest.json")
    actual = {
        p.relative_to(inputs.body_output).as_posix(): review.original.digest(p.read_bytes())
        for p in inputs.body_output.rglob("*") if p.is_file() and p.name != "packet_manifest.json"
    }
    assert manifest["artifacts"] == actual
    assert manifest["complete"] is True
    assert manifest["importable"] is manifest["source_associations_approved"] is manifest["labels_published"] is False
    original_manifest = (inputs.output / "packet_manifest.json").read_bytes()
    assert (inputs.body_output / "inputs/source_packet_manifest.json").read_bytes() == original_manifest
    assert summary["source_packet_manifest_sha256"] == review.original.digest(original_manifest)
    assert proposals[0]["source_binding"]["source_packet_manifest_sha256"] == summary["source_packet_manifest_sha256"]
    assert proposals[0]["source_binding"]["source_text_sha256"] == review.original.digest(inputs.raw)


@pytest.mark.parametrize("name", list(review.ESSENTIAL_INPUTS) + ["original/0.txt", "articles/0.md"])
def test_any_manifest_artifact_tampering_rejected(inputs, name):
    prepare_source(inputs)
    target = inputs.output / name
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source_packet_artifact_changed"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:/outside.txt",
                                  "original\\0.txt", "original//0.txt", "./original/0.txt",
                                  "original/../0.txt"])
def test_manifest_path_escape_and_noncanonical_paths_rejected(inputs, name):
    prepare_source(inputs)
    manifest = read_json(inputs.output, "packet_manifest.json")
    manifest["artifacts"][name] = "0" * 64
    (inputs.output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="unsafe_packet_artifact_path"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("field,value", [("complete", False), ("source_associations_approved", True),
                                        ("labels_published", True), ("schema_version", "untrusted")])
def test_completed_pending_source_envelope_required(inputs, field, value):
    prepare_source(inputs)
    manifest = read_json(inputs.output, "packet_manifest.json")
    manifest[field] = value
    (inputs.output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="complete_pending_source_packet_required"):
        review.load_source_packet(inputs.output)


def test_missing_essential_artifact_and_bad_fingerprint_rejected(inputs):
    prepare_source(inputs)
    manifest = read_json(inputs.output, "packet_manifest.json")
    original = deepcopy(manifest)
    del manifest["artifacts"]["source_workbook.xlsx"]
    (inputs.output / "packet_manifest.json").write_bytes(review.original.encoded(manifest))
    with pytest.raises(ValueError, match="complete_source_packet_artifacts_required"):
        review.load_source_packet(inputs.output)
    original["artifacts"]["source_workbook.xlsx"] = "NOT-A-HASH"
    (inputs.output / "packet_manifest.json").write_bytes(review.original.encoded(original))
    with pytest.raises(ValueError, match="invalid_packet_artifact_sha256"):
        review.load_source_packet(inputs.output)


def test_duplicate_manifest_json_keys_are_not_last_value_wins(inputs):
    prepare_source(inputs)
    manifest = (inputs.output / "packet_manifest.json").read_bytes()
    (inputs.output / "packet_manifest.json").write_bytes(b'{"complete":true,' + manifest[1:])
    with pytest.raises(ValueError, match="(?i)duplicate"):
        review.load_source_packet(inputs.output)


def test_rehashed_original_text_cannot_disagree_with_source_zip(inputs):
    prepare_source(inputs)
    resign(inputs.output, "original/0.txt", inputs.raw + b"Extra content")
    with pytest.raises(ValueError, match="original_text_differs_from_source_archive"):
        review.load_source_packet(inputs.output)


def test_rehashed_workbook_cannot_disagree_with_source_zip(inputs):
    prepare_source(inputs)
    rows = source_tests.metadata_rows()
    rows[0][2] = "Substituted source publisher"
    resign(inputs.output, "source_workbook.xlsx", source_tests.workbook_bytes(rows))
    with pytest.raises(ValueError, match="workbook_differs_from_source_archive"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("name", ["source_inventory.json", "article_lineage.json"])
def test_duplicate_article_id_rows_rejected_after_resigning(inputs, name):
    prepare_source(inputs)
    rows = read_json(inputs.output, name)
    rows.append(deepcopy(rows[0]))
    resign(inputs.output, name, rows)
    with pytest.raises(ValueError, match="unique_packet_row_ids_required"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("field,value", [("member", "New/articletexts/1.txt"),
                                         ("raw_bytes_sha256", "0" * 64),
                                         ("historical_kept_paragraphs", 99)])
def test_inventory_recipe_binding_rejected_after_resigning(inputs, field, value):
    prepare_source(inputs)
    rows = read_json(inputs.output, "source_inventory.json")
    rows[0][field] = value
    resign(inputs.output, "source_inventory.json", rows)
    with pytest.raises(ValueError, match="inventory_differs_from_frozen_source_recipe"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("mutation", ["text", "start", "quote", "csv_row", "input_id", "order"])
def test_lineage_input_text_identity_and_positions_rechecked(inputs, mutation):
    prepare_source(inputs)
    rows = read_json(inputs.output, "article_lineage.json")
    group = rows[0]
    if mutation == "order":
        group["all_retained_paragraphs_in_order"] = False
    elif mutation in {"start", "quote"}:
        group["paragraphs"][0]["locations"][0][mutation] = 1 if mutation == "start" else "Fabricated"
    else:
        field = "input_text" if mutation == "text" else mutation
        group["paragraphs"][0][field] = "Changed" if mutation != "csv_row" else 999
    resign(inputs.output, "article_lineage.json", rows)
    with pytest.raises(ValueError, match="lineage_paragraphs_or_positions_differ"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("field,value", [("url_identity_review", "approved"),
                                         ("source_association_approved", True),
                                         ("publication_status", "published"),
                                         ("classification_semantic_review", "approved"),
                                         ("original_page_completeness", "complete"),
                                         ("input_is_complete_original_article", True)])
def test_rehashed_lineage_cannot_silently_promote_source_review(inputs, field, value):
    prepare_source(inputs)
    rows = read_json(inputs.output, "article_lineage.json")
    rows[0][field] = value
    resign(inputs.output, "article_lineage.json", rows)
    with pytest.raises(ValueError, match="pending_source_decisions_required"):
        review.load_source_packet(inputs.output)


def test_rehashed_selected_csv_cannot_disagree_with_frozen_cleaned_sequence(inputs):
    prepare_source(inputs)
    changed = source_tests.csv_data(["id", "article_id", "text"], [
        ["1", "0", inputs.canonical + " additional words"], ["2", "0", inputs.canonical],
    ])
    resign(inputs.output, "input_paragraphs.csv", changed)
    with pytest.raises(ValueError):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("mutation", ["body", "hash", "version", "payload", "duplicate"])
def test_snapshot_body_payload_version_and_record_identity_rechecked(inputs, mutation):
    prepare_source(inputs)
    snapshot = read_json(inputs.output, "current_source_snapshot.json")
    row = snapshot["records"][0]
    if mutation == "duplicate":
        snapshot["records"].append(deepcopy(row))
    elif mutation == "body":
        row["body"] += " Tampered"
    elif mutation == "hash":
        row["body_sha256"] = "0" * 64
    elif mutation == "version":
        row["version_id"] = "0" * 64
    else:
        row["payload"]["publisher"] = "Tampered publisher"
    resign(inputs.output, "current_source_snapshot.json", snapshot)
    with pytest.raises(ValueError):
        review.load_source_packet(inputs.output)


def test_new_valid_current_version_requires_new_lineage_candidate_binding(inputs):
    prepare_source(inputs)
    snapshot = read_json(inputs.output, "current_source_snapshot.json")
    payload = snapshot["records"][0]["payload"]
    payload.update(body="New valid version that has not been bound to the old lineage.", publisher="New publisher")
    snapshot["records"] = [bind_row(payload)]
    resign(inputs.output, "current_source_snapshot.json", snapshot)
    with pytest.raises(ValueError, match="lineage_current_url_candidates_differ"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("ranges", [[[1, 0]], [[0, 999999]], [[0, 5], [4, 6]],
                                    [[True, 3]], [], [[0, "5"]]])
def test_invalid_current_retrieval_ranges_rejected_before_proposals(inputs, ranges):
    # The first packager intentionally only records current source identity;
    # this body-review step must validate the character ranges themselves.
    prepare_source(inputs, ranges=ranges)
    with pytest.raises((ValueError, TypeError)):
        review.write_packet(inputs.output, inputs.body_output)
    assert not inputs.body_output.exists()


@pytest.mark.parametrize("field,value", [("retrieval_ranges", [[0, 1]]),
                                        ("payload_sha256", "0" * 64)])
def test_snapshot_convenience_fields_must_match_payload(inputs, field, value):
    prepare_source(inputs)
    snapshot = read_json(inputs.output, "current_source_snapshot.json")
    snapshot["records"][0][field] = value
    resign(inputs.output, "current_source_snapshot.json", snapshot)
    with pytest.raises(ValueError, match="snapshot_convenience_fields_differ"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("field,value", [("retrievable", 1), ("countable", None)])
def test_explicit_boolean_eligibility_required_not_truthy_coercion(inputs, field, value):
    prepare_source(inputs)
    snapshot = read_json(inputs.output, "current_source_snapshot.json")
    payload = snapshot["records"][0]["payload"]
    payload[field] = value
    snapshot["records"] = [bind_row(payload)]
    resign(inputs.output, "current_source_snapshot.json", snapshot)
    with pytest.raises(ValueError, match="explicit_current_eligibility_required"):
        review.load_source_packet(inputs.output)


def test_existing_output_rejected_before_reading_and_never_overwritten(inputs, monkeypatch):
    inputs.body_output.mkdir()
    marker = inputs.body_output / "keep.txt"
    marker.write_bytes(b"Existing work")
    monkeypatch.setattr(review, "load_source_packet", lambda _: pytest.fail("must reject first"))
    with pytest.raises(ValueError, match="new_private_output_directory_required"):
        review.write_packet(inputs.output, inputs.body_output)
    assert marker.read_bytes() == b"Existing work"
    assert not (inputs.body_output / "packet_manifest.json").exists()


def test_output_inside_source_packet_rejected_before_source_reads(inputs, monkeypatch):
    prepare_source(inputs)
    destination = inputs.output / "nested-body-review"
    before = (inputs.output / "packet_manifest.json").read_bytes()
    monkeypatch.setattr(review, "load_source_packet", lambda _: pytest.fail("must reject first"))
    with pytest.raises(ValueError, match="output_must_not_modify_source_packet"):
        review.write_packet(inputs.output, destination)
    assert not destination.exists()
    assert (inputs.output / "packet_manifest.json").read_bytes() == before


@pytest.mark.parametrize("field", ["source_file_sha256", "cleaning_settings", "projection_contract",
                                  "workbook_sha256", "source_articles", "metadata_records",
                                  "selected_article_groups", "selected_input_paragraphs"])
def test_preparation_recipe_summary_binds_to_underlying_frozen_files(inputs, field):
    prepare_source(inputs)
    summary = read_json(inputs.output, "preparation_summary.json")
    summary[field] = "Tampered yet rehashed summary"
    resign(inputs.output, "preparation_summary.json", summary)
    with pytest.raises(ValueError, match="preparation_summary_differs_from_frozen_inputs"):
        review.load_source_packet(inputs.output)


@pytest.mark.parametrize("joiner,method", [(" ", "exact"), ("\n", "whitespace_normalized")])
def test_strict_match_counts_distinguish_whitespace_from_fixed_ascii_projection(inputs, joiner, method):
    body = joiner.join(inputs.canonical.split())
    prepare_source(inputs, body=body + "\n\n" + body, retrievable=True)
    summary, comparisons, _ = run(inputs)
    assert summary["paragraphs_located_current_strict"] == 2
    assert summary["paragraphs_located_current"] == 2
    assert all(span["match_method"] == method and span["lossy"] is False
               for row in comparisons[0]["current_locations"] for span in row["locations"])


def test_title_apostrophe_readable_and_untrusted_markup_remains_escaped(inputs):
    snapshot = set_current(inputs)
    payload = snapshot["records"][0]["payload"]
    payload["title"] = "Bird's title <script>alert(1)</script> ![image](https://example.org/pixel)"
    snapshot["records"] = [bind_row(payload)]
    inputs.current_snapshot.write_bytes(review.original.encoded(snapshot))
    source_tests.prepare(inputs)
    run(inputs)
    text = (inputs.body_output / "articles/0.md").read_text(encoding="utf-8")
    table_line = next(line for line in text.splitlines() if line.startswith("| title |"))
    assert "Bird's title" in table_line
    assert "&#x27;" not in table_line
    assert "<script>" not in table_line
    assert "&lt;script&gt;" in table_line
    assert "![image](" not in table_line


def test_one_usable_repeated_location_does_not_make_full_usable_sequence(inputs):
    prepare_source(inputs, retrievable=True, ranges=[[0, len(source_tests.PARAGRAPH)]])
    summary, comparisons, _ = run(inputs)
    assert comparisons[0]["current_all_retained_in_order"] is True
    assert comparisons[0]["current_all_usable_retained_in_order"] is False
    assert summary["paragraphs_with_usable_current_location"] == 2
    assert summary["all_usable_retained_in_order_current_groups"] == 0
    assert summary["all_usable_retained_in_order_current_paragraphs"] == 0


def test_later_repeated_locations_can_form_complete_usable_ordered_sequence(inputs):
    paragraph = source_tests.PARAGRAPH
    body = "\r\n\r\n".join([paragraph] * 3)
    prepare_source(inputs, body=body, retrievable=True, ranges=[[len(paragraph) + 4, len(body)]])
    summary, comparisons, _ = run(inputs)
    assert comparisons[0]["current_all_retained_in_order"] is True
    assert comparisons[0]["current_all_usable_retained_in_order"] is True
    assert summary["all_usable_retained_in_order_current_groups"] == 1
    assert summary["all_usable_retained_in_order_current_paragraphs"] == 2
    for row in comparisons[0]["current_locations"]:
        assert [span["usable_under_current_retrieval"] for span in row["locations"]] == [False, True, True]


def test_formula_url_preserved_as_source_assertion_without_correspondence_or_execution(inputs):
    rows = source_tests.metadata_rows()
    formula = '=HYPERLINK("https://example.org/original","Open")'
    rows[0][1] = formula
    inputs.manual_zip.write_bytes(source_tests.source_zip(
        source_tests.workbook_bytes(rows), {
            "0.txt": inputs.raw, "1.txt": (source_tests.OTHER + "\r\n").encode("utf-8"),
        },
    ))
    prepare_source(inputs)
    summary, comparisons, proposals = run(inputs)
    assert proposals == [] and summary["pending_body_proposals"] == 0
    assert comparisons[0]["provided_metadata"]["formula_fields"] == ["url"]
    assert comparisons[0]["provided_metadata"]["values"]["url"] == formula
    assert comparisons[0]["current_match_status"] == "no_current_url"


def test_source_notebook_cells_not_executed_when_rechecking_recipe(inputs, monkeypatch):
    marker = inputs.body_output.parent / "upstream-executed.txt"
    notebook = json.loads(inputs.notebook.read_bytes())
    notebook["cells"][0]["source"].extend([
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        "raise RuntimeError('must not execute upstream')\n",
    ])
    data = review.original.encoded(notebook)
    inputs.notebook.write_bytes(data)
    fingerprint = review.original.digest(data)
    monkeypatch.setattr(source_tests.review, "UPSTREAM_NOTEBOOK_SHA256", fingerprint)
    monkeypatch.setattr(review.original, "UPSTREAM_NOTEBOOK_SHA256", fingerprint)
    prepare_source(inputs)
    summary, _, _ = run(inputs)
    assert not marker.exists()
    assert (inputs.body_output / "inputs/cleaning_notebook.ipynb").read_bytes() == data
    assert summary["model_calls"] == summary["network_calls"] == summary["database_writes"] == 0


def test_source_changes_during_preparation_rejected_without_completed_output(inputs, monkeypatch):
    prepare_source(inputs)
    actual = review.article_markdown

    def change_source(*args):
        result = actual(*args)
        path = inputs.output / "original/0.txt"
        path.write_bytes(path.read_bytes() + b" Drifting source")
        return result

    monkeypatch.setattr(review, "article_markdown", change_source)
    with pytest.raises(ValueError, match="source_packet_changed_during_preparation"):
        review.write_packet(inputs.output, inputs.body_output)
    assert not inputs.body_output.exists()


def test_failed_output_write_does_not_leave_completed_manifest(inputs, monkeypatch):
    prepare_source(inputs)
    actual = Path.write_bytes

    def fail_proposals(path, data):
        if path.name == "pending_body_proposals.json":
            raise OSError("synthetic disk failure")
        return actual(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_proposals)
    with pytest.raises(OSError, match="synthetic disk failure"):
        review.write_packet(inputs.output, inputs.body_output)
    assert not (inputs.body_output / "packet_manifest.json").exists()


def test_explicit_six_sources_preserve_sample_scope_and_report_no_input_as_not_applicable(inputs):
    article_ids = prepare_six_sources(inputs)
    summary, comparisons, proposals = run(inputs, article_ids=list(reversed(article_ids)))
    loaded = review.load_source_packet(inputs.output)
    assert set(loaded["groups"]) == {"124", "125"}
    assert set(loaded["inventory"]) == set(article_ids)
    assert summary["selected_article_ids"] == article_ids
    assert summary["selected_groups"] == 6 and summary["selected_input_paragraphs"] == 48
    assert summary["source_articles_with_retained_input"] == 2
    assert summary["source_articles_without_retained_input"] == 4
    assert summary["pending_body_proposals"] == 6
    assert summary["paragraphs_unlocated_current"] == 48
    manifest = read_json(inputs.body_output, "packet_manifest.json")
    assert all(manifest[key] == summary[key] for key in review.selection_fields(loaded, article_ids))
    by_id = {row["upstream_article_id"]: row for row in comparisons}
    for aid in article_ids[:4]:
        comparison = by_id[aid]
        assert comparison["retained_input_coverage_status"] == "not_applicable_no_retained_input"
        assert comparison["current_all_retained_in_order"] is None
        assert comparison["current_all_usable_retained_in_order"] is None
        assert comparison["original_locations"] == comparison["current_locations"] == []
        assert comparison["supplied_paragraphs"] == 0 and comparison["unlocated_current_input_ids"] == []
        detail = (inputs.body_output / f"articles/{aid}.md").read_text(encoding="utf-8")
        assert "没有历史 CLAIMS 保留输入" in detail and "0/0" not in detail
        assert "### 输入 " not in detail and "完整有序序列：True" not in detail
    assert "retained_input_coverage_status" not in by_id["124"]
    assert all(p["candidate_text"]["annotations"] == [] and p["review"]["publication"] == "hold" for p in proposals)
    assert all(p["provided_metadata"]["values"]["title"].startswith("Supplied") for p in proposals)
    assert all(p["retained_metadata"]["title"].startswith("Current") for p in proposals)


def test_empty_sample_does_not_inflate_ordered_or_retrievable_coverage(inputs):
    article_ids = prepare_six_sources(inputs, source_current=True, retrievable=True)
    summary, comparisons, _ = run(inputs, article_ids=article_ids)
    assert summary["all_retained_in_order_current_groups"] == 2
    assert summary["all_retained_in_order_retrievable_groups"] == 2
    assert summary["all_usable_retained_in_order_current_groups"] == 2
    assert summary["all_retained_in_order_retrievable_paragraphs"] == 48
    assert summary["all_usable_retained_in_order_current_paragraphs"] == 48
    assert summary["paragraphs_located_current"] == 48
    assert all(c["current_all_usable_retained_in_order"] is None for c in comparisons[:4])
    assert all(c["review_priority"] == 6 for c in comparisons[:4])


def test_unsampled_only_selection_has_no_coverage_or_fabricated_history(inputs):
    prepare_six_sources(inputs, source_current=True, retrievable=True)
    summary, comparisons, proposals = run(inputs, article_ids=["116"])
    assert summary["selected_input_paragraphs"] == 0 and summary["pending_body_proposals"] == 1
    assert summary["source_articles_with_retained_input"] == 0
    assert summary["source_articles_without_retained_input"] == 1
    assert summary["all_retained_in_order_current_groups"] == 0
    assert summary["all_usable_retained_in_order_current_groups"] == 0
    assert comparisons[0]["original_locations"] == []
    assert proposals[0]["candidate_text"]["annotations"] == []
    assert "不适用（无历史输入）" in (inputs.body_output / "index.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("article_ids, error", [
    ([], "must_name_verified"), (["missing"], "must_name_verified"),
    ([116], "must_name_verified"), ([None], "must_name_verified"),
    (["0116"], "must_name_verified"), ("116", "must_name_verified"),
    (["116", "116"], "duplicate_selected_article_id"),
])
def test_invalid_or_duplicate_explicit_source_ids_fail_before_output(inputs, article_ids, error):
    prepare_six_sources(inputs)
    with pytest.raises(ValueError, match=error):
        run(inputs, article_ids=article_ids)
    assert not inputs.body_output.exists()


def test_two_sources_for_one_current_record_do_not_create_competing_updates(inputs):
    article_ids = prepare_six_sources(inputs, shared_url=True)
    with pytest.raises(ValueError, match="duplicate_selected_target_record"):
        run(inputs, article_ids=article_ids)
    assert not inputs.body_output.exists()


def test_default_selection_remains_sampled_only_without_new_scope_or_row_fields(inputs):
    prepare_six_sources(inputs)
    summary, comparisons, proposals = run(inputs)
    manifest = read_json(inputs.body_output, "packet_manifest.json")
    assert summary["selected_groups"] == 2 and summary["selected_input_paragraphs"] == 48
    assert [c["upstream_article_id"] for c in comparisons] == ["124", "125"]
    assert len(proposals) == 2
    assert "selected_article_ids" not in manifest and "selected_article_ids" not in summary
    assert all("retained_input_coverage_status" not in c for c in comparisons)


def test_cli_explicit_ids_uses_offline_verified_inventory(inputs, monkeypatch, capsys):
    article_ids = prepare_six_sources(inputs)
    monkeypatch.setattr(sys, "argv", ["prepare_native_body_review.py", "--source-packet", str(inputs.output),
                                     "--output", str(inputs.body_output), "--article-ids", *reversed(article_ids)])
    review.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["selected_article_ids"] == article_ids and summary["selected_input_paragraphs"] == 48
    assert summary["model_calls"] == summary["network_calls"] == summary["database_writes"] == 0
