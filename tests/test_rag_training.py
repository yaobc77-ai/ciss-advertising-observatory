"""Task-split provenance checks; fixtures do not measure semantic accuracy."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from observatory.evaluate import canonical_digest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("rag_training_preparation", SCRIPTS / "prepare_rag_training.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def source(rid, *, sponsor="Alpha", published_at="2020-01-03", active=True, **changes):
    payload = {"record_id": rid, "dataset": "native", "title": "Article " + rid,
               "body": f'中文💡 {rid} background. According to a local researcher, we plan to test the process next year. '
                       'However, this experiment has not produced a confirmed outcome yet. The team explains its current method.',
               "countable": True, "retrievable": True, "sponsor": sponsor,
               "keyword": "Collection term", "publisher": "Example Outlet",
               "url": "https://example.org/" + rid, "archive_url": None,
               "published_at": published_at, "issues": []}
    payload.update(changes)
    return {"record_id": rid, "version_id": canonical_digest(payload), "dataset": "native",
            "body": payload["body"], "active": active, "payload": payload}


def sources():
    return [source("a", sponsor="Alpha", published_at="2019-01-01"),
            source("b", sponsor="Alpha", published_at=None),
            source("c", sponsor="Beta", published_at="2021-01-01"),
            source("d", sponsor="Beta", published_at="2022-01-01"),
            source("held", countable=False, retrievable=False, body=""),
            source("inactive", active=False)]


def questions():
    return {"status": "draft_requires_client_confirmation", "questions": [
        {"question_id": f"Q{i:02d}", "question_exact": f"Client content task {i}: special concept?",
         "query_question": f"Client content task {i}?", "source_ref": f"PD3-P{291+i}",
         "source_paragraph_exact": f"Client content task {i}: special concept?", "candidate_search_terms": []}
        for i in range(1, 25)]}


def variants():
    return {"development_variants": [{"case_id": f"D{i:02d}", "question": f"Seen development concept variant {i}?",
                                      "split": "development", "previously_exposed": True, "human_gold_approved": False}
                                     for i in range(18)]}


def setup(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    definitions = tmp_path / "questions.json"
    previous = tmp_path / "variants.json"
    snapshot.write_bytes(module.encoded({"records": sources(), "observation": {"mode": "fixture"}}))
    definitions.write_bytes(module.encoded(questions()))
    previous.write_bytes(module.encoded(variants()))
    return snapshot, definitions, previous, tmp_path / "out"


def normalized():
    return module.normalize_records(sources())


def candidates():
    records = normalized()
    groups = {r["record_id"]: "G-" + r["record_id"] for r in records}
    return records, module.candidate_cases(records, groups)


def test_client_questions_copied_byte_for_byte_and_roles_are_honest(tmp_path):
    snapshot, questions_path, old, out = setup(tmp_path)
    original = questions_path.read_bytes()
    result = module.prepare(snapshot, questions_path, old, out)
    assert (out / "inputs/client_questions.original.json").read_bytes() == original
    assert questions_path.read_bytes() == original
    tests = json.loads((out / "client_task_test.json").read_text(encoding="utf-8"))
    assert len(tests) == 24
    assert {t["case_id"] for t in tests} == {f"Q{i:02d}" for i in range(1, 25)}
    assert all(t["split"] == "client_task_test" and t["previously_exposed"] is True
               and t["independent_unseen"] is False and not t["permitted_in_prompts_or_training_examples"]
               and not t["human_gold_approved"] for t in tests)
    assert result["client_questions_sha256"] == module.digest(original)
    assert result["summary"]["independent_unseen_test_questions"] == 0
    assert result["fine_tuning_performed"] is False and result["model_calls"] == 0


def test_small_fixture_reports_coverage_gap_without_inventing_examples(tmp_path):
    result = module.prepare(*setup(tmp_path))
    assert not result["coverage_threshold_met"]
    assert not result["coverage_checks"]["candidate_count"]
    assert result["summary"]["human_approved_training_examples"] == 0
    assert result["summary"]["semantic_performance_scores"] is None
    assert result["training_policy"]["runtime_demonstration_insertion"] == "disabled_until_review"


def test_prior_18_variants_stay_development_and_are_not_training(tmp_path):
    _, _, _, out = paths = setup(tmp_path)
    module.prepare(*paths)
    retained = json.loads((out / "development_variants.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in (out / "training_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert retained == variants()["development_variants"]
    assert not {v["question"] for v in retained} & {c["question"] for c in cases}
    assert all(c["split"] == "train_development_candidate" and c["runtime_enabled"] is False for c in cases)


def test_counts_ties_and_dates_independently_match_fixture_members():
    records, cases = candidates()
    by_operation = {}
    for c in cases:
        by_operation.setdefault(c["operation"], []).append(c)
    outlet = by_operation["count_outlet_records"][0]
    assert outlet["reference"]["count"] == 4
    assert {r["record_id"] for r in outlet["source_records"]} == {"a", "b", "c", "d"}
    tied = by_operation["find_all_tied_top_sponsors"][0]
    assert tied["reference"]["sponsors"] == ["Alpha", "Beta"] and tied["reference"]["top_count"] == 2
    alpha_years = next(c for c in by_operation["group_sponsor_records_by_year"] if c["arguments"]["sponsor"] == "Alpha")
    assert alpha_years["reference"]["groups"] == [{"year": "2019", "count": 1}, {"year": "Unknown date", "count": 1}]
    comparison = by_operation["compare_two_calendar_years"][0]
    assert comparison["arguments"]["years"] == ["2021", "2022"]
    assert comparison["reference"]["difference_second_minus_first"] == 0
    module.verify_references(cases, records)


def test_unavailable_body_remains_unknown_not_a_negative_content_label():
    _, cases = candidates()
    unavailable = next(c for c in cases if c["operation"] == "handle_unavailable_retained_text")
    assert unavailable["arguments"]["record_id"] == "held"
    assert unavailable["reference"]["content_state"] == "unknown"
    assert not unavailable["reference"]["body_search_permitted"]
    assert all(c["arguments"].get("record_id") != "inactive" for c in cases)


def test_real_source_offsets_and_semantic_boundaries_never_create_gold():
    records, cases = candidates()
    index = {r["record_id"]: r for r in records}
    spans = [c for c in cases if c["source_span"]]
    assert spans
    assert {"speaker_attribution", "negation_scope", "planned_vs_achieved"} <= {c["task_family"] for c in spans}
    for c in spans:
        span = c["source_span"]
        assert index[c["arguments"]["record_id"]]["body"][span["start"]:span["end"]] == span["quote"]
        if c["reference_status"] == "semantic_draft_requires_review":
            assert c["reference"]["judgment"] is None and c["reference"]["speaker"] is None
            assert c["reference"]["treatment"] is None and not c["human_gold_approved"]


@pytest.mark.parametrize("change", ["quote", "version", "count", "members", "semantic"])
def test_tampered_reference_identity_or_semantic_approval_rejected(change):
    records, cases = candidates()
    cases = deepcopy(cases)
    if change == "quote":
        next(c for c in cases if c["source_span"])["source_span"]["quote"] = "Invented"
    elif change == "version":
        cases[0]["source_records"][0]["version_id"] = "changed"
    elif change == "count":
        next(c for c in cases if c["operation"] == "count_outlet_records")["reference"]["count"] = 900
    elif change == "members":
        next(c for c in cases if c["operation"] == "count_outlet_records")["source_records"].pop()
    else:
        next(c for c in cases if c["reference_status"] == "semantic_draft_requires_review")["reference"]["judgment"] = "positive"
    with pytest.raises(ValueError):
        module.verify_references(cases, records)


@pytest.mark.parametrize("which", ["test", "variant"])
def test_test_question_or_seen_variant_cannot_enter_training_questions(which):
    _, cases = candidates()
    qs = module.validate_questions(questions())
    old = variants()["development_variants"]
    cases[0]["question"] = qs[0]["question_exact"] if which == "test" else old[0]["question"]
    with pytest.raises(ValueError, match="overlaps"):
        module.assert_question_separation(cases, qs, old)


def test_near_copy_groups_limit_repeated_record_examples_without_merging_counts():
    records = normalized()
    groups = {r["record_id"]: "shared" for r in records}
    cases = module.candidate_cases(records, groups)
    assert len([c for c in cases if c["task_family"] == "source_identity"]) == 1
    outlet = next(c for c in cases if c["operation"] == "count_outlet_records")
    assert outlet["reference"]["count"] == 4


def test_existing_even_empty_destination_refused_before_reading_any_input(tmp_path):
    with pytest.raises(ValueError, match="output_already_exists"):
        module.prepare(Path("absent"), Path("absent"), Path("absent"), tmp_path)


def test_hash_bound_manifest_and_original_inputs_are_preserved(tmp_path):
    snapshot, question_path, old, out = setup(tmp_path)
    source_before = snapshot.read_bytes()
    previous_before = old.read_bytes()
    result = module.prepare(snapshot, question_path, old, out)
    for item in result["files"]:
        data = (out / item["path"]).read_bytes()
        assert item["bytes"] == len(data) and item["sha256"] == module.digest(data)
    assert snapshot.read_bytes() == source_before and old.read_bytes() == previous_before
    assert (out / "inputs/source_snapshot.json").read_bytes() == source_before
    assert result["training_policy"]["test_source_overlap"].startswith("Training source groups may overlap")


def test_invalid_body_hash_and_payload_versions_refused_before_output(tmp_path):
    snapshot, qs, old, out = setup(tmp_path)
    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    raw["records"][0]["version_id"] = "not-the-payload-hash"
    snapshot.write_bytes(module.encoded(raw))
    with pytest.raises(ValueError, match="payload_version"):
        module.prepare(snapshot, qs, old, out)
    assert not out.exists()


def test_missing_exposed_variant_status_refused(tmp_path):
    snapshot, qs, old, out = setup(tmp_path)
    raw = variants()
    raw["development_variants"][0]["previously_exposed"] = False
    old.write_bytes(module.encoded(raw))
    with pytest.raises(ValueError, match="18_exposed"):
        module.prepare(snapshot, qs, old, out)
    assert not out.exists()
