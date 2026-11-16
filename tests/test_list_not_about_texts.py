"""C24 (client meeting MT6-015): a list question that is not about the ads or posts is answered so.

The criterion draft says, in the same call, whether the question asks about what the ads or
posts say or show. Only an explicit "no" stops the list: nothing is triaged or screened, the
answer asks for another wording, and the draft's cost stays recorded. A reply without the
check, or an unusable one, lists as before. Fictional questions and the golden fixtures only.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_list_criterion_mode import roles, service_for
from test_list_golden import JOBS, reply

from observatory import relevance_triage
from observatory.models import Filters
from observatory.relevance_triage import NOT_ABOUT_THE_TEXTS, Criterion, CriterionDraft

NONSENSE = "Which ads do the harbor pebbles daydream about on Tuesdays?"
NONSENSE_ZH = "哪些广告是港口的鹅卵石在星期二梦见的？"


def drafting(about, counts=("The ad presents tidal kites as a source of jobs.",)):
    return CriterionDraft(about_the_texts=about, counts=list(counts), does_not_count=[])


def triage_rag(parsed):
    budget = SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock())
    parse = Mock(return_value=reply(parsed, 20, 10))
    return SimpleNamespace(budget=budget, client=SimpleNamespace(responses=SimpleNamespace(parse=parse), post=Mock()))


def test_the_draft_says_when_a_question_is_not_about_the_texts(monkeypatch):
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "on")
    rag = triage_rag(drafting(False))
    criterion, cost = relevance_triage.make_criterion(rag, NONSENSE, "visitor")
    assert criterion == NOT_ABOUT_THE_TEXTS and cost > 0
    request = rag.client.responses.parse.call_args.kwargs
    assert request["text_format"] is CriterionDraft and "First say whether the question can be answered by reading" in request["input"][0]["content"]
    assert rag.budget.settle.call_args.args[2]["observatory_request"]["prompt"] == relevance_triage.CRITERION_PROMPT
    # About the texts: the criterion alone, as before, without the check.
    criterion, _ = relevance_triage.make_criterion(triage_rag(drafting(True)), JOBS, "visitor")
    assert criterion == {"counts": ["The ad presents tidal kites as a source of jobs."], "does_not_count": []}


def test_only_an_explicit_and_valid_no_stops_the_list(monkeypatch):
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "on")
    # A reply without the check counts as about the texts.
    criterion, _ = relevance_triage.make_criterion(
        triage_rag(Criterion(counts=["Kites as a source of jobs."], does_not_count=[])), JOBS, "visitor")
    assert criterion == {"counts": ["Kites as a source of jobs."], "does_not_count": []}
    # An unusable reply is no criterion, whatever its check says: the list is screened as before.
    blank = CriterionDraft.model_construct(about_the_texts=False, counts=[], does_not_count=[])
    assert relevance_triage.make_criterion(triage_rag(blank), NONSENSE, "visitor")[0] is None
    # Rules that pass the reply format but not the criterion check (blank only) refuse nothing either:
    # the reply is returned as before (the card treats it as a failed draft) and its cost is kept.
    rag = triage_rag(drafting(False, counts=["   "]))
    criterion, cost = relevance_triage.make_criterion(rag, NONSENSE, "visitor")
    assert criterion == {"counts": ["   "], "does_not_count": []} and cost > 0
    assert rag.budget.settle.called


def test_blank_rules_marked_not_about_still_give_the_card(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    parse = service.rag.client.responses.parse

    def draft(**request):
        if request["text_format"] is CriterionDraft:
            return reply(drafting(False, counts=["   "]), 20, 10)
        return parse(**request)

    service.rag.client.responses.parse = draft
    card = service.answer(NONSENSE, Filters(dataset="native"), "offline", criterion_confirmation="ask")
    assert card.failure_reason == "criterion_confirmation_required"
    assert card.structured_result["condition"]["kind"] == "draft_failed"


def not_about(service, calls):
    parse = service.rag.client.responses.parse

    def draft(**request):
        if request["text_format"] is CriterionDraft:
            calls.add(None, "criterion", {"model": request["model"], "messages": len(request["input"]),
                                          "question": request["input"][-1]["content"]})
            return reply(drafting(False), 20, 10)
        return parse(**request)

    service.rag.client.responses.parse = draft


@pytest.mark.parametrize(("name", "noun", "embedded"),
                         [("native_triage", "ads", 1), ("both_triage", "ads or company posts", 2)])
def test_a_list_not_about_the_texts_judges_nothing_and_asks_for_another_wording(monkeypatch, name, noun, embedded):
    service, scenario, calls, ledger = service_for(name, monkeypatch)
    not_about(service, calls)
    result = service._answer_evidence(NONSENSE, Filters(**scenario.filters), "offline", audit=False)
    assert (result.status, result.answer_mode, result.failure_reason) == (
        "insufficient_evidence", "clarification", NOT_ABOUT_THE_TEXTS)
    assert result.answer == (
        f"This question does not seem to ask about anything the {noun} say or show, so none of them was read for "
        "it. Please ask it another way: about what they say or show, for example a topic, a claim, a product, "
        "a company, an outlet or a period.")
    # The drafting call only: no Decisions, screening or writer call, and nothing shown as read.
    assert roles(calls) == ["embed", "criterion"]
    assert all(calls.by_dataset[d] == {"screen": [], "judge": []} for d in calls.by_dataset)
    assert result.evidence == [] and result.citations == []
    assert result.research_trace["criterion_draft"]["status"] == NOT_ABOUT_THE_TEXTS
    assert result.research_trace["criterion_draft"]["cost_usd"] == pytest.approx(0.000016)
    assert result.cost_usd == pytest.approx(0.000016 + 0.000001 * embedded)  # the drafting call and the embedding


def test_the_chinese_wording(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    not_about(service, calls)
    result = service._answer_evidence(NONSENSE_ZH, Filters(dataset="native"), "offline", audit=False)
    assert result.failure_reason == NOT_ABOUT_THE_TEXTS and result.answer == ("这个问题看起来不是在问广告里的内容，所以没有逐条去看。请换个问法，问它们说了什么或展示了什么，"
                             "例如某个话题、说法、产品、公司、媒体或时间段。")


def test_ask_mode_gives_no_card_and_keeps_no_flow(monkeypatch):
    service, scenario, calls, ledger = service_for("native_triage", monkeypatch)
    not_about(service, calls)
    result = service.answer(NONSENSE, Filters(dataset="native"), "offline", criterion_confirmation="ask")
    assert result.failure_reason == NOT_ABOUT_THE_TEXTS and "continuation" not in (result.structured_result or {})
    assert roles(calls) == ["embed", "criterion"]
    assert service.flows._entries == {}  # the registered flow was discarded: nothing to confirm or continue
    service._search_external.assert_not_called()  # no web fallback for a question to rephrase
    assert result.cost_usd == pytest.approx(0.000016 + 0.000001)  # the embedding and the draft, each once
