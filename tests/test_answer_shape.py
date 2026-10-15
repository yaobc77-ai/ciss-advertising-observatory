"""The planner's declared answer shape routes lists the surface rule misses (B1K-N: 17 of 50)."""

from test_list_screening import KITE, screening_service
from test_research_agent import FakeCatalog, harness, response

from observatory.list_screening import Decision
from observatory.models import Filters
from observatory.question_policy import question_contract

UNRULED = "讲潮汐风筝的广告都是哪几篇？"


def test_a_list_the_rule_misses_is_screened_when_the_planner_declares_it():
    assert question_contract(UNRULED)["requires_complete_list"] is False  # the rule alone misses it
    service, parse, _ = screening_service([
        Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
        Decision(ref="A2", decision="does_not_match", passage_id="A2.1", quote=""),
        Decision(ref="A3", decision="does_not_match", passage_id="A3.1", quote=""),
    ])
    result = service._answer_evidence(UNRULED, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    assert parse.call_count == 1 and "list_screening" in result.research_trace
    assert [c.evidence_id for c in result.citations] == [KITE.evidence_id]
    assert result.research_trace["list_decision"] == {"rule": False, "planner": "every_matching_source"}


def test_a_declared_list_outside_screening_is_labelled_as_examples():
    from test_answer_failure_repair import generation_service, selected_payload

    # Both collections are not screened, so the declared list is answered from examples and says so.
    service, _, _ = generation_service(selected_payload())
    result = service._answer_evidence("Find every Larkfield ad that touches on winter reopening.", Filters(dataset="all"),
                                      "offline", audit=False, declared_shape="every_matching_source")
    assert "list_screening" not in result.research_trace
    assert "not a complete list" in result.answer


def test_the_planner_shape_reaches_the_evidence_result():
    args = {"query": "tidal kites", "filters": {"dataset": "native"}, "answer_shape": "every_matching_source"}
    agent, _, _, _ = harness([response("search_records", args)], catalog=FakeCatalog())
    result = agent.run(UNRULED, Filters(dataset="native"), "visitor")
    assert result.route == "evidence" and result.result["answer_shape"] == "every_matching_source"


def test_a_joined_name_is_returned_once_to_be_resolved_separately():
    not_found = {"status": "not_found", "candidates": [], "candidate_count": 0, "message": "No sponsor"}
    question = "Find Pineglass or Larkfield ads that mention canals."
    agent, _, catalog, calls = harness(
        [response("resolve_entity", {"query": "Pineglass or Larkfield", "entity_type": "sponsor"}),
         response("search_records", {"query": "canals", "filters": {"dataset": "native"}}, call_id="call_2")],
        catalog=FakeCatalog({"resolve_entity": not_found}), repairs=1)
    result = agent.run(question, Filters(dataset="native"), "visitor")
    assert result.failure_reason != "named_source_not_in_collection"
    assert result.tool_trace[0]["repair"] == "composite_name_returned_to_model"
    assert "separately" in calls[1]["input"][-1]["output"]
