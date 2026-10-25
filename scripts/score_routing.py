"""Score query routing and known-source retrieval from recorded app events; never query a service.

Usage: python scripts/score_routing.py --labels LABELS.json --events RUN/server/events.jsonl
       [--events OTHER/events.jsonl ...] --out-dir OUT

LABELS is a JSON list of {query_id, query_class, expected_route, source_record_ids}.
Routing is judged from the research trace of each answer_result. Retrieval uses
the app's own record_selection (top 5 shown to the generator) and
generation_context events against the frozen source records. These are
known-source measures: Recall is over the labelled sources, not the corpus, and
Precision/NDCG need pooled graded judgments (scripts/score_retrieval_run.py).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

# Expected first collection tool for each route label.
ROUTES = {
    "content_search": {"search_records"},
    "title_lookup": {"find_records", "get_record", "get_record_metadata"},
    "statistics": {"record_statistics"},
    "scope_check": {"search_records", "record_statistics"},
}
COLLECTION_TOOLS = {"search_records", "find_records", "get_record", "get_record_metadata", "record_statistics"}
CLASSES = {"title_lookup", "content_single", "content_multi", "cross_collection", "statistics", "no_answer"}
# Title lookups return a record, not a ranked list; they are scored by routing only.
RETRIEVAL_CLASSES = {"content_single", "content_multi", "cross_collection"}
K = 5


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    labels = {}
    for row in rows:
        qid = row["query_id"]
        if qid in labels:
            raise ValueError(f"duplicate label {qid}")
        if row["query_class"] not in CLASSES:
            raise ValueError(f"{qid}: unknown query_class {row['query_class']}")
        if row["expected_route"] not in ROUTES:
            raise ValueError(f"{qid}: unknown expected_route {row['expected_route']}")
        labels[qid] = row
    return labels


def load_events(paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """Group app events by query; a query may appear in only one events file."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    owner: dict[str, Path] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            qid = event.get("query_id")
            if not qid or event.get("phase", "app") != "app":
                continue
            if owner.setdefault(qid, path) != path:
                raise ValueError(f"{qid} appears in more than one events file")
            grouped[qid].append(event)
    return grouped


def route_outcome(label: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tools = [(t.get("tool"), t.get("status")) for t in (result.get("research_trace") or {}).get("tools") or []]
    expected = ROUTES[label["expected_route"]]
    collection = [(tool, status) for tool, status in tools if tool in COLLECTION_TOOLS]
    first = collection[0][0] if collection else None
    reached = any(tool in expected and status == "ok" for tool, status in collection)
    if first in expected:
        error = ""
    elif first is None:
        error = "web_without_collection" if any(t == "search_external_sources" for t, _ in tools) else "no_collection_tool"
    elif label["expected_route"] == "content_search" and first in ROUTES["title_lookup"]:
        error = "content_sent_to_title_lookup"
    else:
        error = f"{first}_instead_of_{label['expected_route']}"
    return {"tools": tools, "first_collection_tool": first, "first_route_correct": first in expected,
            "reached_expected_ok": reached, "rejected_calls": sum(s in {"invalid_request", "not_found"} for _, s in tools),
            "routing_error": error, "status": result.get("status"), "answer_mode": result.get("answer_mode")}


def retrieval_outcome(label: dict[str, Any], events: list[dict[str, Any]], tools: list[tuple]) -> dict[str, Any]:
    known = list(dict.fromkeys(label.get("source_record_ids") or []))
    selections = [[e["record_id"] for e in event.get("evidence") or []]
                  for event in events if event["kind"] == "record_selection"]
    selections = [list(dict.fromkeys(ids))[:K] for ids in selections]
    context = {e["record_id"] for event in events if event["kind"] == "generation_context"
               for e in event.get("evidence") or []}
    failures = sum(event["kind"] == "retrieval_failure" for event in events)
    if not known or label["query_class"] not in RETRIEVAL_CLASSES:
        return {"known_sources": 0, "searches": len(selections), "retrieval_failures": failures}
    found = {rid for ids in selections for rid in ids}
    ranks = [ids.index(rid) + 1 for ids in selections for rid in known if rid in ids]
    # Attribute a miss to the earliest stage that lost the source.
    if all(rid in found for rid in known):
        cause = "found"
    elif failures:
        cause = "retrieval_error"
    elif not selections and any(t == "search_records" and st == "clarify" for t, st in tools):
        cause = "search_blocked_by_guard"
    elif not selections:
        cause = "no_search"
    elif found & set(known):
        cause = "partly_in_top5"
    else:
        cause = "not_in_top5"
    return {"known_sources": len(known), "searches": len(selections), "retrieval_failures": failures,
            "retrieval_cause": cause,
            "recall_known_at_5": sum(rid in found for rid in known) / len(known),
            "all_known_at_5": all(rid in found for rid in known),
            "mrr_known_at_5": 1 / min(ranks) if ranks else 0.0,
            "context_recall_known": sum(rid in context for rid in known) / len(known)}


def score(labels: dict[str, dict[str, Any]], events: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for qid, label in labels.items():
        query_events = events.get(qid, [])
        answers = [e for e in query_events if e["kind"] == "answer_result"]
        if len(answers) > 1:
            raise ValueError(f"{qid}: more than one primary answer_result")
        row = {"query_id": qid, "query_class": label["query_class"], "expected_route": label["expected_route"],
               "run": bool(answers)}
        if answers:
            row.update(route_outcome(label, answers[0]["result"]))
            row.update(retrieval_outcome(label, query_events, row["tools"]))
        else:
            # A planned question without a run stays in every denominator as a miss.
            row.update({"first_route_correct": False, "reached_expected_ok": False, "routing_error": "not_run"})
        rows.append(row)

    def summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        result = {"planned": len(group), "run": sum(r["run"] for r in group),
                  "first_route_correct": sum(r["first_route_correct"] for r in group),
                  "reached_expected_ok": sum(r["reached_expected_ok"] for r in group),
                  "routing_errors": dict(Counter(r["routing_error"] for r in group if r["routing_error"]))}
        result["first_route_accuracy"] = result["first_route_correct"] / len(group)
        scored = [r for r in group if r["query_class"] in RETRIEVAL_CLASSES and r.get("known_sources", 1)]
        if scored:
            for metric in ("recall_known_at_5", "mrr_known_at_5", "context_recall_known"):
                # Unrun questions with known sources count as zero retrieval.
                result[metric] = mean(r.get(metric, 0.0) for r in scored)
            result["known_source_questions"] = len(scored)
            result["retrieval_causes"] = dict(Counter(r.get("retrieval_cause", "not_run") for r in scored))
        return result

    by_class = defaultdict(list)
    for row in rows:
        by_class[row["query_class"]].append(row)
    return {"schema_version": "routing-score-v1", "k": K, "questions": rows,
            "by_class": {name: summary(group) for name, group in sorted(by_class.items())},
            "overall": summary(rows),
            "limits": ["Known-source recall is over labelled sources, not the full corpus.",
                       "Precision@5 and NDCG@5 require pooled graded judgments; see score_retrieval_run.py.",
                       "Routing correctness does not imply a correct answer."]}


def write(report: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "routing_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    fields = ["query_id", "query_class", "expected_route", "run", "first_collection_tool", "first_route_correct",
              "reached_expected_ok", "routing_error", "rejected_calls", "status", "answer_mode", "known_sources",
              "searches", "retrieval_failures", "retrieval_cause", "recall_known_at_5", "all_known_at_5", "mrr_known_at_5",
              "context_recall_known"]
    with (directory / "routing_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["questions"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--events", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = score(load_labels(args.labels), load_events(args.events))
    write(report, args.out_dir)
    overall = report["overall"]
    print(json.dumps({"planned": overall["planned"], "first_route_accuracy": round(overall["first_route_accuracy"], 4),
                      "out_dir": str(args.out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
