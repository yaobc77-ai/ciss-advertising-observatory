"""Pipeline steps 1-2: the QuestionPlan records how a question is handled, and the evidence route reads it.

Step 1 mirrored today's decisions into the run record without changing behaviour;
step 2 made service._answer_evidence read shape, list kind, phrases, source
reading and web permission from the plan. Fictional questions and records only,
written against the product interfaces (Service, ResearchRun) so this module
stays in the free completion gate. The plan is built from the understanding
stage (question, scope, agent run); plan_check compares it with the final answer.
"""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_list_screening import KITE, screening_service
from test_research_fallback import harness as fallback_harness

from observatory.config import Settings
from observatory.list_screening import pure_literal_question, quoted_phrases
from observatory.models import Answer, Filters
from observatory.question_plan import (
    COLLECTION_ONLY,
    PLAN_VERSION,
    build_evidence_plan,
    build_question_plan,
    list_requested,
    plan_check,
)
from observatory.question_policy import (
    original_metadata_question,
    question_contract,
    sources_content_request,
)
from observatory.research_agent import ResearchRun
from observatory.service import Service, _list_over_selection

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
    assert plan.phrases == ["tidal kite"] and plan.version == PLAN_VERSION == "question-plan-v2"


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


# ---------------------------------------------------------------------------
# Step 2: the evidence route reads the plan.
# ---------------------------------------------------------------------------

LITERAL = 'Which ads mention "tidal kite"?'
TWO_PHRASES = 'Which ads mention "tidal kite" or "harbor"?'
SAYS = "What do Tidal Co's ads say about kites? Cite each ad."
ORIGINAL = "Read the stored original title"
POST_LITERAL = 'Find the posts that use "#KitePower"'
LISTING = {"list_all": True, "selections": [{"relations": {"mentions": ["kiteguild"]}}]}
GROUPS = [{"query": "tidal kites", "filters": {"dataset": "native"}, "label": "A"},
          {"query": "harbor power", "filters": {"dataset": "native"}, "label": "B"}]
SCOPES = [Filters(dataset="native"), Filters(dataset="social"), Filters(dataset="all"),
          Filters(dataset="all", labels=["energy"]), Filters(dataset="social", record_ids=["p1", "p2"]),
          Filters(dataset="social", record_ids=["no-relation-match"])]


def before_step_2(question, filters, declared_shape, relation_listing, retrieval_groups):
    """_answer_evidence's own decisions as written before step 2 (service.py at 69a3846), kept as the oracle."""
    contract = question_contract(question)
    rule_list = contract["requires_complete_list"]
    wants_list = rule_list or declared_shape == "every_matching_source"
    list_mode = wants_list and not retrieval_groups and filters.dataset in ("native", "social")
    both_list = wants_list and not retrieval_groups and filters.dataset == "all" and not filters.labels
    list_mode = list_mode or both_list
    relation_list = bool(relation_listing and relation_listing.get("list_all") and relation_listing.get("selections")
                         and filters.dataset == "social" and filters.record_ids
                         and filters.record_ids != ["no-relation-match"])
    list_mode = list_mode or relation_list
    if not list_mode:
        kind = None
    elif both_list:
        kind = "screen"  # _screen_both reads the quoted phrase itself
    elif relation_list:
        kind = "relation"
    elif pure_literal_question(question):
        kind = "literal"
    else:
        kind = "screen"
    return {
        "shape": "list" if list_mode else "answer", "list_kind": kind, "both": bool(both_list),
        "wants_list": bool(wants_list), "phrases": quoted_phrases(question),
        # Web help needed no collection-only wording and no screened list (every list result carries list_screening).
        "allow_web": not COLLECTION_ONLY.search(question) and not list_mode,
        "read_sources": sources_content_request(question), "original_metadata": original_metadata_question(question),
        "coverage_note_rule": bool(contract["selects_sources"] or contract["requires_content_count"]),
        "list_decision": {"rule": bool(rule_list), "planner": declared_shape},
    }


def decisions(plan):
    return {
        "shape": plan.shape, "list_kind": plan.list_kind,
        "both": plan.shape == "list" and plan.datasets == ["native", "social"],
        "wants_list": plan.wants_list, "phrases": plan.phrases, "allow_web": plan.allow_web,
        "read_sources": plan.read_sources, "original_metadata": plan.original_metadata,
        "coverage_note_rule": plan.coverage_note_rule,
        "list_decision": {"rule": plan.signals["rule_list"], "planner": plan.signals["planner_shape"]},
    }


def without_provenance(plan):
    data = plan.as_dict()
    data.pop("agent_route")
    data["reasons"] = {k: v for k, v in data["reasons"].items() if k not in ("route", "search_query")}
    return data


@pytest.mark.parametrize("question", [RULE_LIST, UNRULED_LIST, PLAIN, LITERAL, TWO_PHRASES, SAYS,
                                      "Only use the collection: " + PLAIN, ORIGINAL, POST_LITERAL])
def test_both_builders_reproduce_the_evidence_route_decisions_made_before_step_2(question):
    cases = 0
    for filters in SCOPES:
        for declared in (None, "every_matching_source"):
            for listing in (None, LISTING):
                for groups in (None, GROUPS):
                    for query in (None, "tidal kites"):
                        expected = before_step_2(question, filters, declared, listing, groups)
                        direct = build_evidence_plan(question, filters, search_query=query, declared_shape=declared,
                                                     relation_listing=listing, retrieval_groups=groups)
                        data = {"filters": filters.model_dump(mode="json"), "search_query": query, "answer_shape": declared,
                                "relation_listing": listing, "retrieval_groups": groups}
                        agent = build_question_plan(question, filters, run_for("evidence", data), filters)
                        assert decisions(direct) == expected, (question, filters, declared, listing, groups)
                        assert decisions(agent) == expected, (question, filters, declared, listing, groups)
                        assert without_provenance(direct) == without_provenance(agent)
                        assert direct.filters == agent.filters == filters.model_dump(mode="json")
                        assert direct.search_query == agent.search_query == (query or question)
                        cases += 1
    assert cases == 96
    direct = build_evidence_plan(question, Filters(), search_query="tidal kites")
    assert (direct.agent_route, direct.reasons["route"], direct.reasons["search_query"]) == ("direct", "caller:evidence", "caller")
    assert build_evidence_plan(question, Filters()).reasons["search_query"] == "default:question"


def test_a_literal_question_over_both_collections_is_screened_in_each_not_matched_literally():
    # The step-1 mirror put "literal" first; _answer_evidence screens both collections first.
    plan = build_evidence_plan(LITERAL, Filters(dataset="all"))
    assert plan.shape == "list" and plan.list_kind == "screen" and plan.datasets == ["native", "social"]
    assert plan.phrases == ["tidal kite"] and plan.signals["pure_literal"] is True
    assert build_evidence_plan(LITERAL, Filters(dataset="native")).list_kind == "literal"


def test_list_requested_is_the_one_rule_the_selection_widening_reads():
    assert list_requested(RULE_LIST) is True and list_requested(UNRULED_LIST) is False
    assert list_requested(UNRULED_LIST, "every_matching_source") is True
    both = Filters(dataset="all")
    assert _list_over_selection(RULE_LIST, Filters(dataset="native"), both, {}).dataset == "all"
    assert _list_over_selection(UNRULED_LIST, Filters(dataset="native"), both, {"answer_shape": "every_matching_source"}).dataset == "all"
    assert _list_over_selection(UNRULED_LIST, Filters(dataset="native"), both, {}).dataset == "native"
    assert _list_over_selection(RULE_LIST, Filters(dataset="native"), both, {"retrieval_groups": GROUPS}).dataset == "native"


KITE_MATCH = [{"ref": "A1", "decision": "matches", "passage_id": "A1.1",
               "quote": "Tidal kites will supply cheap power to the harbor."},
              {"ref": "A2", "decision": "does_not_match", "passage_id": "A2.1", "quote": ""},
              {"ref": "A3", "decision": "does_not_match", "passage_id": "A3.1", "quote": ""}]


def kite_service():
    from observatory.list_screening import Decision

    return screening_service([Decision(**item) for item in KITE_MATCH])


def test_the_route_follows_the_plan_shape_not_the_question_wording():
    question = "Which ads mention tidal kites?"
    assert question_contract(question)["requires_complete_list"] is True
    # Control: the same question, fixture and mocked replies screen the candidates.
    service, parse, _ = kite_service()
    service.rag.generate = Mock(side_effect=AssertionError("a list is screened, not generated"))
    screened = service._answer_evidence(question, Filters(dataset="native"), "offline", audit=False)
    assert parse.call_count == 1 and "list_screening" in screened.research_trace
    assert [c.evidence_id for c in screened.citations] == [KITE.evidence_id]
    assert screened.research_trace["question_plan"]["list_kind"] == "screen"  # the route's own plan is recorded

    # Only the plan changes: shape "answer" sends the same question to generation.
    service, parse, _ = kite_service()
    service.rag.generate = Mock(return_value=Answer(status="answered", answer_mode="rag", answer="Prose about kites."))
    plan = build_evidence_plan(question, Filters(dataset="native"))
    prose = service._answer_evidence(question, Filters(dataset="native"), "offline", audit=False,
                                     plan=replace(plan, shape="answer", list_kind=None, allow_web=True))
    assert parse.call_count == 0 and service.rag.generate.call_count == 1
    assert prose.answer.startswith("Prose about kites.") and "list_screening" not in prose.research_trace
    assert prose.research_trace["list_decision"] == {"rule": True, "planner": None}
    assert prose.research_trace["coverage_note"] == "retrieved_examples_only"  # wants_list still notes the scope
    assert "question_plan" not in prose.research_trace  # a caller's plan is recorded by the caller


def test_a_plan_declaring_a_list_screens_a_question_the_rule_misses_without_the_declared_shape_argument():
    assert question_contract(UNRULED_LIST)["requires_complete_list"] is False
    service, parse, _ = kite_service()
    plan = build_evidence_plan(UNRULED_LIST, Filters(dataset="native"), declared_shape="every_matching_source")
    assert plan.shape == "list" and plan.reasons["shape"] == "planner:answer_shape"
    result = service._answer_evidence(UNRULED_LIST, Filters(dataset="native"), "offline", audit=False, plan=plan)
    assert parse.call_count == 1 and "list_screening" in result.research_trace
    assert result.research_trace["list_decision"] == {"rule": False, "planner": "every_matching_source"}


def test_web_help_follows_the_plan_permission():
    question = "Describe hydrogen"
    service, _, web, _ = fallback_harness()
    allowed = service._answer_evidence(question, Filters(), "reader-a", audit=False)
    assert len(web.calls) == 1 and allowed.external_research["status"] == "ok"
    assert allowed.research_trace["question_plan"]["allow_web"] is True

    service, _, web, _ = fallback_harness()
    plan = replace(build_evidence_plan(question, Filters()), allow_web=False)
    refused = service._answer_evidence(question, Filters(), "reader-b", audit=False, plan=plan)
    assert not web.calls and not refused.external_research and refused.status == "insufficient_evidence"

    service, _, web, _ = fallback_harness()
    wording = service._answer_evidence("Only use the collection: " + question, Filters(), "reader-c", audit=False)
    assert not web.calls and wording.research_trace["question_plan"]["reasons"]["allow_web"] == "rule:collection_only"


def test_the_legacy_path_records_the_route_plan_and_gets_the_check():
    service, db, web, _ = fallback_harness()  # research agent and question intent are off: _answer_legacy
    result = service.answer("Describe hydrogen", Filters(), "legacy-reader")
    assert result.answer_mode == "web_supplement" and len(web.calls) == 1
    plan = result.research_trace["question_plan"]
    assert (plan["agent_route"], plan["reasons"]["route"], plan["reasons"]["search_query"]) == ("direct", "caller:evidence", "default:question")
    assert plan["shape"] == "answer" and plan["allow_web"] is True
    check = result.research_trace["plan_check"]
    assert check["web_matches"] is True and check["shape_matches"] is True and check["actual"]["answer_mode"] == "web_supplement"
    assert len(db.saved) == 1


def test_the_agent_path_records_the_plan_it_built_not_the_route_copy():
    service, db, web, _ = fallback_harness()
    service.settings.research_agent_enabled = True
    # The agent's narrowed filters keep the dashboard's inferred-date basis, as the real planner does.
    run = ResearchRun(route="evidence", result={"filters": Filters(include_inferred_dates=True).model_dump(mode="json"), "search_query": "hydrogen"},
                      cost_usd=0.001)
    service.research_agent = ScriptedAgent(run)
    result = service.answer("How do the ads discuss hydrogen?", Filters(), "agent-reader")
    assert result.answer_mode == "web_supplement" and len(web.calls) == 1
    assert db.reads[-1][0] == "hydrogen"  # the plan's search query reached retrieval
    plan = result.research_trace["question_plan"]
    assert (plan["agent_route"], plan["reasons"]["route"], plan["search_query"]) == ("evidence", "agent:last_tool", "hydrogen")
    assert plan["reasons"]["search_query"] == "planner" and plan["shape"] == "answer"
    check = result.research_trace["plan_check"]
    assert check["web_matches"] is True and check["shape_matches"] is True


def test_a_failing_plan_builder_is_the_understanding_failure_it_replaced(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("plan unavailable")

    # Agent path: the plan is built inside the understanding boundary, like the inline rules before it.
    monkeypatch.setattr("observatory.service.build_question_plan", explode)
    service, db, _, _ = fallback_harness()
    service.settings.research_agent_enabled = True
    service.research_agent = ScriptedAgent(ResearchRun(route="evidence", result={"filters": Filters(include_inferred_dates=True).model_dump(mode="json")}, cost_usd=0.001))
    result = service.answer("How do the ads discuss hydrogen?", Filters(), "agent-fail")
    assert result.status == "service_unavailable" and result.failure_reason == "research_agent_unavailable"
    assert "question_plan" not in result.research_trace and not db.reads

    # Direct and legacy calls: a structured failure of this route, never an exception to the caller.
    monkeypatch.setattr("observatory.service.build_evidence_plan", explode)
    service, db, web, _ = fallback_harness()
    result = service._answer_evidence(PLAIN, Filters(), "direct-fail", audit=False)
    assert result.status == "service_unavailable" and result.failure_reason == "RuntimeError"
    assert not db.reads and not web.calls and "question_plan" not in result.research_trace


@pytest.mark.parametrize("helper", ["quoted_phrases", "pure_literal_question", "sources_content_request",
                                    "question_contract", "original_metadata_question"])
def test_a_failing_rule_inside_the_plan_is_reported_as_this_route_s_failure(monkeypatch, helper):
    # Before step 2 the first three ran inside the route's try (structured failure) and the last two
    # before it (an exception to the caller); every rule now fails the same way: structured.
    def explode(*_args, **_kwargs):
        raise KeyError(helper)

    monkeypatch.setattr(f"observatory.question_plan.{helper}", explode)
    service, db, web, _ = fallback_harness()
    result = service._answer_evidence(PLAIN, Filters(), "rule-fail", audit=False)
    assert result.status == "service_unavailable" and result.failure_reason == "KeyError"
    assert not db.reads and not web.calls


def test_the_original_metadata_return_carries_the_route_plan():
    service, db, _, _ = fallback_harness()
    plan = build_evidence_plan(ORIGINAL, Filters())
    assert plan.original_metadata is True and plan.shape == "answer"
    result = service._answer_evidence(ORIGINAL, Filters(), "metadata-reader", audit=False)
    assert result.failure_reason == "original_source_metadata_required" and not db.reads
    assert result.research_trace["question_plan"]["original_metadata"] is True
    # With a caller's plan the caller records it: nothing is added here.
    with_plan = service._answer_evidence(ORIGINAL, Filters(), "metadata-reader", audit=False, plan=plan)
    assert with_plan.failure_reason == "original_source_metadata_required" and with_plan.research_trace == {}


def test_a_screened_list_with_no_match_is_a_finding_and_never_searches_the_web_through_the_whole_service():
    from observatory.list_screening import Decision

    service, parse, _ = screening_service([
        Decision(ref="A1", decision="does_not_match", passage_id="A1.1", quote=""),
        Decision(ref="A2", decision="does_not_match", passage_id="A2.1", quote=""),
        Decision(ref="A3", decision="does_not_match", passage_id="A3.1", quote="")])
    service.settings.research_agent_enabled = True
    narrowed = Filters(dataset="native", include_inferred_dates=True).model_dump(mode="json")
    service.research_agent = ScriptedAgent(ResearchRun(route="evidence", result={"filters": narrowed, "search_query": "tidal kites"},
                                                       cost_usd=0.001))
    result = service.answer("Which ads mention tidal kites?", Filters(dataset="native"), "empty-list-reader")
    # _search_external in this fixture raises if called: the outer _ensure_answer must not call it either.
    assert parse.call_count == 1 and result.status == "answered" and not result.citations
    assert result.research_trace["list_screening"]["matches"] == 0
    plan, check = result.research_trace["question_plan"], result.research_trace["plan_check"]
    assert plan["shape"] == "list" and plan["allow_web"] is False and plan["agent_route"] == "evidence"
    assert check["shape_matches"] is True and check["web_matches"] is None and check["actual"]["web_attempted"] is False
