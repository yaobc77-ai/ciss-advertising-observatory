"""Score version-bound ranking exports with ir_measures; never query a service.

Usage: python scripts/score_retrieval_run.py --manifest RUN/run_manifest.json
       --out-dir RUN/scored

Inputs follow templates/retrieval_evaluation. This wrapper validates identities,
preserves failed primary attempts, and labels incomplete relevance judgments.
All ranking mathematics is delegated to the explicit pytrec_eval provider.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

STATUSES = {"completed", "empty", "error", "timeout", "not_run"}
FAILURES = {"error", "timeout", "not_run"}
STAGES = {"candidate", "record_selection", "generation_context"}
MODES = {"keyword", "vector", "hybrid"}
UNITS = {"record", "passage"}
METRICS = ("ndcg", "precision", "recall", "mrr", "map", "hit", "judged")
STATISTICAL_TASKS = {"statistics", "statistical", "count"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def decode(value: str, kind: type, label: str) -> Any:
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid JSON") from exc
    require(isinstance(result, kind), f"{label}: expected {kind.__name__}")
    return result


def integer(value: str, label: str, minimum: int = 0) -> int:
    require(bool(re.fullmatch(r"\d+", value)), f"{label}: expected integer")
    result = int(value)
    require(result >= minimum, f"{label}: must be >= {minimum}")
    return result


def boolean(value: str, label: str) -> bool:
    require(value.lower() in {"true", "false"}, f"{label}: expected true/false")
    return value.lower() == "true"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_table(path: Path, columns: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        require(len(set(fields)) == len(fields), f"{path.name}: duplicate headers")
        require(columns <= set(fields), f"{path.name}: missing columns {sorted(columns-set(fields))}")
        rows = list(reader)
    require(all(None not in row and all(v is not None for v in row.values()) for row in rows),
            f"{path.name}: malformed CSV row")
    return rows


def source_binding(row: dict[str, str]) -> tuple[str, ...]:
    for field in ("eval_unit_id", "record_id", "version_id", "body_hash"):
        require(bool(row[field]), f"source binding: missing {field}")
    require(bool(re.fullmatch(r"[a-fA-F0-9]{64}", row["body_hash"])), "source binding: invalid body_hash")
    require(row["unit_type"] in UNITS, "source binding: unknown unit_type")
    locator = decode(row["evidence_locator_json"] or "{}", dict, "evidence_locator_json")
    binding = (row["record_id"], row["version_id"], row["body_hash"].lower())
    if row["unit_type"] == "passage":
        require(bool(row["chunk_id"] and locator), "passage requires chunk_id and locator")
        binding += (row["chunk_id"], json.dumps(locator, sort_keys=True))
    return binding


def load_inputs(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    require(isinstance(manifest, dict), "manifest must be an object")
    require(bool(manifest.get("run_id")), "manifest requires run_id")
    require(manifest.get("status") != "template_not_run", "blank template is not a run")
    query_ids = manifest.get("query_ids")
    require(isinstance(query_ids, list) and bool(query_ids), "manifest requires planned query_ids")
    require(all(isinstance(q, str) and q for q in query_ids), "invalid query_ids")
    require(len(query_ids) == len(set(query_ids)), "duplicate planned query_id")
    spec = manifest.get("metric_spec", {})
    require(spec.get("gain") == "linear_0_to_3", "only frozen linear gain is supported")
    require(spec.get("binary_relevant_minimum") == 2, "binary relevance threshold must be 2")
    require(spec.get("discount") == "log2(rank+1)", "unsupported position discount")
    required = {
        "queries": {"query_id", "task_type", "filters_json", "answerability", "reference_origin"},
        "judgments": {"query_id", "qrels_scope_id", "unit_type", "eval_unit_id", "record_id", "version_id",
                      "body_hash", "chunk_id", "evidence_locator_json", "relevance", "judgment_status",
                      "judgment_method", "corpus_relevance_complete"},
        "rankings": {"run_id", "attempt_id", "request_id", "query_id", "ranking_id", "stage", "retrieval_mode",
                     "retrieval_group_id", "collection", "unit_type", "effective_filters_json", "requested_k",
                     "returned_count", "status", "failure_stage", "reason", "qrels_scope_id"},
        "query_outcomes": {"run_id", "attempt_id", "is_primary", "query_id", "request_id", "status",
                           "ranking_ids_json", "metric_eligibility_json"},
        "retrieval_runs": {"run_id", "attempt_id", "request_id", "query_id", "ranking_id", "stage", "collection",
                           "unit_type", "rank", "eval_unit_id", "record_id", "version_id", "body_hash",
                           "chunk_id", "evidence_locator_json", "filters_json"},
    }
    tables: dict[str, Any] = {"manifest": manifest, "input_files": {}}
    for name, columns in required.items():
        path = manifest_path.parent / (manifest.get(f"{name}_file") or f"{name}.csv")
        digest = sha256(path)
        expected = manifest.get(f"{name}_sha256")
        require(not expected or digest == expected, f"{name}: frozen hash mismatch")
        tables[name] = read_table(path, columns)
        tables["input_files"][name] = {"path": str(path.resolve()), "sha256": digest,
                                      "frozen_hash_verified": bool(expected)}
    return tables


def validate(tables: dict[str, Any]) -> dict[str, Any]:
    manifest = tables["manifest"]
    run_id = manifest["run_id"]
    queries = {row["query_id"]: row for row in tables["queries"]}
    require(len(queries) == len(tables["queries"]), "duplicate queries row")
    require(set(queries) == set(manifest["query_ids"]), "queries must exactly match all planned IDs")
    for row in queries.values():
        decode(row["filters_json"], dict, "query filters")
    outcomes, primary = {}, {}
    for row in tables["query_outcomes"]:
        require(row["run_id"] == run_id and row["query_id"] in queries, "outcome run/query mismatch")
        require(bool(row["attempt_id"]), "outcome missing attempt_id")
        require(row["status"] in STATUSES, "unknown outcome status")
        key = (row["query_id"], row["attempt_id"])
        require(key not in outcomes, "duplicate query attempt")
        outcomes[key] = row
        row["_rankings"] = decode(row["ranking_ids_json"], list, "ranking_ids_json")
        require(len(set(row["_rankings"])) == len(row["_rankings"]), "duplicate outcome ranking ID")
        decode(row["metric_eligibility_json"] or "{}", dict, "metric_eligibility_json")
        row["_primary"] = boolean(row["is_primary"], "is_primary")
        if row["_primary"]:
            require(row["query_id"] not in primary, "multiple primary attempts")
            primary[row["query_id"]] = row
    require(set(primary) == set(queries), "every planned query needs exactly one primary outcome")
    rankings, stream_identities = {}, set()
    for row in tables["rankings"]:
        rid = row["ranking_id"]
        require(bool(rid) and rid not in rankings, "duplicate or empty ranking_id")
        key = (row["query_id"], row["attempt_id"])
        require(row["run_id"] == run_id and key in outcomes, "ranking run/attempt mismatch")
        outcome = outcomes[key]
        require(row["request_id"] == outcome["request_id"], "ranking request mismatch")
        require(rid in outcome["_rankings"], "ranking not declared by attempt")
        require(row["stage"] in STAGES and row["retrieval_mode"] in MODES, "unknown ranking stage/mode")
        require(row["unit_type"] in UNITS and bool(row["collection"]), "unknown ranking unit/collection")
        require(bool(row["qrels_scope_id"]), "ranking needs qrels_scope_id")
        require(row["status"] in STATUSES, "unknown ranking status")
        row["_filters"] = decode(row["effective_filters_json"], dict, "ranking filters")
        row["_k"] = integer(row["requested_k"], "requested_k", 1)
        row["_returned"] = integer(row["returned_count"], "returned_count")
        row["_primary"] = outcome["_primary"]
        stream_identity = tuple(row[field] for field in ("query_id", "attempt_id", "stage", "retrieval_mode",
            "retrieval_group_id", "collection", "unit_type", "requested_k", "qrels_scope_id")) + (
                json.dumps(row["_filters"], sort_keys=True),)
        require(stream_identity not in stream_identities, "duplicate logical ranking stream")
        stream_identities.add(stream_identity)
        rankings[rid] = row
    for outcome in outcomes.values():
        actual = {r["ranking_id"] for r in rankings.values()
                  if (r["query_id"], r["attempt_id"]) == (outcome["query_id"], outcome["attempt_id"])}
        require(set(outcome["_rankings"]) == actual, "attempt declares missing ranking")
        if queries[outcome["query_id"]]["task_type"] not in STATISTICAL_TASKS:
            require(bool(actual), "retrieval attempt requires planned ranking, including failures")
    qrels, bindings = defaultdict(dict), {}
    for row in tables["judgments"]:
        require(row["query_id"] in queries, "qrels query not planned")
        require(bool(row["qrels_scope_id"]), "qrels needs scope")
        topic = (row["query_id"], row["qrels_scope_id"], row["unit_type"])
        unit = row["eval_unit_id"]
        require(unit not in qrels[topic], "duplicate qrels unit")
        binding = source_binding(row)
        identity = (row["unit_type"], unit)
        require(identity not in bindings or bindings[identity] == binding, "inconsistent source binding")
        bindings[identity] = binding
        if row["relevance"] == "":
            require(row["judgment_status"] != "judged", "judged row missing relevance")
            row["_grade"] = None
        else:
            require(row["judgment_status"] == "judged", "unjudged row cannot have relevance")
            row["_grade"] = integer(row["relevance"], "relevance")
            require(row["_grade"] <= 3, "relevance must be 0..3")
            require(row["judgment_method"] in {"human", "ai_assisted", "rule_derived"}, "invalid judgment_method")
        boolean(row["corpus_relevance_complete"], "corpus_relevance_complete")
        qrels[topic][unit] = row
    for topic, rows in qrels.items():
        if topic[2] == "record":
            records = [row["record_id"] for row in rows.values()]
            require(len(records) == len(set(records)), "qrels contains multiple units for one record in one scope")
    runs = defaultdict(list)
    for row in tables["retrieval_runs"]:
        require(row["ranking_id"] in rankings, "result has undeclared ranking")
        ranking = rankings[row["ranking_id"]]
        for field in ("run_id", "query_id", "attempt_id", "request_id", "stage", "collection", "unit_type"):
            require(row[field] == ranking[field], f"result {field} mismatch")
        require(decode(row["filters_json"], dict, "result filters") == ranking["_filters"], "result filters mismatch")
        identity = (row["unit_type"], row["eval_unit_id"])
        binding = source_binding(row)
        require(identity not in bindings or bindings[identity] == binding, "returned source binding mismatch")
        bindings[identity] = binding
        row["_rank"] = integer(row["rank"], "rank", 1)
        runs[row["ranking_id"]].append(row)
    for rid, ranking in rankings.items():
        rows = runs[rid]
        require(len(rows) == ranking["_returned"], "returned_count mismatch")
        require([r["_rank"] for r in rows] == list(range(1, len(rows)+1)), "ranks must be consecutive in emitted order")
        require(len({r["eval_unit_id"] for r in rows}) == len(rows), "duplicate returned unit")
        if ranking["unit_type"] == "record":
            require(len({r["record_id"] for r in rows}) == len(rows), "duplicate returned record")
        if ranking["status"] in {"empty", "not_run"}:
            require(not rows, "empty/not_run ranking contains results")
    return {"queries": queries, "outcomes": outcomes, "primary": primary,
            "rankings": rankings, "qrels": qrels, "runs": runs}


def backend():
    try:
        import ir_measures
    except ImportError as exc:
        raise RuntimeError("Install ir_measures and pytrec_eval in an isolated evaluation environment") from exc
    provider = ir_measures.providers.registry["pytrec_eval"]
    require(provider.is_available(), "pytrec_eval provider is unavailable")
    return ir_measures, provider, ir_measures.providers.registry["judged"]


def evaluation_streams(rankings: dict[str, Any], metric_spec: dict[str, Any]):
    """Preserve retrieval request K while scoring predeclared smaller cutoffs."""
    cutoffs = metric_spec.get("evaluation_cutoffs")
    if cutoffs is not None:
        require(isinstance(cutoffs, list) and bool(cutoffs), "evaluation_cutoffs requires a nonempty list")
        require(all(type(k) is int and k > 0 for k in cutoffs), "evaluation_cutoffs requires positive integers")
        require(len(cutoffs) == len(set(cutoffs)), "duplicate evaluation cutoff")
    for rid, ranking in rankings.items():
        requested = ranking["_k"]
        applicable = [k for k in cutoffs if k <= requested] if cutoffs is not None else [requested]
        require(bool(applicable), f"{rid}: no evaluation cutoff fits requested_k; register an applicable cutoff")
        for k in applicable:
            yield rid, ranking, k


def score_manifest(manifest_path: Path) -> dict[str, Any]:
    tables = load_inputs(manifest_path)
    data = validate(tables)
    irm, provider, judged_provider = backend()
    scored = []
    for rid, ranking, k in evaluation_streams(data["rankings"], tables["manifest"]["metric_spec"]):
        query = data["queries"][ranking["query_id"]]
        topic = (ranking["query_id"], ranking["qrels_scope_id"], ranking["unit_type"])
        qrels = data["qrels"].get(topic, {})
        judged = {u: r["_grade"] for u, r in qrels.items() if r["_grade"] is not None}
        rows = data["runs"][rid]
        top = rows[:k]
        unjudged = sum(row["eval_unit_id"] not in judged for row in top)
        has_gain = any(grade > 0 for grade in judged.values())
        has_binary = any(grade >= 2 for grade in judged.values())
        measures = {"ndcg": irm.nDCG(dcg="log2") @ k, "precision": irm.P(rel=2) @ k,
                    "recall": irm.R(rel=2) @ k, "mrr": irm.RR(rel=2),
                    "map": irm.AP(rel=2) @ k, "hit": irm.Success(rel=2) @ k}
        raw = {metric: 0.0 for metric in METRICS}
        if judged:
            library_qrels = [irm.Qrel("topic", unit, grade) for unit, grade in judged.items()]
            # pytrec_eval RR has no cutoff. Truncating all input runs to K
            # implements MRR@K without credit for a later relevant result.
            library_run = [irm.ScoredDoc("topic", row["eval_unit_id"], -row["_rank"]) for row in top]
            result = provider.calc_aggregate(list(measures.values()), library_qrels, library_run)
            raw = {name: float(result[measure]) for name, measure in measures.items()}
            # ir_measures Judged divides by returned positions; project Judged@K
            # deliberately uses K, including missing positions. Preserve both.
            judged_ratio = judged_provider.calc_aggregate([irm.Judged @ k], library_qrels, library_run)[irm.Judged @ k]
            raw["judged"] = float(judged_ratio) * len(top) / k
        failed = ranking["status"] in FAILURES
        quality = {name: (0.0 if failed else raw[name]) for name in METRICS if name != "judged"}
        quality["judged"] = raw["judged"]
        eligibility = {}
        for metric in METRICS:
            reason = "eligible"
            if metric != "judged":
                if query["task_type"] in STATISTICAL_TASKS:
                    reason = "statistical_task"
                elif query["answerability"] == "verified_no_answer":
                    reason = "verified_no_answer"
                elif not judged:
                    reason = "reference_missing"
                elif metric == "ndcg" and not has_gain:
                    reason = "zero_idcg"
                elif metric in {"recall", "mrr", "map", "hit"} and not has_binary:
                    reason = "no_binary_reference"
                elif unjudged and not failed:
                    reason = "unjudged_provisional"
            eligibility[metric] = reason
            if reason not in {"eligible", "unjudged_provisional"}:
                quality[metric] = None
        row = {field: ranking[field] for field in ("ranking_id", "query_id", "attempt_id", "stage", "retrieval_mode",
                "retrieval_group_id", "collection", "unit_type", "qrels_scope_id", "status", "failure_stage", "reason")}
        row.update({"is_primary": ranking["_primary"], "requested_k": ranking["_k"], "metric_k": k,
                    "returned_count": len(rows), "judged_returned_count": sum(r["eval_unit_id"] in judged for r in rows),
                    "judged_at_k_count": len(top)-unjudged,
                    "unjudged_at_k": unjudged, "judged_fraction_of_returned_at_k": (len(top)-unjudged)/len(top) if top else None,
                    "known_relevant_count": sum(g >= 2 for g in judged.values()), "judged_candidate_count": len(judged),
                    "recall_scope": "corpus" if qrels and all(r["_grade"] is not None and boolean(r["corpus_relevance_complete"], "complete") for r in qrels.values()) else "known_judged_positives",
                    "eligibility": eligibility, "metrics": quality,
                    "successful_retrieval": ranking["status"] in {"completed", "empty"},
                    "unjudged_policy": "preserved rank; provisional diagnostic uses zero gain"})
        scored.append(row)
    groups = defaultdict(list)
    grouping = ("stage", "retrieval_mode", "retrieval_group_id", "collection", "unit_type", "metric_k")
    for row in scored:
        if row["is_primary"]:
            groups[tuple(row[field] for field in grouping)].append(row)
    aggregates = []
    for identity, rows in groups.items():
        summary = dict(zip(grouping, identity, strict=True))
        requested_ks = sorted({row["requested_k"] for row in rows})
        summary.update({"requested_ks": requested_ks, "requested_k": requested_ks[0] if len(requested_ks) == 1 else None})
        summary.update({"planned_rankings": len(rows), "failed_rankings": sum(not r["successful_retrieval"] for r in rows), "metrics": {}})
        for name in METRICS:
            official = [r["metrics"][name] for r in rows if r["eligibility"][name] == "eligible"]
            diagnostic = [r["metrics"][name] for r in rows if r["metrics"][name] is not None]
            success = [r["metrics"][name] for r in rows if r["successful_retrieval"] and r["eligibility"][name] == "eligible"]
            summary["metrics"][name] = {"mean": mean(official) if official else None, "scored_count": len(official),
                "provisional_inclusive_mean": mean(diagnostic) if diagnostic else None, "diagnostic_count": len(diagnostic),
                "success_only_mean": mean(success) if success else None, "success_only_count": len(success),
                "eligibility_counts": dict(Counter(r["eligibility"][name] for r in rows))}
        aggregates.append(summary)
    manifest = tables["manifest"]
    return {"schema_version": "retrieval-score-v1", "run_id": manifest["run_id"],
            "input_files": tables["input_files"], "manifest_sha256": sha256(manifest_path),
            "run_identity": {field: manifest.get(field) for field in (
                "transport", "deployment_url", "release_commit", "source_sha256", "data_version",
                "index_profile", "index_version", "model", "embedding_model", "prompt_version", "tool_policy_version")},
            "source_validation": "exported identity/version/hash/locator consistency; original bodies not read",
            "backend": {"library": "ir_measures", "version": importlib.metadata.version("ir_measures"),
                        "provider": "pytrec_eval", "provider_version": importlib.metadata.version("pytrec_eval-terrier"),
                        "judged_provider": "ir_measures.judged", "judged_denominator": "K; library returned-position ratio rescaled"},
            "metric_spec": manifest["metric_spec"], "planned_query_count": len(manifest["query_ids"]),
            "eligibility_authority": "computed from exported qrels and rankings; supplied eligibility is not trusted",
            "primary_outcome_counts": dict(Counter(r["status"] for r in data["primary"].values())),
            "attempt_count": len(data["outcomes"]), "ranking_stream_count": len(data["rankings"]),
            "ranking_cutoff_evaluation_count": len(scored), "rankings": scored, "aggregates": aggregates,
            "limits": ["This report does not measure answer correctness or customer acceptance.",
                       "Provisional zero-imputed scores are diagnostics, not fully judged comparison results.",
                       "Known-positive recall is not full-corpus recall unless completeness was declared."]}


def write_report(report: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    flattened = []
    for row in report["rankings"]:
        flat = {k: v for k, v in row.items() if k not in {"metrics", "eligibility"}}
        flat.update(row["metrics"])
        flat.update({f"{k}_eligibility": v for k, v in row["eligibility"].items()})
        flattened.append(flat)
    with (directory / "ranking_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        if flattened:
            writer = csv.DictWriter(handle, fieldnames=list(flattened[0]))
            writer.writeheader()
            writer.writerows(flattened)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = score_manifest(args.manifest)
    write_report(report, args.out_dir)
    print(json.dumps({"run_id": report["run_id"], "planned_queries": report["planned_query_count"],
                      "rankings": len(report["rankings"]), "out_dir": str(args.out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
