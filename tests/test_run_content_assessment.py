"""Synthetic local pilot planning/checkpoint tests, with no API or database."""

import importlib.util
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_prepare_content_assessment import (
    definitions,
    lines,
    read,
    record,
    replace,
    response,
)
from test_prepare_content_assessment import (
    inputs as source_inputs,
)

from observatory.budget import LimitReached

inputs = source_inputs

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location("run_content_assessment", Path(__file__).parents[1] / "scripts/run_content_assessment.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


@pytest.fixture(autouse=True)
def no_real_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "EXECUTION_REGISTRY", tmp_path / "registry")

    def forbidden():
        pytest.fail("This synthetic test must not load credentials or construct real dependencies")

    monkeypatch.setattr(cli, "_live_dependencies", forbidden)


@pytest.fixture
def prepared(inputs):
    cli.preparation.prepare(inputs.packet, inputs.prepared)
    inputs.plan = inputs.root / "pilot"
    inputs.run = inputs.root / "run"
    return inputs


def make_plan(prepared, ids=None, **kwargs):
    return cli.write_plan(prepared.packet, prepared.prepared, prepared.plan,
                          ["ordinary", "no-keywords"] if ids is None else ids,
                          max_usd=kwargs.pop("max_usd", "1"), **kwargs)


class FakeBudget:
    def __init__(self, *, reserve_error=None, settle_error=None, uncertain_error=None):
        self.reserved, self.settled, self.uncertain_calls = [], [], []
        self.reserve_error, self.settle_error, self.uncertain_error = reserve_error, settle_error, uncertain_error

    def reserve(self, amount, visitor, kind, model):
        if self.reserve_error:
            raise self.reserve_error
        rid = f"reservation-{len(self.reserved) + 1}"
        self.reserved.append((rid, amount, visitor, kind, model))
        return rid

    def settle(self, rid, actual, usage):
        if self.settle_error:
            raise self.settle_error
        self.settled.append((rid, actual, deepcopy(usage)))

    def uncertain(self, rid, reason):
        self.uncertain_calls.append((rid, reason))
        if self.uncertain_error:
            raise self.uncertain_error

    def cancel_unsent(self, *_args):
        pytest.fail("A dispatched pilot must not cancel unknown exposure")


def provider_response(request, *, status="completed", text=None):
    return {"id": "synthetic-response", "model": cli.provider.MODEL, "status": status,
            "usage": {"input_tokens": 120, "output_tokens": 40,
                      "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 4}},
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": json.dumps(response(request)) if text is None else text}]}]}


def harness(prepared, *, outcomes=None, budget=None, on_create=None):
    calls = []
    wrappers = {row["request"]["record_id"]: row for row in lines(prepared.prepared, "requests.jsonl")}
    selected = read(prepared.plan, "plan.json")["selected_record_ids"]

    def create(**kwargs):
        if on_create:
            on_create(len(calls), kwargs)
        request = wrappers[selected[len(calls)]]["request"]
        outcome = provider_response(request) if outcomes is None else outcomes[len(calls)]
        calls.append(deepcopy(kwargs))
        if isinstance(outcome, Exception):
            raise outcome
        return deepcopy(outcome)

    client = SimpleNamespace(max_retries=0, responses=SimpleNamespace(create=create))
    return client, budget or FakeBudget(), calls


def execute(prepared, client, budget, *, output=None):
    sha = read(prepared.plan, "plan_summary.json")["plan_sha256"]
    return cli.execute(prepared.packet, prepared.prepared, prepared.plan, output or prepared.run,
                       approved_plan_sha256=sha, client=client, budget=budget)


def rehash_plan(prepared, value):
    replace(prepared.plan, "plan.json", value, map_name="artifacts")
    # The plan uses size+sha declarations rather than the older string maps.
    manifest = read(prepared.plan, "manifest.json")
    data = (prepared.plan / "plan.json").read_bytes()
    manifest["artifacts"]["plan.json"] = {"sha256": cli.preparation.original.digest(data), "size": len(data)}
    manifest["plan_sha256"] = cli.preparation.original.digest(data)
    (prepared.plan / "manifest.json").write_bytes(cli.encoded(manifest))


def assert_unknown(row):
    assert len(row["assessment"]["judgments"]) == 24
    assert all(j["membership"] == "unknown" and j["article_membership"] == "uncertain"
               for j in row["assessment"]["judgments"])
    assert row["assessment"]["publication_status"] == "hold"
    assert row["assessment"]["source_completeness"] == "unknown"


def test_pure_plan_does_not_load_environment_construct_dependencies_or_make_calls(prepared, monkeypatch):
    monkeypatch.setattr(cli.provider, "execute_provider_call", lambda *_a, **_k: pytest.fail("No call in plan"))
    result = cli.plan(prepared.packet, prepared.prepared, ["no-keywords"], max_usd="0.10")
    assert result["model_calls"] == result["accounting_operations"] == 0
    assert result["status"] == "pending_authorization" and result["publication_status"] == "hold"
    assert result["human_authorization_recorded"] is False
    assert result["selected_record_ids"] == ["no-keywords"]
    assert result["scope_records"] == 4 and result["judgment_slots"] == 96
    assert not cli.EXECUTION_REGISTRY.exists()
    assert not prepared.plan.exists()


def test_written_plan_freezes_all_requests_sources_calls_prices_and_hold(prepared):
    before = {p.relative_to(prepared.packet): p.read_bytes() for p in prepared.packet.rglob("*") if p.is_file()}
    summary = make_plan(prepared)
    planned = read(prepared.plan, "plan.json")
    assert planned["requests"] == lines(prepared.prepared, "requests.jsonl")
    assert planned["max_calls"] == len(planned["selected_calls"]) == 2
    assert planned["max_output_tokens"] == 6000
    assert planned["price_reference"]["verified_on"] == "2026-10-06"
    assert planned["price_reference"]["usd_per_million_tokens"] == {
        "input": "0.20", "cached_input": "0.02", "cache_write": "0.25", "output": "1.20"}
    for row in planned["selected_calls"]:
        request = next(w["request"] for w in planned["requests"] if w["request_id"] == row["request_id"])
        assert row["call_spec"] == cli.provider.build_provider_call(request)
        assert "tools" not in row["call_spec"]["kwargs"]
    assert Decimal(planned["total_reserved_usd"]) == sum(Decimal(c["call_spec"]["reserved_usd"]) for c in planned["selected_calls"])
    assert summary["plan_sha256"] == cli.preparation.original.digest((prepared.plan / "plan.json").read_bytes())
    assert cli.load_plan(prepared.packet, prepared.prepared, prepared.plan)["plan"] == planned
    assert planned["code_fingerprints"]["sdk"]["openai_version"]
    assert len(planned["code_fingerprints"]["sdk"]["openai_responses_sha256"]) == 64
    assert all(p.read_bytes() == before[p.relative_to(prepared.packet)] for p in prepared.packet.rglob("*") if p.is_file())
    assert not cli.EXECUTION_REGISTRY.exists()
    assert not (prepared.plan / ".execution_started.json").exists()


def test_pure_plan_is_deterministic_and_written_new_plans_require_new_hash(prepared):
    args = (prepared.packet, prepared.prepared, ["ordinary"])
    assert cli.plan(*args, max_usd="1") == cli.plan(*args, max_usd="1")
    one = make_plan(prepared, ["ordinary"])
    other = prepared.root / "another-plan"
    two = cli.write_plan(prepared.packet, prepared.prepared, other, ["ordinary"], max_usd="1")
    assert one["plan_sha256"] != two["plan_sha256"]
    assert read(prepared.plan, "plan.json")["plan_id"] != read(other, "plan.json")["plan_id"]


@pytest.mark.parametrize("amount", ["NaN", "sNaN", "Infinity", "-Infinity", "0", "-1", "", "not money", True, False, 1, 0.1, None])
def test_plan_rejects_nonfinite_nonpositive_or_inexact_cap(prepared, amount):
    with pytest.raises(ValueError):
        cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd=amount)
    assert not prepared.plan.exists() and not cli.EXECUTION_REGISTRY.exists()


def test_cap_equal_to_total_reservation_is_valid(prepared):
    original = cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd="1")
    cap = original["total_reserved_usd"]
    assert cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd=cap)["max_usd"] == cap
    with pytest.raises(ValueError, match="cap_below"):
        cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd=str(Decimal(cap) / 2))


@pytest.mark.parametrize("selection", [[], ["ordinary", "ordinary"], ["missing"], ["empty"], ["video"], ["excluded"], ["inactive"], ["social"], [None], "ordinary"])
def test_plan_rejects_nonready_unknown_duplicate_or_implicit_selection(prepared, selection):
    with pytest.raises(ValueError):
        cli.plan(prepared.packet, prepared.prepared, selection, max_usd="1")


def test_thirty_one_calls_are_rejected_without_model_or_registry(tmp_path):
    q, s = tmp_path / "q.json", tmp_path / "s.json"
    q.write_bytes(cli.preparation.original.encoded(definitions()))
    ids = [f"r{i}" for i in range(31)]
    s.write_bytes(cli.preparation.original.encoded([record(rid) for rid in ids]))
    packet, prepared = tmp_path / "packet", tmp_path / "prepared"
    cli.preparation.original.prepare(s, q, packet)
    cli.preparation.prepare(packet, prepared)
    with pytest.raises(ValueError, match="maximum_30"):
        cli.plan(packet, prepared, ids, max_usd="10")


@pytest.mark.parametrize("output_cap", [True, 0, 999, 16001, "6000", None])
def test_plan_rejects_invalid_provider_output_cap(prepared, output_cap):
    with pytest.raises(ValueError):
        cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd="1", max_output_tokens=output_cap)


def test_model_and_local_rates_must_match_verified_configuration(prepared, monkeypatch):
    with pytest.raises(ValueError, match="model"):
        cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd="1", model="different")
    monkeypatch.setattr(cli.accounting, "price", lambda *_a, **_k: Decimal("999"))
    with pytest.raises(ValueError, match="rate_configuration"):
        cli.plan(prepared.packet, prepared.prepared, ["ordinary"], max_usd="1")


@pytest.mark.parametrize("where", ["existing", "source", "prepared"])
def test_new_plan_output_is_exclusive_and_outside_inputs(prepared, where):
    output = prepared.plan
    if where == "existing":
        output.mkdir()
    elif where == "source":
        output = prepared.packet / "nested"
    else:
        output = prepared.prepared / "nested"
    with pytest.raises(ValueError):
        cli.write_plan(prepared.packet, prepared.prepared, output, ["ordinary"], max_usd="1")


@pytest.mark.parametrize("field,value", [
    ("model", "different"), ("max_calls", 1), ("max_usd", "NaN"), ("judgment_slots", 24),
    ("scope_records", 1), ("publication_status", "published"), ("status", "approved"),
    ("customer_approved", True), ("semantic_gold", True), ("quality_scores", {"f1": 1}),
    ("plan_id", None), ("plan_id", "bad"),
])
def test_plan_rebuild_rejects_rehashed_scope_policy_or_approval_drift(prepared, field, value):
    make_plan(prepared)
    changed = read(prepared.plan, "plan.json")
    changed[field] = value
    rehash_plan(prepared, changed)
    with pytest.raises(ValueError):
        cli.load_plan(prepared.packet, prepared.prepared, prepared.plan)


def test_plan_rebuild_rejects_rehashed_callspec_full_requests_and_code_drift(prepared):
    make_plan(prepared)
    changed = read(prepared.plan, "plan.json")
    changed["selected_calls"][0]["call_spec"]["kwargs"]["store"] = True
    rehash_plan(prepared, changed)
    with pytest.raises(ValueError, match="rebuilt"):
        cli.load_plan(prepared.packet, prepared.prepared, prepared.plan)


@pytest.mark.parametrize("mutation", ["drop-request", "code", "sdk", "frozen-input", "size", "unsafe", "extra", "missing", "hash"])
def test_packet_artifacts_and_full_request_bindings_cannot_drift(prepared, mutation):
    make_plan(prepared)
    if mutation in {"drop-request", "code", "sdk"}:
        changed = read(prepared.plan, "plan.json")
        if mutation == "drop-request":
            changed["requests"].pop()
        elif mutation == "code":
            changed["code_fingerprints"]["runner_sha256"] = "0" * 64
        else:
            changed["code_fingerprints"]["sdk"]["openai_version"] = "stale"
        rehash_plan(prepared, changed)
    elif mutation == "frozen-input":
        (prepared.plan / "inputs/question_definitions.json").write_text("{}")
    else:
        manifest = read(prepared.plan, "manifest.json")
        if mutation == "size":
            manifest["artifacts"]["plan.json"]["size"] += 1
        elif mutation == "unsafe":
            manifest["artifacts"]["../outside"] = manifest["artifacts"].pop("README.md")
        elif mutation == "extra":
            manifest["artifacts"]["extra.json"] = {"sha256": "0" * 64, "size": 0}
        elif mutation == "missing":
            del manifest["artifacts"]["plan.json"]
        else:
            manifest["artifacts"]["plan.json"]["sha256"] = "0" * 64
        (prepared.plan / "manifest.json").write_bytes(cli.encoded(manifest))
    with pytest.raises(ValueError):
        cli.load_plan(prepared.packet, prepared.prepared, prepared.plan)


@pytest.mark.parametrize("root_name", ["packet", "prepared"])
def test_source_and_prepared_change_before_execution_is_blocked_before_dependencies(prepared, root_name):
    make_plan(prepared)
    root = getattr(prepared, root_name)
    name = "source_snapshot.json" if root_name == "packet" else "requests.jsonl"
    (root / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run,
                    approved_plan_sha256=read(prepared.plan, "plan_summary.json")["plan_sha256"])
    assert not prepared.run.exists() and not cli.EXECUTION_REGISTRY.exists()


@pytest.mark.parametrize("approval", [None, "", "0" * 64, "A" * 64, 1])
def test_unapproved_execution_cannot_construct_dependencies_or_consume_plan(prepared, approval):
    make_plan(prepared)
    with pytest.raises(ValueError, match="approved_plan"):
        cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run,
                    approved_plan_sha256=approval)
    assert not prepared.run.exists() and not cli.EXECUTION_REGISTRY.exists()


def test_injected_contract_is_validated_before_single_use_marker(prepared):
    make_plan(prepared)
    sha = read(prepared.plan, "plan_summary.json")["plan_sha256"]
    with pytest.raises(ValueError, match="together"):
        cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run,
                    approved_plan_sha256=sha, client=object())
    with pytest.raises(ValueError, match="synchronous"):
        cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run,
                    approved_plan_sha256=sha, client=object(), budget=object())
    assert not cli.EXECUTION_REGISTRY.exists()
    assert not prepared.run.exists()


@pytest.mark.parametrize("mode", ["bool-retries", "async-create", "async-reserve", "async-settle", "async-uncertain", "getter-error"])
def test_injected_invalid_async_retry_and_getter_contracts_do_not_consume_plan(prepared, mode):
    make_plan(prepared)
    client, budget, calls = harness(prepared)

    async def asynchronous(*_args, **_kwargs):
        pass

    if mode == "bool-retries":
        client.max_retries = False
    elif mode == "async-create":
        client.responses.create = asynchronous
    elif mode.startswith("async-"):
        setattr(budget, mode.removeprefix("async-"), asynchronous)
    else:
        class BrokenClient:
            @property
            def responses(self):
                raise ValueError("PRIVATE dependency contents")

        client = BrokenClient()
    with pytest.raises(ValueError):
        execute(prepared, client, budget)
    assert not calls and not budget.reserved
    assert not prepared.run.exists() and not cli.EXECUTION_REGISTRY.exists()


def test_execution_preserves_complete_scope_and_checkpoint_precedes_next_dispatch(prepared, monkeypatch):
    make_plan(prepared)
    events = []
    original_write = cli._write

    def checked_write(root, name, data, artifacts):
        original_write(root, name, data, artifacts)
        events.append(name)

    monkeypatch.setattr(cli, "_write", checked_write)

    def check_before_create(number, kwargs):
        assert "started.json" in events
        assert (prepared.plan / ".execution_started.json").exists()
        if number:
            assert "private/responses/001.json" in events
            assert "checkpoints/001.json" in events
            assert read(prepared.run, "checkpoints/001.json")["private_response"]["sha256"]
        assert kwargs["reasoning"] == {"effort": "none"}
        assert kwargs["truncation"] == "disabled" and kwargs["store"] is False

    client, budget, calls = harness(prepared, on_create=check_before_create)
    summary = execute(prepared, client, budget)
    assert len(calls) == len(budget.reserved) == len(budget.settled) == 2
    assert len({row[2] for row in budget.reserved}) == 1
    assert all(row[3:] == ("generation", cli.provider.MODEL) for row in budget.reserved)
    results = lines(prepared.run, "results.jsonl")
    assert len(results) == 4 and summary["judgment_slots"] == 96
    assert summary["status"] == "completed_draft" and summary["execution_mode"] == "injected_test"
    assert summary["processing_status_counts"] == {"processed": 2, "not_requested": 2}
    assert summary["ledger_complete"] is True
    assert Decimal(summary["cost_usd"]) == sum(row[1] for row in budget.settled)
    assert summary["quality_scores"] is None and not summary["semantic_gold"] and not summary["customer_approved"]
    assert summary["source_database_writes"] == summary["publications"] == summary["source_adoptions"] == 0
    for row in results:
        assert row["assessment"]["review_required"] and row["assessment"]["publication_status"] == "hold"
        assert len(row["assessment"]["judgments"]) == 24
        assert "provider_response_private" not in row
    for name, declaration in read(prepared.run, "manifest.json")["artifacts"].items():
        data = (prepared.run / name).read_bytes()
        assert len(data) == declaration["size"] and cli.preparation.original.digest(data) == declaration["sha256"]


def test_one_selected_record_keeps_unselected_ready_and_missing_records_unknown(prepared):
    make_plan(prepared, ["ordinary"])
    client, budget, _ = harness(prepared)
    summary = execute(prepared, client, budget)
    results = lines(prepared.run, "results.jsonl")
    assert summary["scope_records"] == 4 and summary["judgment_slots"] == 96
    assert summary["processing_status_counts"] == {"processed": 1, "not_selected": 1, "not_requested": 2}
    for row in results:
        if row["record_id"] != "ordinary":
            assert_unknown(row)


@pytest.mark.parametrize("mode", ["timeout", "usage", "model", "bound", "incomplete", "refusal", "malformed", "invalid-assessment"])
def test_failed_first_call_stops_next_and_preserves_unknowns_cost_and_full_denominator(prepared, mode):
    make_plan(prepared)
    request = next(w["request"] for w in lines(prepared.prepared, "requests.jsonl") if w["request"]["record_id"] == "ordinary")
    outcome = provider_response(request)
    if mode == "timeout":
        outcome = TimeoutError("PRIVATE TRANSPORT DETAIL")
    elif mode == "usage":
        del outcome["usage"]
    elif mode == "model":
        outcome["model"] = "unpriced-model"
    elif mode == "bound":
        outcome["usage"]["output_tokens"] = 6001
    elif mode == "incomplete":
        outcome["status"] = "incomplete"
        outcome["incomplete_details"] = {"reason": "max_output_tokens"}
    elif mode == "refusal":
        outcome["output"][0]["content"] = [{"type": "refusal", "refusal": "PRIVATE REFUSAL DETAIL"}]
    elif mode == "malformed":
        outcome["output"][0]["content"][0]["text"] = "PRIVATE malformed output"
    else:
        outcome["output"][0]["content"][0]["text"] = '{"judgments": []}'
    client, budget, calls = harness(prepared, outcomes=[outcome])
    summary = execute(prepared, client, budget)
    assert len(calls) == len(budget.reserved) == 1
    assert summary["status"] == "stopped" and summary["scope_records"] == 4 and summary["judgment_slots"] == 96
    assert summary["judgment_membership_counts"] == {"unknown": 96}
    for row in lines(prepared.run, "results.jsonl"):
        assert_unknown(row)
    not_run = next(r for r in lines(prepared.run, "results.jsonl") if r["record_id"] == "no-keywords")
    assert not_run["processing_status"] == "not_executed_after_stop"
    if mode in {"timeout", "usage", "model"}:
        assert summary["cost_usd"] is None and summary["known_settled_cost_usd"] == "0"
        assert summary["ledger_complete"] is False
        assert summary["uncertain_calls"] == 1 and budget.uncertain_calls
    else:
        assert summary["cost_usd"] is not None and summary["ledger_complete"] is True
        assert len(budget.settled) == 1 and not budget.uncertain_calls
    assert "PRIVATE" not in (prepared.run / "coverage_summary.json").read_text()
    assert "PRIVATE" not in (prepared.run / "aggregate_audit.json").read_text()
    assert "PRIVATE" not in (prepared.run / "results.jsonl").read_text()


@pytest.mark.parametrize("mode", ["reserve-limit", "reserve-error", "settle-error", "uncertain-error"])
def test_budget_failures_stop_and_unknown_cost_is_not_reported_zero(prepared, mode):
    make_plan(prepared)
    options = {}
    outcomes = None
    if mode == "reserve-limit":
        options["reserve_error"] = LimitReached("PRIVATE")
    elif mode == "reserve-error":
        options["reserve_error"] = RuntimeError("PRIVATE")
    elif mode == "settle-error":
        options["settle_error"] = RuntimeError("PRIVATE")
    else:
        options["uncertain_error"] = RuntimeError("PRIVATE")
        outcomes = [TimeoutError("PRIVATE")]
    budget = FakeBudget(**options)
    client, budget, calls = harness(prepared, outcomes=outcomes, budget=budget)
    summary = execute(prepared, client, budget)
    assert len(calls) == (0 if mode.startswith("reserve") else 1)
    assert summary["status"] == "stopped" and summary["judgment_membership_counts"] == {"unknown": 96}
    if mode in {"settle-error", "uncertain-error"}:
        assert summary["cost_usd"] is None and not summary["ledger_complete"]


def test_partial_known_cost_and_unknown_second_call_are_distinct(prepared):
    make_plan(prepared)
    request = next(w["request"] for w in lines(prepared.prepared, "requests.jsonl") if w["request"]["record_id"] == "ordinary")
    client, budget, calls = harness(prepared, outcomes=[provider_response(request), TimeoutError("PRIVATE")])
    summary = execute(prepared, client, budget)
    assert len(calls) == 2 and len(budget.settled) == 1
    assert summary["cost_usd"] is None and summary["ledger_complete"] is False
    assert Decimal(summary["known_settled_cost_usd"]) == budget.settled[0][1]
    assert Decimal(summary["exposure_usd"]) > Decimal(summary["known_settled_cost_usd"])


def test_invalid_returned_binding_retains_full_private_failure_and_known_settled_cost(prepared, monkeypatch):
    make_plan(prepared)
    original_execute = cli.provider.execute_provider_call

    def invalid_result(*args, **kwargs):
        value = original_execute(*args, **kwargs)
        value["version_id"] = "PRIVATE WRONG BINDING"
        return value

    monkeypatch.setattr(cli.provider, "execute_provider_call", invalid_result)
    client, budget, calls = harness(prepared)
    summary = execute(prepared, client, budget)
    assert len(calls) == len(budget.settled) == 1
    assert summary["stop_reason"] == "provider_adapter_failure"
    assert summary["ledger_complete"] is True and Decimal(summary["cost_usd"]) == budget.settled[0][1]
    failure = read(prepared.run, "private/failures/001.json")
    assert failure["version_id"] == "PRIVATE WRONG BINDING"
    assert failure["provider_call"]["reservation_id"] == budget.settled[0][0]
    assert failure["provider_call"]["usage"] and failure["provider_response_private"]
    assert "PRIVATE WRONG" not in (prepared.run / "results.jsonl").read_text()
    assert all(j["membership"] == "unknown" for r in lines(prepared.run, "results.jsonl") for j in r["assessment"]["judgments"])


def test_unexpected_adapter_raise_is_private_sanitized_and_preserves_exposure(prepared, monkeypatch):
    make_plan(prepared)
    monkeypatch.setattr(cli.provider, "execute_provider_call", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("PRIVATE")))
    client, budget, calls = harness(prepared)
    summary = execute(prepared, client, budget)
    assert not calls and not budget.reserved
    assert summary["cost_usd"] is None and summary["unknown_dispatch_attempts"] == 1
    assert Decimal(summary["exposure_usd"]) > 0
    assert "PRIVATE" not in (prepared.run / "results.jsonl").read_text()


def test_source_edit_after_first_call_stops_without_dropping_paid_record(prepared):
    make_plan(prepared)

    def edit_during_first(_number, _kwargs):
        (prepared.packet / "question_definitions.json").write_bytes(b"{}")

    client, budget, calls = harness(prepared, on_create=edit_during_first)
    summary = execute(prepared, client, budget)
    assert len(calls) == 1 and len(budget.settled) == 1
    assert summary["stop_reason"] == "run_binding_or_cap_changed"
    assert summary["scope_records"] == 4 and summary["processing_status_counts"]["not_executed_after_stop"] == 1


def test_checkpoint_failure_stops_and_started_scope_cannot_be_redispatched(prepared, monkeypatch):
    make_plan(prepared)
    original_write = cli._write

    def fail_checkpoint(root, name, data, artifacts):
        if name == "checkpoints/001.json":
            raise OSError("PRIVATE filesystem detail")
        original_write(root, name, data, artifacts)

    monkeypatch.setattr(cli, "_write", fail_checkpoint)
    client, budget, calls = harness(prepared)
    with pytest.raises(ValueError, match="checkpoint_failed_no_resume"):
        execute(prepared, client, budget)
    assert len(calls) == len(budget.settled) == 1
    assert read(prepared.run, "started.json")["judgment_slots"] == 96
    assert (prepared.run / "private/responses/001.json").exists()
    assert not (prepared.run / "manifest.json").exists()
    with pytest.raises(ValueError, match="already_consumed"):
        execute(prepared, client, budget, output=prepared.root / "do-not-resume")
    assert len(calls) == 1


def test_same_plan_hash_cannot_execute_twice_or_through_copied_plan_directory(prepared):
    make_plan(prepared, ["ordinary"])
    copied = prepared.root / "copied-plan"
    shutil.copytree(prepared.plan, copied)
    client, budget, calls = harness(prepared)
    execute(prepared, client, budget)
    with pytest.raises(ValueError, match="already_consumed"):
        execute(prepared, client, budget, output=prepared.root / "second-out")
    with pytest.raises(ValueError, match="already_consumed"):
        cli.execute(prepared.packet, prepared.prepared, copied, prepared.root / "copied-out",
                    approved_plan_sha256=read(copied, "plan_summary.json")["plan_sha256"], client=client, budget=budget)
    assert len(calls) == len(budget.reserved) == 1


def test_exclusive_marker_allows_only_one_of_two_competing_runs(prepared):
    make_plan(prepared, ["ordinary"])
    client, budget, calls = harness(prepared)

    def run(number):
        try:
            return execute(prepared, client, budget, output=prepared.root / f"competing-{number}")
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(run, [1, 2]))
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    assert "run_plan_already_consumed" in outcomes
    assert len(calls) == len(budget.reserved) == 1


def test_existing_output_does_not_load_dependencies_or_dispatch_again(prepared):
    make_plan(prepared)
    prepared.run.mkdir()
    sha = read(prepared.plan, "plan_summary.json")["plan_sha256"]
    with pytest.raises(ValueError, match="new_output"):
        cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run, approved_plan_sha256=sha)
    assert not cli.EXECUTION_REGISTRY.exists()


def test_bad_live_configuration_does_not_consume_plan_and_keeps_full_unknown_scope(prepared, monkeypatch):
    make_plan(prepared)

    def bad_configuration():
        raise ValueError("PRIVATE configuration contents")

    monkeypatch.setattr(cli, "_live_dependencies", bad_configuration)
    summary = cli.execute(prepared.packet, prepared.prepared, prepared.plan, prepared.run,
                          approved_plan_sha256=read(prepared.plan, "plan_summary.json")["plan_sha256"])
    assert summary["stop_reason"] == "runtime_dependencies_unavailable"
    assert summary["attempted_calls"] == 0 and summary["cost_usd"] == "0" and summary["ledger_complete"]
    assert summary["judgment_membership_counts"] == {"unknown": 96}
    assert not cli.EXECUTION_REGISTRY.exists()
    assert not (prepared.plan / ".execution_started.json").exists()
    assert "PRIVATE" not in (prepared.run / "coverage_summary.json").read_text()


def test_cli_plan_requires_cap_and_cli_execute_requires_hash_before_dependencies(prepared, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["plan", "--packet", str(prepared.packet), "--prepared", str(prepared.prepared),
                  "--out", str(prepared.plan), "--record-id", "ordinary"])
    assert error.value.code == 2 and not prepared.plan.exists()
    cli.main(["plan", "--packet", str(prepared.packet), "--prepared", str(prepared.prepared),
              "--out", str(prepared.plan), "--record-id", "ordinary", "--max-usd", "0.1"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["max_calls"] == 1 and printed["scope_records"] == 4
    with pytest.raises(SystemExit) as error:
        cli.main(["execute", "--packet", str(prepared.packet), "--prepared", str(prepared.prepared),
                  "--plan", str(prepared.plan), "--out", str(prepared.run), "--approved-plan-sha256", "0" * 64])
    assert error.value.code == 2
    assert not prepared.run.exists() and not cli.EXECUTION_REGISTRY.exists()


@pytest.mark.parametrize("error", [ValueError("PRIVATE Pydantic input; never print me"), OSError("PRIVATE path")])
def test_cli_does_not_echo_arbitrary_exception_contents(prepared, monkeypatch, capsys, error):
    def bad_plan(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(cli, "write_plan", bad_plan)
    with pytest.raises(SystemExit):
        cli.main(["plan", "--packet", str(prepared.packet), "--prepared", str(prepared.prepared),
                  "--out", str(prepared.plan), "--record-id", "ordinary", "--max-usd", "0.1"])
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.err and not captured.out
    assert type(error).__name__ in captured.err
