"""A comparison read inside an all-collections selection keeps its targets' collection.

The "Compare emissions claims" example asks about native ads while the page
selects both collections: each target is read as native, the shared top-level
filters keep "all", and the read was rejected as out of scope.
"""
from test_research_tools import make_catalog, source

from observatory.models import Filters
from observatory.research_agent import _result_dataset


def test_a_comparison_read_reports_the_collection_its_targets_share():
    catalog, db = make_catalog(Filters(dataset="all"))
    db.rows.append(source("gale", "Harbor Daily", "gale union"))
    result = catalog.call("search_records", {"query": "emissions", "comparison_scopes": [
        {"query": "Tidal Co emissions", "filters": {"dataset": "native", "sponsors": ["exxonmobil"]}},
        {"query": "Gale Union emissions", "filters": {"dataset": "native", "sponsors": ["gale union"]}},
    ]})
    assert result["status"] == "ok"
    assert result["filters"]["dataset"] == "all"  # the active selection is unchanged
    assert {group["filters"]["dataset"] for group in result["retrieval_groups"]} == {"native"}
    assert _result_dataset(result) == "native"


def test_mixed_comparison_collections_fall_back_to_the_shared_filters():
    result = {"filters": {"dataset": "all"}, "retrieval_groups": [
        {"filters": {"dataset": "native"}}, {"filters": {"dataset": "social"}}]}
    assert _result_dataset(result) == "all"
    assert _result_dataset({"filters": {"dataset": "social"}}) == "social"
