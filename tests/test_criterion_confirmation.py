"""Pipeline step 3, S3-c: the criterion is confirmed before any ad is judged (two-phase lists).

Fictional ads and posts (the golden fixtures of test_list_golden), through Service.answer so
the whole wrapping is covered. Under "ask" a screened list stops with the card: the criterion
drafted from the question alone, one verbatim example sentence per rule (never sent to a
model), what phase 2 will read, and a signed token. A continuation checks the token, binds the
flow once in the in-process registry, and judges by the confirmed criterion; "confirmed" or
"edited" is decided from the draft's hash. Invalid or stale continuations, conflicts, retries,
a full registry and a changed collection spend nothing. API and internal callers stay "auto"
(user decision 1 of 2026-10-27), and an auto list says its rules are an unconfirmed draft.
"""
import threading
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_list_criterion_mode import (
    CONFIRMED,
    NOTE_HEAD,
    roles,
    screening_questions,
    service_for,
)
from test_list_golden import (
    CRITERION,
    HASHTAG,
    JOBS,
    PHRASE_READ,
    SCENARIOS,
    Calls,
    GoldenDb,
    Ledger,
    golden_rag,
)

from observatory import criterion_confirmation as cc
from observatory.config import Settings
from observatory.criterion_confirmation import (
    UNCONFIRMED_NOTE,
    ConfirmationTokens,
    ContinuationInvalid,
    CriterionInvalid,
    FlowRegistry,
    RegistryFull,
    pending_confirmation,
)
from observatory.models import Answer, Citation, Evidence, Filters
from observatory.relevance_triage import Criterion, CriterionDraft
from observatory.research_agent import ResearchRun
from observatory.service import Service

NATIVE = Filters(dataset="native")
DRAFT = CRITERION.model_dump()  # what the fictional drafting model returns for JOBS
EXAMPLE = "Tidal kites will bring 400 jobs to the harbor."  # n2's sentence, the best overlap with the draft's rule
WEB_ON = replace(Settings(), web_search_enabled=True)


def card_for(name, monkeypatch, **answer_options):
    service, scenario, calls, ledger = service_for(name, monkeypatch)
    card = service.answer(scenario.question, Filters(**scenario.filters), "offline", criterion_confirmation="ask", **answer_options)
    return service, scenario, card, calls, ledger


def continue_with(service, card, criterion, question=JOBS, filters=NATIVE, visitor="offline", **extra):
    return service.answer(question, filters, visitor,
                          continuation={"token": card.structured_result["continuation"], "criterion": criterion, **extra})


def model_calls(calls):
    snapshot = calls.snapshot()
    return len(snapshot["shared"]) + sum(len(snapshot[d][r]) for d in ("native", "social") for r in ("screen", "judge"))


def saved(service):
    return [call.args[2] for call in service.db.save_answer.call_args_list]


def screened_records(calls, dataset="native"):
    return {record for call in calls.by_dataset[dataset]["screen"] for record, _ in call["ads"]}


# --- Phase 1: the card -----------------------------------------------------------------------------


def test_ask_stops_with_the_card_before_any_judgment(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    stages = []
    card = service.answer(JOBS, NATIVE, "offline", progress=stages.append, criterion_confirmation="ask")
    assert (card.status, card.answer_mode, card.failure_reason) == (
        "insufficient_evidence", "clarification", "criterion_confirmation_required")
    assert pending_confirmation(card) and "drafting" in stages
    # Only the drafting call, from the question alone; no Decisions, screening or writer call.
    assert roles(calls) == ["embed", "criterion"] and calls.by_dataset["native"] == {"screen": [], "judge": []}
    assert calls.shared[1]["question"] == JOBS and calls.shared[1]["messages"] == 2
    structured = card.structured_result
    assert structured["kind"] == "criterion_confirmation" and structured["criterion"] == DRAFT
    assert structured["condition"] == {"kind": "draft", "phrases": [], "relations": None}
    assert structured["examples"] == [{
        "rule": 1, "sentence": EXAMPLE, "record_id": "n2", "evidence_id": "n2-e1", "dataset": "native",
        "title": "Kite notice n2", "publisher": "Harbor Daily", "sponsor": "Tidal Co", "published_at": "2021-05-04",
        "overlap": 3, "basis": "word_overlap"}]
    assert structured["candidates"] == {"native": {"scope_total": 6, "retrieved": 3, "with_rules": "whole_scope", "condition_only": None}}
    assert isinstance(structured["continuation"], str) and structured["continuation"]
    assert structured["expires_at"].endswith("+00:00") and structured["data_version"] == "golden-v1"
    assert structured["limits"] == {"max_rules": 4, "max_exclusions": 3} and structured["flow_id"]
    assert [e.evidence_id for e in card.evidence] == ["n1-e1", "n2-e1", "n3-e1"]  # the ranked candidates, free to browse
    assert card.answer.startswith("All 6 ads in your selection with readable text will be judged by the rules below; "
                                  "the example sentences come from the most relevant ones.")
    assert "Confirm the rules below" in card.answer and EXAMPLE not in card.answer
    assert card.cost_usd == pytest.approx(0.000001 + 0.000016)  # the embedding and the drafting call
    draft = card.research_trace["criterion_draft"]
    assert (draft["status"], draft["criterion"], draft["examples"]) == ("draft", DRAFT, structured["examples"])
    assert draft["cost_usd"] == pytest.approx(0.000016) and draft["example_source"] == "retrieval_top_5_per_collection"
    assert card.research_trace["flow_id"] == structured["flow_id"]
    plan = card.research_trace["question_plan"]
    assert plan["criterion_mode"] == "ask" and card.research_trace["plan_check"]["criterion_matches"] is True
    assert service.flows.snapshot(structured["flow_id"])["state"] == "pending"
    # The run row keeps the token's hash, never the token; the card returned keeps it.
    [row] = saved(service)
    assert row.structured_result["continuation"] is None and len(row.structured_result["continuation_sha256"]) == 64
    assert card.structured_result["continuation"] and "continuation_sha256" not in card.structured_result
    # Not an evidence shortfall: no web supplement even with web search on.
    service.settings = WEB_ON
    assert service._ensure_answer(JOBS, NATIVE, "offline", card) is card
    assert [item[3] for item in ledger.closed] == ["cancelled", "settled"]  # the question's hold, the drafting call


def test_the_card_over_both_collections_describes_each(monkeypatch):
    service, scenario, card, calls, _ = card_for("both_triage", monkeypatch)
    assert pending_confirmation(card) and roles(calls) == ["embed", "criterion"]
    structured = card.structured_result
    assert structured["candidates"] == {
        "native": {"scope_total": 6, "retrieved": 3, "with_rules": "whole_scope", "condition_only": None},
        "social": {"scope_total": 4, "retrieved": 2, "with_rules": "whole_scope", "condition_only": None}}
    assert [(e["dataset"], e["record_id"], e["overlap"]) for e in structured["examples"]] == [("native", "n2", 3), ("social", "s1", 2)]
    assert structured["examples"][1]["sentence"] == "Every tidal kite farm hires local crews: jobs for the harbor."
    assert structured["examples"][1]["publisher"] == "Kite Guild"  # a post's account stands for its outlet
    assert card.answer.startswith("All 6 ads in your selection") and "All 4 posts in your selection" in card.answer


# --- Phase 2: the confirmed criterion ------------------------------------------------------------------


def test_continuing_with_the_unchanged_draft_judges_by_it_as_confirmed(monkeypatch):
    service, scenario, card, calls, ledger = card_for("native_triage", monkeypatch)
    stages = []
    result = service.answer(JOBS, NATIVE, "offline", progress=stages.append,
                            continuation={"token": card.structured_result["continuation"], "criterion": DRAFT})
    assert result.status == "answered" and "judging" in stages
    # Stage order of a judged list: retrieval, then "judging" through the triage and the screening,
    # "organizing" only when the writer starts, "citations" last (the walkthrough of 2026-10-27 showed
    # "organizing" during the judging).
    last_judging = len(stages) - 1 - stages[::-1].index("judging")
    assert stages.index("database") < last_judging < stages.index("organizing") < stages.index("citations")
    assert roles(calls) == ["embed", "criterion", "embed", "writer"]  # nothing drafted again, no research agent
    judged = calls.by_dataset["native"]["judge"]
    assert len(judged) == 6 and all(call["questions"] == ["verdict", "strength", "rule_1", "exclusion_1"] for call in judged)
    asked = screening_questions(calls)
    assert len(asked) == 2 and all(NOTE_HEAD in question for question in asked)  # by the confirmed criterion
    assert [c.evidence_id for c in result.citations] == ["n1-e9", "n2-e1"]
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["screening_basis"]) == ("confirmed", "confirmed_criterion")
    assert trace["criterion"] == DRAFT and trace["criterion_draft"] == DRAFT
    assert trace["criterion_quotes_examples"] == [] and trace["confirmed_condition"] == "draft"
    assert result.structured_result["criterion_source"] == "confirmed"
    assert UNCONFIRMED_NOTE["en"] not in result.answer
    flow_id = card.structured_result["flow_id"]
    assert result.research_trace["flow_id"] == flow_id
    confirmation = result.research_trace["criterion_confirmation"]
    assert (confirmation["phase"], confirmation["condition"], confirmation["criterion_source"]) == (2, "draft", "confirmed")
    assert confirmation["criterion_hash"] == confirmation["draft_hash"] == cc.criterion_hash(DRAFT)
    plan = result.research_trace["question_plan"]
    assert plan["criterion_mode"] == "ask" and result.research_trace["plan_check"]["criterion_matches"] is True
    assert service.flows.snapshot(flow_id)["state"] == "done"
    assert len(saved(service)) == 2 and saved(service)[1].research_trace["flow_id"] == flow_id


def test_an_edited_criterion_is_recorded_as_edited_with_the_draft_beside_it(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "answered"
    judged = calls.by_dataset["native"]["judge"]
    assert all(call["questions"] == ["verdict", "strength", "rule_1", "rule_2", "exclusion_1"] for call in judged)
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["criterion"], trace["criterion_draft"]) == ("edited", CONFIRMED, DRAFT)
    assert result.research_trace["criterion_confirmation"]["criterion_source"] == "edited"
    assert result.structured_result["criterion_source"] == "edited"


def test_rules_quoting_a_shown_example_are_recorded_and_judged_as_usual(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    quoting = {"counts": [f'The ad says something like "{EXAMPLE}"'], "does_not_count": []}
    result = continue_with(service, card, quoting, example_choices=[{"example": 0, "choice": "counts"}])
    assert result.status == "answered" and len(calls.by_dataset["native"]["judge"]) == 6
    quotes = [{"example": 0, "rule": 1, "record_id": "n2", "evidence_id": "n2-e1"}]
    assert result.research_trace["list_screening"]["criterion_quotes_examples"] == quotes
    confirmation = result.research_trace["criterion_confirmation"]
    assert confirmation["criterion_quotes_examples"] == quotes and confirmation["criterion_source"] == "edited"
    assert confirmation["example_choices"] == [{"example": 0, "choice": "counts"}]
    assert all(EXAMPLE in question for question in screening_questions(calls))  # the human's rule, as written


def test_a_retry_with_the_same_criterion_replays_the_final_answer_without_paying(monkeypatch):
    service, scenario, card, calls, ledger = card_for("native_triage", monkeypatch)
    first = continue_with(service, card, DRAFT)
    before = (model_calls(calls), list(ledger.snapshot()))
    again = continue_with(service, card, DRAFT)
    assert (model_calls(calls), list(ledger.snapshot())) == before
    assert again.answer == first.answer and again.citations == first.citations and again.status == "answered"
    assert again.cost_usd == 0.0 and again.research_trace["continuation_replay"] == {
        "flow_id": card.structured_result["flow_id"], "evidence_trimmed": True, "original_cost_usd": first.cost_usd}
    assert "plan_check" in again.research_trace  # the stored answer is the wrapped one
    assert {e.evidence_id for e in again.evidence} >= {c.evidence_id for c in first.citations}
    assert first.cost_usd > 0 and "continuation_replay" not in first.research_trace  # the original is untouched
    # Another criterion after the judgment is a conflict, not a second paid run.
    conflict = continue_with(service, card, CONFIRMED)
    assert (conflict.status, conflict.failure_reason) == ("insufficient_evidence", "continuation_conflict")
    assert (model_calls(calls), list(ledger.snapshot())) == before
    assert saved(service)[-1].failure_reason == "continuation_conflict"  # every answer is still recorded


def test_a_second_submission_while_judging_is_refused_and_a_full_registry_refuses_new_cards(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    service.flows = FlowRegistry(max_entries=1)
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    original, entered, release = service._list_answer, threading.Event(), threading.Event()

    def blocking(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    service._list_answer = blocking
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.setdefault("first", continue_with(service, card, DRAFT)))
    thread.start()
    assert entered.wait(10)
    drafted = roles(calls).count("criterion")
    second = continue_with(service, card, DRAFT)
    assert (second.status, second.failure_reason) == ("insufficient_evidence", "continuation_in_progress")
    another = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert (another.status, another.failure_reason) == ("limited", "confirmation_registry_full")
    assert roles(calls).count("criterion") == drafted  # refused before drafting
    release.set()
    thread.join(10)
    first = outcome["first"]
    assert first.status == "answered" and service.flows.snapshot(card.structured_result["flow_id"])["state"] == "done"
    assert "continuation_replay" in continue_with(service, card, DRAFT).research_trace


def test_a_failed_judgment_is_terminal(monkeypatch):
    service, scenario, card, calls, ledger = card_for("native_triage", monkeypatch)
    service._list_answer = Mock(side_effect=RuntimeError("boom"))
    failed = continue_with(service, card, DRAFT)
    assert (failed.status, failed.failure_reason) == ("service_unavailable", "RuntimeError")
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"
    before = model_calls(calls)
    retry = continue_with(service, card, DRAFT)
    assert (retry.failure_reason, retry.structured_result["detail"]) == ("continuation_invalid", "flow_failed")
    assert model_calls(calls) == before and "ask the question again" in retry.answer


def test_a_limit_during_the_judgment_fails_the_flow(monkeypatch):
    # native_limit_reached: no Decisions client (the card states the condition); its ledger denies
    # the third reservation, which is the first screening batch of phase 2.
    monkeypatch.setenv("OBS_ANSWER_NORMS", "off")
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE", raising=False)
    scenario = SCENARIOS["native_limit_reached"]
    db, ledger, calls = GoldenDb(), Ledger(scenario.limit_at), Calls()
    service = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls))
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert card.structured_result["condition"]["kind"] == "triage_off" and card.structured_result["criterion"] is None
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "limited" and result.cost_usd == pytest.approx(0.000001)  # this run's embedding; nothing settled
    assert result.research_trace["cost_basis"].startswith("embedding_and_settled_calls")
    assert result.structured_result["cost_basis"] == result.research_trace["cost_basis"]  # in the compact body too
    assert [item[3] for item in ledger.closed].count("denied") == 1
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"
    before = model_calls(calls)
    retry = continue_with(service, card, CONFIRMED)
    assert retry.structured_result["detail"] == "flow_failed" and model_calls(calls) == before


def test_the_data_version_is_checked_before_and_at_retrieval(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    before = model_calls(calls)
    service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}
    stale = continue_with(service, card, DRAFT)
    assert (stale.failure_reason, stale.structured_result["detail"]) == ("continuation_invalid", "data_changed")
    assert "updated" in stale.answer and model_calls(calls) == before
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "pending"  # not claimed
    # The version passes the entry check and changes before retrieval: the route stops, the flow fails.
    versions = ["golden-v1", "golden-v2"]
    service.db.health = lambda: {"status": "ok", "data_version": versions.pop(0) if len(versions) > 1 else versions[0]}
    changed = continue_with(service, card, DRAFT)
    assert (changed.failure_reason, changed.structured_result["detail"]) == ("continuation_invalid", "data_changed")
    assert model_calls(calls) == before
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"


def invalid_cases():
    def expired(service, card, clock):
        clock["token"] += 1801
        return {}, "expired"

    def tampered(service, card, clock):
        token = card.structured_result["continuation"]
        return {"token": token[:-4] + ("abcd" if not token.endswith("abcd") else "dcba")}, "bad_signature"

    def other_visitor(service, card, clock):
        return {"visitor": "someone-else"}, "visitor"

    def other_question(service, card, clock):
        return {"question": JOBS + " now"}, "question_changed"

    def narrower_scope(service, card, clock):
        return {"filters": Filters(dataset="native", sponsors=["Fenwick Gas"])}, "scope"

    def other_collection(service, card, clock):
        return {"filters": Filters(dataset="social")}, "scope"

    def extra_key(service, card, clock):
        return {"flow_id": "x"}, "malformed"

    def bad_choices(service, card, clock):
        return {"example_choices": [{"example": "0", "choice": "counts"}]}, "malformed"

    def forgotten(service, card, clock):
        clock["registry"] += 1801  # the pending flow is pruned; the token itself is still in date
        return {}, "flow_unknown"

    return [expired, tampered, other_visitor, other_question, narrower_scope, other_collection, extra_key, bad_choices, forgotten]


@pytest.mark.parametrize("case", invalid_cases(), ids=lambda case: case.__name__)
def test_invalid_continuations_are_refused_without_a_model_call(monkeypatch, case):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    clock = {"token": 1_700_000_000.0, "registry": 1000.0}
    service._confirmation_tokens = ConfirmationTokens("fixed-secret", clock=lambda: clock["token"])
    service.flows = FlowRegistry(clock=lambda: clock["registry"])
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    before = (model_calls(calls), list(ledger.snapshot()))
    overrides, detail = case(service, card, clock)
    arguments = {"question": JOBS, "filters": NATIVE, "visitor": "offline"}
    continuation = {"token": overrides.pop("token", card.structured_result["continuation"]), "criterion": DRAFT}
    for key in ("flow_id", "example_choices"):
        if key in overrides:
            continuation[key] = overrides.pop(key)
    arguments.update(overrides)
    result = service.answer(arguments["question"], arguments["filters"], arguments["visitor"], continuation=continuation)
    assert (result.status, result.answer_mode, result.failure_reason) == ("insufficient_evidence", "clarification", "continuation_invalid")
    assert result.structured_result["detail"] == detail
    assert (model_calls(calls), list(ledger.snapshot())) == before
    service.settings = WEB_ON
    assert service._ensure_answer(JOBS, NATIVE, "offline", result) is result  # never a web supplement


def test_a_restart_forgets_the_flow_even_with_a_valid_token(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    service._confirmation_tokens = ConfirmationTokens("fixed-secret")
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    db, ledger, other_calls = GoldenDb(), Ledger(), Calls()
    restarted = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, other_calls))
    restarted._confirmation_tokens = ConfirmationTokens("fixed-secret")
    result = continue_with(restarted, card, DRAFT)
    assert (result.failure_reason, result.structured_result["detail"]) == ("continuation_invalid", "flow_unknown")
    assert model_calls(other_calls) == 0 and ledger.closed == []


@pytest.mark.parametrize("criterion, detail", [
    ({"counts": [], "does_not_count": []}, "no_rules"),
    ({"counts": ["  ", "\n"], "does_not_count": []}, "no_rules"),
    ({"counts": [f"Rule {n}" for n in range(5)], "does_not_count": []}, "too_many_rules"),
    ({"counts": ["A rule."], "does_not_count": [f"Not {n}" for n in range(4)]}, "too_many_exclusions"),
    ({"counts": [1], "does_not_count": []}, "not_text"),
    ({"rules": ["A rule."]}, "not_a_criterion"),
    (None, "rules_required"),
])
def test_invalid_criteria_are_refused_and_the_flow_stays_pending(monkeypatch, criterion, detail):
    service, scenario, card, calls, ledger = card_for("native_triage", monkeypatch)
    before = (model_calls(calls), list(ledger.snapshot()))
    result = continue_with(service, card, criterion)
    assert (result.status, result.answer_mode, result.failure_reason) == ("insufficient_evidence", "clarification", "criterion_invalid")
    assert result.structured_result["detail"] == detail and result.structured_result["limits"] == {"max_rules": 4, "max_exclusions": 3}
    assert (model_calls(calls), list(ledger.snapshot())) == before
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "pending"
    # Corrected, the same card still works.
    assert continue_with(service, card, DRAFT).status == "answered"


# --- Lists that draft no criterion, or whose drafting failed ------------------------------------------------


def test_a_card_without_a_draft_requires_rules_and_judges_by_them(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    parse = service.rag.client.responses.parse

    def failing_draft(**request):
        if request["text_format"] is CriterionDraft:
            raise ConnectionError("drafting unavailable")
        return parse(**request)

    service.rag.client.responses.parse = failing_draft
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    structured = card.structured_result
    assert pending_confirmation(card) and structured["criterion"] is None and structured["examples"] == []
    assert structured["condition"]["kind"] == "draft_failed" and "could not be drafted" in card.answer
    assert structured["candidates"]["native"]["with_rules"] == "whole_scope"  # the triage is on: rules reach every ad
    assert card.research_trace["criterion_draft"]["status"] == "draft_failed"
    assert [item[3] for item in ledger.closed] == ["cancelled", "uncertain"]  # the failed drafting call is kept as exposure
    without = continue_with(service, card, None)
    assert (without.failure_reason, without.structured_result["detail"]) == ("criterion_invalid", "rules_required")
    assert calls.by_dataset["native"] == {"screen": [], "judge": []}
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "answered" and len(calls.by_dataset["native"]["judge"]) == 6
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["screening_basis"]) == ("edited", "confirmed_criterion")
    assert "criterion_draft" not in trace and trace["confirmed_condition"] == "draft_failed"


def test_with_the_triage_off_the_card_states_the_condition_and_confirming_screens_by_the_question(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    structured = card.structured_result
    assert roles(calls) == ["embed"] and structured["criterion"] is None
    assert structured["condition"]["kind"] == "triage_off" and "Decisions triage is off" in card.answer
    assert structured["candidates"]["native"] == {"scope_total": 6, "retrieved": 3, "with_rules": "whole_scope", "condition_only": "whole_scope"}
    assert card.research_trace["question_plan"]["criterion_available"] is False
    result = continue_with(service, card, None)
    assert result.status == "answered" and calls.by_dataset["native"]["judge"] == []
    # The whole small scope, by the question: six ads in two batches, then n1's re-reading.
    assert screening_questions(calls) == [JOBS, JOBS, JOBS]
    assert screened_records(calls) == {"n1", "n2", "n3", "n4", "n5", "n6"}
    assert result.research_trace["list_screening"]["first_read"] == 6
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["screening_basis"], trace["confirmed_condition"]) == ("confirmed", "question", "triage_off")
    assert "criterion" not in trace and result.structured_result["criterion_source"] == "confirmed"
    assert UNCONFIRMED_NOTE["en"] not in result.answer
    assert result.research_trace["plan_check"]["criterion_matches"] is True
    # Rules the researcher writes reach the screening prompt, still without a judge.
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "answered" and calls.by_dataset["native"]["judge"] == []
    assert all(NOTE_HEAD in question for question in screening_questions(calls)[3:])
    assert result.research_trace["list_screening"]["criterion_source"] == "edited"


def test_a_quoted_phrase_question_stops_with_its_condition_and_confirming_reads_the_phrase_hits_first(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_phrase_read", monkeypatch)
    structured = card.structured_result
    assert roles(calls) == ["embed"] and structured["criterion"] is None  # no draft for a quoted phrase
    assert structured["condition"] == {"kind": "phrases", "phrases": ["tidal kite"], "relations": None}
    assert structured["candidates"]["native"] == {"scope_total": 6, "retrieved": 3, "with_rules": "whole_scope",
                                                  "condition_only": "whole_scope", "phrase_hits": 3}
    assert "must contain “tidal kite”" in card.answer
    assert "all 6 ads with readable text are screened by the question" in card.answer
    result = continue_with(service, card, None, question=PHRASE_READ)
    assert result.status == "answered"
    searches = [call for call in service.db.calls["native"] if call["method"] == "phrase_search"]
    assert len(searches) == 2 and searches[1]["phrases"] == ["tidal kite"]  # once for the card, once to read first
    assert all(NOTE_HEAD not in question for question in screening_questions(calls))
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["screening_basis"], trace["confirmed_condition"]) == ("confirmed", "question", "phrases")
    assert "content_reading" in result.research_trace  # the matched ads were read, as in auto mode


def test_a_relation_hint_card_keeps_the_hint_for_the_confirmed_screening(monkeypatch):
    service, scenario, calls, _ = service_for("social_relation_hint", monkeypatch)
    filters = Filters(**scenario.filters, include_inferred_dates=True)
    card = service._answer_evidence(HASHTAG, filters, "offline", audit=False, relation_listing=scenario.relation_listing,
                                    criterion_confirmation="ask", confirmation_flow=True)
    structured = card.structured_result
    assert pending_confirmation(card) and roles(calls) == ["embed"]
    assert structured["condition"] == {"kind": "relation_hint", "phrases": [], "relations": "hashtags: #KitePower"}
    assert "already satisfies the relation" in card.answer
    result = service.answer(HASHTAG, filters, "offline", continuation={"token": structured["continuation"], "criterion": None})
    assert result.status == "answered"
    asked = screening_questions(calls, "social")
    assert asked and all("the relation hashtags: #KitePower" in question for question in asked)  # from the registry
    trace = result.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["confirmed_condition"]) == ("confirmed", "relation_hint")


# --- Other entries: compound questions, the fallback, auto mode, the switch -----------------------------------


def agent_service(run, monkeypatch, name="native_triage"):
    service, scenario, calls, ledger = service_for(name, monkeypatch)
    service.settings = replace(Settings(), research_agent_enabled=True, web_search_enabled=True)
    service.research_agent = SimpleNamespace(run=lambda *args, **kwargs: run)
    return service, calls


def test_a_compound_list_part_under_ask_is_deferred_not_drafted(monkeypatch):
    part = {"question_part": JOBS, "dataset": "native", "route": "evidence",
            "result": {"filters": Filters(dataset="native", include_inferred_dates=True).model_dump(mode="json"),
                       "search_query": JOBS, "answer_shape": "every_matching_source"}}
    run = ResearchRun(route="composite", result={"status": "ok", "kind": "composite", "complete": True,
                                                 "pending_parts": [], "parts": [part]})
    service, calls = agent_service(run, monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert (result.status, result.failure_reason) == ("insufficient_evidence", "criterion_confirmation_required")
    assert roles(calls) == ["embed"] and calls.by_dataset["native"] == {"screen": [], "judge": []}  # nothing drafted or judged
    [incomplete] = result.structured_result["incomplete_parts"]
    assert incomplete["failure_reason"] == "criterion_confirmation_required"
    assert result.structured_result["parts"][0]["answer"]["answer"].endswith("Ask this part on its own to confirm the criterion.")
    assert len(service.flows) == 0 and not pending_confirmation(result)
    assert "collection_first_fallback" not in result.research_trace  # the fallback does not replace the deferral
    assert not result.external_research  # protected: no web supplement


def test_the_collection_first_fallback_may_stop_with_a_card(monkeypatch):
    run = ResearchRun(route="clarify", failure_reason="research_plan_clarification", result={"message": "Please clarify."})
    service, calls = agent_service(run, monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert pending_confirmation(result) and roles(calls) == ["embed", "criterion"]
    assert result.research_trace["collection_first_fallback"] == "research_plan_clarification"
    assert result.research_trace["criterion_draft"]["status"] == "draft" and result.research_trace["flow_id"]
    assert isinstance(result.structured_result["continuation"], str)
    [row] = saved(service)
    assert row.structured_result["continuation"] is None  # redacted in the run row here too


def test_auto_says_its_draft_is_unconfirmed_in_the_answer_and_the_structured_result(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline")
    assert result.status == "answered" and not pending_confirmation(result)
    head = result.answer.split("\n\n", 1)[0]
    assert head.endswith(" " + UNCONFIRMED_NOTE["en"]) and result.answer.count(UNCONFIRMED_NOTE["en"]) == 1
    assert result.structured_result["criterion_source"] == "draft_unconfirmed"
    assert result.research_trace["list_screening"]["criterion_source"] == "draft_unconfirmed"
    plain, _, _, _ = service_for("native_screen", monkeypatch)
    result = plain.answer(JOBS, NATIVE, "offline")
    assert UNCONFIRMED_NOTE["en"] not in result.answer and result.structured_result["criterion_source"] == "none"


def test_api_and_internal_entries_stay_auto_when_the_web_switch_says_ask(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    service.settings = replace(Settings(), criterion_confirmation="ask")
    result = service.answer(JOBS, NATIVE, "offline")  # no mode given: the entry's default is auto, not the switch
    assert result.status == "answered" and result.research_trace["list_screening"]["criterion_source"] == "draft_unconfirmed"
    assert pending_confirmation(service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask"))
    with pytest.raises(ValueError):
        service.answer(JOBS, NATIVE, "offline", criterion_confirmation="maybe")


# --- The pure helpers -----------------------------------------------------------------------------------------


def passage(record, text, dataset="native", number=1):
    return Evidence(evidence_id=f"{record}-e{number}", record_id=record, version_id=f"{record}-v", dataset=dataset,
                    title=f"Notice {record}", publisher="Harbor Daily", sponsor="Tidal Co", published_at=date(2022, 1, 2),
                    text=text, start=0, end=len(text))


def test_normalize_criterion_and_its_hash():
    loose = {"counts": ["  The ad   presents tidal kites. ", "", "\n"], "does_not_count": [" Jobs unrelated. "]}
    tight = {"counts": ["The ad presents tidal kites."], "does_not_count": ["Jobs unrelated."]}
    assert cc.normalize_criterion(loose) == tight and cc.criterion_hash(loose) == cc.criterion_hash(tight)
    assert cc.criterion_hash(tight) != cc.criterion_hash({"counts": ["The ad presents tidal kites."], "does_not_count": []})
    assert cc.normalize_criterion({"counts": ["A rule"]}) == {"counts": ["A rule"], "does_not_count": []}
    for value, detail in [({"counts": []}, "no_rules"), ({"counts": "A rule"}, "not_text"), ("rules", "not_a_criterion"),
                          ({"counts": ["r"] * 5}, "too_many_rules"), ({"counts": ["r"], "does_not_count": ["x"] * 4}, "too_many_exclusions")]:
        with pytest.raises(CriterionInvalid) as caught:
            cc.normalize_criterion(value)
        assert caught.value.detail == detail


def test_tokens_round_trip_expire_and_reject_tampering():
    clock = {"now": 1_700_000_000.0}
    tokens = ConfirmationTokens("secret", clock=lambda: clock["now"])
    token = tokens.issue({"v": 1, "flow_id": "f1", "visitor": "v"})
    assert tokens.read(token)["flow_id"] == "f1"
    assert tokens.expires_at() == "2023-11-14T22:43:20+00:00"
    clock["now"] += 1801
    with pytest.raises(ContinuationInvalid, match="expired"):
        tokens.read(token)
    clock["now"] -= 1801
    for bad in (token[:-2] + "zz", token.replace(".", "-", 1), "", None, 7):
        with pytest.raises(ContinuationInvalid):
            tokens.read(bad)
    with pytest.raises(ContinuationInvalid, match="bad_signature"):
        ConfirmationTokens("other").read(token)
    with pytest.raises(ContinuationInvalid, match="malformed"):
        tokens.read(tokens.issue({"v": 2}))
    assert ConfirmationTokens().issue({"v": 1}) != ConfirmationTokens().issue({"v": 1})  # random secrets per process


def test_flow_registry_state_machine():
    clock = {"now": 0.0}
    flows = FlowRegistry(pending_ttl=100, done_ttl=1000, max_entries=2, clock=lambda: clock["now"])
    flows.register("a", "v1", {"draft": None})
    assert flows.claim("a", "v1", "h1") == ("unknown", None)  # not issued yet: nothing to continue
    assert flows.ready("a", draft={"counts": ["r"]}) is True and flows.ready("a") is False  # issued once
    assert flows.claim("a", "v2", "h1") == ("unknown", None) and flows.claim("zzz", "v1", "h1") == ("unknown", None)
    assert flows.claim("a", "v1", "h1") == ("started", {"draft": {"counts": ["r"]}})
    assert flows.claim("a", "v1", "h1") == ("in_progress", None) and flows.claim("a", "v1", "h2") == ("conflict", None)
    stored = Answer(status="answered", answer="done", evidence=[passage("n1", "A sentence.")])
    flows.finish("a", stored)
    assert flows.claim("a", "v1", "h1")[0] == "done" and flows.claim("a", "v1", "h1")[1].answer == "done"
    assert flows.claim("a", "v1", "h2") == ("conflict", None)
    flows.register("b", "v1", {})
    flows.ready("b")
    clock["now"] = 150  # the pending flow is forgotten, the done one stays
    assert flows.claim("b", "v1", "h") == ("unknown", None) and flows.snapshot("a")["state"] == "done"
    clock["now"] = 1200
    assert flows.snapshot("a") is None and len(flows) == 0  # done flows are forgotten after done_ttl
    # A preparing or judging flow is never evicted for room; when every slot holds one, a new card is refused.
    flows.register("c", "v1", {})
    flows.ready("c")
    flows.claim("c", "v1", "h")
    clock["now"] = 5000
    assert flows.snapshot("c")["state"] == "judging"
    flows.register("d", "v1", {})
    flows.ready("d")
    flows.register("e", "v1", {})  # evicts the pending d, not the judging c
    assert flows.snapshot("d") is None and flows.snapshot("c") is not None and flows.snapshot("e")["state"] == "preparing"
    with pytest.raises(RegistryFull):
        flows.register("f", "v1", {})  # c is judging, e is still preparing
    flows.discard("e")
    assert flows.snapshot("e") is None
    flows.register("g", "v1", {})
    flows.ready("g")
    flows.claim("g", "v1", "h")
    flows.fail("g", "boom")
    assert flows.claim("g", "v1", "h") == ("failed", None) and flows.snapshot("g")["reason"] == "boom"
    with pytest.raises(ValueError):
        flows.register("c", "v1", {})
    flows.register("p", "v1", {})
    clock["now"] = 5200  # a preparation that never finished is forgotten with the pending ones
    assert flows.snapshot("p") is None and flows.ready("p") is False  # and issues no card
    # The pending window starts when the card is issued, not when the flow was registered.
    flows.register("w", "v1", {})
    clock["now"] = 5280
    assert flows.ready("w") is True
    clock["now"] = 5280 + 99
    assert flows.claim("w", "v1", "h")[0] == "started"


def test_compact_result_replay_and_redaction():
    kept, cited, other = passage("n1", "Kept by the structured result."), passage("n2", "Cited."), passage("n3", "Dropped.")
    result = Answer(status="answered", answer="A list.", cost_usd=0.02, evidence=[kept, cited, other],
                    citations=[Citation(evidence_id="n2-e1", quote="Cited.")],
                    structured_result={"kind": "ai_screened_list", "rows": [{"evidence_id": "n1-e1"}]},
                    research_trace={"flow_id": "f"})
    compact = cc.compact_result(result)
    assert [e.evidence_id for e in compact.evidence] == ["n1-e1", "n2-e1"] and len(result.evidence) == 3
    replayed = cc.replay(compact, "f")
    assert replayed.cost_usd == 0.0 and replayed.latency_ms == 0 and replayed.answer == "A list."
    assert replayed.research_trace == {"flow_id": "f", "continuation_replay": {"flow_id": "f", "evidence_trimmed": True, "original_cost_usd": 0.02}}
    assert compact.cost_usd == 0.02 and "continuation_replay" not in compact.research_trace
    card = Answer(status="insufficient_evidence", answer="Confirm.", structured_result={"kind": "criterion_confirmation", "continuation": "tok.en"})
    redacted = cc.redact_continuation(card)
    assert redacted.structured_result["continuation"] is None and len(redacted.structured_result["continuation_sha256"]) == 64
    assert card.structured_result["continuation"] == "tok.en" and cc.redact_continuation(result) is result
    assert pending_confirmation(card) and pending_confirmation(card.model_dump()) and not pending_confirmation(result)


def test_criterion_examples_pick_the_overlapping_sentence_or_the_opening():
    long_tail = "Tidal kites bring jobs " + "and more work " * 40 + "to the harbor."
    evidence = [passage("n1", "Our festival opens on the pier. Kites fly above the harbor."),
                passage("n2", long_tail),
                passage("n3", "Ferries leave at nine."),
                passage("s1", "Posts about jobs on the pier.", dataset="social")]
    criterion = {"counts": ["The ad presents tidal kites as a source of jobs.", "The ad quotes a mayor."], "does_not_count": []}
    examples = cc.criterion_examples(criterion, evidence, ["native", "social"])
    assert [(e["rule"], e["dataset"], e["record_id"], e["basis"]) for e in examples] == [
        (1, "native", "n2", "word_overlap"), (2, "native", "n1", "opening"), (1, "social", "s1", "word_overlap"), (2, "social", "s1", "opening")]
    assert examples[0]["overlap"] == 3 and len(examples[0]["sentence"]) <= cc.MAX_QUOTE and not examples[0]["sentence"].endswith(" ")
    assert long_tail.startswith(examples[0]["sentence"])  # cut at a word boundary, still verbatim
    assert examples[1]["sentence"] == "Our festival opens on the pier." and examples[1]["overlap"] == 0
    assert cc.criterion_examples(criterion, evidence[:1] * 1, ["native"], per_collection=1)[0]["record_id"] == "n1"
    assert cc.criterion_examples(criterion, [], ["native"]) == []


def test_example_choice_lines_and_quoted_examples():
    assert cc.example_choice_line("Kites bring jobs.", "counts") == 'A statement like "Kites bring jobs." also counts.'
    assert cc.example_choice_line("Kites bring jobs.", "does_not_count") == '"Kites bring jobs." does not count.'
    assert cc.example_choice_line("风筝带来工作。", "counts", is_chinese=True) == "含有“风筝带来工作。”这样的说法也算"
    assert cc.example_choice_line("风筝带来工作。", "does_not_count", is_chinese=True) == "“风筝带来工作。”这类不算"
    with pytest.raises(ValueError):
        cc.example_choice_line("x", "maybe")
    examples = [{"rule": 1, "sentence": "Kites bring 400 jobs.", "record_id": "n2", "evidence_id": "n2-e1"},
                {"rule": 2, "sentence": "Ferries leave at nine.", "record_id": "n4", "evidence_id": "n4-e1"}]
    criterion = {"counts": [cc.example_choice_line("kites bring  400 jobs", "counts")], "does_not_count": ["“Ferries leave at nine” does not count."]}
    assert cc.quoted_examples(criterion, examples) == [
        {"example": 0, "rule": 1, "record_id": "n2", "evidence_id": "n2-e1"},
        {"example": 1, "rule": 2, "record_id": "n4", "evidence_id": "n4-e1"}]
    assert cc.quoted_examples({"counts": ["The ad presents kites as jobs."], "does_not_count": []}, examples) == []


def test_candidate_summary_and_card_wording():
    evidence = [passage("n1", "a"), passage("n2", "b"), passage("s1", "c", dataset="social")]
    summary = cc.candidate_summary({"native": 6, "social": 500}, evidence, "phrases", {"native": 3, "social": 9})
    assert summary == {"native": {"scope_total": 6, "retrieved": 2, "with_rules": "whole_scope", "condition_only": "whole_scope", "phrase_hits": 3},
                       "social": {"scope_total": 500, "retrieved": 1, "with_rules": "candidates", "condition_only": "phrase_hits_and_candidates", "phrase_hits": 9}}
    assert cc.candidate_summary({"native": 6}, evidence, "draft")["native"] == {"scope_total": 6, "retrieved": 2, "with_rules": "whole_scope", "condition_only": None}
    assert cc.candidate_summary({"native": 401}, evidence, "triage_off")["native"] == {"scope_total": 401, "retrieved": 2, "with_rules": "candidates", "condition_only": "candidates"}
    text = cc.confirmation_text(JOBS, summary, "phrases", None, ["tidal kite"])
    assert "All 6 ads in your selection with readable text will be judged by the rules you write." in text
    assert "If you only confirm the stated condition, all 6 ads with readable text are screened by the question." in text
    assert "Your selection has 500 posts; all 1 retrieved candidates will be judged by the rules you write." in text
    assert "every item containing “tidal kite” (9 so far) is read first, then all 1 retrieved candidates, by the question." in text
    assert text.endswith("Confirm, or write rules for them.")
    for kind, phrase in [("draft", "Confirm the rules below"), ("draft_failed", "could not be drafted"),
                         ("relation_hint", "already satisfies the relation"), ("triage_off", "Decisions triage is off")]:
        assert phrase in cc.confirmation_text(JOBS, {"native": summary["native"]}, kind, {"counts": ["r"]} if kind == "draft" else None)
    large = cc.confirmation_text(JOBS, {"native": cc.candidate_summary({"native": 401}, evidence, "triage_off")["native"]}, "triage_off", None)
    assert "all 2 retrieved candidates are screened by the question" in large
    chinese = cc.confirmation_text("讲潮汐风筝的广告都是哪几篇？", {"native": summary["native"]}, "draft", {"counts": ["r"]})
    assert chinese.startswith("范围内有正文的 6 篇广告都会按下面的规则判定；例句来自最相关的几篇。") and "请确认下面的规则" in chinese


def test_mark_unconfirmed_and_refusals():
    marked = cc.mark_unconfirmed("Found 2 matching ads among the 6 in your selection (all checked).\n\n1. A line.", JOBS)
    assert marked == ("Found 2 matching ads among the 6 in your selection (all checked). " + UNCONFIRMED_NOTE["en"] + "\n\n1. A line.")
    assert cc.mark_unconfirmed("在所选的 6 篇广告中找到 2 篇符合。", "哪几篇广告？") == "在所选的 6 篇广告中找到 2 篇符合。" + UNCONFIRMED_NOTE["zh"]
    full = cc.refusal("confirmation_registry_full", None, JOBS)
    assert (full.status, full.failure_reason) == ("limited", "confirmation_registry_full")
    invalid = cc.refusal("criterion_invalid", "too_many_rules", "哪几篇广告？", evidence=[])
    assert invalid.status == "insufficient_evidence" and invalid.answer == "规则最多 4 条。"
    assert invalid.structured_result == {"kind": "criterion_invalid", "detail": "too_many_rules", "limits": {"max_rules": 4, "max_exclusions": 3}}
    assert cc.refusal("continuation_invalid", "nonsense", JOBS).answer == "This confirmation is no longer valid; ask the question again."
    assert set(cc.CONFIRMATION_REFUSALS) == set(cc._REFUSALS)


# --- After the Codex pre-commit review: the promise of the card, the cost, the registry, the examples -----------


def test_a_confirmed_list_reads_the_whole_small_scope_whichever_way_the_triage_switch_flips(monkeypatch):
    # Card with the triage on, judged with it off: screening alone still reads every ad in scope.
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    assert card.structured_result["candidates"]["native"]["with_rules"] == "whole_scope"
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    result = continue_with(service, card, DRAFT)
    assert result.status == "answered" and calls.by_dataset["native"]["judge"] == []
    assert screened_records(calls) == {"n1", "n2", "n3", "n4", "n5", "n6"}
    assert result.research_trace["list_screening"]["first_read"] == 6 and "triage" not in result.research_trace["list_screening"]
    # Card with the triage off, judged with it on: the Decisions judge reads every ad in scope.
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert card.structured_result["condition"]["kind"] == "triage_off"
    assert card.structured_result["candidates"]["native"]["with_rules"] == "whole_scope"
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE")
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "answered" and len(calls.by_dataset["native"]["judge"]) == 6
    assert result.research_trace["list_screening"]["triage"]["whole_scope"] is True


def test_a_confirmed_large_scope_reads_every_candidate_without_the_stopping_rule(monkeypatch):
    from test_list_golden import N2, TEXT_RECORD, ad

    monkeypatch.setenv("OBS_ANSWER_NORMS", "off")
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE", raising=False)
    scenario = SCENARIOS["native_screen"]  # no Decisions client: screening alone
    quiet = [ad(f"q{k:02d}", 1, f"Quiet yard {k} opens on Monday.") for k in range(1, 45)]
    for item in quiet:
        monkeypatch.setitem(TEXT_RECORD, item.text, item.record_id)

    def service_with_many_candidates():
        db, ledger, calls = GoldenDb(large=True), Ledger(), Calls()
        db.search = lambda query, scope, **options: [*quiet, N2]  # the only match is the 45th candidate
        return Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls)), calls

    # Auto mode, as before: the first 40 candidates have no match, so reading stops before n2.
    service, calls = service_with_many_candidates()
    auto = service.answer(JOBS, NATIVE, "offline")
    # (Batches past the stopping point are dispatched in parallel and discarded, as before.)
    assert auto.status == "answered" and auto.citations == []
    assert "n2" not in {d["record_id"] for d in auto.research_trace["list_screening"]["decisions"]}
    # After a confirmation every retrieved candidate is read: n2 is found.
    service, calls = service_with_many_candidates()
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert card.structured_result["candidates"]["native"] == {"scope_total": 450, "retrieved": 45, "with_rules": "candidates",
                                                            "condition_only": "candidates"}
    assert "all 45 retrieved candidates will be judged" in card.answer
    result = continue_with(service, card, CONFIRMED)
    assert result.status == "answered" and {c.evidence_id for c in result.citations} == {"n2-e1"}  # listed, then summarised
    assert {d["record_id"]: d["decision"] for d in result.research_trace["list_screening"]["decisions"]}["n2"] == "matches"
    assert len(screened_records(calls)) == 45 and result.research_trace["list_screening"]["first_read"] == 45


def test_a_limit_after_settled_calls_keeps_them_in_the_ledger_and_fails_the_flow(monkeypatch):
    monkeypatch.setenv("OBS_ANSWER_NORMS", "off")
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE", raising=False)
    scenario = SCENARIOS["native_limit_reached"]
    db, ledger, calls = GoldenDb(), Ledger(limit_at=5), Calls()  # two screening batches settle, the re-reading is denied
    service = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls))
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    result = continue_with(service, card, CONFIRMED)
    settled = [item for item in ledger.closed if item[3] == "settled"]
    assert len(settled) == 2 and [item[3] for item in ledger.closed].count("denied") == 1
    # The answer's cost is its embedding plus the two settled screening batches, as the ledger has them.
    assert result.status == "limited" and result.cost_usd == pytest.approx(0.000001 + sum(item[5] for item in settled))
    assert result.research_trace["cost_basis"].startswith("embedding_and_settled_calls")
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"


def test_a_replayed_unfinished_answer_is_never_supplemented(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    service.settings = WEB_ON
    flow_id = card.structured_result["flow_id"]
    assert service.flows.claim(flow_id, "offline", cc.criterion_hash(DRAFT))[0] == "started"
    service.flows.finish(flow_id, Answer(status="insufficient_evidence", answer="Nothing listed.", research_trace={"flow_id": flow_id}))
    before = model_calls(calls)
    replayed = continue_with(service, card, DRAFT)
    assert replayed.status == "insufficient_evidence" and "continuation_replay" in replayed.research_trace
    assert not replayed.external_research and model_calls(calls) == before  # _search_external would raise


def test_a_compound_answer_with_its_own_failure_reason_still_protects_the_deferred_part(monkeypatch):
    part = {"question_part": JOBS, "dataset": "native", "route": "evidence",
            "result": {"filters": Filters(dataset="native", include_inferred_dates=True).model_dump(mode="json"),
                       "search_query": JOBS, "answer_shape": "every_matching_source"}}
    run = ResearchRun(route="composite", failure_reason="research_plan_invalid",
                      result={"status": "ok", "kind": "composite", "complete": False, "pending_parts": [], "parts": [part]})
    service, calls = agent_service(run, monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert (result.status, result.failure_reason) == ("insufficient_evidence", "research_plan_invalid")
    assert result.structured_result["incomplete_parts"][0]["failure_reason"] == "criterion_confirmation_required"
    assert not result.external_research and "collection_first_fallback" not in result.research_trace
    assert roles(calls) == ["embed"] and len(service.flows) == 0


def test_two_cards_drafted_at_once_keep_both_flows(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    service.flows = FlowRegistry(max_entries=1)
    original, entered, release = service._draft_criterion, threading.Event(), threading.Event()

    def blocking(question, visitor):
        entered.set()
        assert release.wait(10)
        return original(question, visitor)

    service._draft_criterion = blocking
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.setdefault("card", service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")))
    thread.start()
    assert entered.wait(10)
    other = service.answer(JOBS, NATIVE, "other-visitor", criterion_confirmation="ask")
    assert (other.status, other.failure_reason) == ("limited", "confirmation_registry_full")  # the preparing flow is not evicted
    release.set()
    thread.join(10)
    card = outcome["card"]
    assert pending_confirmation(card) and service.flows.snapshot(card.structured_result["flow_id"])["state"] == "pending"
    assert continue_with(service, card, DRAFT).status == "answered"  # the first card's token is good


def test_a_blank_draft_is_a_failed_draft_with_its_cost_kept(monkeypatch):
    from test_list_golden import reply

    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    parse = service.rag.client.responses.parse

    def blank_draft(**request):
        if request["text_format"] is CriterionDraft:
            calls.add(None, "criterion", {"model": request["model"], "messages": len(request["input"]),
                                          "question": request["input"][-1]["content"]})
            return reply(Criterion(counts=["   "], does_not_count=[]), 20, 10)
        return parse(**request)

    service.rag.client.responses.parse = blank_draft
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert card.structured_result["condition"]["kind"] == "draft_failed" and card.structured_result["criterion"] is None
    assert card.research_trace["criterion_draft"]["cost_usd"] == pytest.approx(0.000016)  # the call was made and settled
    assert [item[3] for item in ledger.closed] == ["cancelled", "settled"]
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "pending"
    assert continue_with(service, card, CONFIRMED).status == "answered"


def test_example_openings_are_verbatim_even_with_odd_spacing():
    sentence = "Tidal  kites\tbring " + "  ".join(f"word{n}" for n in range(1, 40)) + "."
    opening = cc._opening(sentence)
    assert sentence.startswith(opening) and len(opening.split()) == 30 and not opening.endswith(" ")
    assert cc._opening("One sentence.  Another one.") == "One sentence."
    evidence = [passage("n1", sentence)]
    example = cc.criterion_examples({"counts": ["Something unrelated entirely."], "does_not_count": []}, evidence, ["native"])[0]
    assert example["basis"] == "opening" and sentence.startswith(example["sentence"])


def test_a_version_change_during_retrieval_stops_before_any_judgment(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    before = model_calls(calls)
    search = service.db.search

    def search_then_update(query, scope, **options):
        found = search(query, scope, **options)
        service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}  # the collection moves under the retrieval
        return found

    service.db.search = search_then_update
    result = continue_with(service, card, DRAFT)
    assert (result.status, result.failure_reason) == ("service_unavailable", "data_changed_during_retrieval")
    assert calls.by_dataset["native"] == {"screen": [], "judge": []} and model_calls(calls) == before + 1  # the embedding only
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"
    service.db.health = lambda: {"status": "ok", "data_version": "golden-v1"}  # the entry check passes again
    assert continue_with(service, card, DRAFT).structured_result["detail"] == "flow_failed"


def test_the_api_round_trip_with_the_real_service(monkeypatch):
    from observatory.api import create_api

    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    details = SimpleNamespace(get=lambda record_id: None, attachment=lambda record_id, asset_id: None)
    client = create_api(service, SimpleNamespace(api_cors_origins=(), show_source_links=True), record_details=details).test_client()
    body = {"question": JOBS, "filters": {"dataset": "native"}, "criterion_confirmation": "ask"}
    first = client.post("/api/v1/ask", json=body, headers={"X-Visitor-Id": "r1"})
    card = first.get_json()
    assert first.status_code == 200 and card["structured_result"]["kind"] == "criterion_confirmation"
    assert [e["evidence_id"] for e in card["evidence"]] == ["n1-e1", "n2-e1", "n3-e1"]  # the compact body keeps the candidates
    assert "research_trace" not in card and isinstance(card["structured_result"]["continuation"], str)
    continuation = {"token": card["structured_result"]["continuation"], "criterion": card["structured_result"]["criterion"]}
    other = client.post("/api/v1/ask", json={"question": JOBS, "filters": {"dataset": "native"}, "continuation": continuation},
                        headers={"X-Visitor-Id": "r2"}).get_json()
    assert (other["failure_reason"], other["structured_result"]["detail"]) == ("continuation_invalid", "visitor")
    second = client.post("/api/v1/ask", json={"question": JOBS, "filters": {"dataset": "native"}, "continuation": continuation},
                         headers={"X-Visitor-Id": "r1"})
    judged = second.get_json()
    assert second.status_code == 200 and judged["status"] == "answered"
    assert judged["structured_result"]["criterion_source"] == "confirmed" and len(judged["citations"]) == 2
    assert {e["evidence_id"] for e in judged["evidence"]} >= {c["evidence_id"] for c in judged["citations"]}


def test_the_pending_window_starts_when_the_card_is_issued(monkeypatch):
    # The drafting takes 1,000 s on the registry's clock; the card is then good for a full window.
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    tick = {"now": 1000.0}
    service.flows = FlowRegistry(clock=lambda: tick["now"])
    original = service._draft_criterion

    def slow_draft(question, visitor):
        tick["now"] += 1000
        return original(question, visitor)

    service._draft_criterion = slow_draft
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert pending_confirmation(card)
    tick["now"] += 1799
    assert continue_with(service, card, DRAFT).status == "answered"
    # A preparation forgotten before the card is issued issues no card at all.
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    service.flows = FlowRegistry(clock=lambda: tick["now"])

    def very_slow_draft(question, visitor):
        tick["now"] += 1801
        return original(question, visitor)

    service._draft_criterion = very_slow_draft
    lost = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert (lost.status, lost.failure_reason) == ("service_unavailable", "confirmation_unavailable")
    assert not pending_confirmation(lost) and len(service.flows) == 0 and "ask the question again" in lost.answer


def test_a_version_change_during_the_later_reads_stops_before_any_judgment(monkeypatch):
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    before = model_calls(calls)
    read = service.db.record_passages

    def read_then_update(record_ids, scope, per_record=8):
        rows = read(record_ids, scope, per_record)
        service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}  # moves while whole articles are read
        return rows

    service.db.record_passages = read_then_update
    result = continue_with(service, card, DRAFT)
    assert (result.status, result.failure_reason) == ("service_unavailable", "data_changed_during_retrieval")
    assert calls.by_dataset["native"] == {"screen": [], "judge": []} and model_calls(calls) == before + 1
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"


@pytest.mark.parametrize("triage", ["on", "off"], ids=lambda value: f"triage_{value}")
def test_a_version_change_while_the_omitted_records_are_read_stops_before_any_judgment(monkeypatch, triage):
    # Every earlier read sees the card's version; only the whole-scope read of the records the
    # retrieval did not return (n4, n5, n6) moves it. Nothing may be judged after that read.
    service, scenario, card, calls, _ = card_for("native_triage", monkeypatch)
    if triage == "off":
        monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    before = model_calls(calls)
    read = service.db.record_passages

    def read_omitted_then_update(record_ids, scope, per_record=8):
        rows = read(record_ids, scope, per_record)
        if per_record is None and set(record_ids) == {"n4", "n5", "n6"}:
            service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}
        return rows

    service.db.record_passages = read_omitted_then_update
    result = continue_with(service, card, DRAFT)
    assert (result.status, result.failure_reason) == ("service_unavailable", "data_changed_during_retrieval")
    assert calls.by_dataset["native"] == {"screen": [], "judge": []} and model_calls(calls) == before + 1  # the embedding only
    assert service.flows.snapshot(card.structured_result["flow_id"])["state"] == "failed"
    assert result.cost_usd == pytest.approx(0.000001) and result.research_trace["cost_basis"].startswith("embedding_and_settled_calls")


def test_a_judged_list_reports_judging_during_the_screening_and_organizing_for_the_writer(monkeypatch):
    # Auto mode is unchanged: a list judged by the model's own draft never says "judging by the confirmed rules".
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    stages = []
    result = service.answer(JOBS, NATIVE, "offline", progress=stages.append)
    assert result.status == "answered" and "judging" not in stages
    assert stages.index("database") < stages.index("organizing") < stages.index("citations")


def test_a_confirmed_list_that_reads_its_matches_reports_judging_then_organizing(monkeypatch):
    # The source-reader branch: "organizing" starts with the reader, after the judging; the trace shows the reading.
    from test_list_criterion_mode import answer as evidence_answer
    stages = []
    result, calls, _ = evidence_answer("native_phrase_read", monkeypatch, criterion=CONFIRMED, criterion_source="edited",
                                       progress=stages.append)
    assert result.status == "answered" and "content_reading" in result.research_trace
    last_judging = len(stages) - 1 - stages[::-1].index("judging")
    assert stages.index("database") < last_judging < stages.index("organizing") < stages.index("citations")


def test_a_confirmed_list_without_matches_never_reaches_the_writer_stage(monkeypatch):
    from test_list_criterion_mode import answer as evidence_answer
    stages = []
    result, calls, _ = evidence_answer("native_zero_match", monkeypatch, criterion=CONFIRMED, criterion_source="edited",
                                       progress=stages.append)
    assert result.status == "answered" and not result.citations
    assert "judging" in stages and "organizing" not in stages and stages[-1] == "citations"


def test_a_confirmed_condition_without_rules_keeps_the_organizing_stage(monkeypatch):
    # Only rules a researcher confirmed or edited are "the confirmed rules": a confirmed condition alone is not.
    service, scenario, card, calls, _ = card_for("native_phrase_read", monkeypatch)
    stages = []
    result = service.answer(PHRASE_READ, NATIVE, "offline", progress=stages.append,
                            continuation={"token": card.structured_result["continuation"], "criterion": None})
    assert result.status == "answered" and "judging" not in stages and "organizing" in stages
