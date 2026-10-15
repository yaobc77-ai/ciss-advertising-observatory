"""Independent fictional exports; no client questions, corpus, or live calls."""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from scripts.score_retrieval_run import (
    load_inputs,
    score_manifest,
    validate,
    write_report,
)

HAS_BACKEND = importlib.util.find_spec("ir_measures") is not None
requires_backend = pytest.mark.skipif(not HAS_BACKEND, reason="isolated ir_measures evaluation dependency not installed")


def make_export(tmp_path: Path) -> tuple[Path, dict]:
    """A fictional 3-position retrieval containing B then A, with C missed."""
    manifest = {"status": "completed", "run_id": "fictional-run", "query_ids": ["q-one"],
                "metric_spec": {"gain": "linear_0_to_3", "binary_relevant_minimum": 2,
                                "discount": "log2(rank+1)"}}
    query = {"query_id": "q-one", "task_type": "content", "filters_json": "{}",
             "answerability": "answerable", "reference_origin": "fictional_rules"}
    outcome = {"run_id": "fictional-run", "attempt_id": "attempt-one", "is_primary": "true",
               "query_id": "q-one", "request_id": "request-one", "status": "completed",
               "ranking_ids_json": '["rank-one"]', "metric_eligibility_json": "{}"}
    ranking = {"run_id": "fictional-run", "attempt_id": "attempt-one", "request_id": "request-one",
               "query_id": "q-one", "ranking_id": "rank-one", "stage": "record_selection",
               "retrieval_mode": "keyword", "retrieval_group_id": "whole", "collection": "native",
               "unit_type": "record", "effective_filters_json": "{}", "requested_k": "3",
               "returned_count": "2", "status": "completed", "failure_stage": "", "reason": "",
               "qrels_scope_id": "scope-one"}
    judgments = []
    for unit, grade in zip("ABCD", [3, 2, 1, 0], strict=True):
        judgments.append({"query_id": "q-one", "qrels_scope_id": "scope-one", "unit_type": "record",
            "eval_unit_id": unit, "record_id": f"record-{unit}", "version_id": "version-one",
            "body_hash": hashlib.sha256(unit.encode()).hexdigest(), "chunk_id": "", "evidence_locator_json": "{}",
            "relevance": str(grade), "judgment_status": "judged", "judgment_method": "rule_derived",
            "corpus_relevance_complete": "false"})
    runs = []
    for rank, unit in enumerate("BA", 1):
        source = next(row for row in judgments if row["eval_unit_id"] == unit)
        runs.append({key: ranking[key] for key in ("run_id", "attempt_id", "request_id", "query_id",
                     "ranking_id", "stage", "collection", "unit_type")} | {key: source[key] for key in
                    ("eval_unit_id", "record_id", "version_id", "body_hash", "chunk_id", "evidence_locator_json")}
                    | {"rank": str(rank), "filters_json": "{}"})
    tables = {"queries": [query], "query_outcomes": [outcome], "rankings": [ranking],
              "judgments": judgments, "retrieval_runs": runs}
    path = tmp_path / "run_manifest.json"
    persist(path, manifest, tables)
    return path, tables


def persist(path: Path, manifest: dict, tables: dict) -> None:
    for name, rows in tables.items():
        table_path = path.parent / f"{name}.csv"
        if rows:
            fields = list(rows[0])
        else:
            with table_path.open(encoding="utf-8", newline="") as handle:
                fields = csv.DictReader(handle).fieldnames
        with table_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def update(path: Path, tables: dict, **manifest_changes) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(manifest_changes)
    persist(path, manifest, tables)


def add_attempt(tables: dict, query: str, ranking: str, attempt: str, *, primary=True, mode="keyword") -> None:
    for table in ("query_outcomes", "rankings", "retrieval_runs"):
        base = copy.deepcopy(tables[table])
        for row in base:
            row["query_id"] = query
            row["attempt_id"] = attempt
            row["request_id"] = attempt
            if table == "query_outcomes":
                row["ranking_ids_json"] = json.dumps([ranking])
                row["is_primary"] = str(primary).lower()
            else:
                row["ranking_id"] = ranking
                if table == "rankings":
                    row["retrieval_mode"] = mode
            tables[table].append(row)


@requires_backend
def test_linear_grade_discount_and_short_list_denominators(tmp_path):
    path, _ = make_export(tmp_path)
    row = score_manifest(path)["rankings"][0]
    expected = (2+3/math.log2(3))/(3+2/math.log2(3)+1/math.log2(4))
    assert row["metrics"] == pytest.approx({"ndcg": expected, "precision": 2/3,
        "recall": 1, "mrr": 1, "map": 1, "hit": 1, "judged": 2/3})
    assert row["judged_fraction_of_returned_at_k"] == 1
    assert row["recall_scope"] == "known_judged_positives"


@requires_backend
def test_unjudged_keeps_rank_and_is_provisional(tmp_path):
    path, tables = make_export(tmp_path)
    tables["judgments"][1]["relevance"] = ""
    tables["judgments"][1]["judgment_status"] = "unjudged"
    update(path, tables)
    report = score_manifest(path)
    row = report["rankings"][0]
    assert row["metrics"]["mrr"] == .5
    assert row["metrics"]["judged"] == pytest.approx(1/3)
    assert row["eligibility"]["ndcg"] == "unjudged_provisional"
    assert report["aggregates"][0]["metrics"]["ndcg"]["mean"] is None
    assert report["aggregates"][0]["metrics"]["ndcg"]["diagnostic_count"] == 1


@requires_backend
@pytest.mark.parametrize("status", ["empty", "error", "timeout", "not_run"])
def test_empty_failure_and_not_run_stay_zero_in_denominator(tmp_path, status):
    path, tables = make_export(tmp_path)
    add_attempt(tables, "q-two", "rank-two", "attempt-two")
    tables["queries"].append(dict(tables["queries"][0], query_id="q-two"))
    tables["judgments"] += [dict(row, query_id="q-two") for row in tables["judgments"]]
    tables["query_outcomes"][-1]["status"] = status
    tables["rankings"][-1].update(status=status, returned_count="0")
    tables["retrieval_runs"] = [r for r in tables["retrieval_runs"] if r["query_id"] == "q-one"]
    update(path, tables, query_ids=["q-one", "q-two"])
    report = score_manifest(path)
    assert report["planned_query_count"] == 2
    assert report["rankings"][1]["metrics"]["ndcg"] == 0
    result = report["aggregates"][0]["metrics"]["ndcg"]
    assert result["scored_count"] == 2
    assert result["mean"] == report["rankings"][0]["metrics"]["ndcg"]/2


@requires_backend
@pytest.mark.parametrize("grades,ndcg_reason,binary_reason", [([0, 0, 0, 0], "zero_idcg", "no_binary_reference"),
    ([1, 1, 0, 0], "eligible", "no_binary_reference")])
def test_graded_zero_and_binary_zero_are_different(tmp_path, grades, ndcg_reason, binary_reason):
    path, tables = make_export(tmp_path)
    for row, grade in zip(tables["judgments"], grades, strict=True):
        row["relevance"] = str(grade)
    update(path, tables)
    row = score_manifest(path)["rankings"][0]
    assert row["eligibility"]["ndcg"] == ndcg_reason
    assert row["eligibility"]["recall"] == binary_reason
    assert row["metrics"]["recall"] is None
    assert row["metrics"]["precision"] == 0


@requires_backend
def test_no_reference_is_not_zero_quality(tmp_path):
    path, tables = make_export(tmp_path)
    tables["judgments"] = []
    update(path, tables)
    row = score_manifest(path)["rankings"][0]
    assert row["eligibility"]["ndcg"] == "reference_missing"
    assert row["metrics"]["ndcg"] is None
    assert row["metrics"]["judged"] == 0


@requires_backend
def test_verified_no_answer_separate_from_unknown_pool(tmp_path):
    path, tables = make_export(tmp_path)
    tables["queries"][0]["answerability"] = "verified_no_answer"
    update(path, tables)
    row = score_manifest(path)["rankings"][0]
    assert row["metrics"]["ndcg"] is None
    assert row["eligibility"]["ndcg"] == "verified_no_answer"


@requires_backend
def test_retry_does_not_replace_or_duplicate_primary(tmp_path):
    path, tables = make_export(tmp_path)
    add_attempt(tables, "q-one", "rank-retry", "attempt-retry", primary=False)
    update(path, tables)
    report = score_manifest(path)
    assert report["attempt_count"] == 2 and len(report["rankings"]) == 2
    assert report["aggregates"][0]["planned_rankings"] == 1


@requires_backend
def test_record_and_passage_cannot_mix_qrels(tmp_path):
    path, tables = make_export(tmp_path)
    for row in tables["rankings"]+tables["retrieval_runs"]:
        row["unit_type"] = "passage"
        if "eval_unit_id" in row:
            row["chunk_id"] = "chunk-"+row["eval_unit_id"]
            row["evidence_locator_json"] = '{"start": 0, "end": 30}'
    update(path, tables)
    assert score_manifest(path)["rankings"][0]["eligibility"]["ndcg"] == "reference_missing"


@requires_backend
def test_scope_cannot_reuse_other_filter_qrels(tmp_path):
    path, tables = make_export(tmp_path)
    tables["rankings"][0]["qrels_scope_id"] = "another-scope"
    update(path, tables)
    assert score_manifest(path)["rankings"][0]["metrics"]["ndcg"] is None


@requires_backend
def test_mrr_does_not_credit_relevant_result_beyond_cutoff(tmp_path):
    path, tables = make_export(tmp_path)
    tables["rankings"][0].update(requested_k="2", returned_count="3")
    sample = tables["retrieval_runs"][0]
    tables["retrieval_runs"] = []
    for rank, unit in enumerate("DCA", 1):
        source = next(r for r in tables["judgments"] if r["eval_unit_id"] == unit)
        tables["retrieval_runs"].append(dict(sample, rank=str(rank), **{key: source[key] for key in
            ("eval_unit_id", "record_id", "version_id", "body_hash")}))
    update(path, tables)
    metrics = score_manifest(path)["rankings"][0]["metrics"]
    assert metrics["mrr"] == metrics["precision"] == metrics["recall"] == 0
    assert metrics["map"] == metrics["hit"] == 0
    assert metrics["ndcg"] > 0  # Grade-one background still earns graded gain.
    assert metrics["judged"] == 1


@requires_backend
def test_average_precision_and_hit_use_binary_relevance(tmp_path):
    path, tables = make_export(tmp_path)
    sample = tables["retrieval_runs"][0]
    tables["retrieval_runs"] = []
    for rank, unit in enumerate("DA", 1):  # irrelevant first, then grade 3
        source = next(r for r in tables["judgments"] if r["eval_unit_id"] == unit)
        tables["retrieval_runs"].append(dict(sample, rank=str(rank), **{key: source[key] for key in
            ("eval_unit_id", "record_id", "version_id", "body_hash")}))
    update(path, tables)
    metrics = score_manifest(path)["rankings"][0]["metrics"]
    # Two binary-relevant units (A, B); only A found, at rank 2: AP = (1/2)/2.
    assert metrics["map"] == pytest.approx(0.25)
    assert metrics["hit"] == 1


@requires_backend
def test_groups_modes_and_k_have_separate_aggregates(tmp_path):
    path, tables = make_export(tmp_path)
    ranking = dict(tables["rankings"][0], ranking_id="rank-vector", retrieval_mode="vector", requested_k="5")
    tables["rankings"].append(ranking)
    tables["query_outcomes"][0]["ranking_ids_json"] = '["rank-one", "rank-vector"]'
    tables["retrieval_runs"] += [dict(r, ranking_id="rank-vector") for r in tables["retrieval_runs"]]
    update(path, tables)
    result = score_manifest(path)
    assert len(result["aggregates"]) == 2
    assert {(a["retrieval_mode"], a["requested_k"]) for a in result["aggregates"]} == {("keyword", 3), ("vector", 5)}


@requires_backend
def test_original_score_ties_do_not_replace_emitted_order(tmp_path):
    path, tables = make_export(tmp_path)
    for row in tables["retrieval_runs"]:
        row["raw_score"] = "0.99"
    update(path, tables)
    original = score_manifest(path)["rankings"][0]["metrics"]["ndcg"]
    tables["retrieval_runs"].reverse()
    for rank, row in enumerate(tables["retrieval_runs"], 1):
        row["rank"] = str(rank)
    update(path, tables)
    assert score_manifest(path)["rankings"][0]["metrics"]["ndcg"] > original


@requires_backend
def test_statistical_question_kept_in_outcomes_without_ir_mean(tmp_path):
    path, tables = make_export(tmp_path)
    tables["queries"][0]["task_type"] = "statistics"
    update(path, tables)
    report = score_manifest(path)
    assert report["planned_query_count"] == 1
    assert report["rankings"][0]["eligibility"]["ndcg"] == "statistical_task"
    assert report["aggregates"][0]["metrics"]["ndcg"]["mean"] is None


@requires_backend
def test_passage_locator_change_rejected_even_with_same_hash(tmp_path):
    path, tables = make_export(tmp_path)
    for row in tables["judgments"]+tables["rankings"]+tables["retrieval_runs"]:
        row["unit_type"] = "passage"
        if "eval_unit_id" in row:
            row["chunk_id"] = "chunk-"+row["eval_unit_id"]
            row["evidence_locator_json"] = '{"start": 0, "end": 30}'
    tables["retrieval_runs"][0]["evidence_locator_json"] = '{"start": 1, "end": 30}'
    update(path, tables)
    with pytest.raises(ValueError, match="binding mismatch"):
        score_manifest(path)


@pytest.mark.parametrize("mutation,message", [
    (lambda t: t["queries"].append(dict(t["queries"][0])), "duplicate queries"),
    (lambda t: t["judgments"].append(dict(t["judgments"][0])), "duplicate qrels"),
    (lambda t: t["query_outcomes"].clear(), "primary outcome"),
    (lambda t: t["query_outcomes"][0].update(is_primary="false"), "primary outcome"),
    (lambda t: t["query_outcomes"][0].update(ranking_ids_json="[]"), "not declared"),
    (lambda t: t["rankings"].append(dict(t["rankings"][0])), "duplicate or empty ranking"),
    (lambda t: t["rankings"][0].update(returned_count="3"), "returned_count"),
    (lambda t: t["retrieval_runs"][1].update(rank="3"), "consecutive"),
    (lambda t: t["retrieval_runs"][1].update(rank="1"), "consecutive"),
    (lambda t: t["retrieval_runs"][0].update(version_id="wrong"), "binding mismatch"),
    (lambda t: t["retrieval_runs"][0].update(body_hash="a"*64), "binding mismatch"),
    (lambda t: t["retrieval_runs"][0].update(filters_json='{"years":[2040]}'), "filters mismatch"),
    (lambda t: t["retrieval_runs"][0].update(request_id="other"), "request_id mismatch"),
    (lambda t: t["judgments"][0].update(relevance="4"), "0..3"),
    (lambda t: t["judgments"][0].update(judgment_status="unjudged"), "cannot have relevance"),
    (lambda t: t["rankings"][0].update(requested_k="0"), ">= 1"),
])
def test_invalid_export_rejected_before_backend(tmp_path, mutation, message):
    path, tables = make_export(tmp_path)
    mutation(tables)
    update(path, tables)
    with pytest.raises(ValueError, match=message):
        validate(load_inputs(path))


def test_hash_tampering_rejected(tmp_path):
    path, tables = make_export(tmp_path)
    update(path, tables, queries_sha256="0"*64)
    with pytest.raises(ValueError, match="frozen hash mismatch"):
        load_inputs(path)


def test_logically_identical_stream_cannot_double_weight_query(tmp_path):
    path, tables = make_export(tmp_path)
    tables["rankings"].append(dict(tables["rankings"][0], ranking_id="rank-duplicate"))
    tables["query_outcomes"][0]["ranking_ids_json"] = '["rank-one", "rank-duplicate"]'
    update(path, tables)
    with pytest.raises(ValueError, match="duplicate logical ranking"):
        validate(load_inputs(path))


def test_qrels_cannot_double_count_record_under_other_unit_id(tmp_path):
    path, tables = make_export(tmp_path)
    tables["judgments"].append(dict(tables["judgments"][0], eval_unit_id="A-copy"))
    update(path, tables)
    with pytest.raises(ValueError, match="multiple units for one record"):
        validate(load_inputs(path))


def test_duplicate_returned_unit_does_not_earn_extra_credit(tmp_path):
    path, tables = make_export(tmp_path)
    tables["retrieval_runs"][1] = dict(tables["retrieval_runs"][0], rank="2")
    update(path, tables)
    with pytest.raises(ValueError, match="duplicate returned unit"):
        validate(load_inputs(path))


@requires_backend
def test_output_retains_nulls_statuses_and_versions(tmp_path):
    path, _ = make_export(tmp_path)
    report = score_manifest(path)
    write_report(report, tmp_path / "scored")
    saved = json.loads((tmp_path / "scored/metrics.json").read_text(encoding="utf-8"))
    assert saved["backend"]["provider"] == "pytrec_eval"
    assert saved["input_files"]["queries"]["sha256"]
    with (tmp_path / "scored/ranking_metrics.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["ndcg_eligibility"] == "eligible"


@requires_backend
def test_predeclared_cutoffs_preserve_requested_k_and_separate_metrics(tmp_path):
    path, tables = make_export(tmp_path)
    tables["rankings"][0]["requested_k"] = "10"
    manifest = json.loads(path.read_text())
    manifest["metric_spec"]["evaluation_cutoffs"] = [5, 10]
    persist(path, manifest, tables)
    report = score_manifest(path)
    assert report["ranking_stream_count"] == 1
    assert report["ranking_cutoff_evaluation_count"] == 2
    assert [(r["requested_k"], r["metric_k"]) for r in report["rankings"]] == [(10, 5), (10, 10)]
    assert {a["metric_k"] for a in report["aggregates"]} == {5, 10}
    assert [r["metrics"]["precision"] for r in report["rankings"]] == [.4, .2]
    assert [r["metrics"]["judged"] for r in report["rankings"]] == [.4, .2]


@requires_backend
@pytest.mark.parametrize("status", ["empty", "error", "timeout", "not_run"])
def test_multiple_cutoffs_keep_failed_primary_at_each_denominator(tmp_path, status):
    path, tables = make_export(tmp_path)
    tables["rankings"][0].update(requested_k="10", returned_count="0", status=status)
    tables["query_outcomes"][0]["status"] = status
    tables["retrieval_runs"] = []
    manifest = json.loads(path.read_text())
    manifest["metric_spec"]["evaluation_cutoffs"] = [5, 10]
    persist(path, manifest, tables)
    report = score_manifest(path)
    assert report["planned_query_count"] == 1
    for group in report["aggregates"]:
        assert group["planned_rankings"] == 1
        assert group["requested_k"] == 10
        assert group["metrics"]["ndcg"]["scored_count"] == 1
        assert group["metrics"]["ndcg"]["mean"] == 0


@requires_backend
def test_cutoff_above_requested_k_is_not_scored(tmp_path):
    path, tables = make_export(tmp_path)
    tables["rankings"][0]["requested_k"] = "5"
    manifest = json.loads(path.read_text())
    manifest["metric_spec"]["evaluation_cutoffs"] = [5, 10]
    persist(path, manifest, tables)
    rows = score_manifest(path)["rankings"]
    assert len(rows) == 1 and rows[0]["metric_k"] == rows[0]["requested_k"] == 5


@requires_backend
@pytest.mark.parametrize("cutoffs,error", [([], "nonempty"), ([0], "positive"), ([True], "positive"),
    ([5, 5], "duplicate"), ([5, 10], "no evaluation cutoff")])
def test_invalid_cutoffs_fail_instead_of_silently_losing_ranking(tmp_path, cutoffs, error):
    path, tables = make_export(tmp_path)
    manifest = json.loads(path.read_text())
    manifest["metric_spec"]["evaluation_cutoffs"] = cutoffs
    persist(path, manifest, tables)
    with pytest.raises(ValueError, match=error):
        score_manifest(path)
