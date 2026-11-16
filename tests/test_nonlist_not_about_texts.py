"""C24 for questions that are not lists (plan step 5b, client meeting MT6-015).

An answer that is not a list and found no supporting evidence would next search the web. Before
that, the same drafting call a list makes says whether the question is about what the ads or
posts say or show; only an explicit, valid "no" turns the answer into the request to ask
another way, with no evidence shown and no web search. Everything else is as before. Fictional
questions and the golden fixtures only.
"""
from unittest.mock import Mock

import pytest
from test_list_criterion_mode import service_for
from test_list_without_agent import StubAgent, agent_service

from observatory.budget import LimitReached
from observatory.config import Settings
from observatory.models import Answer, Evidence, Filters
from observatory.relevance_triage import NOT_ABOUT_THE_TEXTS
from observatory.research_agent import ResearchRun
from observatory.service import Service

NONSENSE = "What do the harbor pebbles daydream about on Tuesdays?"
NONSENSE_ZH = "港口的鹅卵石星期二在梦见什么？"
ABOUT = "What do the ads say about tidal kites?"
RULES = {"counts": ["The ad mentions tidal kites."], "does_not_count": []}


def evidence():
    return Evidence(evidence_id="e1", record_id="r1", dataset="native", title="Kites", text="Tidal kites.",
                    version_id="v1", start=0, end=12, score=1.0, source_url="https://example.test/kites")


def short_answer(**extra):
    fields = {"status": "insufficient_evidence", "answer": "The selected records do not provide sufficient evidence.",
              "evidence": [evidence()], "cost_usd": 0.01, "research_trace": {"route": "evidence"}}
    return Answer(**{**fields, **extra})


def service(draft=(NOT_ABOUT_THE_TEXTS, 0.0003)):
    item = Service(Settings(), db=object(), rag=object())
    item._draft_criterion = Mock(side_effect=draft) if isinstance(draft, BaseException) else Mock(return_value=draft)
    item._search_external = Mock(return_value={"status": "unresolved", "reason": "no_results", "cost_usd": 0.002})
    item.health = Mock(return_value={"status": "ok", "data_version": "v1"})
    return item


@pytest.mark.parametrize(("dataset", "noun"), [("native", "ads"), ("social", "company posts"),
                                                ("all", "ads or company posts")])
def test_a_short_answer_not_about_the_texts_asks_for_another_wording_without_the_web(dataset, noun):
    item = service()
    shown = short_answer(structured_result={"kind": "evidence_overview"},
                         citations=[{"evidence_id": "e1", "quote": "Tidal kites."}])
    shown.media_evidence = [Mock()]  # anything shown below the answer is cleared
    result = item._ensure_answer(NONSENSE, Filters(dataset=dataset), "v", shown)
    assert (result.status, result.answer_mode, result.failure_reason) == (
        "insufficient_evidence", "clarification", NOT_ABOUT_THE_TEXTS)
    assert result.answer == (
        f"This question does not seem to ask about anything the {noun} say or show, so it cannot be answered "
        "from them. Please ask it another way: about what they say or show, for example a topic, a claim, a "
        "product, a company, an outlet or a period.")
    assert result.evidence == [] and result.citations == [] and result.media_evidence == []
    assert result.structured_result is None
    item._search_external.assert_not_called()
    item._draft_criterion.assert_called_once_with(NONSENSE, "v")
    assert result.cost_usd == pytest.approx(0.0103)  # the answer so far and the check
    assert result.research_trace["about_check"] == {
        "status": NOT_ABOUT_THE_TEXTS, "cost_usd": 0.0003,
        "replaced": {"answer_mode": "rag", "failure_reason": ""}}
    assert result.research_trace["route"] == "evidence"  # the rest of the trace is kept


def test_the_chinese_wording():
    result = service()._ensure_answer(NONSENSE_ZH, Filters(dataset="native"), "v", short_answer())
    assert result.answer == ("这个问题看起来不是在问广告里的内容，所以没法从它们回答。请换个问法，问它们说了什么或展示了什么，"
                             "例如某个话题、说法、产品、公司、媒体或时间段。")


@pytest.mark.parametrize("mode", ["clarification", "tools", "statistics"])
def test_only_answers_written_from_passages_are_checked(mode):
    # The check called valid count and metadata questions "not about the texts" (paid run, 2026-11-10).
    item = service()
    original = short_answer(answer_mode=mode, failure_reason="research_plan_clarification",
                            answer="Which company do you mean?", evidence=[])
    result = item._ensure_answer(NONSENSE, Filters(dataset="native"), "v", original)
    item._draft_criterion.assert_not_called()
    assert result.failure_reason != NOT_ABOUT_THE_TEXTS


@pytest.mark.parametrize(("draft", "status", "cost"), [
    ((RULES, 0.0003), "about", 0.0003),          # about the texts
    ((None, 0.0), "unchecked", 0.0),             # triage off, a failed or unusable call
    (LimitReached("limit"), "limited", 0.0),     # the check's reservation refused
])
def test_anything_but_an_explicit_no_searches_the_web_as_before(draft, status, cost):
    item = service(draft)
    original = short_answer()
    before = original.model_dump(include={"answer", "answer_mode", "failure_reason", "evidence"})
    result = item._ensure_answer(ABOUT, Filters(dataset="native"), "v", original)
    item._search_external.assert_called_once()
    # Nothing of the answer changed but its cost and trace (a snapshot: the answer is changed in place).
    assert result.model_dump(include={"answer", "answer_mode", "failure_reason", "evidence"}) == before
    assert result.research_trace["about_check"] == {"status": status, "cost_usd": cost}
    assert result.cost_usd == pytest.approx(0.01 + cost + 0.002)


@pytest.mark.parametrize("original", [
    short_answer(status="answered"),                                           # an answer: never checked
    short_answer(research_trace={"list_screening": {"decisions": []}}),        # a list: checked by its draft
    short_answer(research_trace={"about_check": {"status": "about", "cost_usd": 0.0003}}),  # checked already
    short_answer(structured_result={"kind": "composite", "parts": []}),       # parts keep their own outcome
    short_answer(failure_reason="named_source_not_in_collection"),             # a protected reason
    short_answer(external_research={"status": "disabled", "reason": "web_search_not_enabled", "cost_usd": 0.0}),
])
def test_answers_that_are_not_checked(original):
    item = service()
    item._ensure_answer(ABOUT, Filters(dataset="native"), "v", original)
    item._draft_criterion.assert_not_called()


def test_a_collection_only_question_is_not_checked():
    item = service()
    item._ensure_answer("Only using the collection, what do the pebbles dream?", Filters(dataset="native"), "v",
                        short_answer())
    item._draft_criterion.assert_not_called()
    item._search_external.assert_not_called()


def not_supported(*_args, **_kwargs):
    return Answer(status="insufficient_evidence", answer="The selected records do not provide sufficient evidence.",
                  cost_usd=0.0)


def test_the_evidence_route_checks_before_its_own_web_search(monkeypatch):
    item, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    item.rag.generate = Mock(side_effect=not_supported)
    item._draft_criterion = Mock(return_value=(NOT_ABOUT_THE_TEXTS, 0.0003))
    result = item._answer_evidence(NONSENSE, Filters(dataset="native"), "offline", audit=False)
    assert "list_screening" not in result.research_trace  # not a list: the writer answered
    item.rag.generate.assert_called_once()
    assert result.failure_reason == NOT_ABOUT_THE_TEXTS and result.evidence == []
    item._search_external.assert_not_called()  # the fixture fails the test on any web search
    # _ensure_answer sees the checked answer and neither checks nor searches again.
    assert item._ensure_answer(NONSENSE, Filters(dataset="native"), "offline", result) is result
    item._draft_criterion.assert_called_once()


def test_the_evidence_route_searches_the_web_when_the_question_is_about_the_texts(monkeypatch):
    item, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    item.rag.generate = Mock(side_effect=not_supported)
    item._draft_criterion = Mock(return_value=(RULES, 0.0003))
    item._search_external = Mock(return_value={"status": "unresolved", "reason": "no_results", "cost_usd": 0.0})
    result = item._answer_evidence(ABOUT, Filters(dataset="native"), "offline", audit=False)
    item._search_external.assert_called_once()
    assert result.research_trace["about_check"]["status"] == "about"
    assert result.failure_reason != NOT_ABOUT_THE_TEXTS


def test_a_list_still_makes_no_extra_check(monkeypatch):
    item, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    item._refuse_if_not_about = Mock(side_effect=AssertionError("a list is checked by its own draft"))
    result = item._answer_evidence(scenario.question, Filters(**scenario.filters), "offline", audit=False)
    assert "list_screening" in result.research_trace


@pytest.mark.parametrize(("question", "extra"), [
    ("Only using the collection, what do the pebbles dream?", {}),        # the web step would skip it
    (NONSENSE, {"failure_reason": "named_source_not_in_collection"}),     # a reason that is the answer
    (NONSENSE, {"failure_reason": "data_changed_during_generation"}),
    (NONSENSE, {"external_research": {"status": "unresolved", "reason": "no_results", "cost_usd": 0.002}}),
])
def test_the_check_applies_the_web_steps_exemptions_itself(question, extra):
    item = service()
    original = short_answer(**extra)
    before = original.model_dump()
    assert item._refuse_if_not_about(question, Filters(dataset="native"), "v", original) is False
    item._draft_criterion.assert_not_called()
    assert original.model_dump() == before  # nothing charged, nothing changed


def test_the_evidence_route_does_not_check_a_collection_only_question(monkeypatch):
    item, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    item.rag.generate = Mock(side_effect=not_supported)
    item._draft_criterion = Mock(return_value=(NOT_ABOUT_THE_TEXTS, 0.0003))
    question = "Only using the collection, what do the harbor pebbles daydream about?"
    result = item._answer_evidence(question, Filters(dataset="native"), "offline", audit=False)
    assert result.status == "insufficient_evidence" and result.failure_reason != NOT_ABOUT_THE_TEXTS
    assert item._ensure_answer(question, Filters(dataset="native"), "offline", result) is result
    item._draft_criterion.assert_not_called()
    item._search_external.assert_not_called()


def evidence_answer(monkeypatch, check_cost, web_cost):
    item, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    item.rag.generate = Mock(side_effect=not_supported)
    item._draft_criterion = Mock(return_value=(RULES, check_cost))
    item._search_external = Mock(return_value={"status": "unresolved", "reason": "no_results", "cost_usd": web_cost})
    result = item._answer_evidence(ABOUT, Filters(dataset="native"), "offline", audit=False)
    return item, item._ensure_answer(ABOUT, Filters(dataset="native"), "offline", result)


def test_an_answer_about_the_texts_is_checked_and_searched_once_across_both_entries(monkeypatch):
    _, free = evidence_answer(monkeypatch, 0.0, 0.0)  # the same answer with a free check and web search
    item, result = evidence_answer(monkeypatch, 0.0003, 0.002)
    item._draft_criterion.assert_called_once()
    item._search_external.assert_called_once()
    assert result.cost_usd == pytest.approx(free.cost_usd + 0.0003 + 0.002)  # each charged exactly once


def test_the_tool_path_keeps_the_check_in_the_trace_it_rebuilds(monkeypatch):
    run = ResearchRun(route="evidence", result={
        "filters": Filters(dataset="native", include_inferred_dates=True).model_dump(mode="json"),
        "search_query": NONSENSE, "answer_shape": "named_sources"}, cost_usd=0.002)
    item, calls, ledger = agent_service("native_triage", monkeypatch, switch=True, agent=StubAgent(run))
    item.rag.generate = Mock(side_effect=not_supported)
    item._draft_criterion = Mock(return_value=(NOT_ABOUT_THE_TEXTS, 0.0003))
    item._search_external = Mock(side_effect=AssertionError("no web search for a question to rephrase"))
    result = item.answer(NONSENSE, Filters(dataset="native"), "offline")
    assert result.failure_reason == NOT_ABOUT_THE_TEXTS and result.evidence == []
    assert result.research_trace["about_check"]["status"] == NOT_ABOUT_THE_TEXTS  # kept by the agent's audit
    assert result.research_trace["policy"]  # the rebuilt trace (the agent's audit), not the evidence route's
    item._draft_criterion.assert_called_once()
