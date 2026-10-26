"""C15 keyword topic comparison: patterns, page rendering, API and app wiring (fictional data)."""
import re
from types import SimpleNamespace

import pytest

from observatory import api as api_module
from observatory.api import create_api
from observatory.topic_compare import (
    MAX_TOPICS,
    ask_question,
    first_match,
    topic_pattern,
    topic_table,
    topics_by_id,
)
from observatory.topic_compare_ui import render


@pytest.mark.parametrize("text, terms, found", [
    ("Tidal Co is scaling carbon capture at the harbor.", ["carbon capture"], "carbon capture"),
    ("Tidal Co is scaling carbon\ncapture at the harbor.", ["carbon capture"], "carbon\ncapture"),
    ("Kites sequestered the gusts.", ["sequester*"], "sequestered"),
    ("No CCSA here, only CCS.", ["CCS"], "CCS"),
    ("Our R&D team flies kites.", ["R&D"], "R&D"),
    ("A gas-fired kite plant.", ["gas-fired"], "gas-fired"),
    ("Recapture of kites.", ["capture"], None),
    ("Nothing on topic.", ["hydrogen"], None),
])
def test_whole_word_matching(text, terms, found):
    span = first_match(text, terms)
    assert (text[span[0]:span[1]] if span else None) == found


def test_postgres_pattern_uses_word_boundaries_and_escapes():
    pattern = topic_pattern(["R&D", "fuel cell*"])
    assert pattern == "(\\mR\\&D\\M|\\mfuel\\s+cell\\w*)"


def test_topic_table_is_valid_and_has_unique_ids():
    table = topic_table()
    ids = [t["id"] for t in table["topics"]]
    assert len(ids) == len(set(ids)) and "carbon_capture" in ids
    for topic in table["topics"]:
        assert topic["terms"] and topic["label"] and topic["label_zh"]
        re.compile(topic_pattern(topic["terms"], "py"))  # every term compiles


def test_ask_question_names_company_and_topics():
    question = ask_question("Tidal Co", ["carbon_capture", "hydrogen"])
    assert question.startswith("How do Tidal Co's native ads and its social posts discuss carbon capture")
    assert " and hydrogen?" in question


def result(**extra):
    item = {"mentions": 9, "mention_counts": [4, 5], "matched": 3, "undated": 1, "counts": [1, 1],
            "examples": [{"record_id": "kite-1", "title": "Kites over Marlow Bay", "date": "2021-05-01",
                          "source": "Gull Gazette", "url": "", "record_url": "/records/kite-1?v=v1&hl=4-9#quote-1",
                          "snippet": {"before": "The ", "match": "kites", "after": " fly."}}]}
    data = {"label": "x", "source_spellings": ["Tidal Co"], "total": 12, "undated": 2, "period_totals": [2, 10],
            "topics": {"carbon_capture": item}}
    return {"status": "ok", "company": "Tidal Co", "organization": "org:tidal", "review_status": "ai_proposed",
            "topics": [topics_by_id()["carbon_capture"]], "granularity": "year", "periods": ["2020", "2021"],
            "datasets": {"native": data, "social": {**data, "total": 0, "period_totals": [0, 0]}},
            "measure": "Counts.", "date_basis": "Dates.", "interpretation": "Leads only.", **extra}


def text_of(component):
    if isinstance(component, (str, int, float)):
        return str(component)
    if component is None:
        return ""
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(text_of(c) for c in children)
    return text_of(children)


def test_render_shows_shares_counts_and_linked_examples():
    page = render(result())
    text = text_of(page)
    assert "Tidal Co: native ads vs. social posts" in text
    assert "mentions · in 3 of 12 records · 1 undated" in text
    assert "per 1,000" not in text and "%" not in text and "Counts." in text
    assert "Leads only." in text
    links = []

    def walk(node):
        if getattr(node, "href", None):
            links.append(node.href)
        children = getattr(node, "children", None)
        for child in children if isinstance(children, (list, tuple)) else [children]:
            if child is not None and not isinstance(child, str):
                walk(child)
    walk(page)
    assert "/records/kite-1?v=v1&hl=4-9#quote-1" in links


def test_render_not_found_message():
    assert "no spelling is guessed" in text_of(render({"status": "not_found", "message": "No match; no spelling is guessed."}))


def test_api_compare_validates_and_returns_result(monkeypatch):
    seen = {}

    def fake(db, company, topics, **kwargs):
        seen.update(company=company, topics=topics, **kwargs)
        return {"status": "ok", "company": company}

    monkeypatch.setattr(api_module, "compare_topics", fake)
    client = create_api(SimpleNamespace(db=object()), SimpleNamespace(api_cors_origins=())).test_client()
    ok = client.get("/api/v1/compare?company=Tidal%20Co&topics=carbon_capture,hydrogen&date_from=2020-01-01")
    assert ok.status_code == 200 and seen["topics"] == ["carbon_capture", "hydrogen"]
    assert str(seen["date_from"]) == "2020-01-01" and seen["date_to"] is None
    assert client.get("/api/v1/compare?company=Tidal%20Co").status_code == 400
    assert client.get("/api/v1/compare?company=Tidal%20Co&topics=hydrogen&date_to=May").status_code == 400
    options = client.get("/api/v1/compare/topics").get_json()
    assert options["topics"][0]["terms"] and options["companies"]


def test_api_rejects_unknown_or_too_many_topics():
    client = create_api(SimpleNamespace(db=object()), SimpleNamespace(api_cors_origins=())).test_client()
    assert client.get("/api/v1/compare?company=Tidal%20Co&topics=kites").status_code == 400
    many = ",".join(t["id"] for t in topic_table()["topics"][:MAX_TOPICS + 1])
    assert client.get(f"/api/v1/compare?company=Tidal%20Co&topics={many}").status_code == 400


def test_compare_tab_is_wired_and_ask_fills_the_question_page():
    from observatory.app import create_app
    from tests.test_app import FakeService, callback

    app = create_app(FakeService(), SimpleNamespace(show_source_links=True, cookie_secret="test-cookie-secret",
                                                    monthly_budget_usd=100))
    keys = list(app.callback_map)
    assert any("compare-result.children" in key for key in keys)
    assert any("all-compare.hidden" in key for key in keys)
    client = app.server.test_client()
    values = {"compare-ask.n_clicks": 1, "compare-company.value": "Tidal Co", "compare-topics.value": ["hydrogen"]}
    shown = callback(app, client, "page-location.pathname", values, "compare-ask.n_clicks")
    assert shown["page-location"]["pathname"] == "/query" and shown["search-scope"]["value"] == "all"
    assert shown["research-question"]["value"].startswith("How do Tidal Co's native ads")
