"""A read may not filter to a sponsor, publisher or account nobody named (B1K-P027/P006)."""

from research_fakes import FakeCatalog, harness, response

from observatory.models import Filters
from observatory.research_agent import _ungrounded_source_names

QUESTION = "Which ads published between 2020 and 2022 mention harbor safety?"
INVENTED = {"query": "harbor safety", "filters": {"dataset": "native", "sponsors": ["pineglass"]}}
PLAIN = {"query": "harbor safety", "filters": {"dataset": "native"}}


def test_names_must_come_from_the_question_the_selection_or_a_resolved_question_name():
    base = Filters(dataset="native")
    assert _ungrounded_source_names("search_records", INVENTED, QUESTION, base, set()) == ["pineglass"]
    assert _ungrounded_source_names("search_records", INVENTED, "Which Pineglass ads mention harbor safety?",
                                    base, set()) == []
    assert _ungrounded_source_names("search_records", INVENTED, QUESTION, Filters(sponsors=["pineglass"]), set()) == []
    assert _ungrounded_source_names("search_records", INVENTED, QUESTION, base, {"pineglass"}) == []
    assert _ungrounded_source_names("resolve_entity", {"query": "Pineglass", "entity_type": "sponsor"},
                                    QUESTION, base, set()) == ["Pineglass"]
    scoped = {"query": "x", "comparison_scopes": [{"label": "a", "filters": {"publishers": ["Harbor Daily"]}}]}
    assert _ungrounded_source_names("search_records", scoped, QUESTION, base, set()) == ["Harbor Daily"]


def test_an_invented_filter_is_returned_once_and_the_corrected_read_runs():
    agent, _, catalog, calls = harness(
        [response("search_records", INVENTED), response("search_records", PLAIN, call_id="call_2")],
        catalog=FakeCatalog(), repairs=1)
    result = agent.run(QUESTION, Filters(dataset="native"), "visitor")
    assert [args["filters"].get("sponsors") for _, args in catalog.called] == [None]
    assert "pineglass" in calls[1]["input"][-1]["output"]
    assert result.tool_trace[0]["repair"] == "ungrounded_names_returned_to_model"


def test_a_repeated_invented_filter_ends_without_reading_it():
    agent, _, catalog, _ = harness(
        [response("search_records", INVENTED), response("search_records", INVENTED, call_id="call_2")],
        catalog=FakeCatalog(), repairs=1)
    result = agent.run(QUESTION, Filters(dataset="native"), "visitor")
    assert result.failure_reason == "research_filter_not_in_question"
    assert catalog.called == []


def test_short_forms_parentheses_and_exclusions_are_not_inventions():
    base = Filters(dataset="social")
    post = {"query": "x", "filters": {"accounts": ["Larkfield Energy"]}}
    assert _ungrounded_source_names("search_records", post, "What did Larkfield’s May 2031 post say?", base, set()) == []
    named = {"query": "Harbor Oil Corporation Limited HOCL", "entity_type": "account"}
    assert _ungrounded_source_names("resolve_entity", named, "What did Harbor Oil Corporation Limited (HOCL)’s post say?",
                                    base, set()) == []
    others = {"query": "x", "filters": {"sponsors": ["pineglass", "larkfield"]}}
    assert _ungrounded_source_names("search_records", others, "Which ads sponsored by companies other than Tidal Co "
                                    "mention canals?", Filters(dataset="native"), set()) == []
    assert _ungrounded_source_names("search_records", others, "Which ads mention canals?",
                                    Filters(dataset="native"), set()) == ["pineglass", "larkfield"]
