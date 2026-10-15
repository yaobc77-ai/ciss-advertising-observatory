"""A read that drops a collection the question names is returned to the model once (B1K cross-collection)."""

from test_research_agent import FakeCatalog, harness, response

from observatory.models import Filters

QUESTION = ("Use both collections: (1) What does the Pineglass native ad say about canals? "
            "(2) What did the Pineglass post say about ferries? Cite both.")
NATIVE_ONLY = {"query": "Pineglass canals ferries", "filters": {"dataset": "native"}}
BOTH = {"query": "Pineglass canals ferries", "filters": {"dataset": "all"}}


def test_a_dropped_collection_is_corrected_once_instead_of_ending_the_read():
    agent, _, catalog, calls = harness(
        [response("search_records", NATIVE_ONLY), response("search_records", BOTH, call_id="call_2")],
        catalog=FakeCatalog(), repairs=1)
    result = agent.run(QUESTION, Filters(dataset="all"), "visitor")
    assert result.failure_reason != "explicit_collection_scope_missing"
    assert [args["filters"]["dataset"] for _, args in catalog.called] == ["all"]
    hint = calls[1]["input"][-1]["output"]
    assert "native and social" in hint and "comparison_scopes" in hint
    assert result.tool_trace[0]["repair"] == "collection_scope_returned_to_model"


def test_a_second_dropped_collection_still_stops_without_a_read():
    agent, _, catalog, _ = harness(
        [response("search_records", NATIVE_ONLY), response("search_records", NATIVE_ONLY, call_id="call_2")],
        catalog=FakeCatalog(), repairs=1)
    result = agent.run(QUESTION, Filters(dataset="all"), "visitor")
    assert result.failure_reason == "explicit_collection_scope_missing"
    assert catalog.called == []


def test_use_both_collections_names_both_even_when_only_native_ad_and_post_follow():
    from observatory.question_policy import question_contract

    assert question_contract(QUESTION)["explicit_datasets"] == ["native", "social"]
    assert question_contract("同时使用两个数据集：（1）Pineglass 的原生广告说了什么？（2）它的帖子说了什么？")[
        "explicit_datasets"] == ["native", "social"]
    assert question_contract("What does the Pineglass native ad say about canals?")["explicit_datasets"] == ["native"]
