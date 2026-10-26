from types import SimpleNamespace

import pytest

from observatory.api import create_api
from observatory.models import Answer


class _Details:
    def get(self, record_id):
        return {"record_id": record_id, "title": "Quiet kites"} if record_id == "rec-1" else None

    def attachment(self, record_id, asset_id):
        return None


class _Service:
    def __init__(self):
        self.calls = []
        self.answer_status = "answered"

    def health(self):
        return {"status": "ok", "record_counts": {"native": 2}, "secret_path": "hidden"}

    def facets(self, dataset):
        self.calls.append(("facets", dataset))
        return {"sponsors": ["Tidal Co"]}

    def dashboard(self, filters, offset, limit, sort_by, descending):
        self.calls.append(("dashboard", filters, offset, limit, sort_by, descending))
        return {"collections": [], "page": {"rows": [], "total": 0}}

    def page(self, filters, offset, limit, sort_by, descending):
        self.calls.append(("page", filters, offset, limit))
        return {"rows": [{"record_id": "rec-1", "title": "Quiet kites"}], "total": 1}

    def answer(self, question, filters, visitor):
        self.calls.append(("answer", question, filters.dataset, visitor))
        return Answer(status=self.answer_status, answer="Two Tidal Co ads mention kites.")


@pytest.fixture
def client_and_service():
    service = _Service()
    settings = SimpleNamespace(api_cors_origins=("http://localhost:5173",), show_source_links=True)
    api = create_api(service, settings, record_details=_Details())
    return api.test_client(), service


def test_health_returns_only_public_fields(client_and_service):
    client, _ = client_and_service
    body = client.get("/api/v1/health").get_json()
    assert body == {"status": "ok", "record_counts": {"native": 2}}


def test_dashboard_parses_repeated_and_comma_separated_filters(client_and_service):
    client, service = client_and_service
    response = client.get("/api/v1/dashboard?dataset=native&sponsors=Tidal Co,Fenwick Gas&sponsors=Marlow Oil"
                          "&date_from=2020-01-01&include_unknown_dates=false&limit=5&sort_by=title&descending=false")
    assert response.status_code == 200
    _, filters, offset, limit, sort_by, descending = service.calls[-1]
    assert filters.dataset == "native"
    assert filters.sponsors == ["Tidal Co", "Fenwick Gas", "Marlow Oil"]
    assert str(filters.date_from) == "2020-01-01" and filters.include_unknown_dates is False
    assert (offset, limit, sort_by, descending) == (0, 5, "title", False)


@pytest.mark.parametrize("query", ["dataset=ads", "limit=0", "limit=101", "offset=-1", "sort_by=secret",
                                   "include_unknown_dates=maybe", "date_from=yesterday"])
def test_bad_parameters_are_400_before_any_read(client_and_service, query):
    client, service = client_and_service
    response = client.get(f"/api/v1/records?{query}")
    assert response.status_code == 400
    assert "error" in response.get_json()
    assert not service.calls


def test_record_detail_and_missing_record(client_and_service):
    client, _ = client_and_service
    assert client.get("/api/v1/records/rec-1").get_json()["title"] == "Quiet kites"
    assert client.get("/api/v1/records/rec-404").status_code == 404


def test_ask_validates_body_and_uses_a_visitor_id(client_and_service):
    client, service = client_and_service
    assert client.post("/api/v1/ask", json={"question": ""}).status_code == 400
    assert client.post("/api/v1/ask", data="not json").status_code == 400
    response = client.post("/api/v1/ask", json={"question": "Which ads mention kites?"},
                           headers={"X-Visitor-Id": "frontend-dev"})
    assert response.status_code == 200
    assert response.get_json()["answer"] == "Two Tidal Co ads mention kites."
    assert service.calls[-1] == ("answer", "Which ads mention kites?", "all", "api:frontend-dev")


def test_a_rate_limited_question_is_429(client_and_service):
    client, service = client_and_service
    service.answer_status = "limited"
    assert client.post("/api/v1/ask", json={"question": "Which ads mention kites?"}).status_code == 429


def test_cors_allows_only_configured_origins(client_and_service):
    client, _ = client_and_service
    allowed = client.get("/api/v1/facets", headers={"Origin": "http://localhost:5173"})
    other = client.get("/api/v1/facets", headers={"Origin": "http://example.invalid"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in other.headers
    assert client.options("/api/v1/ask", headers={"Origin": "http://localhost:5173"}).status_code == 204


def test_unknown_routes_and_methods_keep_their_status(client_and_service):
    client, _ = client_and_service
    assert client.get("/api/v1/nothing").status_code == 404
    assert client.get("/api/v1/ask").status_code == 405


def test_compact_answer_keeps_only_cited_passages_and_drops_the_trace():
    from observatory.api import compact_answer

    body = {"answer": "Two ads.", "research_trace": {"steps": ["internal"]},
            "citations": [{"evidence_id": "ev-1"}], "cited_claims": [{"citations": [{"evidence_id": "ev-2"}]}],
            "evidence": [{"evidence_id": "ev-1"}, {"evidence_id": "ev-2"}, {"evidence_id": "ev-unused"}]}
    compact = compact_answer(body)
    assert "research_trace" not in compact
    assert [e["evidence_id"] for e in compact["evidence"]] == ["ev-1", "ev-2"]
    assert len(body["evidence"]) == 3


def test_public_nativeads_env_names_map_to_settings_and_win_over_old_names():
    from observatory.config import apply_public_env_names

    environ = {"NATIVEADS_API_PORT": "19000", "OBS_API_PORT": "18060", "OBS_HOST": "127.0.0.1"}
    apply_public_env_names(environ)
    assert environ["OBS_API_PORT"] == "19000"
    assert environ["OBS_HOST"] == "127.0.0.1"


def test_knowledge_maps_endpoint_serves_the_latest_file_and_one_view(client_and_service, tmp_path, monkeypatch):
    client, _ = client_and_service
    monkeypatch.setenv("OBS_KNOWLEDGE_MAPS_DIR", str(tmp_path))
    assert client.get("/api/v1/knowledge-maps").status_code == 404
    folder = tmp_path / "build1"
    folder.mkdir()
    (folder / "knowledge_maps.json").write_text(
        '{"schema_version": 1, "views": {"hashtags": {"nodes": [1]}, "companies": {"nodes": [2]}}}', encoding="utf-8")
    assert set(client.get("/api/v1/knowledge-maps").get_json()["views"]) == {"hashtags", "companies"}
    one = client.get("/api/v1/knowledge-maps?view=companies").get_json()
    assert one["views"] == {"companies": {"nodes": [2]}} and one["schema_version"] == 1
    assert client.get("/api/v1/knowledge-maps?view=secret").status_code == 400
