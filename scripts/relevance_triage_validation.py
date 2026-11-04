"""Ask the five label questions through the full answer path (criterion, Decisions triage, screening) and
score each route against human labels (paid; about $0.10 per arm).

Adds a block (default "triage") to src/observatory/relevance_validation.v1.json for the Evaluation page and
the track-record line under each list answer. Every paid phase is saved the moment it returns, before any
check: <run-dir>/<block>/<label>.card.json, <label>.judgment.json, then <label>.row.json once scored; the
completed answers also go to <run-dir>/<block>_answers.json.

    .venv/Scripts/python scripts/relevance_triage_validation.py --run-dir .runtime/rag_validation_20261023

`--strategy confirmed` (pipeline step 3, S3-e) goes through the two phases as the web does: the card first,
then the judgment by the card's unchanged draft. That is a programmatic acceptance of the model's draft, not
a human validation; the server labels it criterion_source "confirmed", screening_basis "confirmed_criterion"
(strategy (b): the criterion drives the triage and the screening). The judgment's provenance is checked
against the strategy before it is scored. `--doc-map` reuses another run's document map, `--block` names the
arm (its checkpoint folder and its block in --out), `--out` may point away from the shipped record, but only
into the run-dir; the shipped record takes only its own block "triage". An arm whose checkpoint folder
already holds files, or whose block already exists in --out, is refused.

Before anything is spent: the frozen cohort (15 articles, 75 pairs, 29 human positives) and the label
columns are checked, and with `--manifest` the exact inputs too (file hashes, the document mapping, the
positive documents of every label, label rows for every article, no missing values). Each arm's ledger
visitor is "relevance-validation:<block>:<run id>", unique to the run, so its charges are attributable
exactly; with `--cap-usd` the arm stops before a question when the ledger rows under that visitor (settled
amounts plus open reservations) plus `--reserve-usd` (the most one question is expected to cost; default
0.03, the baseline's largest question 0.024 plus a card) would exceed the cap. The cap is then enforced on
every reservation: the service's Budget is wrapped in AllowanceBudget, which, under one process lock, reads
what the ledger holds under the arm's visitor (settled amounts plus open reservations, rows only this process
writes) and refuses a reservation whose maximum would take that figure past the cap, whatever other visitors
do; the ledger's own monthly check still runs afterwards. The maximum counted is a true bound per path:
generation and embedding reservations already are (bytes of the prompt as the token bound, max_output_tokens,
the 1.25 cache-write margin); the Decisions judge reserves price(bytes // 3 + 400) for input-only billing and
a token is at least one byte, so its maximum is three times its reservation (BOUND_FACTORS), and the arm's
rows are recorded in the ledger at that maximum so outstanding holds keep the full bound until settlement;
the criterion draft reserves a fixed 0.003, above the computed maximum of that call for the frozen questions
(recorded in the run's protocol). The final ledger figure is compared with the cap and reported, never clamped:
`cap_exceeded`, exit status 3 (also when the figure could not be read).

    .venv/Scripts/python scripts/relevance_triage_validation.py --run-dir .runtime/s3e_20261028 \\
        --doc-map .runtime/rag_validation_20261023/doc_map.json --manifest .runtime/s3e_20261028/cohort_manifest.json \\
        --strategy confirmed --block triage_confirmed --cap-usd 0.20 \\
        --out .runtime/s3e_20261028/relevance_validation_s3e.json

A refusal, a missing card or draft, a `limited` or failed answer, an answer that is not a judged list, a
provenance that is not the strategy's, the cap, or an exception stops the run at that question: the phases
already saved stay and their cost is kept in the summary, nothing is retried, and the exit status is 2 (an
exception is recorded in the summary, then raised).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "src/observatory/relevance_validation.v1.json"
QUESTIONS = {
    "green_labels.decreasing_emissions": "Which ads describe reducing or decreasing greenhouse gas emissions?",
    "green_labels.policies_programs": "Which ads mention environmental or climate policies, regulations or programs?",
    "ff_labels.infrastructure_and_production": "Which ads mention fossil fuel infrastructure or production, such as drilling, pipelines, refineries or power plants?",
    "green_labels.recycling_waste_management": "Which ads mention recycling or waste management?",
    "green_labels.nature_animal_references": "Which ads refer to nature or animals?",
}
ROUTES = ("pass", "review", "exclude")
VISITOR = "relevance-validation"
COHORT = {"articles": 15, "pairs": 75, "human_positive": 29}  # the frozen hand-coded set of the 2026-10-24 baseline
RESERVE_USD = Decimal("0.03")  # the most one question is expected to cost: the baseline's largest (0.024) plus a card
# What a call can settle at, as a multiple of its reservation. The Decisions judge (gpt-6-luna, input only)
# reserves price(bytes // 3 + 400) and a token is at least one byte: actual <= price(bytes) <= 3 x reservation.
# Generation (gpt-5.6-luna) and embedding reservations are already strict bounds (rag.py).
BOUND_FACTORS = {"gpt-6-luna": Decimal("3")}
PROVENANCE = {"confirmed": ("confirmed", "confirmed_criterion"), "auto": ("draft_unconfirmed", "question")}


class RunStopped(Exception):
    """The run ends at this question; what was done so far is kept."""


def load_doc_map(path):
    """(doc_map, record_id -> doc id) of the retrievable hand-coded articles; checked before anything is spent."""
    doc_map = {int(k): v for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items()}
    doc_of = {v["record_id"]: k for k, v in doc_map.items() if v and v.get("retrievable")}
    if not doc_of:
        raise RunStopped(f"{path}: no retrievable article")
    if len(doc_of) != sum(1 for v in doc_map.values() if v and v.get("retrievable")):
        raise RunStopped(f"{path}: two articles share a record id")
    return doc_map, doc_of


def truth_for(labels, label, doc_of):
    return {int(d) for d in labels[labels[label] == 1].doc_id.unique() if int(d) in doc_of.values()}


def check_cohort(labels, doc_of, questions, cohort):
    """The frozen cohort's counts, before anything is spent: label columns, articles, pairs and human positives."""
    missing = [label for label in questions if label not in labels.columns]
    if missing:
        raise RunStopped(f"labels: no column for {missing}")
    found = {"articles": len(doc_of), "pairs": len(doc_of) * len(questions),
             "human_positive": sum(len(truth_for(labels, label, doc_of)) for label in questions)}
    if cohort is not None and found != dict(cohort):
        raise RunStopped(f"cohort differs from the frozen set: found {found}, expected {dict(cohort)}")
    return found


def cohort_for(questions, labels, doc_of, cohort=COHORT, all_questions=None):
    """The cohort figures a block must match: the frozen set for a full run, else the subset's figures derived
    from the validated labels and document map (a stopped arm's remainder), never from other files."""
    all_questions = all_questions or QUESTIONS
    if cohort is None or set(questions) == set(all_questions):
        return cohort
    return {"articles": len(doc_of), "pairs": len(doc_of) * len(questions),
            "human_positive": sum(len(truth_for(labels, label, doc_of)) for label in questions)}


def build_manifest(labels, labels_path, doc_map_path, doc_of, questions):
    """The identity of the frozen inputs: file hashes, the document mapping and every label's positive documents."""
    return {"labels_sha256": hashlib.sha256(Path(labels_path).read_bytes()).hexdigest(),
            "doc_map_sha256": hashlib.sha256(Path(doc_map_path).read_bytes()).hexdigest(),
            "doc_of": {record_id: doc for record_id, doc in sorted(doc_of.items(), key=lambda item: item[1])},
            "positives": {label: sorted(truth_for(labels, label, doc_of)) for label in questions}}


def check_manifest(labels, labels_path, doc_map_path, doc_of, questions, manifest_path):
    """The inputs are the frozen ones, document by document, and every article has complete label rows."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    current = build_manifest(labels, labels_path, doc_map_path, doc_of, questions)
    problems = []
    for key in ("labels_sha256", "doc_map_sha256"):
        if current[key] != manifest.get(key):
            problems.append(f"{key.replace('_sha256', '')} file differs from the manifest")
    if {k: int(v) for k, v in manifest.get("doc_of", {}).items()} != dict(doc_of):
        problems.append("document mapping differs from the manifest")
    for label in questions:
        if current["positives"][label] != manifest.get("positives", {}).get(label):
            problems.append(f"positive documents differ for {label}")
    rows = labels[labels.doc_id.isin(list(doc_of.values()))]
    without_rows = sorted(set(doc_of.values()) - {int(d) for d in rows.doc_id.unique()})
    if without_rows:
        problems.append(f"articles without label rows: {without_rows}")
    if rows[list(questions)].isna().any().any():
        problems.append("label rows with missing values")
    if problems:
        raise RunStopped("cohort manifest: " + "; ".join(problems))
    return manifest


def check_destination(run_dir, block, out):
    """The shipped record takes only its own block "triage"; any other --out must lie inside the run-dir."""
    out, run_dir = Path(out).resolve(), Path(run_dir).resolve()
    if out == SHIPPED.resolve():
        if block != "triage":
            raise RunStopped(f"{out} is the shipped record: only the block 'triage' may be written there")
        return
    if run_dir not in out.parents:
        raise RunStopped(f"--out {out} must lie inside --run-dir {run_dir}")


def select_questions(only, questions=None):
    """The questions to run: all of them, or the labels named in `only` (comma-separated), in the script's order."""
    questions = questions or QUESTIONS
    if not only:
        return dict(questions)
    wanted = [label.strip() for label in only.split(",") if label.strip()]
    if not wanted:
        raise RunStopped("--only names no label")
    unknown = [label for label in wanted if label not in questions]
    if unknown:
        raise RunStopped(f"--only names unknown labels: {unknown}")
    return {label: question for label, question in questions.items() if label in wanted}


def usable_draft(structured):
    criterion = structured.get("criterion")
    return isinstance(criterion, dict) and bool(criterion.get("counts"))


def ledger_attributed(database_url, visitor):
    """What the ledger holds under one visitor: settled amounts plus open (pending or uncertain) reservations."""
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(sum(COALESCE(actual_usd, reserved_usd)), 0) FROM usage_ledger "
                    "WHERE visitor = %s AND state <> 'cancelled'", (visitor,))
        return Decimal(str(cur.fetchone()[0]))


def ledger_open_rows(database_url, visitor):
    """Reservations under one visitor that have not settled yet (pending or uncertain)."""
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usage_ledger WHERE visitor = %s AND state IN ('pending', 'uncertain')", (visitor,))
        return int(cur.fetchone()[0])


class AllowanceBudget:
    """The service's Budget plus the arm's own allowance, checked on every reservation under one process lock.

    `reserve` first reads what the ledger holds under the arm's visitor (settled amounts plus open
    reservations: rows only this process writes) and refuses when that figure plus the new reservation
    would pass the allowance; other visitors' rows never widen it. The inner budget's own checks (the
    monthly budget, per-visitor limits) then run in its transaction. Everything else (settle, uncertain,
    cancel_unsent, reservation_cost, summary) is the inner budget's.
    """

    def __init__(self, inner, visitor, allowance, attributed):
        self.inner, self.visitor, self.allowance, self.attributed = inner, visitor, Decimal(str(allowance)), attributed
        self.refused, self._lock = [], threading.Lock()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @staticmethod
    def maximum(amount, model):
        """What the call can settle at: the reservation times the path's bound factor (1 where it is strict)."""
        return Decimal(str(amount)) * BOUND_FACTORS.get(model, Decimal(1))

    def reserve(self, amount, visitor, kind, model):
        """The guarded visitor's reservation is recorded at the call's maximum, so the ledger's outstanding
        holds keep the full bound until settlement (a smaller settlement releases the difference, an
        uncertain row keeps the whole hold): settled + outstanding maxima + this maximum <= allowance."""
        from observatory.budget import LimitReached

        with self._lock:
            if visitor == self.visitor:
                used, asked = Decimal(str(self.attributed(visitor))), self.maximum(amount, model)
                if used + asked > self.allowance:
                    self.refused.append({"kind": kind, "model": model, "used": str(used), "asked": str(amount), "maximum": str(asked)})
                    raise LimitReached(f"the arm's allowance {self.allowance} would be passed: {used} held plus up to {asked} for {kind}")
                return self.inner.reserve(asked, visitor, kind, model)
            return self.inner.reserve(amount, visitor, kind, model)


def install_allowance(service, visitor, cap_usd, attributed):
    """Wrap the service's budget so every reservation of this arm is checked against its allowance."""
    service.rag.budget = AllowanceBudget(service.rag.budget, visitor, cap_usd, attributed)
    return {"visitor": visitor, "allowance_usd": str(Decimal(str(cap_usd))), "guard": "AllowanceBudget on every reservation"}


def run_question(service, label, question, filters, strategy, visitor, save):
    """One question through the chosen arm; `save(stage, answer)` runs the moment each paid phase returns.

    "confirmed": the card, then the judgment by the card's unchanged draft (strategy (b)); "auto": one call
    (today's default, strategy (a)). A refusal, a missing card or draft, an answer that is not a judged list,
    a `limited` / failed status, or a provenance that is not the strategy's stops the run here.
    Returns {"result", "card", "cost_usd", "card_cost_usd"} as JSON dumps.
    """
    card = None
    if strategy == "confirmed":
        card = service.answer(question, filters, visitor, criterion_confirmation="ask")
        save("card", card)
        structured = card.structured_result or {}
        if structured.get("kind") != "criterion_confirmation" or not structured.get("continuation"):
            raise RunStopped(f"{label}: no card ({card.failure_reason or card.status})")
        if not usable_draft(structured):
            raise RunStopped(f"{label}: the card has no usable draft; nothing judged")
        result = service.answer(question, filters, visitor,
                                continuation={"token": structured["continuation"], "criterion": structured["criterion"]})
    else:
        result = service.answer(question, filters, visitor)
    save("judgment", result)
    if result.status not in ("answered", "insufficient_evidence") or result.failure_reason:
        raise RunStopped(f"{label}: {result.status} ({result.failure_reason or 'no reason'}); stopped, nothing retried")
    trace = (result.research_trace or {}).get("list_screening")
    if not trace or "decisions" not in trace:
        raise RunStopped(f"{label}: the answer is not a judged list (no list_screening.decisions)")
    actual = (trace.get("criterion_source"), trace.get("screening_basis"))
    if actual != PROVENANCE[strategy]:
        raise RunStopped(f"{label}: provenance {actual} is not strategy {strategy!r} {PROVENANCE[strategy]}; not scored")
    card_cost = float(card.cost_usd or 0) if card is not None else 0.0
    return {"result": result.model_dump(mode="json"), "card": card.model_dump(mode="json") if card is not None else None,
            "cost_usd": float(result.cost_usd or 0) + card_cost, "card_cost_usd": card_cost}


def score(label, question, done, truth, doc_of, strategy, seconds):
    """The three routes against the human labels, the listed documents, and every pair not counted.

    A document with more than one decision is ambiguous and a document whose route is not pass / review /
    exclude is unknown: both are reported and left out of the counts, never folded into a route (the frozen
    protocol). Listed = the answer's own list: one decision, matches, route pass.
    """
    trace = done["result"]["research_trace"]["list_screening"]
    seen = {}
    for item in trace["decisions"]:
        doc = doc_of.get(item.get("record_id"))
        if doc is not None:  # outside the hand-coded set otherwise
            seen.setdefault(doc, []).append((item.get("route"), item.get("decision")))
    ambiguous = sorted(doc for doc, items in seen.items() if len(items) > 1)
    unknown = sorted(doc for doc, items in seen.items() if len(items) == 1 and items[0][0] not in ROUTES)
    routes = {doc: items[0][0] for doc, items in seen.items() if len(items) == 1 and items[0][0] in ROUTES}
    listed = {doc for doc, items in seen.items() if len(items) == 1 and items[0] == ("pass", "matches")}
    missing = sorted(set(doc_of.values()) - set(seen))
    row = {"label": label, "question": question, "strategy": strategy, "criterion": trace.get("criterion"),
           "criterion_source": trace.get("criterion_source"), "screening_basis": trace.get("screening_basis"),
           "human_positive": sorted(truth), "routes": {str(k): v for k, v in sorted(routes.items())},
           "listed": sorted(listed), "listed_human_yes": len(listed & truth), "human_positive_listed": len(truth & listed),
           "missing_docs": missing, "ambiguous_docs": ambiguous, "unknown_route_docs": unknown,
           "cost_usd": done["cost_usd"], "card_cost_usd": done["card_cost_usd"], "seconds": round(seconds, 1)}
    for route in ROUTES:
        docs = {doc for doc, r in routes.items() if r == route}
        row[route], row[f"{route}_human_yes"] = len(docs), len(docs & truth)
    row["counted"] = sum(row[route] for route in ROUTES)
    row["accounted"] = row["counted"] + len(missing) + len(ambiguous) + len(unknown)  # == the articles of the cohort
    return row


def versions(service):
    """What was run: code, data and models; for the record, never for tuning."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                check=False).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/relevance_triage_validation.py"],
                                    cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip())
    except OSError:
        commit, dirty = "", None
    health = service.health() if hasattr(service, "health") else {}
    settings = getattr(service, "settings", None)
    return {"commit": commit, "script_uncommitted": dirty, "data_version": health.get("data_version"),
            "generation_model": getattr(settings, "generation_model", None),
            "embedding_model": getattr(settings, "embedding_model", None)}


def exit_status(summary):
    """3 when the arm's ledger figure exceeds its cap or could not be verified, 2 when it stopped early, else 0."""
    if summary.get("cap_exceeded") or (summary.get("cap_usd") is not None and summary.get("cap_exceeded") is None):
        return 3
    return 2 if summary.get("stopped") else 0


def run(service, labels, doc_of, *, strategy, run_dir, block, out, questions=None, visitor=None, cohort=COHORT,
        cap_usd=None, reserve_usd=RESERVE_USD, spent=None, guard=None, clock=time.time, now=None):
    """Every question of one arm, each paid phase saved as it returns; the block summary at the end.

    Refuses to start when the destination is not allowed, the arm's checkpoint folder already holds files,
    `out` already has the block, or the cohort is not the frozen one. With `cap_usd`: `guard(visitor, cap)`
    is installed once before the first question (install_allowance: every reservation of the arm is checked
    against the cap), and `spent(visitor)` (the ledger rows under the arm's visitor) is read before every
    question, which runs only when that figure plus `reserve_usd` (the most a question is expected to cost)
    stays within the cap. Stops at the first question that cannot be judged; the phases saved so far stay
    and their cost is in the summary. An unexpected exception is recorded in the summary and then raised.
    The final ledger figure is compared with the cap: `cap_exceeded` is reported, never hidden.
    """
    questions = questions or QUESTIONS
    run_dir, out = Path(run_dir), Path(out)
    now = now or (lambda: datetime.now(timezone.utc))
    run_id = now().strftime("%Y%m%dT%H%M%SZ")
    visitor = visitor or f"{VISITOR}:{block}:{run_id}"  # unique to this arm and run: its ledger rows are its own
    arm_dir = run_dir / block
    check_destination(run_dir, block, out)
    if arm_dir.exists() and any(arm_dir.iterdir()):
        raise RunStopped(f"{arm_dir} already holds checkpoints: choose another --block or --run-dir")
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    if block in data:
        raise RunStopped(f"{out} already has a block {block!r}: choose another --block or --out")
    found = check_cohort(labels, doc_of, questions, cohort)
    if cap_usd is not None and spent is not None and Decimal(str(spent(visitor))) != 0:
        raise RunStopped(f"the ledger already holds rows under {visitor}; the visitor must be new to this run")
    allowance_guard = guard(visitor, cap_usd) if cap_usd is not None and guard is not None else None
    arm_dir.mkdir(parents=True, exist_ok=True)
    started_at = now().isoformat()
    from observatory.models import Filters

    filters = Filters(dataset="native", record_ids=sorted(doc_of))
    answers, per_question, phases = {}, [], []
    totals = {f"{route}{suffix}": 0 for route in ROUTES for suffix in ("", "_human_yes")}
    stopped, failure = None, None

    def saver(label):
        def save(stage, answer):
            (arm_dir / f"{label}.{stage}.json").write_text(json.dumps(answer.model_dump(mode="json"), indent=1, ensure_ascii=False),
                                                            encoding="utf-8")
            phases.append({"label": label, "stage": stage, "status": answer.status, "failure_reason": answer.failure_reason or None,
                           "cost_usd": float(answer.cost_usd or 0), "at": now().isoformat()})
        return save

    try:
        for label, question in questions.items():
            if cap_usd is not None and spent is not None:
                used, reserve = Decimal(str(spent(visitor))), Decimal(str(reserve_usd))
                if used + reserve > Decimal(str(cap_usd)):
                    raise RunStopped(f"cap {cap_usd}: {used} attributed to {visitor} plus the reserve {reserve} for {label} "
                                     f"would exceed it; stopped before {label}")
            started = clock()
            done = run_question(service, label, question, filters, strategy, visitor, saver(label))
            row = score(label, question, done, truth_for(labels, label, doc_of), doc_of, strategy, clock() - started)
            (arm_dir / f"{label}.row.json").write_text(json.dumps(row, indent=1, ensure_ascii=False), encoding="utf-8")
            answers[label] = done["result"]
            if done["card"] is not None:
                answers[f"{label}.card"] = done["card"]
            for key in totals:
                totals[key] += row[key]
            per_question.append(row)
            print(label, {k: row[k] for k in totals}, "listed", row["listed_human_yes"], "/", len(row["listed"]),
                  "not counted", len(row["missing_docs"]) + len(row["ambiguous_docs"]) + len(row["unknown_route_docs"]),
                  f"${row['cost_usd']:.5f}", row["seconds"], flush=True)
    except RunStopped as exc:
        stopped = str(exc)
        print("stopped:", stopped, flush=True)
    except Exception as exc:  # noqa: BLE001 - recorded in the summary, then raised: nothing is retried
        stopped, failure = f"{type(exc).__name__}: {exc}", exc
        print("stopped:", stopped, flush=True)
    done_labels = {row["label"] for row in per_question}
    cost = sum(phase["cost_usd"] for phase in phases)
    attributed, cap_exceeded = None, None
    if spent is not None:
        try:
            final = Decimal(str(spent(visitor)))
            attributed = str(final)
            if cap_usd is not None:
                cap_exceeded = final > Decimal(str(cap_usd))
        except Exception as exc:  # noqa: BLE001 - the summary still records the run without the ledger figure
            attributed = f"unavailable: {type(exc).__name__}"
    (run_dir / f"{block}_answers.json").write_text(json.dumps(answers, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {"run_date": date.today().isoformat(), "run_id": run_id, "started_at": started_at, "ended_at": now().isoformat(),
               "strategy": strategy, "visitor": visitor, "cap_usd": None if cap_usd is None else str(cap_usd),
               "reserve_usd": None if cap_usd is None else str(reserve_usd),
               "acceptance": "the card's unchanged model draft, accepted programmatically" if strategy == "confirmed"
               else "no confirmation: the draft drives the triage only",
               "cohort": found, "pairs": sum(r["counted"] for r in per_question), "pairs_expected": found["pairs"],
               "human_positive": sum(len(r["human_positive"]) for r in per_question), "human_positive_expected": found["human_positive"],
               "questions_done": len(per_question), "questions_total": len(questions), "stopped": stopped,
               "listed": sum(len(r["listed"]) for r in per_question), "listed_human_yes": sum(r["listed_human_yes"] for r in per_question),
               "missing_pairs": sum(len(r["missing_docs"]) for r in per_question),
               "ambiguous_pairs": sum(len(r["ambiguous_docs"]) for r in per_question),
               "unknown_route_pairs": sum(len(r["unknown_route_docs"]) for r in per_question),
               **totals, "cost_usd": round(cost, 6),
               "stopped_question_cost_usd": round(sum(p["cost_usd"] for p in phases if p["label"] not in done_labels), 6),
               "ledger_attributed_usd": attributed, "cap_exceeded": cap_exceeded, "allowance_guard": allowance_guard,
               "phases": phases, "versions": versions(service), "questions": per_question}
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    data[block] = summary
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("questions", "phases")}, indent=1, ensure_ascii=False))
    if failure is not None:
        raise failure
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=ROOT / "sources/Native Advertising Data/handcoded_labels.csv")
    parser.add_argument("--out", type=Path, default=SHIPPED)
    parser.add_argument("--strategy", choices=("auto", "confirmed"), default="auto",
                        help="auto: one call, the draft drives the triage only (today's default); "
                             "confirmed: the card, then the judgment by its unchanged draft (S3-e)")
    parser.add_argument("--doc-map", type=Path, default=None, help="another run's doc_map.json (default: <run-dir>/doc_map.json)")
    parser.add_argument("--manifest", type=Path, default=None, help="frozen-input manifest to verify before anything is spent")
    parser.add_argument("--block", default="triage", help="name of the arm: its checkpoint folder and its block in --out")
    parser.add_argument("--cap-usd", type=Decimal, default=None,
                        help="run a question only while the arm's ledger rows plus --reserve-usd stay within this")
    parser.add_argument("--reserve-usd", type=Decimal, default=RESERVE_USD, help="the most one question is expected to cost")
    parser.add_argument("--only", default=None, help="comma-separated labels: run only these questions (the rest of a stopped arm)")
    args = parser.parse_args(argv)

    from observatory.config import Settings
    from observatory.service import Service

    try:
        check_destination(args.run_dir, args.block, args.out)
        questions = select_questions(args.only)
        labels = pd.read_csv(args.labels)
        doc_map_path = args.doc_map or (args.run_dir / "doc_map.json")
        _, doc_of = load_doc_map(doc_map_path)
        check_cohort(labels, doc_of, QUESTIONS, COHORT)  # the whole frozen set, whatever subset runs
        if args.manifest is not None:
            check_manifest(labels, args.labels, doc_map_path, doc_of, QUESTIONS, args.manifest)
        settings = Settings.from_env()
        service = Service(settings)
        spent = guard = None
        if args.cap_usd is not None:
            spent = lambda visitor: ledger_attributed(settings.database_url, visitor)  # noqa: E731 - a small hook
            guard = lambda visitor, cap: install_allowance(service, visitor, cap, spent)  # noqa: E731 - a small hook
        summary = run(service, labels, doc_of, strategy=args.strategy, run_dir=args.run_dir, block=args.block, out=args.out,
                      questions=questions, cohort=cohort_for(questions, labels, doc_of), cap_usd=args.cap_usd, reserve_usd=args.reserve_usd,
                      spent=spent, guard=guard)
    except RunStopped as exc:
        sys.exit(str(exc))
    sys.exit(exit_status(summary))


if __name__ == "__main__":
    main()
