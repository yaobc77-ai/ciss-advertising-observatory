"""Independent fresh audit probes, entirely synthetic and unpaid."""

from copy import deepcopy

import pytest

from observatory.question_policy import (
    literal_scope_preserved,
    statistics_request_preserves_question,
)
from scripts import prepare_embedding_backfill as prep


def frozen_fixture(tmp_path):
    rows = []
    for i, text in enumerate(("Moss Lantern cooperative keeps exact bytes ♨️.", "Cedar Quay guild preserves another interval.")):
        rows.append({"chunk_id": f"new-{i}", "record_id": f"native:independent-{i}", "dataset": "native",
            "version_id": prep.sha(f"version-{i}"), "body_hash": prep.sha(text),
            "start_char": 0, "end_char": len(text), "text": text, "text_hash": prep.sha(text),
            "token_count": prep._tokens(text), "source_observation_id": None,
            "source_version_id": None, "source_body_hash": None})
    definition = {"embedding_model": prep.MODEL, "embedding_input": prep.INPUT_STRATEGY}
    state = {"model": prep.MODEL, "snapshot": {"chunks": 2, "active_profile": "new-fixture"},
        "profile": {"definition": definition, "definition_hash": prep.sha(prep.canonical(definition))},
        "code_sha256": {"fictional": "frozen"}, "cache": {},
        "tables": {table: {"rows": 2, "fingerprint": "frozen"} for table in prep.STATE_TABLES}}
    manifest, inputs, batches = prep.prepare(state, rows, batch_size=1)
    manifest = prep.write_bundle(tmp_path / "fixture", manifest, inputs, batches)
    return manifest, inputs, batches, state


def event_and_ledger(manifest, batch, reservation):
    event = {"state": "settled_cached", "plan_sha256": manifest["plan_sha256"], "model": prep.MODEL,
        "dimensions": 1536, "reservation_id": reservation, "response_sha256": "b" * 64,
        "batch_id": batch["batch_id"], "request_sha256": batch["request_sha256"],
        "vector_hashes": {key: "a" * 32 for key in batch["text_hashes"]}}
    ledger = {"state": "settled", "kind": "embedding", "reservation_id": reservation,
        "model": prep.MODEL, "actual_usd": "0.000001", "usage": {"embedding_backfill": {
            "schema": prep.SETTLEMENT_SCHEMA,
            **{key: event[key] for key in prep.SETTLEMENT_FIELDS}}}}
    return event, ledger


@pytest.mark.parametrize("kind", ["done", "settled_cached_without_live_cache", "pending", "uncertain"])
def test_local_completion_cannot_remove_an_unstored_input(tmp_path, kind):
    manifest, inputs, batches, live = frozen_fixture(tmp_path)
    event, ledger = event_and_ledger(manifest, batches[0], "new-reservation-a")
    if kind != "settled_cached_without_live_cache":
        event["state"] = kind
    with pytest.raises(ValueError):
        prep.resume_remaining(manifest, inputs, live, [event], {"new-reservation-a": ledger})


def test_distinct_paid_settlements_and_actual_live_cache_resume_only_remaining(tmp_path):
    manifest, inputs, batches, live = frozen_fixture(tmp_path)
    event, ledger = event_and_ledger(manifest, batches[0], "new-reservation-a")
    live = deepcopy(live)
    live["cache"].update(event["vector_hashes"])
    assert prep.resume_remaining(manifest, inputs, live, [event], {"new-reservation-a": ledger}) == batches[1]["text_hashes"]


def test_one_paid_settlement_must_not_certify_two_distinct_request_batches(tmp_path):
    manifest, inputs, batches, live = frozen_fixture(tmp_path)
    events = [event_and_ledger(manifest, batch, "reused-reservation")[0] for batch in batches]
    ledger = event_and_ledger(manifest, batches[0], "reused-reservation")[1]
    live = deepcopy(live)
    for event in events:
        live["cache"].update(event["vector_hashes"])
    with pytest.raises(ValueError):
        prep.resume_remaining(manifest, inputs, live, events, {"reused-reservation": ledger})


@pytest.mark.parametrize("phrase", ["last year", "this month", "past 4 weeks", "yesterday", "今年", "本季度"])
def test_new_relative_guard_blocks_unresolved_calendar(phrase):
    company = "Moss Lantern Guild"
    context = {"sponsors": [company]}
    filters = {"sponsors": [company]}
    question = f"How many native ads sponsored by {company} {phrase}?"
    assert not literal_scope_preserved(question, context, filters, {"dataset": "native"})
    assert not statistics_request_preserves_question(question, context, {"filters": filters}, {"dataset": "native"})


@pytest.mark.parametrize("phrase", ["last calendar year", "past two years", "上一年", "近两年"])
def test_additional_unresolved_relative_periods_cannot_become_all_time(phrase):
    company = "Moss Lantern Guild"
    context = {"sponsors": [company]}
    filters = {"sponsors": [company]}
    assert not statistics_request_preserves_question(
        f"Count native ads sponsored by {company} {phrase}", context,
        {"filters": filters}, {"dataset": "native"})


def test_relative_term_in_exact_company_name_is_not_a_date():
    company = "This Year Lantern Guild"
    context = {"sponsors": [company]}
    assert statistics_request_preserves_question(f"Count native ads sponsored by {company}", context,
        {"filters": {"sponsors": [company]}}, {"dataset": "native"})


def test_explicit_year_remains_supported_after_guard_change():
    company = "Moss Lantern Guild"
    context = {"sponsors": [company]}
    assert statistics_request_preserves_question(f"Count native ads sponsored by {company} in 2057", context,
        {"filters": {"sponsors": [company], "date_from": "2057-01-01", "date_to": "2057-12-31"}},
        {"dataset": "native"})
