"""Injected transport/accounting tests; never connect to a model or database."""

import json
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_content_assessment import definitions, record
from test_content_assessment import response as assessment_response

from observatory.budget import LimitReached, price
from observatory.content_assessment import build_article_request
from observatory.content_provider import (
    MAX_VERIFIED_INPUT,
    build_provider_call,
    execute_provider_call,
)
from observatory.evaluate import canonical_digest


class FakeBudget:
    def __init__(self, events, *, reserve_error=None, settle_error=None, uncertain_error=None):
        self.events = events
        self.reserve_error, self.settle_error, self.uncertain_error = reserve_error, settle_error, uncertain_error
        self.reserved, self.settled, self.uncertain_calls = [], [], []

    def reserve(self, amount, visitor, kind, model):
        self.events.append("reserve")
        if self.reserve_error:
            raise self.reserve_error
        self.reserved.append(("reserved-1", amount, visitor, kind, model))
        return "reserved-1"

    def settle(self, rid, actual, usage):
        self.events.append("settle")
        if self.settle_error:
            raise self.settle_error
        self.settled.append((rid, actual, deepcopy(usage)))

    def uncertain(self, rid, error):
        self.events.append("uncertain")
        self.uncertain_calls.append((rid, error))
        if self.uncertain_error:
            raise self.uncertain_error

    def cancel_unsent(self, *_args):
        pytest.fail("An attempted call must never cancel its paid exposure")


class SDKObject(SimpleNamespace):
    def model_dump(self, **_kwargs):
        def plain(value):
            if isinstance(value, SDKObject):
                return {key: plain(item) for key, item in vars(value).items()}
            if isinstance(value, list):
                return [plain(item) for item in value]
            if isinstance(value, dict):
                return {key: plain(item) for key, item in value.items()}
            return value
        return plain(self)


def provider_response(request, *, status="completed", text=None):
    return {"id": "response-1", "model": "gpt-5.6-luna", "status": status,
            "usage": {"input_tokens": 120, "output_tokens": 40,
                      "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 4}},
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text",
                                     "text": json.dumps(assessment_response(request)) if text is None else text}]}]}


def harness(outcome=None, **budget_options):
    request = build_article_request(record(), definitions())
    call = build_provider_call(request)
    events, calls = [], []
    budget = FakeBudget(events, **budget_options)
    outcome = provider_response(request) if outcome is None else outcome

    def create(**kwargs):
        events.append("create")
        calls.append(deepcopy(kwargs))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = SimpleNamespace(max_retries=0, responses=SimpleNamespace(create=create))
    return request, call, client, budget, calls, events


def execute(bundle):
    request, call, client, budget, _, _ = bundle
    return execute_provider_call(request, call, client=client, budget=budget, visitor="offline-draft-test")


def assert_unknown(result, reason, *, state, dispatched):
    assert result["processing_status"] == reason
    assert result["provider_call"]["reason"] == reason
    assert result["provider_call"]["state"] == state
    assert result["provider_call"]["dispatched"] is dispatched
    assert len(result["assessment"]["judgments"]) == 24
    assert all(j["membership"] == "unknown" for j in result["assessment"]["judgments"])
    assert result["review_required"] is True and result["publication_status"] == "hold"
    assert result["assessment"]["publication_status"] == "hold"


def test_call_uses_strict_full_input_official_model_and_explicit_no_tools_no_retry_settings():
    request = build_article_request(record(raw={"secret": "PRIVATE_MARKER"},
                                           annotations=[{"label": "OLD_PREDICTION"}]), definitions())
    call = build_provider_call(request)
    kwargs = call["kwargs"]
    assert kwargs["model"] == "gpt-5.6-luna"
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["store"] is False and kwargs["truncation"] == "disabled"
    assert kwargs["service_tier"] == "default" and "tools" not in kwargs
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["schema"] == request["response_schema"]
    user = json.loads(kwargs["input"][1]["content"])
    assert user == request["model_input"]["data"]
    assert user["retained_article"]["body"] == request["record"]["body"]
    assert "PRIVATE_MARKER" not in json.dumps(kwargs) and "OLD_PREDICTION" not in json.dumps(kwargs)
    assert call == build_provider_call(request)
    assert call["call_sha256"] == canonical_digest(kwargs)
    assert Decimal(call["reserved_usd"]) == price("gpt-5.6-luna", call["upper_input_tokens"], 6000) * Decimal("1.25")


@pytest.mark.parametrize("options", [{"model": "other-model"}, {"model": "text-embedding-3-small"},
                                     {"max_output_tokens": True}, {"max_output_tokens": 999},
                                     {"max_output_tokens": 16001}, {"max_output_tokens": "6000"}])
def test_unverified_model_or_output_limit_refused_offline(options):
    request = build_article_request(record(), definitions())
    with pytest.raises(ValueError):
        build_provider_call(request, **options)


def test_unready_request_never_builds_provider_call():
    request = build_article_request(record("Video", retrievable=False), definitions())
    with pytest.raises(ValueError, match="ready"):
        build_provider_call(request)


def test_conservative_input_threshold_accepts_boundary_and_rejects_next_byte(monkeypatch):
    import observatory.content_provider as module
    request = build_article_request(record(), definitions())
    monkeypatch.setattr(module, "_serialize", lambda _v: "x" * (MAX_VERIFIED_INPUT - 4096))
    assert build_provider_call(request)["upper_input_tokens"] == MAX_VERIFIED_INPUT
    monkeypatch.setattr(module, "_serialize", lambda _v: "x" * (MAX_VERIFIED_INPUT - 4095))
    with pytest.raises(ValueError, match="pricing_bound"):
        build_provider_call(request)


def test_reserve_precedes_single_call_and_known_usage_is_settled_before_materialization():
    bundle = harness()
    result = execute(bundle)
    request, call, _, budget, calls, events = bundle
    assert events == ["reserve", "create", "settle"]
    assert len(calls) == 1 and calls[0] == call["kwargs"]
    assert budget.reserved[0][2:] == ("offline-draft-test", "generation", "gpt-5.6-luna")
    assert result["processing_status"] == "processed"
    assert result["provider_call"]["state"] == "settled"
    actual = price("gpt-5.6-luna", 120, 40, 20, 4)
    assert result["provider_call"]["cost_usd"] == str(actual)
    assert result["provider_call"]["exposure_usd"] == str(actual)
    assert result["provider_response_private"] == provider_response(request)
    assert budget.settled[0][2]["observatory_request"]["request_sha256"] == request["request_sha256"]
    assert result["assessment"]["status"] == "draft_ai_unreviewed"
    assert result["assessment"]["judgments"][5]["support_evidence"][0]["quote"] == "The company proposes CCS."


@pytest.mark.parametrize("exception,reason", [(LimitReached("PRIVATE_LIMIT"), "budget_limited"),
                                             (ConnectionError("PRIVATE_DATABASE"), "budget_unavailable")])
def test_budget_failure_dispatches_nothing_and_keeps_full_unknown_set(exception, reason):
    bundle = harness(reserve_error=exception)
    result = execute(bundle)
    assert_unknown(result, reason, state="none", dispatched=False)
    assert bundle[4] == [] and bundle[5] == ["reserve"]
    assert result["provider_call"]["exposure_usd"] == "0"
    assert "PRIVATE_" not in json.dumps(result)


@pytest.mark.parametrize("mutate", [
    lambda request, call: call.update(reserved_usd="0.00001"),
    lambda request, call: call["kwargs"].update(tools=[{"type": "web_search"}]),
    lambda request, call: call.update(call_sha256="wrong"),
    lambda request, call: request["record"].update(body="A changed body"),
    lambda request, call: request["definitions"]["questions"][0].update(definition_draft="Changed"),
    lambda request, call: request["model_input"]["data"].update(raw="PRIVATE_RAW_LEAK"),
])
def test_call_request_definition_or_price_drift_rejected_before_reserve(mutate):
    bundle = harness()
    mutate(bundle[0], bundle[1])
    with pytest.raises(ValueError):
        execute(bundle)
    assert bundle[4] == [] and bundle[5] == []


def test_client_without_create_or_with_sdk_retries_refused_before_reservation():
    for client in (SimpleNamespace(), SimpleNamespace(max_retries=2, responses=SimpleNamespace(create=lambda **_kwargs: None))):
        bundle = harness()
        with pytest.raises(ValueError):
            execute_provider_call(bundle[0], bundle[1], client=client, budget=bundle[3], visitor="test")
        assert bundle[3].reserved == []


@pytest.mark.parametrize("retries", [False, "0", None])
def test_retry_configuration_requires_explicit_integer_zero(retries):
    bundle = harness()
    bundle[2].max_retries = retries
    with pytest.raises(ValueError, match="provider_client_retries_must_be_disabled"):
        execute(bundle)
    assert bundle[4] == [] and bundle[5] == []


def test_failed_local_client_getter_is_redacted_before_reserve():
    class BrokenClient:
        @property
        def responses(self):
            raise RuntimeError("PRIVATE_API_KEY_CONFIG")

    bundle = harness()
    with pytest.raises(ValueError, match="provider_local_configuration_unavailable") as caught:
        execute_provider_call(bundle[0], bundle[1], client=BrokenClient(), budget=bundle[3], visitor="test")
    assert "PRIVATE_API_KEY_CONFIG" not in str(caught.value)
    assert bundle[4] == [] and bundle[5] == []


def test_async_budget_configuration_is_refused_before_reserve():
    async def reserve(*_args):
        pytest.fail("async reserve must never dispatch")

    bundle = harness()
    bundle[3].reserve = reserve
    with pytest.raises(ValueError, match="provider_budget_contract_required"):
        execute(bundle)
    assert bundle[4] == [] and bundle[5] == []


def test_timeout_keeps_reserved_exposure_without_retry_or_cancel():
    bundle = harness(TimeoutError("API_KEY_SECRET"))
    result = execute(bundle)
    assert_unknown(result, "provider_unavailable", state="uncertain", dispatched=True)
    assert bundle[5] == ["reserve", "create", "uncertain"] and len(bundle[4]) == 1
    assert result["provider_call"]["cost_usd"] is None
    assert result["provider_call"]["exposure_usd"] == bundle[1]["reserved_usd"]
    assert "API_KEY_SECRET" not in json.dumps(result)


def test_unreadable_response_metadata_keeps_unknown_reservation_without_error_text():
    class BrokenResponse:
        @property
        def id(self):
            raise RuntimeError("SECRET_TRANSPORT_METADATA")

        def model_dump(self, mode):
            return {"response_marker": "private-original"}

    bundle = harness(BrokenResponse())
    result = execute(bundle)
    assert_unknown(result, "provider_unavailable", state="uncertain", dispatched=True)
    assert bundle[5] == ["reserve", "create", "uncertain"]
    assert result["provider_response_private"] == {"response_marker": "private-original"}
    assert "SECRET_TRANSPORT_METADATA" not in json.dumps(result)


@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("usage"),
    lambda p: p["usage"].update(input_tokens=True),
    lambda p: p["usage"].update(output_tokens=-1),
    lambda p: p["usage"].update(input_tokens="120"),
    lambda p: p["usage"]["input_tokens_details"].update(cached_tokens=False),
    lambda p: p["usage"]["input_tokens_details"].update(cache_write_tokens=True),
    lambda p: p["usage"]["input_tokens_details"].update(cached_tokens=120),
])
def test_missing_invalid_or_coerced_usage_keeps_uncertain_exposure(mutate):
    base = harness()
    provider = provider_response(base[0])
    mutate(provider)
    bundle = harness(provider)
    result = execute(bundle)
    assert_unknown(result, "provider_usage_unavailable", state="uncertain", dispatched=True)
    assert bundle[3].settled == [] and len(bundle[4]) == 1
    assert result["provider_response_private"] == provider


@pytest.mark.parametrize("model", [None, "other-model", "gpt-5.6-luna-unverified-snapshot"])
def test_unverified_provider_model_is_not_priced_as_requested_model(model):
    base = harness()
    provider = provider_response(base[0])
    provider["model"] = model
    bundle = harness(provider)
    result = execute(bundle)
    assert_unknown(result, "model_mismatch", state="uncertain", dispatched=True)
    assert result["provider_call"]["usage"]["input_tokens"] == 120
    assert result["provider_call"]["cost_usd"] is None and bundle[3].settled == []


def test_settlement_and_uncertain_tracking_failures_do_not_release_exposure():
    bundle = harness(settle_error=RuntimeError("PRIVATE_LEDGER_FAILURE"),
                     uncertain_error=ConnectionError("PRIVATE_TRACKING_FAILURE"))
    result = execute(bundle)
    assert_unknown(result, "budget_settlement_unavailable", state="uncertain", dispatched=True)
    assert result["provider_call"]["cost_usd"] is None
    assert result["provider_call"]["usage"]["input_tokens"] == 120
    assert result["provider_call"]["uncertain_tracking_error_type"] == "ConnectionError"
    assert "PRIVATE_" not in json.dumps(result)


@pytest.mark.parametrize("failure,reason", [
    ("incomplete", "provider_incomplete"),
    ("refusal", "provider_refused"),
    ("partial_json", "provider_malformed_output"),
    ("duplicate_keys", "provider_malformed_output"),
    ("multiple_texts", "provider_malformed_output"),
    ("tool_call", "provider_malformed_output"),
    ("missing_question", "assessment_validation_failed"),
    ("fabricated_quote", "assessment_validation_failed"),
])
def test_known_paid_but_unusable_results_still_settle_full_usage(failure, reason):
    base = harness()
    provider = provider_response(base[0])
    content = provider["output"][0]["content"]
    if failure == "incomplete":
        provider["status"] = "incomplete"
    elif failure == "refusal":
        provider["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot answer"}]
    elif failure == "partial_json":
        content[0]["text"] = '{"judgments":['
    elif failure == "duplicate_keys":
        content[0]["text"] = '{"judgments": [], "judgments": []}'
    elif failure == "multiple_texts":
        content.append(deepcopy(content[0]))
    elif failure == "tool_call":
        provider["output"] = [{"type": "function_call", "name": "something"}]
    else:
        parsed = json.loads(content[0]["text"])
        if failure == "missing_question":
            parsed["judgments"].pop()
        else:
            parsed["judgments"][0]["quote"] = "Invented quote"
        content[0]["text"] = json.dumps(parsed)
    bundle = harness(provider)
    result = execute(bundle)
    assert_unknown(result, reason, state="settled", dispatched=True)
    assert len(bundle[3].settled) == 1 and bundle[3].uncertain_calls == []
    assert bundle[5] == ["reserve", "create", "settle"]
    assert result["provider_call"]["cost_usd"] == str(price("gpt-5.6-luna", 120, 40, 20, 4))


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_correct_model_bound_overrun_is_settled_but_not_processed(field):
    base = harness()
    provider = provider_response(base[0])
    provider["usage"][field] = base[1]["upper_input_tokens"] + 1 if field == "input_tokens" else 6001
    bundle = harness(provider)
    result = execute(bundle)
    assert_unknown(result, "accounting_bound_exceeded", state="settled", dispatched=True)
    actual = price("gpt-5.6-luna", provider["usage"]["input_tokens"], provider["usage"]["output_tokens"], 20, 4)
    assert result["provider_call"]["cost_usd"] == str(actual)
    assert bundle[3].settled[0][1] == actual


def test_actual_long_context_usage_is_not_underpriced_with_short_context_rates():
    base = harness()
    provider = provider_response(base[0])
    provider["usage"]["input_tokens"] = MAX_VERIFIED_INPUT + 1
    bundle = harness(provider)
    result = execute(bundle)
    assert_unknown(result, "pricing_bound_exceeded", state="uncertain", dispatched=True)
    assert result["provider_call"]["cost_usd"] is None and bundle[3].settled == []
    assert result["provider_call"]["usage"]["input_tokens"] == MAX_VERIFIED_INPUT + 1


def test_sdk_object_response_uses_same_materialization_and_private_dump():
    base = harness()
    data = provider_response(base[0])
    sdk = SDKObject(**data)
    sdk.usage = SDKObject(**data["usage"])
    sdk.usage.input_tokens_details = SDKObject(**data["usage"]["input_tokens_details"])
    sdk.output = [SDKObject(**data["output"][0])]
    sdk.output[0].content = [SDKObject(**data["output"][0]["content"][0])]
    result = execute(harness(sdk))
    assert result["processing_status"] == "processed"
    assert result["provider_response_private"] == data


def test_caller_mutation_during_dispatch_does_not_rebind_frozen_article():
    bundle = harness()
    original_create = bundle[2].responses.create

    def mutate(**kwargs):
        bundle[0]["record"]["body"] = "Changed caller state."
        return original_create(**kwargs)

    bundle[2].responses.create = mutate
    result = execute(bundle)
    assert result["processing_status"] == "processed"
    assert result["assessment"]["judgments"][5]["support_evidence"][0]["quote"] == "The company proposes CCS."
