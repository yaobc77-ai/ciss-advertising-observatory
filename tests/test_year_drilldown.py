from datetime import date
from types import SimpleNamespace

import pytest

from observatory.api import create_api
from observatory.models import Filters
from observatory.year_drilldown import (
    UNKNOWN,
    clicked_year,
    year_detail,
    year_filters,
    year_records,
)


class _Service:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"status": "ok"}

    def page(self, filters, offset=0, limit=20, sort_by="date", descending=True):
        self.calls.append((filters, limit, sort_by, descending))
        rows = [{"record_id": f"{filters.dataset}-{i}", "title": f"Kite story {i}", "date": "2019-03-0" + str(i + 1),
                 "sponsor": "Tidal Co", "publisher": "Gull Gazette", "account": "tidalco"} for i in range(min(limit, 3))]
        return {"rows": rows, "total": 3 if filters.dataset == "native" else 41}


def test_clicked_year_reads_the_bar_label():
    assert clicked_year({"points": [{"x": "2019", "y": 4}]}) == "2019"
    assert clicked_year({"points": [{"x": UNKNOWN}]}) == UNKNOWN
    assert clicked_year({"points": [{"x": "<script>"}]}) is None
    assert clicked_year(None) is None


def test_year_narrows_but_never_widens_the_selection():
    narrowed = year_filters(Filters(dataset="all", date_from=date(2019, 6, 1)), "2019")
    assert (narrowed.date_from, narrowed.date_to) == (date(2019, 6, 1), date(2019, 12, 31))
    assert narrowed.include_unknown_dates is False
    assert year_filters(Filters(dataset="all", date_to=date(2018, 1, 1)), "2019") is None
    unknown = year_filters(Filters(dataset="native"), UNKNOWN)
    assert unknown.date_presence == "missing" and unknown.date_from is None
    assert year_filters(Filters(dataset="native", include_unknown_dates=False), UNKNOWN) is None


def test_year_records_lists_each_collection_newest_first():
    service = _Service()
    result = year_records(service, Filters(dataset="all", sponsors=["Tidal Co"]), "2019", limit=2)
    assert [(c["dataset"], c["total"], len(c["rows"])) for c in result["collections"]] == [("native", 3, 2), ("social", 41, 2)]
    filters, limit, sort_by, descending = service.calls[0]
    assert filters.sponsors == ["Tidal Co"] and (limit, sort_by, descending) == (2, "date", True)
    text = str(year_detail(result))
    assert "2019: 44 records" in text and "newest 2 shown" in text and "/records/native-0" in text


def test_year_outside_the_filters_reads_nothing():
    service = _Service()
    result = year_records(service, Filters(dataset="native", date_to=date(2010, 1, 1)), "2019")
    assert result["collections"] == [{"dataset": "native", "total": 0, "rows": []}] and not service.calls


@pytest.fixture
def client():
    service = _Service()
    details = SimpleNamespace(get=lambda record_id: None)
    return create_api(service, SimpleNamespace(api_cors_origins=()), record_details=details).test_client(), service


def test_api_timeline_year_endpoint(client):
    api, service = client
    body = api.get("/api/v1/timeline/year?year=2019&dataset=all&limit=5").get_json()
    assert body["year"] == "2019" and body["date_from"] == "2019-01-01"
    assert [c["total"] for c in body["collections"]] == [3, 41]
    assert api.get("/api/v1/timeline/year?year=19").status_code == 400


def test_api_year_parameter_on_records(client):
    api, service = client
    assert api.get("/api/v1/records?dataset=social&year=2021").status_code == 200
    filters = service.calls[-1][0]
    assert (filters.date_from, filters.date_to) == (date(2021, 1, 1), date(2021, 12, 31))
    assert api.get("/api/v1/records?dataset=native&year=unknown").status_code == 200
    assert service.calls[-1][0].date_presence == "missing"
    assert api.get("/api/v1/records?year=2021&date_to=2020-01-01").status_code == 400


@pytest.mark.parametrize("prefix", ["all", "native", "social"])
def test_clicking_a_year_in_each_timeline_lists_records_below(prefix):
    from observatory.app import create_app
    from tests.test_app import FakeService, callback, defaults

    service = FakeService()
    app = create_app(service, SimpleNamespace(show_source_links=True, cookie_secret="test-cookie-secret",
                                              monthly_budget_usd=100))
    client = app.server.test_client()
    year = next(str(row["date"])[:4] for row in service.browse(Filters(dataset="native")) if row.get("date"))
    values = defaults(prefix) | {f"{prefix}-accounts.value": [], f"{prefix}-replies.value": [],
                                 f"{prefix}-timeline-chart.clickData": {"points": [{"x": year}]}}
    shown = callback(app, client, f"{prefix}-year-detail.children", values, f"{prefix}-timeline-chart.clickData")
    assert f"{year}:" in str(shown[f"{prefix}-year-detail"]["children"])
    assert "temporarily unavailable" not in str(shown)
    assert shown[f"{prefix}-year-browse"]["hidden"] is False
