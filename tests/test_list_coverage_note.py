"""A list or count answer built from retrieved passages says it holds examples only."""

from test_answer_failure_repair import generation_service, selected_payload

from observatory.models import Filters


def answer(question):
    service, _, _ = generation_service(selected_payload())
    # Both collections: list screening applies to native ads only.
    return service._answer_evidence(question, Filters(dataset="all"), "offline", audit=False)


def test_a_which_ads_question_is_told_it_received_examples_not_the_complete_list():
    result = answer("Which ads mention a winter reopening?")
    assert result.status == "answered"
    assert result.answer.endswith(
        "These are 1 supported example from the most relevant retrieved ads, not a complete list of every "
        "matching ad in the collection. A complete list or count needs article-by-article review.")
    assert result.research_trace["coverage_note"] == "retrieved_examples_only"


def test_a_chinese_list_question_gets_the_note_in_chinese():
    result = answer("哪些广告提到冬季重新开放？")
    assert "不是集合中全部相符广告的完整名单" in result.answer


def test_a_selection_by_stored_fields_answered_from_passages_is_still_labelled():
    # B1K: the note followed predicate detection, so 75 of 76 unscreened lists had none.
    result = answer("Which ads were published by Larkfield in 2031?")
    assert "not a complete list" in result.answer
    assert result.research_trace["coverage_note"] == "retrieved_examples_only"


def test_a_question_about_one_source_gets_no_list_note():
    result = answer("What schedule does the museum notice give?")
    assert "complete list" not in result.answer
    assert "coverage_note" not in result.research_trace


def test_an_empty_search_states_the_scope_it_searched():
    from datetime import date

    from observatory.service import empty_scope_note

    scope = Filters(dataset="social", accounts=["Larkfield"], date_from=date(2031, 3, 1), date_to=date(2031, 3, 31))
    note = empty_scope_note("What did the Larkfield account post about canals in March 2031?", scope)
    assert note == ("No stored records matched the searched scope (social posts; posts from source-listed "
                    "accounts Larkfield and posts dated 2031-03-01 to 2031-03-31).")
    assert empty_scope_note("Larkfield 账号 2031年3月发了什么？", scope).startswith("检索范围内没有找到相符的记录")
    assert "native ads; the current selection" in empty_scope_note("What about canals?", Filters(dataset="native"))


def test_an_unrecognised_list_that_cites_several_ads_is_still_labelled():
    # F04: the note backs up list recognition, so it cannot depend on it.
    from test_answer_failure_repair import fictional_evidence

    from observatory.models import Evidence

    payload = selected_payload()
    payload["claims"].append({"passage_id": "Q2", "text": "The ferry notice schedules sailings in winter."})
    payload["summary"][0]["citation_indices"] = [1, 2]
    service, _, _ = generation_service(payload)
    text = "The ferry notice says winter sailings are scheduled."
    second = Evidence(evidence_id="ferry-e1", record_id="ferry-record", version_id="ferry-v1",
                      dataset="native", title="Ferry notice", text=text, start=0, end=len(text))
    service.db.search = lambda *args, **kwargs: [fictional_evidence(), second]
    result = service._answer_evidence("Point me to winter schedules.", Filters(dataset="all"), "offline", audit=False)
    assert result.status == "answered"
    assert "These are 2 supported examples" in result.answer
    assert result.research_trace["coverage_note"] == "retrieved_examples_only"
