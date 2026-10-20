"""Fictional second check of listed ads: it may remove a listed ad, never add one (2026-10-18)."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from test_list_screening import KITE, OTHER, VAGUE, screening_service

import pytest

from observatory import list_screening
from observatory.list_screening import Decision, Verdict, Verdicts
from observatory.models import Filters

MATCHES = [
    Decision(ref="A1", decision="matches", passage_id="A1.1", quote="Tidal kites will supply cheap power to the harbor."),
    Decision(ref="A2", decision="does_not_match", passage_id="", quote=""),
    Decision(ref="A3", decision="matches", passage_id="A3.1", quote="Kites appear in the gallery."),
]


@pytest.fixture(autouse=True)
def second_check_on(monkeypatch):
    # Off in production since B1K-V (2026-10-19); these tests exercise the check itself.
    monkeypatch.setattr(list_screening, "VERIFY_LISTED", True)


def test_the_second_check_is_off_by_default():
    assert list_screening.VERIFY_LISTED is True  # the fixture above
    import importlib
    source = importlib.util.find_spec("observatory.list_screening").origin
    assert "VERIFY_LISTED = False" in open(source, encoding="utf-8").read()


def verifier(service, verdicts):
    """Replace the second check with fixed verdicts; return the mock that records its requests."""
    def respond(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        return SimpleNamespace(
            status="completed", output_parsed=Verdicts(verdicts=[v for v in verdicts if v.ref in {a["ref"] for a in ads}]),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                  model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    check = Mock(side_effect=respond)
    screening = service.rag.client.responses.parse
    service.rag.client.responses.parse = lambda **request: (check if request["text_format"] is Verdicts else screening)(**request)
    return check


def test_the_second_check_removes_a_listed_ad_and_records_why():
    service, _, _ = screening_service(MATCHES)
    check = verifier(service, [Verdict(ref="A1", verdict="keep", reason=""),
                               Verdict(ref="A2", verdict="remove", reason="different_thing")])
    result = service._answer_evidence("Which ads say tidal kites power the harbor?", Filters(dataset="native"),
                                      "offline", audit=False)
    sent = json.loads(check.call_args.kwargs["input"][1]["content"])["ads"]
    # Only the two listed ads are re-checked, each with its screening quote and passages.
    assert [ad["screening_quote"] for ad in sent] == ["Tidal kites will supply cheap power to the harbor",
                                                       "Kites appear in the gallery"]
    assert sent[1]["passages"] == [{"passage_id": "A2.1", "text": VAGUE.text}]
    assert [c.evidence_id for c in result.citations] == [KITE.evidence_id]
    trace = result.research_trace["list_screening"]
    assert trace["verified_removed"] == 1 and trace["matches"] == 1
    removed = next(d for d in trace["decisions"] if d["record_id"] == VAGUE.record_id)
    assert removed == {"record_id": VAGUE.record_id, "decision": "does_not_match", "reason": "different_thing",
                       "verified_from": "matches"}


def test_a_missing_verdict_keeps_the_ad():
    service, _, _ = screening_service(MATCHES)
    verifier(service, [])
    result = service._answer_evidence("Which ads say tidal kites power the harbor?", Filters(dataset="native"),
                                      "offline", audit=False)
    assert {c.evidence_id for c in result.citations} == {KITE.evidence_id, VAGUE.evidence_id}
    assert result.research_trace["list_screening"]["verified_removed"] == 0


def test_the_second_check_never_adds_an_ad():
    service, _, _ = screening_service(MATCHES)
    verifier(service, [Verdict(ref=f"A{n}", verdict="keep", reason="") for n in (1, 2, 3)])
    result = service._answer_evidence("Which ads say tidal kites power the harbor?", Filters(dataset="native"),
                                      "offline", audit=False)
    assert OTHER.evidence_id not in {c.evidence_id for c in result.citations}


def test_a_quoted_phrase_question_is_not_re_checked():
    service, _, db = screening_service(MATCHES)
    db.phrase_search = Mock(return_value=[])
    check = verifier(service, [Verdict(ref="A1", verdict="remove", reason="missing_relation")])
    service._answer_evidence('Which ads describe "tidal kites" as cheap power?', Filters(dataset="native"),
                             "offline", audit=False)
    check.assert_not_called()
