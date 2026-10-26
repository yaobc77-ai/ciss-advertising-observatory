"""One record of how a question is handled: the QuestionPlan (pipeline step 1).

Today "how to handle this question" is decided in several places: the regex
contract (question_policy), the research agent's final tool (run.route), the
list rule in the evidence route and the web-supplement rules. This module only
*mirrors* those decisions into one structure that is written to the run record
(research_trace["question_plan"]) so the plan can be compared with what actually
happened (research_trace["plan_check"]). No branch reads the plan yet; see
docs/architecture/pipeline_current_vs_target.zh-CN.md, section 4, step 1.

Everything here is pure: no database, model or network access. A failure while
building or checking the plan must never change an answer, so callers wrap the
calls and fall back to leaving the keys out.

`structured_queries.QuestionPlan` is the legacy path's own plan; it is unrelated
and stays until step 6 decides the legacy path's future.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from .list_screening import pure_literal_question, quoted_phrases
from .question_policy import question_contract

PLAN_VERSION = "question-plan-v1"

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
    """The merged decision for one question. Fields follow doc section 2.2."""

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
    reasons: dict[str, str] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    version: str = PLAN_VERSION

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(asdict(self))


def _datasets(dataset: str | None) -> list[str]:
    if dataset == "all" or dataset is None:
        return ["native", "social"]
    return [dataset]


def build_question_plan(question: str, base_filters, run, narrowed_filters=None) -> QuestionPlan:
    """Mirror today's decisions for `question` into one plan.

    `run` is the ResearchRun (route, result, failure_reason); `narrowed_filters`
    is the Filters the evidence branch computed (model validation, share-scope
    check and _list_over_selection), passed in so this function never repeats
    narrowing. Only understanding-stage inputs are used: the answer itself is
    never consulted, so plan_check stays an independent comparison.
    """
    data = run.result if isinstance(getattr(run, "result", None), dict) else {}
    agent_route = str(getattr(run, "route", "") or "unavailable")
    route = _ROUTE_GROUPS.get(agent_route, "unavailable")
    contract = question_contract(question)
    reasons: dict[str, str] = {"route": "agent:last_tool" if agent_route not in {"clarify", "limited", "unavailable"}
                               else f"agent:{agent_route}"}

    effective = narrowed_filters if (route == "evidence" and narrowed_filters is not None) else base_filters
    filters_dump = effective.model_dump(mode="json")
    requested = _datasets(base_filters.dataset)
    datasets = _datasets(effective.dataset)
    reasons["datasets"] = "filters:narrowed" if effective is not base_filters else "filters:user"

    # Shape: the evidence route's step 1 (service._answer_evidence), reproduced
    # from the same inputs. A rule-detected list, the planner's declaration or a
    # relation listing each suffice; the rule and planner are both kept.
    rule_list = bool(contract["requires_complete_list"])
    declared_shape = data.get("answer_shape")
    planner_list = declared_shape == "every_matching_source"
    relation_listing = data.get("relation_listing") if isinstance(data.get("relation_listing"), dict) else None
    retrieval_groups = bool(data.get("retrieval_groups"))
    phrases = quoted_phrases(question)
    relation_list = bool(relation_listing and relation_listing.get("list_all") and relation_listing.get("selections")
                         and effective.dataset == "social" and effective.record_ids
                         and effective.record_ids != ["no-relation-match"])
    wants_list = rule_list or planner_list
    # Lists are screened in one collection, or in both when the user selected both
    # without labels; retrieval groups (comparisons) are never screened as lists.
    list_mode = wants_list and not retrieval_groups and (
        effective.dataset in ("native", "social") or (effective.dataset == "all" and not effective.labels))
    list_mode = list_mode or relation_list

    signals = {
        "rule_list": rule_list, "planner_shape": declared_shape, "relation_list": relation_list,
        "quoted_phrases": len(phrases), "pure_literal": bool(phrases) and pure_literal_question(question),
        "retrieval_groups": retrieval_groups, "collection_only": bool(COLLECTION_ONLY.search(question)),
        "contract_task": contract.get("task"), "original_metadata_only": bool(contract.get("original_metadata_only")),
    }

    list_kind = None
    if route == "evidence" and list_mode:
        shape = "list"
        if relation_list:
            list_kind, reasons["shape"] = "relation", "planner:relation_listing"
        elif signals["pure_literal"]:
            list_kind = "literal"
            reasons["shape"] = "rule:requires_complete_list" if rule_list else "planner:answer_shape"
        else:
            list_kind = "screen"
            reasons["shape"] = ("rule:requires_complete_list" if rule_list else "planner:answer_shape")
        if rule_list and planner_list:
            reasons["shape"] = "rule_and_planner"
    elif route in _TABLE_ROUTES:
        shape, reasons["shape"] = "table", f"route:{route}"
    elif route == "evidence":
        shape, reasons["shape"] = "answer", "default"
        if wants_list:
            # The user asked for a list but it cannot be screened here (a comparison, or
            # labels over both collections): recorded so step 2 sees the dropped signal.
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

    search_query = None
    if route == "evidence":
        search_query = data.get("search_query") or data.get("query") or question
        reasons["search_query"] = "planner" if (data.get("search_query") or data.get("query")) else "default:question"
    clarify_message = data.get("message") if route == "clarify" and isinstance(data.get("message"), str) else None

    return QuestionPlan(
        route=route, agent_route=agent_route, shape=shape, list_kind=list_kind,
        datasets_requested=requested, datasets=datasets, filters=filters_dump, search_query=search_query,
        allow_web=allow_web, clarify_message=clarify_message,
        failure_reason=str(getattr(run, "failure_reason", "") or ""), reasons=reasons, signals=signals,
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
    return {"version": plan.get("version"), "shape_matches": shape_matches, "web_matches": web_matches,
            "actual": actual}
