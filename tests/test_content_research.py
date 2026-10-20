"""Shared content reads keep reviewed coverage separate from model prose."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from observatory.config import Settings
from observatory.content_assessment import QUESTION_IDS, QUESTION_TEXTS
from observatory.db import Database
from observatory.models import Filters
from observatory.research_tools import ToolCatalog
from observatory.service import Service
from tests.test_content_publication import (
    APPROVAL,
    current_rows,
    encoded,
    mark,
    source_for,
)
from tests.test_research_agent import FakeCatalog, harness, response
from tests.test_research_tools import SourceDB


def public_result():
    return {"status": "ok", "available": True, "publication_version": "a" * 64,
            "review_version": "b" * 64, "question": {"question_id": "Q03", "question_exact": QUESTION_TEXTS[2]},
            "totals": {"scope_records": 4, "relevant": 1, "not_relevant": 1, "unknown": 2},
            "coverage": {"classification_complete": False, "reviewed_records": 3},
            "records": [], "offset": 0, "limit": 5, "page_complete": True,
            "next_offset": None, "source_refs": [{"record_id": "r1", "version_id": "version-r1",
                                                   "question_id": "Q03", "body_hash": "c" * 64}]}


def configured_service(monkeypatch):
    from observatory import content_publication

    calls = []
    monkeypatch.setattr(content_publication, "load_publication", lambda *args: calls.append(args) or {})
    monkeypatch.setattr(content_publication, "read_match_page", lambda pub, rows, qid, **kwargs:
                        calls.append((deepcopy(rows), qid, kwargs)) or public_result())
    db = SourceDB()
    db.content_match_sources = db.select
    service = Service(Settings(content_publication_path="/private/content.json",
                               content_publication_sha256="a" * 64, content_review_sha256="b" * 64),
                      db=db, rag=object())
    return service, db, calls


def test_unconfigured_publication_does_not_read_database_or_assert_zero():
    result = Service(Settings(), db=object(), rag=object()).content_matches(Filters(), question_id="Q03")
    assert result["status"] == "unavailable" and not result["available"]
    assert result["totals"] is None and not result["coverage"]["classification_complete"]
    assert "not negative" in result["message"]


@pytest.mark.parametrize("args", [{"question_id": "Q25"}, {"question_id": "q03"},
                                  {"question_id": "Q03", "offset": True},
                                  {"question_id": "Q03", "limit": 21},
                                  {"question_id": "Q03", "offset": -1}])
def test_service_invalid_input_rejected_without_source_read(args):
    with pytest.raises(ValueError):
        Service(Settings(), db=object(), rag=object()).content_matches(Filters(), **args)


def test_shared_tool_preserves_every_filter_and_reads_nonsearchable_denominator(monkeypatch):
    service, db, calls = configured_service(monkeypatch)
    selected = Filters(publishers=["The Washington Post"], sponsors=["bp"],
                       date_presence="missing", include_unknown_dates=True, include_inferred_dates=False,
                       record_ids=["r2"])
    result = ToolCatalog(service, selected).call("get_content_matches", {"question_id": "Q03"})
    assert result["status"] == "ok"
    assert db.reads[-1] == selected
    assert len(calls[-1][0]) == 1 and calls[-1][0][0]["record_id"] == "r2"
    assert not calls[-1][0][0]["retrievable"]
    assert result["filters"] == selected.model_dump(mode="json")
    assert result["model_calls"] == 0 and len(result["source_scope_sha256"]) == 64
    assert "/private/" not in json.dumps(result)


@pytest.mark.parametrize("args", [{"question_id": "Q00"}, {"question_id": "Q03", "path": "x"},
                                  {"question_id": "Q03", "reviewer": "actor"},
                                  {"question_id": "Q03", "publish": True},
                                  {"question_id": "Q03", "limit": True},
                                  {"question_id": "Q03", "offset": 10001}])
def test_tool_rejects_file_authority_and_invalid_pages_before_database_read(args):
    db = SourceDB()
    result = ToolCatalog(Service(Settings(), db=db, rag=object()), Filters()).call("get_content_matches", args)
    assert result["status"] == "invalid_request" and not db.reads


def test_tool_disjoint_entity_scope_rejected_before_source_read():
    db = SourceDB()
    result = ToolCatalog(Service(Settings(), db=db, rag=object()), Filters(record_ids=["r1"])).call(
        "get_content_matches", {"question_id": "Q03", "filters": {"record_ids": ["r3"]}})
    assert result["status"] == "clarify" and not db.reads


@pytest.mark.parametrize("dataset", ["social", "all"])
def test_native_content_questions_do_not_silently_switch_collection(dataset):
    result = Service(Settings(), db=object(), rag=object()).content_matches(Filters(dataset=dataset), question_id="Q03")
    assert result["status"] == "clarify"


def test_model_receives_all_exact_questions_and_keeps_publication_trace():
    result = public_result()
    agent, _, _, calls = harness([response("get_content_matches", {"question_id": "Q03"})],
                                  catalog=FakeCatalog({"get_content_matches": result}))
    run = agent.run("Which ads mention tidal kites?", Filters(), "synthetic-visitor")
    assert run.route == "content_matches" and run.result == result
    payload = json.loads(calls[0]["input"][1]["content"])
    assert payload["client_content_questions"] == [
        {"question_id": qid, "question_exact": text} for qid, text in zip(QUESTION_IDS, QUESTION_TEXTS, strict=True)]
    assert run.tool_trace[0]["publication_version"] == result["publication_version"]
    assert run.tool_trace[0]["review_version"] == result["review_version"]
    assert run.tool_trace[0]["data_refs"] == result["source_refs"]
    assert len(calls) == 1  # Injected provider response, no live API or prose generation.


def test_pending_route_is_preserved_and_cannot_trigger_external_complete_list():
    pending = {"status": "unavailable", "available": False, "message": "Reviewed results pending."}
    agent, _, _, _ = harness([response("get_content_matches", {"question_id": "Q03"})],
                              catalog=FakeCatalog({"get_content_matches": pending}))
    run = agent.run("Which ads mention tidal kites?", Filters(), "synthetic-visitor")
    assert run.route == "content_matches" and run.result == pending
    answer = Service._tool_content_answer(run.result)
    assert answer.failure_reason == "content_publication_unavailable"
    service = Service(Settings(), db=object(), rag=object())
    service._search_external = lambda *args, **kwargs: pytest.fail("Publication pending is not a database evidence miss")
    assert service._ensure_answer("Which ads mention tidal kites?", Filters(), "v", answer) is answer


def test_partial_membership_answer_keeps_unknown_and_page_coverage():
    result = public_result()
    result.update(page_complete=False)
    answer = Service._tool_content_answer(result)
    assert answer.status == "answered" and answer.structured_result["kind"] == "content_matches"
    assert "2 unknown" in answer.answer and "partial reviewed list" in answer.answer
    assert "part of the matching list" in answer.answer


def test_database_content_source_query_uses_full_filtered_current_snapshot():
    statements = []
    rows = [{"record_id": "unsearchable", "body": "", "body_hash": hashlib.sha256(b"").hexdigest()}]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, args=None):
            statements.append((sql, args))
            return SimpleNamespace(fetchall=lambda: rows)

    db = Database("")
    db.connect = lambda: Conn()
    selection = Filters(publishers=["Outlet"], record_ids=["r1"], include_inferred_dates=False)
    assert db.content_match_sources(selection) == rows
    assert statements[0][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    sql, args = statements[1]
    assert "v.record_id=selected.record_id" in sql and "v.body_hash" in sql and "retrieval_ranges" in sql
    assert "r.current_version" in sql and "LIMIT 10001" in sql
    assert "raw" not in sql and "retrievable')::boolean=true" not in sql
    assert "Outlet" not in sql and ["Outlet"] in args and ["r1"] in args


@pytest.mark.parametrize("dataset", ["social", "all"])
def test_source_projection_rejects_unsupported_dataset_without_connection(dataset):
    db = Database("")
    db.connect = lambda: pytest.fail("Unsupported source scope must fail before connection")
    with pytest.raises(ValueError):
        db.content_match_sources(Filters(dataset=dataset))


def reviewed_service(tmp_path):
    """Actual strict private publication -> flat SQL projection -> shared tool."""
    from observatory.content_publication import build_publication, make_review_template

    frozen = source_for(("one", "two", "unknown"))
    review = make_review_template(frozen)
    review["definition_review"] = deepcopy(APPROVAL)
    review["publication_review"] = deepcopy(APPROVAL)
    mark(review, "one")
    mark(review, "two", membership="not_relevant")
    mark(review, "unknown", membership="unknown")
    review_bytes = json.dumps(review, ensure_ascii=False, indent=2).encode("utf-8")
    review_sha = hashlib.sha256(review_bytes).hexdigest()
    publication = build_publication(frozen, review, review_sha256=review_sha, review_bytes=review_bytes)
    data = encoded(publication)
    path = tmp_path / "private-published.json"
    path.write_bytes(data)
    db = SourceDB()
    db.rows = []
    for row in current_rows(frozen):
        metadata = row.pop("publicmetadata")
        db.rows.append({**row, **metadata, "date": "2026-01-02", "inferred_tier": "synthetic-tier"})
    db.content_match_sources = db.select
    settings = Settings(content_publication_path=str(path),
                        content_publication_sha256=hashlib.sha256(data).hexdigest(),
                        content_review_sha256=review_sha)
    return Service(settings, db=db, rag=object()), db, path


def test_actual_publication_to_shared_tool_keeps_denominator_and_exact_source(tmp_path):
    service, db, path = reviewed_service(tmp_path)
    selection = Filters(publishers=["Current publisher"], sponsors=["Current sponsor"],
                        date_from="2026-01-01", date_to="2026-12-31", include_unknown_dates=False)
    result = ToolCatalog(service, selection).call("get_content_matches", {"question_id": "Q06"})
    assert result["status"] == "ok" and result["available"]
    assert result["totals"] == {"scope_records": 3, "relevant": 1, "not_relevant": 1, "unknown": 1}
    assert result["coverage"]["unknown_reasons"]["insufficient"] == 1
    assert result["records"][0]["title"] == "Current synthetic title"
    assert result["records"][0]["inferred_tier"] == "synthetic-tier"
    evidence = result["records"][0]["support_evidence"][0]
    assert evidence["quote"] == "CCS"
    assert db.rows[0]["body"][evidence["start"]:evidence["end"]] == evidence["quote"]
    assert evidence["review_version"] == service.settings.content_review_sha256
    assert result["page_complete"] and not result["coverage"]["classification_complete"]
    serialized = json.dumps(result)
    for private in (str(path), "C:/private", "Synthetic named reviewer", "review_json_utf8"):
        assert private not in serialized
    assert db.reads[-1] == selection


def test_real_reader_detects_corrupt_unchanged_body_and_closes_source_links(tmp_path):
    service, db, _ = reviewed_service(tmp_path)
    before = service.content_matches(Filters(), question_id="Q06")
    db.rows[0]["body"] += " changed without a declared new hash or version"
    after = service.content_matches(Filters(), question_id="Q06")
    assert after["totals"] == {"scope_records": 3, "relevant": 0, "not_relevant": 1, "unknown": 2}
    assert after["coverage"]["unknown_reasons"]["stale"] == 1
    assert before["source_scope_sha256"] != after["source_scope_sha256"]
    db.rows[0]["body"] = db.rows[0]["body"].split(" changed without")[0]
    service.settings.show_source_links = False
    closed = service.content_matches(Filters(), question_id="Q06")
    assert closed["totals"] == before["totals"]
    assert "url" not in closed["records"][0] and "archive_url" not in closed["records"][0]


def test_actual_pin_failure_is_unavailable_not_zero_or_private_error(tmp_path):
    service, db, path = reviewed_service(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    result = service.content_matches(Filters(), question_id="Q06")
    assert result["status"] == "unavailable" and result["totals"] is None
    assert not db.reads and str(path) not in json.dumps(result)
