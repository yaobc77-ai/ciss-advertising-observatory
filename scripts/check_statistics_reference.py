"""Read-only application reconciliation against a frozen development reference.

This checks explicitly selected metadata operations, not natural-language/model
interpretation, semantic gold, unseen performance or customer acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from prepare_statistics_reference import (
    build_reference,
    encoded,
    normalize_rows,
    strict_json,
)
from psycopg import sql
from psycopg.rows import dict_row

from observatory.config import Settings
from observatory.db import Database
from observatory.models import Filters
from observatory.research_tools import ToolCatalog
from observatory.service import Service


class ForbiddenModels:
    def __getattr__(self, name):
        raise RuntimeError("Model, embedding and web access forbidden in this check")


class ReadOnlyDatabase(Database):
    def connect(self, vector=False):
        if vector:
            raise RuntimeError("Vector access forbidden in this check")
        conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10,
                              options="-c default_transaction_read_only=on")
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return conn


def load_reference(folder):
    manifest = strict_json((folder / "manifest.json").read_text(encoding="utf-8"))
    for name in ("source_metadata.json", "reference.json", "config.json"):
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if actual != manifest["input_sha256"].get(name):
            raise ValueError("Frozen reference hash mismatch")
    reference = strict_json((folder / "reference.json").read_text(encoding="utf-8"))
    rows = normalize_rows(strict_json((folder / "source_metadata.json").read_text(encoding="utf-8"))["records"])
    if (reference["status"] != "observed_development_reference"
            or any(reference[key] is not False for key in ("customer_approved", "semantic_gold", "unseen_evaluation"))):
        raise ValueError("Development-reference boundary missing")
    if not all(row["version_id"] for row in rows):
        raise ValueError("Exact source versions required")
    independent = build_reference(rows, reference["scope"])
    for key in ("selected_count", "selected_record_ids", "G01_company_outlet", "G02_source_relationships", "G03_dates"):
        if independent[key] != reference[key]:
            raise ValueError("Frozen reference does not reproduce")
    return reference, rows


def state_guard(db):
    result = {}
    with db.connect() as conn:
        for name in ("usage_ledger", "answer_runs", "generation_outputs", "embeddings"):
            result[name] = conn.execute(sql.SQL(
                "SELECT count(*) AS count, md5(COALESCE(string_agg(h,',' ORDER BY h),'')) AS digest "
                "FROM (SELECT md5(to_jsonb(t)::text) AS h FROM {} t) rows"
            ).format(sql.Identifier(name))).fetchone()
    return result


def scoped(reference, **updates):
    return Filters(dataset=reference["scope"]["dataset"], **{
        **reference["scope"]["filters"], **updates,
    })


def metadata(rows):
    return sorted([{key: row.get(key) for key in ("record_id", "version_id", "dataset", "sponsor", "publisher", "date")}
                   for row in rows], key=lambda row: row["record_id"])


def graph_projection(graph):
    return {
        "nodes": [node for node in graph["nodes"] if node["type"] in ("Article", "SponsorCandidate", "Outlet")],
        "edges": [edge for edge in graph.get("edges", graph.get("article_edges", []))
                  if edge["predicate"] in ("source_lists_sponsor", "published_in")],
        "summary_edges": graph.get("summary_edges", []),
        "records": metadata(graph["records"]), "coverage": graph["coverage"],
    }


def collect_application(service, reference):
    base = scoped(reference)
    observed = {"health_before": service.health(), "guard_before": state_guard(service.db)}
    observed["statistics"] = service.statistics(base)
    dashboard = service.dashboard(base)
    observed["matrix"], observed["timeline"] = dashboard["matrix"], dashboard["timeline"]
    observed["records"] = metadata(service.browse(base))
    observed["cells"] = []
    for cell in reference["G01_company_outlet"]["cells"]:
        selected = scoped(reference, sponsors=[cell["source_sponsor"] or "(Unknown)"],
                          publishers=[cell["outlet"] or "(Unknown)"])
        observed["cells"].append({
            "source_sponsor": cell["source_sponsor"], "outlet": cell["outlet"],
            "tool": ToolCatalog(service, selected).call("record_statistics", {"group_by": "none"}),
            "members": metadata(service.browse(selected)),
        })
    observed["map"] = graph_projection(service.knowledge_map(base))
    catalog, pages, offset = ToolCatalog(service, base), [], 0
    while offset < reference["selected_count"] and len(pages) < 2000:
        page = catalog.call("get_graph_neighborhood", {"offset": offset, "limit": 5})
        if page.get("status") != "ok":
            pages.append(page)
            break
        pages.append({"status": page["status"], "data_version": page.get("data_version"),
                      "graph": graph_projection(page["graph"])})
        shown = page["graph"]["coverage"]["shown_records"]
        if not shown:
            break
        offset += shown
    observed["graph_pages"] = pages
    periods = [{"label": item["id"], "date_from": item["date_from"], "date_to": item["date_to"]}
               for item in reference["scope"]["periods"]]
    scopes = [("all", None, reference["G03_dates"]["overall"])]
    for dimension in ("sponsor", "publisher"):
        scopes.extend((dimension, item["key"], item) for item in reference["G03_dates"]["by_entity"][dimension])
    observed["dates"] = []
    for dimension, key, expected in scopes:
        selected = scoped(reference) if dimension == "all" else scoped(reference, **{dimension + "s": [key or "(Unknown)"]})
        catalog = ToolCatalog(service, selected)
        item = {
            "dimension": dimension, "key": key,
            "years": catalog.call("record_statistics", {"group_by": "years", "ranking": "all"}),
            "highest": catalog.call("record_statistics", {"group_by": "years", "ranking": "highest"}),
            "periods": catalog.call("record_statistics", {"periods": periods}),
            "year_members": {}, "period_members": {},
        }
        for year in expected["years"]:
            bounds = selected.model_copy(update={"date_from": date(year["year"], 1, 1),
                                                 "date_to": date(year["year"], 12, 31),
                                                 "include_unknown_dates": False})
            item["year_members"][str(year["year"])] = metadata(service.browse(bounds))
        for period in reference["scope"]["periods"]:
            start, end = date.fromisoformat(period["date_from"]), date.fromisoformat(period["date_to"])
            bounds = selected.model_copy(update={"date_from": max(start, selected.date_from or start),
                                                 "date_to": min(end, selected.date_to or end),
                                                 "include_unknown_dates": False})
            item["period_members"][period["id"]] = metadata(service.browse(bounds))
        observed["dates"].append(item)
    observed["health_after"], observed["guard_after"] = service.health(), state_guard(service.db)
    return observed


def compare_application(reference, source_rows, observed):
    checks = []
    versions = {row["record_id"]: row["version_id"] for row in source_rows}

    def check(name, expected, actual):
        def display(value):
            if isinstance(value, dict):
                return {str(k): display(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [display(v) for v in value]
            return value

        checks.append({"check": name, "passed": expected == actual,
                       **({} if expected == actual else {"expected": display(expected), "actual": display(actual)})})

    def members(name, expected, rows):
        check(name + ":record_ids", sorted(expected), sorted(row["record_id"] for row in rows))
        check(name + ":versions", True, all(row["version_id"] == versions.get(row["record_id"]) for row in rows))

    def tool(name, value):
        check(name + ":status", "ok", value.get("status"))
        check(name + ":identity", observed["health_before"].get("data_version"), value.get("data_version"))

    def total(value):
        return next((item["total"] for item in value.get("collections", []) if item["dataset"] == "native"), None)

    check("state:source_bound", reference["source_identity"]["observed_source_version_md5"],
          observed["health_before"].get("source_data_version"))
    check("state:health_unchanged", observed["health_before"], observed["health_after"])
    check("state:no_ledger_answer_generation_embedding_change", observed["guard_before"], observed["guard_after"])
    members("selection", reference["selected_record_ids"], observed["records"])
    check("statistics:total", reference["selected_count"], observed["statistics"]["total"])
    check("statistics:unknown_dates", reference["G03_dates"]["overall"]["unknown_date_count"],
          observed["statistics"]["unknown_dates"])
    matrix = observed["matrix"]
    actual = {(None if sponsor["value"] == "(Unknown)" else sponsor["value"],
               None if outlet == "(Unknown)" else outlet): matrix["matrix"][i][j]
              for i, sponsor in enumerate(matrix["sponsors"]) for j, outlet in enumerate(matrix["publishers"])}
    cells = reference["G01_company_outlet"]["cells"]
    check("matrix:all_cells", {(c["source_sponsor"], c["outlet"]): c["count"] for c in cells}, actual)
    check("matrix:selection_cell_keys", [(c["source_sponsor"], c["outlet"]) for c in cells],
          [(c["source_sponsor"], c["outlet"]) for c in observed["cells"]])
    for i, (expected, cell) in enumerate(zip(cells, observed["cells"])):
        name = "cell:" + str(i)
        members(name, expected["record_ids"], cell["members"])
        tool(name, cell["tool"])
        check(name + ":tool_count", expected["count"], total(cell["tool"]))
    expected_years = {str(item["year"]): item["count"] for item in reference["G03_dates"]["overall"]["years"]}
    expected_years["Unknown"] = reference["G03_dates"]["overall"]["unknown_date_count"]
    check("dashboard:year_timeline", expected_years, {str(item["year"]): item["count"] for item in observed["timeline"]})

    def graph_paths(name, graph):
        nodes, edges = {n["id"]: n for n in graph["nodes"]}, {e["id"]: e for e in graph["edges"]}
        valid = len(nodes) == len(graph["nodes"]) and len(edges) == len(graph["edges"])
        actual_paths = []
        for edge in edges.values():
            source, target = nodes.get(edge["source"], {}), nodes.get(edge["target"], {})
            expected_type = "SponsorCandidate" if edge["predicate"] == "source_lists_sponsor" else "Outlet"
            rid = source.get("properties", {}).get("record_id")
            field = "sponsor" if expected_type == "SponsorCandidate" else "publisher"
            original = next((r for r in source_rows if r["record_id"] == rid), {})
            actual_paths.append((rid, edge["predicate"], target.get("properties", {}).get("source_value")))
            valid &= (source.get("type") == "Article" and target.get("type") == expected_type
                      and target.get("properties", {}).get("source_value") == original.get(field)
                      and edge.get("record_ids") == [rid]
                      and edge.get("provenance", {}).get("version_id") == versions.get(rid))
        check(name + ":typed_versioned_paths", True, bool(valid))
        expected_paths = []
        for row in source_rows:
            if row["record_id"] not in {r["record_id"] for r in graph["records"]}:
                continue
            for field, predicate in (("sponsor", "source_lists_sponsor"), ("publisher", "published_in")):
                if row[field]:
                    expected_paths.append((row["record_id"], predicate, row[field]))
        check(name + ":all_source_paths", sorted(expected_paths), sorted(actual_paths))
        return nodes, edges

    full = observed["map"]
    members("map", reference["selected_record_ids"], full["records"])
    check("map:not_truncated", False, full["coverage"].get("truncated"))
    nodes, edges = graph_paths("map", full)
    relationships, witness_ok = {}, True
    for edge in full["summary_edges"]:
        source, target = nodes[edge["source"]], nodes[edge["target"]]
        key = (source["properties"]["source_value"], target["properties"]["source_value"])
        relationships[key] = {"count": edge["count"], "record_ids": sorted(edge["record_ids"])}
        witness_ok &= (edge["predicate"] == "derived_source_association" and source["type"] == "SponsorCandidate"
                       and target["type"] == "Outlet")
        witness_ok &= sorted(w["record_id"] for w in edge["witnesses"]) == sorted(edge["record_ids"])
        for witness in edge["witnesses"]:
            paths = [edges.get(eid, {}) for eid in witness["source_edge_ids"]]
            witness_ok &= (witness["version_id"] == versions.get(witness["record_id"])
                           and len(paths) == 2 and {p.get("predicate") for p in paths} == {"source_lists_sponsor", "published_in"}
                           and {p.get("target") for p in paths} == {edge["source"], edge["target"]}
                           and all(p.get("source") == witness["article_node_id"] for p in paths))
    expected_relations = {(r["source"]["key"], r["target"]["key"]): {"count": r["record_count"], "record_ids": r["record_ids"]}
                          for r in reference["G02_source_relationships"]["relationships"]}
    check("map:all_relationships_and_members", expected_relations, relationships)
    check("map:summary_witnesses", True, bool(witness_ok))
    paged_records = []
    for i, page in enumerate(observed["graph_pages"]):
        tool("mcp_graph:" + str(i), page)
        if page.get("graph"):
            graph_paths("mcp_graph:" + str(i), page["graph"])
            paged_records.extend(page["graph"]["records"])
    members("mcp_graph:complete_pages", reference["selected_record_ids"], paged_records)

    expected_scopes = [("all", None, reference["G03_dates"]["overall"])]
    for dimension in ("sponsor", "publisher"):
        expected_scopes.extend((dimension, r["key"], r) for r in reference["G03_dates"]["by_entity"][dimension])
    check("dates:all_scope_keys", [(d, k) for d, k, _ in expected_scopes],
          [(item["dimension"], item["key"]) for item in observed["dates"]])
    comparison = reference["G03_dates"]["period_comparison"]
    for (dimension, key, expected), actual_scope in zip(expected_scopes, observed["dates"]):
        name = "dates:" + dimension + ":" + str(key)
        for operation in ("years", "highest", "periods"):
            value = actual_scope[operation]
            tool(name + ":" + operation, value)
            check(name + ":" + operation + ":total", expected["total"], total(value))
            unknown = next((r["unknown_dates"] for r in value.get("collections", []) if r["dataset"] == "native"), None)
            check(name + ":" + operation + ":unknown", expected["unknown_date_count"], unknown)
        years = {str(y["year"]): y["count"] for y in expected["years"]}
        check(name + ":years", years, {r["name"]: r["count"] for r in actual_scope["years"].get("groups", [])})
        check(name + ":all_highest_ties", {str(y): expected["maximum_known_year_count"] for y in expected["all_maximum_years"]},
              {r["name"]: r["count"] for r in actual_scope["highest"].get("groups", [])})
        for y in expected["years"]:
            members(name + ":year:" + str(y["year"]), y["record_ids"], actual_scope["year_members"][str(y["year"])])
        expected_periods = comparison["periods"] if dimension == "all" else next(
            r["periods"] for r in comparison["by_entity"][dimension] if r["key"] == key)
        expected_counts = {p.get("id", p.get("period_id")): p["count"] for p in expected_periods}
        check(name + ":period_counts", expected_counts, {p["label"]: total(p) for p in actual_scope["periods"].get("periods", [])})
        for p in expected_periods:
            label = p.get("id", p.get("period_id"))
            members(name + ":period:" + label, p["record_ids"], actual_scope["period_members"][label])
        configured = reference["scope"]["periods"]
        check(name + ":period_ranges", [(p["id"], p["date_from"], p["date_to"], False) for p in configured],
              [(p["label"], p.get("filters", {}).get("date_from"), p.get("filters", {}).get("date_to"),
                p.get("filters", {}).get("include_unknown_dates")) for p in actual_scope["periods"].get("periods", [])])
    return {"status": "passed_read_only_engineering" if all(c["passed"] for c in checks) else "failed_read_only_engineering",
            "checks": checks, "customer_accepted": False, "semantic_reviewed": False, "M01_result": None, "M02_result": None,
            "limits": [
                "Explicit source-key selection; no natural-language question, model answer or browser interaction evaluated.",
                "Statistics tool records are at most ten examples; complete memberships independently reconciled via Service.browse.",
                "MCP graph paginated in groups of at most five; all selected record IDs and versions checked.",
                "Separate production read-only snapshots with before/after source, index and ledger fingerprints; not one global transaction.",
                "Source-defined associations are not verified business partnerships; corpus counts are not market totals.",
            ]}


def run(reference_folder, output):
    if output.exists():
        raise ValueError("Refuse to overwrite an existing check packet")
    reference, rows = load_reference(reference_folder)
    identity = reference.get("source_identity", {})
    if not isinstance(identity, dict) or not identity.get("observed_source_version_md5"):
        raise ValueError("Database-observed source identity required before application reconciliation")
    script_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    settings = replace(Settings.from_env(), research_agent_enabled=False, web_search_enabled=False)
    forbidden = ForbiddenModels()
    service = Service(settings, db=ReadOnlyDatabase(settings.database_url),
                      rag=forbidden, research_agent=forbidden, web_research=forbidden)
    observed = collect_application(service, reference)
    receipt = compare_application(reference, rows, observed)
    receipt.update({"built_at_utc": datetime.now(timezone.utc).isoformat(),
                    "reference_sha256": hashlib.sha256((reference_folder / "reference.json").read_bytes()).hexdigest(),
                    "script_sha256": script_sha256,
                    "graph_pages": len(observed["graph_pages"])})
    output.mkdir(parents=True)
    (output / "application_observations.json").write_bytes(encoded(observed))
    (output / "receipt.json").write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.reference, args.output)
    except Exception as exc:
        # Never print driver diagnostics, connection settings or arbitrary paths.
        print(json.dumps({"status": "check_unavailable", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]),
                      "failed": [c["check"] for c in result["checks"] if not c["passed"]],
                      "graph_pages": result["graph_pages"], "M01_result": None, "M02_result": None}))
    return 0 if result["status"] == "passed_read_only_engineering" else 1


if __name__ == "__main__":
    raise SystemExit(main())
