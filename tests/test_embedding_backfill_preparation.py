"""Independent fictional inputs: freeze, cost, scope, drift and paid-resume gates."""

from copy import deepcopy
from decimal import Decimal

import pytest

from scripts import prepare_embedding_backfill as prep


def chunk(text="Wren Harbor preserves this unchanged source passage.", *, dataset="native", cid="chunk-a", cached=False):
    return {"chunk_id": cid, "dataset": dataset, "record_id": dataset + ":fictional-" + cid,
            "version_id": prep.sha("version-" + cid), "body_hash": prep.sha(text),
            "text": text, "text_hash": prep.sha(text), "start_char": 0, "end_char": len(text),
            "token_count": prep._tokens(text), "source_observation_id": None,
            "source_version_id": None, "source_body_hash": None, "cached": cached}


def state(rows):
    definition = {"embedding_input": prep.INPUT_STRATEGY, "embedding_model": prep.MODEL}
    return {"snapshot": {"active_profile": "fictional-profile", "chunks": len(rows), "data_version": "frozen-data"},
            "profile": {"definition": definition, "definition_hash": prep.sha(prep.canonical(definition))},
            "cache": {r["text_hash"]: "cached-vector-digest" for r in rows if r["cached"]},
            "tables": {name: {"rows": 1, "fingerprint": "frozen-" + name} for name in prep.STATE_TABLES},
            "model": prep.MODEL, "code_sha256": {"fictional.py": "frozen-code"}, "transaction_read_only": "on"}


def frozen(tmp_path, *, batch_size=1):
    rows = [chunk(), chunk("Kestrel Cooperative supplies a second literal passage.", cid="chunk-b")]
    original = state(rows)
    manifest, inputs, batches = prep.prepare(original, rows, batch_size=batch_size)
    manifest = prep.write_bundle(tmp_path / "bundle", manifest, inputs, batches)
    return original, manifest, inputs, batches


def checkpoint(manifest, batch, reservation_id="fictional-reservation"):
    return {"state": "settled_cached", "plan_sha256": manifest["plan_sha256"], "model": prep.MODEL,
            "dimensions": 1536, "reservation_id": reservation_id, "response_sha256": "a" * 64,
            "batch_id": batch["batch_id"], "request_sha256": batch["request_sha256"],
            "vector_hashes": {h: "fictional-vector-hash" for h in batch["text_hashes"]}}


def settlement(event):
    binding = {key: event[key] for key in ("plan_sha256", "batch_id", "request_sha256", "response_sha256",
                                          "model", "dimensions")}
    binding["schema"] = "embedding-backfill-settlement-v1"
    return {event["reservation_id"]: {"reservation_id": event["reservation_id"], "state": "settled",
                                      "kind": "embedding", "model": prep.MODEL, "actual_usd": "0.00000100",
                                      "usage": {"embedding_backfill": binding}}}


def test_shared_original_text_is_paid_once_but_all_source_bindings_survive():
    native = chunk()
    social = chunk(native["text"], dataset="social", cid="chunk-social")
    cached = chunk("A previously cached fictional passage.", cid="chunk-cache", cached=True)
    manifest, inputs, batches = prep.prepare(state([native, social, cached]), [native, social, cached])
    assert len(inputs) == len(batches) == 1
    assert inputs[0]["text"] == native["text"]
    assert {b["dataset"] for b in inputs[0]["bindings"]} == {"native", "social"}
    assert manifest["input_tokens"] == native["token_count"]
    assert Decimal(manifest["estimated_usd"]) == prep.price(prep.MODEL, native["token_count"])
    assert manifest["by_dataset"]["native"]["cached_chunks"] == 1
    assert manifest["by_dataset"]["social"]["unique_missing_texts"] == 1
    assert manifest["completed_vectors"] == manifest["api_calls"] == manifest["database_writes"] == 0
    assert manifest["metadata_prefix"] is manifest["index_activated"] is False


def test_unicode_and_literal_special_tokens_are_not_rewritten():
    row = chunk("Wren Harbor：保留 ♨️ café\n<|endoftext|> 的原字符。")
    _, inputs, _ = prep.prepare(state([row]), [row])
    assert inputs[0]["text"].encode("utf-8") == row["text"].encode("utf-8")
    assert inputs[0]["utf8_bytes"] == len(row["text"].encode("utf-8"))


@pytest.mark.parametrize("field,value", [("text_hash", "0" * 64), ("token_count", 999), ("text", "changed")])
def test_changed_hash_token_or_original_text_is_rejected(field, value):
    row = chunk()
    row[field] = value
    with pytest.raises(ValueError):
        prep.prepare(state([row]), [row])


def test_duplicate_chunk_binding_does_not_create_false_coverage():
    row = chunk()
    with pytest.raises(ValueError, match="Duplicate"):
        prep.prepare(state([row]), [row, deepcopy(row)])


def test_source_interval_validation_rejects_wrong_observation_and_body():
    row = chunk()
    source = {key: row[key] for key in ("record_id", "dataset", "version_id", "body_hash")}
    source["body"] = row["text"]
    prep.validate_chunk(row, source)
    source["body"] = source["body"].replace("Wren", "Lark")
    with pytest.raises(ValueError, match="interval"):
        prep.validate_chunk(row, source)
    source["body"] = row["text"]
    row.update(dataset="social", source_observation_id="fictional-observation", source_version_id="v", source_body_hash="h")
    source["dataset"] = "social"
    with pytest.raises(ValueError, match="observation"):
        prep.validate_chunk(row, source, {})
    prep.validate_chunk(row, source, {"fictional-observation": {"body": row["text"], "source_version_id": "v", "source_body_hash": "h"}})


@pytest.mark.parametrize("size,tokens", [(0, 100), (2049, 100), (32, 300001), (True, 100)])
def test_invalid_api_batch_limits_are_rejected(size, tokens):
    with pytest.raises(ValueError):
        prep.batch_inputs([], size, tokens)


def test_batches_obey_combined_token_budget_and_never_drop_an_input():
    rows = [chunk("Wren Harbor " + str(i), cid="chunk-" + str(i)) for i in range(5)]
    manifest, inputs, batches = prep.prepare(state(rows), rows, batch_size=3,
                                           max_batch_tokens=max(r["token_count"] for r in rows) * 2)
    assert [h for b in batches for h in b["text_hashes"]] == [item["text_hash"] for item in inputs]
    assert all(len(b["text_hashes"]) <= 3 and b["input_tokens"] <= manifest["max_batch_tokens"] for b in batches)
    assert Decimal(manifest["existing_rag_reservation_upper_usd"]) >= Decimal(manifest["estimated_usd"])


def test_oversized_input_is_rejected_before_any_request_material_is_written():
    with pytest.raises(ValueError, match="Input exceeds"):
        prep.batch_inputs([{"input_tokens": 8193}])


def test_freeze_roundtrip_and_no_overwrite(tmp_path):
    _, manifest, inputs, batches = frozen(tmp_path)
    assert prep.read_bundle(tmp_path / "bundle") == (manifest, inputs, batches)
    with pytest.raises(FileExistsError):
        prep.write_bundle(tmp_path / "bundle", manifest, inputs, batches)


@pytest.mark.parametrize("filename", ["manifest.json", "inputs.jsonl", "batches.jsonl"])
def test_tampered_frozen_artifact_is_rejected(tmp_path, filename):
    frozen(tmp_path)
    path = tmp_path / "bundle" / filename
    path.write_text(path.read_text(encoding="utf-8").replace("Wren", "Lark") if filename == "inputs.jsonl"
                    else path.read_text(encoding="utf-8").replace("1536", "768").replace("batch-00001", "batch-99999"), encoding="utf-8")
    with pytest.raises(ValueError):
        prep.read_bundle(tmp_path / "bundle")


@pytest.mark.parametrize("key", ["snapshot", "profile", "cache", "tables", "code_sha256"])
def test_live_drift_rejects_prepared_bundle(tmp_path, key):
    original, manifest, _, _ = frozen(tmp_path)
    live = deepcopy(original)
    live[key] = {"changed": True}
    with pytest.raises(ValueError, match="drift"):
        prep.assert_unchanged(manifest, live)


def test_resume_skips_only_a_whole_settled_batch_with_live_cache(tmp_path):
    original, manifest, inputs, batches = frozen(tmp_path)
    event = checkpoint(manifest, batches[0])
    live = deepcopy(original)
    live["cache"].update(event["vector_hashes"])
    assert prep.resume_remaining(manifest, inputs, live, [event], settlement(event)) == batches[1]["text_hashes"]


def test_one_reservation_cannot_certify_two_different_batches(tmp_path):
    original, manifest, inputs, batches = frozen(tmp_path)
    events = [checkpoint(manifest, batch) for batch in batches]
    live = deepcopy(original)
    for event in events:
        live["cache"].update(event["vector_hashes"])
    with pytest.raises(ValueError, match="reservation"):
        prep.resume_remaining(manifest, inputs, live, events, settlement(events[0]))


def test_distinct_reservations_and_bound_settlements_certify_two_whole_batches(tmp_path):
    original, manifest, inputs, batches = frozen(tmp_path)
    events = [checkpoint(manifest, batch, "fictional-reservation-" + str(index))
              for index, batch in enumerate(batches)]
    live, ledgers = deepcopy(original), {}
    for event in events:
        live["cache"].update(event["vector_hashes"])
        ledgers.update(settlement(event))
    assert prep.resume_remaining(manifest, inputs, live, events, ledgers) == []


@pytest.mark.parametrize("field", ["schema", "plan_sha256", "batch_id", "request_sha256",
                                  "response_sha256", "model", "dimensions"])
@pytest.mark.parametrize("mutation", ["missing", "different"])
def test_actual_ledger_requires_each_request_response_binding(tmp_path, field, mutation):
    original, manifest, inputs, batches = frozen(tmp_path)
    event = checkpoint(manifest, batches[0])
    live = deepcopy(original)
    live["cache"].update(event["vector_hashes"])
    ledgers = settlement(event)
    binding = ledgers[event["reservation_id"]]["usage"]["embedding_backfill"]
    if mutation == "missing":
        binding.pop(field)
    else:
        binding[field] = "different"
    with pytest.raises(ValueError, match="settled request"):
        prep.resume_remaining(manifest, inputs, live, [event], ledgers)


@pytest.mark.parametrize("field,value", [("reservation_id", "other-reservation"), ("usage", {}),
                                       ("actual_usd", "NaN"), ("actual_usd", "-0.01")])
def test_mismatched_ledger_identity_or_invalid_actual_cost_is_rejected(tmp_path, field, value):
    original, manifest, inputs, batches = frozen(tmp_path)
    event = checkpoint(manifest, batches[0])
    live = deepcopy(original)
    live["cache"].update(event["vector_hashes"])
    ledgers = settlement(event)
    ledgers[event["reservation_id"]][field] = value
    with pytest.raises(ValueError):
        prep.resume_remaining(manifest, inputs, live, [event], ledgers)


@pytest.mark.parametrize("status", ["pending", "uncertain"])
def test_unknown_paid_attempt_is_never_automatically_resent(tmp_path, status):
    original, manifest, inputs, _ = frozen(tmp_path)
    with pytest.raises(ValueError, match="do not resend"):
        prep.resume_remaining(manifest, inputs, original, [{"state": status}], {})


@pytest.mark.parametrize("field,value", [("state", "done"), ("plan_sha256", "changed"), ("dimensions", 768),
                                       ("request_sha256", "wrong"), ("response_sha256", "missing"), ("model", "other")])
def test_unbound_success_flag_does_not_certify_vectors(tmp_path, field, value):
    original, manifest, inputs, batches = frozen(tmp_path)
    event = checkpoint(manifest, batches[0])
    live = deepcopy(original)
    live["cache"].update(event["vector_hashes"])
    event[field] = value
    with pytest.raises(ValueError):
        prep.resume_remaining(manifest, inputs, live, [event], settlement(event))


def test_resume_requires_actual_settlement_and_rejects_unaccounted_cache(tmp_path):
    original, manifest, inputs, batches = frozen(tmp_path)
    event = checkpoint(manifest, batches[0])
    live = deepcopy(original)
    live["cache"].update(event["vector_hashes"])
    with pytest.raises(ValueError):
        prep.resume_remaining(manifest, inputs, live, [event], {})
    with pytest.raises(ValueError, match="Unaccounted"):
        prep.resume_remaining(manifest, inputs, live, [], {})


def test_read_only_connection_rejects_remote_and_enforces_server_setting(monkeypatch):
    import psycopg

    calls = []
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: calls.append(kwargs) or "fictional-connection")
    assert prep.ReadOnlyDb("postgresql://localhost/fictional").connect() == "fictional-connection"
    assert calls[0]["options"] == "-c default_transaction_read_only=on"
    with pytest.raises(ValueError, match="loopback"):
        prep.ReadOnlyDb("postgresql://example.invalid/fictional").connect()
    with pytest.raises(ValueError, match="hostaddr"):
        prep.ReadOnlyDb("host=localhost hostaddr=192.0.2.5 dbname=fictional").connect()
    assert len(calls) == 1


def test_cli_private_text_destination_cannot_be_a_tracked_source_directory():
    with pytest.raises(ValueError, match="Private artifacts"):
        prep.private_directory(prep.ROOT / "docs" / "fictional-private-text")
