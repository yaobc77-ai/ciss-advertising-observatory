"""RAG evaluation disclosure (free, offline): each test question's real verdicts and relevance rule,
P/R/F1 on the final list, and P@K/R@K/F1@K/MRR/NDCG on the order.

Reads saved runs only: no model calls, no database, writes only --out. Each test set keeps its own truth
and is never pooled with another:

  human    5 label questions x 15 hand-coded native ads (the research team's labels, not the customer's
           questions); an ad is relevant to a label when the coder marked at least one of its sentences.
  keyword  B1K synthetic "which ads mention X" questions; relevant = the ad's stored passages in the run's
           snapshot match the question's keyword rule (case-insensitive) and the ad is in its scope.
  frame    B1K synthetic framing questions; relevant = positive in the frozen reference ref_v2 (AI
           annotation + AI adjudication); disputed and neutral ads have no label and count neither way.
  content  B1K questions written from known source ads; relevant = those ads (known-source retrieval).

Orders, named by where they come from. B1K list questions and the 10-23 human run: the screening's read order
("read"); a matched ad's recorded search rank equals its read position (checked per run), which is evidence for
the matched ads only, so these are read-order scores, not search-ranking scores. The 10-24 and 10-28 human runs
rank by the judge's probability ("judge"); their saved order is close to it but not exactly it, so their decisions
are sorted by it here, highest first. Content questions: the answer's evidence list. The
10-29 depth run ranked every searchable ad with that day's search; only the 15 coded ads have labels, so it is
scored twice under different names: "full_rank" over every ranked ad (an uncoded ad counts as not relevant, so
its RR and P@k can only be too low, while its NDCG and R@k hold only under that assumption) and "condensed" over the
coded ads only.

List questions also get a read funnel over their relevant ads, taken from the screening's saved read record: how many
were among its first 10 and first 40 places, how many it holds at all (these three only grow: they are cumulative
read coverage), and how many ended on the final list. The record does not say why a screening read on or stopped.
Every screened answer records first_read = 40, the first batch it meant to read; first_batch() checks each record
against it. A list question wants every relevant ad, so the funnel, not MRR or an NDCG over 120 places, is the main
ranking view of a list question; those stay in metrics.json.

An answer that read or retrieved nothing scores 0 where the question has relevant ads. An expected question
without a saved answer is listed as missing, and each summary says how many questions it covers.

    .venv/Scripts/python -X utf8 scripts/rag_metrics_report.py --out reports/rag_metrics_20261029
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import re
import re._parser as sre_parse
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B1K = ROOT / ".runtime/rag_eval_test_20261008"
VAL = ROOT / ".runtime/rag_validation_20261023"
S3E = ROOT / ".runtime/s3e_20261028"
DEPTH = ROOT / ".runtime/decisions_depth_demo/result.json"
LABELS = ROOT / "sources/Native Advertising Data/handcoded_labels.csv"
SHIPPED = ROOT / "src/observatory/relevance_validation.v1.json"
# run name -> (run folder, question set); the screening version and dates are read from the runs
RUNS = {"R": ("root_b1kr", "new3"), "U": ("root_b1ku", "new4"), "vA": ("root_b1kv_A", "new5"),
        "vB": ("root_b1kv_B", "new5"), "wA1": ("root_b1kw_A1", "new6"), "wA2": ("root_b1kw_A2", "new6"),
        "wB1": ("root_b1kw_B1", "new6"), "wB2": ("root_b1kw_B2", "new6")}
HEADLINE = ("wB1", "wB2")  # the newest screening version among the B1K runs (two passes of new6)
LIST_KS, HUMAN_KS, CONTENT_KS, DEPTH_KS = (10, 120), (10, 15), (1, 5, 10), (10, 15, 40, 120)
FUNNEL_KS = (10, 40)  # the first 10 the screening read, and the first 40, which it always reads (first_read)
FORM_LIMIT = 32
TITLE_CLASSES = {"title_lookup", "disclosure_by_title"}
SHOWN_FIELD = {"publisher": "publisher", "sponsor": "sponsor", "date": "publication_date",
               "disclosure_head": "disclosure_language"}  # expected field -> the field the answer shows
FRAME_PREFIX = "The ad does this: "
# The scorer of the time (each run folder's score_b1k.py) asked an AI adjudicator about each listed ad outside the
# truth; author.call cached each answer under a hash of the request, so the answer it used can be read back.
ADJUDICATE_MODEL = "gpt-5.6-luna"
ADJUDICATE_SYSTEM = ("You check one native advertisement against one criterion for a content-analysis study. Answer yes only "
                     "if a passage of the ad's own text satisfies the criterion, and copy that passage exactly (at least 12 "
                     "characters). Otherwise no.")
ADJUDICATE_SCHEMA = {"properties": {"quote": {"title": "Quote", "type": "string"},
                                    "verdict": {"enum": ["yes", "no"], "title": "Verdict", "type": "string"}},
                     "required": ["verdict", "quote"], "title": "Adj", "type": "object"}


# ---------- metrics ----------

def set_metrics(listed, relevant, unknown=frozenset()):
    """Scores of a final list. A listed ad without a label (unknown) counts neither way."""
    listed, relevant = set(listed), set(relevant)
    judged = listed - set(unknown)
    tp, fp, fn = len(judged & relevant), len(judged - relevant), len(relevant - listed)
    return {"tp": tp, "fp": fp, "fn": fn, "unlabelled_listed": len(listed - judged),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / len(relevant) if relevant else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def order_metrics(order, relevant, ks, unknown=frozenset()):
    """Scores of an order (best first); relevant ads that are not in it count as not found, so an empty order scores 0.
    None without truth."""
    relevant = set(relevant)
    if not relevant:
        return None
    first = next((i for i, rid in enumerate(order, 1) if rid in relevant), None)
    out = {"rr": 1 / first if first else 0.0, "first_relevant": first}
    for k in ks:
        top = order[:k]
        hits = sum(1 for rid in top if rid in relevant)
        p, r = hits / k, hits / len(relevant)
        dcg = sum(1 / math.log2(i + 1) for i, rid in enumerate(top, 1) if rid in relevant)
        ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
        # p@k divides by k, so a question with fewer than k relevant ads cannot reach 1: pmax@k says how high it can go
        out.update({f"p@{k}": p, f"pmax@{k}": min(k, len(relevant)) / k, f"r@{k}": r,
                    f"f1@{k}": 2 * p * r / (p + r) if p + r else 0.0, f"ndcg@{k}": dcg / ideal,
                    f"hit@{k}": 1.0 if first and first <= k else 0.0,
                    f"unlabelled@{k}": sum(1 for rid in top if rid in unknown)})
    return out


def read_funnel(order, relevant, listed, ks=FUNNEL_KS):
    """Where a list question's relevant ads drop out: among the first k ads the screening read (each k in ks, every
    read ad keeping its place, labelled or not), read at all, and on the final list. Only relevant ads are counted.
    The read and the listed relevant ads are compared as sets: read but not listed, and listed but not in the
    screening's read record (the answer came by another route; that does not mean no other tool read it)."""
    relevant, listed = set(relevant), set(listed)
    place = {rid: i for i, rid in enumerate(order, 1)}
    read, kept = relevant & set(place), relevant & listed
    out = {"relevant": len(relevant)}
    out.update({f"first_{k}": sum(1 for rid in relevant if place.get(rid, k + 1) <= k) for k in ks})
    out.update({"read": len(read), "listed": len(kept), "read_not_listed": len(read - kept),
                "listed_not_read": len(kept - read)})
    return out


def pooled_funnel(rows):
    """The funnel of several questions: each stage's count added up, and as a share of the relevant ads."""
    funnels = [r["funnel"] for r in rows]
    total = {key: sum(f[key] for f in funnels) for key in funnels[0]}
    return {**total, "rates": {key: n / total["relevant"] if total["relevant"] else None
                               for key, n in total.items() if key != "relevant"}}


def disagreement(label, listed):
    """How an ad's place in the final list disagrees with its label: "missed", "wrong" or None. Only explicit labels
    disagree: an ad that is disputed, neutral, unlabelled, or merely not a known source ("other") never does."""
    if label == "relevant" and not listed:
        return "missed"
    if label == "not_relevant" and listed:
        return "wrong"
    return None


def micro(rows):
    """Pooled final-list scores over questions (empty-truth questions add their wrong listings)."""
    tp, fp, fn = (sum(r["final"][key] for r in rows) for key in ("tp", "fp", "fn"))
    return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None, "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None}


def mean(values):
    values = [v for v in values if v is not None]
    return {"mean": sum(values) / len(values) if values else None, "n": len(values)}


def summarize(rows, ks, missing=()):
    """One run's numbers for one test set: final list (micro, and macro over questions that have relevant ads and
    where the score is defined) and the order (means over questions that have relevant ads, an empty order scoring
    0). Expected questions without a saved answer (missing) are listed and set the coverage."""
    truth = [r for r in rows if r["n_relevant"]]
    finals = [r for r in rows if r.get("final")]  # content questions have a source to find, not a list
    expected = len(rows) + len(missing)
    out = {"questions": len(rows), "expected": expected, "missing": sorted(missing),
           "coverage": len(rows) / expected if expected else None,
           "with_truth": len(truth), "empty_truth": len(rows) - len(truth),
           "empty_truth_correct": sum(1 for r in rows if not r["n_relevant"] and not r["n_listed"]),
           "empty_order": sum(1 for r in truth if r.get("n_read") == 0),  # read or retrieved nothing: scored 0
           "final_micro": micro(finals) if finals else None,
           "final_macro": {key: mean(r["final"][key] for r in finals if r["n_relevant"])
                           for key in ("precision", "recall", "f1")} if finals else None}
    # keyword questions also scored on the frozen reference (AI-accepted synonyms count neither way) and the
    # way the scorer of the time did (they count as relevant)
    for basis in ("final_reference", "final_old_scorer"):
        alternative = [r for r in finals if r.get(basis)]
        if alternative:
            out[f"{basis}_micro"] = micro([{"final": r[basis]} for r in alternative])
            out[f"{basis}_macro"] = {key: mean(r[basis][key] for r in alternative if r["n_relevant"])
                                     for key in ("precision", "recall", "f1")}
    keys = ["rr"] + [f"{m}@{k}" for k in ks for m in ("p", "pmax", "r", "f1", "ndcg", "hit")]
    out["order_mean"] = {key: mean(r["order"][key] for r in truth) for key in keys}
    reference = Counter()
    for r in finals:
        reference.update(r["final"].get("fp_by_reference") or {})
    if reference:  # keyword questions: what the frozen reference says about ads listed without the keyword
        out["wrong_listings_by_reference"] = dict(sorted(reference.items()))
    found = {k: sum(round(r["order"][f"r@{k}"] * r["n_relevant"]) for r in truth) for k in ks}
    out["pooled_recall"] = {f"r@{k}": found[k] / sum(r["n_relevant"] for r in truth) if truth else None for k in ks}
    if rows and all(r.get("funnel") for r in rows):  # list questions
        out["funnel"] = pooled_funnel(rows)
        # its last stage is the final list's: the relevant ads listed are the true positives
        assert out["funnel"]["listed"] == out["final_micro"]["tp"], "funnel and final list disagree"
        out["max_read"] = max(r["n_read"] for r in rows)
        if out["max_read"] <= ks[-1] and truth:  # then every read ad is inside the top ks[-1] of the order
            assert out["funnel"]["read"] == found[ks[-1]], "funnel and pooled recall disagree"
    return out


# ---------- the keyword rule in words ----------

def _expand(tokens):
    """Every string a parsed pattern accepts, exactly ("#" stands for one digit), or None when that is not a small
    finite set of exact strings: open-ended repeats (+, *), whitespace classes (\\s also takes tabs and newlines),
    word classes, ranges, boundaries and anchors all give None."""
    out = [""]
    for op, arg in tokens:
        name = str(op)
        if name == "LITERAL":
            parts = [chr(arg)]
        elif name == "SUBPATTERN":
            parts = _expand(arg[-1])
        elif name == "BRANCH":
            parts = []
            for branch in arg[1]:
                got = _expand(branch)
                if got is None:
                    return None
                parts += got
        elif name == "IN":
            parts = _class_chars(arg)
        elif name in ("MAX_REPEAT", "MIN_REPEAT"):
            low, high, sub = arg
            base = _expand(sub)
            if base is None or str(high) == "MAXREPEAT" or high > 3:
                return None
            parts = sorted({"".join(c) for n in range(low, high + 1) for c in _product(base, n)})
        else:
            return None
        if parts is None:
            return None
        out = [a + b for a in out for b in parts]
        if len(out) > FORM_LIMIT:
            return None
    return out


def _class_chars(items):
    """The characters a set like [- ] or \\d accepts, or None when it is not a few literal characters or digits."""
    chars = []
    for kind, value in items:
        if str(kind) == "LITERAL":
            chars.append(chr(value))
        elif str(kind) == "CATEGORY" and str(value) == "CATEGORY_DIGIT":
            chars.append("#")
        else:
            return None
    return sorted(set(chars))


def _product(base, n):
    if n == 0:
        return [()]
    return [(b,) + rest for b in base for rest in _product(base, n - 1)]


def _alternatives(rule):
    """The rule's top-level alternatives as written: split at each '|' outside groups and character sets.

    (The parser cannot give them: it moves a prefix every alternative shares, such as \\b, in front of them.)"""
    parts, depth, in_set, start, i = [], 0, False, 0, 0
    while i < len(rule):
        char = rule[i]
        if char == "\\":
            i += 2
            continue
        if in_set:
            in_set = char != "]"
        elif char == "[":
            in_set = True
        elif char in "()":
            depth += 1 if char == "(" else -1
        elif char == "|" and depth == 0:
            parts.append(rule[start:i])
            start = i + 1
        i += 1
    return parts + [rule[start:]]


def _is_boundary(token):
    return str(token[0]) == "AT" and str(token[1]) == "AT_BOUNDARY"


def keyword_forms(rule):
    """The rule spelled out: one entry per alternative with its exact word forms and whether it must be a whole word
    (\\b on both ends). None when an alternative is not a small finite set of exact forms, or has a boundary on one end
    only or inside it: then only the raw rule says what matches, and it is always kept beside this."""
    out = []
    for alternative in _alternatives(rule):
        tokens = list(sre_parse.parse(alternative, re.I))
        bounded = len(tokens) > 2 and _is_boundary(tokens[0]) and _is_boundary(tokens[-1])
        forms = _expand(tokens[1:-1] if bounded else tokens)
        if forms is None:
            return None
        out.append({"forms": sorted(dict.fromkeys(f for f in forms if f), key=str.lower), "whole_word": bounded})
    return out


def matched_forms(rule, text, top=6):
    """The forms of the rule that occur in a text, most frequent first: [[form, count], ...]."""
    found = Counter(m.group(0).lower() for m in re.finditer(rule, text or "", re.I))
    return [[form, n] for form, n in found.most_common(top)]


def scope_words(scope):
    def names(value):
        return "、".join(value) if isinstance(value, list) else str(value)

    parts = []
    if scope.get("sponsor"):
        parts.append(f"赞助方 = {names(scope['sponsor'])}")
    if scope.get("not_sponsor"):
        parts.append(f"赞助方不是 {names(scope['not_sponsor'])}")
    if scope.get("publisher"):
        parts.append(f"媒体 = {scope['publisher']}")
    if scope.get("years"):
        parts.append(f"发布年份 {scope['years'][0]}–{scope['years'][1]}（无日期的不算）")
    if scope.get("from"):
        parts.append(f"{scope['from']} 年及以后发布（无日期的不算）")
    if scope.get("before"):
        parts.append(f"{scope['before']} 年以前发布（无日期的不算）")
    return "；".join(parts) or "全部可检索的原生广告"


def in_scope(ad, scope):
    """The generator's scope test (root_b1k/gen.py truth_t1 and in_scope)."""
    year = int(ad["date"][:4]) if ad.get("date") else None
    sponsors = scope.get("sponsor")
    sponsors = [sponsors] if isinstance(sponsors, str) else sponsors
    years = scope.get("years")
    return ((not sponsors or ad["sponsor"] in sponsors)
            and (not scope.get("not_sponsor") or ad["sponsor"] not in scope["not_sponsor"])
            and (not scope.get("publisher") or ad["publisher"] == scope["publisher"])
            and (not years or (year is not None and years[0] <= year <= years[1]))
            and (not scope.get("before") or (year is not None and year < scope["before"]))
            and (not scope.get("from") or (year is not None and year >= scope["from"])))


# ---------- the scorer of the time ----------

def _norm(text):
    """author.norm of the run folders: the text a quote must be found in, normalized the same way."""
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'").replace("“", '"')
    text = text.replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().casefold()


def scoring_time_verdict(folder, criterion, ad):
    """What the scorer of the time decided about one ad for one criterion, read from that run folder's cache:
    {"verdict", "quote", "accepted", "cache"} (accepted: a yes whose quote is in the ad's text, as score_b1k.py
    required; cache: the file it came from, relative to the B1K folder), or None when that run never asked."""
    text = "\n".join(ad["chunks"])
    user = f"Criterion: {criterion}\n\nAd title: {ad['title']}\n{text}"
    key = hashlib.sha256(json.dumps(["adjudicate", ADJUDICATE_MODEL, "high", ADJUDICATE_SYSTEM, user, ADJUDICATE_SCHEMA],
                                    sort_keys=True).encode()).hexdigest()
    path = B1K / folder / "cache" / f"adjudicate-{key[:24]}.json"
    if not path.exists():
        return None
    got = json.load(open(path, encoding="utf-8"))["parsed"]
    quote = got["quote"]
    return {"verdict": got["verdict"], "quote": quote,
            "accepted": got["verdict"] == "yes" and len(quote.strip()) >= 12 and _norm(quote) in _norm(text),
            "cache": path.relative_to(B1K).as_posix()}


def old_scorer_counts(listed, positive, neutral=frozenset()):
    """A keyword question scored the way score_b1k.py did: neutral ads leave the judged list, and a question with
    nothing to find or nothing judged scores 1 or 0 instead of having no score."""
    listed, positive = set(listed), set(positive)
    judged = listed - set(neutral)
    tp, judged_tp = len(listed & positive), len(judged & positive)
    precision = judged_tp / len(judged) if judged else (1.0 if not positive else 0.0)
    recall = tp / len(positive) if positive else (1.0 if not judged else 0.0)
    return {"tp": tp, "fp": len(judged - positive), "fn": len(positive - listed), "n_pos": len(positive),
            "n_judged_cited": len(judged), "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def old_scorer_differences(got, old):
    """The old scorer's per-question keyword numbers this report does not reproduce ([] when all of them match)."""
    out = [key for key in ("tp", "n_pos", "n_judged_cited") if got[key] != old.get(key)]
    return out + [key for key in ("precision", "recall")
                  if not isinstance(old.get(key), (int, float)) or abs(got[key] - old[key]) > 1e-9]


# ---------- reading saved runs ----------

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def latest_answers(run_dir):
    """query id -> (answered at, result): the last answer each question got in one run."""
    latest = {}
    files = sorted(glob.glob(str(run_dir / "shards/*/server/events.jsonl")) + glob.glob(str(run_dir / "server/events.jsonl")))
    for name in files:
        for line in open(name, encoding="utf-8"):
            event = json.loads(line)
            if event.get("kind") != "answer_result":
                continue
            at = event.get("at_utc") or ""
            if event["query_id"] not in latest or at > latest[event["query_id"]][0]:
                latest[event["query_id"]] = (at, event["result"])
    return latest, files


def cited_ids(result):
    """The ads the answer lists: the records its citations point to (as the B1K scorer counted them)."""
    by_evidence = {e["evidence_id"]: e["record_id"] for e in (result.get("evidence") or []) + (result.get("media_evidence") or [])}
    return {by_evidence[c["evidence_id"]] for c in result.get("citations") or [] if c.get("evidence_id") in by_evidence}


def searches(result):
    """The search sentences the answer's tools ran, in order."""
    tools = (result.get("research_trace") or {}).get("tools") or []
    return list(dict.fromkeys(t["arguments"]["query"] for t in tools
                              if isinstance(t, dict) and (t.get("arguments") or {}).get("query")))


def read_order(result):
    """The screening's decisions in read order (record ids, each once) and each ad's verdict."""
    decisions = ((result.get("research_trace") or {}).get("list_screening") or {}).get("decisions") or []
    order = list(dict.fromkeys(d["record_id"] for d in decisions))
    return order, {d["record_id"]: d for d in decisions}


def judge_order(order, verdicts, relevant=frozenset()):
    """(order, how far the saved order was from it): the ads by the judge's probability that they meet the
    criterion, highest first; ties, and ads without a probability (put last), keep their saved order. "inversions"
    counts the pairs the saved order puts the other way round and "across_labels" those of them between a relevant
    and a not-relevant ad; "labels_moved" says whether sorting changed which places hold a relevant ad, the only
    change a score on a relevant/not-relevant order can see."""
    def meets(rid):
        value = (verdicts[rid].get("triage") or {}).get("meets")
        return value if isinstance(value, (int, float)) else None

    ranked = sorted(order, key=lambda rid: (meets(rid) is None, -(meets(rid) or 0.0)))
    known = [(meets(rid), rid in relevant) for rid in order if meets(rid) is not None]
    reversed_pairs = [(a, b) for i, a in enumerate(known) for b in known[i + 1:] if a[0] < b[0]]
    return ranked, {"inversions": len(reversed_pairs), "across_labels": sum(1 for a, b in reversed_pairs if a[1] != b[1]),
                    "without_probability": len(order) - len(known),
                    "labels_moved": [rid in relevant for rid in order] != [rid in relevant for rid in ranked]}


def order_check(result, order):
    """(matched ads with a recorded rank, of them at that read position). Evidence that the screening read in search
    order, for the ads it matched only: the ranks of the ads it did not match are not kept the same way."""
    rank = {}
    for item in result.get("evidence") or []:
        if isinstance(item.get("retrieval_rank"), int):
            rank[item["record_id"]] = min(rank.get(item["record_id"], 10 ** 9), item["retrieval_rank"])
    _, verdicts = read_order(result)
    matched = [(i, rid) for i, rid in enumerate(order, 1) if verdicts[rid].get("decision") == "matches" and rid in rank]
    return len(matched), sum(1 for i, rid in matched if rank[rid] == i)


def kind_of(spec):
    """The test set a B1K question belongs to, or None for the kinds this report does not score."""
    if spec["task_type"] == "complete_list" and spec.get("list_truth") is not None:
        return "keyword" if spec["group"] == "T1" else "frame"
    if spec.get("source_record_ids"):
        return "title" if spec["query_class"] in TITLE_CLASSES else "content"
    return None


def reference_frames():
    """frame id -> its English definition, from each frame question's criterion in the frozen reference ref_v2: the
    sentence the AI adjudicator was given ("The ad does this: ..."), from the frame list the annotator also used."""
    frames = {}
    for qset in sorted({qset for _, qset in RUNS.values()}):
        specs = {e["query_id"]: e for e in json.load(open(B1K / f"dataset_b1k_{qset}/expected.json", encoding="utf-8"))}
        for q in json.load(open(B1K / f"ref_v2/ref_{qset}_v2.json", encoding="utf-8"))["questions"]:
            frame_id = specs[q["query_id"]].get("frame_id")
            if frame_id:
                assert q["criterion"].startswith(FRAME_PREFIX), q["query_id"]
                en = q["criterion"][len(FRAME_PREFIX):]
                assert frames.setdefault(frame_id, en) == en, frame_id  # one definition per frame
    return frames


def ad_brief(ad, rid):
    if not ad:
        return {"record_id": rid, "title": None}
    return {"record_id": rid, "title": (ad.get("title") or "").strip() or None, "sponsor": ad.get("sponsor"),
            "publisher": ad.get("publisher") or ad.get("account"), "date": ad.get("date")}


def b1k_list_row(name, spec, result, ads, searchable, frame_labels, ref_items, frames, with_ads, scoring_time=None):
    """One B1K list question in one run: its rule in words, its verdicts and its scores. scoring_time(record id) gives
    what the scorer of the time decided about a listed ad outside the truth (keyword questions)."""
    scope = spec.get("scope") or {}
    in_range = {rid for rid in searchable if in_scope(ads[rid], scope)}
    order, verdicts = read_order(result)
    listed = cited_ids(result)
    labels, why = {}, {}
    if spec["group"] == "T1":
        rule = spec["rule"]
        relevant = set(spec["list_truth"]["positive"])
        recomputed = {rid for rid in in_range if re.search(rule, ads[rid]["text"], re.I)}
        criterion = {"kind": "keyword", "rule": rule, "alternatives": keyword_forms(rule), "scope": scope,
                     "scope_words": scope_words(scope), "ads_in_scope": len(in_range),
                     "truth_matches_rule": recomputed == relevant}
        unknown = set()
        for rid in set(order) | listed | relevant:
            labels[rid] = "relevant" if rid in relevant else "not_relevant"
            ad = ads.get(rid)
            item = ref_items.get(rid) or {}  # beside the literal rule: what the AI adjudicator said, if asked
            why[rid] = {"forms": matched_forms(rule, ad["text"]) if ad else [],
                        "in_title": bool(ad and re.search(rule, ad.get("title") or "", re.I)),
                        "in_scope": rid in in_range, "reference": item.get("status"), "adjudicator": item.get("adjudicator"),
                        "adjudicator_quote": item.get("adjudicator_quote")}
        # the frozen reference (ref_v2) also accepts wording an AI adjudicator took for the keyword: "disputed" there
        disputed = {rid for rid, item in ref_items.items() if item.get("status") in ("disputed", "neutral")} - relevant
    else:
        frame = frames[spec["frame_id"]]
        annotations = {rid: ((frame_labels.get(rid) or {}).get(spec["frame_id"]) or {}).get("verdict") for rid in in_range}
        # one AI annotator read every searchable ad in scope against the frame (gen.py); no keyword pool narrows it
        criterion = {"kind": "frame", "frame_id": spec["frame_id"], "en": frame, "scope": scope,
                     "scope_words": scope_words(scope), "ads_in_scope": len(in_range),
                     "annotation_counts": dict(sorted(Counter(v or "missing" for v in annotations.values()).items()))}
        for rid in in_range | set(order) | listed:
            item = ref_items.get(rid)
            annotation = ((frame_labels.get(rid) or {}).get(spec["frame_id"]) or {}).get("verdict")
            if rid not in in_range:
                status = "not_relevant"
            elif item:
                status = {"positive": "relevant", "negative": "not_relevant"}.get(item["status"], item["status"])
            else:  # the reference only lists ads some run cited or the annotation accepted: one "no" decides
                status = {"yes": "relevant", "no": "not_relevant", "unclear": "neutral",
                          "unverified_yes": "neutral"}.get(annotation, "unlabelled")
            labels[rid] = status
            why[rid] = {"annotation": annotation, "adjudicator": (item or {}).get("adjudicator"),
                        "adjudicator_quote": (item or {}).get("adjudicator_quote"),
                        "reference": (item or {}).get("status"), "in_scope": rid in in_range}
        relevant = {rid for rid, s in labels.items() if s == "relevant"}
        unknown = {rid for rid, s in labels.items() if s in ("disputed", "neutral", "unlabelled")}
    trace = result.get("research_trace") or {}
    row = {"query_id": spec["query_id"], "run": name, "group": spec["group"], "class": spec["query_class"],
           "question": spec["question"], "status": result.get("status"), "criterion": criterion,
           "searches": searches(result), "n_relevant": len(relevant), "n_listed": len(listed),
           "n_read": len(order), "in_scope_not_read": len(in_range - set(order)),
           "read_outside_scope": len(set(order) - in_range),
           "screened": bool(trace.get("list_screening")), "route": trace.get("route"),
           "scope_total": (trace.get("list_screening") or {}).get("scope_total"),
           "first_read": (trace.get("list_screening") or {}).get("first_read"),
           "final": set_metrics(listed, relevant, unknown), "funnel": read_funnel(order, relevant, listed),
           "order": order_metrics(order, relevant, LIST_KS, unknown), "order_kind": "read"}
    if spec["group"] == "T1":
        row["final"]["fp_by_reference"] = dict(sorted(Counter(why[rid]["reference"] or "not_reviewed"
                                                              for rid in listed - relevant).items()))
        row["final_reference"] = set_metrics(listed, relevant, disputed)
        # the scorer of the time (score_b1k.py) added each listed ad its adjudicator accepted to the truth
        neutral = set(spec["list_truth"].get("neutral") or [])
        asked = {rid: scoring_time(rid) if scoring_time else None
                 for rid in sorted(listed - relevant - neutral) if (ads.get(rid) or {}).get("chunks")}
        added = {rid for rid, verdict in asked.items() if verdict and verdict["accepted"]}
        row["final_old_scorer"] = old_scorer_counts(listed, relevant | added, neutral)
        # where that differs from the frozen reference's adjudicator, the two bases disagree about the ad
        row["adjudication_changed"] = [
            {"record_id": rid, "title": ad_brief(ads.get(rid), rid)["title"], "then": verdict,
             "reference": (ref_items.get(rid) or {}).get("status"),
             "reference_adjudicator": (ref_items.get(rid) or {}).get("adjudicator"),
             "reference_quote": (ref_items.get(rid) or {}).get("adjudicator_quote")}
            for rid, verdict in asked.items()
            if bool(verdict and verdict["accepted"]) != ((ref_items.get(rid) or {}).get("adjudicator") == "yes")]
    if with_ads:
        position = {rid: i for i, rid in enumerate(order, 1)}
        rows = []
        for rid in sorted(labels, key=lambda r: (position.get(r, 10 ** 6), r)):
            if rid not in position and rid not in listed and labels[rid] != "relevant":
                continue  # an unread, unlisted ad that is not relevant says nothing about this answer
            decision = verdicts.get(rid) or {}
            rows.append({**ad_brief(ads.get(rid), rid), "label": labels[rid], "why": why[rid],
                         "position": position.get(rid), "verdict": decision.get("decision"),
                         "quote": decision.get("quote"), "listed": rid in listed,
                         "disagreement": disagreement(labels[rid], rid in listed)})
        row["ads"] = rows
    return row


def b1k_content_row(name, spec, result, ads, with_ads):
    """One B1K question written from known source ads: did the search place the source, did the answer cite it."""
    gold = set(spec["source_record_ids"])
    order = list(dict.fromkeys(e["record_id"] for e in result.get("evidence") or [] if e.get("record_id")))
    cited = cited_ids(result)
    criterion = {"kind": "source", "sources": [ad_brief(ads.get(rid), rid) for rid in spec["source_record_ids"]],
                 "quotes": spec.get("quotes") or [], "required_points": spec.get("required_points") or []}
    row = {"query_id": spec["query_id"], "run": name, "group": spec["group"], "class": spec["query_class"],
           "question": spec["question"], "status": result.get("status"), "criterion": criterion,
           "searches": searches(result), "n_relevant": len(gold), "n_listed": len(cited), "n_read": len(order),
           "evidence_records": len(order), "sources_cited": len(gold & cited),
           "order": order_metrics(order, gold, CONTENT_KS), "order_kind": "evidence"}
    if with_ads:
        rows = [{**ad_brief(ads.get(rid), rid), "label": "relevant" if rid in gold else "other", "position": i,
                 "cited": rid in cited} for i, rid in enumerate(order[:10], 1)]
        rows += [{**ad_brief(ads.get(rid), rid), "label": "relevant", "cited": rid in cited,  # a source placed lower
                  "position": order.index(rid) + 1 if rid in order else None}
                 for rid in spec["source_record_ids"] if rid not in order[:10]]
        for item in rows:  # a cited ad that is not a known source is not a wrong citation
            item["disagreement"] = disagreement(item["label"], item["cited"])
        row["ads"] = rows
    return row


def field_match(key, expected, shown):
    """An expected field value against the value the answer showed (case and spacing ignored)."""
    if shown is None:
        return False
    want, got = (" ".join(str(v).split()).casefold() for v in (expected, shown))
    if key == "date":
        return got[:10] == want[:10]
    if key == "disclosure_head":  # the label's opening words, inside the stored disclosure sentence
        return want in got
    return got == want


def b1k_title_row(name, spec, result, ads):
    """One B1K question that names an ad by its title: did the title lookup find that ad, were its fields right."""
    gold = set(spec["source_record_ids"])
    tools = (result.get("research_trace") or {}).get("tools") or []
    lookups = [t for t in tools if t.get("tool") == "find_records"]
    order = list(dict.fromkeys(ref["record_id"] for t in lookups for ref in t.get("data_refs") or []))
    selected = [rid for rid in ((t.get("selected_record") or {}).get("record_id") for t in lookups) if rid]
    searched = [(t.get("arguments") or {}).get("title") for t in lookups]
    stored = [(ads.get(rid) or {}).get("title") or "" for rid in spec["source_record_ids"]]
    shown = (result.get("structured_result") or {}).get("display_fields") or {}
    answer = result.get("answer") or ""
    expected = spec.get("field_truth") or spec.get("attr_truth") or {}
    fields = {}
    for key, value in expected.items():
        got = shown.get(SHOWN_FIELD[key])
        fields[key] = {"expected": value, "shown": got, "match": field_match(key, value, got),
                       "in_answer_text": str(value)[:10 if key == "date" else None].casefold() in answer.casefold()}
    same = {" ".join(t.split()).casefold() for t in stored}
    return {"query_id": spec["query_id"], "run": name, "group": spec["group"], "class": spec["query_class"],
            "question": spec["question"], "status": result.get("status"),
            "criterion": {"kind": "title", "titles": stored, "sources": [ad_brief(ads.get(rid), rid) for rid in spec["source_record_ids"]],
                          "expected_fields": expected},
            "title_searched": searched, "title_exact": bool(searched) and all(" ".join((t or "").split()).casefold() in same for t in searched),
            "selected": selected, "record_found": bool(gold & set(selected)), "fields": fields,
            "fields_correct": all(f["match"] for f in fields.values()) if fields else None, "answer": answer[:400],
            "n_relevant": len(gold), "n_listed": len(set(selected)), "n_read": len(order),
            "order": order_metrics(order, gold, CONTENT_KS), "order_kind": "lookup"}


def b1k(with_ads_for):
    """Every B1K run: list (keyword, frame) and content rows, per-run summaries, checks and provenance."""
    snapshot = B1K / "root_b1k/snap/native.json"
    ads = {r["record_id"]: {**r, "text": "\n".join(r["chunks"])} for r in json.load(open(snapshot, encoding="utf-8"))["native"]}
    searchable = {rid for rid, r in ads.items() if r["chunks"] and r["countable"] == "true"}
    frame_labels = json.load(open(B1K / "root_b1k/snap/frame_labels.json", encoding="utf-8"))
    frames = reference_frames()
    posts = {r["record_id"]: r for r in json.load(open(B1K / "root_b1k/snap/social_meta.json", encoding="utf-8"))}
    records = {**posts, **ads}  # content questions also come from social posts
    kinds = ("keyword", "frame", "content", "title")
    rows, missing, runs, provenance = {k: [] for k in kinds}, {k: [] for k in kinds}, [], {}
    for name, (folder, qset) in RUNS.items():
        expected = sorted(json.load(open(B1K / f"dataset_b1k_{qset}/expected.json", encoding="utf-8")), key=lambda e: e["query_id"])
        ref_path = B1K / f"ref_v2/ref_{qset}_v2.json"
        ref = {q["query_id"]: q for q in json.load(open(ref_path, encoding="utf-8"))["questions"]}
        answers, files = latest_answers(B1K / folder)
        stamps = sorted(at for at, _ in answers.values() if at)
        policies, data_versions, check, failed, asked, caches = Counter(), Counter(), [0, 0], Counter(), [0, 0], set()
        for spec in expected:
            kind, got = kind_of(spec), answers.get(spec["query_id"])
            if got is None:
                if kind:  # an expected question without a saved answer: listed, never scored
                    missing[kind].append({"run": name, "query_id": spec["query_id"], "question": spec["question"]})
                continue
            result = got[1]
            trace = result.get("research_trace") or {}
            data_versions[(trace.get("data_version") or "")[:16]] += 1
            policy = (trace.get("list_screening") or {}).get("policy")
            if policy:
                policies[policy] += 1
            with_ads = name in with_ads_for
            if kind in ("keyword", "frame"):
                q = ref.get(spec["query_id"]) or {}
                verdict_of = None
                if kind == "keyword":
                    def verdict_of(rid, criterion=q.get("criterion")):
                        verdict = scoring_time_verdict(folder, criterion, ads[rid])
                        asked[0], asked[1] = asked[0] + 1, asked[1] + (verdict is not None)
                        if verdict:
                            caches.add(verdict["cache"])
                        return verdict
                row = b1k_list_row(name, spec, result, ads, searchable, frame_labels, q.get("items") or {}, frames,
                                   with_ads, verdict_of)
                rows[kind].append(row)
                if row["n_read"]:
                    got_check = order_check(result, read_order(result)[0])
                    check = [check[0] + got_check[0], check[1] + got_check[1]]
            elif kind == "title":
                rows["title"].append(b1k_title_row(name, spec, result, records))
            elif kind == "content":
                rows["content"].append(b1k_content_row(name, spec, result, records, with_ads))
            if result.get("status") not in ("answered", "insufficient_evidence"):
                failed[result.get("status")] += 1
        runs.append({"run": name, "folder": folder, "question_set": qset, "answers": len(answers),
                     "expected_scored": sum(1 for e in expected if kind_of(e)),
                     "missing": sum(1 for k in kinds for m in missing[k] if m["run"] == name),
                     "from_utc": stamps[0] if stamps else None, "to_utc": stamps[-1] if stamps else None,
                     "screening_policy": dict(policies), "data_version": dict(data_versions),
                     "not_answered": dict(failed), "order_check": {"matched_with_rank": check[0], "rank_equals_position": check[1]},
                     "scoring_time_cache": {"asked": asked[0], "found": asked[1]}})
        provenance[name] = {"expected": sha256(B1K / f"dataset_b1k_{qset}/expected.json"), "reference": sha256(ref_path),
                            "events": {Path(f).relative_to(B1K).as_posix(): sha256(f) for f in files},
                            "old_scores": sha256(B1K / folder / f"scores_{qset}.json"),
                            "scoring_time_cache": {path: sha256(B1K / path) for path in sorted(caches)}}
    provenance["snapshot"] = {"native": sha256(snapshot), "frame_labels": sha256(B1K / "root_b1k/snap/frame_labels.json"),
                              "social_meta": sha256(B1K / "root_b1k/snap/social_meta.json"), "searchable_ads": len(searchable)}
    summaries = {}
    for kind, items in rows.items():
        ks = CONTENT_KS if kind in ("content", "title") else LIST_KS
        groups = {name: [r for r in items if r["run"] == name] for name in RUNS}
        groups["headline"] = [r for r in items if r["run"] in HEADLINE]
        lost = {name: [f"{m['run']}:{m['query_id']}" for m in missing[kind] if m["run"] == name] for name in RUNS}
        lost["headline"] = [x for name in HEADLINE for x in lost[name]]
        summaries[kind] = {name: {**summarize(group, ks, lost[name]), **kind_extras(kind, group)}
                           for name, group in groups.items()}
    return rows, summaries, runs, provenance, missing


def first_batch(rows):
    """Each screened answer's saved read record against the first batch it recorded (first_read). With at least that
    many searchable ads in scope, by the count only (the record cannot show they were the search's first ones); with
    fewer, by whether every one of them is in the record. Also how many records are longer than the batch, how many
    hold an ad outside the scope as this report counts it, and how many fall short against the run's own scope count
    (scope_total), which counts more ads than this report does."""
    screened = [r for r in rows if r["screened"]]
    target = [r for r in screened if r["first_read"] is not None]
    wide = [r for r in target if r["criterion"]["ads_in_scope"] >= r["first_read"]]
    narrow = [r for r in target if r["criterion"]["ads_in_scope"] < r["first_read"]]
    return {"screened": len(screened), "scope_at_least_target": len(wide),
            "read_target_count": sum(1 for r in wide if r["n_read"] >= r["first_read"]),
            "scope_below_target": len(narrow), "read_whole_scope": sum(1 for r in narrow if not r["in_scope_not_read"]),
            "read_on": sum(1 for r in target if r["n_read"] > r["first_read"]),
            "outside_scope_in_record": sum(1 for r in target if r["read_outside_scope"]),
            "below_run_scope_total": sum(1 for r in target if r["scope_total"] is not None
                                         and r["n_read"] < min(r["first_read"], r["scope_total"]))}


def kind_extras(kind, rows):
    """What one kind's summary adds beside summarize()."""
    if kind in ("keyword", "frame"):  # answered by another route: the screening read nothing, scored 0
        screened = [r for r in rows if r["screened"]]
        return {"not_screened": sorted(r["query_id"] for r in rows if not r["screened"]),
                "first_read": {str(k): v for k, v in sorted(Counter(r["first_read"] for r in screened).items(),
                                                            key=lambda kv: str(kv[0]))},
                "first_batch": first_batch(rows)}
    if kind == "content":  # beside whether the search placed the source: did the answer cite it
        return {"source_cited": mean(r["sources_cited"] / r["n_relevant"] for r in rows),
                "no_evidence_list": sum(1 for r in rows if not r["n_read"])}
    if kind == "title":  # a lookup, not a ranking: found the named ad, showed its fields right
        return {key: mean(float(r[key]) if r[key] is not None else None for r in rows)
                for key in ("record_found", "title_exact", "fields_correct")}
    return {}


# ---------- the human-coded set ----------

def human_truth():
    doc_map = json.load(open(VAL / "doc_map.json", encoding="utf-8"))
    docs = {int(k): v for k, v in doc_map.items() if v and v.get("retrievable")}
    by_record = {v["record_id"]: k for k, v in docs.items()}
    sentences = {}
    for row in csv.DictReader(open(LABELS, encoding="utf-8")):
        doc = int(row["doc_id"])
        if doc in docs:
            sentences.setdefault(doc, []).append(row)
    return docs, by_record, sentences


def label_truth(label, docs, sentences):
    """(relevant record ids, coded record ids) for one label question, from the hand codes alone: an ad is relevant
    when the coder marked at least one of its sentences for the label."""
    coded = {docs[d]["record_id"] for d in sentences}
    relevant = {docs[d]["record_id"] for d, rows in sentences.items() if any(r[label] in ("1", "1.0") for r in rows)}
    return relevant, coded


def human_answers():
    """(run -> label -> result, label -> the 10-28 criterion card): the 10-28 run is two blocks (a documented
    stop and its remainder); it searched while drafting the card, so its search sentence is on the card. Every
    saved answer counts, an empty one too (it scores 0); only a question with no saved answer is missing."""
    runs = {"h1023": {label: item["response"] for label, item in json.load(open(VAL / "results.json", encoding="utf-8")).items()},
            "h1024": json.load(open(VAL / "triage_answers.json", encoding="utf-8")), "h1028": {}}
    cards = {}
    for path in (S3E / "triage_confirmed_answers.json", S3E / "triage_confirmed_rest_answers.json"):
        for label, result in json.load(open(path, encoding="utf-8")).items():
            if label.endswith(".card"):
                cards[label[:-len(".card")]] = result
            else:
                assert label not in runs["h1028"], f"two 10-28 answers for {label}"  # the blocks never share a question
                runs["h1028"][label] = result
    return runs, cards


def human_rows(questions, docs, by_record, sentences):
    """(rows, missing): each label question in each human run with every coded ad's label, the coder's sentences and
    the verdicts; and the label questions a run has no saved answer for. An ad's "position" is its place in the
    scored order (the read order, or the judge's order for 10-24 and 10-28); "saved_position" its place among the
    saved decisions."""
    out, missing = [], []
    answers_by_run, cards = human_answers()
    for run, answers in answers_by_run.items():
        for label, question in questions.items():
            result = answers.get(label)
            if result is None:
                missing.append({"run": run, "label": label, "question": question})
                continue
            order, verdicts = read_order(result)
            relevant, coded = label_truth(label, docs, sentences)
            assert set(order) <= coded, f"{run}:{label} read an ad without hand codes"  # so not relevant is a label
            triage = run != "h1023"
            saved_at, judge = {rid: i for i, rid in enumerate(order, 1)}, None
            if triage:  # these runs rank by the judge's probability; the saved order is close to it, not exactly it
                order, judge = judge_order(order, verdicts, relevant)
            listed = ({rid for rid, d in verdicts.items() if d.get("route") == "pass"} if triage else cited_ids(result))
            flagged = {rid for rid, d in verdicts.items() if d.get("route") == "review"}
            ls = (result.get("research_trace") or {}).get("list_screening") or {}
            ads = []
            for i, rid in enumerate(order, 1):
                doc = by_record.get(rid)
                decision = verdicts[rid]
                coded = [r["sentence"] for r in sentences.get(doc, []) if r[label] in ("1", "1.0")]
                ad_label = "relevant" if rid in relevant else "not_relevant"
                ads.append({"doc": doc, "record_id": rid, "title": (docs.get(doc) or {}).get("title"),
                            "sponsor": (docs.get(doc) or {}).get("sponsor"), "publisher": (docs.get(doc) or {}).get("publisher"),
                            "label": ad_label, "coded_sentences": coded,
                            "position": i, "saved_position": saved_at[rid],
                            "verdict": decision.get("decision"), "route": decision.get("route"),
                            "meets": (decision.get("triage") or {}).get("meets"), "quote": decision.get("quote"),
                            "listed": rid in listed, "disagreement": disagreement(ad_label, rid in listed)})
            card = cards.get(label) or {}
            version = ((result.get("research_trace") or {}).get("data_version")
                       or (card.get("research_trace") or {}).get("data_version") or "")
            row = {"run": run, "label": label, "question": question, "status": result.get("status"),
                   "screening_policy": ls.get("policy"), "data_version": version[:16] or None,
                   "criterion": ls.get("criterion"), "searches": searches(result) or searches(card),
                   "n_relevant": len(relevant),
                   "n_listed": len(listed), "n_flagged": len(flagged), "n_read": len(order),
                   "final": set_metrics(listed, relevant),
                   "final_with_flagged": set_metrics(listed | flagged, relevant) if triage else None,
                   "groups": {route: [sum(1 for a in ads if a["route"] == route), sum(1 for a in ads if a["route"] == route and a["label"] == "relevant")]
                              for route in ("pass", "review", "exclude")} if triage else None,
                   "funnel": read_funnel(order, relevant, listed, ks=()),  # it reads all the coded ads it is given
                   "order": order_metrics(order, relevant, HUMAN_KS),
                   "order_kind": "judge" if triage else "read", "judge_order": judge, "ads": ads}
            if not triage:
                row["order_check"] = order_check(result, order)
            out.append(row)
    return out, missing


def depth_scores(ranked, relevant, coded):
    """One question's 10-29 ranking (record ids, best first) against the hand codes, scored two ways, named apart.
    A relevant ad the ranking left out counts as not found. "full_rank": every ranked ad in its place, an uncoded ad
    counting as not relevant (its RR and P@k can only be too low; its NDCG and R@k hold only under that
    assumption). "condensed": the coded ads only, in the same order."""
    unknown = set(ranked) - set(coded)
    return {"full_rank": order_metrics(list(ranked), relevant, DEPTH_KS, unknown),
            "condensed": order_metrics([rid for rid in ranked if rid in coded], relevant, HUMAN_KS)}


def depth_rows(by_record, truth):
    """The 10-29 depth run: where that day's search placed each coded ad among every searchable ad. The truth
    (label -> (relevant, coded) record ids) comes from the hand codes, not from the run's own copy of them; the
    run's copy is compared with it (flag_mismatch) and every coded ad is listed, ranked or not."""
    data = json.load(open(DEPTH, encoding="utf-8"))
    out = []
    for q in data["questions"]:
        ranked = sorted(q["ads"], key=lambda a: a["rank"])
        ids = [a["record_id"] for a in ranked]
        assert [a["rank"] for a in ranked] == list(range(1, len(ranked) + 1)), q["label"]  # a place is a rank
        assert len(set(ids)) == len(ids), f"an ad ranked twice for {q['label']}"
        relevant, coded = truth[q["label"]]
        place = {a["record_id"]: a for a in ranked}
        expected_flag = lambda rid: (rid in relevant) if rid in coded else None  # noqa: E731
        mismatch = sorted(a["record_id"] for a in ranked if a.get("human") != expected_flag(a["record_id"]))
        ranks = [{"doc": by_record.get(rid), "record_id": rid, "title": (place.get(rid) or {}).get("title"),
                  "rank": (place.get(rid) or {}).get("rank"), "label": "relevant" if rid in relevant else "not_relevant"}
                 for rid in coded]
        ranks.sort(key=lambda a: (a["rank"] is None, a["rank"] or 0, a["record_id"]))
        out.append({"label": q["label"], "question": q["question"], "scope_total": q["scope_total"], "ranked": q["ranked"],
                    "n_relevant": len(relevant), "n_coded": len(coded), "not_ranked": sorted(coded - set(ids)),
                    "flag_mismatch": mismatch, "ranks": ranks, **depth_scores(ids, relevant, coded)})
    return out, {"run_date": data["run_date"], "data_version": data["data_version"], "sha256": sha256(DEPTH)}


def human(questions):
    docs, by_record, sentences = human_truth()
    rows, missing = human_rows(questions, docs, by_record, sentences)
    summaries = {}
    for run in ("h1023", "h1024", "h1028"):
        items = [r for r in rows if r["run"] == run]
        summary = summarize(items, HUMAN_KS, [f"{m['run']}:{m['label']}" for m in missing if m["run"] == run])
        summary["screening_policy"] = dict(Counter(r["screening_policy"] for r in items))
        summary["data_version"] = dict(Counter(r["data_version"] for r in items))
        if run != "h1023":
            summary["final_with_flagged_micro"] = micro([{"final": r["final_with_flagged"]} for r in items])
            summary["groups"] = {route: [sum(r["groups"][route][0] for r in items), sum(r["groups"][route][1] for r in items)]
                                 for route in ("pass", "review", "exclude")}
            summary["judge_order"] = {key: sum(r["judge_order"][key] for r in items)
                                      for key in ("inversions", "across_labels", "without_probability", "labels_moved")}
        summaries[run] = summary
    depth, depth_source = depth_rows(by_record, {label: label_truth(label, docs, sentences) for label in questions})
    k_found = {k: sum(round(d["full_rank"][f"r@{k}"] * d["n_relevant"]) for d in depth) for k in (10, 40, 120)}
    total = sum(d["n_relevant"] for d in depth)
    summaries["depth"] = {"pooled_full_recall": {f"r@{k}": v / total for k, v in k_found.items()},
                          "found": k_found, "relevant": total, "questions": len(depth),
                          "coded": sum(d["n_coded"] for d in depth),
                          "not_ranked": sum(len(d["not_ranked"]) for d in depth),
                          "flag_mismatch": sum(len(d["flag_mismatch"]) for d in depth),
                          "full_rank_mean": {key: mean(d["full_rank"][key] for d in depth)
                                             for key in ("rr", "ndcg@10", "ndcg@15", "ndcg@120", "p@10", "r@10")},
                          "condensed_mean": {key: mean(d["condensed"][key] for d in depth)
                                             for key in ("rr", "ndcg@10", "ndcg@15", "p@10", "r@10")}}
    provenance = {"labels": sha256(LABELS), "doc_map": sha256(VAL / "doc_map.json"), "results_1023": sha256(VAL / "results.json"),
                  "triage_1024": sha256(VAL / "triage_answers.json"), "shipped_record": sha256(SHIPPED),
                  "s3e_confirmed": sha256(S3E / "triage_confirmed_answers.json"),
                  "s3e_confirmed_rest": sha256(S3E / "triage_confirmed_rest_answers.json"), "depth": depth_source,
                  "articles": len(docs)}
    return rows, depth, summaries, provenance, missing


# ---------- checks against earlier published numbers ----------

def primer_numbers():
    """The 10-29 primer's ranking numbers, recomputed its way: all list questions of the 8 runs with generator
    truth (frames by one AI annotation), read order, MRR and NDCG@120; content MRR and Hit@1 on evidence order.
    Its way skips a question whose order is empty instead of scoring it 0."""
    rr, ndcg, found, total, content = [], [], 0, 0, []
    for folder, qset in RUNS.values():
        expected = {e["query_id"]: e for e in json.load(open(B1K / f"dataset_b1k_{qset}/expected.json", encoding="utf-8"))}
        for qid, (_, result) in latest_answers(B1K / folder)[0].items():
            spec = expected.get(qid)
            if not spec:
                continue
            order, _ = read_order(result)
            if spec["task_type"] == "complete_list" and spec.get("list_truth"):
                truth = set(spec["list_truth"]["positive"])
                if order and truth:
                    got = order_metrics(order, truth, (120,))
                    rr.append(got["rr"]), ndcg.append(got["ndcg@120"])
                    found, total = found + round(got["r@120"] * len(truth)), total + len(truth)
            elif spec.get("source_record_ids") and result.get("evidence"):
                evidence = list(dict.fromkeys(e["record_id"] for e in result["evidence"] if e.get("record_id")))
                content.append(order_metrics(evidence, spec["source_record_ids"], (1,)))
    return {"list_questions": len(rr), "mrr": sum(rr) / len(rr), "ndcg@120": sum(ndcg) / len(ndcg),
            "pooled_recall@120": found / total, "content_questions": len(content),
            "content_mrr": sum(c["rr"] for c in content) / len(content),
            "content_hit@1": sum(1 for c in content if c["p@1"]) / len(content)}


def old_scorer_check(rows):
    """Per question, this report against the scorer of the time (each run folder's scores_<set>.json): keyword
    questions counted its way (tp, positives, judged listings, precision, recall), the content source rate, the title
    verdict. Also every ad whose adjudication then differs from the frozen reference's."""
    out = {kind: {"same": 0, "total": 0, "differs": []} for kind in ("keyword", "content", "title")}
    files, changed = {}, []
    for name, (folder, qset) in RUNS.items():
        path = B1K / folder / f"scores_{qset}.json"
        files[name] = sha256(path)
        old = {s["query_id"]: s for s in json.load(open(path, encoding="utf-8"))}
        for kind in out:
            for row in (r for r in rows[kind] if r["run"] == name):
                s = old[row["query_id"]]
                if kind == "keyword":
                    fields = old_scorer_differences(row["final_old_scorer"], s)
                    changed += [{"run": name, "query_id": row["query_id"], **item} for item in row["adjudication_changed"]]
                elif kind == "content":
                    fields = [] if abs(row["sources_cited"] / row["n_relevant"] - s.get("source_recall", -1)) < 1e-9 else ["source_recall"]
                else:
                    fields = [] if bool(s.get("ok")) == bool(row["fields_correct"]) else ["ok"]
                out[kind]["total"] += 1
                out[kind]["same"] += not fields
                if fields:
                    out[kind]["differs"].append({"run": name, "query_id": row["query_id"], "fields": fields})
    return {**out, "adjudication_changed": changed, "files": files}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "reports/rag_metrics_20261029")
    parser.add_argument("--ads-for", default=",".join(HEADLINE), help="B1K runs whose per-ad tables are kept")
    args = parser.parse_args(argv)
    shipped = json.load(open(SHIPPED, encoding="utf-8"))
    questions = {q["label"]: q["question"] for q in shipped["triage"]["questions"]}
    h_rows, depth, h_summary, h_provenance, h_missing = human(questions)
    b_rows, b_summary, b_runs, b_provenance, b_missing = b1k(set(filter(None, args.ads_for.split(","))))
    report = {"report": "rag-metrics", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "cost_usd": 0, "headline_b1k_runs": list(HEADLINE),
              "ks": {"list": LIST_KS, "human": HUMAN_KS, "content": CONTENT_KS, "depth": DEPTH_KS},
              "human": {"summary": h_summary, "questions": h_rows, "missing": h_missing, "depth": depth,
                        "shipped_groups": {k: shipped["triage"][k] for k in ("pass", "pass_human_yes", "review", "review_human_yes", "exclude", "exclude_human_yes")}},
              "b1k": {"runs": b_runs, "summary": b_summary, "questions": b_rows, "missing": b_missing},
              "checks": {"primer_recomputed": primer_numbers(), "old_scorer": old_scorer_check(b_rows)},
              "provenance": {"human": h_provenance, "b1k": b_provenance, "script": sha256(Path(__file__))}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    old = report["checks"]["old_scorer"]
    print(json.dumps({"human": {k: {"final_micro": v.get("final_micro"), "groups": v.get("groups"), "missing": v.get("missing")}
                                for k, v in h_summary.items() if k != "depth"},
                      "depth": h_summary["depth"], "primer": report["checks"]["primer_recomputed"],
                      "old_scorer": {k: {"same": old[k]["same"], "total": old[k]["total"]} for k in ("keyword", "content", "title")},
                      "adjudication_changed": len(old["adjudication_changed"]),
                      "missing": {k: len(v) for k, v in b_missing.items()},
                      "cache": {r["run"]: r["scoring_time_cache"] for r in b_runs}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
