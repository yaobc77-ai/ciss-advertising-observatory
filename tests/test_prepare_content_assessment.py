"""Synthetic file-backed CLI contracts; these tests do not measure semantic quality."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "prepare_content_assessment", Path(__file__).parents[1] / "scripts/prepare_content_assessment.py"
)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def definitions():
    return {"status": "draft_requires_client_confirmation", "questions": [
        {"question_id": qid, "question_exact": text, "source_paragraph_exact": text,
         "query_question": text, "source_ref": f"synthetic-P{i}",
         "status": "draft_requires_client_confirmation", "definition_draft": "Synthetic draft rule pending review.",
         "candidate_search_terms": ["blue hydrogen", "CCS"]}
        for i, (qid, text) in enumerate(zip(cli.mechanism.QUESTION_IDS, cli.mechanism.QUESTION_TEXTS, strict=True), 1)
    ]}


def record(rid, body=None, *, active=True, **values):
    if body is None:
        body = "The company describes a proposal for equipment at a plant. An independent researcher questions its effects. " * 3
    payload = {"record_id": rid, "dataset": "native", "body": body,
               "countable": True, "retrievable": True, "url": f"https://example.org/{rid}",
               "title": "Synthetic ad", "publisher": "Synthetic publisher", "sponsor": "Synthetic sponsor",
               "raw": {}, "issues": []}
    payload.update(values)
    return {"record_id": rid, "dataset": payload["dataset"], "version_id": cli.canonical_digest(payload),
            "active": active, "body": body, "payload": payload}


@pytest.fixture
def inputs(tmp_path):
    questions, sources = tmp_path / "questions.json", tmp_path / "sources.json"
    questions.write_bytes(cli.original.encoded(definitions()))
    sources.write_bytes(cli.original.encoded([
        record("ordinary"), record("no-keywords", "No matching search term is present. " * 10),
        record("empty", "", retrievable=False), record("video", "video", retrievable=False),
        record("excluded", countable=False), record("inactive", active=False),
        record("social", dataset="social"),
    ]))
    packet = tmp_path / "source_packet"
    cli.original.prepare(sources, questions, packet)
    return SimpleNamespace(root=tmp_path, packet=packet, prepared=tmp_path / "prepared",
                           responses=tmp_path / "responses.json", output=tmp_path / "replayed")


def read(root, name):
    return json.loads((root / name).read_bytes())


def lines(root, name):
    return [json.loads(line) for line in (root / name).read_text(encoding="utf-8").splitlines()]


def replace(root, name, value, *, manifest_name="manifest.json", map_name="artifacts", raw=False):
    data = value if raw else cli.original.encoded(value)
    (root / name).write_bytes(data)
    manifest = read(root, manifest_name)
    manifest[map_name][name] = cli.original.digest(data)
    (root / manifest_name).write_bytes(cli.original.encoded(manifest))


def prepare(inputs, **kwargs):
    return cli.prepare(inputs.packet, inputs.prepared, **kwargs)


def response(request, *, positive=False):
    judgments = []
    for qid in cli.mechanism.QUESTION_IDS:
        relevant = positive and qid == "Q06"
        judgments.append({"question_id": qid, "membership": "relevant" if relevant else "not_found",
                          "support_passage_ids": [next(iter(request["passage_catalog"]))] if relevant else [],
                          "limiting_passage_ids": [], "speaker": "company", "treatment": "reported",
                          "temporal_status": "planned", "rationale": "Synthetic replay rationale.",
                          "consensus_position": "not_applicable", "consensus_passage_ids": []})
    return {"judgments": judgments}


def write_responses(inputs, rows):
    inputs.responses.write_bytes(cli.original.encoded(rows))


def run_replay(inputs, rows):
    write_responses(inputs, rows)
    return cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)


def ready(inputs):
    return next(row for row in lines(inputs.prepared, "requests.jsonl") if row["request"]["status"] == "ready")


def test_prepare_includes_no_keyword_missing_body_and_every_selected_record(inputs):
    summary = prepare(inputs)
    wrappers = lines(inputs.prepared, "requests.jsonl")
    assert {row["request"]["record_id"] for row in wrappers} == {"ordinary", "no-keywords", "empty", "video"}
    assert summary["selected_records"] == 4 and summary["judgment_slots"] == 96
    assert summary["ready_records"] == summary["not_requested_records"] == 2
    no_hint = next(row["request"] for row in wrappers if row["request"]["record_id"] == "no-keywords")
    assert no_hint["status"] == "ready"
    assert no_hint["record"]["body"] in json.dumps(no_hint["model_input"], ensure_ascii=False)
    assert all(row["request_id"] == cli.canonical_digest(row["request"]) for row in wrappers)
    assert summary["classifications"] == summary["model_calls"] == summary["database_writes"] == 0
    assert summary["quality_scores"] is None and not summary["semantic_gold"]
    assert summary["response_origin"] == "not_obtained" and not summary["response_origin_verified"]


def test_prepare_preserves_metadata_annotations_full_body_and_exact_frozen_bytes(inputs):
    loaded = cli.load_content_packet(inputs.packet)
    prepare(inputs)
    for row in lines(inputs.prepared, "requests.jsonl"):
        expected = next(r for r in loaded["selected"] if r["record_id"] == row["request"]["record_id"])
        assert row["request"]["record"] == expected
        assert row["request"]["definitions"] == loaded["definitions"]
    for name in cli.INPUT_NAMES:
        assert (inputs.prepared / "inputs" / name).read_bytes() == (inputs.packet / name).read_bytes()
    assert (inputs.prepared / "inputs/source_manifest.json").read_bytes() == (inputs.packet / "manifest.json").read_bytes()
    manifest = read(inputs.prepared, "manifest.json")
    assert manifest["complete"] is True
    assert all(cli.original.digest((inputs.prepared / name).read_bytes()) == sha for name, sha in manifest["artifacts"].items())


def test_duplicate_bodies_keep_distinct_record_requests_and_scope(tmp_path):
    q, s = tmp_path / "q.json", tmp_path / "s.json"
    q.write_bytes(cli.original.encoded(definitions()))
    s.write_bytes(cli.original.encoded([record("one"), record("two")]))
    packet, out = tmp_path / "packet", tmp_path / "out"
    cli.original.prepare(s, q, packet)
    result = cli.prepare(packet, out)
    assert result["selected_records"] == 2
    assert len({r["request_id"] for r in lines(out, "requests.jsonl")}) == 2


def test_token_budget_skip_keeps_complete_body_and_deterministic_request(inputs):
    summary = prepare(inputs, max_input_tokens=1)
    wrappers = lines(inputs.prepared, "requests.jsonl")
    assert summary["not_requested_records"] == 4
    assert all(r["request"]["model_input"] is None for r in wrappers)
    loaded = cli.load_content_packet(inputs.packet)
    assert wrappers == cli.build_requests(loaded, 1)
    assert all(r["request"]["record"]["body"] == next(s["body"] for s in loaded["selected"] if s["record_id"] == r["request"]["record_id"]) for r in wrappers)


def test_missing_responses_retain_every_record_and_24_unknown_not_negatives(inputs):
    prepare(inputs)
    summary = run_replay(inputs, [])
    results = lines(inputs.output, "results.jsonl")
    assert len(results) == 4 and summary["judgment_slots"] == 96
    assert summary["processing_status_counts"] == {"not_requested": 2, "not_processed": 2}
    for row in results:
        assert len(row["assessment"]["judgments"]) == 24
        assert all(j["membership"] == "unknown" and j["article_membership"] == "uncertain" for j in row["assessment"]["judgments"])
        assert row["assessment"]["publication_status"] == "hold"
        assert row["assessment"]["source_completeness"] == "unknown"
        assert row["response_origin"] == "not_provided"
    assert summary["response_origin"] == "external_replay_unverified"
    assert summary["response_origin_verified"] is False
    assert summary["judgment_membership_counts"] == {"unknown": 96}
    assert summary["reviewed_units"] == summary["article_negative_units"] == 0


def test_valid_replay_is_draft_and_program_resolves_original_evidence(inputs):
    prepare(inputs)
    wrapper = ready(inputs)
    source_bytes = inputs.responses
    summary = run_replay(inputs, [{"request_id": wrapper["request_id"], "response": response(wrapper["request"], positive=True)}])
    result = next(r for r in lines(inputs.output, "results.jsonl") if r["request_id"] == wrapper["request_id"])
    assert result["processing_status"] == "processed"
    assert result["validation_error_type"] is None
    for field in ("record_id", "version_id", "body_sha256", "payload_sha256", "definitions_sha256", "request_sha256"):
        assert result[field] == wrapper["request"][field] == result["assessment"][field]
    positive = next(j for j in result["assessment"]["judgments"] if j["question_id"] == "Q06")
    assert positive["article_membership"] == "candidate_relevant"
    evidence = positive["support_evidence"][0]
    assert wrapper["request"]["record"]["body"][evidence["start"]:evidence["end"]] == evidence["quote"]
    assert all(j["article_membership"] != "negative" for j in result["assessment"]["judgments"])
    assert summary["quality_scores"] is None and not summary["customer_approved"]
    assert summary["model_calls"] == summary["source_adoptions"] == summary["publications"] == 0
    assert (inputs.output / "inputs/responses.json").read_bytes() == source_bytes.read_bytes()
    assert summary["responses_sha256"] == cli.original.digest(source_bytes.read_bytes())
    manifest = read(inputs.output, "manifest.json")
    assert all(cli.original.digest((inputs.output / name).read_bytes()) == sha for name, sha in manifest["artifacts"].items())


@pytest.mark.parametrize("malformed", [None, 42, [], {}, {"judgments": []}, {"private": "password=private"}])
def test_invalid_individual_response_preserves_record_as_unknown_and_no_sensitive_error(inputs, malformed):
    prepare(inputs)
    wrapper = ready(inputs)
    summary = run_replay(inputs, [{"request_id": wrapper["request_id"], "response": malformed}])
    result = next(r for r in lines(inputs.output, "results.jsonl") if r["request_id"] == wrapper["request_id"])
    assert len(lines(inputs.output, "results.jsonl")) == 4
    assert summary["processing_status_counts"]["validation_failed"] == 1
    assert result["processing_status"] == "validation_failed" and result["validation_error_type"]
    assert result["assessment"]["processing_status"] == "validation_failed"
    assert result["assessment"]["response_received"] is True
    assert result["assessment"]["reason"] == "invalid_external_response"
    assert len(result["assessment"]["judgments"]) == 24
    assert all(j["membership"] == "unknown" for j in result["assessment"]["judgments"])
    assert "password=private" not in (inputs.output / "results.jsonl").read_text(encoding="utf-8")


def test_unknown_passage_does_not_destroy_other_records(inputs):
    prepare(inputs)
    wrapper = ready(inputs)
    draft = response(wrapper["request"], positive=True)
    draft["judgments"][5]["support_passage_ids"] = ["P999999"]
    summary = run_replay(inputs, [{"request_id": wrapper["request_id"], "response": draft}])
    assert summary["processing_status_counts"]["validation_failed"] == 1
    assert len(lines(inputs.output, "results.jsonl")) == 4


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "skip", "extra_field", "not_list", "nonobject_row"])
def test_response_envelope_errors_stop_entire_batch_before_output(inputs, kind):
    prepare(inputs)
    wrapper = ready(inputs)
    entry = {"request_id": wrapper["request_id"], "response": response(wrapper["request"])}
    if kind == "duplicate":
        rows = [entry, deepcopy(entry)]
    elif kind == "unknown":
        rows = [{**entry, "request_id": "0" * 64}]
    elif kind == "skip":
        skip = next(r for r in lines(inputs.prepared, "requests.jsonl") if r["request"]["status"] == "not_requested")
        rows = [{**entry, "request_id": skip["request_id"]}]
    elif kind == "extra_field":
        rows = [{**entry, "approved": True}]
    elif kind == "not_list":
        rows = entry
    else:
        rows = ["private"]
    write_responses(inputs, rows)
    with pytest.raises(ValueError):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


@pytest.mark.parametrize("raw", [b'[{"request_id":"one","request_id":"two","response":{}}]',
                                 b'[{"request_id":"one","response":{"judgments":NaN}}]',
                                 b'[{"request_id":"one","response":{"judgments":Infinity}}]'])
def test_nonfinite_and_duplicate_json_keys_refused_globally(inputs, raw):
    prepare(inputs)
    inputs.responses.write_bytes(raw)
    with pytest.raises(ValueError):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


@pytest.mark.parametrize("name", ["source_snapshot.json", "question_definitions.json", "preparation_summary.json", "review_guide.md"])
def test_any_declared_source_file_tamper_refused(inputs, name):
    (inputs.packet / name).write_bytes((inputs.packet / name).read_bytes() + b" ")
    with pytest.raises(ValueError, match="artifact_changed"):
        prepare(inputs)
    assert not inputs.prepared.exists()


@pytest.mark.parametrize("key,value", [
    ("status", "approved"), ("customer_approved", True), ("customer_approved", 0),
    ("semantic_gold", True), ("quality_scores", {}), ("format_version", "other"),
    ("input_sha256", []), ("input_sha256", None),
])
def test_source_manifest_scope_and_unapproved_flags_refused(inputs, key, value):
    manifest = read(inputs.packet, "manifest.json")
    manifest[key] = value
    (inputs.packet / "manifest.json").write_bytes(cli.original.encoded(manifest))
    with pytest.raises(ValueError):
        prepare(inputs)
    assert not inputs.prepared.exists()


@pytest.mark.parametrize("name", ["../outside", "a/../x", "/absolute", "C:/absolute", "a\\b", "a//b", "./x"])
def test_unsafe_declared_source_paths_refused(inputs, name):
    manifest = read(inputs.packet, "manifest.json")
    manifest["input_sha256"][name] = "0" * 64
    (inputs.packet / "manifest.json").write_bytes(cli.original.encoded(manifest))
    with pytest.raises(ValueError):
        prepare(inputs)
    assert not inputs.prepared.exists()


@pytest.mark.parametrize("key,value", [
    ("selected_records", 1), ("source_records", 1), ("question_count", 23),
    ("review_units", 0), ("reviewed_units", 1), ("relevant_units", 0),
    ("selection", {"dataset": "all"}), ("selection_sha256", "0" * 64),
    ("source_snapshot_sha256", "0" * 64), ("customer_approved", True),
    ("semantic_gold", True), ("quality_scores", {}), ("unseen_test", True),
])
def test_rehashed_source_summary_scope_or_claims_refused(inputs, key, value):
    summary = read(inputs.packet, "preparation_summary.json")
    summary[key] = value
    replace(inputs.packet, "preparation_summary.json", summary, map_name="input_sha256")
    with pytest.raises(ValueError):
        prepare(inputs)
    assert not inputs.prepared.exists()


@pytest.mark.parametrize("kind", ["version", "body", "identity", "dataset", "payload_sha", "body_sha", "ranges", "duplicate"])
def test_rehashed_source_snapshot_canonical_identity_and_convenience_fields_refused(inputs, kind):
    snapshot = read(inputs.packet, "source_snapshot.json")
    row = snapshot["records"][0]
    if kind == "version":
        row["version_id"] = "0" * 64
    elif kind == "body":
        row["body"] = "different"
    elif kind == "identity":
        row["payload"]["record_id"] = "different"
    elif kind == "dataset":
        row["dataset"] = "social" if row["dataset"] == "native" else "native"
    elif kind == "payload_sha":
        row["payload_sha256"] = "0" * 64
    elif kind == "body_sha":
        row["body_sha256"] = "0" * 64
    elif kind == "ranges":
        row["retrieval_ranges"] = [[0, 1]]
    else:
        snapshot["records"].append(deepcopy(row))
    replace(inputs.packet, "source_snapshot.json", snapshot, map_name="input_sha256")
    with pytest.raises(ValueError):
        prepare(inputs)


def test_changed_definitions_question_count_or_exact_wording_refused(inputs):
    draft = read(inputs.packet, "question_definitions.json")
    draft["questions"][0]["question_exact"] = "Altered client question"
    replace(inputs.packet, "question_definitions.json", draft, map_name="input_sha256")
    with pytest.raises(ValueError):
        prepare(inputs)


@pytest.mark.parametrize("name", ["requests.jsonl", "preparation_summary.json", "inputs/source_manifest.json", "inputs/source_snapshot.json"])
def test_prepared_artifact_hash_tamper_stops_replay(inputs, name):
    prepare(inputs)
    (inputs.prepared / name).write_bytes((inputs.prepared / name).read_bytes() + b" ")
    write_responses(inputs, [])
    with pytest.raises(ValueError, match="artifact_changed"):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


@pytest.mark.parametrize("kind", ["drop_record", "duplicate_record", "request_id", "model_input", "schema", "status", "definition"])
def test_rehashed_prepared_request_changes_are_rebuilt_and_refused(inputs, kind):
    prepare(inputs)
    wrappers = lines(inputs.prepared, "requests.jsonl")
    if kind == "drop_record":
        wrappers.pop()
    elif kind == "duplicate_record":
        wrappers.append(deepcopy(wrappers[0]))
    elif kind == "request_id":
        wrappers[0]["request_id"] = "0" * 64
    else:
        request = next(w["request"] for w in wrappers if w["request"]["status"] == "ready")
        if kind == "model_input":
            request["model_input"] = {"instruction": "Do something else"}
        elif kind == "schema":
            request["response_schema"] = {}
        elif kind == "status":
            request["status"] = "not_requested"
        else:
            request["definitions"]["questions"][0]["definition_draft"] = "different"
        request["request_sha256"] = cli.canonical_digest({k: v for k, v in request.items() if k != "request_sha256"})
        for wrapper in wrappers:
            wrapper["request_id"] = cli.canonical_digest(wrapper["request"])
    replace(inputs.prepared, "requests.jsonl", cli.jsonl_bytes(wrappers), raw=True)
    write_responses(inputs, [])
    with pytest.raises(ValueError, match="rebuilt_scope"):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


def test_stale_module_or_cli_code_fingerprint_refused_even_if_rehashed(inputs, monkeypatch):
    prepare(inputs)
    before = cli.code_fingerprints()
    monkeypatch.setattr(cli, "code_fingerprints", lambda: {**before, "mechanism_sha256": "0" * 64})
    write_responses(inputs, [])
    with pytest.raises(ValueError, match="code_changed"):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


def test_rehashed_changed_source_packet_binding_stops_all_replay(inputs):
    prepare(inputs)
    snapshot = read(inputs.packet, "source_snapshot.json")
    snapshot["observation"]["new_note"] = "changed frozen source input"
    data = cli.original.encoded(snapshot)
    replace(inputs.packet, "source_snapshot.json", data, map_name="input_sha256", raw=True)
    summary = read(inputs.packet, "preparation_summary.json")
    summary["source_snapshot_sha256"] = cli.original.digest(data)
    replace(inputs.packet, "preparation_summary.json", summary, map_name="input_sha256")
    write_responses(inputs, [])
    with pytest.raises(ValueError, match="source_binding_changed"):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


@pytest.mark.parametrize("key,value", [
    ("status", "approved"), ("customer_approved", True), ("semantic_gold", True),
    ("quality_scores", {}), ("complete", False), ("model_calls", 1), ("publications", 1),
    ("artifacts", []),
])
def test_prepared_manifest_claims_and_shape_refused(inputs, key, value):
    prepare(inputs)
    manifest = read(inputs.prepared, "manifest.json")
    manifest[key] = value
    (inputs.prepared / "manifest.json").write_bytes(cli.original.encoded(manifest))
    write_responses(inputs, [])
    with pytest.raises(ValueError):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


@pytest.mark.parametrize("key,value", [
    ("selected_records", 1), ("ready_records", 1), ("request_ids_sha256", "0" * 64),
    ("max_input_tokens", 1), ("max_input_tokens", True), ("quality_scores", {}),
])
def test_rehashed_prepared_summary_stale_counts_budget_and_bindings_refused(inputs, key, value):
    prepare(inputs)
    summary = read(inputs.prepared, "preparation_summary.json")
    summary[key] = value
    replace(inputs.prepared, "preparation_summary.json", summary)
    write_responses(inputs, [])
    with pytest.raises(ValueError):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


def test_rehashed_prepared_request_duplicate_json_keys_refused(inputs):
    prepare(inputs)
    raw = b'{"request_id":"one","request_id":"two","request":{}}\n'
    replace(inputs.prepared, "requests.jsonl", raw, raw=True)
    write_responses(inputs, [])
    with pytest.raises(ValueError, match="invalid_assessment_json"):
        cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.output)
    assert not inputs.output.exists()


def test_source_json_duplicate_keys_refused_even_after_manifest_rehash(inputs):
    raw = b'{"records":[],"records":[]}'
    replace(inputs.packet, "source_snapshot.json", raw, map_name="input_sha256", raw=True)
    with pytest.raises(ValueError, match="invalid_assessment_json"):
        prepare(inputs)


def test_missing_essential_declared_input_refused_before_output(inputs):
    manifest = read(inputs.packet, "manifest.json")
    del manifest["input_sha256"]["question_definitions.json"]
    (inputs.packet / "manifest.json").write_bytes(cli.original.encoded(manifest))
    with pytest.raises(ValueError, match="complete_assessment_artifacts_required"):
        prepare(inputs)


def test_invalid_response_evidence_retains_other_valid_response(inputs):
    prepare(inputs)
    wrappers = [r for r in lines(inputs.prepared, "requests.jsonl") if r["request"]["status"] == "ready"]
    malformed = response(wrappers[0]["request"], positive=True)
    malformed["judgments"][5]["support_passage_ids"] = ["P999999"]
    summary = run_replay(inputs, [
        {"request_id": wrappers[0]["request_id"], "response": malformed},
        {"request_id": wrappers[1]["request_id"], "response": response(wrappers[1]["request"], positive=True)},
    ])
    assert summary["processing_status_counts"] == {"not_requested": 2, "validation_failed": 1, "processed": 1}
    assert summary["judgment_membership_counts"] == {"unknown": 72, "relevant": 1, "not_found": 23}
    assert len(lines(inputs.output, "results.jsonl")) == 4


@pytest.mark.parametrize("kind", ["existing", "inside_original", "inside_prepared"])
def test_output_must_be_new_and_outside_inputs(inputs, kind):
    if kind == "existing":
        inputs.prepared.mkdir()
        with pytest.raises(ValueError, match="new_output"):
            prepare(inputs)
    elif kind == "inside_original":
        with pytest.raises(ValueError, match="inside_input"):
            cli.prepare(inputs.packet, inputs.packet / "new-child")
        assert not (inputs.packet / "new-child").exists()
    else:
        prepare(inputs)
        write_responses(inputs, [])
        with pytest.raises(ValueError, match="inside_input"):
            cli.replay(inputs.packet, inputs.prepared, inputs.responses, inputs.prepared / "new-child")
        assert not (inputs.prepared / "new-child").exists()


@pytest.mark.parametrize("budget", [0, -1, True, 1_000_001, "24000"])
def test_invalid_input_token_budget_refused_before_output(inputs, budget):
    with pytest.raises(ValueError):
        prepare(inputs, max_input_tokens=budget)
    assert not inputs.prepared.exists()


def test_total_packet_size_is_bounded(inputs, monkeypatch):
    monkeypatch.setattr(cli, "MAX_PACKET_BYTES", 1)
    with pytest.raises(ValueError, match="too_large"):
        prepare(inputs)


def test_single_artifact_size_is_bounded(inputs, monkeypatch):
    monkeypatch.setattr(cli.original, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="too_large"):
        prepare(inputs)


def test_cli_prepare_then_replay_runs_only_file_work(inputs, monkeypatch, capsys):
    monkeypatch.setattr(cli.original, "acquire_database", lambda: (_ for _ in ()).throw(AssertionError("DB forbidden")))
    assert cli.main(["prepare", "--packet", str(inputs.packet), "--out", str(inputs.prepared)]) == 0
    write_responses(inputs, [])
    assert cli.main(["replay", "--packet", str(inputs.packet), "--prepared", str(inputs.prepared),
                     "--responses", str(inputs.responses), "--out", str(inputs.output)]) == 0
    assert '"model_calls": 0' in capsys.readouterr().out


def test_cli_failure_does_not_echo_private_error_text(inputs, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_content_packet", lambda _: (_ for _ in ()).throw(RuntimeError("password=private")))
    assert cli.main(["prepare", "--packet", str(inputs.packet), "--out", str(inputs.prepared)]) == 2
    text = capsys.readouterr().out
    assert "private" not in text and '"error_type": "RuntimeError"' in text


def test_preparer_does_not_modify_input_bytes_and_definitions(inputs):
    before = {str(p.relative_to(inputs.packet)): p.read_bytes() for p in inputs.packet.rglob("*") if p.is_file()}
    prepare(inputs)
    run_replay(inputs, [])
    assert before == {str(p.relative_to(inputs.packet)): p.read_bytes() for p in inputs.packet.rglob("*") if p.is_file()}
