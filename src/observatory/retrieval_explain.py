"""The reader's retrieval score: how high the search placed a passage, out of 100, and why.

db.search ranks passages by reciprocal-rank fusion: each route that finds a passage
adds 1/(60 + place). This module rescales that same sum so the reader can follow it:
with R routes run, place n in one route is worth (100 / R) x 61 / (60 + n) points,
place 1 in every route is 100, and a route that did not find the passage adds 0.
The order is unchanged within one search. The score says how high the search
placed the passage for these words and this meaning, not whether the ad is relevant
or correct; that is the Decisions judge's accuracy score on list answers.

The reader sees the list's NDCG (ndcg): each shown ad's RAG score, the fused score the
search returned for it, as its gain at the place the answer shows it, against the same
ads in the order of their RAG scores; each card shows its share of that NDCG.
"""

from __future__ import annotations

import math

K = 60  # the fusion constant in db.search
ROUTES = ("keyword", "title", "vector", "literal")
ROUTE_NAMES = {"keyword": "Words in the text", "title": "Words in the title",
               "vector": "Similar meaning", "literal": "Exact phrase"}


def route_points(place, routes_run):
    """Points one route gives for one place."""
    return 100 * (K + 1) / (len(routes_run) * (K + place))


def _field(item, name):
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def passage_score(routes):
    """{"score", "parts", "missed", "run"} for one passage's retrieval_routes; None without detail."""
    run = [route for route in (routes or {}).get("run") or [] if route in ROUTES]
    if not run:
        return None
    parts, missed = [], []
    for route in run:
        detail = routes.get(route)
        if not isinstance(detail, dict) or not isinstance(detail.get("rank"), int) or detail["rank"] < 1:
            missed.append(route)
            continue
        parts.append({"route": route, "place": detail["rank"], "points": route_points(detail["rank"], run),
                      **{key: detail[key] for key in ("terms", "similarity") if key in detail}})
    return {"score": sum(part["points"] for part in parts), "parts": parts, "missed": missed, "run": run}


def _rag_score(item):
    score = _field(item, "score")
    return float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None


def group_explain(evidence):
    """For one retrieval group: the search words and, per record returned, its highest-scoring
    passage: that passage's RAG score and, when the passage kept them, the routes behind it
    ("run" is None without them). No records only when the search returned nothing; "partial"
    when some passage kept no route detail."""
    search, best = {}, {}
    for item in evidence:
        rid, score = _field(item, "record_id"), _rag_score(item)
        explained = passage_score(_field(item, "retrieval_routes"))
        rank = (-math.inf if score is None else score, -math.inf if explained is None else explained["score"])
        if rid not in best or rank > best[rid][0]:  # the highest RAG score; route points break a tie
            best[rid] = (rank, score, explained, item)
    partial = any(passage_score(_field(item, "retrieval_routes")) is None for item in evidence)
    records = {}
    for rid, (_, score, explained, item) in best.items():
        if explained is not None:
            search = search or dict(_field(item, "retrieval_search") or {})
        records[rid] = {**(explained or {"score": None, "parts": [], "missed": [], "run": None}),
                        "rag_score": score, "evidence_id": _field(item, "evidence_id"),
                        "version_id": _field(item, "version_id"), "dataset": _field(item, "dataset")}
    return {"terms": list(search.get("terms") or []), "dropped": list(search.get("dropped") or []),
            "cut": list(search.get("cut") or []), "unindexed": list(search.get("unindexed") or []),
            "runs": {r["dataset"]: r["run"] for r in records.values() if r["run"]},
            "records": records, "partial": partial}


def searches(result):
    """[(label, query, explain or None)] for each of the answer's searches, in order; None when the
    search kept no detail."""
    out = []
    for group in (result.get("structured_result") or {}).get("groups") or []:
        if isinstance(group, dict) and (group.get("query") or "retrieval_explain" in group):
            out.append((str(group.get("label") or "Search"), str(group.get("query") or ""),
                        group.get("retrieval_explain") or None))
    return out


def complete(result):
    """True when every search kept its detail, so an ad no search placed was really not found."""
    found = searches(result)
    return bool(found) and all(explain is not None and not explain.get("partial") for _, _, explain in found)


def rag_scores(result):
    """record id -> its RAG score, taken with its explanation (the first search that returned it);
    a record returned without a score is left out."""
    return {rid: item["rag_score"] for rid, item in explanations(result).items()
            if item.get("rag_score") is not None}


def list_ndcg(result, shown_ids):
    """(NDCG out of 100 or None, record id -> share, unknown) for the ads shown, in order. A shown ad
    without a score counts 0 only when every search kept its detail and none returned it; otherwise
    its score is unknown and no NDCG is given (unknown is True)."""
    returned, gains = explanations(result), rag_scores(result)
    unknown = any(rid not in gains and (rid in returned or not complete(result)) for rid in shown_ids)
    if unknown:
        return None, {}, True
    return (*ndcg(shown_ids, gains), False)


def ndcg(order, scores):
    """(NDCG out of 100, record id -> its share) for the ads in the order shown, each ad's RAG score
    as its gain (0 for an ad the searches did not return); the shares add up to the total.
    (None, {}) when no ad has a score."""
    ids = list(dict.fromkeys(order))
    gains = [float(scores.get(rid) or 0) for rid in ids]
    ideal = sum(gain / math.log2(place + 1) for place, gain in enumerate(sorted(gains, reverse=True), 1))
    if ideal <= 0:
        return None, {}
    shares = {rid: 100 * gain / math.log2(place + 1) / ideal
              for place, (rid, gain) in enumerate(zip(ids, gains), 1) if gain > 0}
    return sum(shares.values()), shares


def explanations(result):
    """record id -> its retrieval explanation: one passage's RAG score and, when kept, its routes. A
    record found by several searches takes the first search's (the order shown in the account); the
    explanation names that search."""
    found = searches(result)
    out, several = {}, len(found) > 1
    for label, _, explain in found:
        for rid, item in (explain or {}).get("records", {}).items():
            out.setdefault(rid, {**item, "search": label if several else None})
    return out
