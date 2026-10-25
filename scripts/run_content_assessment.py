"""Plan a private full-text pilot; execute only an explicitly asserted plan.

Planning is offline and never loads credentials. The execution switch is an
operator assertion, not evidence of human authorization or customer approval.
There is no resume or automatic retry: an existing run directory is rejected.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import inspect
import json
import os
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import prepare_content_assessment as preparation

from observatory import budget as accounting
from observatory import content_provider as provider
from observatory import research_agent
from observatory.evaluate import canonical_digest

PLAN_FORMAT = "content-assessment-run-plan-v1"
RUN_FORMAT = "content-assessment-provider-run-v1"
MAX_CALLS = 30
EXECUTION_REGISTRY = Path(__file__).resolve().parents[1] / ".runtime/content_assessment_execution"
PRICE_REFERENCE = {
    "source": "https://developers.openai.com/api/docs/pricing",
    "verified_on": "2026-10-06", "model": "gpt-5.6-luna",
    "context": "standard short-context input at most 272000 tokens",
    "usd_per_million_tokens": {
        "input": "0.20", "cached_input": "0.02", "cache_write": "0.25", "output": "1.20",
    },
    "reservation_multiplier": "1.25",
    "note": "Conservative application exposure control; not an absolute provider bill limit.",
}
PENDING = {**preparation.PENDING_FLAGS, "review_required": True, "publication_status": "hold"}
BINDINGS = ("request_sha256", "record_id", "version_id", "body_sha256", "payload_sha256", "definitions_sha256")
STOP_STATUSES = {
    "budget_limited", "budget_unavailable", "provider_unavailable", "provider_usage_unavailable",
    "model_mismatch", "pricing_bound_exceeded", "budget_settlement_unavailable", "accounting_bound_exceeded",
}


def dollars(value, *, positive=True):
    """Accept exact finite amounts; never normalize NaN, Infinity or Boolean."""
    if not isinstance(value, (str, Decimal)):
        raise ValueError("decimal_string_required")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("finite_usd_required") from exc
    if not amount.is_finite() or (amount <= 0 if positive else amount < 0):
        raise ValueError("positive_finite_usd_required" if positive else "nonnegative_finite_usd_required")
    return amount


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sdk_file(package, relative=None):
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.origin:
        raise ValueError("required_provider_sdk_unavailable")
    path = Path(spec.origin) if relative is None else Path(spec.origin).parent / relative
    return preparation.original.digest(preparation.read_bytes(path))


def code_fingerprints():
    """Package inspection is local; it does not construct an SDK client."""
    return {
        "runner_sha256": preparation.original.digest(Path(__file__).read_bytes()),
        "provider_sha256": preparation.original.digest(Path(provider.__file__).read_bytes()),
        "budget_sha256": preparation.original.digest(Path(accounting.__file__).read_bytes()),
        "usage_helper_sha256": preparation.original.digest(Path(research_agent.__file__).read_bytes()),
        "preparation": preparation.code_fingerprints(),
        "sdk": {"openai_version": importlib.metadata.version("openai"),
                "openai_init_sha256": _sdk_file("openai"),
                "openai_responses_sha256": _sdk_file("openai", "resources/responses/responses.py"),
                "pydantic_version": importlib.metadata.version("pydantic"),
                "tiktoken_version": importlib.metadata.version("tiktoken")},
    }


def _verify_prices():
    observed = [accounting.price(provider.MODEL, 1_000_000),
                accounting.price(provider.MODEL, 1_000_000, cached_tokens=1_000_000),
                accounting.price(provider.MODEL, 1_000_000, cache_write_tokens=1_000_000),
                accounting.price(provider.MODEL, 0, 1_000_000)]
    if observed != [Decimal(".20"), Decimal(".02"), Decimal(".25"), Decimal("1.20")]:
        raise ValueError("verified_rate_configuration_changed")


def _build_plan(source, frozen, record_ids, *, max_usd, max_output_tokens=6000, model=provider.MODEL):
    cap = dollars(max_usd)
    if (not isinstance(record_ids, (list, tuple)) or not record_ids
            or any(not isinstance(rid, str) or not rid.strip() for rid in record_ids)
            or len(record_ids) != len(set(record_ids))):
        raise ValueError("explicit_unique_record_ids_required")
    if len(record_ids) > MAX_CALLS:
        raise ValueError("pilot_maximum_30_generation_calls")
    if model != provider.MODEL:
        raise ValueError("provider_model_has_no_verified_price")
    _verify_prices()
    known = {row["request"]["record_id"]: row for row in frozen["requests"]}
    calls = []
    for rid in record_ids:
        if rid not in known:
            raise ValueError("unknown_selected_record_id")
        row = known[rid]
        if row["request"]["status"] != "ready":
            raise ValueError("selected_record_is_not_ready")
        spec = provider.build_provider_call(row["request"], model=model, max_output_tokens=max_output_tokens)
        calls.append({"record_id": rid, "request_id": row["request_id"], "call_spec": spec})
    total = sum((dollars(row["call_spec"]["reserved_usd"]) for row in calls), Decimal("0"))
    if total > cap:
        raise ValueError("run_cap_below_total_conservative_reservations")
    return {
        "format_version": PLAN_FORMAT, "status": "pending_authorization", **PENDING,
        "human_authorization_recorded": False,
        "authorization_note": "An execution hash assertion does not replace the user's authorization.",
        "scope": "frozen_active_countable_native_source_records",
        "source_records": len(source["records"]), "scope_records": len(frozen["requests"]),
        "question_count": 24, "judgment_slots": len(frozen["requests"]) * 24,
        "source_manifest_sha256": source["manifest_sha256"],
        "prepared_manifest_sha256": frozen["manifest_sha256"],
        "source_input_sha256": {name: preparation.original.digest(source["files"][name]) for name in preparation.INPUT_NAMES},
        "selection_sha256": source["summary"]["selection_sha256"],
        "request_ids_sha256": frozen["summary"]["request_ids_sha256"],
        "requests": deepcopy(frozen["requests"]),
        "selected_record_ids": list(record_ids), "selected_calls": calls, "max_calls": len(calls),
        "model": model, "max_output_tokens": max_output_tokens,
        "max_usd": str(cap), "total_reserved_usd": str(total),
        "client_policy": {"base_url": "https://api.openai.com/v1", "timeout_seconds": 60,
                          "max_retries": 0, "automatic_resume": False, "automatic_retry": False,
                          "visitor_policy": "one unique visitor for the entire run; at most 30 calls",
                          "reasoning_effort": "none", "store": False, "service_tier": "default",
                          "truncation": "disabled", "tools": []},
        "price_reference": deepcopy(PRICE_REFERENCE), "code_fingerprints": code_fingerprints(),
        "model_calls": 0, "accounting_operations": 0, "source_database_writes": 0,
        "source_adoptions": 0, "publications": 0,
    }


def plan(packet, prepared, record_ids, *, max_usd, max_output_tokens=6000, model=provider.MODEL):
    source = preparation.load_content_packet(packet)
    frozen = preparation.load_prepared(prepared, source)
    return _build_plan(source, frozen, record_ids, max_usd=max_usd, max_output_tokens=max_output_tokens, model=model)


def _freeze_inputs(source, frozen):
    return {"inputs/source_manifest.json": source["manifest_bytes"],
            "inputs/prepared_manifest.json": frozen["manifest_bytes"],
            "inputs/prepared_summary.json": frozen["files"]["preparation_summary.json"],
            "inputs/requests.jsonl": frozen["files"]["requests.jsonl"],
            **{f"inputs/{name}": source["files"][name] for name in preparation.INPUT_NAMES}}


def _write(root, name, data, artifacts):
    path = preparation.packet_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if preparation.read_bytes(path) != data:
        raise ValueError("written_run_artifact_changed")
    artifacts[name] = {"sha256": preparation.original.digest(data), "size": len(data)}


def _manifest(root, artifacts, fields):
    _write(root, "manifest.json", encoded({**fields, "complete": True, "artifacts": deepcopy(artifacts)}), {})


def write_plan(packet, prepared, output, record_ids, **kwargs):
    output = preparation.require_new_output(output, packet, prepared)
    source = preparation.load_content_packet(packet)
    frozen = preparation.load_prepared(prepared, source)
    planned = _build_plan(source, frozen, record_ids, **kwargs)
    # A new packet is a new proposed execution, even with the same articles and
    # cap. It requires its own asserted hash; copying it keeps the same identity.
    planned["plan_id"] = uuid4().hex
    data = encoded(planned)
    fingerprint = preparation.original.digest(data)
    summary = {key: planned[key] for key in (
        "format_version", "status", "scope_records", "question_count", "judgment_slots",
        "selected_record_ids", "max_calls", "model", "max_output_tokens", "max_usd", "total_reserved_usd",
        "source_manifest_sha256", "prepared_manifest_sha256", "price_reference")}
    summary.update(plan_sha256=fingerprint, **PENDING, model_calls=0, accounting_operations=0)
    markdown = ("# Full-text assessment pilot plan\n\n"
                "Status: pending authorization. This plan makes no model calls.\n\n"
                f"Scope: {planned['scope_records']} records / {planned['judgment_slots']} judgment slots.\n\n"
                f"Selected calls: {planned['max_calls']}. Model: {planned['model']}.\n\n"
                f"Conservative total reservation: ${planned['total_reserved_usd']}; run cap: ${planned['max_usd']}.\n\n"
                f"Plan SHA256: `{fingerprint}`\n\n"
                "An execution hash assertion is not human authorization, semantic review or permission to publish.\n"
                "Unknown outcomes retain exposure. There is no automatic retry or resume.\n").encode()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for name, value in {**_freeze_inputs(source, frozen), "plan.json": data,
                        "plan_summary.json": encoded(summary), "README.md": markdown}.items():
        _write(output, name, value, artifacts)
    _manifest(output, artifacts, {"format_version": PLAN_FORMAT, "status": "pending_authorization",
                                 "plan_sha256": fingerprint, **PENDING, "model_calls": 0,
                                 "accounting_operations": 0, "source_database_writes": 0,
                                 "source_adoptions": 0, "publications": 0})
    return summary


def _read_plan_files(root, manifest):
    if not isinstance(manifest, dict) or manifest.get("format_version") != PLAN_FORMAT:
        raise ValueError("run_plan_manifest_required")
    preparation.require_flags(manifest)
    if (manifest.get("status") != "pending_authorization" or manifest.get("complete") is not True
            or manifest.get("review_required") is not True or manifest.get("publication_status") != "hold"
            or any(manifest.get(field) != 0 for field in ("model_calls", "accounting_operations",
                                                        "source_database_writes", "source_adoptions", "publications"))):
        raise ValueError("unexecuted_run_plan_required")
    artifacts = manifest.get("artifacts")
    required = {"plan.json", "plan_summary.json", "README.md", "inputs/source_manifest.json",
                "inputs/prepared_manifest.json", "inputs/prepared_summary.json", "inputs/requests.jsonl"}
    required |= {f"inputs/{name}" for name in preparation.INPUT_NAMES}
    if not isinstance(artifacts, dict) or set(artifacts) != required:
        raise ValueError("complete_run_plan_artifacts_required")
    files, total = {}, 0
    for name, declared in artifacts.items():
        if (not isinstance(declared, dict) or set(declared) != {"sha256", "size"}
                or not isinstance(declared["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", declared["sha256"])
                or type(declared["size"]) is not int or declared["size"] < 0):
            raise ValueError("invalid_run_plan_artifact_declaration")
        value = preparation.read_bytes(preparation.packet_path(root, name))
        total += len(value)
        if total > preparation.MAX_PACKET_BYTES:
            raise ValueError("run_plan_packet_too_large")
        if preparation.original.digest(value) != declared["sha256"] or len(value) != declared["size"]:
            raise ValueError("run_plan_artifact_changed")
        files[name] = value
    return files


def load_plan(packet, prepared, plan_dir):
    """Rebuild every source request and call before credentials or connections."""
    root = Path(plan_dir)
    try:
        manifest_bytes = preparation.read_bytes(preparation.packet_path(root, "manifest.json"))
        manifest = preparation.parse_json(manifest_bytes)
        files = _read_plan_files(root, manifest)
        planned = preparation.parse_json(files["plan.json"])
        if not isinstance(planned, dict):
            raise ValueError("run_plan_object_required")
        sha = preparation.original.digest(files["plan.json"])
        if manifest.get("plan_sha256") != sha:
            raise ValueError("run_plan_sha256_changed")
        source = preparation.load_content_packet(packet)
        frozen = preparation.load_prepared(prepared, source)
        if any(files[name] != value for name, value in _freeze_inputs(source, frozen).items()):
            raise ValueError("run_plan_frozen_inputs_changed")
        rebuilt = _build_plan(source, frozen, planned.get("selected_record_ids"),
                              max_usd=planned.get("max_usd"), model=planned.get("model"),
                              max_output_tokens=planned.get("max_output_tokens"))
        if not isinstance(planned.get("plan_id"), str) or not re.fullmatch("[0-9a-f]{32}", planned["plan_id"]):
            raise ValueError("unique_written_plan_identity_required")
        rebuilt["plan_id"] = planned["plan_id"]
        if canonical_digest(planned) != canonical_digest(rebuilt):
            raise ValueError("run_plan_differ_from_rebuilt_scope_and_calls")
        summary = preparation.parse_json(files["plan_summary.json"])
        expected_summary = {key: rebuilt[key] for key in (
            "format_version", "status", "scope_records", "question_count", "judgment_slots", "selected_record_ids",
            "max_calls", "model", "max_output_tokens", "max_usd", "total_reserved_usd", "source_manifest_sha256",
            "prepared_manifest_sha256", "price_reference")}
        expected_summary.update(plan_sha256=sha, **PENDING, model_calls=0, accounting_operations=0)
        if summary != expected_summary:
            raise ValueError("run_plan_summary_changed")
        return {"plan": rebuilt, "plan_bytes": files["plan.json"], "plan_sha256": sha,
                "files": files, "manifest_bytes": manifest_bytes, "source": source, "frozen": frozen}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid_run_plan_structure") from exc


def _live_dependencies():
    # This is the only credential/environment branch. Pure plan/load never call it.
    from openai import OpenAI

    from observatory.budget import Budget
    from observatory.config import Settings
    from observatory.db import Database

    settings = Settings.from_env()
    if settings.generation_model != provider.MODEL:
        raise ValueError("configured_model_differ_from_approved_plan")
    if (not settings.monthly_budget_usd.is_finite() or settings.monthly_budget_usd <= 0
            or not 1 <= settings.requests_per_day <= MAX_CALLS
            or settings.requests_per_minute < 1 or settings.concurrency < 1):
        raise ValueError("invalid_runtime_budget_policy")
    db = Database(settings.database_url)
    client = OpenAI(base_url="https://api.openai.com/v1", timeout=60, max_retries=0)
    return client, Budget(db, settings)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate_dependencies(client, budget):
    try:
        create = getattr(getattr(client, "responses", None), "create", None)
        retries = getattr(client, "max_retries", 0)
        methods = [getattr(budget, name, None) for name in ("reserve", "settle", "uncertain")]
    except Exception as exc:
        raise ValueError("provider_dependency_contract_unavailable") from exc
    if not callable(create) or inspect.iscoroutinefunction(create):
        raise ValueError("synchronous_provider_create_required")
    if type(retries) is not int or retries != 0:
        raise ValueError("provider_client_retries_must_be_disabled")
    if any(not callable(method) or inspect.iscoroutinefunction(method) for method in methods):
        raise ValueError("provider_budget_contract_required")


def _execution_marker(plan_dir, fingerprint):
    return (preparation.packet_path(Path(plan_dir), ".execution_started.json"),
            preparation.packet_path(EXECUTION_REGISTRY, f"{fingerprint}.json"))


def _claim_execution(plan_dir, fingerprint, started, output):
    """One hash can be dispatched once, including copies in a different folder.

    The registry is a private local sidecar, not a credential, approval record or
    resumable queue. Never remove a marker automatically after a crash/error.
    """
    local, global_marker = _execution_marker(plan_dir, fingerprint)
    EXECUTION_REGISTRY.mkdir(parents=True, exist_ok=True)
    marker = encoded({"plan_sha256": fingerprint, "plan_id": started["plan_id"],
                      "run_id": started["run_id"], "output": str(output.resolve()), "started_at": _now(),
                      "status": "execution_claimed_no_automatic_retry", "human_authorization_verified": False})
    try:
        _write(EXECUTION_REGISTRY, global_marker.name, marker, {})
        _write(Path(plan_dir), local.name, marker, {})
    except FileExistsError as exc:
        raise ValueError("run_plan_already_consumed") from exc


def _accounting_from_untrusted(envelope, call_spec):
    """Keep known paid bookkeeping without trusting classifications/bindings."""
    audit = envelope.get("provider_call") if isinstance(envelope, dict) else None
    fallback = {"state": "uncertain", "dispatched": None, "cost_usd": None,
                "exposure_usd": call_spec["reserved_usd"], "reserved_usd": call_spec["reserved_usd"],
                "call_sha256": call_spec["call_sha256"]}
    if not isinstance(audit, dict):
        return fallback
    # Reservation/usage are retained for reconciliation only. A known settled
    # amount is valid bookkeeping even when its accompanying draft was rejected.
    for name in ("reservation_id", "usage", "response_id", "response_status", "provider_model", "requested_model"):
        value = audit.get(name)
        if isinstance(value, (str, dict)) or value is None:
            fallback[name] = deepcopy(value)
    if type(audit.get("dispatched")) is bool:
        fallback["dispatched"] = audit["dispatched"]
    try:
        amount = dollars(audit.get("cost_usd"), positive=False)
        retained_exposure = dollars(audit.get("exposure_usd"), positive=False)
        if (audit.get("state") == "settled" and amount == retained_exposure
                and audit.get("call_sha256") == call_spec["call_sha256"]):
            fallback.update(state="settled", cost_usd=str(amount), exposure_usd=str(retained_exposure))
    except ValueError:
        pass
    return fallback


def _unknown_row(wrapper, reason, *, selected=False):
    request = wrapper["request"]
    assessment = preparation.mechanism.materialize_assessment(request, None)
    assessment.update(processing_status=reason, reason=reason)
    return {"request_id": wrapper["request_id"], **{key: request[key] for key in BINDINGS},
            "processing_status": reason, "selected_for_run": selected,
            "response_origin": "not_obtained", "provider_call": None, "assessment": assessment}


def _validate_envelope(envelope, request, call_spec):
    if not isinstance(envelope, dict) or any(envelope.get(key) != request[key] for key in BINDINGS):
        raise ValueError("provider_result_binding_changed")
    assessment, audit = envelope.get("assessment"), envelope.get("provider_call")
    if (not isinstance(assessment, dict) or not isinstance(audit, dict)
            or audit.get("call_sha256") != call_spec["call_sha256"]
            or audit.get("reserved_usd") != call_spec["reserved_usd"]
            or audit.get("requested_model") != call_spec["model"]
            or type(audit.get("dispatched")) is not bool
            or audit.get("state") not in {"none", "pending", "settled", "uncertain"}
            or not isinstance(envelope.get("processing_status"), str)):
        raise ValueError("provider_result_audit_changed")
    if (assessment.get("publication_status") != "hold" or assessment.get("review_required") is not True
            or assessment.get("status") != "draft_ai_unreviewed" or assessment.get("source_completeness") != "unknown"
            or any(assessment.get(key) != request[key] for key in BINDINGS)
            or not isinstance(assessment.get("judgments"), list)
            or [j.get("question_id") for j in assessment["judgments"]] != list(preparation.mechanism.QUESTION_IDS)):
        raise ValueError("provider_result_assessment_changed")
    dollars(audit.get("exposure_usd"), positive=False)
    if audit.get("cost_usd") is not None:
        dollars(audit["cost_usd"], positive=False)


def _checkpoint(output, number, envelope, artifacts):
    raw = envelope.pop("provider_response_private", None)
    if raw is not None:
        name = f"private/responses/{number:03d}.json"
        _write(output, name, encoded(raw), artifacts)
        envelope["private_response"] = {"path": name, **artifacts[name]}
    else:
        envelope["private_response"] = None
    _write(output, f"checkpoints/{number:03d}.json", encoded(envelope), artifacts)


def execute(packet, prepared, plan_dir, output, *, approved_plan_sha256, client=None, budget=None):
    output = preparation.require_new_output(output, packet, prepared, plan_dir)
    loaded = load_plan(packet, prepared, plan_dir)
    if (not isinstance(approved_plan_sha256, str) or not re.fullmatch("[0-9a-f]{64}", approved_plan_sha256)
            or approved_plan_sha256 != loaded["plan_sha256"]):
        raise ValueError("exact_approved_plan_sha256_required")
    if (client is None) != (budget is None):
        raise ValueError("inject_client_and_budget_together")
    if any(path.exists() for path in _execution_marker(plan_dir, loaded["plan_sha256"])):
        raise ValueError("run_plan_already_consumed")
    # Invalid injected contracts consume neither the plan nor a reservation.
    if client is not None:
        _validate_dependencies(client, budget)
    planned, artifacts = loaded["plan"], {}
    cap = dollars(planned["max_usd"])
    run_id = uuid4().hex
    visitor = f"content-assessment:{run_id}"
    injected = client is not None
    output.mkdir(parents=True, exist_ok=False)
    for name, data in {**_freeze_inputs(loaded["source"], loaded["frozen"]),
                       "inputs/run_plan.json": loaded["plan_bytes"],
                       "inputs/run_plan_manifest.json": loaded["manifest_bytes"]}.items():
        _write(output, name, data, artifacts)
    started = {"format_version": RUN_FORMAT, "status": "started", "run_id": run_id, "visitor": visitor,
               "started_at": _now(), "plan_sha256": loaded["plan_sha256"], "plan_id": planned["plan_id"],
               "operator_approval_asserted": True, "human_authorization_verified": False,
               "execution_mode": "injected_test" if injected else "live",
               "scope_records": planned["scope_records"], "judgment_slots": planned["judgment_slots"],
               "selected_record_ids": planned["selected_record_ids"], "max_calls": planned["max_calls"],
               "max_usd": planned["max_usd"], "total_reserved_usd": planned["total_reserved_usd"],
               "automatic_resume": False, "automatic_retry": False, **PENDING}
    _write(output, "started.json", encoded(started), artifacts)
    rows = {row["request"]["record_id"]: _unknown_row(
        row, "not_requested" if row["request"]["status"] == "not_requested" else "not_selected",
        selected=row["request"]["record_id"] in planned["selected_record_ids"])
        for row in loaded["frozen"]["requests"]}
    wrappers = {row["request"]["record_id"]: row for row in loaded["frozen"]["requests"]}
    stop_reason, error_type, exposure, calls = None, None, Decimal("0"), []
    if not injected:
        try:
            client, budget = _live_dependencies()
            _validate_dependencies(client, budget)
        except Exception as exc:
            stop_reason, error_type = "runtime_dependencies_unavailable", type(exc).__name__
    if stop_reason is None:
        if load_plan(packet, prepared, plan_dir)["plan_sha256"] != loaded["plan_sha256"]:
            raise ValueError("run_plan_changed_before_execution_claim")
        _claim_execution(plan_dir, loaded["plan_sha256"], started, output)
    for number, selected in enumerate(planned["selected_calls"], 1):
        if stop_reason:
            break
        rid = selected["record_id"]
        wrapper, call_spec = wrappers[rid], selected["call_spec"]
        # Every dispatch uses the still-bound source and exact plan. A concurrent
        # edit stops future calls; it never discards already accounted results.
        try:
            if load_plan(packet, prepared, plan_dir)["plan_sha256"] != loaded["plan_sha256"]:
                raise ValueError("run_plan_changed_between_calls")
            if exposure + dollars(call_spec["reserved_usd"]) > cap:
                raise ValueError("run_exposure_cap_reached")
        except Exception as exc:
            stop_reason, error_type = "run_binding_or_cap_changed", type(exc).__name__
            break
        start = _now()
        envelope = None
        try:
            envelope = provider.execute_provider_call(wrapper["request"], call_spec,
                                                       client=client, budget=budget, visitor=visitor)
            _validate_envelope(envelope, wrapper["request"], call_spec)
        except Exception as exc:
            # This should be pre-dispatch in the validated adapter. An unexpected
            # transport defect could have dispatched: conservatively retain the
            # selected reservation estimate and do not attempt another article.
            stop_reason, error_type = "provider_adapter_failure", type(exc).__name__
            untrusted = envelope
            envelope = _unknown_row(wrapper, stop_reason, selected=True)
            envelope["provider_call"] = _accounting_from_untrusted(untrusted, call_spec)
            envelope["provider_call"]["error_type"] = error_type
            if untrusted is not None:
                # Full unexpected output stays private for reconciliation. It
                # never becomes source evidence, public text or a new prompt.
                _write(output, f"private/failures/{number:03d}.json", encoded(untrusted), artifacts)
                raw = untrusted.get("provider_response_private") if isinstance(untrusted, dict) else None
                envelope["provider_response_private"] = deepcopy(raw)
        audit = envelope["provider_call"]
        exposure += dollars(audit["exposure_usd"], positive=False)
        envelope.update(request_id=wrapper["request_id"], selected_for_run=True,
                        response_origin="injected_provider_test" if injected else "provider_run",
                        call_started_at=start, call_finished_at=_now())
        # A checkpoint is durable before any subsequent dispatch. If persistence
        # fails, started.json and frozen scope remain; this run cannot be resumed.
        try:
            _checkpoint(output, number, envelope, artifacts)
        except Exception as exc:
            raise ValueError("run_checkpoint_failed_no_resume") from exc
        rows[rid] = envelope
        calls.append(envelope)
        if (stop_reason is None and (audit["state"] in {"uncertain", "pending"}
                                    or envelope["processing_status"] in STOP_STATUSES or exposure > cap)):
            stop_reason = envelope["processing_status"] if exposure <= cap else "run_exposure_cap_exceeded"
        # A pilot also stops on paid refusal, incomplete output or invalid draft;
        # fix the cause before authorizing another new run.
        if stop_reason is None and envelope["processing_status"] != "processed":
            stop_reason = envelope["processing_status"]
    for rid in planned["selected_record_ids"]:
        if rows[rid]["processing_status"] == "not_selected":
            rows[rid] = _unknown_row(wrappers[rid], "not_executed_after_stop", selected=True)
    results = [rows[wrapper["request"]["record_id"]] for wrapper in loaded["frozen"]["requests"]]
    total_actual = sum((dollars(row["provider_call"]["cost_usd"], positive=False) for row in calls
                        if row["provider_call"].get("cost_usd") is not None), Decimal("0"))
    ledger_complete = all(row["provider_call"].get("state") in {"none", "settled"}
                          and row["provider_call"].get("dispatched") is not None for row in calls)
    summary = {"format_version": RUN_FORMAT, "status": "stopped" if stop_reason else "completed_draft",
               "run_id": run_id, "visitor": visitor, "started_at": started["started_at"], "finished_at": _now(),
               "stop_reason": stop_reason, "error_type": error_type,
               "execution_mode": started["execution_mode"], "operator_approval_asserted": True,
               "human_authorization_verified": False, "plan_sha256": loaded["plan_sha256"],
               "scope": planned["scope"], "scope_records": len(results), "question_count": 24,
               "judgment_slots": len(results) * 24, "planned_calls": planned["max_calls"],
               "attempted_calls": len(calls), "provider_dispatch_attempts": sum(
                   row["provider_call"].get("dispatched") is True for row in calls),
               "unknown_dispatch_attempts": sum(row["provider_call"].get("dispatched") is None for row in calls),
               "processing_status_counts": dict(Counter(row["processing_status"] for row in results)),
               "judgment_membership_counts": dict(Counter(
                   judgment["membership"] for row in results for judgment in row["assessment"]["judgments"])),
               "cost_usd": str(total_actual) if ledger_complete else None,
               "known_settled_cost_usd": str(total_actual), "ledger_complete": ledger_complete,
               "exposure_usd": str(exposure), "max_usd": planned["max_usd"],
               "conservative_total_reserved_usd": planned["total_reserved_usd"],
               "uncertain_calls": sum(row["provider_call"]["state"] == "uncertain" for row in calls),
               "source_manifest_sha256": planned["source_manifest_sha256"],
               "prepared_manifest_sha256": planned["prepared_manifest_sha256"],
               "selection_sha256": planned["selection_sha256"], "request_ids_sha256": planned["request_ids_sha256"],
               "reviewed_units": 0, "article_negative_units": 0, "source_database_writes": 0,
               "source_adoptions": 0, "publications": 0, "automatic_resume": False, "automatic_retry": False,
               "bill_limit_note": PRICE_REFERENCE["note"], **PENDING}
    _write(output, "results.jsonl", preparation.jsonl_bytes(results), artifacts)
    _write(output, "coverage_summary.json", encoded(summary), artifacts)
    # Public-safe aggregate has no text, record IDs, response IDs, visitor or raw
    # provider output. Creating this file does not authorize its publication.
    safe_keys = ("format_version", "status", "scope_records", "question_count", "judgment_slots", "planned_calls",
                 "attempted_calls", "provider_dispatch_attempts", "unknown_dispatch_attempts", "processing_status_counts",
                 "cost_usd", "known_settled_cost_usd", "ledger_complete", "exposure_usd", "max_usd",
                 "uncertain_calls", "reviewed_units", "article_negative_units",
                 "review_required", "publication_status", "quality_scores", "semantic_gold", "customer_approved",
                 "execution_mode", "bill_limit_note", "stop_reason")
    _write(output, "aggregate_audit.json", encoded({key: summary[key] for key in safe_keys}), artifacts)
    _manifest(output, artifacts, {"format_version": RUN_FORMAT, "status": summary["status"],
                                 "run_id": run_id, "plan_sha256": loaded["plan_sha256"], **PENDING,
                                 "source_database_writes": 0, "source_adoptions": 0, "publications": 0})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="Prepare an offline pilot cost plan")
    running = commands.add_parser("execute", help="Execute an explicitly asserted, separately authorized plan")
    for command in (planning, running):
        command.add_argument("--packet", type=Path, required=True)
        command.add_argument("--prepared", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
    planning.add_argument("--record-id", action="append", required=True)
    planning.add_argument("--max-usd", required=True)
    planning.add_argument("--max-output-tokens", type=int, default=6000)
    planning.add_argument("--model", default=provider.MODEL)
    running.add_argument("--plan", type=Path, required=True)
    running.add_argument("--approved-plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            summary = write_plan(args.packet, args.prepared, args.out, args.record_id,
                                 max_usd=args.max_usd, max_output_tokens=args.max_output_tokens, model=args.model)
        else:
            summary = execute(args.packet, args.prepared, args.plan, args.out,
                              approved_plan_sha256=args.approved_plan_sha256)
    except (ValueError, OSError) as exc:
        # Known validation codes are safe; filesystem/transport exception text
        # may contain private data and is never echoed by this command.
        code = str(exc)
        message = code if isinstance(exc, ValueError) and re.fullmatch("[a-z][a-z0-9_]{0,100}", code) else type(exc).__name__
        parser.exit(2, f"{message}\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return summary


if __name__ == "__main__":
    main()
