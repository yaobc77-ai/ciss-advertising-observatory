"""Demo: score the first 400 ranked native ads of each label question with the Decisions API (paid, capped).

A list question reads its ranked candidates in order and stops by rank 120 (list_screening.MAX_WIDENED);
the Decisions judge (gpt-6-luna) only sees those. This run asks how the judge's scores look further down:
for each of the five label questions of the 2026-10-24 validation (team hand coding, not the customer's
questions) it ranks every native ad with the answer path's hybrid search (keyword + vector + title, RRF;
the question text is the query), keeps the first 400 records, reads each whole (cut at MAX_AD_CHARS, as in
the answer path) and scores it with relevance_triage.triage against the rules recorded in that run.
Nothing is screened and no answer is written; /depth-demo (observatory.depth_demo) draws the saved result.

Money: every call reserves and settles through the budget ledger. The cap covers this run and every
earlier run of this script (ledger rows under "depth-demo:%"), so a rerun after a crash cannot spend the
approval twice. The questions are scored in rounds of BATCH ranks, all five per round, so a cap that runs
out leaves every question its first ranks; before each batch only the ads whose reservations fit the rest
of the cap are sent; that ad and every deeper one of the question are marked "not scored (cap)", so each
question keeps a scored prefix. The judge reserves its estimate (about 3 characters a token), but a token is
at least one character of the request, so CapBudget holds HOLD times the estimate for every open or
uncertain call (earlier runs included) and refuses any reservation whose hold would pass the cap. After the
run the ledger rows of this visitor are reconciled with the guard; a mismatch, an open reservation or a
total past the cap exits 3. Approved by the user 2026-10-28: five questions, 400 ads each, $0.60.

    .venv/Scripts/python -X utf8 scripts/decisions_depth_demo.py --cap-usd 0.60

--live-top-only adds to a saved result, for free, whether each ad is among the STOP_AT a live answer
ranks: it ranks again with the cached question vectors (a guard refuses any paid call) and stops if
the saved order no longer matches.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from observatory.budget import QUESTIONS, LimitReached, price
from observatory.depth_demo import DEFAULT_RESULT, STOP_AT, band_counts, group_of
from observatory.models import Filters
from observatory.relevance_judge import JUDGE_MODEL, MAX_AD_CHARS
from observatory.relevance_triage import (
    EXCLUDE_AT,
    PASS_AT,
    POLICY,
    RULE_GUARD,
    _ad_text,
    triage,
    triage_questions,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / ".runtime/rag_validation_20261023"
LABELS = ROOT / "src/observatory/relevance_validation.v1.json"
DEPTH = 400
BATCH = 100
VISITOR_PREFIX = "depth-demo:"
# The judge reserves price(len(body) // 3 + 400); tokens <= len(body) + 400, so 3x the estimate bounds a call.
HOLD = 3
SHORT = {"green_labels.decreasing_emissions": "Reducing emissions", "green_labels.policies_programs": "Climate policy",
         "ff_labels.infrastructure_and_production": "Fossil infrastructure",
         "green_labels.recycling_waste_management": "Recycling and waste", "green_labels.nature_animal_references": "Nature and animals"}


class CapBudget:
    """The run's ledger with a hard cap: earlier runs + settled + held (uncertain, open) + the new hold <= cap.

    A call is held at HOLD times its reservation until it settles; an uncertain call stays held.
    """

    def __init__(self, inner, cap_usd, earlier_usd=0):
        self.inner, self.cap, self.earlier = inner, Decimal(str(cap_usd)), Decimal(str(earlier_usd))
        self.settled, self.uncertain_usd, self.open = Decimal(0), Decimal(0), {}
        self.refused, self.over_hold = 0, 0
        self._lock = threading.Lock()

    def used(self):
        with self._lock:
            return self.earlier + self.settled + self.uncertain_usd + sum(self.open.values())

    def remaining(self):
        return self.cap - self.used()

    def reserve(self, amount, visitor, kind, model):
        amount = Decimal(str(amount))
        with self._lock:
            if self.earlier + self.settled + self.uncertain_usd + sum(self.open.values()) + amount * HOLD > self.cap:
                self.refused += 1
                raise LimitReached(f"Demo cap ${self.cap} reached")
            rid = self.inner.reserve(amount, visitor, kind, model)
            self.open[rid] = amount * HOLD
        return rid

    def settle(self, rid, actual, usage):
        self.inner.settle(rid, actual, usage)
        actual = Decimal(str(actual))
        with self._lock:
            held = self.open.pop(rid, None)
            self.over_hold += held is not None and actual > held
            self.settled += actual

    def uncertain(self, rid, error_type):
        self.inner.uncertain(rid, error_type)
        with self._lock:
            amount = self.open.pop(rid, None)
            if amount is not None:  # an unreconciled call stays held
                self.uncertain_usd += amount

    def cancel_unsent(self, rid):
        self.inner.cancel_unsent(rid)
        with self._lock:
            self.open.pop(rid, None)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def ledger_rows(db, pattern):
    """This script's ledger rows: settled cost, reserved amount of uncertain rows, pending rows and their amount."""
    with db.connect() as conn:
        row = conn.execute("SELECT COALESCE(sum(actual_usd) FILTER (WHERE state='settled'),0) AS settled, "
                           "COALESCE(sum(reserved_usd) FILTER (WHERE state='uncertain'),0) AS uncertain, "
                           "count(*) FILTER (WHERE state='pending') AS pending, "
                           "COALESCE(sum(reserved_usd) FILTER (WHERE state='pending'),0) AS pending_usd "
                           "FROM usage_ledger WHERE visitor LIKE %s", (pattern,)).fetchone()
    return {"settled": Decimal(str(row["settled"])), "uncertain": Decimal(str(row["uncertain"])),
            "pending": int(row["pending"]), "pending_usd": Decimal(str(row["pending_usd"]))}


def exposure(rows):
    """Settled at their cost; uncertain and pending rows held at HOLD x their reservation."""
    return rows["settled"] + (rows["uncertain"] + rows["pending_usd"]) * HOLD


def reconcile(guard, rows):
    """Problems between the guard's totals and this run's ledger rows; empty when they agree."""
    problems = []
    if abs(rows["settled"] - guard.settled) > Decimal("0.000001"):
        problems.append(f"ledger settled ${rows['settled']} but the run counted ${guard.settled}")
    if abs(rows["uncertain"] * HOLD - guard.uncertain_usd) > Decimal("0.000001"):
        problems.append(f"ledger holds ${rows['uncertain'] * HOLD} uncertain but the run counted ${guard.uncertain_usd}")
    if rows["pending"] or guard.open:
        problems.append(f"{rows['pending']} ledger rows pending, {len(guard.open)} reservations open in the run")
    if guard.over_hold:
        problems.append(f"{guard.over_hold} calls settled above their hold")
    if guard.earlier + exposure(rows) > guard.cap:
        problems.append(f"exposure ${guard.earlier + exposure(rows)} is past the cap ${guard.cap}")
    return problems


class NoSpend:
    """A ledger that refuses every reservation: the step it guards must stay free."""

    def __init__(self, inner):
        self.inner = inner

    def reserve(self, amount, visitor, kind, model):
        raise LimitReached("This step makes no paid call")

    def __getattr__(self, name):
        return getattr(self.inner, name)


def mark_live_top(result, rank_of):
    """Add in_live_top to every saved ad; rank_of(question) gives (order, shallow) record ids.

    Refuses unless the new ranking is exactly the saved one, rank for rank.
    """
    for q in result["questions"]:
        order, shallow = rank_of(q["question"])
        saved = [ad["record_id"] for ad in q["ads"]]
        if list(order) != saved:
            raise SystemExit(f"{q['label']}: the ranking changed since the run; nothing written")
        inside = set(shallow)
        for ad in q["ads"]:
            ad["in_live_top"] = ad["record_id"] in inside
    return result


def reservation(question, criterion, passages):
    """The amount relevance_judge._call will reserve for this ad (its own estimate)."""
    body = {"model": JUDGE_MODEL, "input": _ad_text(passages), "questions": triage_questions(question, criterion)}
    return max(price(JUDGE_MODEL, len(json.dumps(body)) // 3 + 400), Decimal("0.000001"))


def ranked_records(service, query, scope, vector, limit):
    """Record ids in the hybrid search's order, the first `limit` of them, and the passages found."""
    found = service.db.search(query, scope, vector=vector, model=service.settings.embedding_model,
                              chunks_per_record=2, limit=limit)
    return list(dict.fromkeys(e.record_id for e in found))[:limit], found


def whole_articles(service, order, scope, found):
    """One passage list per record, in rank order: the whole article, else what the search returned."""
    groups = {rid: [] for rid in order}
    for item in service._public_evidence(service.db.record_passages(order, scope, per_record=None)):
        groups[item.record_id].append(item)
    for item in found:
        if item.record_id in groups and not groups[item.record_id]:
            groups[item.record_id].append(item)
    return [groups[rid] for rid in order if groups[rid]]


def prepare(service, label, question, criterion, visitor, costs, depth):
    """Rank and read one question's ads (one embedding call; no judging)."""
    scope = Filters(dataset="native")
    vector = service.rag.embed([question], visitor=visitor, cost_sink=costs)[0]
    order, found = ranked_records(service, question, scope, vector, depth)
    # The answer path asks for MAX_WIDENED records; a deeper pool can reorder the top.
    shallow, _ = ranked_records(service, question, scope, vector, STOP_AT)
    groups = whole_articles(service, order, scope, found)
    return {"label": label, "question": question, "criterion": criterion, "scope": scope, "groups": groups,
            "estimates": [reservation(question, criterion, g) for g in groups], "shallow_ids": shallow,
            "ranked": len(order), "top_overlap": len(set(order[:STOP_AT]) & set(shallow)), "shallow": len(shallow)}


def fitting(estimates, room):
    """How many of these reservations, in order, fit in `room`."""
    n, total = 0, Decimal(0)
    for amount in estimates:
        if total + amount > room:
            break
        total, n = total + amount, n + 1
    return n


def score(service, prepared, guard, visitor, costs, batch=BATCH):
    """Judge every question's ads in rounds of `batch` ranks; returns {label: {record_id: numbers}} and statuses.

    Once an ad of a question does not fit, it and every deeper ad of that question stay "cap".
    """
    numbers = {p["label"]: {} for p in prepared}
    status = {p["label"]: {} for p in prepared}
    stopped = set()
    longest = max((len(p["groups"]) for p in prepared), default=0)
    for start in range(0, longest, batch):
        for p in prepared:
            groups, estimates = p["groups"][start:start + batch], p["estimates"][start:start + batch]
            if not groups:
                continue
            n = 0 if p["label"] in stopped else fitting([e * HOLD for e in estimates], guard.remaining())
            if n < len(groups):
                stopped.add(p["label"])
            for g in groups[n:]:
                status[p["label"]][g[0].record_id] = "cap"
            if n:
                refused = guard.refused
                got, _ = triage(service.rag, p["question"], p["criterion"], groups[:n], visitor,
                                cost_sink=costs[p["label"]])
                numbers[p["label"]].update(got)
                # triage turns any error into None; a refusal by the guard is the cap, not a failed call.
                missing = "cap" if guard.refused > refused else "failed"
                if missing == "cap":
                    stopped.add(p["label"])
                for g in groups[:n]:
                    status[p["label"]][g[0].record_id] = "scored" if got.get(g[0].record_id) else missing
            print(f"ranks {start + 1}-{start + len(groups)} {p['label']}: sent {n}, used ${float(guard.used()):.4f}",
                  file=sys.stderr)
    return numbers, status


def question_result(service, p, numbers, status, human_by_record, cost, depth):
    ads, shallow = [], set(p["shallow_ids"])
    for rank, group in enumerate(p["groups"], 1):
        first, rid = group[0], group[0].record_id
        text_chars = len("\n".join(item.text for item in group))
        ads.append({"rank": rank, "record_id": rid, "title": first.title, "publisher": first.publisher,
                    "sponsor": first.sponsor, "date": first.published_at.isoformat() if first.published_at else "",
                    "numbers": numbers.get(rid), "group": group_of(numbers.get(rid)), "status": status.get(rid, "cap"),
                    "truncated": text_chars > MAX_AD_CHARS, "human": human_by_record.get(rid),
                    "in_live_top": rid in shallow})
    return {"label": p["label"], "short": SHORT.get(p["label"], p["label"]), "question": p["question"],
            "criterion": p["criterion"], "scope_total": service._scope_count(p["scope"]), "ranked": p["ranked"],
            "top_overlap": p["top_overlap"], "shallow_ranked": p["shallow"],
            "scored": sum(a["status"] == "scored" for a in ads), "failed": sum(a["status"] == "failed" for a in ads),
            "not_scored_cap": sum(a["status"] == "cap" for a in ads), "truncated": sum(a["truncated"] for a in ads),
            "cost_usd": round(cost, 6), "bands": band_counts(ads, depth), "ads": ads}


def inputs(run_dir, labels_path):
    """(label, question, criterion, {record_id: human label}) for each validation question."""
    answers = json.loads((run_dir / "triage_answers.json").read_text(encoding="utf-8"))
    doc_map = json.loads((run_dir / "doc_map.json").read_text(encoding="utf-8"))
    record_doc = {entry["record_id"]: int(doc) for doc, entry in doc_map.items()}
    out = []
    for q in json.loads(labels_path.read_text(encoding="utf-8"))["questions"]:
        criterion = answers[q["label"]]["research_trace"]["list_screening"].get("criterion")
        if not criterion:
            raise SystemExit(f"No recorded criterion for {q['label']}")
        positives = set(q["human_positive"])
        out.append((q["label"], q["question"], criterion, {rid: doc in positives for rid, doc in record_doc.items()}))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--live-top-only", action="store_true",
                        help="Add live top-120 membership to the saved result; no paid call")
    parser.add_argument("--depth", type=int, default=DEPTH)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--dry-run", action="store_true", help="Rank and read only; print the reservations, judge nothing")
    args = parser.parse_args(argv)
    from observatory.config import Settings
    from observatory.service import Service

    service = Service(Settings.from_env())
    if args.live_top_only:
        service.rag.budget = NoSpend(service.rag.budget)
        result = json.loads(args.out.read_text(encoding="utf-8"))
        if service.db.health()["data_version"] != result["data_version"]:
            raise SystemExit("The collection changed since the run; nothing written")
        scope = Filters(dataset="native")

        def rank_of(question):
            vector = service.rag.embed([question], visitor="depth-demo-check")[0]
            return (ranked_records(service, question, scope, vector, result["depth"])[0],
                    ranked_records(service, question, scope, vector, STOP_AT)[0])

        mark_live_top(result, rank_of)
        result["live_top_checked_utc"] = datetime.now(timezone.utc).isoformat()
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        for q in result["questions"]:
            deep = [ad for ad in q["ads"] if ad["rank"] > STOP_AT]
            print(f"{q['label']}: past rank {STOP_AT}: {len(deep)}, of which in the live {STOP_AT}: "
                  f"{sum(ad['in_live_top'] for ad in deep)}", file=sys.stderr)
        return
    if args.cap_usd is None:
        parser.error("--cap-usd is required for a scoring run")
    earlier = exposure(ledger_rows(service.db, VISITOR_PREFIX + "%"))
    guard = CapBudget(service.rag.budget, args.cap_usd, earlier)
    service.rag.budget = guard
    started = datetime.now(timezone.utc)
    visitor = f"{VISITOR_PREFIX}{started:%Y%m%dT%H%M%S}"
    version = service.db.health()["data_version"]
    questions = inputs(RUN_DIR, LABELS)
    costs = {label: [] for label, *_ in questions}
    with QUESTIONS.question(visitor):  # the run counts as one question for the visitor limits
        prepared = [prepare(service, label, question, criterion, visitor, costs[label], args.depth)
                    for label, question, criterion, _ in questions]
        for p in prepared:
            print(f"{p['label']}: ranked {p['ranked']}, read {len(p['groups'])}, top-{STOP_AT} overlap "
                  f"{p['top_overlap']}/{p['shallow']}, reservations ${float(sum(p['estimates'])):.4f}", file=sys.stderr)
        if args.dry_run:
            print(f"Dry run: no ad judged; embedding ${float(guard.used() - earlier):.6f}", file=sys.stderr)
            return
        numbers, status = score(service, prepared, guard, visitor, costs)
    rows = ledger_rows(service.db, visitor)
    problems = reconcile(guard, rows)
    after = service.db.health()["data_version"]
    if after != version:  # paid scores are kept, marked; the page says so
        print("The collection changed during the run; the result is marked", file=sys.stderr)
    results = [question_result(service, p, numbers[p["label"]], status[p["label"]], human, sum(costs[p["label"]]), args.depth)
               for p, (_, _, _, human) in zip(prepared, questions)]
    out = {"run_date": started.date().isoformat(), "started_utc": started.isoformat(), "visitor": visitor,
           "model": JUDGE_MODEL, "policy": POLICY, "pass_at": PASS_AT, "exclude_at": EXCLUDE_AT, "rule_guard": RULE_GUARD,
           "max_ad_chars": MAX_AD_CHARS, "depth": args.depth, "batch": BATCH, "cap_usd": args.cap_usd,
           "earlier_runs_usd": float(earlier), "settled_usd": float(guard.settled), "uncertain_usd": float(guard.uncertain_usd / HOLD),
           "cost_usd": round(float(guard.settled + guard.uncertain_usd / HOLD), 6), "hold": HOLD,
           "open_reservations": len(guard.open), "ledger_exposure_usd": float(exposure(rows)), "reconcile_problems": problems,
           "data_version": version, "data_version_after": after, "questions": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {args.out}: ${out['cost_usd']:.4f} this run (+${float(earlier):.4f} earlier) of ${args.cap_usd:.2f}",
          file=sys.stderr)
    if problems:
        print("Ledger check failed: " + "; ".join(problems), file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
