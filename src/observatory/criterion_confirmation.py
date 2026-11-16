"""Two-phase list questions: the criterion is confirmed before any ad is judged (step 3, S3-c).

A screened list under "ask" (QuestionPlan.criterion_mode) stops after retrieval and the
free-to-cheap preparation with a pending answer, the *card*: the criterion drafted from
the question alone (relevance_triage.make_criterion), one example sentence per rule taken
verbatim from the best-ranked candidates (never sent to any model), what the judgment
will cover (design 3.9), and a signed continuation token. The researcher confirms the
rules, edits them, writes their own, or only browses the candidates. Phase 2
(Service.answer(..., continuation=...)) checks the token, binds the flow in the
in-process FlowRegistry so one card pays for one judgment, and re-enters the evidence
route with the confirmed criterion (design 3.5). Decisions of 2026-10-27: API and
internal callers keep an unconfirmed "auto" mode and say so; a human may quote
collection sentences in the rules, which is recorded, never refused; after confirmation
screening judges by the confirmed criterion.

Everything here is pure or process-local: no database and no model call. The registry is
process-local like query_progress.ProgressRegistry (the current deployment is one process).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    TimestampSigner,
    URLSafeTimedSerializer,
)

from .list_screening import MAX_QUOTE
from .models import Answer
from .relevance_triage import TRIAGE_ALL_MAX, Criterion

KIND = "criterion_confirmation"
TOKEN_SALT = "criterion-confirmation-v1"
# A card can be continued for this long; a pending flow is forgotten after it.
TOKEN_MAX_AGE = 1800
# A judged or failed flow stays known this long, so a retry replays or is refused instead of paying again.
DONE_TTL = 86_400
MAX_FLOWS = 256
EXAMPLES_PER_COLLECTION = 5
MAX_RULES, MAX_EXCLUSIONS = 4, 3
EXAMPLE_SOURCE = f"retrieval_top_{EXAMPLES_PER_COLLECTION}_per_collection"
# Answers that refuse or defer a continuation: not evidence shortfalls, never supplemented from the web.
CONFIRMATION_REFUSALS = frozenset({"continuation_invalid", "continuation_conflict", "continuation_in_progress",
                                   "criterion_invalid", "confirmation_registry_full", "confirmation_unavailable"})
# Conditions a researcher may confirm without writing rules (nothing was drafted for them).
CONDITIONS_WITHOUT_RULES = frozenset({"phrases", "relation_hint", "triage_off"})

_CJK = re.compile(r"[一-鿿]")
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+|\n+")
# Words that carry no meaning of their own when a rule is matched against a sentence.
_STOP = frozenset("""a an the of in on at to for with by as and or that this these those it its their is are be was
were ad ads advertisement advertisements article articles post posts says say said presents present presented
mentions mention mentioned about from which what any all every""".split())


class ContinuationInvalid(ValueError):
    """A continuation that must not run: a bad or expired token, another visitor, changed data or scope, an unknown flow."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class CriterionInvalid(ValueError):
    """A criterion the registry would not accept: no rules, too many, or not text."""

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class RegistryFull(RuntimeError):
    """Every slot of the flow registry holds a judgment in progress; nothing is evicted while it runs."""


class FlowLost(RuntimeError):
    """The flow was forgotten while its card was being prepared: no card is issued for it."""


def chinese(question):
    return bool(_CJK.search(question or ""))


def pending_confirmation(result) -> bool:
    """The one marker every consumer uses: the answer stopped at the card (design 3.2)."""
    structured = result.get("structured_result") if isinstance(result, dict) else getattr(result, "structured_result", None)
    return isinstance(structured, dict) and structured.get("kind") == KIND


def normal_question(question):
    """The question as the token records it: surrounding and repeated whitespace do not matter."""
    return " ".join(str(question or "").split())


def new_flow_id():
    return secrets.token_urlsafe(16)


# --- The criterion a researcher confirmed ---------------------------------------------------------


def normalize_criterion(value):
    """The researcher's rules as the judge gets them: trimmed, blank lines dropped, within the Criterion limits."""
    if not isinstance(value, dict) or set(value) - {"counts", "does_not_count"}:
        raise CriterionInvalid("not_a_criterion")

    def rules(key):
        items = value.get(key) or []
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise CriterionInvalid("not_text")
        return [" ".join(item.split()) for item in items if item.strip()]

    counts, excluded = rules("counts"), rules("does_not_count")
    if not counts:
        raise CriterionInvalid("no_rules")
    if len(counts) > MAX_RULES:
        raise CriterionInvalid("too_many_rules")
    if len(excluded) > MAX_EXCLUSIONS:
        raise CriterionInvalid("too_many_exclusions")
    return Criterion(counts=counts, does_not_count=excluded).model_dump()


def criterion_hash(criterion):
    """One text for one criterion: the server decides "confirmed" or "edited" by comparing hashes, not labels."""
    canonical = json.dumps(normalize_criterion(criterion), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Tokens ---------------------------------------------------------------------------------------


class _ClockSigner(TimestampSigner):
    """A TimestampSigner whose clock can be set, so tests expire tokens without waiting."""

    def __init__(self, *args, clock=time.time, **kwargs):
        super().__init__(*args, **kwargs)
        self.clock = clock

    def get_timestamp(self):
        return int(self.clock())


class ConfirmationTokens:
    """Signed, timestamped continuation tokens (itsdangerous, as query_records.py already uses).

    The token carries what phase 2 must trust without a database: flow id, visitor, the
    question, the scope the evidence route was called with, the plan (its effective scope
    inside), the hash of the drafted criterion, the condition kind and the data version.
    Without a configured cookie secret the key is random per process: a restart invalidates
    every card, which is what design 3.5 wants (the registry is gone too).
    """

    def __init__(self, secret=None, clock=time.time):
        self.clock = clock
        self._serializer = URLSafeTimedSerializer(secret or secrets.token_urlsafe(32), salt=TOKEN_SALT,
                                                  signer=_ClockSigner, signer_kwargs={"clock": clock})

    def issue(self, payload) -> str:
        return self._serializer.dumps(payload)

    def read(self, token, max_age=TOKEN_MAX_AGE):
        if not isinstance(token, str) or not token:
            raise ContinuationInvalid("malformed")
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except SignatureExpired:
            raise ContinuationInvalid("expired") from None
        except BadSignature:
            raise ContinuationInvalid("bad_signature") from None
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ContinuationInvalid("malformed")
        return payload

    def expires_at(self, max_age=TOKEN_MAX_AGE):
        """When a token issued now stops working, as UTC text for the card."""
        return (datetime.fromtimestamp(int(self.clock()), tz=timezone.utc) + timedelta(seconds=max_age)).isoformat()


# --- Flow registry --------------------------------------------------------------------------------


class FlowRegistry:
    """One card, one judgment: preparing -> pending -> judging -> done | failed, atomic under one lock (design 3.5).

    A flow is registered as "preparing" before anything is drafted and becomes "pending" once its
    card is issued; both are forgotten after `pending_ttl`. Done and failed flows stay `done_ttl`,
    so a retry replays the stored answer or is refused instead of paying again. Preparing and
    judging flows are never evicted for room; when every slot holds one, a new card is refused
    (RegistryFull) before anything is drafted.
    """

    EVICTABLE = ("pending", "done", "failed")

    def __init__(self, *, pending_ttl=TOKEN_MAX_AGE, done_ttl=DONE_TTL, max_entries=MAX_FLOWS, clock=time.monotonic):
        self.pending_ttl, self.done_ttl, self.max_entries, self.clock = pending_ttl, done_ttl, max_entries, clock
        self._entries = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        for flow_id, entry in list(self._entries.items()):
            if entry["state"] in ("preparing", "pending") and now - entry["created"] >= self.pending_ttl:
                del self._entries[flow_id]
            elif entry["state"] in ("done", "failed") and now - entry["updated"] >= self.done_ttl:
                del self._entries[flow_id]

    def register(self, flow_id, visitor, context):
        with self._lock:
            now = self.clock()
            self._prune(now)
            if flow_id in self._entries:
                raise ValueError("flow id already registered")
            if len(self._entries) >= self.max_entries:
                evictable = [fid for fid, entry in self._entries.items() if entry["state"] in self.EVICTABLE]
                if not evictable:
                    raise RegistryFull()
                del self._entries[min(evictable, key=lambda fid: self._entries[fid]["updated"])]
            self._entries[flow_id] = {"visitor": visitor, "state": "preparing", "created": now, "updated": now,
                                      "context": dict(context), "criterion_hash": None, "result": None, "reason": None}

    def ready(self, flow_id, **context):
        """The card is issued with these findings (the draft, the examples): the flow may be continued.

        The pending window (`pending_ttl`) starts now, not at registration (design 3.5: from the
        end of phase one). False when the preparation was forgotten meanwhile: no card then.
        """
        with self._lock:
            now = self.clock()
            self._prune(now)
            entry = self._entries.get(flow_id)
            if not entry or entry["state"] != "preparing":
                return False
            entry["context"].update(context)
            entry.update(state="pending", created=now, updated=now)
            return True

    def discard(self, flow_id):
        """Phase 1 failed before a card was issued: nothing to continue."""
        with self._lock:
            entry = self._entries.get(flow_id)
            if entry and entry["state"] == "preparing":
                del self._entries[flow_id]

    def claim(self, flow_id, visitor, criterion_hash):
        """(outcome, data): "started" binds the criterion and returns the phase-1 context; "done" returns the stored answer.

        Other outcomes: "unknown" (no such flow for this visitor, not issued yet, or forgotten),
        "in_progress" (judging with the same criterion), "conflict" (another criterion already
        bound), "failed" (terminal). None of them runs anything.
        """
        with self._lock:
            now = self.clock()
            self._prune(now)
            entry = self._entries.get(flow_id)
            if entry is None or entry["visitor"] != visitor or entry["state"] == "preparing":
                return "unknown", None
            if entry["state"] == "pending":
                entry.update(state="judging", criterion_hash=criterion_hash, updated=now)
                return "started", dict(entry["context"])
            if entry["state"] == "failed":
                return "failed", None
            if entry["criterion_hash"] != criterion_hash:
                return "conflict", None
            if entry["state"] == "judging":
                return "in_progress", None
            return "done", entry["result"]

    def finish(self, flow_id, result):
        with self._lock:
            entry = self._entries.get(flow_id)
            if entry and entry["state"] == "judging":
                entry.update(state="done", result=compact_result(result), updated=self.clock())

    def fail(self, flow_id, reason):
        with self._lock:
            entry = self._entries.get(flow_id)
            if entry and entry["state"] == "judging":
                entry.update(state="failed", reason=str(reason), updated=self.clock())

    def __len__(self):
        with self._lock:
            self._prune(self.clock())
            return len(self._entries)

    def snapshot(self, flow_id):
        """State only (for tests and operators), never the stored answer or the token."""
        with self._lock:
            self._prune(self.clock())
            entry = self._entries.get(flow_id)
            if entry is None:
                return None
            return {key: entry[key] for key in ("visitor", "state", "criterion_hash", "reason", "created", "updated")}


def _referenced_ids(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_id" and isinstance(item, str):
                found.add(item)
            else:
                _referenced_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _referenced_ids(item, found)
    return found


def compact_result(result):
    """The final answer with only the passages its citations and structured result refer to (stored for replays)."""
    kept = _referenced_ids([result.structured_result, [c.model_dump() for c in result.citations]], set())
    return result.model_copy(update={"evidence": [e for e in result.evidence if e.evidence_id in kept]}, deep=True)


def replay(stored, flow_id):
    """A retry with the same criterion gets the judged answer again, at no new cost, as a new copy."""
    copy = stored.model_copy(deep=True)
    copy.research_trace = {**copy.research_trace,
                           "continuation_replay": {"flow_id": flow_id, "evidence_trimmed": True,
                                                   "original_cost_usd": stored.cost_usd}}
    copy.cost_usd = 0.0
    copy.latency_ms = 0
    return copy


def redact_continuation(result):
    """The run record keeps the token's hash, never the token (design 3.5); the answer returned is untouched."""
    if not pending_confirmation(result):
        return result
    structured = dict(result.structured_result)
    token = structured.get("continuation")
    if not isinstance(token, str):
        return result
    structured["continuation"] = None
    structured["continuation_sha256"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return result.model_copy(update={"structured_result": structured})


# --- Example sentences (design 3.3) ---------------------------------------------------------------


def _sentences(text):
    return [part.strip() for part in _SENTENCE_END.split(text or "") if part and part.strip()]


def _cut(sentence, limit=MAX_QUOTE):
    if len(sentence) <= limit:
        return sentence
    head = sentence[:limit]
    return head.rsplit(" ", 1)[0] if " " in head else head


def _words(text):
    return set(re.findall(r"\w+", text.casefold())) - _STOP


def _opening(text, limit=30):
    """A passage's first sentence, at most `limit` words, verbatim: cut at the end of the limit-th word."""
    parts = _sentences(text)
    sentence = parts[0] if parts else (text or "").strip()
    ends = [match.end() for match in re.finditer(r"\S+", sentence)]
    if len(ends) > limit:
        sentence = sentence[:ends[limit - 1]]
    return _cut(sentence)


def criterion_examples(criterion, evidence, datasets, per_collection=EXAMPLES_PER_COLLECTION):
    """One verbatim sentence per inclusion rule and collection, from the best-ranked candidates.

    Word overlap between the rule and each sentence of the top `per_collection` records (in
    retrieval order) picks the sentence; ties keep the earlier record, then the earlier
    sentence; no overlap at all falls back to the top record's opening sentence. Cheap and
    explainable (v1); the examples go to the card and the trace only, never to a model.
    """
    examples = []
    for dataset in datasets:
        own = [item for item in evidence if getattr(item, "dataset", None) == dataset]
        records = list(dict.fromkeys(item.record_id for item in own))[:per_collection]
        passages = [item for item in own if item.record_id in records]
        if not passages:
            continue
        rank = {record_id: number for number, record_id in enumerate(records)}
        for number, rule in enumerate(criterion["counts"], 1):
            wanted = _words(rule)
            best, position = None, 0
            for passage in passages:
                for sentence in _sentences(passage.text):
                    sentence = _cut(sentence)
                    score = len(wanted & _words(sentence))
                    key = (-score, rank[passage.record_id], position)
                    if best is None or key < best[0]:
                        best = (key, sentence, passage, score)
                    position += 1
            if best is None:
                continue
            _, sentence, passage, score = best
            basis = "word_overlap"
            if score == 0:
                sentence, passage, basis = _opening(passages[0].text), passages[0], "opening"
            examples.append({
                "rule": number, "sentence": sentence, "record_id": passage.record_id, "evidence_id": passage.evidence_id,
                "dataset": dataset, "title": passage.title,
                "publisher": passage.publisher or getattr(passage, "account", "") or "", "sponsor": passage.sponsor,
                "published_at": passage.published_at.isoformat() if passage.published_at else None,
                "overlap": score, "basis": basis,
            })
    return examples


def example_choice_line(sentence, choice, is_chinese=False):
    """The draft line a click on an example adds to the rules (the human may edit, keep or delete it)."""
    if choice not in ("counts", "does_not_count"):
        raise ValueError("choice must be counts or does_not_count")
    if is_chinese:
        return f"含有“{sentence}”这样的说法也算" if choice == "counts" else f"“{sentence}”这类不算"
    return f'A statement like "{sentence}" also counts.' if choice == "counts" else f'"{sentence}" does not count.'


def _plain(text):
    text = str(text or "").casefold()
    text = re.sub(r"[\"“”‘’']", "", text)
    return " ".join(text.split()).strip(" .。!！?？;；,，:：")


def quoted_examples(criterion, examples):
    """Which shown examples the confirmed rules quote (recorded, never refused: decision 2 of 2026-10-27)."""
    rules = _plain(" ".join([*criterion.get("counts", []), *(criterion.get("does_not_count") or [])]))
    return [{"example": number, "rule": item["rule"], "record_id": item["record_id"], "evidence_id": item["evidence_id"]}
            for number, item in enumerate(examples) if _plain(item["sentence"]) and _plain(item["sentence"]) in rules]


# --- What the judgment covers, and the card's wording (design 3.9, 3.5) ----------------------------


def candidate_summary(totals, evidence, condition, phrase_hits=None):
    """Per collection: the scope, the retrieved candidates, and what phase 2 reads (design 3.9).

    The card promises exactly what _list_answer does after a confirmation: every record with
    text of a scope up to TRIAGE_ALL_MAX ("whole_scope"), every retrieved candidate of a larger
    one ("candidates"), with no stopping rule, through the Decisions triage when it is on and
    screening alone otherwise. `with_rules` is that coverage with a confirmed or written
    criterion; `condition_only` the same when the stated condition is confirmed without rules
    (screening by the question; a quoted-phrase list reads every record containing the phrases
    first, `phrase_hits` counted by the same search phase 2 runs).
    """
    summary = {}
    for dataset, total in totals.items():
        retrieved = len({item.record_id for item in evidence if getattr(item, "dataset", None) == dataset})
        whole = total <= TRIAGE_ALL_MAX
        item = {"scope_total": total, "retrieved": retrieved, "with_rules": "whole_scope" if whole else "candidates",
                "condition_only": None}
        if condition in CONDITIONS_WITHOUT_RULES:
            item["condition_only"] = ("whole_scope" if whole else "phrase_hits_and_candidates" if condition == "phrases"
                                      else "candidates")
        if phrase_hits and dataset in phrase_hits:
            item["phrase_hits"] = phrase_hits[dataset]
        summary[dataset] = item
    return summary


def confirmation_text(question, candidates, condition, criterion, phrases=()):
    """The card's prose: who the judgment covers, then what the researcher is asked to confirm."""
    zh = chinese(question)
    quoted = "、".join(f"“{p}”" for p in phrases) if zh else ", ".join(f"“{p}”" for p in phrases)
    lines = []
    for dataset, item in candidates.items():
        noun = ("帖子" if dataset == "social" else "广告") if zh else ("posts" if dataset == "social" else "ads")
        total, retrieved, only = item["scope_total"], item["retrieved"], item["condition_only"]
        if zh:
            rules = "下面的规则" if criterion else "你写的规则"
            if item["with_rules"] == "whole_scope":
                lines.append(f"范围内有正文的 {total} 篇{noun}都会按{rules}判定" + ("；例句来自最相关的几篇。" if criterion else "。"))
            else:
                lines.append(f"范围内有 {total} 篇{noun}，检索到的 {retrieved} 篇候选都会按{rules}判定；规则选错会漏掉候选之外的，请在这里确认。")
            if only == "whole_scope":
                lines.append(f"只确认判定条件而不写规则时，按问题筛查范围内有正文的 {total} 篇{noun}。")
            elif only == "phrase_hits_and_candidates":
                lines.append(f"只确认判定条件而不写规则时，先读含有{quoted}的每一篇（目前 {item.get('phrase_hits', 0)} 篇），再按问题筛查这 {retrieved} 篇候选。")
            elif only == "candidates":
                lines.append(f"只确认判定条件而不写规则时，按问题筛查这 {retrieved} 篇候选。")
        else:
            rules = "the rules below" if criterion else "the rules you write"
            if item["with_rules"] == "whole_scope":
                lines.append(f"All {total} {noun} in your selection with readable text will be judged by {rules}"
                             + ("; the example sentences come from the most relevant ones." if criterion else "."))
            else:
                lines.append(f"Your selection has {total} {noun}; all {retrieved} retrieved candidates will be judged by {rules}. "
                             f"A wrong rule misses {noun} outside the candidates, so confirm the rules here.")
            if only == "whole_scope":
                lines.append(f"If you only confirm the stated condition, all {total} {noun} with readable text are screened by the question.")
            elif only == "phrase_hits_and_candidates":
                lines.append(f"If you only confirm the stated condition, every item containing {quoted} "
                             f"({item.get('phrase_hits', 0)} so far) is read first, then all {retrieved} retrieved candidates, by the question.")
            elif only == "candidates":
                lines.append(f"If you only confirm the stated condition, all {retrieved} retrieved candidates are screened by the question.")
    if zh:
        asks = {
            "draft": "请确认下面的规则，或改宽改窄；现在还没有判定任何一篇。",
            "draft_failed": "规则起草失败。请自己写规则，或只看检索结果；没有规则就不判定。",
            "phrases": f"列出的每一篇都必须含有{quoted}；问题的其余条件按正文判定。请确认，或为其余条件写规则。",
            "relation_hint": "每条候选帖子已由来源记录满足所选关系；只判定问题的其余条件。请确认，或为其余条件写规则。",
            "triage_off": "没有判定规则（分流已关闭）：筛查只按问题找句子。请确认，或写规则给筛查用。",
        }
    else:
        asks = {
            "draft": "Confirm the rules below, or adjust them; nothing has been judged yet.",
            "draft_failed": "The rules could not be drafted. Write them yourself, or only browse the retrieved candidates; "
                            "nothing is judged without rules.",
            "phrases": f"Every listed item must contain {quoted}; the question's other conditions are judged from the text. "
                       "Confirm, or write rules for them.",
            "relation_hint": "Every candidate post already satisfies the relation by its source record; only the question's "
                             "other conditions are judged. Confirm, or write rules for them.",
            "triage_off": "No judging rules are in use (the Decisions triage is off): screening looks for a sentence that "
                          "answers the question. Confirm, or write rules for the screening to use.",
        }
    lines.append(asks[condition])
    return "\n\n".join(lines)


# --- The unconfirmed marking of auto mode (decision 1) -----------------------------------------------

UNCONFIRMED_NOTE = {"en": "The inclusion rules were drafted by the model from the question and not confirmed by a researcher.",
                    "zh": "判定规则由模型从问题起草，未经研究者确认。"}


def mark_unconfirmed(answer, question):
    """Say in the list's first paragraph that its rules are an unconfirmed model draft."""
    head, separator, rest = answer.partition("\n\n")
    note = UNCONFIRMED_NOTE["zh" if chinese(question) else "en"]
    return (head + ("" if chinese(question) else " ") + note) + separator + rest


# --- Refusals ----------------------------------------------------------------------------------------

_REFUSALS = {
    "continuation_invalid": {
        None: ("This confirmation is no longer valid; ask the question again.", "这次确认已失效，请重新提问。"),
        "data_changed": ("The collection was updated since the rules were shown; ask the question again.",
                         "数据更新了，这次确认已失效，请重新提问。"),
        "flow_failed": ("The judging for this confirmation failed; ask the question again.",
                        "这次确认的判定失败了，请重新提问。"),
    },
    "continuation_in_progress": {None: ("This list is being judged; wait for the result.", "正在判定中，请稍候。")},
    "continuation_conflict": {None: ("This question was already judged by another set of rules; ask it again to judge by new rules.",
                                     "冲突：这道题已按另一份规则判定。要换规则，请重新提问。")},
    "criterion_invalid": {
        None: ("The rules could not be used; check them and submit again.", "规则无法使用，请检查后再提交。"),
        "no_rules": ("Give at least one rule.", "至少写一条规则。"),
        "too_many_rules": (f"At most {MAX_RULES} rules.", f"规则最多 {MAX_RULES} 条。"),
        "too_many_exclusions": (f"At most {MAX_EXCLUSIONS} exclusions.", f"例外最多 {MAX_EXCLUSIONS} 条。"),
        "rules_required": ("Write at least one rule, or only browse the retrieved candidates; nothing is judged without rules.",
                           "请至少写一条规则，或只看检索结果；没有规则就不判定。"),
    },
    "confirmation_registry_full": {None: ("Too many confirmations are being judged right now; try again in a few minutes.",
                                          "正在判定的确认太多，请几分钟后再试。")},
    "confirmation_unavailable": {None: ("The confirmation could not be prepared in time; ask the question again.",
                                        "这次确认没能及时准备好，请重新提问。")},
}
_REFUSAL_STATUS = {"confirmation_registry_full": "limited", "confirmation_unavailable": "service_unavailable"}


def refusal(reason, detail=None, question="", **fields):
    """A clear refusal that spends nothing and is never supplemented from the web (the reason is protected)."""
    texts = _REFUSALS[reason]
    text = texts.get(detail, texts[None])[1 if chinese(question) else 0]
    return Answer(status=_REFUSAL_STATUS.get(reason, "insufficient_evidence"),
                  answer_mode="clarification", failure_reason=reason, answer=text,
                  structured_result={"kind": reason, "detail": detail,
                                     "limits": {"max_rules": MAX_RULES, "max_exclusions": MAX_EXCLUSIONS}},
                  **fields)
