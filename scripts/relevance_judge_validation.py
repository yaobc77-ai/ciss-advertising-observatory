"""Score the list screening and the independent judge against human labels (paid; about $0.01).

Inputs: the hand-coded sentence labels, the article map (label doc_id -> record_id) and a
saved run of the five label questions (API detail=full), all from the 2026-10-23 validation.
The judge (relevance_judge, Decisions API) reads every article for every question, so its
recall is not limited to what screening read. Writes src/observatory/relevance_validation.v1.json,
which the Evaluation page shows.

    .venv/Scripts/python scripts/relevance_judge_validation.py --run-dir .runtime/rag_validation_20261023
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from observatory.config import Settings
from observatory.models import Filters
from observatory.relevance_judge import (
    THRESHOLD,
    ads_from_passages,
    judge_answer,
    kappa,
)
from observatory.service import Service

ROOT = Path(__file__).resolve().parents[1]
SHORT = {
    "green_labels.decreasing_emissions": "Reducing emissions",
    "green_labels.policies_programs": "Policies & programs",
    "ff_labels.infrastructure_and_production": "Fossil infrastructure",
    "green_labels.recycling_waste_management": "Recycling & waste",
    "green_labels.nature_animal_references": "Nature & animals",
}


def prf(predicted, truth):
    tp, fp, fn = len(predicted & truth), len(predicted - truth), len(truth - predicted)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p == 0 or r == 0 else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=ROOT / "sources/Native Advertising Data/handcoded_labels.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "src/observatory/relevance_validation.v1.json")
    parser.add_argument("--ndcg10", type=float, default=0.76, help="Hybrid retrieval NDCG@10 of the 2026-10-15 run")
    args = parser.parse_args()

    labels = pd.read_csv(args.labels)
    doc_map = {int(k): v for k, v in json.loads((args.run_dir / "doc_map.json").read_text(encoding="utf-8")).items()}
    doc_of = {v["record_id"]: k for k, v in doc_map.items() if v and v["retrievable"]}
    run = json.loads((args.run_dir / "results.json").read_text(encoding="utf-8"))

    service = Service(Settings.from_env())
    passages = service._public_evidence(service.db.record_passages(list(doc_of), Filters(dataset="all"), per_record=None))

    questions, totals, raw = [], {"screening": [0, 0, 0], "judge": [0, 0, 0]}, {}
    agree_pairs, human_pairs = [], []
    for label, item in run.items():
        truth = {int(d) for d in labels[labels[label] == 1].doc_id.unique() if int(d) in doc_of.values()}
        screened = {d["record_id"]: d for d in item["response"]["research_trace"]["list_screening"]["decisions"]}
        # Every article is judged; screening's decision and quote are attached where it read the article.
        decisions = [{"record_id": rid, "dataset": "native", **{k: screened.get(rid, {}).get(k) for k in
                      ("decision", "quote", "screening_reasoning")}} for rid in doc_of]
        for d in decisions:
            d["decision"] = d["decision"] or "does_not_match"
        report = judge_answer(service.rag, item["question"], ads_from_passages(decisions, passages), "relevance-validation")
        raw[label] = report
        probability = {doc_of[row["record_id"]]: row["probability"] for row in report["ads"]}
        listed = {doc_of[rid] for rid, d in screened.items() if d["decision"] == "matches" and rid in doc_of}
        judged = {doc for doc, p in probability.items() if p is not None and p >= THRESHOLD}
        scores = {"screening": prf(listed, truth), "judge": prf(judged, truth)}
        for who in totals:
            for n, key in enumerate(("tp", "fp", "fn")):
                totals[who][n] += scores[who][key]
        agree_pairs += [(doc in listed, doc in judged) for doc, p in probability.items() if p is not None]
        human_pairs += [(doc in listed, doc in judged, doc in truth) for doc, p in probability.items() if p is not None]
        questions.append({"label": label, "short": SHORT.get(label, label), "question": item["question"],
                          "human_positive": sorted(truth), "screening_listed": sorted(listed),
                          "judge_probability": {str(doc): p for doc, p in sorted(probability.items())},
                          **scores, "judge_cost_usd": report["summary"]["cost_usd"]})
        print(f"{label:42} screening F1 {scores['screening']['f1']}  judge F1 {scores['judge']['f1']}  "
              f"${report['summary']['cost_usd']:.5f}", flush=True)

    def micro(tp, fp, fn):
        return prf(set(range(tp)) | set(range(10_000, 10_000 + fp)), set(range(tp)) | set(range(20_000, 20_000 + fn)))

    data = {
        "version": "relevance-validation-v1", "run_date": date.today().isoformat(),
        "screening_run": "2026-10-23 run 3 (list-screening-v18)", "judge_model": "gpt-6-luna", "threshold": THRESHOLD,
        "articles": [{"doc": doc, "title": doc_map[doc]["title"]} for doc in sorted(doc_of.values())],
        "questions": questions,
        "micro": {"screening": micro(*totals["screening"]), "judge": micro(*totals["judge"]),
                  "agreement": sum(a == b for a, b in agree_pairs) / len(agree_pairs) if agree_pairs else None,
                  "kappa": kappa(agree_pairs), "ndcg10": args.ndcg10,
                  # Who the human label sides with when the two disagree, and how often an ad both list is relevant.
                  "disagreements": sum(s != j for s, j, _ in human_pairs),
                  "disagreements_screening_right": sum(s != j and s == h for s, j, h in human_pairs),
                  "both_listed": sum(s and j for s, j, _ in human_pairs),
                  "both_listed_human_yes": sum(s and j and h for s, j, h in human_pairs)},
        "cost_usd": round(sum(q["judge_cost_usd"] for q in questions), 6),
        "note": "Human labels: Spark team hand coding (sentence level). The judge is a model and can be wrong; it is "
                "scored here so its flags can be trusted to the measured degree. NDCG@10 is from the 2026-10-15 "
                "retrieval run, judged by AI, not by these human labels.",
    }
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.run_dir / "judge_raw.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(data["micro"], indent=1), "cost", data["cost_usd"])


if __name__ == "__main__":
    main()
