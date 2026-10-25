"""Independent second opinion on a list answer, from OpenAI's Decisions API (gpt-6-luna).

List screening decides which ads answer a question (gpt-5.6-luna, four ads per
call, a copied sentence for every listed ad). This module asks a different
model, one ad at a time and from the ad's full stored text, three bounded
questions:

- belongs: the probability that the ad belongs in the answer;
- degree: how strongly it addresses the question, on a four-level scale;
- quote_supports (listed ads only): whether the copied sentence on its own
  shows that the ad belongs.

The Decisions API returns numbers, not text, so it cannot invent evidence; it
is used only to grade. Comparing its answer with the screening decision puts
every ad in one of four plain groups (VERDICTS) that a reader can check.
The judge is itself a model: its agreement with human labels is measured by
scripts/relevance_judge_validation.py, and it does not change any answer.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from .budget import QUESTIONS, price

JUDGE_MODEL = "gpt-6-luna"
POLICY = "relevance-judge-v1"
# Probability at or above which the judge counts an ad as belonging.
THRESHOLD = 0.5
# Long ads are cut; the opening of an advertorial carries its topic.
MAX_AD_CHARS = 12_000
MAX_ADS = 300
WORKERS = 8

LEVELS = [
    {"label": "Not related", "description": "The ad does not touch what the question asks about."},
    {"label": "Passing mention", "description": "The ad touches it in a phrase or aside only."},
    {"label": "Clearly discusses", "description": "At least one full sentence of the ad is about it."},
    {"label": "Central theme", "description": "The ad is mainly about it."},
]

# Screening decision x judge opinion -> what a reader should make of the ad.
VERDICTS = {
    "confirmed": "Listed, and the judge agrees",
    "doubted": "Listed, but the judge doubts it",
    "possible_miss": "Not listed, but the judge thinks it belongs",
    "agreed_out": "Not listed, and the judge agrees",
    "not_judged": "The judge gave no answer",
}


def _questions(question, quote):
    asked = f"A researcher asked about a collection of ads: \"{question}\""
    items = [
        {"type": "predicate", "name": "belongs",
         "instructions": f"{asked} Judging only from this ad's text, does this ad belong in the list that answers the question?"},
        {"type": "score", "name": "degree",
         "instructions": f"{asked} How strongly does this ad's text address what the question asks about?",
         "levels": LEVELS},
    ]
    if quote:
        items.append({"type": "predicate", "name": "quote_supports",
                      "instructions": f"{asked} This sentence was copied from the ad as evidence: \"{quote}\". "
                                      "Does this sentence on its own show that the ad belongs in the answer?"})
    return items


def _ad_input(ad):
    head = " · ".join(str(part) for part in (ad.get("title"), ad.get("publisher"), ad.get("sponsor")) if part)
    return f"Ad: {head}\n\n{(ad.get('text') or '')[:MAX_AD_CHARS]}"


def _call(rag, body, visitor, record_id):
    """One paid Decisions request, reserved and settled like every other model call."""
    # About 3 characters per token is a safe overestimate for English ads.
    estimate = max(price(JUDGE_MODEL, len(json.dumps(body)) // 3 + 400), Decimal("0.000001"))
    rid = rag.budget.reserve(estimate, visitor, "generation", JUDGE_MODEL)
    try:
        response = rag.client.post("/decisions", body=body, cast_to=object)
        usage = response.get("usage") or {}
        actual = price(JUDGE_MODEL, int(usage.get("input_tokens") or 0))
        rag.budget.settle(rid, actual, {**usage, "observatory_request": {
            "policy": POLICY, "stage": "relevance_judge", "record_id": record_id}})
    except Exception as exc:
        rag.budget.uncertain(rid, type(exc).__name__)
        raise
    return response, float(actual)


def verdict(decision, probability):
    if probability is None:
        return "not_judged"
    listed = decision == "matches"
    agrees = probability >= THRESHOLD
    return ("confirmed" if agrees else "doubted") if listed else ("possible_miss" if agrees else "agreed_out")


def judge_ad(rag, question, ad, visitor):
    """The judge's three answers for one ad, with its verdict group and cost."""
    row = {key: ad.get(key) for key in ("record_id", "dataset", "title", "decision", "quote", "screening_reasoning")}
    if not (ad.get("text") or "").strip():
        return {**row, "probability": None, "verdict": "not_judged", "error": "no_text", "cost_usd": 0.0}
    body = {"model": JUDGE_MODEL, "input": _ad_input(ad), "questions": _questions(question, ad.get("quote"))}
    try:
        response, cost = _call(rag, body, visitor, ad.get("record_id"))
    except Exception as exc:  # noqa: BLE001 - one failed ad must not hide the others.
        return {**row, "probability": None, "verdict": "not_judged", "error": type(exc).__name__, "cost_usd": 0.0}
    answers = {item.get("name"): item for item in response.get("answers") or []}
    belongs, degree, support = (answers.get(name) or {} for name in ("belongs", "degree", "quote_supports"))
    probability = belongs.get("probability") if belongs.get("type") == "predicate" else None
    level = None
    if degree.get("type") == "score" and degree.get("probabilities"):
        level = max(degree["probabilities"], key=lambda item: item.get("probability") or 0).get("label")
    return {**row, "probability": probability,
            "degree": degree.get("score") if degree.get("type") == "score" else None, "degree_label": level,
            "quote_support": support.get("probability") if support.get("type") == "predicate" else None,
            "verdict": verdict(ad.get("decision"), probability), "cost_usd": cost}


def kappa(pairs):
    """Cohen's kappa for (system listed, judge agrees) booleans; None when undefined."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    p_system = sum(a for a, _ in pairs) / n
    p_judge = sum(b for _, b in pairs) / n
    expected = p_system * p_judge + (1 - p_system) * (1 - p_judge)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def summarize(rows):
    judged = [row for row in rows if row["verdict"] != "not_judged"]
    counts = {name: sum(row["verdict"] == name for row in rows) for name in VERDICTS}
    quoted = [row for row in judged if row.get("decision") == "matches" and row.get("quote_support") is not None]
    return {
        "policy": POLICY, "model": JUDGE_MODEL, "threshold": THRESHOLD,
        "ads": len(rows), "judged": len(judged), "counts": counts,
        "agreement": ((counts["confirmed"] + counts["agreed_out"]) / len(judged)) if judged else None,
        "kappa": kappa([(row["decision"] == "matches", row["probability"] >= THRESHOLD) for row in judged]),
        "quotes_checked": len(quoted),
        "quotes_supported": sum(row["quote_support"] >= THRESHOLD for row in quoted),
        "cost_usd": round(sum(row.get("cost_usd") or 0 for row in rows), 6),
    }


def ads_from_passages(decisions, passages):
    """One judge input per screened ad: its decision and quote, and its passages joined in document order."""
    texts, meta = {}, {}
    for passage in passages:
        texts.setdefault(passage.record_id, []).append(passage.text)
        meta.setdefault(passage.record_id, passage)
    ads = []
    for decision in decisions[:MAX_ADS]:
        source = meta.get(decision.get("record_id"))
        ads.append({**{key: decision.get(key) for key in ("record_id", "dataset", "decision", "quote", "screening_reasoning")},
                    "title": getattr(source, "title", None) or getattr(source, "publisher", None) or decision.get("record_id"),
                    "publisher": getattr(source, "publisher", None), "sponsor": getattr(source, "sponsor", None),
                    "text": "\n".join(texts.get(decision.get("record_id"), []))})
    return ads


def judge_answer(rag, question, ads, visitor, workers=WORKERS):
    """Judge every ad (in parallel); the whole run counts as one question for visitor limits."""
    with QUESTIONS.question(visitor):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(lambda ad: judge_ad(rag, question, ad, visitor), ads[:MAX_ADS]))
    return {"question": question, "summary": summarize(rows), "ads": rows}
