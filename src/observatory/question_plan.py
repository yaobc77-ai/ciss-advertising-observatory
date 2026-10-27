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

from .list_screening import pure_literal_question, quoted_phrases
from .question_policy import (
    original_metadata_question,
    question_contract,
    sources_content_request,
)

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
                        criterion_confirmation="auto") -> QuestionPlan:
    """The plan for an evidence-route call that has no research run.

    Used by the legacy path, composite question parts, the collection-first
    fallback and direct calls: the same decisions as build_question_plan over the
    same scope, with the caller's search query and declared shape.
    """
    return _compose(
        question, route="evidence", agent_route="direct", route_reason="caller:evidence",
        base_filters=filters, effective=filters, declared_shape=declared_shape,
        relation_listing=relation_listing, retrieval_groups=retrieval_groups,
        search_query=search_query, query_reason="caller" if search_query else "default:question",
        clarify_message=None, failure_reason="", triage_enabled=triage_enabled,
        criterion_confirmation=criterion_confirmation,
    )


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
