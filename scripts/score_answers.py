"""Score reviewed answers with Ragas-style answer metrics; never query a model or service.

Usage: python scripts/score_answers.py --reviews answer_reviews.csv [--labels labels.json] --out-dir OUT

Each row of answer_reviews.csv is one primary attempt reviewed by a person or
an AI-assisted reviewer (templates/retrieval_evaluation). Definitions follow
Ragas, computed from the review counts instead of an LLM judge:

  faithfulness        supported_claims / checkable_claims
  answer_correctness  covered_points / required_points
  context_recall      context_supported_points / required_points
  citation_precision  correct_citations / citations
  response_relevancy  reviewer score in [0, 1]
  abstention_accuracy correct refusals on verified no-answer questions

Context Precision is a ranking measure of the generation context; compute it as
MAP@K at stage generation_context with scripts/score_retrieval_run.py.
A blank count means not reviewed and is reported, not treated as zero. A failed
attempt (no answer) scores zero on correctness and stays in the denominator.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

RATIOS = {
    "faithfulness": ("supported_claims", "checkable_claims"),
    "answer_correctness": ("covered_points", "required_points"),
    "context_recall": ("context_supported_points", "required_points"),
    "citation_precision": ("correct_citations", "citations"),
}
FAILED = {"error", "timeout", "not_run", "empty"}


def count(row: dict[str, str], field: str) -> int | None:
    value = (row.get(field) or "").strip()
    if value == "":
        return None
    number = int(value)
    if number < 0:
        raise ValueError(f"{row['query_id']}: {field} must be >= 0")
    return number


def flag(row: dict[str, str], field: str) -> bool | None:
    value = (row.get(field) or "").strip().lower()
    if value == "":
        return None
    if value not in {"true", "false"}:
        raise ValueError(f"{row['query_id']}: {field} must be true/false")
    return value == "true"


def question_scores(row: dict[str, str]) -> dict[str, Any]:
    failed = row.get("attempt_status", "") in FAILED
    scores: dict[str, Any] = {"query_id": row["query_id"], "failed": failed}
    for metric, (numerator, denominator) in RATIOS.items():
        top, bottom = count(row, numerator), count(row, denominator)
        if top is not None and bottom is not None and top > bottom:
            raise ValueError(f"{row['query_id']}: {numerator} exceeds {denominator}")
        if failed and metric == "answer_correctness" and bottom:
            scores[metric] = 0.0
        elif top is None or not bottom:
            # No checkable claims or no required points: not scorable, never 100%.
            scores[metric] = None
        else:
            scores[metric] = top / bottom
    relevancy = (row.get("response_relevancy") or "").strip()
    scores["response_relevancy"] = 0.0 if failed else (float(relevancy) if relevancy else None)
    if scores["response_relevancy"] is not None and not 0 <= scores["response_relevancy"] <= 1:
        raise ValueError(f"{row['query_id']}: response_relevancy must be within 0..1")
    expected, actual = flag(row, "abstention_expected"), flag(row, "abstention_actual")
    scores["abstention_correct"] = (actual is True) if expected else None
    scores["false_refusal"] = (actual is True) if expected is False else None
    return scores


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"questions": len(rows), "failed": sum(r["failed"] for r in rows)}
    for metric in (*RATIOS, "response_relevancy"):
        values = [r[metric] for r in rows if r[metric] is not None]
        result[metric] = {"mean": mean(values) if values else None, "scored": len(values),
                          "unscored": len(rows) - len(values)}
    for metric in ("abstention_correct", "false_refusal"):
        values = [r[metric] for r in rows if r[metric] is not None]
        result[metric] = {"rate": sum(values) / len(values) if values else None, "scored": len(values)}
    return result


def score(reviews: list[dict[str, str]], labels: dict[str, str]) -> dict[str, Any]:
    seen = set()
    rows = []
    for review in reviews:
        if (review.get("is_primary", "true") or "true").lower() != "true":
            continue
        if review["query_id"] in seen:
            raise ValueError(f"{review['query_id']}: more than one primary review")
        seen.add(review["query_id"])
        row = question_scores(review)
        row["query_class"] = labels.get(review["query_id"], "unlabelled")
        rows.append(row)
    groups = defaultdict(list)
    for row in rows:
        groups[row["query_class"]].append(row)
    return {"schema_version": "answer-score-v1", "questions": rows, "overall": summarise(rows),
            "by_class": {name: summarise(group) for name, group in sorted(groups.items())},
            "limits": ["Counts come from reviewers; AI-assisted reviews are not human accuracy.",
                       "Context Precision is scored as MAP@K at stage generation_context."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    with args.reviews.open(encoding="utf-8-sig", newline="") as handle:
        reviews = list(csv.DictReader(handle))
    labels = {}
    if args.labels:
        labels = {row["query_id"]: row["query_class"]
                  for row in json.loads(args.labels.read_text(encoding="utf-8-sig"))}
    report = score(reviews, labels)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "answer_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                      encoding="utf-8")
    print(json.dumps({"questions": report["overall"]["questions"], "out_dir": str(args.out_dir)}))


if __name__ == "__main__":
    main()
