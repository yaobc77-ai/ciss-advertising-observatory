"""One record of how a question is handled: the QuestionPlan (pipeline steps 1-3).

"How to handle this question" used to be decided in several places: the regex
contract (question_policy), the research agent's final tool (run.route), the
list rule inside the evidence route and the web-supplement rules. Step 1
(2026-10-26) mirrored those decisions into one structure written to the run
record (research_trace["question_plan"]) and compared with what happened
(research_trace["plan_check"]). Step 2: the evidence route
(service._answer_evidence) reads its decisions from the plan - shape, list
kind, quoted phrases, source reading, web permission - instead of recomputing
them from the question. The research agent path builds the plan once in
service._answer_with_tools; every other caller (legacy path, composite parts,
the collection-first fallback, direct calls) gets one from build_evidence_plan,
so each rule exists once. Step 3 (S3-a): one list implementation over one or both
collections (service._list_answer), so a literal question over both is matched
literally in each. See docs/architecture/pipeline_current_vs_target.zh-CN.md,
section 4, steps 1-3.

Everything here is pure: no database, model or network access. The plan is
built from the understanding stage only (question, user scope, agent run,
narrowed scope), never from the answer, so plan_check stays an independent
comparison.

`structured_queries.QuestionPlan` is the legacy path's own plan; it is unrelated
and stays until step 6 decides the legacy path's future.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from .entities import field_of, mentioned_in, registry
from .list_screening import pure_literal_question, quoted_phrases
from .question_policy import (
    _DISCLOSURE,
    _FRAMING,
    _GROUPING_REQUEST,
    _LABEL_PREDICATE,
    _MENTION,
    _QUOTED_LITERAL,
    _RELATIVE_CALENDAR,
    _TITLE_LOCATOR,
    _literal_date_scope,
    _unsupported_subyear_dates,
    original_metadata_question,
    question_contract,
    restricts_to_named_source,
    sources_content_request,
)
from .structured_queries import _YEAR_OR_DAY

# v2 (step 2) added wants_list, phrases, original_metadata, read_sources and
# coverage_note_rule; v1 plans recorded by step 1 lack them. v3 (step 3, S3-a):
# list_kind "literal" also for a quoted-phrase question over both collections,
# which v2 recorded as "screen" to mirror the former two-collection function.
# v4 (step 3, S3-b) adds criterion_mode and criterion_available.
PLAN_VERSION = "question-plan-v4"
# The planner's declaration that every matching source is wanted.
PLANNER_LIST = "every_matching_source"

# The user restricted the answer to the collection or current selection. Kept
# identical to service._COLLECTION_ONLY; the service imports this one.
COLLECTION_ONLY = re.compile(
    r"\bonly (?:use|using|from|in)\b|\bin (?:this|the selected|the current) (?:collection|selection) only\b"
    r"|仅使用|只使用|只用|仅限|仅根据|只根据", re.I)

# Agent routes grouped into the target vocabulary (doc section 2.2).
_ROUTE_GROUPS = {
    "statistics": "statistics", "metadata": "metadata", "evidence": "evidence", "composite": "composite",
    "graph": "records", "sources": "records", "record": "records",
    "claims": "claims", "content_matches": "claims",
    "clarify": "clarify", "limited": "limited", "unavailable": "unavailable",
}
# Routes whose answer may be supplemented from the web when the collection cannot
# answer (service._ensure_answer accepts any insufficient_evidence result; the
# other routes return structured data or an outage, never that status).
_WEB_ROUTES = {"evidence", "composite", "clarify"}
# Routes that return rows or fields rather than prose.
_TABLE_ROUTES = {"statistics", "metadata", "records", "claims"}


@dataclass(frozen=True)
class QuestionPlan:
    """The merged decision for one question. Fields follow doc section 2.2.

    The evidence route reads shape, list_kind, datasets, search_query, allow_web,
    wants_list, phrases, original_metadata, read_sources and coverage_note_rule.
    `reasons` says how each decision was made; `signals` keeps the raw inputs.
    """

    route: str
    agent_route: str
    shape: str
    list_kind: str | None
    datasets_requested: list[str]
    datasets: list[str]
    filters: dict[str, Any]
    search_query: str | None
    allow_web: bool
    clarify_message: str | None
    failure_reason: str
    # The user asked for every matching source (rule or planner), even where no
    # list can be screened (a comparison, or labels over both collections).
    wants_list: bool = False
    # Quoted words or phrases: the ads containing them are read first.
    phrases: list[str] = field(default_factory=list)
    # A stored source field is asked for: no retrieval and no web page can answer it.
    original_metadata: bool = False
    # What the matching sources say is asked, not only which sources qualify.
    read_sources: bool = False
    # The surface rule selects or counts sources: a prose answer gets a retrieved-examples note.
    coverage_note_rule: bool = False
    # How a screened list's criterion is decided (step 3): "auto" drafts it from the question
    # and judges at once, "ask" stops for a human first (S3-c), "none" for lists without
    # model screening and for every other shape.
    criterion_mode: str = "none"
    # A criterion would be drafted: the Decisions triage is on and the list is screened
    # without quoted phrases or a relation hint. None when the caller did not say.
    criterion_available: bool | None = None
    reasons: dict[str, str] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    version: str = PLAN_VERSION

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(asdict(self))


def list_requested(question: str, declared_shape: str | None = None) -> bool:
    """A complete list is wanted when the surface rule or the planner says so (plan.md: either suffices)."""
    return bool(question_contract(question)["requires_complete_list"]) or declared_shape == PLANNER_LIST


def _datasets(dataset: str | None) -> list[str]:
    if dataset == "all" or dataset is None:
        return ["native", "social"]
    return [dataset]


def _compose(question: str, *, route: str, agent_route: str, route_reason: str, base_filters, effective,
             declared_shape, relation_listing, retrieval_groups, search_query, query_reason: str,
             clarify_message: str | None, failure_reason: str, triage_enabled=None,
             criterion_confirmation="auto") -> QuestionPlan:
    """The one place where a question's handling is decided, for both builders."""
    contract = question_contract(question)
    reasons: dict[str, str] = {"route": route_reason}
    filters_dump = effective.model_dump(mode="json")
    requested = _datasets(base_filters.dataset)
    datasets = _datasets(effective.dataset)
    reasons["datasets"] = "filters:narrowed" if effective is not base_filters else "filters:user"

    # The evidence route's step 1. A rule-detected list, the planner's declaration
    # or a relation listing each suffice; the rule and the planner are both kept.
    rule_list = bool(contract["requires_complete_list"])
    planner_list = declared_shape == PLANNER_LIST
    wants_list = rule_list or planner_list
    listing = relation_listing if isinstance(relation_listing, dict) else None
    # The planner says the relation filters are the question's whole condition;
    # honoured only when this read actually selected posts by a relation.
    relation_list = bool(listing and listing.get("list_all") and listing.get("selections")
                         and effective.dataset == "social" and effective.record_ids
                         and effective.record_ids != ["no-relation-match"])
    groups = bool(retrieval_groups)
    # Posts selected by a relation get a hint in the screening question (one social
    # collection only); such a list drafts no criterion.
    relation_hint = bool(listing and listing.get("selections") and effective.dataset == "social" and not relation_list)
    phrases = quoted_phrases(question)
    literal = pure_literal_question(question)
    # A list is screened in one collection, or in both when the user selected both
    # without labels; comparison groups (retrieval_groups) are never screened as lists.
    one_list = wants_list and not groups and effective.dataset in ("native", "social")
    both_list = wants_list and not groups and effective.dataset == "all" and not effective.labels
    list_mode = one_list or both_list or relation_list

    signals = {
        "rule_list": rule_list, "planner_shape": declared_shape, "relation_list": relation_list,
        "quoted_phrases": len(phrases), "pure_literal": literal, "retrieval_groups": groups,
        "collection_only": bool(COLLECTION_ONLY.search(question)), "relation_hint": relation_hint,
        "contract_task": contract.get("task"), "original_metadata_only": bool(contract.get("original_metadata_only")),
    }

    list_kind = None
    if route == "evidence" and list_mode:
        shape = "list"
        # One implementation lists over one or both collections (service._list_answer,
        # step 3): a relation selection, exact wording, or model screening per collection.
        if relation_list:
            list_kind = "relation"
        elif literal:
            list_kind = "literal"
        else:
            list_kind = "screen"
        if relation_list:
            reasons["shape"] = "planner:relation_listing"
        else:
            reasons["shape"] = "rule:requires_complete_list" if rule_list else "planner:answer_shape"
        if rule_list and planner_list:
            reasons["shape"] = "rule_and_planner"
    elif route in _TABLE_ROUTES:
        shape, reasons["shape"] = "table", f"route:{route}"
    elif route == "evidence":
        shape, reasons["shape"] = "answer", "default"
        if wants_list:
            # The user asked for a list but it cannot be screened here (a comparison, or
            # labels over both collections): recorded, and the answer gets a scope note.
            reasons["shape"] = "list_signal_not_screenable"
    else:
        shape, reasons["shape"] = "answer", f"route:{route}"

    # Web supplement: service._ensure_answer refuses when the user restricted the
    # answer to the collection; the evidence route also refuses after a screened
    # list (web pages are not advertisements). Integrity failures are decided by
    # the outcome, not the plan, so they are not mirrored here.
    if signals["collection_only"]:
        allow_web, reasons["allow_web"] = False, "rule:collection_only"
    elif route not in _WEB_ROUTES:
        allow_web, reasons["allow_web"] = False, f"route:{route}"
    elif shape == "list":
        allow_web, reasons["allow_web"] = False, "rule:list_screened"
    else:
        allow_web, reasons["allow_web"] = True, "default"

    query = None
    if route == "evidence":
        query = search_query or question
        reasons["search_query"] = query_reason

    # Step 3 (S3-b): only a model-screened list has a criterion. "auto" drafts it from the
    # question and judges at once (today's behaviour); "ask" means the researcher confirms it
    # first, so the list is judged only with a confirmed criterion (a caller passing one, or the
    # two-phase entry of S3-c); never a silent fallback from one to the other.
    if shape == "list" and list_kind == "screen":
        criterion_mode = "ask" if criterion_confirmation == "ask" else "auto"
        reasons["criterion_mode"] = "caller:ask" if criterion_mode == "ask" else "default:auto"
    else:
        criterion_mode, reasons["criterion_mode"] = "none", (f"kind:{list_kind}" if list_kind else f"shape:{shape}")
    # One meaning: this list would get a drafted criterion (the triage is on; screened list
    # without quoted phrases or a relation hint), whichever mode decides when it is confirmed.
    # `triage_enabled` may be a callable, asked only for a screened list (it may touch the
    # model client); None means the caller did not say.
    if criterion_mode == "none":
        criterion_available = None if triage_enabled is None else False
    else:
        on = triage_enabled() if callable(triage_enabled) else triage_enabled
        criterion_available = None if on is None else bool(on) and not phrases and not relation_hint

    return QuestionPlan(
        route=route, agent_route=agent_route, shape=shape, list_kind=list_kind,
        datasets_requested=requested, datasets=datasets, filters=filters_dump, search_query=query,
        allow_web=allow_web, clarify_message=clarify_message, failure_reason=failure_reason,
        wants_list=wants_list, phrases=phrases, original_metadata=original_metadata_question(question),
        read_sources=sources_content_request(question),
        coverage_note_rule=bool(contract["selects_sources"] or contract["requires_content_count"]),
        criterion_mode=criterion_mode, criterion_available=criterion_available,
        reasons=reasons, signals=signals,
    )


def build_question_plan(question: str, base_filters, run, narrowed_filters=None, *, triage_enabled=None,
                        criterion_confirmation="auto") -> QuestionPlan:
    """The plan for a question the research agent understood.

    `run` is the ResearchRun (route, result, failure_reason); `narrowed_filters`
    is the Filters the evidence branch computed (model validation, share-scope
    check and _list_over_selection), passed in so this function never repeats
    narrowing. Only understanding-stage inputs are used: the answer itself is
    never consulted.
    """
    data = run.result if isinstance(getattr(run, "result", None), dict) else {}
    agent_route = str(getattr(run, "route", "") or "unavailable")
    route = _ROUTE_GROUPS.get(agent_route, "unavailable")
    effective = narrowed_filters if (route == "evidence" and narrowed_filters is not None) else base_filters
    query = data.get("search_query") or data.get("query")
    message = data.get("message")
    return _compose(
        question, route=route, agent_route=agent_route,
        route_reason=("agent:last_tool" if agent_route not in {"clarify", "limited", "unavailable"}
                      else f"agent:{agent_route}"),
        base_filters=base_filters, effective=effective, declared_shape=data.get("answer_shape"),
        relation_listing=data.get("relation_listing"), retrieval_groups=data.get("retrieval_groups"),
        search_query=query, query_reason="planner" if query else "default:question",
        clarify_message=message if route == "clarify" and isinstance(message, str) else None,
        failure_reason=str(getattr(run, "failure_reason", "") or ""),
        triage_enabled=triage_enabled, criterion_confirmation=criterion_confirmation,
    )


def build_evidence_plan(question: str, filters, *, search_query=None, declared_shape=None,
                        relation_listing=None, retrieval_groups=None, triage_enabled=None,
                        criterion_confirmation="auto", agent_route="direct",
                        route_reason="caller:evidence") -> QuestionPlan:
    """The plan for an evidence-route call that has no research run.

    Used by the legacy path, composite question parts, the collection-first
    fallback and direct calls: the same decisions as build_question_plan over the
    same scope, with the caller's search query and declared shape. A list that
    skipped the research agent (agent_needed) records `agent_route="skipped"` and
    `route_reason=SKIPPED_AGENT_REASON`.
    """
    return _compose(
        question, route="evidence", agent_route=agent_route, route_reason=route_reason,
        base_filters=filters, effective=filters, declared_shape=declared_shape,
        relation_listing=relation_listing, retrieval_groups=retrieval_groups,
        search_query=search_query, query_reason="caller" if search_query else "default:question",
        clarify_message=None, failure_reason="", triage_enabled=triage_enabled,
        criterion_confirmation=criterion_confirmation,
    )


# --- Lists that need no research agent (latency round 2, item 1; 2026-11-08) -------------------------
#
# The research agent (1-2 model calls over an 8-9k token tool prompt) decides a question's route,
# may narrow the scope to names and dates the question grounds, and writes the English search
# query. For a list question the surface rule already recognises, in which the checks below find
# no scope word, name, date or shape the agent could act on, the service may skip it
# (Settings.list_without_agent). The checks are a conservative heuristic over the question's
# surface, not a proof that the agent would have changed nothing (an unregistered lowercase
# source after a determiner, "in the beacon", passes them), which is why the switch exists; it
# is on by default since 2026-11-08, after the effect was measured on two questions (plan.md).
# `agent_needed` says why the agent still runs; None means the list may skip it. The form
# accepted is positive and narrow: a list head ("which/list/show/find
# ... ads/articles/records (that)"), then a content condition over topic words, over the native
# collection, with no name, date, label, record reference, dataset word, grouping, comparison,
# exclusion, digit, acronym or capitalised word left in it, and nothing between the source noun
# and the content predicate ("which ads in acme review mention ..." keeps the agent). Anything
# else keeps the agent.
SKIPPED_AGENT_REASON = "rule:list_without_agent"
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_COMPARE = re.compile(r"\b(?:compare[ds]?|comparison|versus|vs\.?|difference between|differ(?:s|ed)?)\b|比较|对比|区别", re.I)
_AGGREGATE = re.compile(
    r"\b(?:the\s+most|most\s+(?:often|frequently|common(?:ly)?)|least|fewest|top\s+\d+|highest|largest|"
    r"majority|per\s+(?:year|month|outlet|sponsor|publisher)|by\s+year|over\s+time|trend)\b|最多|最少|最常|趋势", re.I)
_RECORD_REFERENCE = re.compile(
    r"\b(?:this|that|these|those)\s+(?:ads?|advertisements?|articles?|posts?|records?)\b"
    r"|\bthe\s+(?:selected|current|above|open|displayed)\b|\bwhich\s+sources?\b"
    r"|\b(?:NC|SC)[_-]?[A-Za-z]*\d\w*\b|\brecords?\s+(?:ids?|#|no\.?|numbers?)\b"
    r"|\b(?:previous|earlier|prior|last|above|current|first|second)\s+(?:results?|answers?|lists?|selection|search(?:es)?|batch|round)\b"
    r"|这(?:篇|条|则|个|些)|当前(?:广告|文章|帖子|记录)|选中|记录\s*(?:编号|ID)|上(?:一)?(?:次|轮)(?:的)?(?:结果|名单)", re.I)
_LABEL_WORDS = re.compile(r"\b(?:labels?|labell?ed|tags?|tagged)\b|标签", re.I)
_EXCLUSION = re.compile(r"\b(?:other\s+than|except|excluding|not\s+sponsored\s+by|besides)\b|除了|以外|之外", re.I)
_YEAR = re.compile(rf"(?<![A-Za-z0-9_-]){_YEAR_OR_DAY}(?![A-Za-z0-9_-])")
# The list head: a list cue and the source noun, optionally "that"/"which"/"in the collection".
_LIST_HEAD = re.compile(
    r"^\s*(?:which|list|show(?:\s+me)?|find|give\s+me)\s+(?:of\s+)?(?:the\s+|all\s+(?:of\s+)?(?:the\s+)?|every\s+|any\s+|me\s+)?"
    r"(?:native\s+)?(?:ads?|advertisements?|articles?|records?)\b\s*(?:that|which|in\s+the\s+collection|in\s+the\s+selection)?\s*", re.I)
# Words that bind a name to a source role, or name a source dimension, in the remainder.
_SOURCE_ROLE = re.compile(
    r"\b(?:sponsored|paid\s+for|published|posted|placed|run|written)\s+by\b"
    r"|\b(?:by|from)\s+(?!the\s+(?:same|way|time|text|start|end|sea|ground|harbor)\b)(?:the\s+|a\s+|an\s+)?[\w&.'-]+"
    r"|\b(?:accounts?|outlets?|publishers?|sponsors?|advertisers?|platforms?|companies|company)\b", re.I)
_CURLY_QUOTED = re.compile(r"“[^”]*”")
# What may stand between the list head and the content predicate: a relative pronoun, an adverb,
# a negation. The predicate itself is one of the contract's content cues (_MENTION, _FRAMING,
# _DISCLOSURE) or "about".
_PREDICATE_PREFIX = re.compile(
    r"^(?:(?:that|which|who)\s+)?(?:(?:also|explicitly|clearly|directly|openly|ever|still|really)\s+)?"
    r"(?:(?:do|does|did)\s+not\s+|(?:don't|doesn't|didn't)\s+)?", re.I)
_ABOUT = re.compile(r"(?:about|on\s+the\s+topic\s+of)\b", re.I)
# After the predicate, a preposition whose object is not a determiner phrase may name a source
# ("in gazette weekly", 'in "Acme Review"'): the agent decides. Idioms are listed so "in general",
# "in favour of" stay topic words; "in the harbor" is a determiner phrase.
_PREPOSITIONAL_OPERAND = re.compile(
    r"\b(?:in|on|at|via|through|within|across|among|inside)\s+"
    r"(?!(?:the|a|an|their|its|our|your|his|her|this|that|these|those|any|all|some|each|every|which|what|how|"
    r"general|particular|detail|short|favou?r|order|terms|turn|total|fact|part|full|line|response|return|light|"
    r"addition|spite|place|time|front|case|common|practice|principle|effect|essence|brief|other|both|one|two)\b)"
    r"[\w&.'-]+", re.I)
_QUOTED_WORD = " quotedphrase "  # stands in for a quoted segment so its syntactic place stays visible
# A quoted segment is a literal condition only as the predicate's direct object ('mention "tidal
# kite"', 'mention the phrase "x" or "y"'); anywhere else it names a source or a record.
_QUOTED_OBJECT = re.compile(
    r"^(?:(?:that|which|who)\s+)?(?:(?:also|explicitly|clearly|directly|openly|ever|still|really)\s+)?"
    r"(?:(?:do|does|did)\s+not\s+|(?:don't|doesn't|didn't)\s+)?[\w'-]+(?:\s+(?:to|out))?\s+(?:the\s+)?(?:exact\s+)?"
    r"(?:(?:words?|phrases?|terms?|expressions?|wording)\s+)?quotedphrase(?:\s*(?:,|or|and|/)\s*quotedphrase)*", re.I)
# A source frame after the predicate: "published in ...", or a preposition whose object phrase ends
# in a publication, platform, account or record word (whatever determiners and adjectives precede it).
_SOURCE_NOUN = (
    r"(?:quotedphrase|gazette|review|times|post|daily|journal|magazine|news|newspaper|outlets?|publications?|sites?|"
    r"websites?|platforms?|accounts?|pages?|feeds?|channels?|columns?|sections?|editions?|issues?|papers?|tabloid|"
    r"herald|tribune|chronicle|observer|guardian|telegraph|bulletin|dispatch|digest|press|wire|broadcast|network|"
    r"collection|dataset|database|archive|corpus|results?|selection|lists?|search(?:es)?|batch|round)")
_SOURCE_FRAME = re.compile(
    r"\b(?:published|posted|placed|printed|carried|appeared|appearing|ran|run|running|aired|distributed|sponsored|paid)\s+"
    r"(?:in|on|at|by|via|through|within)\b"
    rf"|\b(?:in|on|at|via|through|within|across|among|inside)\s+(?:(?:the|a|an|their|its|our|your|his|her|this|that|these|those|"
    rf"any|all|some|each|every)\s+)?(?:[\w&'-]+\s+){{0,5}}?{_SOURCE_NOUN}\b", re.I)
# A capitalised word that does not open a sentence (language._NAME), and an all-caps token.
_NAME_WORD = re.compile(r"(?<![.!?:]\s)(?<!^)\b[A-ZÀ-Þ][\w'’.-]*", re.M)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
_NAME_DIMENSIONS = ("sponsors", "publishers", "accounts")


def _dates_in(text: str) -> bool:
    if _YEAR.search(text) or _unsupported_subyear_dates(text) or _RELATIVE_CALENDAR.search(text):
        return True
    try:
        return _literal_date_scope(text) is not None
    except ValueError:
        return True  # several dates, or wording the scope parser refuses: the agent decides


def agent_needed(question: str, filters, names, *, setting: bool = True) -> str | None:
    """Why the research agent still runs for this question; None when the rule-detected list may skip it.

    A conservative surface heuristic: every check that fails names a reason, and None says only
    that none of the checks fired, not that the agent would have decided the same. `filters` is
    the active scope, `names` the collection's source names by dimension
    ({"sponsors": [...], "publishers": [...], "accounts": [...]}, from db.facets) or None when
    they could not be read. Pure: regexes and the entity registry only. The reason strings are
    recorded in the run (research_trace["agent_kept"]) so the share of lists each check keeps
    can be read later.
    """
    if not setting:
        return "setting:off"
    if names is None:
        return "names:unavailable"
    contract = question_contract(question)
    if not contract["requires_complete_list"]:
        return "rule:not_a_complete_list"
    for key in ("compound_read_request", "original_metadata_only", "record_fields_lookup", "requires_content_count"):
        if contract[key]:
            return f"contract:{key}"
    if contract["explicit_datasets"] and contract["explicit_datasets"] != [filters.dataset]:
        return "dataset:named_in_question"
    if filters.dataset != "native":
        return f"dataset:{filters.dataset}"
    if len(filters.record_ids) == 1:
        return "selection:one_record"
    if _CJK.search(question):
        return "language:cjk"
    text = re.sub(r"\s+", " ", question).strip()
    if _LABEL_PREDICATE.search(text) or _LABEL_WORDS.search(text):
        return "scope:labels"
    if _RECORD_REFERENCE.search(text):
        return "scope:record_reference"
    if _TITLE_LOCATOR.search(text):
        return "scope:title_locator"
    if _GROUPING_REQUEST.search(text) or _AGGREGATE.search(text):
        return "shape:grouping_or_aggregate"
    if _COMPARE.search(text):
        return "shape:comparison"
    if _EXCLUSION.search(text):
        return "scope:exclusion"
    if _dates_in(text):
        return "scope:dates"
    # A name the question mentions keeps the agent (it may narrow to it), unless that name is the
    # one value selected in its dimension: then the question's scope is the current scope. With
    # several values selected the question may ask for one of them, so the agent decides.
    alone = {}
    for dimension in _NAME_DIMENSIONS:
        chosen = [str(v) for v in (getattr(filters, dimension, None) or [])]
        alone[dimension] = chosen[0] if len(chosen) == 1 else None
        for value in names.get(dimension) or []:
            value = str(value)
            if not value or value == "(Unknown)" or (alone[dimension] or "").casefold() == value.casefold():
                continue
            if mentioned_in(value, text, dimension) or restricts_to_named_source(text, value):
                return f"scope:name:{value}"
    # The positive form: the list head, at once the content predicate ("that/which (also)
    # mention|present|... " or "about"), then topic words. Anything between the source noun and
    # the predicate ("in acme review", "among the previous results") keeps the agent.
    head = _LIST_HEAD.match(text)
    if head is None:
        return "form:no_list_head"
    rest = text[head.end():]
    body = rest[_PREDICATE_PREFIX.match(rest).end():]
    if not (_MENTION.match(body) or _FRAMING.match(body) or _DISCLOSURE.match(body) or _ABOUT.match(body)):
        return "form:no_content_predicate_first"
    # A quoted segment is a literal condition only as the predicate's object ('mention "tidal kite"');
    # as the object of by/from/in it names a source ('kites from "Acme Review"'), so the quoted text
    # is replaced by a plain word, never removed, before the syntax is inspected.
    view = _QUOTED_LITERAL.sub(_QUOTED_WORD, _CURLY_QUOTED.sub(_QUOTED_WORD, rest))
    if _SOURCE_ROLE.search(view):
        return "scope:source_role_words"
    quoted = _QUOTED_OBJECT.match(view)
    if view.count(_QUOTED_WORD.strip()) > (quoted.group(0).count(_QUOTED_WORD.strip()) if quoted else 0):
        return "scope:quoted_operand"
    if _SOURCE_FRAME.search(view):
        return "scope:source_frame"
    if _PREPOSITIONAL_OPERAND.search(view):
        return "scope:prepositional_operand"
    if re.search(r"\d", view):
        return "scope:digits"
    # "API" when sponsors=["api"] is the one selected sponsor names the scope, not a narrowing: the
    # selected name's recorded forms are taken out before the remaining tokens are inspected.
    for dimension in _NAME_DIMENSIONS:
        for form in (_scope_forms(alone[dimension], dimension) if alone[dimension] else ()):
            view = re.sub(rf"(?<![^\W_]){re.escape(form)}(?![^\W_])", " ", view, flags=re.I)
    acronym = _ACRONYM.search(view)
    if acronym:
        return f"scope:acronym:{acronym.group(0)}"
    for token in (m.group(0) for m in _NAME_WORD.finditer(view)):
        if token != "I":
            return f"scope:capitalised:{token}"
    return None


def _scope_forms(value: str, dimension: str) -> tuple[str, ...]:
    """Every recorded spelling of the selected source name (entities registry), or the value itself."""
    field = field_of(dimension)
    entity = registry().entity_of(value, field) if field else None
    return tuple(entity.surface_forms()) if entity else (value,)


def plan_check(plan: dict[str, Any], result) -> dict[str, Any]:
    """Compare the recorded plan with the final answer. Unknown is None, never a mismatch.

    Run after the outer web supplement (service._ensure_answer) so the "web"
    comparison sees every place a supplement can happen.
    """
    trace = result.research_trace or {}
    external = result.external_research or trace.get("external_web") or {}
    web_attempted = bool(external) and external.get("status") not in (None, "disabled") \
        and external.get("reason") != "scope_not_supported"
    actual: dict[str, Any] = {
        "status": result.status, "answer_mode": result.answer_mode, "failure_reason": result.failure_reason,
        "web_attempted": web_attempted, "web_status": external.get("status") if external else None,
    }
    if "list_screening" in trace:
        actual["shape"] = "list"
    elif result.answer_mode == "statistics" or (result.answer_mode == "tools" and result.structured_result is not None):
        actual["shape"] = "table"
    elif result.answer_mode in ("rag", "web_supplement") and result.status == "answered":
        actual["shape"] = "answer"
    else:
        actual["shape"] = None  # clarification, outage or no answer: shape unknown

    shape_matches = None if actual["shape"] is None else actual["shape"] == plan.get("shape")
    # A plan that forbids the web must never see an attempt; a plan that allows
    # it may or may not need one, so only the forbidden case can mismatch.
    web_matches = None
    if web_attempted:
        web_matches = bool(plan.get("allow_web"))
    # Step 3: the criterion the list was judged by must be the kind the plan called for. A list
    # never judged (no screened list) is unknown; a model-screened list without a recorded
    # source is a mismatch; a literal or relation list has no source and needs none.
    screening = trace.get("list_screening") or {}
    source = screening.get("criterion_source")
    screened = screening.get("method") == "ai_screening"
    actual["criterion_source"] = source
    mode = plan.get("criterion_mode")
    pending = (result.structured_result or {}).get("kind") == "criterion_confirmation"
    if mode == "none":
        criterion_matches = not pending and (source == "none" or (source is None and not screened))
    elif mode in ("auto", "ask"):
        expected = ("draft_unconfirmed", "none") if mode == "auto" else ("confirmed", "edited")
        if pending:
            criterion_matches = mode == "ask"
        elif source is None:
            criterion_matches = False if screened else None
        else:
            criterion_matches = source in expected
    else:
        criterion_matches = None
    return {"version": plan.get("version"), "shape_matches": shape_matches, "web_matches": web_matches,
            "criterion_matches": criterion_matches, "actual": actual}
