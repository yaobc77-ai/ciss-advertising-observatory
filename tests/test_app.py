"""Exercise the actual Dash layout and callback HTTP protocol without external services."""

import csv
import json
from io import StringIO
from types import SimpleNamespace

import pytest

from observatory.app import create_app
from observatory.models import Answer, Citation, Evidence

SECRET = "private-disclosure-postgresql-secret-internal-path"
ORIGINAL = "https://example.test/original"
ARCHIVE = "https://archive.example.test/capture"


class FakeService:
    def __init__(self):
        self.browse_calls = []
        self.search_calls = []
        self.answer_calls = []
        self.fail_browse = False
        self.fail_answer = False
        self.answer_status = "answered"
        self.rows = [
            {
                "record_id": "native-a",
                "version_id": "version-a",
                "dataset": "native",
                "publisher": "Outlet A",
                "sponsor": "Sponsor A",
                "title": "A capture proposal",
                "date": "2024-01-01",
                "keyword": "CCS",
                "url": ORIGINAL,
                "archive_url": ARCHIVE,
                "retrievable": True,
                "labels": ["historical_solution"],
                "raw": {"secret": SECRET},
                "disclosure": SECRET,
                "internal_path": SECRET,
                "api_key": SECRET,
            },
            {
                "record_id": "native-b",
                "version_id": "version-b",
                "dataset": "native",
                "publisher": "Outlet B",
                "sponsor": "Sponsor B",
                "title": "=FORMULA()",
                "date": None,
                "keyword": "gas",
                "url": "javascript:alert(1)",
                "archive_url": "file:///private/capture.pdf",
                "retrievable": False,
                "labels": [],
            },
        ]

    def health(self):
        return {
            "status": "ok",
            "record_counts": {"native": 3, "social": 0},
            "data_version": "test",
            "dsn": SECRET,
        }

    def facets(self, dataset):
        return {
            "publishers": ["Outlet A", "Outlet B", "(Unknown)"],
            "sponsors": ["Sponsor A", "Sponsor B"],
            "platforms": [],
            "keywords": ["CCS", "gas"],
            "labels": ["historical_solution"],
        }

    def _selected(self, filters):
        if filters.dataset == "social":
            return []
        return [
            r
            for r in self.rows
            if (not filters.publishers or r["publisher"] in filters.publishers)
            and (not filters.sponsors or r["sponsor"] in filters.sponsors)
            and (filters.include_unknown_dates or r["date"] is not None)
        ]

    def browse(self, filters):
        self.browse_calls.append(filters)
        if self.fail_browse:
            raise RuntimeError(SECRET)
        return self._selected(filters)

    def statistics(self, filters):
        rows = self._selected(filters)

        def groups(field):
            names = {r[field] for r in rows}
            return [
                {
                    "name": n,
                    "count": sum(r[field] == n for r in rows),
                    "percent": 100 * sum(r[field] == n for r in rows) / len(rows),
                }
                for n in names
            ]

        return {
            "total": len(rows),
            "retrievable": sum(r["retrievable"] for r in rows),
            "unknown_dates": sum(r["date"] is None for r in rows),
            "publishers": groups("publisher"),
            "sponsors": groups("sponsor"),
            "platforms": [],
            "timeline": [{"month": "2024-01", "count": 1}] if rows else [],
            "relationships": [
                {"sponsor": r["sponsor"], "publisher": r["publisher"], "count": 1}
                for r in rows
            ],
        }

    def evidence(self):
        return Evidence(
            evidence_id="E1",
            record_id="native-a",
            version_id="version-a",
            dataset="native",
            title="A capture proposal",
            publisher="Outlet A",
            sponsor="Sponsor A",
            url=ORIGINAL,
            archive_url=ARCHIVE,
            text="The sponsor proposes a carbon capture project.",
            start=0,
            end=45,
        )

    def search(self, question, filters, limit=5):
        self.search_calls.append((question, filters, limit))
        return [self.evidence()] if filters.dataset != "social" else []

    def answer(self, question, filters, visitor):
        self.answer_calls.append((question, filters, visitor))
        if self.fail_answer:
            raise RuntimeError(SECRET)
        return Answer(
            status=self.answer_status,
            answer="The sponsor describes a proposed project."
            if self.answer_status == "answered"
            else SECRET,
            evidence=[self.evidence()],
            citations=[
                Citation(evidence_id="E1", quote="proposes a carbon capture project")
            ],
        )


@pytest.fixture
def application():
    service = FakeService()
    settings = SimpleNamespace(
        show_source_links=True,
        cookie_secret="test-cookie-secret",
        monthly_budget_usd=100,
    )
    app = create_app(service, settings)
    return app, app.server.test_client(), service


def component_tree(node):
    if isinstance(node, dict):
        if "props" in node:
            yield node
        for value in node.values():
            yield from component_tree(value)
    elif isinstance(node, list):
        for value in node:
            yield from component_tree(value)


def defaults(dataset):
    values = {
        f"{dataset}-{name}.value": []
        for name in ("publishers", "sponsors", "platforms", "keywords", "labels")
    }
    values.update(
        {
            f"{dataset}-dates.start_date": None,
            f"{dataset}-dates.end_date": None,
            f"{dataset}-unknown-dates.value": ["include"],
            f"{dataset}-metric.value": "count",
        }
    )
    return values


def callback(app, client, output_id, values, changed):
    key, spec = next(
        (key, spec) for key, spec in app.callback_map.items() if output_id in key
    )
    outs = spec["output"]
    outputs = (
        [{"id": out.component_id, "property": out.component_property} for out in outs]
        if isinstance(outs, list)
        else {"id": outs.component_id, "property": outs.component_property}
    )
    body = {
        "output": key,
        "outputs": outputs,
        "changedPropIds": [changed],
        "inputs": [
            {
                "id": x["id"],
                "property": x["property"],
                "value": values.get(x["id"] + "." + x["property"]),
            }
            for x in spec["inputs"]
        ],
        "state": [
            {
                "id": x["id"],
                "property": x["property"],
                "value": values.get(x["id"] + "." + x["property"]),
            }
            for x in spec["state"]
        ],
    }
    response = client.post("/_dash-update-component", json=body)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.json["response"]


def research_values(dataset="native", scope="current"):
    return (
        defaults("native")
        | defaults("social")
        | {
            "research-question.value": "carbon capture",
            "search-scope.value": scope,
            "active-dataset.value": dataset,
            "search-free.n_clicks": 1,
            "answer-paid.n_clicks": 0,
        }
    )


def test_layout_has_both_independent_panels_and_six_native_columns(application):
    app, client, _service = application
    assert client.get("/").status_code == 200
    response = client.get("/_dash-layout")
    assert response.status_code == 200
    components = {
        x["props"]["id"]: x["props"]
        for x in component_tree(response.json)
        if "id" in x["props"]
    }
    assert {f"{dataset}-publishers" for dataset in ("native", "social")} <= set(
        components
    )
    assert [col["field"] for col in components["native-grid"]["columnDefs"]] == [
        "url",
        "publisher",
        "title",
        "date",
        "sponsor",
        "keyword",
    ]
    assert components["research-question"]["maxLength"] == 2000
    assert SECRET not in response.get_data(as_text=True)
    assert client.get("/assets/observatory.css").status_code == 200
    assert client.get("/assets/source_links.js").status_code == 200
    changed = callback(
        app,
        client,
        "native-panel.style",
        {"active-dataset.value": "social"},
        "active-dataset.value",
    )
    assert changed["native-panel"]["style"] == {"display": "none"}
    assert changed["social-panel"]["style"] == {}
    assert len(changed) == 2  # Switching tabs must never reset any filter controls.


def test_filter_chart_and_export_use_same_records(application):
    app, client, service = application
    values = defaults("native") | {
        "native-sponsors.value": ["Sponsor A"],
        "native-metric.value": "percent",
    }
    result = callback(
        app, client, "native-grid.rowData", values, "native-sponsors.value"
    )
    rows = result["native-grid"]["rowData"]
    assert [r["record_id"] for r in rows] == ["native-a"]
    assert result["native-sponsors-chart"]["figure"]["data"][0]["x"] == [100.0]
    assert SECRET not in json.dumps(result)
    exported = callback(
        app,
        client,
        "native-download.data",
        values | {"native-export.n_clicks": 1},
        "native-export.n_clicks",
    )
    csv_rows = list(
        csv.DictReader(StringIO(exported["native-download"]["data"]["content"]))
    )
    assert [r["record_id"] for r in csv_rows] == [r["record_id"] for r in rows]
    assert service.browse_calls[-1] == service.browse_calls[-2]
    assert SECRET not in exported["native-download"]["data"]["content"]


def test_unknown_values_and_csv_formula_handling(application):
    app, client, _service = application
    result = callback(
        app,
        client,
        "native-grid.rowData",
        defaults("native"),
        "native-unknown-dates.value",
    )
    second = result["native-grid"]["rowData"][1]
    assert second["date"] == "(Unknown)"
    assert second["url"] == second["archive_url"] == ""
    exported = callback(
        app,
        client,
        "native-download.data",
        defaults("native") | {"native-export.n_clicks": 1},
        "native-export.n_clicks",
    )
    rows = list(
        csv.DictReader(StringIO(exported["native-download"]["data"]["content"]))
    )
    assert rows[1]["title"] == "'=FORMULA()"
    assert "javascript:" not in json.dumps(result)


def test_social_absence_is_explicit_and_has_no_fake_rows(application):
    app, client, _service = application
    result = callback(
        app, client, "social-grid.rowData", defaults("social"), "social-platforms.value"
    )
    assert result["social-grid"]["rowData"] == []
    assert "not connected" in json.dumps(result)


def test_free_search_never_calls_paid_answer_and_uses_active_filters(application):
    app, client, service = application
    values = research_values() | {
        "native-sponsors.value": ["Sponsor A"],
        "social-sponsors.value": ["Unrelated social sponsor"],
    }
    result = callback(
        app, client, "research-results.children", values, "search-free.n_clicks"
    )
    assert service.answer_calls == []
    assert service.search_calls[-1][1].sponsors == ["Sponsor A"]
    assert service.search_calls[-1][1].dataset == "native"
    serialized = json.dumps(result)
    assert "Last submitted search" in serialized
    assert "Sponsors: Sponsor A" in serialized
    assert "Unrelated social sponsor" not in serialized
    assert (
        "version-a" in serialized
        and "native-a" in serialized
        and ORIGINAL in serialized
    )


def test_all_scope_does_not_silently_carry_collection_filters(application):
    app, client, service = application
    values = research_values(scope="all") | {
        "native-sponsors.value": ["Sponsor A"],
        "social-platforms.value": ["Example platform"],
    }
    result = callback(
        app, client, "research-results.children", values, "search-free.n_clicks"
    )
    filters = service.search_calls[-1][1]
    assert filters.dataset == "all"
    assert filters.sponsors == filters.platforms == filters.publishers == []
    assert "all eligible records" in json.dumps(result)
    assert "Example platform" not in json.dumps(result)


def test_source_switch_covers_table_export_and_evidence():
    service = FakeService()
    app = create_app(
        service, SimpleNamespace(show_source_links=False, cookie_secret="test")
    )
    client = app.server.test_client()
    grid = callback(
        app, client, "native-grid.rowData", defaults("native"), "native-sponsors.value"
    )
    export = callback(
        app,
        client,
        "native-download.data",
        defaults("native") | {"native-export.n_clicks": 1},
        "native-export.n_clicks",
    )
    evidence = callback(
        app,
        client,
        "research-results.children",
        research_values(),
        "search-free.n_clicks",
    )
    for output in (grid, export, evidence):
        text = json.dumps(output)
        assert ORIGINAL not in text and ARCHIVE not in text
        assert SECRET not in text


def test_paid_answer_uses_server_session_and_preserves_evidence(application):
    app, client, service = application
    values = research_values() | {"answer-paid.n_clicks": 1}
    first = callback(
        app, client, "research-results.children", values, "answer-paid.n_clicks"
    )
    callback(
        app,
        client,
        "research-results.children",
        values | {"answer-paid.n_clicks": 2},
        "answer-paid.n_clicks",
    )
    assert len(service.answer_calls) == 2
    assert service.answer_calls[0][2] == service.answer_calls[1][2]
    assert service.answer_calls[0][2] not in json.dumps(first)
    assert "proposes a carbon capture project" in json.dumps(first)


@pytest.mark.parametrize("status", ["limited", "service_unavailable"])
def test_paid_service_status_hides_internal_messages(application, status):
    app, client, service = application
    service.answer_status = status
    result = callback(
        app,
        client,
        "research-results.children",
        research_values(),
        "answer-paid.n_clicks",
    )
    assert SECRET not in json.dumps(result)
    assert "keyword search" in json.dumps(result)


def test_paid_failure_falls_back_to_keyword_evidence(application):
    app, client, service = application
    service.fail_answer = True
    result = callback(
        app,
        client,
        "research-results.children",
        research_values(),
        "answer-paid.n_clicks",
    )
    assert len(service.search_calls) == 1
    assert "native-a" in json.dumps(result)
    assert SECRET not in json.dumps(result)


def test_invalid_dates_and_oversized_questions_do_not_call_services(application):
    app, client, service = application
    invalid = defaults("native") | {
        "native-dates.start_date": "2025-01-01",
        "native-dates.end_date": "2024-01-01",
    }
    result = callback(
        app, client, "native-grid.rowData", invalid, "native-dates.start_date"
    )
    assert "Check the filters" in json.dumps(result)
    assert service.browse_calls == []
    callback(
        app,
        client,
        "research-results.children",
        research_values() | {"research-question.value": "x" * 2001},
        "search-free.n_clicks",
    )
    assert service.search_calls == service.answer_calls == []


def test_collection_exception_is_sanitized(application):
    app, client, service = application
    service.fail_browse = True
    result = callback(
        app,
        client,
        "native-grid.rowData",
        defaults("native"),
        "native-publishers.value",
    )
    assert SECRET not in json.dumps(result)
    assert "temporarily unavailable" in json.dumps(result)
