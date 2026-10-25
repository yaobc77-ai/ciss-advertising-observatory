"""Fictional task contracts (R2): a content search keeps the question's named source and
period, and does not drop an independent part of a plan (Codex audit D1, D2, D6)."""
from research_fakes import FakeCatalog, harness, response

from observatory.models import Filters
from observatory.question_policy import question_source_scope

CONTEXT = {"sponsors": ["Larkspur Energy", "Marigold Gas"], "accounts": ["Larkspur Energy", "Marigold Ferries"]}


class LarkspurCatalog(FakeCatalog):
    def entity_context(self):
        return CONTEXT


def echo_filters(args):
    """A read whose returned scope is what was asked (the trusted selection is all native ads)."""
    filters = Filters(dataset="native").model_copy(update=args.get("filters") or {})
    return {"status": "ok", "filters": filters.model_dump(mode="json"), "data_version": "v-current",
            "query": args.get("query"), "evidence": [], "data_refs": ["record:stored-1"]}


def catalog():
    return LarkspurCatalog({"search_records": echo_filters, "record_statistics": echo_filters})


def test_a_named_source_and_its_stated_year_bind_a_content_search():
    agent, _, cat, _ = harness([response("search_records", {"query": "tidal batteries", "filters": {"dataset": "native"},
                                                            "answer_shape": "named_sources"})], catalog=catalog())
    run = agent.run("What did Larkspur Energy's native ads in 2021 say about tidal batteries?",
                    Filters(dataset="native"), "visitor")
    sent = cat.called[-1][1]["filters"]
    assert sent["sponsors"] == ["Larkspur Energy"] and (sent["date_from"], sent["date_to"]) == ("2021-01-01", "2021-12-31")
    assert run.route == "evidence" and run.tool_trace[-1]["scope_completed_from_question"]["sponsors"] == ["Larkspur Energy"]


def test_only_a_source_role_and_a_past_period_count_as_scope():
    # The ads talk about the company: content, not a sponsor filter.
    assert question_source_scope("Which ads mention Larkspur Energy?", CONTEXT, "native") == {}
    # A target year is not a publication date.
    assert question_source_scope("What do Larkspur Energy's ads say about net zero in 2050?", CONTEXT, "native") == {
        "sponsors": ["Larkspur Energy"]}
    # Words between the possessive and "posts" (B1K-Q009: "Chevron's October 2020 posts").
    assert question_source_scope("What did Marigold Gas's October 2020 posts say about ferries?", CONTEXT, "social") == {
        "sponsors": ["Marigold Gas"], "date_from": "2020-10-01", "date_to": "2020-10-31"}
    # A company's own account name picks the account only when the question says "account".
    assert question_source_scope("Summarize the account Larkspur Energy's posts.", CONTEXT, "social") == {
        "accounts": ["Larkspur Energy"]}
    assert question_source_scope("Summarize Larkspur Energy's posts.", CONTEXT, "social") == {
        "sponsors": ["Larkspur Energy"]}


def test_a_field_the_model_filled_is_left_to_the_other_checks():
    agent, _, cat, _ = harness([response("search_records", {"query": "tidal batteries", "filters": {
        "dataset": "native", "sponsors": ["Larkspur Energy"], "date_from": "2021-03-01"}})], catalog=catalog())
    run = agent.run("What did Larkspur Energy's native ads in 2021 say about tidal batteries?",
                    Filters(dataset="native"), "visitor")
    sent = cat.called[-1][1]["filters"]
    assert sent["date_from"] == "2021-03-01" and not sent.get("date_to")
    assert "scope_completed_from_question" not in run.tool_trace[-1]


def test_a_content_search_does_not_drop_an_independent_count():
    part1, part2 = "Explain Larkspur Energy's tidal battery announcement", "count its native ads"
    agent, _, cat, _ = harness([
        response("set_research_plan", {"tasks": [{"question_part": part1, "dataset": "native", "route": "record"},
                                                 {"question_part": part2, "dataset": "native", "route": "statistics"}]}),
        response("search_records", {"query": "tidal battery announcement", "filters": {
            "dataset": "native", "sponsors": ["Larkspur Energy"]}}, call_id="call_2"),
        response("record_statistics", {"filters": {"dataset": "native", "sponsors": ["Larkspur Energy"]},
                                       "group_by": "none"}, call_id="call_3"),
    ], catalog=catalog())
    run = agent.run(f"{part1}; {part2}.", Filters(dataset="native"), "visitor")
    assert [name for name, _ in cat.called] == ["search_records", "record_statistics"]
    assert run.route == "composite" and run.result["complete"] and not run.result["pending_parts"]
    assert [(p["question_part"], p["route"]) for p in run.result["parts"]] == [(part1, "evidence"), (part2, "statistics")]


def test_a_name_stored_as_another_type_is_not_reported_absent_on_the_last_step():
    elsewhere = {"status": "not_found", "candidates": [], "candidate_count": 0, "truncated": False,
                 "message": "No sponsor named like this; it is stored as an account.",
                 "stored_as_other_entity_type": [{"entity_type": "account", "dataset": "social",
                                                  "source_value": "Marigold Ferries"}]}
    agent, _, _, _ = harness(
        [response("resolve_entity", {"query": "Marigold Ferries", "entity_type": "sponsor", "restricts_read": True})],
        catalog=LarkspurCatalog({"resolve_entity": elsewhere}), max_steps=1, max_tool_calls=1)
    run = agent.run("Summarize Marigold Ferries's posts about tides.", Filters(dataset="social"), "visitor")
    assert run.failure_reason != "named_source_not_in_collection"
    assert "no records to cite" not in (run.result.get("message") or "")


def test_names_joined_by_a_semicolon_are_resolved_separately_not_reported_absent():
    absent = {"status": "not_found", "candidates": [], "candidate_count": 0, "truncated": False,
              "message": "No sponsor named like this is stored in the selected collection."}
    agent, _, cat, _ = harness(
        [response("resolve_entity", {"query": "Larkspur Energy; Marigold Gas", "entity_type": "sponsor",
                                     "restricts_read": True}),
         response("resolve_entity", {"query": "Larkspur Energy", "entity_type": "sponsor"}, call_id="call_2")],
        catalog=LarkspurCatalog({"resolve_entity": lambda args: absent if ";" in args["query"]
                                 else {"status": "ok", "candidates": [], "selected": args["query"]}}))
    run = agent.run("What did Larkspur Energy's ads and Marigold Gas's posts say about ferries?", Filters(dataset="all"), "visitor")
    assert run.failure_reason != "named_source_not_in_collection"
    assert [args["query"] for name, args in cat.called] == ["Larkspur Energy; Marigold Gas", "Larkspur Energy"]
