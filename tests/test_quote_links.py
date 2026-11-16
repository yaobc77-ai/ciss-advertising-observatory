from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask

from observatory.api import create_api
from observatory.models import Answer, Citation, Evidence
from observatory.quote_links import (
    citation_locations,
    mark_segments,
    parse_highlights,
    quote_range,
    record_quote_href,
)
from observatory.record_view import register_record_page

BODY = "Tidal Co builds kites. The kites fly over Marlow Bay every spring."


def evidence(**extra):
    text = BODY[23:]
    return {"evidence_id": "e1", "record_id": "rec/1", "version_id": "v1", "dataset": "native",
            "text": text, "start": 23, "end": 23 + len(text), **extra}


def test_quote_range_is_absolute_in_the_stored_body():
    start, end = quote_range(evidence(), "fly over Marlow Bay")
    assert BODY[start:end] == "fly over Marlow Bay"
    assert quote_range(evidence(), "not in the passage") is None
    assert quote_range(evidence(), "  ") is None


def test_record_href_carries_version_ranges_and_anchor():
    href = record_quote_href(evidence(), ["The kites", "Marlow Bay", "missing"])
    parts = urlsplit(href)
    assert parts.path == "/records/rec%2F1" and parts.fragment == "quote-1"
    assert parse_qs(parts.query) == {"v": ["v1"], "hl": ["23-32", "42-52"]}
    assert record_quote_href(evidence(), ["missing"]) == "/records/rec%2F1"


def test_observation_quotes_name_their_observation():
    href = record_quote_href(evidence(source_observation_id="src:7"), ["The kites"])
    assert parse_qs(urlsplit(href).query)["obs"] == ["src:7"]


def test_parse_and_mark_merge_overlaps_and_reject_out_of_range():
    assert parse_highlights(["5-9", "x-3", "9-2", "1-2-3", "0-4"]) == [(5, 9), (0, 4)]
    parts = mark_segments("abcdefghij", [(2, 5), (4, 7), (8, 9)])
    assert parts == [{"text": "ab", "mark": None}, {"text": "cdefg", "mark": 1}, {"text": "h", "mark": None},
                     {"text": "i", "mark": 2}, {"text": "j", "mark": None}]
    assert mark_segments("abc", [(1, 9)]) is None


def test_citation_locations_for_api_clients():
    located = citation_locations([{"evidence_id": "e1", "quote": "Marlow Bay"},
                                  {"evidence_id": "e9", "quote": "x"}], [evidence()])
    assert located[0]["location"]["start"] == 42 and located[0]["location"]["end"] == 52
    assert located[0]["location"]["record_url"].startswith("/records/rec%2F1?v=v1&hl=42-52")
    assert located[1]["location"] is None


class _Details:
    def __init__(self, record):
        self.record = record

    def get(self, record_id):
        return self.record if record_id == self.record["record_id"] else None


def record(**extra):
    return {"record_id": "rec-1", "version_id": "v1", "dataset": "native", "title": "Kites", "publisher": "Gull Gazette",
            "sponsor": "Tidal Co", "date": "2021-05-01", "body": BODY, "attachments": [], **extra}


def page(rec, query):
    app = Flask(__name__)
    register_record_page(app, _Details(rec))
    return app.test_client().get(f"/records/rec-1?{query}").get_data(as_text=True)


def test_record_page_marks_the_quoted_characters():
    html = page(record(), "v=v1&hl=42-52")
    assert '<mark class="cited-quote" id="quote-1">Marlow Bay</mark>' in html
    assert "Highlighted: 1 cited passage" in html


def test_record_page_escapes_marked_text():
    html = page(record(body="<b>bold</b> claim"), "v=v1&hl=0-11")
    assert '<mark class="cited-quote" id="quote-1">&lt;b&gt;bold&lt;/b&gt;</mark>' in html


@pytest.mark.parametrize("query, note", [("v=v0&hl=42-52", "has changed since the answer"),
                                         ("v=v1&hl=42-999", "does not match the stored text")])
def test_record_page_never_marks_a_stale_or_bad_position(query, note):
    html = page(record(), query)
    assert "<mark" not in html and note in html


def test_record_page_without_highlight_is_unchanged():
    assert "<mark" not in page(record(), "") and "quote-note" not in page(record(), "")


def test_record_page_marks_inside_the_cited_social_observation():
    rec = record(dataset="social", account="kites", platform="Twitter", social_admission={
        "scope": "s", "paid_ad_status": "unknown", "count_unit": "u", "member_count": 2, "conflicting_fields": [],
        "variants": [{"source_record_id": "src:1", "body": "first capture"},
                     {"source_record_id": "src:2", "body": "second capture text"}]})
    html = page(rec, "v=v1&obs=src:2&hl=7-14")
    assert '<mark class="cited-quote" id="quote-1">capture</mark> text' in html
    assert "first capture" in html and html.count("<mark") == 1


class _Service:
    def health(self):
        return {"status": "ok"}

    def answer(self, question, filters, visitor):
        ev = Evidence(**evidence(title="Kites"))
        return Answer(status="answered", answer="Kites fly [1].", evidence=[ev],
                      citations=[Citation(evidence_id="e1", quote="Marlow Bay")])


def test_api_ask_and_record_detail_return_quote_locations():
    details = _Details(record())
    client = create_api(_Service(), SimpleNamespace(api_cors_origins=()), record_details=details).test_client()
    body = client.post("/api/v1/ask", json={"question": "Where do kites fly?"}).get_json()
    location = body["citations"][0]["location"]
    assert (location["start"], location["end"]) == (42, 52)
    detail = client.get("/api/v1/records/rec-1?v=v1&hl=42-52").get_json()
    assert detail["highlights"] == {"status": "ok", "source_observation_id": None,
                                    "spans": [{"start": 42, "end": 52, "text": "Marlow Bay"}]}
    stale = client.get("/api/v1/records/rec-1?v=old&hl=42-52").get_json()
    assert stale["highlights"]["status"] == "version_changed"
