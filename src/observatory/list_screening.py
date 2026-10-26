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
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .analytics import sponsor_display
from .answer_norms import load_norms, norms_tag, screening_prompt, split_tagged
from .budget import price
from .models import Answer, Citation, CitedStatement

POLICY_VERSION = "list-screening-v19"
MAX_CANDIDATES = 40
# Gated widening: past MAX_CANDIDATES, keep reading while the last window of
# ads read still had a match, up to MAX_WIDENED.
MAX_WIDENED = 120
WIDEN_WINDOW = 16
# Batches are independent provider calls, so up to this many run at once.
# Batch contents and the widening stop rule are unchanged: past `limit`, results
# are applied in order and batches after the stop point are discarded.
SCREEN_WORKERS = 8
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


# Second check of listed ads only: it may remove a listed ad, never add one, so
# no ad the screening found is lost except by an explicit rejection. On the
# B1K-U dev questions it cut wrong listings from 24 to 4-5 while losing about
# 1% of correct ones; a stricter screening prompt instead lost 3% (2026-10-18).
# On the sealed B1K-V questions it removed 10 wrong listings and 8 correct ones
# (2026-10-19), so it is off by default until a version holds on new questions.
VERIFY_LISTED = False
VERIFY_SYSTEM = """You double-check ads that a first screening listed as answering one question. For each ad you get
its passages and the sentence the screening quoted. Keep the ad unless its text clearly fails the
question's condition. Remove it only when:
- different_thing: the quoted sentence and the rest of the passages are about something other than what the
  question names (a related goal, a neighbouring topic, another organisation or product), or
- missing_relation: the condition asks for a relation (for example support, a trade-off, a dependence, an
  investment, a comparison, a forecast) and no sentence states that relation, in any wording.
A relation stated in other words counts. A short or passing statement counts if it states the condition.
When in doubt, keep. Return one verdict for every ad ref.

How to read relation words that are often misjudged (general meanings, not tied to any ad):
- investing in X: spending on, owning or holding a stake in, building, acquiring, developing or operating X.
- supporting an agreement or its goals: endorsing that named agreement or its stated goals; a company's own
  climate target counts only if the text ties it to that agreement.
- a trade-off between A, B and C: tension or balancing among them (gaining one costs another, or they must be
  weighed); listing them together as joint aims is not a trade-off.
- X depends on Y / X is essential to Y: Y is made from, needs, or could not exist or run without X.
- everyday products: goods people use in daily life (clothes, packaging, phones, medicines, household items);
  fuels and electricity in general are energy, not products.
- citing a projection of an organisation: a forecast or estimate the text attributes to that organisation.
- positioning the sponsor as an innovator: the sponsor itself develops, tests or applies new technology."""


class Verdict(BaseModel):
    ref: str
    verdict: Literal["keep", "remove"]
    reason: Literal["", "different_thing", "missing_relation"]


class Verdicts(BaseModel):
    verdicts: list[Verdict] = Field(max_length=BATCH_SIZE)


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
    norms = load_norms()
    kind, template, prompt = screening_prompt(norms, question, payload) if norms else (None, None, None)
    if prompt:
        parsed, reasoning, actual, fallback = _judge_tagged(rag, prompt, len(batch), visitor, stage, refs,
                                                            {"norms": norms_tag(norms), "type": kind, "template": template})
        if not fallback:
            return _checked_results(parsed, refs, phrases, reasoning), actual
    else:
        actual, reasoning, fallback = Decimal("0"), "", False
    parsed, extra = _judge_structured(rag, payload, len(batch), visitor, stage, refs)
    if fallback and reasoning:
        # The decisions below come from the structured call; the reasoning is kept
        # from the first call so why an ad was judged relevant stays readable.
        reasoning = "(first call; its answer could not be read) " + reasoning
    results = _checked_results(parsed, refs, phrases, reasoning)
    for result in results if fallback else ():
        result["screening_fallback"] = True
    return results, actual + extra


def _judge_structured(rag, payload, size, visitor, stage, refs):
    """The structured-output screening call (the default without private norms)."""
    upper_input = len((SYSTEM + payload).encode("utf-8")) + 2048
    # Low reasoning: with none, 15 of 40 ads containing the quoted words were
    # judged not to (L3D replay: recall 0.625 with none, 0.925 with low).
    max_output = 300 * size + 200 + REASONING_TOKENS
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
    return (response.output_parsed if response.status == "completed" else None), actual


# Reasoning written before the answer tag, per ad; kept short to bound output.
THINK_TOKENS_PER_AD = 160


def _judge_tagged(rag, prompt, size, visitor, stage, refs, request):
    """r1_zero-style call: <think> then <answer>{"decisions": [...]}</answer>.

    Returns (parsed Batch or None, reasoning, cost, fallback). An answer that
    cannot be parsed falls back to the structured call, so a list never loses
    a batch to a formatting slip; both calls are paid and counted.
    """
    upper_input = len((SYSTEM + prompt).encode("utf-8")) + 2048
    max_output = (300 + THINK_TOKENS_PER_AD) * size + 200 + REASONING_TOKENS
    estimate = price(rag.settings.generation_model, upper_input, max_output) * Decimal("1.25")
    rid = rag.budget.reserve(estimate, visitor, "generation", rag.settings.generation_model)
    try:
        response = rag.client.responses.create(
            model=rag.settings.generation_model,
            input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            max_output_tokens=max_output, reasoning={"effort": "low"}, store=False,
        )
        usage = response.usage
        if usage is None:
            raise ValueError("Provider omitted usage")
        details = usage.input_tokens_details
        actual = price(rag.settings.generation_model, usage.input_tokens, usage.output_tokens,
                       getattr(details, "cached_tokens", 0) or 0, getattr(details, "cache_write_tokens", 0) or 0)
        rag.budget.settle(rid, actual, {**usage.model_dump(), "observatory_request": {
            "policy": POLICY_VERSION, "stage": stage, "refs": list(refs), **request}})
    except Exception as exc:
        rag.budget.uncertain(rid, type(exc).__name__)
        raise
    reasoning, answer = split_tagged(getattr(response, "output_text", "") if response.status == "completed" else "")
    if answer:
        answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())  # a fenced JSON answer is still an answer
    try:
        return Batch.model_validate_json(answer), reasoning, actual, False
    except Exception:  # noqa: BLE001 - malformed or missing answer tag: use the structured call instead.
        return None, reasoning, actual, True


def _checked_results(parsed, refs, phrases, reasoning=""):
    returned = {}
    for decision in (parsed.decisions if parsed else []):
        returned.setdefault(decision.ref, decision)
    results = []
    for ref, (first, numbered) in refs.items():
        checked = checked_decision(returned.get(ref), numbered, phrases)
        if checked.get("reason") == "quote_not_in_passage":  # kept so a dropped match can be reviewed
            checked["rejected_quote"] = returned[ref].quote[:MAX_QUOTE]
        result = {"record_id": first.record_id, "title": first.title, "publisher": first.publisher,
                  "sponsor": first.sponsor, "published_at": first.published_at, **checked}
        if reasoning:
            result["screening_reasoning"] = reasoning[:1200]
        results.append(result)
    return results


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


def _run_batches(calls):
    """Run independent zero-argument calls, at most SCREEN_WORKERS at once, keeping order."""
    if len(calls) <= 1:
        return [call() for call in calls]
    with ThreadPoolExecutor(max_workers=min(SCREEN_WORKERS, len(calls))) as pool:
        return list(pool.map(lambda call: call(), calls))


def screen(rag, question, evidence, visitor, limit=MAX_CANDIDATES, widen_to=None, reread=None, verify=None):
    """Return per-record decisions and the settled cost. One provider call per batch.

    The first `limit` ranked ads are always read. Up to `widen_to` are read
    only while matches are still turning up: reading stops once the last
    WIDEN_WINDOW ads read contain none (B1K: lists with 113 candidates were
    cut at 40 while matches continued).

    `reread(record_ids)` returns every passage of those ads. An ad ruled out or
    left unclear while some of its passages were not shown is judged again on
    its whole text before it is left off the list (B1K-R: 29 screened ads with
    an unshown passage were ruled out). The second reading decides.

    `verify` (default VERIFY_LISTED, off) sends the listed ads through a second check that can only remove
    them (VERIFY_SYSTEM); questions with a quoted phrase are not re-checked.
    """
    groups = candidates_by_record(evidence, max(limit, widen_to or 0))
    phrases = quoted_phrases(question)
    results, cost = [], Decimal("0")
    starts = list(range(0, len(groups), BATCH_SIZE))
    first_wave = max(1, sum(1 for start in starts if start < limit))
    position, stopped = 0, False
    while position < len(starts) and not stopped:
        wave = starts[position:position + (first_wave if position == 0 else SCREEN_WORKERS)]
        outcomes = _run_batches([
            (lambda start=start: _judge(rag, question, groups[start:start + BATCH_SIZE], start + 1, phrases,
                                        visitor, "list_screening"))
            for start in wave
        ])
        for start, (found, spent) in zip(wave, outcomes):
            cost += spent  # every dispatched call is paid, kept or not
            if stopped or (start >= limit and not any(
                    item["decision"] == "matches" for item in results[-WIDEN_WINDOW:])):
                stopped = True
                continue
            results.extend(found)
        position += len(wave)
    if reread is not None:
        shown = {group[0].record_id: {p.evidence_id for p in group} for group in groups}
        open_ids = [item["record_id"] for item in results if item["decision"] != "matches"]
        whole = defaultdict(list)
        for passage in (reread(open_ids) if open_ids else []):
            whole[passage.record_id].append(passage)
        partial = [whole[rid] for rid in open_ids
                   if whole.get(rid) and {p.evidence_id for p in whole[rid]} - shown.get(rid, set())]
        position = {item["record_id"]: n for n, item in enumerate(results)}
        numbered, number = [], len(groups)
        for batch in _reread_batches(partial):
            numbered.append((batch, number + 1))
            number += len(batch)
        outcomes = _run_batches([
            (lambda batch=batch, first=first: _judge(rag, question, batch, first, phrases, visitor,
                                                     "list_screening_reread"))
            for batch, first in numbered
        ])
        for found, spent in outcomes:
            cost += spent
            for item in found:
                first = results[position[item["record_id"]]]["decision"]
                results[position[item["record_id"]]] = {**item, "reread_from": first}
    if verify is None:
        verify = VERIFY_LISTED
    if verify and not phrases:
        # A quoted phrase is checked literally already; the second check is
        # for conditions about meaning.
        texts = {group[0].record_id: group for group in groups}
        if reread is not None:
            texts.update({rid: passages for rid, passages in whole.items() if passages})
        listed = [item for item in results if item["decision"] == "matches"]
        position = {item["record_id"]: n for n, item in enumerate(results)}
        for start in range(0, len(listed), BATCH_SIZE):
            removed, spent = _verify(rag, question, listed[start:start + BATCH_SIZE], texts, visitor)
            cost += spent
            for rid, reason in removed.items():
                item = results[position[rid]]
                results[position[rid]] = {key: value for key, value in item.items() if key not in ("evidence_id", "quote")} | {
                    "decision": "does_not_match", "verified_from": "matches", "reason": reason}
    return results, float(cost)


def _verify(rag, question, listed, texts, visitor):
    """One provider call: which of these listed ads the second check removes, and its cost."""
    refs, ads = {}, []
    for n, item in enumerate(listed, 1):
        ref = f"A{n}"
        refs[ref] = item["record_id"]
        ads.append({"ref": ref, "title": item["title"], "sponsor": item["sponsor"], "screening_quote": item["quote"],
                    "passages": [{"passage_id": f"{ref}.{k}", "text": p.text}
                                 for k, p in enumerate(texts.get(item["record_id"], []), 1)]})
    payload = json.dumps({"question": question, "ads": ads}, ensure_ascii=False)
    max_output = 120 * len(listed) + 200 + REASONING_TOKENS
    upper_input = len((VERIFY_SYSTEM + payload).encode("utf-8")) + 2048
    estimate = price(rag.settings.generation_model, upper_input, max_output) * Decimal("1.25")
    rid = rag.budget.reserve(estimate, visitor, "generation", rag.settings.generation_model)
    try:
        response = rag.client.responses.parse(
            model=rag.settings.generation_model,
            input=[{"role": "system", "content": VERIFY_SYSTEM}, {"role": "user", "content": payload}],
            text_format=Verdicts, max_output_tokens=max_output, reasoning={"effort": "low"}, store=False,
        )
        usage = response.usage
        if usage is None:
            raise ValueError("Provider omitted usage")
        details = usage.input_tokens_details
        actual = price(rag.settings.generation_model, usage.input_tokens, usage.output_tokens,
                       getattr(details, "cached_tokens", 0) or 0, getattr(details, "cache_write_tokens", 0) or 0)
        rag.budget.settle(rid, actual, {**usage.model_dump(), "observatory_request": {
            "policy": POLICY_VERSION, "stage": "list_verification", "refs": list(refs)}})
    except Exception as exc:
        rag.budget.uncertain(rid, type(exc).__name__)
        raise
    parsed = response.output_parsed if response.status == "completed" else None
    # A missing or malformed verdict keeps the ad: only an explicit rejection removes it.
    return {refs[v.ref]: v.reason or "removed" for v in (parsed.verdicts if parsed else [])
            if v.ref in refs and v.verdict == "remove"}, actual


DATASET_NAMES = {"native": ("Native ads", "原生广告"), "social": ("Company posts", "公司社交帖子")}


def _display_order(matched, limit):
    """Matches reordered so the shown ones come first, each collection keeping a fair share.

    A collection with fewer matches than half the slots gives the rest to the
    other one; within a collection the ranked order is kept.
    """
    native = [item for item in matched if item.get("dataset") != "social"]
    social = [item for item in matched if item.get("dataset") == "social"]
    shown_social = min(len(social), max(limit - len(native), limit // 2))
    shown_native = min(len(native), limit - shown_social)
    return [*native[:shown_native], *social[:shown_social], *native[shown_native:], *social[shown_social:]]


def _both_head(chinese, scopes, by_dataset, whole=()):
    """Opening line of a list screened in both collections: what was read and found in each.

    A collection in `whole` was read in full by the triage; the records it did not read have no text.
    """
    parts = []
    for dataset in ("native", "social"):
        total, examined, found = scopes[dataset], by_dataset[dataset]["examined"], by_dataset[dataset]["matches"]
        if chinese:
            unit = "篇" if dataset == "native" else "条"
            read = (f"全部 {total:,} {unit}{DATASET_NAMES[dataset][1]}" if examined >= total else
                    f"全部 {examined:,} {unit}有正文的{DATASET_NAMES[dataset][1]}（{total:,} {unit}中另有 "
                    f"{total - examined:,} {unit}没有可读正文）" if dataset in whole else
                    f"{total:,} {unit}{DATASET_NAMES[dataset][1]}（检索没有找到相关的）" if not examined else
                    f"{total:,} {unit}{DATASET_NAMES[dataset][1]}中最相关的 {examined} {unit}")
            parts.append((read, f"{DATASET_NAMES[dataset][1]} {found} {unit}"))
        else:
            noun = "native ads" if dataset == "native" else "company social posts"
            read = (f"all {total:,} {noun}" if examined >= total else
                    f"all {examined:,} {noun} with readable text ({total - examined:,} of the {total:,} have none)"
                    if dataset in whole else
                    f"the {total:,} {noun} (none came up in the search)" if not examined else
                    f"the {examined} most relevant of the {total:,} {noun}")
            kind = ("ad" if found == 1 else "ads") if dataset == "native" else ("post" if found == 1 else "posts")
            parts.append((read, f"{found} matching {kind}"))
    if chinese:
        return f"检查了所选范围内{parts[0][0]}，以及{parts[1][0]}：找到符合的{parts[0][1]}、{parts[1][1]}。"
    return f"Checked {parts[0][0]} and {parts[1][0]} in your selection: found {parts[0][1]} and {parts[1][1]}."


def list_answer(question, results, evidence, *, scope_total, literal=None, scopes=None, criterion=None, triage=None):
    """Server-written list of screened matches with verbatim, located quotes.

    `literal` is the quoted phrase when the list came from an exact text search.
    `scopes` ({"native": n, "social": m}) marks a list screened in both
    collections; each result then carries its "dataset", the opening line
    counts each collection, and the charts split their bars by collection.
    With `triage` (relevance_triage), only ads routed "pass" are listed; ads
    routed "review" follow as a separate list for a human check.
    """
    chinese = bool(re.search(r"[一-鿿]", question))
    matched = [item for item in results if item["decision"] == "matches" and item.get("route", "pass") == "pass"]
    review = [item for item in results if item.get("route") == "review"]
    if scopes:
        matched = _display_order(matched, DISPLAY_LIMIT)
    counts = {name: sum(item["decision"] == name for item in results)
              for name in ("matches", "does_not_match", "unclear")}
    # A match routed to a human check is not counted as listed.
    counts["matches"] = sum(item["decision"] == "matches" and item.get("route", "pass") == "pass" for item in results)
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
        if item.get("dataset") == "social":
            # A post has no headline or outlet; its account says who posted it.
            line = (f"{'帖子：' if chinese else 'Post by '}{item['publisher'] or sponsor_display(item['sponsor'])}, "
                    f"{date}: “{item['quote']}” [{number}]")
        else:
            # Display names ("TotalEnergies", not the stored "totalenergies").
            line = (f"{item['title']} — {item['publisher']}, {sponsor_display(item['sponsor'])}, {date}: "
                    f"“{item['quote']}” [{number}]")
        if number <= DISPLAY_LIMIT:
            lines.append(f"{number}. {line}")
        claims.append(CitedStatement(text=line, citation_indices=[number]))
    # Every match stays in the citations (for review and scoring); the answer
    # shows the first DISPLAY_LIMIT and says how many more there are.
    hidden = len(matched) - min(len(matched), DISPLAY_LIMIT)
    if hidden:
        lines.append(hidden_line(hidden, chinese, both=bool(scopes)))
    if review:
        # Not dropped and not listed: the judge and the screening did not agree clearly enough.
        lines.append((f"另有 {len(review)} 篇需要人工核对（机器判断不够确定）：" if chinese else
                      f"{len(review)} more need a human check (the machine checks were not clear enough):"))
        for item in review[:DISPLAY_LIMIT]:
            numbers = item.get("triage") or {}
            share = f"{numbers['meets']:.0%}" if numbers.get("meets") is not None else "–"
            lines.append(f"- {item.get('title') or item['record_id']}"
                         + (f": “{item['quote']}”" if item.get("quote") and item["decision"] == "matches" else "")
                         + (f"（评审判定符合 {share}）" if chinese else f" (judge: meets {share})"))
        if len(review) > DISPLAY_LIMIT:
            lines.append(f"……另有 {len(review) - DISPLAY_LIMIT} 篇。" if chinese else
                         f"…and {len(review) - DISPLAY_LIMIT} more.")
    # Plain wording for readers; the method and its limits stay in
    # structured_result and the trace (user, 2026-10-19).
    m = counts["matches"]
    by_dataset = ({dataset: {"scope_total": scopes[dataset],
                             # An exact text search reads every record in scope.
                             "examined": (scopes[dataset] if literal is not None else
                                          sum(item.get("dataset") == dataset for item in results)),
                             "matches": sum(item.get("dataset") == dataset for item in matched)}
                   for dataset in ("native", "social")} if scopes else None)
    if scopes:
        whole = {dataset for dataset, item in ((triage or {}).get("by_dataset") or {}).items()
                 if item.get("whole_scope")}
        head = _both_head(chinese, scopes, by_dataset, whole)
        if literal is not None:
            head += (f"符合指含有“{literal}”（只按字面查找）。" if chinese else
                     f" Matching means containing “{literal}” (exact wording).")
    elif literal is not None and chinese:
        head = f"所选的 {scope_total} 篇广告中，有 {m} 篇含有“{literal}”（只按字面查找）。"
    elif literal is not None:
        head = f"{m} of the {scope_total} ads in your selection contain “{literal}” (exact wording)."
    elif chinese:
        head = (f"在所选的 {scope_total} 篇广告中找到 {m} 篇符合（已全部检查）。" if examined >= scope_total else
                f"在所选的 {scope_total} 篇广告中找到 {m} 篇符合；有正文的 {examined} 篇已全部检查，"
                f"另有 {scope_total - examined} 篇没有可读正文。" if (triage or {}).get("whole_scope") else
                f"在所选的 {scope_total} 篇广告中，检查了最相关的 {examined} 篇，找到 {m} 篇符合；"
                f"其余 {scope_total - examined} 篇未检查。")
    else:
        ads = "matching ad" if m == 1 else "matching ads"
        head = (f"Found {m} {ads} among the {scope_total} in your selection (all checked)."
                if examined >= scope_total else
                f"Found {m} {ads} among the {scope_total} in your selection; all {examined} with readable text "
                f"were checked, the other {scope_total - examined} have no readable text."
                if (triage or {}).get("whole_scope") else
                f"Found {m} {ads} among the {examined} most relevant of the {scope_total} in your selection; "
                f"the other {scope_total - examined} were not checked.")
    trace = {"policy": POLICY_VERSION, "method": "exact_text" if literal is not None else "ai_screening",
             "question": question,
             **({"criterion": criterion} if criterion else {}), **({"triage": triage} if triage else {}),
             "review": len(review),
             "scope_total": scope_total, "examined": scope_total if literal is not None else examined, **counts,
             # Each decision keeps its quote and, on the tagged path, the model's reasoning, so
             # why an ad was judged relevant can be read back (API detail=full, answer_runs).
             "decisions": [{key: (value.isoformat() if hasattr(value, "isoformat") else value)
                            for key, value in item.items() if key in (
                                "record_id", "dataset", "title", "decision", "reason", "evidence_id", "reread_from",
                                "verified_from", "quote", "rejected_quote", "screening_reasoning", "screening_fallback",
                                "route", "triage")} for item in results],
             "reread": sum("reread_from" in item for item in results),
             "verified_removed": sum("verified_from" in item for item in results),
             **({"by_dataset": by_dataset} if by_dataset else {})}
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
                           **{k: trace[k] for k in ("policy", "method", "scope_total", "examined", "matches", "review")},
                           **({"criterion": criterion} if criterion else {}),
                           **({"by_dataset": by_dataset} if by_dataset else {}),
                           "meaning": ("Literal wording found in indexed text; meaning is not judged."
                                       if literal is not None else
                                       "AI check of retrieved passages; not reviewed membership or a "
                                       "complete-collection result."),
                           "charts": list_charts(matched, chinese, both=bool(scopes)),
                           # Citation numbers the page shows (the first DISPLAY_LIMIT matches).
                           "display_citations": list(range(1, min(len(matched), DISPLAY_LIMIT) + 1))},
        research_trace={"list_screening": trace},
    )


# A chart is shown only when it says something: enough listed ads and more than
# one category. Counts come from the listed ads' stored fields, not from a model.
CHART_MIN_ADS = 3
# Matching ads written out in the answer; the rest are counted (user, 2026-10-19).
DISPLAY_LIMIT = 10
CHART_MAX_BARS = 12


def hidden_line(hidden, chinese, both=False):
    """The line counting matches not written out."""
    if chinese:
        return f"另有 {hidden} {'项' if both else '篇'}符合，未在此列出。"
    noun = "item" if both else "ad"
    return f"{hidden} more matching {noun}{'s' if hidden != 1 else ''} not shown here."


def list_charts(matched, chinese=False, both=False):
    """Bar-chart data for the listed ads: by sponsor, by publication year, by outlet.

    With `both`, each chart also carries one series per collection on the same
    category axis ("series"), so ads and posts are told apart by colour.
    """
    if len(matched) < CHART_MIN_ADS:
        return []
    unknown = "未知" if chinese else "Unknown"
    if both:
        titles = (("按公司", "按发布年份", "按媒体或账号") if chinese else
                  ("Listed ads and posts by company", "Listed ads and posts by publication year",
                   "Listed ads and posts by outlet or account"))
    else:
        titles = (("按赞助方", "按发布年份", "按媒体") if chinese else
                  ("Listed ads by sponsor", "Listed ads by publication year", "Listed ads by outlet"))
    dimensions = [
        # A post's account stands where an ad's sponsor or outlet is unknown.
        ("by_sponsor", titles[0],
         lambda item: (sponsor_display(item["sponsor"]) if item.get("sponsor") else
                       item.get("publisher") if item.get("dataset") == "social" and item.get("publisher") else unknown),
         False),
        ("by_year", titles[1],
         lambda item: str(item["published_at"].year) if item.get("published_at") else unknown, True),
        ("by_outlet", titles[2], lambda item: item.get("publisher") or unknown, False),
    ]
    charts = []
    for chart_id, title, key, chronological in dimensions:
        counts = Counter(key(item) for item in matched)
        if len(counts) < 2:
            continue
        if chronological:
            labels = sorted(counts, key=lambda label: (label == unknown, label))
        else:
            labels = [label for label, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        shown = labels[:CHART_MAX_BARS]
        chart = {"id": chart_id, "title": title, "labels": shown, "values": [counts[label] for label in shown],
                 "total": len(matched), "omitted_categories": len(labels) - len(shown)}
        if both:
            chart["series"] = [
                {"dataset": dataset, "name": DATASET_NAMES[dataset][1 if chinese else 0],
                 "values": [sum(key(item) == label for item in matched
                                if (item.get("dataset") == "social") == (dataset == "social")) for label in shown]}
                for dataset in ("native", "social")]
        charts.append(chart)
    return charts
