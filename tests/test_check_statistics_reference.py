"""Engineering checker boundaries, with no database or model calls."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location("check_statistics_reference", Path(__file__).parents[1] / "scripts/check_statistics_reference.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_read_only_connection_and_vector_block(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(checker.psycopg, "connect", connect)
    checker.ReadOnlyDatabase("hidden").connect()
    assert connect.call_args.kwargs["options"] == "-c default_transaction_read_only=on"
    connect.return_value.execute.assert_called_once_with("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    connect.reset_mock()
    with pytest.raises(RuntimeError, match="Vector access forbidden"):
        checker.ReadOnlyDatabase("hidden").connect(vector=True)
    connect.assert_not_called()


def test_model_web_interfaces_fail_before_access():
    with pytest.raises(RuntimeError, match="forbidden"):
        checker.ForbiddenModels().answer()


def test_existing_packet_refused_before_settings_or_database(tmp_path, monkeypatch):
    monkeypatch.setattr(checker.Settings, "from_env", MagicMock(side_effect=AssertionError("must not access")))
    with pytest.raises(ValueError, match="overwrite"):
        checker.run(Path("absent"), tmp_path)


def test_corrupt_reference_is_rejected_before_database(tmp_path):
    (tmp_path / "manifest.json").write_text('{"input_sha256":{"source_metadata.json":"wrong"}}')
    (tmp_path / "source_metadata.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        checker.load_reference(tmp_path)


@pytest.mark.parametrize("identity", [{"source_kind": "offline_file"}, {}, None])
def test_unobserved_reference_refused_before_settings_or_database(tmp_path, monkeypatch, identity):
    monkeypatch.setattr(checker, "load_reference", lambda folder: ({"source_identity": identity}, []))
    monkeypatch.setattr(checker.Settings, "from_env", MagicMock(side_effect=AssertionError("must not access")))
    monkeypatch.setattr(checker, "collect_application", MagicMock(side_effect=AssertionError("must not access")))
    with pytest.raises(ValueError, match="Database-observed source identity required"):
        checker.run(tmp_path / "reference", tmp_path / "new-check")
    checker.Settings.from_env.assert_not_called()
    checker.collect_application.assert_not_called()
    assert not (tmp_path / "new-check").exists()


def test_metadata_preserves_duplicate_ids_and_versions():
    value = checker.metadata([{"record_id": "same", "version_id": "v1"}, {"record_id": "same", "version_id": "v2"}])
    assert len(value) == 2
    assert [r["version_id"] for r in value] == ["v1", "v2"]


def test_projection_retains_typed_relationships_and_excludes_annotations():
    value = checker.graph_projection({
        "nodes": [{"id": "a", "type": "Article"}, {"id": "s", "type": "SponsorCandidate"}, {"type": "Annotation"}],
        "edges": [{"predicate": "source_lists_sponsor", "source": "a", "target": "s"},
                  {"predicate": "has_annotation"}],
        "records": [{"record_id": "a", "version_id": "v"}], "coverage": {"shown_records": 1},
    })
    assert len(value["nodes"]) == 2
    assert [e["predicate"] for e in value["edges"]] == ["source_lists_sponsor"]
    assert value["records"][0]["version_id"] == "v"


def comparison_fixture():
    rows = checker.normalize_rows([
        {"record_id": rid, "version_id": "v-" + rid, "dataset": "native", "countable": True,
         "retrievable": True, "sponsor": sponsor, "publisher": outlet, "published_at": when}
        for rid, sponsor, outlet, when in (("a", "A", "X", "2020-01-01"), ("b", "A", "X", "2021-01-01"),
                                           ("c", "B", "Y", None))
    ])
    config = {"dataset": "native", "counting_unit": "source_record_id", "scope_label": "synthetic development",
              "filters": {"include_unknown_dates": True}, "allow_period_overlap": False,
              "periods": [{"id": label, "date_from": str(year) + "-01-01", "date_to": str(year) + "-12-31",
                           "unknown_dates": "unassigned"} for label, year in (("one", 2020), ("two", 2021))]}
    ref = checker.build_reference(rows, config)
    ref["source_identity"] = {"observed_source_version_md5": "source"}
    public = [{**row, "date": row["published_at"]} for row in rows]

    def members(ids):
        return checker.metadata([row for row in public if row["record_id"] in ids])

    def tool(count, unknown=0, **extra):
        return {"status": "ok", "data_version": "data",
                "collections": [{"dataset": "native", "total": count, "unknown_dates": unknown}], **extra}

    graph = {"nodes": [], "edges": [], "summary_edges": [], "records": members(["a", "b", "c"]),
             "coverage": {"shown_records": 3, "total_records": 3, "truncated": False}}
    for r in rows:
        graph["nodes"].append({"id": r["record_id"], "type": "Article",
                              "properties": {"record_id": r["record_id"], "version_id": r["version_id"]}})
    for field, kind, predicate in (("sponsor", "SponsorCandidate", "source_lists_sponsor"),
                                   ("publisher", "Outlet", "published_in")):
        for key in sorted({r[field] for r in rows}):
            graph["nodes"].append({"id": field + key, "type": kind, "properties": {"source_value": key}})
        for r in rows:
            graph["edges"].append({"id": r["record_id"] + field, "source": r["record_id"], "target": field + r[field],
                                   "predicate": predicate, "record_ids": [r["record_id"]],
                                   "provenance": {"version_id": r["version_id"]}})
    for relation in ref["G02_source_relationships"]["relationships"]:
        graph["summary_edges"].append({
            "source": "sponsor" + relation["source"]["key"], "target": "publisher" + relation["target"]["key"],
            "predicate": "derived_source_association", "count": relation["record_count"], "record_ids": relation["record_ids"],
            "witnesses": [{"record_id": rid, "version_id": "v-" + rid, "article_node_id": rid,
                           "source_edge_ids": [rid + "sponsor", rid + "publisher"]} for rid in relation["record_ids"]],
        })
    observed = {"health_before": {"source_data_version": "source", "data_version": "data"},
                "health_after": {"source_data_version": "source", "data_version": "data"},
                "guard_before": {"ledger": "same"}, "guard_after": {"ledger": "same"},
                "statistics": {"total": 3, "unknown_dates": 1}, "records": members(["a", "b", "c"]),
                "matrix": {"sponsors": [{"value": "A"}, {"value": "B"}], "publishers": ["X", "Y"], "matrix": [[2, 0], [0, 1]]},
                "timeline": [{"year": "2020", "count": 1}, {"year": "2021", "count": 1}, {"year": "Unknown", "count": 1}],
                "cells": [{**c, "tool": tool(c["count"]), "members": members(c["record_ids"])}
                          for c in ref["G01_company_outlet"]["cells"]],
                "map": graph, "graph_pages": [{"status": "ok", "data_version": "data", "graph": deepcopy(graph)}], "dates": []}
    scopes = [("all", None, ref["G03_dates"]["overall"])]
    for dimension in ("sponsor", "publisher"):
        scopes.extend((dimension, r["key"], r) for r in ref["G03_dates"]["by_entity"][dimension])
    comparisons = ref["G03_dates"]["period_comparison"]
    for dimension, key, expected in scopes:
        periods = comparisons["periods"] if dimension == "all" else next(
            r["periods"] for r in comparisons["by_entity"][dimension] if r["key"] == key)
        period_outputs = [{"label": p.get("id", p.get("period_id")), **tool(p["count"]),
                           "filters": {"date_from": c["date_from"], "date_to": c["date_to"], "include_unknown_dates": False}}
                          for p, c in zip(periods, config["periods"])]
        base = tool(expected["total"], expected["unknown_date_count"])
        observed["dates"].append({
            "dimension": dimension, "key": key,
            "years": {**base, "groups": [{"name": str(y["year"]), "count": y["count"]} for y in expected["years"]]},
            "highest": {**base, "groups": [{"name": str(y), "count": expected["maximum_known_year_count"]}
                                           for y in expected["all_maximum_years"]]},
            "periods": {**base, "periods": period_outputs},
            "year_members": {str(y["year"]): members(y["record_ids"]) for y in expected["years"]},
            "period_members": {p.get("id", p.get("period_id")): members(p["record_ids"]) for p in periods},
        })
    return ref, rows, observed


def test_complete_comparison_and_bounded_examples_are_not_full_members():
    ref, rows, observed = comparison_fixture()
    for cell in observed["cells"]:
        cell["tool"]["records"] = []
    result = checker.compare_application(ref, rows, observed)
    assert result["status"] == "passed_read_only_engineering"
    assert result["M01_result"] is None and result["M02_result"] is None


@pytest.mark.parametrize("mutation", ["wrong_member", "missing_tie", "wrong_version", "missing_path",
                                     "missing_period", "ledger_changed", "source_changed", "truncated_graph", "missing_cell"])
def test_real_comparison_failures_are_detected(mutation):
    ref, rows, observed = comparison_fixture()
    if mutation == "wrong_member":
        cell = next(c for c in observed["cells"] if c["count"] == 2)
        cell["members"][1]["record_id"] = "c"
    elif mutation == "missing_tie":
        observed["dates"][0]["highest"]["groups"].pop()
    elif mutation == "wrong_version":
        observed["map"]["summary_edges"][0]["witnesses"][0]["version_id"] = "other"
    elif mutation == "missing_path":
        observed["graph_pages"][0]["graph"]["edges"].pop()
    elif mutation == "missing_period":
        observed["dates"][0]["periods"]["periods"].pop()
    elif mutation == "ledger_changed":
        observed["guard_after"]["ledger"] = "changed"
    elif mutation == "source_changed":
        observed["health_after"]["source_data_version"] = "changed"
    elif mutation == "truncated_graph":
        observed["graph_pages"][0]["graph"]["records"].pop()
    elif mutation == "missing_cell":
        observed["cells"].pop()
    result = checker.compare_application(ref, rows, observed)
    assert result["status"] == "failed_read_only_engineering"
    assert any(not check["passed"] for check in result["checks"])
    checker.encoded(result)  # Failure receipts must remain serializable.
