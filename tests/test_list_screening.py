"""Fictional list screening: every candidate gets a decision; only located quotes are listed."""
import json
import re

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from observatory.config import Settings
from observatory.list_screening import Batch, Decision, candidates_by_record, checked_decision, list_answer
from observatory.models import Evidence, Filters
from observatory.rag import Rag
from observatory.service import Service


def passage(record, n, text):
    return Evidence(evidence_id=f"{record}-e{n}", record_id=record, version_id=f"{record}-v", dataset="native",
                    title=f"Kite notice {record}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=0, end=len(text))


KITE = passage("r1", 1, "Tidal kites will supply cheap power to the harbor. They are quiet.")
OTHER = passage("r2", 1, "The festival program lists food stalls and music.")
VAGUE = passage("r3", 1, "Kites appear in the gallery.")


def test_a_match_needs_a_verbatim_quote_from_the_named_passage_of_that_ad():
    numbered = {"A1.1": KITE}
    good = Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap  power to the harbor.")
    assert checked_decision(good, numbered)["decision"] == "matches"
    invented = good.model_copy(update={"quote": "Tidal kites are the cheapest power source."})
    assert checked_decision(invented, numbered) == {"decision": "unclear", "reason": "quote_not_in_passage"}
    wrong_passage = good.model_copy(update={"passage_id": "A2.1"})
    assert checked_decision(wrong_passage, numbered) == {"decision": "unclear", "reason": "unknown_passage"}
    assert checked_decision(None, numbered) == {"decision": "unclear", "reason": "not_returned"}


def test_candidates_keep_retrieval_order_and_group_passages_by_record():
    second = passage("r1", 2, "Second passage.")
    assert candidates_by_record([KITE, OTHER, second], limit=1) == [[KITE, second]]


def test_the_list_states_how_many_ads_were_read_and_that_it_is_not_a_review():
    results = [{"record_id": "r1", "title": KITE.title, "publisher": KITE.publisher, "sponsor": KITE.sponsor,
                "published_at": KITE.published_at, "decision": "matches", "evidence_id": KITE.evidence_id,
                "quote": "Tidal kites will supply cheap power to the harbor."},
               {"record_id": "r2", "decision": "does_not_match", "title": "", "publisher": "", "sponsor": "",
                "published_at": None}]
    answer = list_answer("Which ads mention tidal kites?", results, [KITE, OTHER], scope_total=263)
    assert answer.status == "answered"
    assert answer.answer.startswith("AI screening of the 2 most relevant of 263 ads in the selected scope found 1 that match.")
    assert "1. Kite notice r1 — Harbor Daily, Tidal Co, 2021-05-04: “Tidal kites will supply cheap power to the harbor.” [1]" in answer.answer
    assert answer.citations[0].evidence_id == KITE.evidence_id
    assert answer.structured_result["kind"] == "ai_screened_list"
    assert "未核对" in list_answer("哪些广告提到潮汐风筝？", results, [KITE, OTHER], scope_total=263).answer


def screening_service(decisions):
    db = SimpleNamespace(
        validate_evidence=lambda _: True, connect=lambda: MagicMock(),
        health=lambda: {"status": "ok", "data_version": "kite-version"},
        public_rows=lambda _: [{"record_id": f"r{n}", "title": "", "dataset": "native"} for n in range(263)], search=Mock(return_value=[KITE, OTHER, VAGUE]), save_answer=Mock(),
    )

    def respond(**request):
        assert request["text_format"] is Batch
        return SimpleNamespace(
            status="completed", model="offline-fictional", output_parsed=Batch(decisions=decisions),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                  model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    parse = Mock(side_effect=respond)
    rag = Rag(db, Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    rag.budget = SimpleNamespace(reserve=Mock(return_value="kite-reservation"), settle=Mock(), uncertain=Mock(),
                                cancel_unsent=Mock(), reservation_cost=lambda _: 0.001)
    rag.embed = Mock(return_value=[[0.0]])
    service = Service(Settings(), db=db, rag=rag)
    service._search_external = Mock(side_effect=AssertionError("A screened list must not search the web"))
    return service, parse, db


def test_a_native_list_question_screens_every_candidate_and_lists_only_checked_matches():
    service, parse, db = screening_service([
        Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
        Decision(ref="A2", decision="does_not_match", passage_id="A2.1", quote=""),
        Decision(ref="A3", decision="matches", passage_id="A3.1", quote="Kites power the whole town."),
    ])
    result = service._answer_evidence("Which ads mention tidal kites?", Filters(dataset="native"), "offline", audit=False)
    assert parse.call_count == 1
    assert result.status == "answered"
    assert [c.evidence_id for c in result.citations] == [KITE.evidence_id]
    trace = result.research_trace["list_screening"]
    assert (trace["examined"], trace["matches"], trace["does_not_match"], trace["unclear"]) == (3, 1, 1, 1)
    assert "not a complete list" not in result.answer  # the screening header replaces the examples note
    # 120 ranked candidates are retrieved; only 40 are read unless matches continue.
    assert db.search.call_args.kwargs["limit"] == 120 and db.search.call_args.kwargs["chunks_per_record"] == 2
    service.rag.budget.cancel_unsent.assert_called_once()


def test_a_screened_list_without_matches_answers_none_found_and_does_not_search_the_web():
    service, _, _ = screening_service([Decision(ref=f"A{n}", decision="does_not_match", passage_id="", quote="")
                                      for n in (1, 2, 3)])
    result = service._answer_evidence("Which ads mention tidal kites?", Filters(dataset="native"), "offline", audit=False)
    assert result.status == "answered"
    assert result.status == "answered" and "found 0 that match" in result.answer
    service._search_external.assert_not_called()


def test_screening_counts_survive_the_retrieval_coverage_summary():
    service, _, _ = screening_service([
        Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
    ])
    result = service._answer_evidence("Which ads mention tidal kites?", Filters(dataset="native"), "offline", audit=False)
    assert result.structured_result["kind"] == "ai_screened_list"
    assert result.structured_result["examined"] == 3 and result.structured_result["groups"]


def test_a_quoted_phrase_must_occur_in_the_quote_allowing_hyphen_case_and_plural():
    from observatory.list_screening import contains_phrases, quoted_phrases

    assert quoted_phrases('Which ads mention "tidal kite"?') == ["tidal kite"]
    assert contains_phrases("Tidal-kites will supply cheap power.", ["tidal kite"])
    assert not contains_phrases("Kites ride the tide.", ["tidal kite"])
    numbered = {"A1.1": KITE}
    loose = Decision(ref="A1", decision="matches", passage_id="A1.1", quote="They are quiet.")
    assert checked_decision(loose, numbered, ["tidal kite"]) == {"decision": "unclear", "reason": "quoted_phrase_absent"}
    exact = loose.model_copy(update={"quote": "Tidal kites will supply cheap power to the harbor."})
    assert checked_decision(exact, numbered, ["tidal kite"])["decision"] == "matches"


def test_every_ad_with_a_quoted_phrase_is_screened_first_with_its_matching_passage():
    from observatory.list_screening import BATCH_SIZE

    literal = [passage(f"p{n}", 1, f"Tidal kites number {n} supply cheap power.") for n in range(45)]
    service, parse, db = screening_service([])
    db.phrase_search = Mock(return_value=literal)
    service._answer_evidence('Which ads present "tidal kites" as cheap power?', Filters(dataset="native"),
                             "offline", audit=False)
    assert db.phrase_search.call_args.args[0] == ["tidal kites"]
    # 45 literal ads plus 3 ranked ones fit in max(40, 45) = 45 screened records.
    assert parse.call_count == -(-45 // BATCH_SIZE)
    first_batch = parse.call_args_list[0].kwargs["input"][1]["content"]
    assert '"title": "Kite notice p0"' in first_batch


def test_typographic_quotes_in_a_model_quote_still_match_the_source():
    curly = passage("r9", 1, "The company said it’s “ready” now.")
    decision = Decision(ref="A1", decision="matches", passage_id="A1.1", quote="The company said it's \"ready\" now.")
    assert checked_decision(decision, {"A1.1": curly})["decision"] == "matches"


def test_a_pure_quoted_mention_question_lists_every_exact_match_without_a_model_call():
    literal = [passage(f"p{n}", 1, f"Intro. Tidal-kites number {n} supply cheap power. End.") for n in range(45)]
    service, parse, db = screening_service([])
    db.phrase_search = Mock(return_value=literal)
    result = service._answer_evidence('Which ads mention "tidal kites"?', Filters(dataset="native"), "offline", audit=False)
    assert parse.call_count == 0
    assert result.status == "answered" and len(result.citations) == 45
    assert result.citations[0].quote == "Tidal-kites number 0 supply cheap power."
    assert result.answer.startswith("An exact text search of the 263 ads in the selected scope found 45 whose "
                                    "indexed text contains “tidal kites”")
    assert result.structured_result["kind"] == "exact_text_list"


def test_only_a_bare_quoted_mention_is_treated_as_literal():
    from observatory.list_screening import phrase_sentence, pure_literal_question

    assert pure_literal_question('Which ads mention "tidal kites"?')
    assert pure_literal_question('List the ads that use the phrase “tidal kites”.')
    assert pure_literal_question('Which ads contain the words "tidal kites" anywhere in their text?')
    assert not pure_literal_question('Which ads say "tidal kites" are safe?')
    assert not pure_literal_question('Which ads mention "tidal kites" as a solution?')
    assert not pure_literal_question("Which ads mention tidal kites?")
    assert phrase_sentence("A. Big TIDAL kites rise! B.", "tidal kite") == "Big TIDAL kites rise!"


def test_a_quote_is_found_in_any_passage_of_the_ad_ignoring_case_edges_and_length():
    # B1K: 253 model matches were dropped, 138 only for exceeding the quote length.
    tail = passage("r1", 2, "Fishing crews, " + "harbor pilots and ferry operators " * 12 + "all back the kites.")
    numbered = {"A1.1": KITE, "A1.2": tail}
    other = Decision(ref="A1", decision="matches", passage_id="A1.1", quote="fishing crews, harbor pilots")
    assert checked_decision(other, numbered) == {"decision": "matches", "evidence_id": tail.evidence_id,
                                                 "quote": "Fishing crews, harbor pilots"}
    edged = other.model_copy(update={"passage_id": "A1.1", "quote": "“They are quiet,”"})
    assert checked_decision(edged, numbered)["quote"] == "They are quiet"
    long = other.model_copy(update={"quote": tail.text})
    kept = checked_decision(long, numbered)
    assert kept["decision"] == "matches" and len(kept["quote"]) <= 300 and tail.text.startswith(kept["quote"])
    assert checked_decision(other.model_copy(update={"quote": "harbor pilots sell kites"}), numbered)["reason"] == (
        "quote_not_in_passage")


def test_each_screened_ad_is_read_with_the_rest_of_its_article_in_document_order():
    later = passage("r1", 2, "A second kite line opens next spring.")
    later = later.model_copy(update={"start": 70, "end": 107})
    service, parse, db = screening_service([
        Decision(ref="A1", decision="matches", passage_id="A1.2", quote="A second kite line opens next spring."),
        Decision(ref="A2", decision="does_not_match", passage_id="A2.1", quote=""),
        Decision(ref="A3", decision="does_not_match", passage_id="A3.1", quote=""),
    ])
    db.record_passages = Mock(return_value=[KITE, later, OTHER, VAGUE])
    result = service._answer_evidence("Which ads announce a new kite line?", Filters(dataset="native"), "offline", audit=False)
    assert db.record_passages.call_args_list[0].args[0] == ["r1", "r2", "r3"]  # candidates and their order unchanged
    sent = parse.call_args.kwargs["input"][-1]["content"]
    assert sent.index(KITE.text) < sent.index(later.text) < sent.index(OTHER.text)
    assert [c.evidence_id for c in result.citations] == [later.evidence_id]


def gated(match_at):
    """Screen 60 one-passage ads; the model says an ad matches only at the given positions."""
    from observatory.list_screening import screen

    ads = [passage(f"g{n}", 1, f"Kite notice {n} about tidal kites on the harbor.") for n in range(1, 61)]
    seen = []

    def respond(**request):
        payload = json.loads(request["input"][-1]["content"])
        refs = [ad["ref"] for ad in payload["ads"]]
        seen.extend(refs)
        return SimpleNamespace(status="completed", output_parsed=Batch(decisions=[
            Decision(ref=ref, decision="matches" if int(ref[1:]) in match_at else "does_not_match",
                     passage_id=f"{ref}.1", quote="about tidal kites on the harbor") for ref in refs]),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                  model_dump=lambda: {}))

    rag = SimpleNamespace(settings=Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=respond)),
                          budget=SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock()))
    results, _ = screen(rag, "Which ads mention tidal kites?", ads, "offline", limit=40, widen_to=120)
    return len(results), sum(item["decision"] == "matches" for item in results)


def test_reading_past_forty_continues_only_while_matches_turn_up():
    # Matches continue near the cut: keep reading until a dry window of 16 ads, or the end.
    assert gated({3, 38, 45, 52}) == (60, 4)
    # No match in the last 16 of the first 40: stop at 40.
    assert gated({3, 10}) == (40, 2)
    # A late match extends the read by batches until 16 dry ads follow it.
    assert gated({39}) == (56, 1)


def test_a_quote_differing_only_by_spaces_lost_in_the_stored_text_still_matches():
    # Q round: "One benchmark solutionis shifting the grid" was quoted with its space restored and dropped.
    joined = passage("r4", 1, "Renewable EnergyOne benchmark solutionis shifting the electric grid to wind.")
    restored = Decision(ref="A1", decision="matches", passage_id="A1.1",
                        quote="One benchmark solution is shifting the electric grid")
    kept = checked_decision(restored, {"A1.1": joined})
    assert kept == {"decision": "matches", "evidence_id": joined.evidence_id,
                    "quote": "One benchmark solutionis shifting the electric grid"}
    invented = restored.model_copy(update={"quote": "One benchmark solution is burying the grid"})
    assert checked_decision(invented, {"A1.1": joined})["reason"] == "quote_not_in_passage"


def test_the_answer_lists_matches_only_without_ruled_out_or_unclear_counts():
    # User (2026-10-15): ads ruled out or left unclear are not part of the answer.
    service, _, _ = screening_service([
        Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
        Decision(ref="A2", decision="does_not_match", passage_id="", quote=""),
        Decision(ref="A3", decision="unclear", passage_id="", quote=""),
    ])
    for question in ("Which ads mention tidal kites?", "哪些广告提到潮汐风筝？"):
        result = service._answer_evidence(question, Filters(dataset="native"), "offline", audit=False)
        assert not re.search(r"Not matching|unclear|不符合|无法判断", result.answer)
        assert not {"does_not_match", "unclear"} & set(result.structured_result)
        trace = result.research_trace["list_screening"]
        assert (trace["does_not_match"], trace["unclear"]) == (1, 1)  # kept for review
