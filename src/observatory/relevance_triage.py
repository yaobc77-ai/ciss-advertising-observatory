"""Explicit criterion and Decisions-API triage before list screening.

A list question is answered in four checkable steps:

1. Criterion: before any ad is read, the question is turned into short
   inclusion rules and exclusions (make_criterion, gpt-5.6-luna). The answer
   page shows them, so "relevant" means "meets these rules", not "answered".
2. Triage: every ad in a small scope (or every retrieved candidate in a large
   one) is read whole by OpenAI's Decisions API (gpt-6-luna) against those
   rules. One request per ad asks several bounded questions, like the official
   examples: a verdict choice (meets / borderline / does not meet), a strength
   score, and one probability per rule and per exclusion. The numbers are kept
   and shown as the judge's reasoning.
3. Screening: ads the triage does not exclude are screened as before, four at
   a time, from the question; a match needs a sentence copied from the ad and
   verified on the server. The criterion is not given to screening: with it,
   screening missed 5 of 29 coder-relevant articles (2026-10-24 run), so the
   two checks stay independent and the rules are the judge's.
4. Route: an ad passes the machine check when the triage says it meets the
   rules and screening found a verified sentence; it is excluded when the
   triage is confident it does not meet them; every other ad goes to a human
   check. The answer lists the passed ads and, separately, the ads to check.

Measured 2026-10-24 on 15 hand-coded articles x 5 questions (75 pairs, 29 relevant
to the coders), full answer path: 30 passed (25 relevant), 21 sent to a human check
(4 relevant), 24 excluded (none relevant). Thresholds were set from logic and one
earlier run of the same set, not tuned; one small set, no out-of-sample check yet.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .budget import price
from .relevance_judge import JUDGE_MODEL, MAX_AD_CHARS, _call

log = logging.getLogger(__name__)

POLICY = "relevance-triage-v1"
CRITERION_MODEL = "gpt-5.6-luna"
# Excluded without screening when the judge is at least this sure the ad does not meet the rules.
EXCLUDE_AT = 0.8
# No exclusion while any single rule is at least this likely: the judge's dimensions disagree
# (2026-10-24: "waste management" 0.49 but "does not meet" 0.97 on a coder-relevant article).
RULE_GUARD = 0.3
# Passes the machine check when P(meets) is at least this and screening verified a sentence.
PASS_AT = 0.5
# Scopes up to this many records are triaged whole; larger ones triage their retrieved candidates.
TRIAGE_ALL_MAX = 400
TRIAGE_MAX = 400
# At most this many triaged ads are screened; the rest of the non-excluded go to a human check.
SCREEN_MAX = 200
WORKERS = 16

CRITERION_SYSTEM = """You turn a researcher's list question about advertisements into an explicit inclusion
criterion, written before any ad is read. Give 1-4 short inclusion rules (what in an ad's own text makes it
count) and 0-3 exclusions (near misses that do not count). Each rule must be checkable against one sentence
of ad text. Keep the question's meaning: do not broaden or narrow it, and do not add conditions it does not
state. Write in the question's language."""


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    counts: list[str] = Field(min_length=1, max_length=4, description="Inclusion rules")
    does_not_count: list[str] = Field(max_length=3, description="Exclusions: near misses that do not count")


def enabled(rag):
    """Triage needs a client that can reach /v1/decisions; OBS_RELEVANCE_TRIAGE=off turns it off."""
    if os.environ.get("OBS_RELEVANCE_TRIAGE", "").lower() in ("off", "false", "0"):
        return False
    return callable(getattr(getattr(rag, "client", None), "post", None))


def make_criterion(rag, question, visitor):
    """(criterion dict or None, cost). A failed call leaves screening as it was."""
    if not enabled(rag):
        return None, 0.0
    rid = rag.budget.reserve(Decimal("0.003"), visitor, "generation", CRITERION_MODEL)
    try:
        response = rag.client.responses.parse(
            model=CRITERION_MODEL,
            input=[{"role": "system", "content": CRITERION_SYSTEM}, {"role": "user", "content": question}],
            text_format=Criterion, max_output_tokens=900, reasoning={"effort": "low"}, store=False)
        usage = response.usage
        details = getattr(usage, "input_tokens_details", None)
        actual = price(CRITERION_MODEL, usage.input_tokens, usage.output_tokens,
                       getattr(details, "cached_tokens", 0) or 0, getattr(details, "cache_write_tokens", 0) or 0)
        rag.budget.settle(rid, actual, {**usage.model_dump(), "observatory_request": {"policy": POLICY, "stage": "criterion"}})
    except Exception as exc:  # noqa: BLE001 - the list is still screened without a criterion.
        rag.budget.uncertain(rid, type(exc).__name__)
        # Logged by type only: the failure is visible to operators, the question is not.
        log.warning("Criterion call failed (%s); the list is screened without a criterion", type(exc).__name__)
        return None, 0.0
    parsed = response.output_parsed if response.status == "completed" else None
    try:
        return Criterion.model_validate(parsed.model_dump()).model_dump(), float(actual)
    except Exception as exc:  # noqa: BLE001 - an unusable criterion is no criterion.
        log.warning("Criterion reply unusable (%s, status %s); the list is screened without a criterion",
                    type(exc).__name__, getattr(response, "status", None))
        return None, float(actual)


def criterion_text(criterion):
    rules = "; ".join(f"({n}) {rule}" for n, rule in enumerate(criterion["counts"], 1))
    excluded = "; ".join(f"({n}) {rule}" for n, rule in enumerate(criterion.get("does_not_count") or [], 1))
    return f"Inclusion rules: {rules}." + (f" Exclusions: {excluded}." if excluded else "")


def triage_questions(question, criterion):
    head = f"Research question: \"{question}\". {criterion_text(criterion)}"
    items = [
        {"type": "choice", "name": "verdict",
         "instructions": head + " Judge only from the ad's own text. Which describes this ad?",
         "choices": [
             {"value": "meets", "description": "At least one sentence of the ad clearly satisfies an inclusion rule and no exclusion applies."},
             {"value": "borderline", "description": "A sentence comes close to a rule, or whether a rule or exclusion applies is a matter of interpretation."},
             {"value": "does_not_meet", "description": "No sentence of the ad satisfies any inclusion rule."}]},
        {"type": "score", "name": "strength", "instructions": head + " How much of the ad is about what the rules describe?",
         "levels": [{"label": "Absent", "description": "Nothing in the ad."},
                    {"label": "Passing", "description": "A phrase or aside."},
                    {"label": "Clear", "description": "At least one full sentence."},
                    {"label": "Central", "description": "The ad is mainly about it."}]},
    ]
    items += [{"type": "predicate", "name": f"rule_{n}", "instructions": f"Does a sentence of this ad satisfy this rule: {rule}"}
              for n, rule in enumerate(criterion["counts"], 1)]
    items += [{"type": "predicate", "name": f"exclusion_{n}",
               "instructions": f"Is the ad's only possible match ruled out by this exclusion: {rule}"}
              for n, rule in enumerate(criterion.get("does_not_count") or [], 1)]
    return items


def read_answers(response):
    """The judge's numbers for one ad: verdict probabilities, strength, and per-rule probabilities."""
    answers = {item.get("name"): item for item in response.get("answers") or []}
    verdict = answers.get("verdict") or {}
    if verdict.get("type") != "choice":
        return None
    probabilities = {item["value"]: item.get("probability") or 0.0 for item in verdict.get("probabilities") or []}
    strength = answers.get("strength") or {}
    level = None
    if strength.get("type") == "score" and strength.get("probabilities"):
        level = max(strength["probabilities"], key=lambda item: item.get("probability") or 0).get("label")

    def pick(prefix):
        return [round(item.get("probability") or 0.0, 3) for name, item in sorted(answers.items())
                if name.startswith(prefix) and item.get("type") == "predicate"]

    return {"choice": verdict.get("choice"), "meets": round(probabilities.get("meets", 0.0), 3),
            "borderline": round(probabilities.get("borderline", 0.0), 3),
            "does_not_meet": round(probabilities.get("does_not_meet", 0.0), 3),
            "confidence": verdict.get("confidence"),
            "strength": strength.get("score") if strength.get("type") == "score" else None, "strength_label": level,
            "rules": pick("rule_"), "exclusions": pick("exclusion_")}


def _ad_text(passages):
    first = passages[0]
    head = " · ".join(str(p) for p in (first.title, first.publisher, getattr(first, "sponsor", None)) if p)
    return f"Ad: {head}\n\n" + "\n".join(p.text for p in passages)[:MAX_AD_CHARS]


def triage(rag, question, criterion, groups, visitor, workers=WORKERS):
    """{record_id: judge numbers or None} and cost, one Decisions request per ad (in parallel)."""
    questions = triage_questions(question, criterion)

    def one(passages):
        body = {"model": JUDGE_MODEL, "input": _ad_text(passages), "questions": questions}
        try:
            response, cost = _call(rag, body, visitor, passages[0].record_id)
        except Exception as exc:  # noqa: BLE001 - an ad the judge could not read goes to screening as before.
            log.warning("Triage call failed for record %s (%s); the ad goes to screening",
                        passages[0].record_id, type(exc).__name__)
            return None, 0.0
        return read_answers(response), cost

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(one, groups))
    return {group[0].record_id: numbers for group, (numbers, _) in zip(groups, outcomes)}, sum(c for _, c in outcomes)


def excludable(numbers):
    """The judge is sure the ad does not meet the rules, and no single rule says otherwise."""
    return bool(numbers) and numbers["does_not_meet"] >= EXCLUDE_AT and max(numbers.get("rules") or [0.0]) < RULE_GUARD


def route(decision, numbers):
    """pass / review / exclude for one ad from its screening decision and the judge's numbers."""
    if numbers is None:
        return "pass" if decision == "matches" else "exclude"  # judge unavailable: screening alone decides
    if excludable(numbers):
        return "exclude"
    return "pass" if decision == "matches" and numbers["meets"] >= PASS_AT else "review"


def triaged_screen(screen, rag, question, evidence, visitor, *, criterion, extra=(), reread=None):
    """Triage, then screen what was not excluded; returns (results, cost, summary).

    `screen` is list_screening.screen. `evidence` holds the ranked candidates'
    passages and `extra` every passage of the other records in a small scope.
    Each result carries "route" and "triage" (the judge's numbers).
    """
    groups = {}
    for item in [*evidence, *extra]:
        groups.setdefault(item.record_id, []).append(item)
    groups = list(groups.values())[:TRIAGE_MAX]
    numbers, cost = triage(rag, question, criterion, groups, visitor)
    excluded = [g for g in groups if excludable(numbers.get(g[0].record_id))]
    kept = [g for g in groups if g not in excluded]
    # The likeliest matches are screened first; ties keep the retrieval order.
    kept.sort(key=lambda g: -((numbers.get(g[0].record_id) or {}).get("meets", 0.5)))
    screened, unscreened = kept[:SCREEN_MAX], kept[SCREEN_MAX:]
    results, spent = (screen(rag, question, [p for g in screened for p in g], visitor, limit=len(screened),
                             widen_to=len(screened), reread=reread) if screened else ([], 0.0))
    cost += spent
    for item in results:
        item["triage"] = numbers.get(item["record_id"])
        item["route"] = route(item["decision"], item["triage"])
    for g in unscreened:
        results.append({"record_id": g[0].record_id, "title": g[0].title, "decision": "unclear",
                        "reason": "not_screened", "triage": numbers.get(g[0].record_id), "route": "review"})
    for g in excluded:
        results.append({"record_id": g[0].record_id, "title": g[0].title, "decision": "does_not_match",
                        "reason": "triage_excluded", "triage": numbers[g[0].record_id], "route": "exclude"})
    summary = {"policy": POLICY, "model": JUDGE_MODEL, "exclude_at": EXCLUDE_AT, "rule_guard": RULE_GUARD, "pass_at": PASS_AT,
               "triaged": len(groups), "judged": sum(v is not None for v in numbers.values()),
               "screened": len(screened), "cost_usd": round(float(cost - spent), 6),
               **{name: sum(item["route"] == name for item in results) for name in ("pass", "review", "exclude")}}
    return results, float(cost), summary
