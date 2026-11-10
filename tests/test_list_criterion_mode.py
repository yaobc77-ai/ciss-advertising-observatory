"""Pipeline step 3, S3-b: a criterion a researcher confirmed can enter the list route.

Fictional ads and posts (the golden fixtures of test_list_golden). Without a confirmed
criterion the list behaves as before: a criterion drafted from the question drives the
Decisions triage only and screening judges by the question. With one, nothing is drafted,
the triage judges by it when it is on, and screening is asked to judge by it too (the
user's decision of 2026-10-27, design 3.4a (b)); the quoted phrases every match must
contain still come from the question alone. The plan records the criterion mode ("ask"
for a call with a confirmed criterion), a plan asking for confirmation is never judged by
a draft, a confirmed criterion with an unconfirmed label or an "auto" plan is refused
before anything is spent, and plan_check compares the mode with what the list was judged by.
"""
import base64
import gzip
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_list_golden import (
    JOBS,
    LISTING,
    LITERAL,
    SCENARIOS,
    TEXT_RECORD,
    Calls,
    GoldenDb,
    Ledger,
    canon,
    golden_rag,
    reply,
)

from observatory.config import Settings
from observatory.list_screening import CONFIRMED_CRITERION_NOTE, Decision
from observatory.models import Answer, Filters
from observatory.question_plan import PLAN_VERSION, build_evidence_plan, plan_check
from observatory.service import Service

CONFIRMED = {"counts": ["The ad presents tidal kites as a source of jobs.",
                        "The ad says kites hire local crews."],
             "does_not_count": ["Jobs unrelated to kites."]}
# Rules a researcher wrote with sentences from the collection in quotation marks, as a
# positive and as a negative example.
QUOTING = {"counts": ['The ad says something like "Tidal kites will bring 400 jobs to the harbor."'],
           "does_not_count": ['Only festival notices such as "Our kite festival starts on Friday."']}
NOTE_HEAD = CONFIRMED_CRITERION_NOTE.split("{")[0].strip()
# Fictional screening norms: one norm per question type, the payload after it.
NORMS = {"version": "test-norms",
         "templates": {"r1_zero": "{norm}\n\n{question}", "r1_zero_three_shot": "{norm}\n\n{examples}\n\n{question}"},
         "types": {"mention": {"norm": "MENTION NORM: judge only whether the ad mentions the thing."},
                   "framing": {"norm": "FRAMING NORM: judge how the ad presents the thing."},
                   "general_list": {"norm": "GENERAL NORM."}}}


def service_for(name, monkeypatch, norms=None):
    if norms is None:
        monkeypatch.setenv("OBS_ANSWER_NORMS", "off")
    else:
        monkeypatch.delenv("OBS_ANSWER_NORMS", raising=False)
        monkeypatch.setenv("OBS_ANSWER_NORMS_B64", base64.b64encode(gzip.compress(json.dumps(norms).encode("utf-8"))).decode("ascii"))
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE", raising=False)
    scenario = SCENARIOS[name]
    db, ledger, calls = GoldenDb(), Ledger(), Calls()
    service = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls))
    service._search_external = Mock(side_effect=AssertionError("a list must not search the web"))
    return service, scenario, calls, ledger


def answer(name, monkeypatch, **extra):
    service, scenario, calls, ledger = service_for(name, monkeypatch)
    result = service._answer_evidence(scenario.question, Filters(**scenario.filters), "offline", audit=False,
                                      relation_listing=scenario.relation_listing, **extra)
    return result, calls, ledger


def roles(calls):
    return [call["role"] for call in calls.shared]


def screening_questions(calls, dataset="native"):
    return [call["question"] for call in calls.by_dataset[dataset]["screen"]]


def test_a_confirmed_criterion_is_not_drafted_and_drives_both_the_judge_and_the_screening(monkeypatch):
    result, calls, ledger = answer("native_triage", monkeypatch, criterion=CONFIRMED, criterion_source="edited")
    assert "criterion" not in roles(calls)  # nothing drafted
    judged = calls.by_dataset["native"]["judge"]
    assert len(judged) == 6 and all(call["questions"] == ["verdict", "strength", "rule_1", "rule_2", "exclusion_1"]
                                    for call in judged)  # two rules: the confirmed criterion, not the one-rule draft
    asked = screening_questions(calls)
    assert len(asked) == 2  # the first reading and the re-reading of n1 both carry the criterion
    for question in asked:
        assert question.startswith(JOBS) and NOTE_HEAD in question
        assert "(1) The ad presents tidal kites as a source of jobs." in question
        assert "(2) The ad says kites hire local crews." in question and "Exclusions: (1) Jobs unrelated to kites." in question
    trace = result.research_trace["list_screening"]
    assert trace["criterion"] == CONFIRMED and "criterion_draft" not in trace  # the draft is not known here
    assert (trace["criterion_source"], trace["screening_basis"]) == ("edited", "confirmed_criterion")
    assert [c.evidence_id for c in result.citations] == ["n1-e9", "n2-e1"]
    assert not [item for item in ledger.closed if item[3] == "settled" and item[4] == "criterion"]
    # The route's own plan says the criterion is confirmed first, and the check agrees.
    plan = result.research_trace["question_plan"]
    assert (plan["criterion_mode"], plan["reasons"]["criterion_mode"]) == ("ask", "caller:ask")
    assert plan_check(plan, result)["criterion_matches"] is True


def test_confirmed_and_edited_differ_only_in_the_recorded_source(monkeypatch):
    runs = {}
    for source in ("confirmed", "edited"):
        result, calls, ledger = answer("native_triage", monkeypatch, criterion=CONFIRMED, criterion_source=source)
        trace = dict(result.research_trace["list_screening"])
        assert trace.pop("criterion_source") == source
        runs[source] = (canon(calls.snapshot()), canon(ledger.snapshot()), canon(trace), result.answer,
                        [c.evidence_id for c in result.citations])
    assert runs["confirmed"] == runs["edited"]
    result, _, _ = answer("native_triage", monkeypatch, criterion=CONFIRMED)
    assert result.research_trace["list_screening"]["criterion_source"] == "confirmed"  # omitted: taken as given


@pytest.mark.parametrize("label", ["draft_unconfirmed", "none", "whatever"])
def test_a_criterion_with_an_unconfirmed_or_unknown_label_is_refused_before_anything_is_spent(monkeypatch, label):
    result, calls, ledger = answer("native_triage", monkeypatch, criterion=CONFIRMED, criterion_source=label)
    assert (result.status, result.failure_reason) == ("service_unavailable", "criterion_source_invalid")
    assert roles(calls) == [] and calls.by_dataset["native"] == {"screen": [], "judge": []} and ledger.closed == []
    assert result.research_trace["question_plan"]["criterion_mode"] == "ask"
    # The outer web supplement leaves an operational refusal alone even with web search on.
    service, scenario, _, _ = service_for("native_triage", monkeypatch)
    service.settings = replace(service.settings, web_search_enabled=True)
    assert service._ensure_answer(scenario.question, Filters(dataset="native"), "offline", result) is result


def test_a_passed_auto_plan_with_a_criterion_is_refused_not_judged(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    auto = build_evidence_plan(scenario.question, Filters(dataset="native"), triage_enabled=True)
    result = service._answer_evidence(scenario.question, Filters(dataset="native"), "offline", audit=False,
                                      plan=auto, criterion=CONFIRMED)
    assert (result.status, result.failure_reason) == ("service_unavailable", "criterion_plan_mismatch")
    assert roles(calls) == [] and ledger.closed == []
    service.settings = replace(service.settings, web_search_enabled=True)
    assert service._ensure_answer(scenario.question, Filters(dataset="native"), "offline", result) is result
    # A plan without a criterion to confirm (an exact-text list) may travel with one: nothing is judged anyway.
    literal_plan = build_evidence_plan(LITERAL, Filters(dataset="native"), triage_enabled=True)
    service, scenario, calls, _ = service_for("native_literal", monkeypatch)
    result = service._answer_evidence(LITERAL, Filters(dataset="native"), "offline", audit=False, plan=literal_plan, criterion=CONFIRMED)
    assert result.status == "answered" and result.structured_result["kind"] == "exact_text_list"
    assert "criterion_source" not in result.research_trace["list_screening"]


def test_a_known_draft_is_recorded_beside_the_confirmed_criterion(monkeypatch):
    draft = {"counts": ["The ad presents tidal kites as a source of jobs."], "does_not_count": []}
    result, _, _ = answer("native_triage", monkeypatch, criterion=CONFIRMED, criterion_source="edited", criterion_draft=draft)
    trace = result.research_trace["list_screening"]
    assert trace["criterion"] == CONFIRMED and trace["criterion_draft"] == draft


def test_quoted_sentences_in_confirmed_rules_are_not_literal_requirements(monkeypatch):
    # The screening question carries the rules, but the phrases every match must contain come
    # from the question alone: n1's matching sentence contains neither quoted sentence and still counts.
    result, calls, _ = answer("native_screen", monkeypatch, criterion=QUOTING)
    asked = screening_questions(calls)
    # S3-c: a confirmed list reads the whole small scope: six ads in two batches, then n1's re-reading.
    assert len(asked) == 3 and all(NOTE_HEAD in question and "kite festival starts on Friday" in question for question in asked)
    trace = result.research_trace["list_screening"]
    decisions = {d["record_id"]: d for d in trace["decisions"]}
    assert decisions["n1"]["decision"] == "matches" and decisions["n1"]["evidence_id"] == "n1-e9"
    assert decisions["n1"]["reread_from"] == "does_not_match"  # the re-reading also judged by the criterion
    assert "quote_not_in_passage" not in {d.get("reason") for d in trace["decisions"]}
    assert trace["screening_basis"] == "confirmed_criterion"


def test_without_a_triage_client_a_confirmed_criterion_still_reaches_the_screening(monkeypatch):
    # native_screen has no Decisions client: no judge calls, screening alone, by the confirmed criterion.
    result, calls, _ = answer("native_screen", monkeypatch, criterion=CONFIRMED)
    assert calls.by_dataset["native"]["judge"] == [] and "criterion" not in roles(calls)
    assert all(NOTE_HEAD in question for question in screening_questions(calls))
    trace = result.research_trace["list_screening"]
    assert "triage" not in trace and trace["criterion"] == CONFIRMED
    assert (trace["criterion_source"], trace["screening_basis"]) == ("confirmed", "confirmed_criterion")


def test_with_the_triage_switched_off_a_confirmed_criterion_still_reaches_the_screening(monkeypatch):
    # The client could reach the Decisions API, but the operator switched the triage off.
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    result = service._answer_evidence(scenario.question, Filters(dataset="native"), "offline", audit=False, criterion=CONFIRMED)
    assert calls.by_dataset["native"]["judge"] == [] and "criterion" not in roles(calls)
    assert len(screening_questions(calls)) == 3 and all(NOTE_HEAD in question for question in screening_questions(calls))
    trace = result.research_trace["list_screening"]
    assert "triage" not in trace and trace["screening_basis"] == "confirmed_criterion"
    assert result.research_trace["question_plan"]["criterion_available"] is False


def test_when_every_judge_call_fails_the_screening_still_judges_by_the_confirmed_criterion(monkeypatch):
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    service.rag.client.post = Mock(side_effect=ConnectionError("down"))
    result = service._answer_evidence(scenario.question, Filters(dataset="native"), "offline", audit=False, criterion=CONFIRMED)
    trace = result.research_trace["list_screening"]
    assert trace["triage"]["judged"] == 0 and trace["triage"]["triaged"] == 6  # every ad went to screening
    assert all(NOTE_HEAD in question for question in screening_questions(calls))
    assert {d["record_id"]: d["route"] for d in trace["decisions"]}["n1"] == "pass"  # screening alone decides
    assert trace["screening_basis"] == "confirmed_criterion"


def test_lists_that_never_judge_do_not_ask_whether_the_triage_is_on(monkeypatch):
    monkeypatch.setattr("observatory.service.triage_enabled", Mock(side_effect=AssertionError("the triage flag was asked")))
    for name in ("native_literal", "social_relation_list"):
        result, _, _ = answer(name, monkeypatch)
        assert result.status == "answered"
    result, _, _ = answer("native_literal", monkeypatch, criterion=CONFIRMED)
    assert result.structured_result["kind"] == "exact_text_list"


def test_with_norms_on_the_type_comes_from_the_question_and_the_prompt_carries_the_criterion(monkeypatch):
    service, scenario, calls, _ = service_for("native_screen", monkeypatch, norms=NORMS)
    created = []

    def create(**request):
        prompt = request["input"][1]["content"]
        created.append(prompt)
        payload = json.loads(prompt.rsplit("\n\n", 1)[1])  # the template puts the payload last
        decisions = []
        for item in payload["ads"]:
            hit = next((p for p in item["passages"] if "jobs" in p["text"].casefold()), None)
            decisions.append(Decision(ref=item["ref"], decision="matches" if hit else "does_not_match",
                                      passage_id=hit["passage_id"] if hit else "", quote=hit["text"] if hit else ""))
        answer_json = json.dumps({"decisions": [d.model_dump() for d in decisions]})
        return SimpleNamespace(status="completed", output_text=f"<think>checked</think><answer>{answer_json}</answer>",
                               usage=reply(None, 10, 5).usage)

    service.rag.client.responses.create = create
    # No question mark: a type read from the question with the criterion appended would see
    # "presents" in the rules and pick the framing norm; the question itself asks about mentions.
    question = "List the ads that mention tidal kites as a source of jobs"
    result = service._answer_evidence(question, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source", criterion=CONFIRMED)
    assert result.status == "answered" and [c.evidence_id for c in result.citations][-2:] == ["n1-e9", "n2-e1"]
    assert len(created) == 3 and all(prompt.startswith("MENTION NORM") for prompt in created)
    for prompt in created:
        norm, payload_text = prompt.split("\n\n", 1)
        payload = json.loads(payload_text)
        assert payload["question"].startswith(question) and NOTE_HEAD in payload["question"]
        assert "(1) The ad presents tidal kites as a source of jobs." in payload["question"]
        assert {TEXT_RECORD[p["text"]] for item in payload["ads"] for p in item["passages"]} <= {"n1", "n2", "n3", "n4", "n5", "n6"}
    assert calls.by_dataset["native"]["screen"] == []  # the tagged call answered; no structured fallback
    trace = result.research_trace["list_screening"]
    assert trace["screening_basis"] == "confirmed_criterion" and all(d.get("screening_reasoning") == "checked" for d in trace["decisions"])


def test_auto_mode_records_the_draft_as_unconfirmed_and_screens_by_the_question(monkeypatch):
    result, calls, _ = answer("native_triage", monkeypatch)
    trace = result.research_trace["list_screening"]
    assert roles(calls)[:2] == ["embed", "criterion"]
    assert (trace["criterion_source"], trace["screening_basis"]) == ("draft_unconfirmed", "question")
    assert trace["criterion_draft"] == trace["criterion"]
    assert all(question == JOBS for question in screening_questions(calls))
    plan = result.research_trace["question_plan"]
    assert (plan["criterion_mode"], plan["criterion_available"]) == ("auto", True)
    assert plan_check(plan, result)["criterion_matches"] is True
    plain, calls, _ = answer("native_screen", monkeypatch)
    trace = plain.research_trace["list_screening"]
    assert (trace["criterion_source"], trace["screening_basis"]) == ("none", "question") and "criterion_draft" not in trace
    assert plain.research_trace["question_plan"]["criterion_available"] is False  # no Decisions client


def test_a_plan_asking_for_confirmation_is_refused_without_a_confirmed_criterion(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    plan = build_evidence_plan(scenario.question, Filters(dataset="native"), triage_enabled=True, criterion_confirmation="ask")
    result = service._answer_evidence(scenario.question, Filters(dataset="native"), "offline", audit=False, plan=plan)
    assert (result.status, result.answer_mode, result.failure_reason) == (
        "insufficient_evidence", "clarification", "criterion_confirmation_required")
    assert roles(calls) == ["embed"] and calls.by_dataset["native"] == {"screen": [], "judge": []}  # no draft, no judging
    assert [item[3] for item in ledger.closed] == ["cancelled"]  # only the question's own reservation, cancelled unsent
    assert "list_screening" not in result.research_trace and result.evidence  # the candidates are shown
    # Not an evidence shortfall: the outer web supplement leaves it alone even with web search on.
    service.settings = replace(service.settings, web_search_enabled=True)
    assert service._ensure_answer(scenario.question, Filters(dataset="native"), "offline", result) is result
    assert plan_check(plan.as_dict(), result)["criterion_matches"] is None  # nothing judged yet: unknown


def test_lists_without_model_screening_carry_no_criterion_keys(monkeypatch):
    for name in ("native_literal", "social_relation_list"):
        result, _, _ = answer(name, monkeypatch)
        trace = result.research_trace["list_screening"]
        assert "criterion_source" not in trace and "screening_basis" not in trace and "criterion_draft" not in trace
        plan = result.research_trace["question_plan"]
        assert plan["criterion_mode"] == "none" and plan_check(plan, result)["criterion_matches"] is True


def test_the_plan_records_the_criterion_mode_and_whether_one_would_be_drafted():
    native = Filters(dataset="native")
    auto = build_evidence_plan(JOBS, native, triage_enabled=True)
    assert (auto.criterion_mode, auto.criterion_available, auto.reasons["criterion_mode"]) == ("auto", True, "default:auto")
    assert build_evidence_plan(JOBS, native, triage_enabled=False).criterion_available is False
    assert build_evidence_plan(JOBS, native).criterion_available is None  # the caller did not say
    asked = []
    assert build_evidence_plan(JOBS, native, triage_enabled=lambda: asked.append(1) or True).criterion_available is True
    assert asked == [1]  # a callable flag is asked once, for a screened list
    ask = build_evidence_plan(JOBS, native, triage_enabled=True, criterion_confirmation="ask")
    assert (ask.criterion_mode, ask.criterion_available, ask.reasons["criterion_mode"]) == ("ask", True, "caller:ask")
    # Quoted phrases and a relation hint draft no criterion; a literal or relation list has no mode.
    assert build_evidence_plan('Which ads mention "tidal kite" as a source of jobs?', native, triage_enabled=True).criterion_available is False
    hinted = build_evidence_plan("Which posts use #KitePower?", Filters(dataset="social", record_ids=["s1"]),
                                 relation_listing={**LISTING, "list_all": False}, triage_enabled=True)
    assert hinted.criterion_mode == "auto" and hinted.criterion_available is False and hinted.signals["relation_hint"] is True
    never = []
    literal = build_evidence_plan(LITERAL, native, triage_enabled=lambda: never.append(1) or True)
    assert (literal.criterion_mode, literal.criterion_available, literal.reasons["criterion_mode"]) == ("none", False, "kind:literal")
    assert never == []  # a list that never judges does not ask
    relation = build_evidence_plan("Which posts use #KitePower?", Filters(dataset="social", record_ids=["s1"]),
                                   relation_listing=LISTING, triage_enabled=True)
    assert (relation.criterion_mode, relation.reasons["criterion_mode"]) == ("none", "kind:relation")
    assert relation.signals["relation_hint"] is False  # a relation list is listed, not hinted
    prose = build_evidence_plan("What do the ads say about harbor power?", native, triage_enabled=True)
    assert (prose.criterion_mode, prose.criterion_available, prose.reasons["criterion_mode"]) == ("none", False, "shape:answer")
    assert build_evidence_plan(LITERAL, native, criterion_confirmation="ask").criterion_mode == "none"  # nothing to confirm
    assert auto.version == PLAN_VERSION == "question-plan-v4"


def listed(source=None, pending=False, method="ai_screening"):
    screening = {"method": method, **({"criterion_source": source} if source else {})}
    structured = {"kind": "criterion_confirmation"} if pending else {"kind": "ai_screened_list"}
    return Answer(status="insufficient_evidence" if pending else "answered", answer="",
                  research_trace={} if pending else {"list_screening": screening},
                  structured_result=structured, answer_mode="clarification" if pending else "rag")


def test_plan_check_compares_the_criterion_mode_with_what_the_list_was_judged_by():
    def check(mode, result):
        return plan_check({"criterion_mode": mode, "shape": "list"}, result)["criterion_matches"]

    assert check("auto", listed("draft_unconfirmed")) is True and check("auto", listed("none")) is True
    assert check("auto", listed("confirmed")) is False and check("auto", listed(pending=True)) is False
    assert check("auto", Answer(status="service_unavailable", answer="")) is None  # never screened: unknown
    assert check("auto", listed()) is False  # a screened list without a recorded source is a mismatch, not unknown
    assert check("none", Answer(status="answered", answer="")) is True and check("none", listed("draft_unconfirmed")) is False
    assert check("none", listed(method="exact_text")) is True and check("none", listed()) is False
    assert check("ask", listed(pending=True)) is True and check("ask", listed("edited")) is True
    assert check("ask", listed("draft_unconfirmed")) is False and check("ask", Answer(status="limited", answer="")) is None
    assert check("ask", listed()) is False
    assert check(None, listed("confirmed")) is None
    assert plan_check({"criterion_mode": "auto"}, listed("confirmed"))["actual"]["criterion_source"] == "confirmed"
    bare = SimpleNamespace(research_trace={}, external_research={}, status="answered", answer_mode="rag",
                           failure_reason="", structured_result=None)
    assert plan_check({}, bare)["criterion_matches"] is None
