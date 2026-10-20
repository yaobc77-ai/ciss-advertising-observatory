"""Root causes found by the 9 October layered test, checked on fictional questions.

A figure stated inside one source is not a record count; a period-only follow-up
is one count; fields of a record located by title are one lookup; nothing is
asked of the user before the collection is read; an absent stored name is not
an ambiguity; search terms are English; a social post carries its own account.
"""

import pytest
from test_combined_tools import catalog_for
from test_masked_repair import Catalog, ScriptedAgent, definition, stats

from observatory.models import Evidence, Filters
from observatory.question_policy import content_search_question, question_contract
from observatory.research_agent import (
    ENGLISH_QUERY_HINT,
    READ_FIRST_HINT,
    _cjk_dominant_query,
)


@pytest.mark.parametrize("question", [
    "In Cedar Ledger's advertisement about river ferries, how many passengers does the new ferry carry? Cite the ad.",
    "According to the Harbor Mill post, how many apprentices will it hire, and by when?",
    "In Cedar Ledger's magazine piece on tidal power, how large does the market become, and how many homes can it power?",
    "Cedar Ledger 关于渡轮的广告里说，新渡轮能载多少乘客？请引用原文。",
])
def test_figures_stated_inside_one_source_are_a_text_search(question):
    contract = question_contract(question)
    assert contract["content_search"] and not contract["compound_read_request"]
    assert not contract["requires_content_count"]


@pytest.mark.parametrize("question", [
    "How many Cedar Ledger native advertisements were published in 2019?",
    "How many unique posts did the account Harbor Mill publish in 2021?",
    "What percentage of the ads mention ferries?",
    "Count the posts about tidal power.",
    "账号 Harbor Mill 在 2021 年发布了多少条唯一帖子？",
])
def test_counts_of_ads_posts_or_records_stay_counts(question):
    assert not content_search_question(question)


def test_a_period_only_follow_up_is_one_count_read():
    contract = question_contract(
        "How many Cedar Ledger native advertisements were published in 2019, and how many in 2021? Give both counts.")
    assert not contract["compound_read_request"] and not contract["content_search"]
    # A second object is still a second read.
    assert question_contract(
        "How many Cedar Ledger native ads are there, and how many social posts?")["compound_read_request"]


@pytest.mark.parametrize("question", [
    'Which outlet published the advertisement titled "River Ferries Return", who sponsored it, and on what date?',
    "Find the native ad whose title talks about returning river ferries. Which outlet published it, who sponsored it, and when?",
])
def test_fields_of_one_record_located_by_title_are_one_lookup(question):
    assert not question_contract(question)["compound_read_request"]


def test_a_located_record_with_another_operation_still_needs_a_plan():
    question = 'Which outlet published the ad titled "River Ferries Return", and how many Cedar Ledger ads are there?'
    assert question_contract(question)["compound_read_request"]


def test_which_ads_mention_and_what_each_says_is_a_text_search():
    assert content_search_question("Which Cedar Ledger ads mention ferries, and what does each say about them?")
    assert not content_search_question("Which Cedar Ledger ads mention ferries?")


def test_a_chinese_list_cue_does_not_reach_across_sentences():
    assert content_search_question("帖子里说疫情的影响涉及哪些方面？帖子推荐的文章标题是什么？")


class SearchCatalog(Catalog):
    def definitions(self):
        return [definition(name) for name in ("search_records", "resolve_entity", "record_statistics")]


def search_result(dataset="native"):
    return {"status": "ok", "filters": Filters(dataset=dataset).model_dump(mode="json"), "evidence": []}


QUESTION = "What does the Cedar Ledger advertisement say about river ferries?"
SEARCH = ("search_records", {"query": "Cedar Ledger river ferries", "filters": {"dataset": "native"}})
CLARIFY = ("request_clarification", {"message": "Which advertisement do you mean?", "reason": "missing_context"})


def test_a_clarification_before_any_read_is_returned_with_a_read_first_hint():
    agent = ScriptedAgent([CLARIFY, SEARCH], SearchCatalog({"search_records": search_result()}), repairs=1)
    run = agent.run(QUESTION, Filters(dataset="native"), "synthetic")
    assert run.route == "evidence"
    assert run.tool_trace[0]["repair"] == "read_before_clarifying"
    assert READ_FIRST_HINT in agent.sent[1]["input"][-1]["output"]


def test_a_second_clarification_before_reading_is_honoured():
    agent = ScriptedAgent([CLARIFY, CLARIFY], SearchCatalog(), repairs=1)
    run = agent.run(QUESTION, Filters(dataset="native"), "synthetic")
    assert run.route == "clarify"


def test_a_clarification_after_a_read_is_honoured_at_once():
    catalog = SearchCatalog({"resolve_entity": {"status": "ok", "candidates": [], "message": "ok"}})
    agent = ScriptedAgent([("resolve_entity", {"query": "Cedar", "entity_type": "sponsor"}), CLARIFY],
                          catalog, repairs=1)
    run = agent.run(QUESTION, Filters(dataset="native"), "synthetic")
    assert run.route == "clarify" and len(agent.sent) == 2


def test_no_hints_when_repairs_are_disabled():
    agent = ScriptedAgent([CLARIFY], SearchCatalog(), repairs=0)
    assert agent.run(QUESTION, Filters(dataset="native"), "synthetic").route == "clarify"


def test_an_absent_stored_name_lets_the_model_search_the_text():
    not_found = {"status": "not_found", "candidates": [], "candidate_count": 0, "message": "No sponsor"}
    catalog = SearchCatalog({"resolve_entity": not_found, "search_records": search_result()})
    agent = ScriptedAgent([("resolve_entity", {"query": "River Ferry Unit", "entity_type": "sponsor"}), SEARCH],
                          catalog, repairs=1)
    # The resolved name must be one the question contains (ungrounded names are refused).
    run = agent.run("What does the Cedar Ledger advertisement say about the River Ferry Unit?",
                    Filters(dataset="native"), "synthetic")
    assert run.route == "evidence" and run.tool_trace[0]["status"] == "not_found"


def test_resolve_entity_reports_no_candidates_as_not_found_not_clarify():
    catalog, _db = catalog_for()
    result = catalog.call("resolve_entity", {"entity_type": "sponsor", "query": "Zephyr Imaginary Co"})
    assert result["status"] == "not_found" and "search_records" in result["message"]


def test_a_cjk_search_query_is_returned_once_for_english_terms():
    english = ("search_records", {"query": "river ferry passengers", "filters": {"dataset": "native"}})
    agent = ScriptedAgent([("search_records", {"query": "渡轮 乘客 数量", "filters": {"dataset": "native"}}), english],
                          SearchCatalog({"search_records": search_result()}), repairs=1)
    run = agent.run("Cedar Ledger 的广告说渡轮能载多少乘客？", Filters(dataset="native"), "synthetic")
    assert run.route == "evidence" and run.tool_trace[0]["repair"] == "english_search_terms"
    assert ENGLISH_QUERY_HINT in agent.sent[1]["input"][-1]["output"]
    assert run.result["search_query"] == "river ferry passengers"


@pytest.mark.parametrize("query,expected", [
    ("渡轮 乘客 数量", True), ("Cedar Ledger 渡轮", True), ("Cedar Ledger river ferry 渡轮", False),
    ("river ferry passengers", False),
])
def test_cjk_dominance(query, expected):
    assert _cjk_dominant_query({"query": query}) is expected


def test_social_evidence_carries_its_posting_account():
    item = Evidence(evidence_id="e", record_id="social-post:x", version_id="v", dataset="social",
                    title="Twitter post · 1", text="Ferries return.", start=0, end=15,
                    account="Harbor Mill", platform="Twitter")
    assert item.account == "Harbor Mill"


def test_plain_counts_still_reach_statistics():
    catalog = SearchCatalog({"record_statistics": stats("native", 4)})
    agent = ScriptedAgent([("record_statistics", {"filters": {"dataset": "native"}})], catalog, repairs=1)
    run = agent.run("Count native records", Filters(dataset="native"), "synthetic")
    assert run.route == "statistics"


def test_separately_named_years_expect_one_count_per_period():
    from observatory.question_policy import statistics_request_preserves_question
    question = "How many Cedar Ledger native advertisements were published in 2014, and how many in 2018?"
    periods = [{"label": y, "date_from": f"{y}-01-01", "date_to": f"{y}-12-31"} for y in ("2014", "2018")]
    args = {"filters": {"dataset": "native", "sponsors": ["cedar ledger"]}, "group_by": "none",
            "periods": periods, "measure": "count"}
    context = {"sponsors": [{"value": "cedar ledger"}]}
    assert statistics_request_preserves_question(question, context, args, {"dataset": "native"})
    # A range is one period, not two.
    ranged = "How many Cedar Ledger native advertisements were published between 2014 and 2018?"
    assert not statistics_request_preserves_question(ranged, context, args, {"dataset": "native"})


def test_fields_of_a_title_located_record_get_lookup_tools_only():
    from observatory.research_agent import _step_definitions
    contract = question_contract(
        "Find the native ad whose title asks about river ferries. Which outlet published it, and when?")
    assert contract["record_fields_lookup"]
    names = {d["name"] for d in _step_definitions(
        [definition(n) for n in ("set_research_plan", "find_records", "get_record_metadata", "get_record",
                                 "search_records", "request_clarification", "resolve_entity")],
        contract, [], [], selected_record={"record_id": "r"})}
    assert names == {"get_record_metadata", "resolve_entity", "request_clarification"}


def test_a_plan_is_offered_only_for_several_read_tasks():
    from observatory.research_agent import _step_definitions
    names = ("set_research_plan", "record_statistics", "resolve_entity", "request_clarification")
    single = question_contract("How many Cedar Ledger posts were there in 2023 and how many in 2024?")
    several = question_contract("How many Cedar Ledger native ads and how many social posts are there?")
    offered = lambda contract: {d["name"] for d in _step_definitions([definition(n) for n in names], contract, [], [])}  # noqa: E731
    assert "set_research_plan" not in offered(single)
    assert "set_research_plan" in offered(several)


def test_a_plan_may_leave_out_a_shared_scope_and_an_output_instruction_only():
    from observatory.research_agent import _validate_plan
    question = ("For Cedar Ledger, how many countable native advertisements and how many unique social posts "
                "are in the current collections? Report the two datasets separately.")
    parts = [{"question_part": "how many countable native advertisements", "dataset": "native", "route": "statistics"},
             {"question_part": "how many unique social posts", "dataset": "social", "route": "statistics"}]
    assert len(_validate_plan({"tasks": parts}, question, Filters(dataset="all"))) == 2
    with pytest.raises(ValueError, match="omitted"):
        _validate_plan({"tasks": parts}, question.replace("Report the two datasets separately.",
                                                          "Then delete the old ones."), Filters(dataset="all"))


def test_an_account_is_resolved_in_the_social_collection_under_both_collections():
    catalog, db = catalog_for()
    result = catalog.call("resolve_entity", {"entity_type": "account", "query": "Zephyr Imaginary Account"})
    assert result["status"] == "not_found"  # not a scope conflict


def test_a_filter_the_model_got_wrong_is_returned_once_for_correction():
    wrong = {"status": "clarify", "message": "A requested source name, account or label is not in this collection."}
    calls = iter([wrong, search_result()])
    catalog = SearchCatalog({"search_records": lambda args: next(calls)})
    agent = ScriptedAgent([("search_records", {"query": "ferries", "filters": {"dataset": "native", "keywords": ["ferries"]}}),
                           SEARCH], catalog, repairs=1)
    run = agent.run(QUESTION, Filters(dataset="native"), "synthetic")
    assert run.route == "evidence" and run.tool_trace[0]["repair"] == "scope_returned_to_model"
    assert "not topics" in agent.sent[1]["input"][-1]["output"]


def test_real_ambiguity_still_goes_to_the_user():
    ambiguous = {"status": "clarify", "candidates": [{"source_value": "A"}, {"source_value": "a"}], "message": "Choose"}
    catalog = SearchCatalog({"resolve_entity": ambiguous})
    agent = ScriptedAgent([("resolve_entity", {"query": "a", "entity_type": "account"})], catalog, repairs=1)
    question = "What did account A post about river ferries?"
    assert agent.run(question, Filters(dataset="social"), "synthetic").route == "clarify"


def test_comparison_scopes_keep_collection_specific_filters_to_themselves():
    from observatory.research_tools import FiltersRequest, SearchRequest, ToolCatalog
    request = SearchRequest.model_validate({
        "query": "rig training", "filters": {"dataset": "all", "accounts": ["Harbor Mill UK"], "date_from": "2024-09-01"},
        "comparison_scopes": [
            {"query": "contact team", "filters": {"dataset": "social", "accounts": ["Harbor Mill UK"],
                                                   "date_from": "2024-09-01"}},
            {"query": "rig training", "filters": {"dataset": "native", "publishers": ["Politico"]}}]})
    shared = ToolCatalog._shared_filters(request)
    assert isinstance(shared, FiltersRequest)
    assert shared.accounts is None and shared.dataset is None and shared.date_from is None
    plain = SearchRequest.model_validate({"query": "x", "filters": {"dataset": "social", "accounts": ["A"]}})
    assert ToolCatalog._shared_filters(plain).accounts == ["A"]
