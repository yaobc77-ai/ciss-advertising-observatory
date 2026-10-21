"""A question restricted to a sponsor/account the collection lacks is answered as such (B1K-0544/0694)."""

import pytest
from research_fakes import FakeCatalog, harness, response

from observatory.models import Filters
from observatory.question_policy import restricts_to_named_source

NOT_FOUND = {"status": "not_found", "candidates": [], "candidate_count": 0, "truncated": False,
             "message": "No sponsor named like this is stored in the selected collection."}


@pytest.mark.parametrize("question, name, restricted", [
    ("Only use native advertisements sponsored by Corvane Oil: what do they say about canals?", "Corvane Oil", True),
    ("Summarize the posts from the account Kestrel Ridge Energy.", "Kestrel Ridge Energy", True),
    ("What do Corvane Oil ads say about canals?", "Corvane Oil", True),
    ("只使用 Corvane Oil 赞助的原生广告：它们怎么说运河？", "Corvane Oil", True),
    ("只看账号 Kestrel Ridge Energy 的帖子", "Kestrel Ridge Energy", True),
    ("What do Pineglass ads say about the Harbor Kite Challenge?", "Harbor Kite Challenge", False),
    ("Which ads mention Pineglass Foundation grants?", "Pineglass Foundation", False),
])
def test_a_source_role_binds_the_name(question, name, restricted):
    assert restricts_to_named_source(question, name) is restricted


def run(question, follow_up):
    responses = [response("resolve_entity", {"query": "Corvane Oil", "entity_type": "sponsor"})]
    responses += follow_up
    agent, _, catalog, calls = harness(responses, catalog=FakeCatalog({"resolve_entity": NOT_FOUND}))
    return agent.run(question, Filters(dataset="native"), "visitor"), catalog


def test_an_absent_named_sponsor_ends_the_read_without_another_search():
    result, catalog = run("Only use native advertisements sponsored by Corvane Oil: what do they say about canals?",
                          [response("search_records", {"query": "Corvane Oil canals"}, call_id="call_2")])
    assert result.route == "clarify"
    assert result.failure_reason == "named_source_not_in_collection"
    assert "no sponsor named “Corvane Oil”" in result.result["message"]
    assert [name for name, _ in catalog.called] == ["resolve_entity"]


def test_a_chinese_question_gets_the_statement_in_chinese():
    result, _ = run("只使用 Corvane Oil 赞助的原生广告：它们怎么说运河？", [])
    assert result.result["message"].startswith("该集合中没有名为“Corvane Oil”的赞助方")


def test_a_name_used_without_a_source_role_is_still_searched_in_the_text():
    result, catalog = run("What do the ads say about Corvane Oil's canal plans?",
                          [response("search_records", {"query": "Corvane Oil canal plans"}, call_id="call_2")])
    assert result.failure_reason != "named_source_not_in_collection"
    assert [name for name, _ in catalog.called] == ["resolve_entity", "search_records"]


def test_the_service_neither_searches_the_web_nor_drops_the_filter_for_an_absent_source():
    from test_answer_failure_repair import web_service

    from observatory.models import Answer

    service = web_service()
    original = Answer(status="insufficient_evidence", answer_mode="clarification",
                      answer="The collection has no sponsor named “Corvane Oil”, so there are no records to cite.",
                      failure_reason="named_source_not_in_collection")
    question = "What do Corvane Oil ads say about canals?"
    assert service._ensure_answer(question, Filters(), "offline", original) is original
    assert service._search_external.call_count == 0


def test_the_planner_declaring_a_restricted_read_ends_it_when_the_rule_misses_the_wording():
    question = "What did Corvane Oil say in its native ads about canals?"
    assert restricts_to_named_source(question, "Corvane Oil") is False  # B1K-M057 wording
    agent, _, catalog, _ = harness(
        [response("resolve_entity", {"query": "Corvane Oil", "entity_type": "sponsor", "restricts_read": True}),
         response("search_records", {"query": "Corvane Oil canals"}, call_id="call_2")],
        catalog=FakeCatalog({"resolve_entity": NOT_FOUND}))
    result = agent.run(question, Filters(dataset="native"), "visitor")
    assert result.failure_reason == "named_source_not_in_collection"
    assert [name for name, _ in catalog.called] == ["resolve_entity"]


def test_a_name_stored_as_an_account_is_resolved_again_instead_of_answered_absent():
    # B1K-Q059/Q094: "RWE AG" and "bp America" are accounts, not sponsors.
    elsewhere = {**NOT_FOUND, "stored_as_other_entity_type": [
        {"entity_type": "account", "dataset": "social", "source_value": "Kestrel Ridge Energy"}]}
    agent, _, catalog, _ = harness(
        [response("resolve_entity", {"query": "Kestrel Ridge Energy", "entity_type": "sponsor", "restricts_read": True}),
         response("resolve_entity", {"query": "Kestrel Ridge Energy", "entity_type": "account"}, call_id="call_2")],
        catalog=FakeCatalog({"resolve_entity": lambda args: elsewhere if args["entity_type"] == "sponsor"
                             else {"status": "ok", "candidates": [], "selected": "Kestrel Ridge Energy"}}))
    result = agent.run("Summarize Kestrel Ridge Energy's posts about ferries.", Filters(dataset="social"), "visitor")
    assert result.failure_reason != "named_source_not_in_collection"
    assert [args["entity_type"] for name, args in catalog.called if name == "resolve_entity"] == ["sponsor", "account"]
