"""What an answer's two scores are based on, listed as plain elements (no formulas).

explain_block goes under the answer's first sentence ("Found 3 matching ads among the
15…"): each search's words and the ways it used, and on list answers what the accuracy
score was judged from. retrieval_lines go on each cited ad: the words each way matched,
the similarity and the ad's place in each way. Both open on a click; the scores stay in view.
"""

from __future__ import annotations

from dash import html

from .relevance_judge import JUDGE_MODEL, MAX_AD_CHARS
from .retrieval_explain import ROUTE_NAMES, searches

COLLECTIONS = {"native": "native ads", "social": "social posts"}


def _words(items):
    return ", ".join(items) if items else "none"


def retrieval_badge(explained):
    """The ad's share of the list's NDCG (not an NDCG of its own)."""
    if explained is None or explained.get("ndcg") is None:
        return None
    return html.Span(f"NDCG share {explained['ndcg']:.1f} of {explained['ndcg_total']:.1f}",
                     className="relevance-score retrieval-score")


def retrieval_lines(explained, read_without_search=False):
    """What each way matched in this ad and where it placed it."""
    if explained is None:
        text = ("The search did not place this ad; it was read because every ad in the selection is read."
                if read_without_search else "No search detail was recorded for this ad.")
        return html.P(text, className="related-to scope-note")
    items = []
    if explained.get("rag_score") is not None:
        place = f", shown at place {explained['shown_at']}" if explained.get("shown_at") else ""
        items.append(html.Li(f"RAG score {explained['rag_score']:.4f}{place}"))
    if not explained.get("run"):
        items.append(html.Li("Which words or ways found this ad was not recorded.", className="scope-note"))
    for part in explained.get("parts") or []:
        if part["route"] in ("keyword", "title"):
            found = f": {_words(part.get('terms'))}"
        elif part["route"] == "vector" and part.get("similarity") is not None:
            found = f": similarity {part['similarity']:.2f}"
        else:
            found = ""
        items.append(html.Li(f"{ROUTE_NAMES[part['route']]}{found} — place {part['place']}"))
    items += [html.Li(f"{ROUTE_NAMES[route]}: not returned by this way", className="scope-note")
              for route in explained.get("missed") or []]
    if explained.get("changed"):
        items.append(html.Li("This ad's text has changed since the answer was saved.", className="scope-note"))
    source = f" for “{explained['search']}”" if explained.get("search") else ""
    return html.Details([html.Summary(f"Matched by the search{source}"), html.Ul(items)], className="related-to")


def _ways(explain):
    runs = explain["runs"]
    if len(runs) == 1:
        return _words([ROUTE_NAMES[route] for route in next(iter(runs.values()))])
    return "; ".join(f"{COLLECTIONS.get(dataset, dataset)}: {_words([ROUTE_NAMES[r] for r in run])}"
                     for dataset, run in runs.items())


def _search_items(question, query, explain):
    items = []
    if query and query.strip() != question.strip():
        items.append(html.Li(f"Search wording, written from your question: “{query}”"))
    if explain is None:
        return items + [html.Li("No search detail was recorded for this search.")]
    if not explain["records"]:
        return items + [html.Li("This search found no ads.")]
    if not explain["runs"]:
        return items + [html.Li("This search's words and ways were not recorded; its RAG scores were.")]
    items.append(html.Li("Search words: " + _words([t for t in explain["terms"] if t not in explain["unindexed"]])))
    common = [*explain["dropped"], *explain["unindexed"]]
    if common:
        items.append(html.Li("Left out (too common or one letter): " + _words(common)))
    if explain.get("cut"):
        items.append(html.Li("Not used for word and title matching (only the first 40 words are): "
                             + _words(explain["cut"])))
    return items + [html.Li("Ways used: " + _ways(explain))]


def explain_block(result, screening=None, whole_scope=None, ndcg_total=None, ndcg_unknown=False):
    """The elements behind one answer's scores; None when there is neither a search nor list rules."""
    screening = screening or {}
    found = searches(result)
    listed = bool(screening.get("criterion"))
    if not found and not listed:
        return None
    question = (result.get("research_trace") or {}).get("original_question") or ""
    if len(found) == 1:
        items = _search_items(question, found[0][1], found[0][2])
    else:
        items = [html.Li([html.Strong(f"Search “{label}”"), html.Ul(_search_items(question, query, explain))])
                 for label, query, explain in found]
    kept = [explain for _, _, explain in found if explain is not None]
    if any(explain["records"] for explain in kept):
        if ndcg_unknown:
            items.append(html.Li("NDCG score: not computed, as some shown ads have no recorded RAG score."))
        else:
            items.append(html.Li(
                "NDCG score"
                + (f" of this list: {ndcg_total:.1f}/100. It" if ndcg_total is not None else ": it")
                + " compares the order the ads are shown in with the same ads ordered by their RAG scores. Each "
                "ad shows its RAG score (from the words matched in its text and title, its similarity in meaning "
                "and its place in each way), the place it is shown at and its share of the list's NDCG."))
    elif found and len(kept) == len(found):
        items.append(html.Li("NDCG score: none, as the search returned no ads."))
    elif kept:
        items.append(html.Li("NDCG score: none, as the searches returned no ads or kept no detail."))
    else:
        items.append(html.Li("NDCG score: not shown, as no search detail was recorded."))
    if listed:
        items.append(html.Li(f"Accuracy score: {JUDGE_MODEL}'s judgment of each ad's text (first "
                             f"{MAX_AD_CHARS:,} characters) against the rules under “What counts for this "
                             "question” (shown on each ad as “Related to”)."))
        if whole_scope:
            items.append(html.Li(f"Ads read: {whole_scope[0]} of {whole_scope[1]} in this selection."))
        items.append(html.Li("Your check: under each listed ad you can mark it right or wrong for the question; "
                             "the choice is saved and changes neither the answer nor the scores."))
    else:
        items.append(html.Li("Accuracy score: not assessed for this kind of question."))
    notes = []
    recomputed = [explain for _, _, explain in found if explain and explain.get("recomputed")]
    if recomputed:
        notes.append(html.P(f"Retrieval details were recomputed on today's collection "
                            f"({recomputed[0]['recomputed']}); accuracy scores and the answer are from the saved run.",
                            className="scope-note"))
    return html.Details([html.Summary("What the scores are based on"), html.Ul(items, className="score-steps"),
                         *notes], className="score-method")
