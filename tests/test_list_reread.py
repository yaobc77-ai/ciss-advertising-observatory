"""Fictional re-reading: an ad is not ruled out from part of its text (R1; B1K-R: 29 such ads ruled out)."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from test_list_screening import passage

from observatory import list_screening
from observatory.config import Settings
from observatory.list_screening import Batch, Decision, screen

ASK = "Which ads say kites power the harbor?"
OPENING = passage("r1", 1, "Tidal Co sponsors the spring festival on the pier.")
LATER = passage("r1", 2, "By night, kites power the harbor lights.")
SHORT = passage("r2", 1, "The gallery shows paper kites from the bay.")
CLEAR = passage("r3", 1, "Kites power the harbor every windy day.")


def fake_rag():
    """A model that matches an ad only when a supplied passage says kites power the harbor."""
    def respond(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        decisions = []
        for ad in ads:
            hit = next((p for p in ad["passages"] if "power the harbor" in p["text"]), None)
            decisions.append(Decision(ref=ad["ref"], decision="matches" if hit else "does_not_match",
                                      passage_id=hit["passage_id"] if hit else "", quote=hit["text"] if hit else ""))
        return SimpleNamespace(status="completed", output_parsed=Batch(decisions=decisions),
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                     input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                                     model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    return SimpleNamespace(settings=Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=Mock(side_effect=respond))),
                           budget=SimpleNamespace(reserve=Mock(return_value="kite"), settle=Mock(), uncertain=Mock()))


def whole_text(ids):
    return [p for p in (OPENING, LATER, SHORT, CLEAR) if p.record_id in ids]


def test_an_ad_ruled_out_from_part_of_its_text_is_judged_again_on_the_whole_text():
    rag = fake_rag()
    reread = Mock(side_effect=whole_text)
    results, _ = screen(rag, ASK, [OPENING, SHORT, CLEAR], "offline", reread=reread)
    by_id = {item["record_id"]: item for item in results}
    assert by_id["r1"]["decision"] == "matches" and by_id["r1"]["reread_from"] == "does_not_match"
    assert by_id["r1"]["evidence_id"] == LATER.evidence_id
    # r2 was already read whole, r3 already matched: neither is sent again.
    assert "reread_from" not in by_id["r2"] and "reread_from" not in by_id["r3"]
    assert reread.call_args.args[0] == ["r1", "r2"]
    assert rag.client.responses.parse.call_count == 2
    stages = [call.args[2]["observatory_request"]["stage"] for call in rag.budget.settle.call_args_list]
    assert stages == ["list_screening", "list_screening_reread"]


def test_nothing_is_reread_when_every_ruled_out_ad_was_shown_whole():
    rag = fake_rag()
    results, _ = screen(rag, ASK, [OPENING, LATER, SHORT], "offline", reread=whole_text)
    assert rag.client.responses.parse.call_count == 1
    assert [item["decision"] for item in results] == ["matches", "does_not_match"]


def test_without_a_reader_the_screening_is_unchanged():
    rag = fake_rag()
    results, _ = screen(rag, ASK, [OPENING, SHORT], "offline")
    assert [item["decision"] for item in results] == ["does_not_match", "does_not_match"]
    assert rag.client.responses.parse.call_count == 1


def test_long_articles_are_reread_in_calls_bounded_by_text_size(monkeypatch):
    monkeypatch.setattr(list_screening, "REREAD_CHARS", 100)
    articles = [[passage(f"L{n}", 1, "x" * 60), passage(f"L{n}", 2, "y" * 30)] for n in range(3)]
    assert [len(batch) for batch in list_screening._reread_batches(articles)] == [1, 1, 1]
    assert [len(batch) for batch in list_screening._reread_batches([[SHORT]] * 3)] == [2, 1]  # 43 characters each


def test_the_service_cites_a_match_found_on_rereading():
    from test_list_screening import screening_service

    from observatory.models import Filters

    service, _, db = screening_service([])
    service.rag.client.responses.parse = fake_rag().client.responses.parse
    db.search.return_value = [OPENING, SHORT]
    # The first read shows each ad's opening passage only; the whole text is fetched on request.
    db.record_passages = Mock(side_effect=lambda ids, filters, per_record=8:
                              whole_text(ids) if per_record is None else [p for p in (OPENING, SHORT) if p.record_id in ids])
    result = service._answer_evidence(ASK, Filters(dataset="native"), "offline", audit=False)
    assert [c.evidence_id for c in result.citations] == [LATER.evidence_id]
    assert result.research_trace["list_screening"]["reread"] == 1
