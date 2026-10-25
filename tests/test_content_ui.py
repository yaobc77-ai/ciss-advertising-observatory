"""Reviewed list presentation and pagination, independent of live model calls."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from dash import Dash, dcc, html
from plotly.utils import PlotlyJSONEncoder
from test_app import callback, component_tree

from observatory.content_ui import (
    content_panel,
    content_record_cards,
    content_summary,
    read_content_page,
    register_content_browser,
)
from observatory.models import Filters
from tests.test_content_research import public_result


def page_service(count=23):
    def read(filters, *, question_id, offset, limit):
        result = public_result()
        result.update(source_scope_sha256="d" * 64,
                      totals={"scope_records": count + 2, "relevant": count, "not_relevant": 1, "unknown": 1},
                      records=[{"record_id": f"r{i}"} for i in range(count)][offset:offset + limit],
                      offset=offset, limit=limit, page_complete=offset == 0 and count <= limit,
                      next_offset=offset + limit if offset + limit < count else None)
        return result
    return SimpleNamespace(content_matches=read)


def test_multi_page_membership_retains_whole_scope_and_exact_members():
    service, seen, state = page_service(), [], None
    for direction in (None, "next", "next"):
        result, state = read_content_page(service, Filters(), "Q03", state, direction)
        seen.extend(row["record_id"] for row in result["records"])
        assert result["totals"] == {"scope_records": 25, "relevant": 23, "not_relevant": 1, "unknown": 1}
        assert not result["page_complete"] and not result["coverage"]["classification_complete"]
    assert seen == [f"r{i}" for i in range(23)]
    assert result["next_offset"] is None  # Last page is not a whole matching set.


@pytest.mark.parametrize("change", ["question", "filters", "publication", "source", "offset", "direction"])
def test_changed_or_forged_page_identity_does_not_continue_a_list(change):
    service = page_service()
    _, state = read_content_page(service, Filters(), "Q03")
    question, filters, direction = "Q03", Filters(), "next"
    if change == "question":
        question = "Q04"
    elif change == "filters":
        filters = Filters(sponsors=["shell"])
    elif change == "publication":
        state["publication_version"] = "forged"
    elif change == "source":
        state["source_scope_sha256"] = "forged"
    elif change == "offset":
        state["offset"] = True
    elif change == "direction":
        direction = "write"
    with pytest.raises(ValueError):
        read_content_page(service, filters, question, state, direction)


def test_no_positive_but_unknown_is_not_displayed_as_absence():
    result = public_result()
    result["totals"] = {"scope_records": 4, "relevant": 0, "not_relevant": 1, "unknown": 3}
    text = content_summary(result)
    assert "3 unknown" in text and "additional matches" in text
    assert "no advertisements" not in text
    assert "not negative" in content_summary({"available": False})


def test_inconsistent_or_unknown_complete_totals_cannot_be_displayed():
    result = public_result()
    result["coverage"]["classification_complete"] = True
    with pytest.raises(ValueError):
        content_summary(result)
    result = public_result()
    result["totals"]["scope_records"] = 100
    with pytest.raises(ValueError):
        content_summary(result)


def test_evidence_cards_are_readable_and_honor_link_switch():
    result = public_result()
    result["records"] = [{"record_id": "r1", "version_id": "a" * 64, "title": "Current ad",
                          "publisher": "Outlet", "sponsor": "exxonmobil", "date": None,
                          "url": "https://example.org/ad", "speaker": "Company", "treatment": "reported",
                          "temporal_status": "planned", "rationale": "The ad presents this as a plan.",
                          "support_evidence": [{"quote": "甲😀 says blue hydrogen.", "start": 0, "end": 23}],
                          "limiting_evidence": [{"quote": "The project is proposed.", "start": 25, "end": 49}],
                          "consensus_evidence": [], "consensus_position": "not_applicable"}]
    cards = json.dumps(content_record_cards(result, False), cls=PlotlyJSONEncoder, ensure_ascii=False)
    assert "Supporting text" in cards and "Qualifications or limitations" in cards
    assert "Source location" in cards and "Publication date unknown" in cards and "甲😀" in cards
    assert "https://example.org/ad" not in cards and "/records/r1" in cards
    assert "https://example.org/ad" in json.dumps(content_record_cards(result, True), cls=PlotlyJSONEncoder)
    assert result["records"][0]["url"] == "https://example.org/ad"  # Rendering never mutates the source result.


def test_pending_panel_has_fixed_questions_without_placeholder_results():
    encoded = json.dumps(content_panel(), cls=PlotlyJSONEncoder)
    assert "Reviewed content questions" in encoded and '"value": "Q24"' in encoded
    assert '"value": "Q25"' not in encoded and "independent fact" not in encoded


def test_export_current_page_rechecks_bound_selection_without_changing_offset():
    service = page_service()
    _, state = read_content_page(service, Filters(), "Q03")
    result, state = read_content_page(service, Filters(), "Q03", state, "next")
    reread, unchanged = read_content_page(service, Filters(), "Q03", deepcopy(state), "current")
    assert reread == result and unchanged == state


@pytest.fixture
def content_app():
    service = page_service()
    original = service.content_matches
    service.calls = []

    def read(filters, **kwargs):
        service.calls.append((filters, kwargs))
        result = original(filters, **kwargs)
        for row in result["records"]:
            row.update(title="Synthetic " + row["record_id"], version_id="a" * 64,
                       support_evidence=[{"start": 0, "end": 3, "quote": "CCS"}])
        return result

    service.content_matches = read
    app = Dash(__name__)
    app.layout = html.Div([dcc.Store(id="native-network-data"), dcc.Location(id="page-location"),
                          dcc.RadioItems(id="native-view", value="overview"),
                          dcc.RadioItems(id="active-dataset", value="native"), content_panel()])
    register_content_browser(app, service, links_enabled=True)
    return app, app.server.test_client(), service


def ui_values():
    return {"native-network-data.data": {"filters": {"dataset": "native", "sponsors": ["shell"]}},
            "page-location.pathname": "/data", "native-view.value": "overview",
            "active-dataset.value": "native", "content-reviewed-question.value": "Q03",
            "content-reviewed-prev.n_clicks": 0, "content-reviewed-next.n_clicks": 0,
            "content-reviewed-page.data": {"offset": 0}, "content-reviewed-export.n_clicks": 1}


def test_actual_dash_callbacks_page_and_export_exact_current_selection(content_app):
    app, client, service = content_app
    inputs = ui_values()
    first = callback(app, client, "content-reviewed-results.children", inputs, "native-network-data.data")
    assert "23 reviewed matches" in first["content-reviewed-status"]["children"]
    assert "1 unknown" in first["content-reviewed-status"]["children"]
    assert not first["content-reviewed-next"]["disabled"]
    inputs["content-reviewed-page.data"] = first["content-reviewed-page"]["data"]
    second = callback(app, client, "content-reviewed-results.children", inputs, "content-reviewed-next.n_clicks")
    links = {node["props"]["href"] for node in component_tree(second)
             if node.get("type") == "Link" and node["props"].get("href", "").startswith("/records/")}
    assert links == {f"/records/r{i}" for i in range(10, 20)}
    assert "CCS" in json.dumps(second)
    inputs["content-reviewed-page.data"] = second["content-reviewed-page"]["data"]
    exported = callback(app, client, "content-reviewed-download.data", inputs, "content-reviewed-export.n_clicks")
    packet = json.loads(exported["content-reviewed-download"]["data"]["content"])
    assert {row["record_id"] for row in packet["records"]} == {f"r{i}" for i in range(10, 20)}
    assert not packet["page_complete"] and not packet["coverage"]["classification_complete"]
    assert service.calls[-1][1]["offset"] == 10 and service.calls[-1][0].sponsors == ["shell"]
    inputs["content-reviewed-page.data"]["source_scope_sha256"] = "changed"
    invalid = callback(app, client, "content-reviewed-download.data", inputs, "content-reviewed-export.n_clicks")
    assert "content-reviewed-download" not in invalid
    assert "Refresh" in invalid["content-reviewed-export-status"]["children"]


@pytest.mark.parametrize("change,value", [("page-location.pathname", "/query"),
                                         ("native-view.value", "relationships"),
                                         ("active-dataset.value", "social")])
def test_hidden_content_callback_does_not_read_sources(content_app, change, value):
    app, client, service = content_app
    inputs = ui_values()
    inputs[change] = value
    result = callback(app, client, "content-reviewed-results.children", inputs, change)
    assert not service.calls and result["content-reviewed-results"]["children"] == []


def test_dash_unavailable_and_empty_scopes_do_not_share_zero_or_unknown_wording(content_app):
    app, client, service = content_app
    service.content_matches = lambda *args, **kwargs: {"status": "unavailable", "available": False}
    pending = callback(app, client, "content-reviewed-results.children", ui_values(), "native-network-data.data")
    assert "awaiting publication" in pending["content-reviewed-status"]["children"]
    assert "0 reviewed" not in pending["content-reviewed-status"]["children"]
    service.content_matches = lambda *args, **kwargs: public_result() | {
        "totals": {"scope_records": 0, "relevant": 0, "not_relevant": 0, "unknown": 0},
        "coverage": {"classification_complete": True}, "records": [], "page_complete": True}
    empty = callback(app, client, "content-reviewed-results.children", ui_values(), "native-network-data.data")
    assert "0 current records" in empty["content-reviewed-status"]["children"]
    assert "Complete classification for this question and selection" in empty["content-reviewed-status"]["children"]


def test_query_card_uses_same_reviewed_sources_and_summary_evidence_scope(tmp_path):
    from observatory.app import _tools_card
    from observatory.service import Service
    from tests.test_content_research import reviewed_service

    service, _, path = reviewed_service(tmp_path)
    answer = Service._tool_content_answer(service.content_matches(Filters(), question_id="Q06"))
    rendered = json.dumps(_tools_card(answer.model_dump(mode="json"), False), cls=PlotlyJSONEncoder)
    for required in ("Summary", "Evidence", "Scope and limits", "CCS", "1 unknown", "/records/one"):
        assert required in rendered
    assert "https://example.org/one" not in rendered
    assert str(path) not in rendered and "Synthetic named reviewer" not in rendered
