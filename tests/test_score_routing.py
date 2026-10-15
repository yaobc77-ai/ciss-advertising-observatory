import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score_routing.py"
spec = importlib.util.spec_from_file_location("score_routing", SCRIPT)
score_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_routing)


def label(qid, query_class="content_single", route="content_search", sources=("a",)):
    return {"query_id": qid, "query_class": query_class, "expected_route": route, "source_record_ids": list(sources)}


def answer(qid, *tools):
    return {"kind": "answer_result", "query_id": qid, "phase": "app",
            "result": {"status": "answered", "answer_mode": "rag",
                       "research_trace": {"tools": [{"tool": t, "status": s} for t, s in tools]}}}


def selection(qid, *records, kind="record_selection"):
    return {"kind": kind, "query_id": qid, "phase": "app", "evidence": [{"record_id": r} for r in records]}


def run(labels, events):
    grouped = {}
    for event in events:
        grouped.setdefault(event["query_id"], []).append(event)
    return score_routing.score({row["query_id"]: row for row in labels}, grouped)


def test_content_found_at_rank_two():
    report = run([label("Q1")], [answer("Q1", ("search_records", "ok")), selection("Q1", "x", "a", "y"),
                                 selection("Q1", "a", kind="generation_context")])
    row = report["questions"][0]
    assert row["first_route_correct"] and row["reached_expected_ok"]
    assert row["recall_known_at_5"] == 1.0 and row["mrr_known_at_5"] == 0.5
    assert row["retrieval_cause"] == "found" and row["context_recall_known"] == 1.0


def test_content_sent_to_title_lookup_is_named():
    report = run([label("Q1")], [answer("Q1", ("set_research_plan", "ok"), ("find_records", "not_found"),
                                        ("search_external_sources", "ok"))])
    row = report["questions"][0]
    assert row["routing_error"] == "content_sent_to_title_lookup"
    assert row["retrieval_cause"] == "no_search" and row["recall_known_at_5"] == 0.0


def test_web_only_and_guard_block_are_distinct():
    report = run([label("Q1"), label("Q2")],
                 [answer("Q1", ("set_research_plan", "invalid_request"), ("search_external_sources", "ok")),
                  answer("Q2", ("search_records", "clarify"), ("search_external_sources", "ok"))])
    first, second = report["questions"]
    assert first["routing_error"] == "web_without_collection"
    assert second["first_route_correct"] and not second["reached_expected_ok"]
    assert second["retrieval_cause"] == "search_blocked_by_guard"


def test_source_beyond_top_five_gets_no_credit():
    report = run([label("Q1")], [answer("Q1", ("search_records", "ok")), selection("Q1", "b", "c", "d", "e", "f", "a")])
    row = report["questions"][0]
    assert row["recall_known_at_5"] == 0.0 and row["mrr_known_at_5"] == 0.0
    assert row["retrieval_cause"] == "not_in_top5"


def test_cross_collection_partial_and_failure_attribution():
    report = run([label("Q1", "cross_collection", sources=("a", "b")), label("Q2")],
                 [answer("Q1", ("search_records", "ok")), selection("Q1", "a"),
                  answer("Q2", ("search_records", "unavailable")),
                  {"kind": "retrieval_failure", "query_id": "Q2", "phase": "app"}])
    first, second = report["questions"]
    assert first["recall_known_at_5"] == 0.5 and first["retrieval_cause"] == "partly_in_top5"
    assert second["retrieval_cause"] == "retrieval_error"


def test_unrun_question_stays_in_denominators():
    report = run([label("Q1"), label("Q2")], [answer("Q1", ("search_records", "ok")), selection("Q1", "a")])
    overall = report["overall"]
    assert overall["planned"] == 2 and overall["run"] == 1
    assert overall["first_route_accuracy"] == 0.5
    assert overall["recall_known_at_5"] == 0.5
    assert overall["retrieval_causes"] == {"found": 1, "not_run": 1}


def test_lookup_statistics_and_no_answer_score_routing_only():
    report = run([label("T", "title_lookup", "title_lookup"), label("S", "statistics", "statistics", ()),
                  label("N", "no_answer", "scope_check", ())],
                 [answer("T", ("find_records", "ok"), ("get_record_metadata", "ok")),
                  answer("S", ("resolve_entity", "ok"), ("record_statistics", "ok")),
                  answer("N", ("search_records", "ok"))])
    assert all(row["first_route_correct"] for row in report["questions"])
    assert "recall_known_at_5" not in report["overall"]
    assert set(report["by_class"]) == {"title_lookup", "statistics", "no_answer"}


def test_labels_and_events_are_validated(tmp_path):
    bad = tmp_path / "labels.json"
    bad.write_text(json.dumps([label("Q1", "content_title")]), encoding="utf-8")
    with pytest.raises(ValueError, match="query_class"):
        score_routing.load_labels(bad)
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    for path in (first, second):
        path.write_text(json.dumps(answer("Q1")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="more than one events file"):
        score_routing.load_events([first, second])
    with pytest.raises(ValueError, match="more than one primary"):
        run([label("Q1")], [answer("Q1"), answer("Q1")])
