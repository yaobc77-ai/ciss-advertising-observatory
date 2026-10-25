"""Fictional list answers that answer in words first, then list every match, with chart data (2026-10-19)."""
from datetime import date
from unittest.mock import Mock

from test_list_screening import KITE, VAGUE, screening_service
from test_multi_source_content import ASK as SAYS_ASK
from test_multi_source_content import written

from observatory.list_screening import Decision, list_charts
from observatory.models import CitedStatement, Filters

LIST_ASK = "Which ads say tidal kites power the harbor?"
MATCHES = [
    Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
    Decision(ref="A2", decision="does_not_match", passage_id="", quote=""),
    Decision(ref="A3", decision="matches", passage_id="A3.1", quote="Kites appear in the gallery."),
]


def summarized(**answer):
    service, _, _ = screening_service(MATCHES)
    reply = written((KITE, "They are quiet."))
    service.rag.generate = Mock(return_value=reply.model_copy(update=answer))
    return service, service._answer_evidence(LIST_ASK, Filters(dataset="native"), "offline", audit=False)


def test_a_list_answer_opens_with_a_written_answer_then_lists_every_match():
    service, result = summarized(summary=[CitedStatement(text="Tidal Co ads call the kites quiet.", citation_indices=[1])])
    passages = service.rag.generate.call_args.args[1]
    assert {p.record_id for p in passages} == {"r1", "r3"}  # matched ads only, most relevant first
    # Summary: the coverage line, then the writer's summary.
    assert result.summary[0].text.startswith("Found 2 matching ads among the 3 most relevant") and not result.summary[0].citation_indices
    assert result.summary[1].text == "Tidal Co ads call the kites quiet."
    assert [s.title for s in result.sections] == ["Key points", "Matching ads (2)"]
    # Writer citations first, then the screened list renumbered after them.
    assert [c.evidence_id for c in result.citations] == [KITE.evidence_id, KITE.evidence_id, VAGUE.evidence_id]
    assert [c.citation_indices for c in result.cited_claims] == [[1], [2], [3]]
    assert result.sections[1].citation_indices == [2, 3]
    assert not result.cited_claims[1].text.endswith("]")  # the old "[1]" is not repeated
    assert result.structured_result["summary_basis"] == "Summary drawn from the 2 most relevant matching ads."
    assert "Summary drawn" not in result.answer  # kept out of the reader's text
    assert result.structured_result["display_citations"] == [1, 2, 3]
    assert result.research_trace["list_summary"] == {"status": "answered", "records": ["r1", "r3"]}


def test_without_a_writer_summary_the_first_points_stand_in():
    _, result = summarized()
    assert [s.text for s in result.summary][1:] == ["The ad says: They are quiet."]


def test_a_failed_writer_leaves_the_list_answer_unchanged():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=ValueError("Unverifiable citation"))
    result = service._answer_evidence(LIST_ASK, Filters(dataset="native"), "offline", audit=False)
    assert not result.summary and not result.sections
    assert "“Tidal kites will supply cheap power to the harbor” [1]" in result.answer
    assert result.research_trace["list_summary"] == {"status": "failed", "reason": "ValueError"}


def test_a_what_do_they_say_list_is_shown_in_sections_too():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(return_value=written((KITE, "They are quiet.")))
    result = service._answer_evidence(SAYS_ASK, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    assert result.summary[0].text.startswith("Found 2 matching ads among the 3 most relevant")
    assert [s.title for s in result.sections] == ["What the matching ads say", "Other matching ads (screening quote only)"]


def item(sponsor, year, publisher):
    return {"sponsor": sponsor, "published_at": date(year, 5, 1) if year else None, "publisher": publisher}


def test_charts_count_the_listed_ads_by_sponsor_year_and_outlet():
    charts = {c["id"]: c for c in list_charts([item("totalenergies", 2019, "CNBC"), item("shell", 2020, "CNBC"),
                                               item("totalenergies", None, "Forbes")])}
    assert charts["by_sponsor"]["labels"] == ["TotalEnergies", "Shell"] and charts["by_sponsor"]["values"] == [2, 1]
    assert charts["by_year"]["labels"] == ["2019", "2020", "Unknown"]  # chronological, unknown last
    assert charts["by_outlet"]["values"] == [2, 1]


def test_charts_are_left_out_when_they_would_say_nothing():
    assert list_charts([item("shell", 2019, "CNBC"), item("shell", 2020, "CNBC")]) == []  # fewer than 3 ads
    charts = list_charts([item("shell", 2019, "CNBC")] * 3)
    assert charts == []  # one category in every dimension
    many = list_charts([item(f"Co {n}", 2019 + n % 2, "CNBC") for n in range(15)])
    sponsors = next(c for c in many if c["id"] == "by_sponsor")
    assert len(sponsors["labels"]) == 12 and sponsors["omitted_categories"] == 3


def test_the_answer_page_shows_the_list_charts():
    from dash import dcc

    from observatory.app import _render_answer_result

    _, result = summarized(summary=[CitedStatement(text="Tidal Co ads call the kites quiet.", citation_indices=[1])])
    payload = result.model_dump(mode="json")
    payload["structured_result"]["charts"] = list_charts([item("totalenergies", 2019, "CNBC"), item("shell", 2020, "CNBC"),
                                                           item("totalenergies", 2020, "Forbes")])

    def graphs(node):
        found = [node] if isinstance(node, dcc.Graph) else []
        children = getattr(node, "children", None)
        for child in (children if isinstance(children, list) else [children] if children is not None else []):
            found.extend(graphs(child))
        return found

    cards = _render_answer_result(payload, links_enabled=False, service=None)
    assert len([g for card in cards if card is not None for g in graphs(card)]) == 3


def test_the_answer_lists_ten_ads_and_counts_the_rest_while_every_match_stays_cited():
    from test_list_screening import passage

    from observatory.list_screening import list_answer

    ads = [passage(f"m{n}", 1, f"Kite model {n} lifts the harbor buoy.") for n in range(12)]
    results = [{"record_id": e.record_id, "evidence_id": e.evidence_id, "decision": "matches", "quote": e.text,
                "title": e.title, "publisher": e.publisher, "sponsor": e.sponsor, "published_at": e.published_at}
               for e in ads]
    answer = list_answer("Which ads mention kite models?", results, ads, scope_total=12)
    assert len(answer.citations) == 12 and answer.structured_result["display_citations"] == list(range(1, 11))
    assert "10. Kite notice m9" in answer.answer and "11. " not in answer.answer
    assert answer.answer.endswith("2 more matching ads not shown here.")
    zh = list_answer("哪些广告提到风筝型号？", results, ads, scope_total=12)
    assert zh.answer.endswith("另有 2 篇符合，未在此列出。")


def test_the_date_basis_note_stays_out_of_the_answer_text():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=ValueError("writer off"))
    service._cites_inferred_dates = Mock(return_value=True)
    result = service._answer_evidence(LIST_ASK, Filters(dataset="native"), "offline", audit=False)
    assert "tier" not in result.answer.lower()
    assert "tier A" in result.research_trace["date_note"]


def test_the_page_shows_only_the_passages_of_the_displayed_citations():
    from observatory.app import _render_answer_result

    _, result = summarized(summary=[CitedStatement(text="Tidal Co ads call the kites quiet.", citation_indices=[1])])
    payload = result.model_dump(mode="json")
    payload["structured_result"]["display_citations"] = [1]
    rendered = str(_render_answer_result(payload, links_enabled=False, service=None))
    cards = rendered.split("Records and quoted evidence", 1)[1]
    assert cards.count("evidence-heading") == 1 and "Kite notice r1" in cards and "Kite notice r3" not in cards


def test_each_claim_shows_its_exact_quote_in_bold():
    from dash import html

    from observatory.app import _claim_with_quotes

    citations = [{"evidence_id": "e1", "quote": "Tidal kites will supply cheap power"},
                 {"evidence_id": "e2", "quote": "They are quiet."}]
    listed = _claim_with_quotes({"text": "Kite notice — Harbor Daily: “Tidal kites will supply cheap power”",
                                 "citation_indices": [1]}, citations)
    assert isinstance(listed[1], html.Strong) and listed[1].children == "“Tidal kites will supply cheap power”"
    written = _claim_with_quotes({"text": "The ad calls the kites quiet.", "citation_indices": [2]}, citations)
    assert written[0] == "The ad calls the kites quiet." and written[-1].children == "“They are quiet.”"
    assert _claim_with_quotes({"text": "No citation.", "citation_indices": []}, citations) == ["No citation."]
