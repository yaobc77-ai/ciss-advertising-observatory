"""Pipeline step 1: the QuestionPlan mirrors today's decisions into the run record without changing behaviour.

Fictional questions and records only, written against the product interfaces
(Service, ResearchRun) so this module stays in the free completion gate. The plan
is built from the understanding stage (question, scope, agent run); plan_check
compares it with the final answer.
"""
from types import SimpleNamespace

import pytest

from observatory.config import Settings
from observatory.models import Answer, Filters
from observatory.question_plan import PLAN_VERSION, build_question_plan, plan_check
from observatory.question_policy import question_contract
from observatory.research_agent import ResearchRun
from observatory.service import Service

RULE_LIST = "Which native ads mention tidal kites?"
UNRULED_LIST = "讲潮汐风筝的广告都是哪几篇？"
PLAIN = "What do the ads say about harbor power?"
COUNT = "How many ads come from Harbor Daily?"


def run_for(route, result=None, failure_reason=""):
    return SimpleNamespace(route=route, result=result or {}, failure_reason=failure_reason)


class ScriptedAgent:
    """Returns one prepared ResearchRun, as the research agent would."""

    def __init__(self, run):
        self.result = run
        self.calls = []

    def run(self, question, filters, visitor):
        self.calls.append((question, filters, visitor))
        self.result.original_question = question
        self.result.base_filters = filters.model_dump(mode="json")
        return self.result


class ReadOnlyDatabase:
    def __init__(self):
        self.version = "fictional-v1:index1"
        self.saved = []

    def health(self):
        return {"status": "ok", "data_version": self.version}

    def public_rows(self, _filters):
        return []

    def search(self, _query, _filters, **_kwargs):
        return []

    def save_answer(self, *args):
        self.saved.append(args)


def count_result():
    return {
        "status": "ok", "kind": "count", "method": "database", "group_by": None,
        "filters": Filters(publishers=["Harbor Daily"], include_inferred_dates=True).model_dump(mode="json"),
        "collections": [{"dataset": "native", "total": 7, "retrievable": 5, "unknown_dates": 1}],
        "groups": [], "records": [], "scope_notes": ["Stored records only."],
    }


def service_for(run):
    db = ReadOnlyDatabase()
    service = Service(Settings(research_agent_enabled=True), db=db, rag=object(), research_agent=ScriptedAgent(run))
    return service, db


def test_rule_list_over_both_collections_is_a_screened_list_without_web_help():
    assert question_contract(RULE_LIST)["requires_complete_list"] is True
    base = Filters(dataset="all")
    plan = build_question_plan(RULE_LIST, base, run_for("evidence", {"filters": base.model_dump(mode="json"),
                                                                    "search_query": "tidal kites"}), base)
    assert plan.version == PLAN_VERSION
    assert (plan.route, plan.agent_route, plan.shape, plan.list_kind) == ("evidence", "evidence", "list", "screen")
    assert plan.datasets_requested == plan.datasets == ["native", "social"]
    assert plan.search_query == "tidal kites" and plan.reasons["search_query"] == "planner"
    assert plan.allow_web is False and plan.reasons["allow_web"] == "rule:list_screened"
    assert plan.reasons["shape"] == "rule:requires_complete_list"
    assert plan.signals["rule_list"] is True and plan.signals["planner_shape"] is None


def test_planner_declared_list_the_rule_misses_is_recorded_as_planner_decided():
    assert question_contract(UNRULED_LIST)["requires_complete_list"] is False
    base = Filters(dataset="native")
    plan = build_question_plan(UNRULED_LIST, base,
                               run_for("evidence", {"filters": base.model_dump(mode="json"), "answer_shape": "every_matching_source"}),
                               base)
    assert plan.shape == "list" and plan.list_kind == "screen"
    assert plan.reasons["shape"] == "planner:answer_shape"
    assert plan.datasets == ["native"]


def test_rule_and_planner_agreement_is_kept_for_review():
    base = Filters(dataset="native")
    plan = build_question_plan(RULE_LIST, base,
                               run_for("evidence", {"filters": base.model_dump(mode="json"), "answer_shape": "every_matching_source"}),
                               base)
    assert plan.reasons["shape"] == "rule_and_planner"


def test_labels_over_both_collections_keep_the_list_signal_but_are_not_screened():
    # Mirrors _answer_evidence: both_list needs dataset 'all' without labels.
    base = Filters(dataset="all", labels=["energy"])
    plan = build_question_plan(RULE_LIST, base, run_for("evidence", {"filters": base.model_dump(mode="json")}), base)
    assert plan.shape == "answer" and plan.list_kind is None
    assert plan.reasons["shape"] == "list_signal_not_screenable"
    assert plan.allow_web is True


def test_relation_listing_over_selected_posts_is_a_relation_list():
    narrowed = Filters(dataset="social", record_ids=["p1", "p2"])
    data = {"filters": narrowed.model_dump(mode="json"),
            "relation_listing": {"list_all": True, "selections": [{"relations": {"replies_to": ["acct"]}}]}}
    plan = build_question_plan("Show the replies to that account", Filters(dataset="all"), run_for("evidence", data), narrowed)
    assert plan.shape == "list" and plan.list_kind == "relation"
    assert plan.reasons["shape"] == "planner:relation_listing"
    assert plan.datasets_requested == ["native", "social"] and plan.datasets == ["social"]
    assert plan.reasons["datasets"] == "filters:narrowed" and plan.filters["record_ids"] == ["p1", "p2"]


def test_one_quoted_phrase_asked_literally_is_a_literal_list():
    base = Filters(dataset="native")
    question = 'Which ads mention "tidal kite"?'
    plan = build_question_plan(question, base, run_for("evidence", {"filters": base.model_dump(mode="json")}), base)
    assert plan.shape == "list" and plan.list_kind == "literal"
    assert plan.signals["quoted_phrases"] == 1 and plan.signals["pure_literal"] is True


def test_comparison_groups_are_never_screened_as_lists():
    base = Filters(dataset="native")
    data = {"filters": base.model_dump(mode="json"), "retrieval_groups": [{"query": "a"}, {"query": "b"}]}
    plan = build_question_plan(RULE_LIST, base, run_for("evidence", data), base)
    assert plan.shape == "answer" and plan.signals["retrieval_groups"] is True


def test_collection_only_wording_forbids_web_help_for_an_ordinary_answer():
    base = Filters()
    plan = build_question_plan("Only use the collection: " + PLAIN, base,
                               run_for("evidence", {"filters": base.model_dump(mode="json")}), base)
    assert plan.shape == "answer" and plan.search_query == "Only use the collection: " + PLAIN
    assert plan.reasons["search_query"] == "default:question"
    assert plan.allow_web is False and plan.reasons["allow_web"] == "rule:collection_only"
    assert plan.signals["collection_only"] is True


@pytest.mark.parametrize("agent_route, route, shape", [
    ("statistics", "statistics", "table"), ("metadata", "metadata", "table"), ("graph", "records", "table"),
    ("sources", "records", "table"), ("record", "records", "table"), ("claims", "claims", "table"),
    ("content_matches", "claims", "table"), ("limited", "limited", "answer"), ("unavailable", "unavailable", "answer"),
])
def test_structured_and_terminal_routes_are_grouped_and_never_supplemented(agent_route, route, shape):
    plan = build_question_plan("How many ads per outlet?", Filters(), run_for(agent_route, failure_reason="x"))
    assert (plan.route, plan.agent_route, plan.shape) == (route, agent_route, shape)
    assert plan.allow_web is False and plan.reasons["allow_web"] == f"route:{route}"
    assert plan.search_query is None and plan.failure_reason == "x"
    assert plan.reasons["datasets"] == "filters:user"


def test_clarification_keeps_the_message_and_allows_web_help():
    plan = build_question_plan("那家公司有多少广告", Filters(), run_for("clarify", {"message": "请确认公司的名称。"}, "research_intent_unresolved"))
    assert plan.route == plan.agent_route == "clarify" and plan.clarify_message == "请确认公司的名称。"
    assert plan.allow_web is True and plan.reasons["route"] == "agent:clarify"


def test_as_dict_is_a_detached_copy():
    plan = build_question_plan(PLAIN, Filters(), run_for("evidence", {"filters": Filters().model_dump(mode="json")}), Filters())
    first, second = plan.as_dict(), plan.as_dict()
    first["reasons"]["shape"] = "edited"
    assert second["reasons"]["shape"] == "default" and plan.reasons["shape"] == "default"


def answer(**kwargs):
    return Answer(**{"status": "answered", "answer": "text", **kwargs})


def test_plan_check_reads_the_shape_from_the_answer_and_marks_unknowns_none():
    plan = {"version": PLAN_VERSION, "shape": "list", "allow_web": False}
    screened = answer(answer_mode="rag", research_trace={"list_screening": {"examined": 3}})
    check = plan_check(plan, screened)
    assert check["shape_matches"] is True and check["web_matches"] is None and check["actual"]["shape"] == "list"
    prose = answer(answer_mode="rag")
    assert plan_check(plan, prose)["shape_matches"] is False
    table = answer(answer_mode="statistics", structured_result={"kind": "count"})
    assert plan_check({**plan, "shape": "table"}, table)["shape_matches"] is True
    clarification = answer(status="insufficient_evidence", answer_mode="clarification")
    assert plan_check(plan, clarification)["shape_matches"] is None
    assert plan_check(plan, clarification)["actual"]["status"] == "insufficient_evidence"


def test_plan_check_flags_a_web_attempt_only_when_the_plan_forbade_it():
    attempted = answer(status="insufficient_evidence", external_research={"status": "unresolved", "reason": "no_cited_answer"})
    assert plan_check({"allow_web": False}, attempted)["web_matches"] is False
    assert plan_check({"allow_web": True}, attempted)["web_matches"] is True
    assert plan_check({"allow_web": True}, attempted)["actual"] == {
        "status": "insufficient_evidence", "answer_mode": "rag", "failure_reason": "", "web_attempted": True,
        "web_status": "unresolved", "shape": None}
    disabled = answer(status="insufficient_evidence", external_research={"status": "disabled"})
    assert plan_check({"allow_web": False}, disabled)["web_matches"] is None
    out_of_scope = answer(status="insufficient_evidence", external_research={"status": "ok", "reason": "scope_not_supported"})
    assert plan_check({"allow_web": False}, out_of_scope)["actual"]["web_attempted"] is False


def test_service_records_the_plan_and_the_check_without_changing_the_statistics_answer():
    service, db = service_for(ResearchRun(route="statistics", result=count_result(), cost_usd=0.002))
    result = service.answer(COUNT, Filters(), "visitor")
    assert result.status == "answered" and result.answer_mode == "statistics"
    assert "7 eligible native ad records" in result.answer and result.cost_usd == pytest.approx(0.002)
    plan = result.research_trace["question_plan"]
    assert plan["route"] == "statistics" and plan["shape"] == "table" and plan["allow_web"] is False
    assert plan["filters"] == Filters(include_inferred_dates=True).model_dump(mode="json")
    check = result.research_trace["plan_check"]
    assert check["shape_matches"] is True and check["web_matches"] is None
    assert check["actual"]["answer_mode"] == "statistics"
    assert len(db.saved) == 1 and db.saved[0][2] is result  # the saved run record carries both keys


def test_service_records_the_plan_for_a_clarification_and_for_an_understanding_failure():
    service, _ = service_for(ResearchRun(route="clarify", result={"message": "请确认公司的名称。"}, cost_usd=0.001))
    result = service.answer("那家公司有多少广告", Filters(), "visitor")
    assert result.answer == "请确认公司的名称。" and result.answer_mode == "clarification"
    plan = result.research_trace["question_plan"]
    assert plan["route"] == "clarify" and plan["clarify_message"] == "请确认公司的名称。" and plan["allow_web"] is True
    assert result.research_trace["plan_check"]["shape_matches"] is None

    # A statistics result without its fields makes the dispatch fail: the plan is still recorded.
    service, _ = service_for(ResearchRun(route="statistics", result={"status": "ok", "kind": "count"}, cost_usd=0.001))
    broken = service.answer(COUNT, Filters(), "visitor")
    assert broken.status == "service_unavailable" and broken.failure_reason == "research_agent_unavailable"
    assert broken.research_trace["question_plan"]["route"] == "statistics"


def test_a_failing_plan_builder_or_checker_leaves_the_answer_untouched(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("plan unavailable")

    reference, _ = service_for(ResearchRun(route="statistics", result=count_result(), cost_usd=0.002))
    expected = reference.answer(COUNT, Filters(), "visitor")

    monkeypatch.setattr("observatory.service.build_question_plan", explode)
    service, db = service_for(ResearchRun(route="statistics", result=count_result(), cost_usd=0.002))
    result = service.answer(COUNT, Filters(), "visitor")
    assert "question_plan" not in result.research_trace and "plan_check" not in result.research_trace
    assert len(db.saved) == 1
    trace_without_plan = {k: v for k, v in expected.research_trace.items() if k not in ("question_plan", "plan_check")}
    assert result.research_trace == trace_without_plan
    assert result.model_dump(exclude={"research_trace", "latency_ms"}) == expected.model_dump(exclude={"research_trace", "latency_ms"})

    monkeypatch.setattr("observatory.service.build_question_plan", build_question_plan)
    monkeypatch.setattr("observatory.service.plan_check", explode)
    service, _ = service_for(ResearchRun(route="statistics", result=count_result(), cost_usd=0.002))
    result = service.answer(COUNT, Filters(), "visitor")
    assert "question_plan" in result.research_trace and "plan_check" not in result.research_trace
    assert result.answer == expected.answer and result.status == expected.status


def test_the_plan_never_reaches_the_user_facing_answer_text():
    service, _ = service_for(ResearchRun(route="statistics", result=count_result(), cost_usd=0.002))
    result = service.answer(COUNT, Filters(), "visitor")
    assert "question_plan" not in result.answer and "plan_check" not in result.answer
