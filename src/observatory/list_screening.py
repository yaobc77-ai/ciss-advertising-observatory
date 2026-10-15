"""AI screening of every retrieved candidate ad for a "which ads ..." question.

Retrieval-augmented answers cite the few most relevant ads. A list question
needs a decision for each candidate instead: the model judges each ad only from
its supplied passages and must copy a supporting sentence, which the server
then finds in that ad's own passage before the ad is listed. The listed answer
is written by the server. It remains an AI check of retrieved passages, never a
reviewed content annotation or a statement about the whole collection beyond
the candidates that were read.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .budget import price
from .models import Answer, Citation, CitedStatement

POLICY_VERSION = "list-screening-v10"
MAX_CANDIDATES = 40
# Gated widening: past MAX_CANDIDATES, keep reading while the last window of
# ads read still had a match, up to MAX_WIDENED.
MAX_WIDENED = 120
WIDEN_WINDOW = 16
# Ads judged per call. Other ads in the batch sway a decision: replaying the
# R round's 8-ad batches, 3 and 1 of 9 missed ads were found, alone 5; on 13
# whole questions 4-ad batches listed every positive in 5, 8-ad ones in 2
# (2026-10-15, about 13% more cost).
BATCH_SIZE = 4
# Text sent per re-reading call; an article longer than this goes alone.
REREAD_CHARS = 40_000
MAX_QUOTE = 300
REASONING_TOKENS = 1500

SYSTEM = """You screen advertisements against one question. Judge each ad ONLY from its supplied passages.
- matches: a passage states or clearly presents what the question asks about. Copy ONE supporting sentence from that passage verbatim (at most 300 characters) and give its passage_id.
- does_not_match: the passages do not satisfy the question's condition.
- unclear: the passages are partial or ambiguous, or the answer depends on text that was not supplied.
A topic mention alone does not satisfy a condition about how an ad positions, frames or argues something.
Planned or aspirational statements are not achievements. You assess what the ad says, not whether it is true.
When the question puts a word or phrase in quotation marks, an ad matches only if its passage contains that
word or phrase (case, hyphenation and plural forms may differ); related wording does not count.
phrase_sentences, when present, lists the sentences of that ad where the quoted phrase occurs.
Return exactly one decision for every ad ref."""

_QUOTED = re.compile(r'"([^"]{2,80})"|“([^”]{2,80})”')


def quoted_phrases(question):
    return [a or b for a, b in _QUOTED.findall(question)]


def _phrase_pattern(phrase):
    """Words in order; hyphen or space between them; an optional plural ending."""
    words = re.findall(r"\w+", phrase.casefold())
    return re.compile(r"\b" + r"[\s-]+".join(re.escape(word) + r"(?:s|es)?" for word in words) + r"\b",
                      re.IGNORECASE)


# Words that only ask for a list of ads containing the quoted text. Any other
# word ("as a solution", "about safety") is a condition on meaning.
_LITERAL_FRAME = frozenset("""which what list show find give me all every any the a native ads ad advertisements
advertisement articles article that mention mentions mentioned use uses used contain contains include includes
refer refers to say says the words word phrase phrases term terms expression anywhere in their its text body
wording of""".split())
_LIST_CUE = re.compile(r"\b(?:which|list|show|find)\b", re.IGNORECASE)
_LITERAL_VERB = re.compile(r"\b(?:mention|mentions|mentioned|use|uses|used|contain|contains|include|includes|"
                           r"refer|refers|say|says)\b", re.IGNORECASE)


def pure_literal_question(question):
    """Only asks which ads contain one quoted word or phrase: wording, not meaning."""
    if len(quoted_phrases(question)) != 1:
        return False
    rest = _QUOTED.sub(" ", question)
    words = re.findall(r"[^\W\d_]+", rest.casefold())
    return (bool(_LIST_CUE.search(rest)) and bool(_LITERAL_VERB.search(rest))
            and all(word in _LITERAL_FRAME for word in words))


def phrase_sentence(text, phrase, limit=MAX_QUOTE):
    """The verbatim sentence of `text` around the first occurrence of `phrase`."""
    match = _phrase_pattern(phrase).search(text)
    if match is None:
        return None
    starts = [0, *(m.end() for m in re.finditer(r"[.!?]\s+|\n+", text[:match.start()]))]
    start = starts[-1]
    end_match = re.search(r"[.!?](?=\s|$)|\n", text[match.end():])
    end = match.end() + (end_match.end() if end_match else len(text) - match.end())
    if end - start > limit:
        start = max(start, match.start() - limit // 2)
        end = min(end, start + limit)
    return text[start:end].strip()


def literal_results(evidence, phrase):
    """Every literal-match ad, decided by the server without a model call."""
    results = []
    for passages in candidates_by_record(evidence, limit=None):
        for item in passages:
            sentence = phrase_sentence(item.text, phrase)
            if sentence:
                results.append({"record_id": item.record_id, "title": item.title, "publisher": item.publisher,
                                "sponsor": item.sponsor, "published_at": item.published_at, "decision": "matches",
                                "evidence_id": item.evidence_id, "quote": sentence, "method": "literal"})
                break
    return results


def contains_phrases(text, phrases):
    return all(_phrase_pattern(phrase).search(text) for phrase in phrases)


class Decision(BaseModel):
    ref: str
    decision: Literal["matches", "does_not_match", "unclear"]
    passage_id: str
    quote: str


class Batch(BaseModel):
    decisions: list[Decision] = Field(max_length=BATCH_SIZE)


_TYPOGRAPHY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "\u00a0": " "})


def _squash(text):
    """Whitespace and typographic quotes/dashes do not decide whether a quote is verbatim."""
    return re.sub(r"\s+", " ", (text or "").translate(_TYPOGRAPHY)).strip()


def _find_spaceless(text, wanted):
    """Span of `wanted` in `text` when only whitespace differs, else None.

    Stored ad text has lost spaces ("solutionis shifting"); a model copying the
    sentence restores them (Q round: correct matches dropped as not verbatim).
    """
    keep = [i for i, ch in enumerate(text) if not ch.isspace()]
    target = re.sub(r"\s+", "", wanted).lower()
    at = "".join(text[i] for i in keep).lower().find(target) if target else -1
    if at < 0 or len(target) < 12:
        return None
    return keep[at], keep[at + len(target) - 1] + 1


def candidates_by_record(evidence, limit=MAX_CANDIDATES):
    """Group passages by record in retrieval order; the first `limit` records are read."""
    groups = {}
    for item in evidence:
        groups.setdefault(item.record_id, []).append(item)
    return list(groups.values())[:limit] if limit is not None else list(groups.values())


def checked_decision(decision, passages, phrases=()):
    """Accept a match only with a quote found verbatim in one passage of that ad.

    The passages of one ad are read as one article: the named passage is tried
    first, then the others. Case and edge punctuation are not part of the check
    and a long quote is cut to a verbatim prefix; the stored quote is always the
    passage's own text (B1K: 253 matches were dropped, 138 for length alone).
    A phrase the question quotes must occur in the located quote (C24/L3:
    "method used" was matched to any sentence about methods).
    """
    if decision is None:
        return {"decision": "unclear", "reason": "not_returned"}
    if decision.decision != "matches":
        return {"decision": decision.decision}
    if decision.passage_id not in passages:
        return {"decision": "unclear", "reason": "unknown_passage"}
    wanted = _squash(decision.quote).strip(_EDGE)
    order = [decision.passage_id, *(pid for pid in passages if pid != decision.passage_id)]
    for pid in order:
        text = _squash(passages[pid].text)
        at = text.lower().find(wanted.lower()) if wanted and len(text.lower()) == len(text) else -1
        if at >= 0:
            passage, quote = passages[pid], text[at:at + len(wanted)]
            break
    else:
        for pid in order:
            text = _squash(passages[pid].text)
            span = _find_spaceless(text, wanted) if len(text.lower()) == len(text) else None
            if span:
                passage, quote = passages[pid], text[span[0]:span[1]]
                break
        else:
            return {"decision": "unclear", "reason": "quote_not_in_passage"}
    if phrases and not contains_phrases(quote, phrases):
        return {"decision": "unclear", "reason": "quoted_phrase_absent"}
    if len(quote) > MAX_QUOTE:
        quote = quote[:MAX_QUOTE].rsplit(" ", 1)[0]
    return {"decision": "matches", "evidence_id": passage.evidence_id, "quote": quote}


_EDGE = " \"'.,;:!?…"


def _judge(rag, question, batch, first_index, phrases, visitor, stage):
    """One provider call for a batch of ads (each a list of passages); returns checked results and cost."""
    refs, ads = {}, []
    for index, passages in enumerate(batch, first_index):
        ref = f"A{index}"
        first = passages[0]
        numbered = {f"{ref}.{n}": item for n, item in enumerate(passages, 1)}
        refs[ref] = (first, numbered)
        ad = {"ref": ref, "title": first.title, "publisher": first.publisher, "sponsor": first.sponsor,
              "published_at": first.published_at.isoformat() if first.published_at else None,
              "passages": [{"passage_id": pid, "text": item.text} for pid, item in numbered.items()]}
        # Long passages hide a literal occurrence from a fast model (L3C:
        # 7 of 10 ads containing "billion people" judged not to).
        located = [{"passage_id": pid, "sentence": sentence} for pid, item in numbered.items()
                   for phrase in phrases if (sentence := phrase_sentence(item.text, phrase))]
        if located:
            ad["phrase_sentences"] = located[:3]
        ads.append(ad)
    payload = json.dumps({"question": question, "ads": ads}, ensure_ascii=False)
    upper_input = len((SYSTEM + payload).encode("utf-8")) + 2048
    # Low reasoning: with none, 15 of 40 ads containing the quoted words were
    # judged not to (L3D replay: recall 0.625 with none, 0.925 with low).
    max_output = 300 * len(batch) + 200 + REASONING_TOKENS
    estimate = price(rag.settings.generation_model, upper_input, max_output) * Decimal("1.25")
    rid = rag.budget.reserve(estimate, visitor, "generation", rag.settings.generation_model)
    try:
        response = rag.client.responses.parse(
            model=rag.settings.generation_model,
            input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": payload}],
            text_format=Batch, max_output_tokens=max_output, reasoning={"effort": "low"}, store=False,
        )
        usage = response.usage
        if usage is None:
            raise ValueError("Provider omitted usage")
        details = usage.input_tokens_details
        actual = price(rag.settings.generation_model, usage.input_tokens, usage.output_tokens,
                       getattr(details, "cached_tokens", 0) or 0, getattr(details, "cache_write_tokens", 0) or 0)
        rag.budget.settle(rid, actual, {**usage.model_dump(), "observatory_request": {
            "policy": POLICY_VERSION, "stage": stage, "refs": list(refs)}})
    except Exception as exc:
        rag.budget.uncertain(rid, type(exc).__name__)
        raise
    parsed = response.output_parsed if response.status == "completed" else None
    returned = {}
    for decision in (parsed.decisions if parsed else []):
        returned.setdefault(decision.ref, decision)
    results = []
    for ref, (first, numbered) in refs.items():
        checked = checked_decision(returned.get(ref), numbered, phrases)
        if checked.get("reason") == "quote_not_in_passage":  # kept so a dropped match can be reviewed
            checked["rejected_quote"] = returned[ref].quote[:MAX_QUOTE]
        results.append({"record_id": first.record_id, "title": first.title, "publisher": first.publisher,
                        "sponsor": first.sponsor, "published_at": first.published_at, **checked})
    return results, actual


def _reread_batches(groups):
    """Whole articles packed by text size, so one long transcript does not overflow a call."""
    batch, size = [], 0
    for passages in groups:
        length = sum(len(item.text) for item in passages)
        if batch and (len(batch) >= BATCH_SIZE or size + length > REREAD_CHARS):
            yield batch
            batch, size = [], 0
        batch.append(passages)
        size += length
    if batch:
        yield batch


def screen(rag, question, evidence, visitor, limit=MAX_CANDIDATES, widen_to=None, reread=None):
    """Return per-record decisions and the settled cost. One provider call per batch.

    The first `limit` ranked ads are always read. Up to `widen_to` are read
    only while matches are still turning up: reading stops once the last
    WIDEN_WINDOW ads read contain none (B1K: lists with 113 candidates were
    cut at 40 while matches continued).

    `reread(record_ids)` returns every passage of those ads. An ad ruled out or
    left unclear while some of its passages were not shown is judged again on
    its whole text before it is left off the list (B1K-R: 29 screened ads with
    an unshown passage were ruled out). The second reading decides.
    """
    groups = candidates_by_record(evidence, max(limit, widen_to or 0))
    phrases = quoted_phrases(question)
    results, cost = [], Decimal("0")
    for start in range(0, len(groups), BATCH_SIZE):
        if start >= limit and not any(item["decision"] == "matches" for item in results[-WIDEN_WINDOW:]):
            break
        found, spent = _judge(rag, question, groups[start:start + BATCH_SIZE], start + 1, phrases, visitor,
                              "list_screening")
        results.extend(found)
        cost += spent
    if reread is not None:
        shown = {group[0].record_id: {p.evidence_id for p in group} for group in groups}
        open_ids = [item["record_id"] for item in results if item["decision"] != "matches"]
        whole = defaultdict(list)
        for passage in (reread(open_ids) if open_ids else []):
            whole[passage.record_id].append(passage)
        partial = [whole[rid] for rid in open_ids
                   if whole.get(rid) and {p.evidence_id for p in whole[rid]} - shown.get(rid, set())]
        position = {item["record_id"]: n for n, item in enumerate(results)}
        number = len(groups)
        for batch in _reread_batches(partial):
            found, spent = _judge(rag, question, batch, number + 1, phrases, visitor, "list_screening_reread")
            number += len(batch)
            cost += spent
            for item in found:
                first = results[position[item["record_id"]]]["decision"]
                results[position[item["record_id"]]] = {**item, "reread_from": first}
    return results, float(cost)


def list_answer(question, results, evidence, *, scope_total, literal=None):
    """Server-written list of screened matches with verbatim, located quotes.

    `literal` is the quoted phrase when the list came from an exact text search.
    """
    chinese = bool(re.search(r"[一-鿿]", question))
    matched = [item for item in results if item["decision"] == "matches"]
    counts = {name: sum(item["decision"] == name for item in results)
              for name in ("matches", "does_not_match", "unclear")}
    examined = len(results)
    by_id = {item.evidence_id: item for item in evidence}
    citations, lines, claims = [], [], []
    for number, item in enumerate(matched, 1):
        passage = by_id[item["evidence_id"]]
        citations.append(Citation(evidence_id=passage.evidence_id, quote=item["quote"],
                                  **{key: getattr(passage, key) for key in (
                                      "source_observation_id", "source_version_id", "source_body_hash")
                                     if hasattr(passage, key)}))
        date = item["published_at"].isoformat() if item["published_at"] else ("日期未知" if chinese else "date unknown")
        line = f"{item['title']} — {item['publisher']}, {item['sponsor']}, {date}: “{item['quote']}” [{number}]"
        lines.append(f"{number}. {line}")
        claims.append(CitedStatement(text=line, citation_indices=[number]))
    if literal is not None and chinese:
        head = (f"对所选范围 {scope_total} 篇广告的可检索正文做逐字查找，{counts['matches']} 篇含“{literal}”"
                "（不区分大小写、连字符和复数）。这只核对字面，不判断含义；未纳入检索的文字（如导航）不在查找范围内。")
    elif literal is not None:
        head = (f"An exact text search of the {scope_total} ads in the selected scope found {counts['matches']} whose "
                f"indexed text contains “{literal}” (ignoring case, hyphens and plural endings). This checks wording, "
                "not meaning; text excluded from indexing, such as navigation, is not searched.")
    elif chinese:
        head = (f"在所选范围的 {scope_total} 篇广告中，AI 逐篇核对了检索最相关的 {examined} 篇，"
                f"{counts['matches']} 篇符合。这是对检索段落的 AI 核对，不是经过审查的标注；"
                f"排在前 {examined} 篇之后的广告未核对。")
    else:
        head = (f"AI screening of the {examined} most relevant of {scope_total} ads in the selected scope found "
                f"{counts['matches']} that match. This is an AI check of retrieved passages, not a reviewed "
                f"annotation; ads ranked below the first {examined} were not checked.")
    trace = {"policy": POLICY_VERSION, "method": "exact_text" if literal is not None else "ai_screening",
             "scope_total": scope_total, "examined": scope_total if literal is not None else examined, **counts,
             "decisions": [{key: (value.isoformat() if hasattr(value, "isoformat") else value)
                            for key, value in item.items() if key in (
                                "record_id", "decision", "reason", "evidence_id", "reread_from")} for item in results],
             "reread": sum("reread_from" in item for item in results)}
    cited_evidence = [by_id[item["evidence_id"]] for item in matched]
    return Answer(
        # Zero matches among the screened ads is itself the answer to a list
        # question, not an evidence shortfall to be filled from web pages.
        status="answered",
        # The answer lists what matched. Ads ruled out or left unclear are not
        # part of it (user, 2026-10-15); their counts stay in the trace.
        answer="\n\n".join(part for part in [head, *lines] if part),
        citations=citations, cited_claims=claims,
        evidence=list({item.evidence_id: item for item in [*cited_evidence, *evidence]}.values()),
        structured_result={"kind": "exact_text_list" if literal is not None else "ai_screened_list",
                           **{k: trace[k] for k in ("policy", "method", "scope_total", "examined", "matches")},
                           "meaning": ("Literal wording found in indexed text; meaning is not judged."
                                       if literal is not None else
                                       "AI check of retrieved passages; not reviewed membership or a "
                                       "complete-collection result.")},
        research_trace={"list_screening": trace},
    )
