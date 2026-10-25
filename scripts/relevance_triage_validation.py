"""Ask the five label questions through the full answer path (criterion, Decisions triage, screening) and
score each route against human labels (paid; about $0.10).

Adds a "triage" block to src/observatory/relevance_validation.v1.json for the Evaluation page and the
track-record line under each list answer; full answers go to <run-dir>/triage_answers.json.

    .venv/Scripts/python scripts/relevance_triage_validation.py --run-dir .runtime/rag_validation_20261023
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd

from observatory.config import Settings
from observatory.models import Filters
from observatory.service import Service

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "green_labels.decreasing_emissions": "Which ads describe reducing or decreasing greenhouse gas emissions?",
    "green_labels.policies_programs": "Which ads mention environmental or climate policies, regulations or programs?",
    "ff_labels.infrastructure_and_production": "Which ads mention fossil fuel infrastructure or production, such as drilling, pipelines, refineries or power plants?",
    "green_labels.recycling_waste_management": "Which ads mention recycling or waste management?",
    "green_labels.nature_animal_references": "Which ads refer to nature or animals?",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=ROOT / "sources/Native Advertising Data/handcoded_labels.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "src/observatory/relevance_validation.v1.json")
    args = parser.parse_args()

    labels = pd.read_csv(args.labels)
    doc_map = {int(k): v for k, v in json.loads((args.run_dir / "doc_map.json").read_text(encoding="utf-8")).items()}
    doc_of = {v["record_id"]: k for k, v in doc_map.items() if v and v["retrievable"]}
    service = Service(Settings.from_env())
    answers, per_question, cost = {}, [], 0.0
    totals = {f"{route}{suffix}": 0 for route in ("pass", "review", "exclude") for suffix in ("", "_human_yes")}
    for label, question in QUESTIONS.items():
        started = time.time()
        result = service.answer(question, Filters(dataset="native", record_ids=sorted(doc_of)), "relevance-validation")
        result = result.model_dump(mode="json")
        answers[label] = result
        trace = result["research_trace"]["list_screening"]
        truth = {int(d) for d in labels[labels[label] == 1].doc_id.unique() if int(d) in doc_of.values()}
        routes = {doc_of[d["record_id"]]: d.get("route") for d in trace["decisions"] if d["record_id"] in doc_of}
        row = {"label": label, "question": question, "criterion": trace.get("criterion"),
               "human_positive": sorted(truth), "routes": {str(k): v for k, v in sorted(routes.items())},
               "cost_usd": result.get("cost_usd"), "seconds": round(time.time() - started, 1)}
        for route in ("pass", "review", "exclude"):
            docs = {doc for doc, r in routes.items() if r == route}
            row[route], row[f"{route}_human_yes"] = len(docs), len(docs & truth)
            totals[route] += len(docs)
            totals[f"{route}_human_yes"] += len(docs & truth)
        cost += result.get("cost_usd") or 0
        per_question.append(row)
        print(label, {k: row[k] for k in totals}, row["cost_usd"], row["seconds"], flush=True)
    (args.run_dir / "triage_answers.json").write_text(json.dumps(answers, indent=1, ensure_ascii=False), encoding="utf-8")
    data = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    data["triage"] = {"run_date": date.today().isoformat(), "pairs": sum(sum(r[k] for k in ("pass", "review", "exclude"))
                                                                       for r in per_question),
                      "human_positive": sum(len(r["human_positive"]) for r in per_question),
                      **totals, "cost_usd": round(cost, 6), "questions": per_question}
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in data["triage"].items() if k != "questions"}, indent=1))


if __name__ == "__main__":
    main()
