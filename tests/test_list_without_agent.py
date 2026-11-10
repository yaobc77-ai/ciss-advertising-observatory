"""Latency round 2, item 1: a list question the surface rule recognises, whose whole restriction is the
active filters, may run without the research agent (Settings.list_without_agent; on by default since
2026-11-08, OBS_LIST_WITHOUT_AGENT=false turns the skip off).

Fictional questions, names and records only (the golden fixtures of test_list_golden); every model call
is mocked. `question_plan.agent_needed` is pure and tested as a table: the accepted form is a list head,
at once a content predicate, then topic words over the native collection; every other shape, scope word,
name, date, label, record reference, digit, acronym or capitalised word keeps the agent. The service
tests go through Service.answer, so the shared tail (data-version guard, audit, plan record, saved run,
the two-phase card and its continuation) is covered with the switch on and off.
"""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_list_criterion_mode import CONFIRMED, roles, service_for
from test_list_golden import JOBS, LITERAL

from observatory.config import Settings
from observatory.criterion_confirmation import pending_confirmation
from observatory.models import Filters
from observatory.question_plan import SKIPPED_AGENT_REASON, agent_needed
from observatory.research_agent import ResearchRun
from observatory.service import NO_AGENT_POLICY

NATIVE = Filters(dataset="native")
NAMES = {"sponsors": ["tidal co", "harbor energy group", "imaginary oil", "bp", "api", "shell"],
         "publishers": ["Harbor Daily", "The Kite Post", "CNBC"], "accounts": []}


# --- The guard ------------------------------------------------------------------------------------------------

FAST = [
    "Which ads mention tidal kites?",
    "Which native ads mention tidal kites?",
    "List all ads that present hydrogen as a climate solution.",
    "Show me every ad that acknowledges climate risk.",
    "Find the ads that describe gas as a bridge fuel.",
    JOBS,  # "Which ads present tidal kites as a source of jobs?"
    LITERAL,  # 'Which ads mention "tidal kite"?': the quoted phrase is a literal condition, not a name
    "Which ads mention kites? Use only the collection.",  # a sentence-initial capital is not a name
    "Which of the ads mention kites and jobs?",
    "Which ads argue that gas is cleaner than coal?",
    "Which ads mention kites in the harbor?",
    "Which ads mention the total cost of kites?",  # "total" is a word here; no facet is named
    "Which ads discuss carbon capture and storage?",
    "Which ads that do not mention jobs discuss kites?",
    "Which ads mention jobs in general?",  # an idiom, not a source after "in"
    'Which ads mention the phrase "harbor power" in their text?',
    'Which ads mention "tidal kite" or "harbor"?',  # several literal conditions, all the predicate's object
    "Which ads mention kites in their text?",
]
KEPT = [
    # Not the accepted shape or scope.
    ("Which ads were sponsored by Imaginary Oil?", NATIVE, "rule:not_a_complete_list"),  # stored fields, no content condition
    ("What do the ads say about harbor power?", NATIVE, "rule:not_a_complete_list"),
    ("How many ads mention kites?", NATIVE, "rule:not_a_complete_list"),
    ("Which ads mention kites, and how many are there?", NATIVE, "contract:compound_read_request"),
    ("Which social media posts mention tidal kites?", NATIVE, "dataset:named_in_question"),
    ("Which ads discuss carbon capture?", Filters(dataset="all"), "dataset:all"),
    ("Which ads mention tidal kites?", Filters(dataset="social"), "dataset:social"),
    ("Which ads mention kites?", Filters(dataset="native", record_ids=["NC_1"]), "selection:one_record"),
    ("哪些广告提到潮汐风筝？", NATIVE, "language:cjk"),
    # Scope words the agent would turn into filters or a clarification.
    ("Which ads with label greenwashing mention jobs?", NATIVE, "scope:labels"),
    ("Which ads tagged safety mention kites?", NATIVE, "scope:labels"),
    ("Which ads among records NC_0012 and NC_0015 mention kites?", NATIVE, "scope:record_reference"),
    ("Which source contains this advertisement?", NATIVE, "scope:record_reference"),
    ("Which of these ads mention kites?", NATIVE, "scope:record_reference"),
    ('Which ads titled "Harbor Power Tomorrow" mention kites?', NATIVE, "scope:title_locator"),
    ("Which Twitter accounts post the most fossil fuel ads?", NATIVE, "shape:grouping_or_aggregate"),
    ("Which outlets ran ads about kites?", NATIVE, "shape:grouping_or_aggregate"),
    ("Which ads mention kites most often?", NATIVE, "shape:grouping_or_aggregate"),
    ("Which ads compare wind and solar?", NATIVE, "shape:comparison"),
    ("Which ads other than Tidal Co's mention kites?", NATIVE, "scope:exclusion"),
    ("Which ads in 2021 mention kites?", NATIVE, "scope:dates"),
    ("Which ads published after 2020 mention kites?", NATIVE, "scope:dates"),
    ("Which ads from last year mention kites?", NATIVE, "scope:dates"),
    ("Which ads mention kites in September 2019?", NATIVE, "scope:dates"),
    # Names: registered forms, source-role bindings, and unregistered names in any spelling.
    ("Which ads by Tidal Co mention safety?", NATIVE, "scope:name:tidal co"),
    ("Which ads from Harbor Daily discuss jobs?", NATIVE, "scope:name:Harbor Daily"),
    ("Which ads mention Harbor Energy Group's plans?", NATIVE, "scope:name:harbor energy group"),
    ("Which ads mention BP?", NATIVE, "scope:name:bp"),
    ("Which ads mention API?", NATIVE, "scope:name:api"),
    ("Which ads in acme review mention kites?", NATIVE, "form:no_content_predicate_first"),
    ('Which ads in "Acme Review" mention kites?', NATIVE, "form:no_content_predicate_first"),
    ("Which ads in “Acme Review” mention kites?", NATIVE, "form:no_content_predicate_first"),
    ("Which ads among the previous results mention kites?", NATIVE, "scope:record_reference"),
    ("Which ads by Acme mention kites?", NATIVE, "form:no_content_predicate_first"),
    ("Which ads on Facebook mention kites?", NATIVE, "form:no_content_predicate_first"),
    ("Which ads mention kites by acme?", NATIVE, "scope:source_role_words"),
    ("Which ads mention kites published by the gazette?", NATIVE, "scope:source_role_words"),
    ('Which ads mention kites from "Acme Review"?', NATIVE, "scope:source_role_words"),  # a quoted source after the predicate
    ("Which ads mention kites by “Acme”?", NATIVE, "scope:source_role_words"),
    ('Which ads mention kites in "Acme Review"?', NATIVE, "scope:quoted_operand"),  # quoted, but not the predicate's object
    ('Which ads mention kites published in the "Acme Review"?', NATIVE, "scope:quoted_operand"),
    ('Which ads mention kites in the "Acme Review" article?', NATIVE, "scope:quoted_operand"),
    ("Which ads mention kites published in the gazette?", NATIVE, "scope:source_frame"),  # a determiner does not clear the phrase
    ("Which ads mention kites in gazette weekly?", NATIVE, "scope:source_frame"),  # an unregistered lowercase source
    ("Which ads mention kites in the harbor gazette?", NATIVE, "scope:source_frame"),
    ("Which ads mention kites in their weekly column?", NATIVE, "scope:source_frame"),
    ("Which ads mention kites among the previous results?", NATIVE, "scope:record_reference"),
    ("Which ads mention investment in renewables?", NATIVE, "scope:prepositional_operand"),  # a topic too, kept on purpose
    ("Which ads mention the Paris Agreement?", NATIVE, "scope:capitalised:Paris"),
    ("Which ads mention CO2 removal?", NATIVE, "scope:digits"),
    ("Which ads mention 400 jobs?", NATIVE, "scope:digits"),
    ("Which ads mention the EU?", NATIVE, "scope:acronym:EU"),
]


@pytest.mark.parametrize("question", FAST)
def test_a_content_list_over_the_active_native_scope_needs_no_agent(question):
    assert agent_needed(question, NATIVE, NAMES) is None


@pytest.mark.parametrize("question, filters, reason", KEPT)
def test_everything_else_keeps_the_agent(question, filters, reason):
    assert agent_needed(question, filters, NAMES) == reason


def test_a_name_is_the_scope_only_when_it_is_the_one_selected_value_of_its_dimension():
    one = Filters(dataset="native", sponsors=["api"])
    assert agent_needed("Which ads mention API?", one, NAMES) is None  # the token names the current scope
    assert agent_needed("Which ads mention api's plans?", one, NAMES) is None
    two = Filters(dataset="native", sponsors=["api", "bp"])
    assert agent_needed("Which ads mention API?", two, NAMES) == "scope:name:api"  # one of two: the agent decides
    both = Filters(dataset="native", publishers=["Harbor Daily", "The Kite Post"])
    assert agent_needed("Which ads mention Harbor Daily?", both, NAMES) == "scope:name:Harbor Daily"
    only = both.model_copy(update={"publishers": ["Harbor Daily"]})
    assert agent_needed("Which ads mention Harbor Daily?", only, NAMES) is None  # a two-word selected name
    assert agent_needed("Which ads mention Harbor Daily and Acme?", only, NAMES) == "scope:capitalised:Acme"
    assert agent_needed("Which ads mention kites?", both, NAMES) is None  # no name: the scope is both
    assert agent_needed("Which ads mention kites?", Filters(dataset="native", record_ids=["NC_1", "NC_2"]), NAMES) is None


def test_the_switch_and_missing_names_keep_the_agent():
    assert agent_needed("Which ads mention kites?", NATIVE, NAMES, setting=False) == "setting:off"
    assert agent_needed("Which ads mention kites?", NATIVE, None) == "names:unavailable"
    assert agent_needed("Which ads mention kites?", NATIVE, {"sponsors": ["(Unknown)", ""]}) is None


# --- The service ----------------------------------------------------------------------------------------------


class NeverAgent:
    """A research agent that must not be asked."""

    def __init__(self):
        self.calls = []

    def run(self, question, filters, visitor, **_):
        self.calls.append(question)
        raise AssertionError("the research agent must not run for this question")


class StubAgent:
    """Returns one prepared ResearchRun, as the research agent would."""

    def __init__(self, run):
        self.result, self.calls = run, []

    def run(self, question, filters, visitor, **_):
        self.calls.append(question)
        self.result.original_question = question
        self.result.base_filters = filters.model_dump(mode="json")
        return self.result


FACETS = {"sponsors": ["Tidal Co"], "publishers": ["Harbor Daily"], "accounts": []}


def agent_service(name, monkeypatch, *, switch, agent):
    service, scenario, calls, ledger = service_for(name, monkeypatch)
    service.settings = replace(Settings(), research_agent_enabled=True, list_without_agent=switch)
    service.research_agent = agent
    service.db.facets = lambda dataset: FACETS
    return service, calls, ledger


def evidence_run(query=JOBS):
    return ResearchRun(route="evidence", result={"filters": Filters(dataset="native", include_inferred_dates=True).model_dump(mode="json"),
                                                 "search_query": query, "answer_shape": "every_matching_source"}, cost_usd=0.002)


def watch_downstream(service, after=None):
    """Record what the evidence route returned before the shared tail adds to it; `after` runs once it did."""
    seen, original = {}, service._answer_evidence

    def watched(*args, **kwargs):
        answer = original(*args, **kwargs)
        seen["cost"] = answer.cost_usd
        if after:
            after()
        return answer

    service._answer_evidence = watched
    return seen


def saved_plans(service):
    return [call.args[2].research_trace.get("question_plan") for call in service.db.save_answer.call_args_list]


def screened(calls):
    """Every screening call's ads with their passages, in call order: what the list route actually read."""
    return [call["ads"] for call in calls.by_dataset["native"]["screen"]]


def model_calls(calls):
    """How many screening, judging and shared (draft, embed, write) model calls the fixture has seen."""
    native = calls.by_dataset["native"]
    return len(native["screen"]), len(native["judge"]), len(calls.shared)


def billed(ledger):
    """What the recording budget settled, by the final state of each reservation."""
    settled = [row[5] for row in ledger.closed if len(row) > 3 and row[3] == "settled"]
    other = [row for row in ledger.closed if len(row) <= 3 or row[3] != "settled"]
    return sum(settled), [row[3] for row in other], dict(ledger.open)


def test_with_the_switch_on_a_rule_list_runs_without_the_agent_through_the_shared_tail(monkeypatch):
    never = NeverAgent()
    service, calls, ledger = agent_service("native_triage", monkeypatch, switch=True, agent=never)
    seen = watch_downstream(service)
    result = service.answer(JOBS, NATIVE, "offline")
    assert result.status == "answered" and never.calls == []
    trace = result.research_trace
    assert "list_screening" in trace and "criterion" in roles(calls)  # the list route ran as it does after the agent
    assert trace["policy"] == NO_AGENT_POLICY and trace["transport"] == "none"
    assert trace["model_calls"] == [] and trace["tools"] == [] and trace["cost_usd"] == 0.0  # the understanding stage spent nothing
    assert trace["agent_skipped"] == {"reason": SKIPPED_AGENT_REASON, "policy": NO_AGENT_POLICY}
    assert "agent_kept" not in trace and trace["data_version"] == "golden-v1"
    assert trace["original_question"] == JOBS and trace["base_filters"]["dataset"] == "native"
    assert trace["question_contract"]["requires_complete_list"] is True
    plan = trace["question_plan"]
    assert (plan["agent_route"], plan["route"], plan["shape"], plan["list_kind"]) == ("skipped", "evidence", "list", "screen")
    assert plan["reasons"]["route"] == SKIPPED_AGENT_REASON and plan["reasons"]["search_query"] == "default:question"
    assert plan["search_query"] == JOBS and plan["filters"]["dataset"] == "native"
    assert trace["plan_check"]["shape_matches"] is True and trace["plan_check"]["web_matches"] is None
    assert result.cost_usd > 0 and result.cost_usd == pytest.approx(seen["cost"])  # the list route's calls, nothing added
    total, other_states, left_open = billed(ledger)
    # The recording budget agrees: nothing left reserved, only the route's placeholder cancelled, and the
    # answer bills at least what was settled (the golden writer reports its own 0.002 outside the ledger).
    assert left_open == {} and set(other_states) <= {"cancelled"} and result.cost_usd >= total - 1e-9
    assert saved_plans(service)[-1]["agent_route"] == "skipped"  # the run row keeps the same plan


def test_the_same_question_with_the_switch_off_runs_the_agent_and_screens_the_same_ads(monkeypatch):
    stub = StubAgent(evidence_run())
    off, off_calls, _ = agent_service("native_triage", monkeypatch, switch=False, agent=stub)
    seen = watch_downstream(off)
    result = off.answer(JOBS, NATIVE, "offline")
    assert result.status == "answered" and stub.calls == [JOBS]
    plan = result.research_trace["question_plan"]
    assert plan["agent_route"] == "evidence" and plan["reasons"]["route"] == "agent:last_tool"
    assert "agent_kept" not in result.research_trace and "agent_skipped" not in result.research_trace  # nothing new when off
    assert result.cost_usd == pytest.approx(seen["cost"] + 0.002)  # the agent's own cost on top, as before

    on, on_calls, _ = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())
    skipped = on.answer(JOBS, NATIVE, "offline")
    # The agent's query equalled the question here, so the list route read the same ads, passages and
    # batches; on real data the plan's query is the question instead of the agent's rewrite (measured apart).
    assert screened(on_calls) == screened(off_calls) and screened(on_calls)
    assert skipped.research_trace["list_screening"]["matches"] == result.research_trace["list_screening"]["matches"]
    assert skipped.citations and [c.evidence_id for c in skipped.citations] == [c.evidence_id for c in result.citations]


def test_a_list_without_the_decisions_triage_also_runs_without_the_agent(monkeypatch):
    never = NeverAgent()
    service, calls, ledger = agent_service("native_screen", monkeypatch, switch=True, agent=never)
    result = service.answer(JOBS, NATIVE, "offline")
    assert result.status == "answered" and never.calls == [] and "criterion" not in roles(calls)  # nothing drafted: screening only
    assert result.research_trace["question_plan"]["agent_route"] == "skipped"
    assert result.research_trace["list_screening"]["criterion_source"] == "none"
    total, _, left_open = billed(ledger)
    assert left_open == {} and result.cost_usd >= total - 1e-9

    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert pending_confirmation(card) and card.structured_result["condition"]["kind"] == "triage_off" and never.calls == []
    judged = service.answer(JOBS, NATIVE, "offline", continuation={"token": card.structured_result["continuation"]})
    assert judged.status == "answered" and never.calls == []
    assert judged.research_trace["list_screening"]["confirmed_condition"] == "triage_off"
    assert judged.research_trace["question_plan"]["agent_route"] == "skipped"


UNKNOWN_SOURCE = "Which ads present tidal kites as a source of jobs in the beacon?"  # "the beacon": an unlisted lowercase name


def test_an_unknown_source_after_a_determiner_passes_the_checks_and_meets_the_agent_route_at_the_same_screening(monkeypatch):
    # The residual the checks accept on purpose. Today's agent route answers such a question by asking
    # for clarification and then searching the collection with the question (the collection-first
    # fallback); the fast path goes straight to that screening. Both read the same ads and passages.
    assert agent_needed(UNKNOWN_SOURCE, NATIVE, NAMES) is None
    clarify = StubAgent(ResearchRun(route="clarify", failure_reason="research_plan_clarification",
                                    result={"message": "Please name the outlet."}))
    off, off_calls, _ = agent_service("native_triage", monkeypatch, switch=False, agent=clarify)
    fallback = off.answer(UNKNOWN_SOURCE, NATIVE, "offline")
    assert clarify.calls == [UNKNOWN_SOURCE] and fallback.status == "answered"
    assert fallback.research_trace["collection_first_fallback"] == "research_plan_clarification"
    on, on_calls, _ = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())
    direct = on.answer(UNKNOWN_SOURCE, NATIVE, "offline")
    assert direct.status == "answered" and direct.research_trace["agent_skipped"]["reason"] == SKIPPED_AGENT_REASON
    assert screened(on_calls) == screened(off_calls) and screened(on_calls)
    assert [c.evidence_id for c in direct.citations] == [c.evidence_id for c in fallback.citations]
    for answer in (fallback, direct):
        assert answer.research_trace["question_plan"]["filters"]["dataset"] == "native"
    # Both retrievals searched the whole native scope with the question itself (the fallback has no
    # agent-written query to reuse; the fast path never had one).
    assert [(c["query"], c["dataset"], c["record_ids"]) for c in off.db.calls["search"]] == \
        [(c["query"], c["dataset"], c["record_ids"]) for c in on.db.calls["search"]]
    assert {c["query"] for c in on.db.calls["search"]} == {UNKNOWN_SOURCE}
    assert direct.research_trace["question_plan"]["search_query"] == UNKNOWN_SOURCE
    # Under "ask" both stop at a card with the same candidates and condition, nothing judged.
    off_card = agent_service("native_triage", monkeypatch, switch=False, agent=clarify)[0].answer(
        UNKNOWN_SOURCE, NATIVE, "offline", criterion_confirmation="ask")
    on_card = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())[0].answer(
        UNKNOWN_SOURCE, NATIVE, "offline", criterion_confirmation="ask")
    assert pending_confirmation(off_card) and pending_confirmation(on_card)
    assert off_card.structured_result["candidates"] == on_card.structured_result["candidates"]
    assert off_card.structured_result["condition"] == on_card.structured_result["condition"]


def test_a_guarded_question_keeps_the_agent_and_the_record_names_the_check(monkeypatch):
    stub = StubAgent(ResearchRun(route="limited", failure_reason="research_budget_limited"))
    service, _, _ = agent_service("native_triage", monkeypatch, switch=True, agent=stub)
    result = service.answer("Which ads with label greenwashing mention jobs?", NATIVE, "offline")
    assert result.status == "limited" and stub.calls == ["Which ads with label greenwashing mention jobs?"]
    assert result.research_trace["agent_kept"] == "scope:labels" and "agent_skipped" not in result.research_trace
    assert result.research_trace["question_plan"]["agent_route"] == "limited"


def test_without_readable_source_names_the_agent_runs(monkeypatch):
    stub = StubAgent(ResearchRun(route="limited", failure_reason="research_budget_limited"))
    service, _, _ = agent_service("native_triage", monkeypatch, switch=True, agent=stub)
    del service.db.facets  # the golden database has none: the names cannot be checked
    result = service.answer(JOBS, NATIVE, "offline")
    assert stub.calls == [JOBS] and result.research_trace["agent_kept"] == "names:unavailable"


def test_the_two_phase_card_and_its_continuation_run_without_the_agent(monkeypatch):
    never = NeverAgent()
    service, calls, _ = agent_service("native_triage", monkeypatch, switch=True, agent=never)
    card = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    assert pending_confirmation(card) and never.calls == []
    assert roles(calls) == ["embed", "criterion"]  # drafted from the question, nothing judged
    plan = card.research_trace["question_plan"]
    assert plan["agent_route"] == "skipped" and plan["criterion_mode"] == "ask" and plan["filters"]["dataset"] == "native"
    assert card.research_trace["agent_skipped"]["reason"] == SKIPPED_AGENT_REASON

    before = model_calls(calls)
    changed = service.answer("Which ads mention jobs?", NATIVE, "offline",
                             continuation={"token": card.structured_result["continuation"], "criterion": CONFIRMED})
    assert changed.failure_reason == "continuation_invalid" and never.calls == []  # another question: refused as before
    assert model_calls(calls) == before  # and nothing was screened, judged or drafted for it

    draft = card.structured_result["criterion"]
    judged = service.answer(JOBS, NATIVE, "offline", continuation={"token": card.structured_result["continuation"], "criterion": draft})
    assert judged.status == "answered" and never.calls == []
    screening = judged.research_trace["list_screening"]
    assert screening["criterion_source"] == "confirmed" and screening["criterion"] == draft  # judged by the confirmed draft
    assert judged.research_trace["question_plan"]["agent_route"] == "skipped"  # the token's plan, the card's
    assert judged.research_trace["criterion_confirmation"]["phase"] == 2
    row = service.db.save_answer.call_args.args[2].research_trace
    assert row["question_plan"]["agent_route"] == "skipped" and row["question_plan"]["filters"]["dataset"] == "native"
    assert row["list_screening"]["criterion_source"] == "confirmed" and row["list_screening"]["criterion"] == draft

    edited = agent_service("native_triage", monkeypatch, switch=True, agent=never)[0]
    other = edited.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    result = edited.answer(JOBS, NATIVE, "offline", continuation={"token": other.structured_result["continuation"], "criterion": CONFIRMED})
    assert result.research_trace["list_screening"]["criterion_source"] == "edited" and never.calls == []  # other rules: said so
    assert result.research_trace["list_screening"]["criterion"] == CONFIRMED  # judged by the researcher's own text

    # The existing contract still guards a continuation: a request that no longer contains the card's
    # scope, or a collection that moved since the card, is refused and nothing is judged.
    strict, strict_calls, _ = agent_service("native_triage", monkeypatch, switch=True, agent=never)
    plain = strict.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    before = model_calls(strict_calls)
    shrunk = strict.answer(JOBS, Filters(dataset="native", sponsors=["Tidal Co"]), "offline",
                           continuation={"token": plain.structured_result["continuation"], "criterion": draft})
    assert shrunk.failure_reason == "continuation_invalid" and never.calls == [] and model_calls(strict_calls) == before
    moved_service, moved_calls, _ = agent_service("native_triage", monkeypatch, switch=True, agent=never)
    before_move = moved_service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask")
    before = model_calls(moved_calls)
    moved_service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}
    moved = moved_service.answer(JOBS, NATIVE, "offline", continuation={"token": before_move.structured_result["continuation"], "criterion": draft})
    assert moved.failure_reason == "continuation_invalid" and never.calls == [] and model_calls(moved_calls) == before
    # The one selected sponsor named in the question still skips the agent on the card.
    narrow = strict.answer("Which ads present Tidal Co's kites as a source of jobs?", Filters(dataset="native", sponsors=["Tidal Co"]),
                           "offline", criterion_confirmation="ask")
    assert pending_confirmation(narrow) and narrow.research_trace["question_plan"]["agent_route"] == "skipped" and never.calls == []


def test_a_collection_that_changes_after_the_list_is_withheld_with_its_cost_and_plan(monkeypatch):
    service, _, _ = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())

    def change_version():
        service.db.health = lambda: {"status": "ok", "data_version": "golden-v2"}

    seen = watch_downstream(service, after=change_version)
    result = service.answer(JOBS, NATIVE, "offline")
    assert (result.status, result.failure_reason) == ("service_unavailable", "data_changed_during_tool_research")
    assert result.cost_usd > 0 and result.cost_usd == pytest.approx(seen["cost"])
    assert result.research_trace["agent_skipped"]["reason"] == SKIPPED_AGENT_REASON
    assert result.research_trace["question_plan"]["agent_route"] == "skipped"


def test_a_failure_inside_the_list_route_still_records_the_plan_and_the_skip(monkeypatch):
    service, _, _ = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())
    service._answer_evidence = Mock(side_effect=RuntimeError("fictional outage"))
    result = service.answer(JOBS, NATIVE, "offline")
    assert (result.status, result.failure_reason) == ("service_unavailable", "research_agent_unavailable")
    assert result.cost_usd == 0.0 and result.research_trace["policy"] == NO_AGENT_POLICY
    assert result.research_trace["agent_skipped"]["reason"] == SKIPPED_AGENT_REASON
    assert result.research_trace["question_plan"]["agent_route"] == "skipped"
    assert result.research_trace["model_calls"] == [] and result.research_trace["tools"] == []


def test_a_failure_after_the_list_keeps_the_downstream_cost(monkeypatch):
    service, _, _ = agent_service("native_triage", monkeypatch, switch=True, agent=NeverAgent())

    def break_health():
        service.health = Mock(side_effect=RuntimeError("fictional outage"))  # the service's own check after the list

    seen = watch_downstream(service, after=break_health)
    result = service.answer(JOBS, NATIVE, "offline")
    assert result.failure_reason == "research_agent_unavailable"
    assert result.cost_usd > 0 and result.cost_usd == pytest.approx(seen["cost"])
    assert result.research_trace["question_plan"]["agent_route"] == "skipped"


def test_the_setting_defaults_on_and_reads_the_environment(monkeypatch):
    assert Settings().list_without_agent is True
    monkeypatch.delenv("OBS_LIST_WITHOUT_AGENT", raising=False)
    assert Settings.from_env().list_without_agent is True
    monkeypatch.setenv("OBS_LIST_WITHOUT_AGENT", "false")
    assert Settings.from_env().list_without_agent is False
    monkeypatch.setenv("OBS_LIST_WITHOUT_AGENT", "true")
    assert Settings.from_env().list_without_agent is True
