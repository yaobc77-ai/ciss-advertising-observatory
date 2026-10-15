"""Fictional "what do these ads say" lists: screening finds the ads, the writer reads them (B1K-Q052)."""
from datetime import date
from unittest.mock import Mock

from test_list_screening import KITE, VAGUE, passage, screening_service

from observatory.list_screening import Decision, list_answer
from observatory.models import Answer, Citation, CitedStatement, Filters
from observatory.question_policy import sources_content_request

ASK = "What do Tidal Co's ads say about kites? Cite each ad that mentions it."
MATCHES = [
    Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
    Decision(ref="A2", decision="does_not_match", passage_id="", quote=""),
    Decision(ref="A3", decision="matches", passage_id="A3.1", quote="Kites appear in the gallery."),
]


def written(*cited):
    """A writer answer with one claim per (evidence, quote) pair."""
    return Answer(status="answered", answer="", cost_usd=0.002,
                  citations=[Citation(evidence_id=e.evidence_id, quote=q) for e, q in cited],
                  cited_claims=[CitedStatement(text=f"The ad says: {q}", citation_indices=[n])
                                for n, (_, q) in enumerate(cited, 1)])


def test_the_wording_separates_what_ads_say_from_which_ads_qualify():
    assert sources_content_request(ASK)
    assert sources_content_request("What do Tidal Co's ads in Harbor Daily and Bay Weekly say about shipping?")
    assert sources_content_request("What do Tidal Co's ads say about kites, and what specific point does each make?")
    assert sources_content_request("哪些广告提到潮汐风筝，各自说了什么？")
    assert not sources_content_request("Which ads mention tidal kites?")
    assert not sources_content_request("Which ads describe tidal kites as cheap power?")
    assert not sources_content_request("List the ads that present kites as important for the harbor.")


def skips_gallery_ads(q, evidence, visitor, **_):
    """A fictional writer that describes the first ad it gets but never the gallery ad (r3)."""
    first = next((e for e in evidence if e.record_id != "r3"), None)
    return written((first, first.text.split(".")[0] + ".")) if first else Answer(status="insufficient_evidence", answer="")


def test_matched_ads_are_read_by_the_writer_and_merged_with_the_screened_list():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=skips_gallery_ads)
    result = service._answer_evidence(ASK, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    first, follow_up = service.rag.generate.call_args_list
    assert {p.record_id for p in first.args[1]} == {"r1", "r3"}  # only the matched ads, the non-match is not read
    assert first.kwargs["one_claim_per_source"] is True
    # The skipped ad gets one call of its own.
    assert {p.record_id for p in follow_up.args[1]} == {"r3"}
    assert result.answer.startswith("AI screening of the 3 most relevant")
    assert "The ad says: Tidal kites will supply cheap power to the harbor. [1]" in result.answer
    # Still not described: it keeps its screening quote under a renumbered citation.
    assert "Other matching ads (screening quote only):" in result.answer and "the gallery” [2]" in result.answer and "[2] [2]" not in result.answer
    assert [c.evidence_id for c in result.citations] == [KITE.evidence_id, VAGUE.evidence_id]
    assert result.structured_result["kind"] == "ai_screened_list"
    assert result.structured_result["content_reading"] == {
        "matched_records": 2, "sent_records": 2, "cited_records": 1, "partial_records": 1, "status": "partial"}
    gaps = {ad["record_id"]: ad["gaps"] for ad in result.research_trace["content_reading"]["records"]}
    assert gaps == {"r1": [], "r3": ["not_cited_by_writer"]}
    assert result.answer.endswith("the retrieved passages were not all read or the ad was not described.")
    assert result.research_trace["content_zones"] == [
        {"records": ["r1", "r3"], "kind": "shard", "status": "answered"},
        {"records": ["r3"], "kind": "follow_up", "status": "insufficient_evidence"}]
    assert result.cost_usd > 0.002  # screening plus the writer


def test_an_ad_the_writer_skips_is_described_by_the_follow_up_call():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=lambda q, evidence, visitor, **_: written((evidence[0], evidence[0].text[:20])))
    result = service._answer_evidence(ASK, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    assert service.rag.generate.call_count == 2
    assert result.structured_result["content_reading"]["status"] == "complete"
    assert "screening quote only" not in result.answer


def test_a_plain_list_question_is_not_sent_to_the_writer():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=AssertionError("a list question keeps one quote per ad"))
    result = service._answer_evidence("Which ads mention tidal kites?", Filters(dataset="native"), "offline", audit=False)
    assert "content_zones" not in result.research_trace


def test_a_failed_writer_call_keeps_the_screened_list():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(side_effect=ValueError("Unverifiable citation"))
    result = service._answer_evidence(ASK, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    assert "“Tidal kites will supply cheap power to the harbor” [1]" in result.answer
    assert result.research_trace["content_zones"][0]["status"] == "failed"
    assert result.structured_result["content_reading"]["status"] == "partial"
    assert result.answer.endswith("the ad was not described.")


def test_every_matched_ad_sent_whole_and_described_is_complete():
    service, _, _ = screening_service(MATCHES)
    service.rag.generate = Mock(return_value=written((KITE, "They are quiet."), (VAGUE, "Kites appear in the gallery.")))
    result = service._answer_evidence(ASK, Filters(dataset="native"), "offline", audit=False,
                                      declared_shape="every_matching_source")
    assert result.structured_result["content_reading"]["status"] == "complete"
    assert "partial" not in result.answer and "screening quote only" not in result.answer


def test_trimmed_or_capped_passages_are_recorded_per_ad():
    long = [passage("big", n, "Kite " + "word " * 3000) for n in range(9)]  # nine long passages of one ad
    results = [{"record_id": "big", "evidence_id": long[0].evidence_id, "decision": "matches", "quote": "Kite",
                "reason": "", "title": "Kite notice big", "publisher": "Harbor Daily", "sponsor": "Tidal Co",
                "published_at": date(2021, 5, 4)}]
    listed = list_answer(ASK, results, long, scope_total=1)
    service, _, _ = screening_service([])
    service.rag.generate = Mock(side_effect=lambda q, evidence, visitor, **_: written((evidence[0], "Kite")))
    merged, _ = service._read_matched_sources(ASK, listed, results, long, "offline")
    ad = merged.research_trace["content_reading"]["records"][0]
    assert ad["available_passages"] == 9 and ad["sent_passages"] < 9
    assert ad["gaps"] == ["passages_trimmed", "retrieval_cap_reached"]
    assert "Content reading is partial" in merged.answer


def test_many_matches_are_read_in_three_shards_of_four_and_the_rest_keep_their_quotes():
    ads = [passage(f"m{n}", 1, f"Kite model {n} lifts the harbor buoy.") for n in range(14)]
    results = [{"record_id": e.record_id, "evidence_id": e.evidence_id, "decision": "matches",
                "quote": e.text, "reason": "", "title": e.title, "publisher": e.publisher,
                "sponsor": e.sponsor, "published_at": date(2021, 5, 4)} for e in ads]
    listed = list_answer(ASK, results, ads, scope_total=14)
    service, _, _ = screening_service([])
    service.rag.generate = Mock(side_effect=lambda q, evidence, visitor, **_: written(*[(e, e.text) for e in evidence]))
    merged, cost = service._read_matched_sources(ASK, listed, results, ads, "offline")
    # Four ads per writer call leave room for a second claim on one ad (B1K-S).
    assert [len(call.args[1]) for call in service.rag.generate.call_args_list] == [4, 4, 4]
    assert len(merged.citations) == 14 and abs(cost - 0.006) < 1e-9
    assert [c.citation_indices for c in merged.cited_claims] == [[n] for n in range(1, 15)]
    assert merged.answer.count("The ad says:") == 12 and "(screening quote only)" in merged.answer
    reading = merged.research_trace["content_reading"]
    assert reading["partial_records"] == 2 and reading["records"][-1]["gaps"] == ["past_shard_limit"]
