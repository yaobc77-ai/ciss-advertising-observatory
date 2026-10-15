"""Reply-status filter over the source post.is_reply mark, social collection only."""

import pytest
from pydantic import ValidationError

from observatory.app import FILTER_NAMES, REPLY_OPTIONS, _filters, _public_rows
from observatory.db import Database
from observatory.models import Filters


def _values(**selected):
    values = [selected.get(name, []) for name in FILTER_NAMES]
    return [*values, None, None, ["include"]]


def test_reply_filter_requires_social_collection():
    assert Filters(dataset="social", replies=["reply"]).replies == ["reply"]
    for dataset in ("native", "all"):
        with pytest.raises(ValidationError):
            Filters(dataset=dataset, replies=["reply"])
    with pytest.raises(ValidationError):
        Filters(dataset="social", replies=["original"])


def test_where_uses_source_mark_only_when_it_restricts():
    marked, _ = Database.where(Filters(dataset="social", replies=["reply"]))
    assert "post,is_reply" in marked and "NOT (" not in marked
    unmarked, _ = Database.where(Filters(dataset="social", replies=["not_marked"]))
    assert "NOT (COALESCE(v.payload#>>'{raw,source_row,post,is_reply}','')='true')" in unmarked
    both, _ = Database.where(Filters(dataset="social", replies=["reply", "not_marked"]))
    assert "is_reply" not in both
    none, _ = Database.where(Filters(dataset="social"))
    assert "is_reply" not in none


def test_where_rejects_bypassed_validation():
    filters = Filters(dataset="native").model_copy(update={"replies": ["reply"]})
    with pytest.raises(ValueError, match="social collection"):
        Database.where(filters)


def test_dash_filters_carry_reply_selection_for_social_only():
    assert _filters("social", *_values(replies=["reply"])).replies == ["reply"]
    assert _filters("social", *_values()).replies == []
    with pytest.raises(ValueError, match="specific collection"):
        _filters("all", *_values(replies=["reply"]))
    assert {option["value"] for option in REPLY_OPTIONS} == {"reply", "not_marked"}


def test_public_rows_expose_reply_status_without_raw_payload():
    rows = _public_rows([
        {"record_id": "s1", "version_id": "v1", "dataset": "social", "reply_status": "reply",
         "title": "t", "url": "https://example.test/1", "raw": {"source_row": {"post": {"is_reply": "true"}}}},
        {"record_id": "s2", "version_id": "v2", "dataset": "social", "title": "t", "url": "https://example.test/2"},
        {"record_id": "n1", "version_id": "v3", "dataset": "native", "title": "t", "url": "https://example.test/3"},
    ], True)
    assert [row.get("reply_status") for row in rows] == ["reply", "not_marked", None]
    assert all("raw" not in row for row in rows)
