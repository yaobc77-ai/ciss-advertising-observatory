"""Demo: the Decisions API makes the final list judgment, with screening's vote removed (free replay).

The answer path routes each ad from two votes (relevance_triage.route): it passes when the Decisions judge
(gpt-6-luna) gives P(meets) >= PASS_AT and screening (gpt-5.6-luna) verified a copied sentence; it is
excluded when the judge is sure it does not meet the rules and no single rule says otherwise; every other ad
goes to a human check. This demo keeps the exclusion and the threshold and drops the screening condition:
P(meets) >= PASS_AT passes on the judge's word alone. Screening's sentence stays as evidence to show, not a
vote. The rule was fixed in plan.md before the replay was run; the thresholds are relevance_triage's.

It replays the judge's numbers recorded by a full-path run (no model call, $0) and scores both rules against
the human labels of the same run (Spark team hand coding, not the customer's questions):

    .venv/Scripts/python -X utf8 scripts/decisions_final_demo.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from observatory.relevance_triage import PASS_AT, excludable
from observatory.relevance_triage import route as current_route

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / ".runtime/rag_validation_20261023"
SHIPPED = ROOT / "src/observatory/relevance_validation.v1.json"
GROUPS = ("pass", "review", "exclude")


def final_route(numbers):
    """pass / review / exclude from the Decisions judge's numbers alone."""
    if numbers is None:
        return "review"  # no judgment: a person decides
    if excludable(numbers):
        return "exclude"
    return "pass" if numbers["meets"] >= PASS_AT else "review"


def replay(answers, positives, record_doc):
    """One row per (question, ad): both routes, the human label and what a reader sees."""
    rows = []
    for label, answer in answers.items():
        screening = answer["research_trace"]["list_screening"]
        for item in screening["decisions"]:
            numbers = item.get("triage")
            if item["record_id"] not in record_doc:
                raise SystemExit(f"No labelled article for record {item['record_id']} ({label})")
            rows.append({"label": label, "record_id": item["record_id"], "title": item.get("title"),
                         "human": record_doc[item["record_id"]] in positives[label],
                         "screening": item.get("decision"), "quote": item.get("quote"),
                         "current": current_route(item.get("decision"), numbers), "decisions_final": final_route(numbers),
                         "meets": None if numbers is None else numbers["meets"],
                         "rules": None if numbers is None else numbers.get("rules"),
                         "criterion": screening.get("criterion")})
    return rows


def tally(rows, key):
    """Per group: ads and how many the coders count as relevant; plus list precision and recall of 'pass'."""
    out = {group: {"ads": 0, "human_yes": 0} for group in GROUPS}
    for row in rows:
        out[row[key]]["ads"] += 1
        out[row[key]]["human_yes"] += row["human"]
    positives = sum(row["human"] for row in rows)
    passed = out["pass"]
    out["pass_precision"] = passed["human_yes"] / passed["ads"] if passed["ads"] else None
    out["pass_recall"] = passed["human_yes"] / positives if positives else None
    return out


def load(run_dir, shipped):
    answers = json.loads((run_dir / "triage_answers.json").read_text(encoding="utf-8"))
    doc_map = json.loads((run_dir / "doc_map.json").read_text(encoding="utf-8"))
    record_doc = {entry["record_id"]: int(doc) for doc, entry in doc_map.items()}
    positives = {q["label"]: set(q["human_positive"]) for q in json.loads(shipped.read_text(encoding="utf-8"))["questions"]}
    missing = set(answers) - set(positives)
    if missing:
        raise SystemExit(f"No human labels for {sorted(missing)}")
    return answers, positives, record_doc


def report(rows):
    lines = ["# Demo: Decisions API makes the final judgment (replay, $0)", "",
             f"{len(rows)} question-ad pairs, {sum(r['human'] for r in rows)} relevant to the coders.", "",
             "| Rule | Pass (coder-relevant) | Human check (coder-relevant) | Excluded (coder-relevant) | Pass precision | Pass recall |",
             "| --- | --- | --- | --- | --- | --- |"]
    for key, name in (("current", "Current: judge and screening"), ("decisions_final", "Demo: judge alone")):
        t = tally(rows, key)
        cells = [f"{t[g]['ads']} ({t[g]['human_yes']})" for g in GROUPS]
        cells += ["N/A" if t[key] is None else f"{t[key]:.0%}" for key in ("pass_precision", "pass_recall")]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    moved = [r for r in rows if r["current"] != r["decisions_final"]]
    lines += ["", f"## Ads that change group ({len(moved)})", ""]
    for r in moved:
        lines.append(f"- {r['label']} · {r['title']}: {r['current']} -> {r['decisions_final']}; P(meets) {r['meets']}, "
                     f"rules {r['rules']}, screening {r['screening']}, coders {'relevant' if r['human'] else 'not relevant'}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR)
    parser.add_argument("--labels", type=Path, default=SHIPPED)
    parser.add_argument("--out", type=Path, help="Also write the report and the rows (as <out>.json) here")
    args = parser.parse_args(argv)
    rows = replay(*load(args.run_dir, args.labels))
    text = report(rows)
    sys.stdout.write(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        args.out.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
