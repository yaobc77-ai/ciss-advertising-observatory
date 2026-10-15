"""Reference/scoring integrity tests. Synthetic predictions are not quality scores."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import evaluate_teacher_reference as score  # noqa: E402
import prepare_teacher_reference as prepare  # noqa: E402
from test_rag_training import candidates, sources  # noqa: E402


def annotations_for(cases):
    result = {}
    for case in cases:
        if case["task_family"] not in prepare.FAMILIES:
            continue
        labels = {key: options[0] for key, options in prepare.FAMILIES[case["task_family"]]["labels"].items()}
        result[case["case_id"]] = {
            "case_id": case["case_id"], "status": "resolved", "labels": labels,
            "speaker_names": [], "answer_zh": "仅用于工程检查的合成判断，不是标准答案。",
            "rationale_zh": "合成夹具检验文件和评分边界。", "limitations": ["不是实际语义成绩。"],
            "evidence_intervals": [{"start": case["source_span"]["start"], "end": case["source_span"]["end"],
                                    "reason_zh": "测试精确原文定位。"}],
        }
    return result


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def prepared(tmp_path):
    records, cases = candidates()
    annotations = annotations_for(cases)
    snapshot, seeds, teacher_root, out = (tmp_path / "snapshot.json", tmp_path / "seeds.jsonl",
                                         tmp_path / "teacher", tmp_path / "prepared")
    snapshot.write_bytes(prepare.encoded({"records": sources()}))
    write_lines(seeds, cases)
    indexed = {row["record_id"]: row for row in records}
    for family, config in prepare.FAMILIES.items():
        selected = [case for case in cases if case["task_family"] == family]
        inputs = [{"case_id": c["case_id"], "question": c["question"], "task_family": family,
                   "focal_span": c["source_span"], "source": c["source_records"][0],
                   "full_saved_body": indexed[c["arguments"]["record_id"]]["body"],
                   "retrieval_ranges": indexed[c["arguments"]["record_id"]]["retrieval_ranges"]} for c in selected]
        inp = teacher_root / "root/inputs" / f"{family}.jsonl"
        refs = teacher_root / config["directory"] / "references.jsonl"
        write_lines(inp, inputs)
        write_lines(refs, [annotations[c["case_id"]] for c in selected])
        receipt = {"model": "gpt-6.1-sol", "human_approved": False,
                   "input_sha256": prepare.digest(inp.read_bytes()), "references_sha256": prepare.digest(refs.read_bytes()),
                   "full_context_read_case_ids": [c["case_id"] for c in selected]}
        (refs.parent / "receipt.json").write_bytes(prepare.encoded(receipt))
    return seeds, snapshot, teacher_root, out


def compiled():
    records, cases = candidates()
    return records, prepare.compile_references(cases, records, annotations_for(cases))


def prediction(case, status="answered", evidence=None):
    return {"case_id": case["case_id"], "status": status,
            "fields": deepcopy(case["expected_fields"]) if status == "answered" else None,
            "evidence": deepcopy(case["evidence"]) if evidence is None else evidence}


def test_objective_counts_full_members_ties_and_unknown_dates_recomputed():
    records, cases = candidates()
    index = {row["record_id"]: row for row in records}
    for case in cases:
        if case["task_family"] not in prepare.FAMILIES:
            assert prepare.objective_reference(case, index) == case["reference"]
    tied = next(c for c in cases if c["task_family"] == "tied_highest_count")
    assert tied["reference"]["sponsors"] == ["Alpha", "Beta"]
    years = next(c for c in cases if c["task_family"] == "yearly_counts" and c["arguments"]["sponsor"] == "Alpha")
    assert {"year": "Unknown date", "count": 1} in years["reference"]["groups"]


@pytest.mark.parametrize("change", ["count", "members", "version", "flags", "focal", "enabled", "approved"])
def test_stale_counts_bindings_focal_quotes_or_authority_rejected(change):
    records, cases = candidates()
    if change in {"count", "members"}:
        case = next(c for c in cases if c["task_family"] == "outlet_volume")
        if change == "count":
            case["reference"]["count"] += 1
        else:
            case["source_records"].pop()
    elif change == "version":
        cases[0]["source_records"][0]["version_id"] = "stale"
    elif change == "flags":
        cases[0]["source_records"][0]["retrievable"] = False
    elif change == "focal":
        next(c for c in cases if c["source_span"])["source_span"]["quote"] = "invented quote"
    elif change == "enabled":
        cases[0]["runtime_enabled"] = True
    else:
        cases[0]["human_gold_approved"] = True
    with pytest.raises(ValueError):
        prepare.compile_references(cases, records, annotations_for(cases))


@pytest.mark.parametrize("change", ["speaker", "label", "unresolved_label", "outside", "focal_missing", "extra", "missing"])
def test_teacher_answers_require_literal_source_names_allowed_labels_and_focal(change):
    records, cases = candidates()
    annotations = annotations_for(cases)
    case = next(c for c in cases if c["task_family"] == "speaker_attribution")
    row = annotations[case["case_id"]]
    if change == "speaker":
        row["speaker_names"] = ["Unmentioned Employee"]
    elif change == "label":
        row["labels"]["speaker_role"] = "unsupported"
    elif change == "unresolved_label":
        row["status"] = "unresolved"
    elif change == "outside":
        row["evidence_intervals"][0]["end"] = 100000
    elif change == "focal_missing":
        row["evidence_intervals"][0]["start"] += 1
    elif change == "extra":
        annotations["not-a-case"] = deepcopy(row)
    else:
        annotations.pop(case["case_id"])
    with pytest.raises(ValueError):
        prepare.compile_references(cases, records, annotations)


def test_unresolved_reference_stays_null_and_is_separately_excluded():
    records, cases = candidates()
    annotations = annotations_for(cases)
    row = next(iter(annotations.values()))
    row.update(status="unresolved", labels={})
    refs = prepare.compile_references(cases, records, annotations)
    unknown = next(c for c in refs if c["case_id"] == row["case_id"])
    assert unknown["expected_fields"] is None
    report = score.evaluate(refs, [prediction(unknown, "unknown")], {r["record_id"]: r for r in records}, executed=True, fixture=True)
    assert report["unresolved_references_excluded"] == 1
    assert all(c.get("status") == "reference_unresolved_not_scored" for c in report["cases"] if c["case_id"] == unknown["case_id"])


def test_unicode_offsets_use_original_codepoints_and_retrieval_range():
    records, _ = candidates()
    source = records[0]
    result = prepare.located_evidence(source, {"start": 0, "end": 3})
    assert result["quote"] == "中文💡"
    assert result["offset_unit"] == "unicode_codepoints"
    with pytest.raises(ValueError):
        prepare.located_evidence(source, {"start": False, "end": 3})
    source["retrieval_ranges"] = [[4, len(source["body"])]]
    with pytest.raises(ValueError):
        prepare.located_evidence(source, {"start": 0, "end": 3})


def test_existing_output_refused_even_when_empty(tmp_path):
    with pytest.raises(ValueError, match="output_directory_already_exists"):
        prepare.prepare(Path("absent"), Path("absent"), Path("absent"), tmp_path)


def test_compiled_jsonl_can_be_read_back_and_bound_to_not_run_report(tmp_path):
    paths = prepared(tmp_path)
    summary = prepare.prepare(*paths)
    out = paths[-1]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    refs = prepare.read_lines(out / "references.jsonl")
    assert len(refs) == summary["reference_cases"]
    report = score.score_files(out, out / "predictions.template.json")
    assert report["status"] == "not_run" and report["system_predictions"] == 0
    assert report["metrics"]["objective"]["strict_task_match"]["rate"] is None
    assert report["metrics"]["ai_reference"]["strict_task_match"]["rate"] is None
    assert report["human_verified_accuracy"] is None and report["overall_mixed_accuracy"] is None
    assert report["client24_test_score"] is None
    assert not manifest["fit_parameters_or_prompts"] and not manifest["runtime_enabled"]
    assert all(not r["permitted_in_training_or_prompts"] for r in refs)


@pytest.mark.parametrize("change", ["model", "input_hash", "references_hash", "read_ids", "full_body", "human"])
def test_teacher_receipt_and_actual_full_input_checked_before_output(tmp_path, change):
    paths = prepared(tmp_path)
    seeds, snapshot, teacher_root, out = paths
    config = prepare.FAMILIES["speaker_attribution"]
    receipt_path = teacher_root / config["directory"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if change == "model":
        receipt["model"] = "other-model"
    elif change == "input_hash":
        receipt["input_sha256"] = "stale"
    elif change == "references_hash":
        receipt["references_sha256"] = "stale"
    elif change == "read_ids":
        receipt["full_context_read_case_ids"].pop()
    elif change == "human":
        receipt["human_approved"] = True
    else:
        inp = teacher_root / "root/inputs/speaker_attribution.jsonl"
        rows = prepare.read_lines(inp)
        rows[0]["full_saved_body"] = "summary instead of the complete saved body"
        write_lines(inp, rows)
        receipt["input_sha256"] = prepare.digest(inp.read_bytes())
    receipt_path.write_bytes(prepare.encoded(receipt))
    with pytest.raises(ValueError):
        prepare.prepare(seeds, snapshot, teacher_root, out)
    assert not out.exists()


@pytest.mark.parametrize("actual", [{"count": True}, {"count": 1.0}, {"count": 1, "extra": False}, {}])
def test_exact_fields_reject_type_confusion_or_missing_extra_fields(actual):
    assert not score.exact_fields(actual, {"count": 1})


def test_only_declared_unordered_lists_ignore_order():
    assert score.exact_fields({"sponsors": ["Beta", "Alpha"], "speaker_names": ["  Local  Researcher "]},
                              {"sponsors": ["Alpha", "Beta"], "speaker_names": ["local researcher"]})
    assert not score.exact_fields({"period_counts": [1, 2]}, {"period_counts": [2, 1]})


def test_missing_unknown_failed_answers_reduce_strict_rate_and_show_coverage():
    records, refs = compiled()
    objective = [r for r in refs if r["reference_kind"] == "source_computed_objective"][:4]
    preds = [prediction(objective[0]), prediction(objective[1], "unknown"), prediction(objective[2], "failed")]
    report = score.evaluate(objective, preds, {r["record_id"]: r for r in records}, executed=True, fixture=True)
    group = report["metrics"]["objective"]
    assert group["strict_task_match"] == {"numerator": 1, "denominator": 4, "rate": 0.25}
    assert group["answered_only_match"]["rate"] == 1.0
    assert group["answered_coverage"]["rate"] == 0.25
    assert group["prediction_coverage"]["rate"] == 0.75
    assert (group["unknown"], group["failed"], group["missing"]) == (1, 1, 1)
    assert report["status"] == "fixture_not_system_score" and report["human_verified_accuracy"] is None


@pytest.mark.parametrize("change", ["unknown_id", "duplicate", "unknown_fields", "unexecuted"])
def test_prediction_membership_run_and_abstention_integrity(change):
    records, refs = compiled()
    preds = [prediction(refs[0])]
    if change == "unknown_id":
        preds[0]["case_id"] = "not-a-case"
    elif change == "duplicate":
        preds.append(deepcopy(preds[0]))
    elif change == "unknown_fields":
        preds[0]["status"] = "unknown"
    with pytest.raises(ValueError):
        score.evaluate(refs, preds, {r["record_id"]: r for r in records}, executed=change != "unexecuted")


@pytest.mark.parametrize("field,value", [("quote", "invented"), ("version_id", "old"),
                                         ("body_sha256", "old"), ("offset_unit", "utf8_bytes"), ("start", -1)])
def test_citation_validity_not_confused_with_matching_labels(field, value):
    records, refs = compiled()
    case = next(r for r in refs if r["reference_kind"] == "ai_teacher_semantic")
    pred = prediction(case)
    pred["evidence"][0][field] = value
    report = score.evaluate([case], [pred], {r["record_id"]: r for r in records}, executed=True, fixture=True)
    assert report["metrics"]["ai_reference"]["strict_task_match"]["rate"] == 1.0
    assert report["source_quote_locator_validity"]["rate"] == 0.0
    assert report["semantic_full_focal_citation_coverage"]["rate"] == 0.0


def test_label_match_with_no_quotes_does_not_get_evidence_credit():
    records, refs = compiled()
    case = next(r for r in refs if r["reference_kind"] == "ai_teacher_semantic")
    report = score.evaluate([case], [prediction(case, evidence=[])], {r["record_id"]: r for r in records}, executed=True, fixture=True)
    assert report["source_quote_locator_validity"]["rate"] is None
    assert report["semantic_full_focal_citation_coverage"]["rate"] == 0.0


@pytest.mark.parametrize("change", ["manifest", "snapshot", "run", "prompt"])
def test_prediction_file_binds_reference_snapshot_and_actual_run(tmp_path, change):
    paths = prepared(tmp_path)
    prepare.prepare(*paths)
    out = paths[-1]
    payload = json.loads((out / "predictions.template.json").read_text(encoding="utf-8"))
    if change == "manifest":
        payload["reference_manifest_sha256"] = "stale"
    elif change == "snapshot":
        payload["source_snapshot_sha256"] = "stale"
    elif change == "run":
        payload.pop("run")
    else:
        payload["run"].update(executed=True, model="fixture", prompt_sha256="not-hash")
    p = out / "malformed_predictions.json"
    p.write_bytes(prepare.encoded(payload))
    with pytest.raises(ValueError):
        score.score_files(out, p)
