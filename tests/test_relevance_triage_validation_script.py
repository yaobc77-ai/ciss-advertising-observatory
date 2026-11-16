"""scripts/relevance_triage_validation.py with a fake service: the two arms, their provenance and cost, every
stop (refused card, missing draft, limited judgment, malformed list, wrong provenance, exception) with the
phases saved before it, the frozen cohort and destination checks, and the denominator rules.
No model call; fictional articles and labels."""
import json
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from observatory.models import Answer
from scripts.relevance_triage_validation import (
    BOUND_FACTORS,
    SHIPPED,
    AllowanceBudget,
    RunStopped,
    build_manifest,
    check_cohort,
    check_destination,
    check_manifest,
    cohort_for,
    exit_status,
    load_doc_map,
    run,
    score,
    select_questions,
)


@pytest.fixture(autouse=True)
def no_subprocess(monkeypatch):
    """versions() asks git for the commit; the masked checks deny subprocesses, so the tests answer for git."""
    import scripts.relevance_triage_validation as module

    def fake_run(args, **kwargs):
        stdout = "a650f6f" if "rev-parse" in args else " M scripts/relevance_triage_validation.py"
        return SimpleNamespace(stdout=stdout + "\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)


DOC_MAP = {"1": {"record_id": "r1", "retrievable": True}, "2": {"record_id": "r2", "retrievable": True},
           "3": {"record_id": "r3", "retrievable": False}}
LABELS = pd.DataFrame({"doc_id": [1, 2, 3], "la": [1, 0, 1], "lb": [0, 1, 0]})
QUESTIONS = {"la": "Which ads mention tidal kites?", "lb": "Which ads mention harbor jobs?"}
COHORT = {"articles": 2, "pairs": 4, "human_positive": 2}
RULES = {"counts": ["The ad mentions tidal kites."], "does_not_count": []}
LIMITED = dict(status="limited", answer="Monthly budget reached.", cost_usd=0.0005)


class FakeListService:
    """answer() as the real service shapes it: a card for ask, a judged list for a continuation or auto."""

    def __init__(self, routes=None, listed=("r1",), refuse_card_for=(), limited=False, raise_for=(), no_draft_for=(),
                 provenance=None, malformed=False):
        self.routes = routes or {"r1": "pass", "r2": "exclude"}
        self.listed, self.refuse_card_for, self.limited = set(listed), set(refuse_card_for), limited
        self.raise_for, self.no_draft_for, self.provenance, self.malformed = set(raise_for), set(no_draft_for), provenance, malformed
        self.calls = []
        self.settings = SimpleNamespace(generation_model="gen-test", embedding_model="emb-test")

    def health(self):
        return {"status": "ok", "data_version": "data-test"}

    def answer(self, question, filters, visitor, **options):
        self.calls.append((question, tuple(filters.record_ids), visitor, options))
        if options.get("criterion_confirmation") == "ask":
            if question in self.refuse_card_for:
                return Answer(**LIMITED)
            return Answer(status="insufficient_evidence", answer_mode="clarification", failure_reason="criterion_confirmation_required",
                          answer="card", cost_usd=0.002,
                          structured_result={"kind": "criterion_confirmation", "flow_id": "f-" + question[:9], "continuation": "token-" + question[:9],
                                             "criterion": None if question in self.no_draft_for else RULES})
        if "continuation" in options:
            if question in self.raise_for:
                raise RuntimeError("judge unavailable")
            if self.limited:
                return Answer(**LIMITED)
            source, basis = self.provenance or ("confirmed", "confirmed_criterion")
            return self.judged(source, basis, 0.01)
        return self.judged("draft_unconfirmed", "question", 0.015)

    def judged(self, source, basis, cost):
        if self.malformed:
            return Answer(status="answered", answer="prose, not a list", cost_usd=cost, research_trace={})
        decisions = [{"record_id": rid, "route": route, "decision": "matches" if rid in self.listed else "does_not_match"}
                     for rid, route in self.routes.items()]
        return Answer(status="answered", answer="list", cost_usd=cost,
                      research_trace={"list_screening": {"decisions": decisions, "criterion": RULES,
                                                         "criterion_source": source, "screening_basis": basis}})


def arm(tmp_path, service, strategy="confirmed", block="arm", cohort=COHORT, **extra):
    doc_map = tmp_path / "doc_map.json"
    doc_map.write_text(json.dumps(DOC_MAP), encoding="utf-8")
    _, doc_of = load_doc_map(doc_map)
    return run(service, LABELS, doc_of, strategy=strategy, run_dir=tmp_path / "run", block=block,
               out=tmp_path / "run" / "out.json", questions=QUESTIONS, cohort=cohort, **extra)


def files(tmp_path, block="arm"):
    return sorted(p.name for p in (tmp_path / "run" / block).iterdir())


def saved(tmp_path):
    return json.loads((tmp_path / "run" / "out.json").read_text(encoding="utf-8"))["arm"]


def test_the_confirmed_arm_runs_the_card_then_the_judgment_and_records_both_costs_and_the_provenance(tmp_path):
    service = FakeListService()
    summary = arm(tmp_path, service)
    assert [c[3] for c in service.calls] == [{"criterion_confirmation": "ask"}, {"continuation": {"token": "token-Which ads", "criterion": RULES}}] * 2
    assert all(c[1] == ("r1", "r2") and c[2].startswith("relevance-validation:arm:20") for c in service.calls)  # the cohort scope, the arm's own visitor
    rows = summary["questions"]
    assert [r["cost_usd"] for r in rows] == [0.012, 0.012] and [r["card_cost_usd"] for r in rows] == [0.002, 0.002]
    assert all((r["criterion_source"], r["screening_basis"], r["strategy"]) == ("confirmed", "confirmed_criterion", "confirmed") for r in rows)
    assert (summary["pass"], summary["review"], summary["exclude"]) == (2, 0, 2) and summary["pass_human_yes"] == 1
    assert (summary["pairs"], summary["pairs_expected"], summary["human_positive"], summary["human_positive_expected"]) == (4, 4, 2, 2)
    assert (summary["listed"], summary["listed_human_yes"], summary["missing_pairs"], summary["stopped"]) == (2, 1, 0, None)
    assert summary["cohort"] == COHORT and summary["visitor"] == f"relevance-validation:arm:{summary['run_id']}"
    assert summary["acceptance"].startswith("the card's unchanged model draft")
    assert summary["versions"]["data_version"] == "data-test" and summary["versions"]["generation_model"] == "gen-test"
    assert [(p["label"], p["stage"], p["cost_usd"]) for p in summary["phases"]] == [("la", "card", 0.002), ("la", "judgment", 0.01),
                                                                                    ("lb", "card", 0.002), ("lb", "judgment", 0.01)]
    assert summary["cost_usd"] == 0.024 and summary["stopped_question_cost_usd"] == 0
    assert files(tmp_path) == ["la.card.json", "la.judgment.json", "la.row.json", "lb.card.json", "lb.judgment.json", "lb.row.json"]
    answers = json.loads((tmp_path / "run" / "arm_answers.json").read_text(encoding="utf-8"))
    assert set(answers) == {"la", "la.card", "lb", "lb.card"}
    assert saved(tmp_path)["questions_done"] == 2 and exit_status(summary) == 0


def test_the_auto_arm_is_one_call_per_question_with_todays_provenance(tmp_path):
    service = FakeListService()
    summary = arm(tmp_path, service, strategy="auto")
    assert [c[3] for c in service.calls] == [{}, {}]
    rows = summary["questions"]
    assert all((r["criterion_source"], r["screening_basis"], r["card_cost_usd"], r["cost_usd"]) == ("draft_unconfirmed", "question", 0.0, 0.015)
               for r in rows)
    assert summary["acceptance"].startswith("no confirmation") and files(tmp_path) == ["la.judgment.json", "la.row.json", "lb.judgment.json", "lb.row.json"]


def test_a_refused_card_is_saved_with_its_cost_and_stops_the_run_without_a_retry(tmp_path):
    service = FakeListService(refuse_card_for={QUESTIONS["lb"]})
    summary = arm(tmp_path, service)
    assert summary["questions_done"] == 1 and summary["stopped"].startswith("lb: no card (limited)") and exit_status(summary) == 2
    assert len(service.calls) == 3  # card + judgment for la, the refused card for lb, nothing more
    assert files(tmp_path) == ["la.card.json", "la.judgment.json", "la.row.json", "lb.card.json"]
    assert summary["phases"][-1] == {**summary["phases"][-1], "label": "lb", "stage": "card", "status": "limited", "cost_usd": 0.0005}
    assert summary["cost_usd"] == 0.0125 and summary["stopped_question_cost_usd"] == 0.0005  # the refused phase still cost something
    assert (summary["pairs"], summary["pairs_expected"]) == (2, 4)  # what was not run is visible, not folded in


def test_a_limited_judgment_after_a_card_keeps_both_phases_and_their_cost(tmp_path):
    service = FakeListService(limited=True)
    summary = arm(tmp_path, service)
    assert summary["questions_done"] == 0 and "limited" in summary["stopped"] and len(service.calls) == 2
    assert files(tmp_path) == ["la.card.json", "la.judgment.json"]
    assert summary["cost_usd"] == 0.0025 and summary["stopped_question_cost_usd"] == 0.0025


def test_an_exception_during_a_judgment_is_recorded_then_raised_and_the_card_stays(tmp_path):
    service = FakeListService(raise_for={QUESTIONS["lb"]})
    with pytest.raises(RuntimeError, match="judge unavailable"):
        arm(tmp_path, service)
    out = saved(tmp_path)
    assert out["questions_done"] == 1 and out["stopped"] == "RuntimeError: judge unavailable"
    assert files(tmp_path) == ["la.card.json", "la.judgment.json", "la.row.json", "lb.card.json"] and out["cost_usd"] == 0.014


def test_a_malformed_judgment_is_saved_and_stops_the_run(tmp_path):
    service = FakeListService(malformed=True)
    summary = arm(tmp_path, service)
    assert summary["questions_done"] == 0 and "not a judged list" in summary["stopped"]
    assert files(tmp_path) == ["la.card.json", "la.judgment.json"] and summary["cost_usd"] == 0.012


def test_a_card_without_a_usable_draft_makes_exactly_one_call(tmp_path):
    service = FakeListService(no_draft_for={QUESTIONS["la"]})
    summary = arm(tmp_path, service)
    assert len(service.calls) == 1 and summary["questions_done"] == 0 and "no usable draft" in summary["stopped"]
    assert files(tmp_path) == ["la.card.json"] and summary["cost_usd"] == 0.002


def test_a_judgment_with_another_provenance_is_saved_but_never_scored(tmp_path):
    service = FakeListService(provenance=("draft_unconfirmed", "question"))
    summary = arm(tmp_path, service)
    assert summary["questions_done"] == 0 and "provenance" in summary["stopped"] and "not scored" in summary["stopped"]
    assert files(tmp_path) == ["la.card.json", "la.judgment.json"] and summary["questions"] == []


def test_a_cohort_that_is_not_the_frozen_one_fails_before_any_call(tmp_path):
    service = FakeListService()
    with pytest.raises(RunStopped, match="cohort differs"):
        arm(tmp_path, service, cohort={"articles": 15, "pairs": 75, "human_positive": 29})
    assert service.calls == []
    with pytest.raises(RunStopped, match="no column"):
        check_cohort(LABELS.drop(columns=["lb"]), {"r1": 1, "r2": 2}, QUESTIONS, COHORT)


def test_the_destinations_are_protected(tmp_path):
    with pytest.raises(RunStopped, match="shipped record"):
        check_destination(tmp_path, "triage_confirmed", SHIPPED)
    check_destination(tmp_path, "triage", SHIPPED)  # today's default
    with pytest.raises(RunStopped, match="must lie inside"):
        check_destination(tmp_path / "run", "arm", tmp_path / "elsewhere.json")
    arm(tmp_path, FakeListService())
    with pytest.raises(RunStopped, match="already holds checkpoints"):
        arm(tmp_path, FakeListService())
    (tmp_path / "run2").mkdir()
    (tmp_path / "run2" / "out.json").write_text(json.dumps({"arm": {"pairs": 4}}), encoding="utf-8")  # the block, no checkpoint folder
    with pytest.raises(RunStopped, match="already has a block"):
        run(FakeListService(), LABELS, {"r1": 1, "r2": 2}, strategy="auto", run_dir=tmp_path / "run2", block="arm",
            out=tmp_path / "run2" / "out.json", questions=QUESTIONS, cohort=COHORT)


def test_the_document_map_is_checked_before_anything_is_spent(tmp_path):
    bad = tmp_path / "dup.json"
    bad.write_text(json.dumps({"1": {"record_id": "r1", "retrievable": True}, "2": {"record_id": "r1", "retrievable": True}}), encoding="utf-8")
    with pytest.raises(RunStopped, match="share a record id"):
        load_doc_map(bad)
    none = tmp_path / "none.json"
    none.write_text(json.dumps({"1": {"record_id": "r1", "retrievable": False}}), encoding="utf-8")
    with pytest.raises(RunStopped, match="no retrievable"):
        load_doc_map(none)


def test_ambiguous_unknown_and_missing_pairs_are_reported_and_left_out_of_the_counts():
    done = {"result": {"research_trace": {"list_screening": {"decisions": [
        {"record_id": "r1", "route": "pass", "decision": "matches"}, {"record_id": "r1", "route": "review", "decision": "matches"},
        {"record_id": "r2", "route": "maybe", "decision": "matches"}, {"record_id": "r3", "route": "pass", "decision": "matches"},
        {"record_id": "r9", "route": "pass", "decision": "matches"}], "criterion": RULES, "criterion_source": "confirmed",
        "screening_basis": "confirmed_criterion"}}}, "card": None, "cost_usd": 0.01, "card_cost_usd": 0.0}
    row = score("la", QUESTIONS["la"], done, {1, 2, 3}, {"r1": 1, "r2": 2, "r3": 3, "r4": 4}, "confirmed", 1.0)
    assert (row["ambiguous_docs"], row["unknown_route_docs"], row["missing_docs"]) == ([1], [2], [4])  # r9 is outside the set
    assert (row["pass"], row["review"], row["exclude"], row["counted"], row["accounted"]) == (1, 0, 0, 1, 4)
    assert row["listed"] == [3] and row["listed_human_yes"] == 1  # the ambiguous and the unknown are never listed


def test_the_cap_is_read_from_the_arms_own_ledger_rows_before_every_question(tmp_path):
    # The ledger figure under the arm's visitor (settled plus open reservations) is read before each question
    # and the question runs only while that figure plus the reserve (the most a question is expected to cost)
    # stays within the cap, so the cap is never passed by a question within the reserve. A visitor with
    # earlier rows is refused: the run id makes it new.
    service = FakeListService()
    ledger = {"rows": 0}

    def spent(visitor):
        assert visitor.startswith("relevance-validation:")  # the arm's own visitor, whichever block
        return ledger["rows"] * 0.012  # what the ledger would show after each completed question

    def service_answer(question, filters, visitor, **options):
        answer = FakeListService.answer(service, question, filters, visitor, **options)
        if "continuation" in options:
            ledger["rows"] += 1
        return answer

    service.answer = service_answer
    summary = arm(tmp_path, service, cap_usd="0.02", reserve_usd="0.012", spent=spent)  # Q1: 0 + 0.012 fits; Q2: 0.012 + 0.012 would not
    assert summary["questions_done"] == 1 and summary["stopped"].startswith("cap 0.02: 0.012 attributed")
    assert "plus the reserve 0.012 for lb would exceed it" in summary["stopped"]
    assert (summary["ledger_attributed_usd"], summary["cap_usd"], summary["reserve_usd"]) == ("0.012", "0.02", "0.012") and exit_status(summary) == 2
    # The allowance guard is installed once, before the first question, with the arm's visitor and cap.
    ledger["rows"] = 0
    installed = []
    both = arm(tmp_path, service, block="roomy", cap_usd="0.10", spent=spent,
               guard=lambda visitor, cap: installed.append((visitor, cap)) or {"visitor": visitor, "allowance_usd": str(cap)})
    assert both["questions_done"] == 2 and both["reserve_usd"] == "0.03" and len(installed) == 1
    assert installed[0][0] == both["visitor"] and str(installed[0][1]) == "0.10" and both["allowance_guard"]["allowance_usd"] == "0.10"
    assert both["cap_exceeded"] is False and exit_status(both) == 0


def test_an_overrun_is_reported_not_hidden(tmp_path):
    # Should a charge ever exceed its reservation, the final ledger figure above the cap is recorded and the
    # exit status is 3 even though every question completed; nothing is clamped.
    service = FakeListService()
    summary = arm(tmp_path, service, cap_usd="0.05", reserve_usd="0.01", spent=lambda visitor: 0.051 if len(service.calls) == 4 else 0)
    assert summary["questions_done"] == 2 and summary["stopped"] is None
    assert summary["ledger_attributed_usd"] == "0.051" and summary["cap_exceeded"] is True and exit_status(summary) == 3
    with pytest.raises(RunStopped, match="already holds rows"):
        arm(tmp_path, FakeListService(), block="arm2", cap_usd="1", spent=lambda visitor: 0.5)


def test_two_arms_get_distinct_visitors_with_the_run_id(tmp_path):
    first = arm(tmp_path, FakeListService(), block="one")
    second = arm(tmp_path, FakeListService(), block="two")
    assert first["visitor"] != second["visitor"] and first["visitor"].endswith(first["run_id"]) and ":one:" in first["visitor"]


def test_the_manifest_pins_the_inputs_document_by_document(tmp_path):
    labels_path, doc_map_path = tmp_path / "labels.csv", tmp_path / "doc_map.json"
    LABELS.to_csv(labels_path, index=False)
    doc_map_path.write_text(json.dumps(DOC_MAP), encoding="utf-8")
    labels = pd.read_csv(labels_path)
    _, doc_of = load_doc_map(doc_map_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(build_manifest(labels, labels_path, doc_map_path, doc_of, QUESTIONS)), encoding="utf-8")
    check_manifest(labels, labels_path, doc_map_path, doc_of, QUESTIONS, manifest_path)  # the frozen inputs pass
    # A substituted article with the same counts: 15/75/29-style aggregates would pass, the manifest does not.
    swapped_path = tmp_path / "doc_map_swapped.json"
    swapped_path.write_text(json.dumps({**DOC_MAP, "2": {"record_id": "r2-other", "retrievable": True}}), encoding="utf-8")
    _, swapped_of = load_doc_map(swapped_path)
    assert check_cohort(labels, swapped_of, QUESTIONS, COHORT) == COHORT
    with pytest.raises(RunStopped, match="document mapping differs"):
        check_manifest(labels, labels_path, swapped_path, swapped_of, QUESTIONS, manifest_path)
    # An article whose (all-zero) label rows are missing: the positives are unchanged, the coverage is not.
    zero_doc_map = {**DOC_MAP, "4": {"record_id": "r4", "retrievable": True}}
    zero_path = tmp_path / "doc_map_zero.json"
    zero_path.write_text(json.dumps(zero_doc_map), encoding="utf-8")
    full = pd.concat([LABELS, pd.DataFrame({"doc_id": [4], "la": [0], "lb": [0]})], ignore_index=True)
    full_path = tmp_path / "labels_full.csv"
    full.to_csv(full_path, index=False)
    _, zero_of = load_doc_map(zero_path)
    manifest2 = tmp_path / "manifest2.json"
    manifest2.write_text(json.dumps(build_manifest(pd.read_csv(full_path), full_path, zero_path, zero_of, QUESTIONS)), encoding="utf-8")
    check_manifest(pd.read_csv(full_path), full_path, zero_path, zero_of, QUESTIONS, manifest2)
    LABELS.to_csv(tmp_path / "labels_short.csv", index=False)  # doc 4 has no row at all
    with pytest.raises(RunStopped, match=r"articles without label rows: \[4\]"):
        check_manifest(pd.read_csv(tmp_path / "labels_short.csv"), tmp_path / "labels_short.csv", zero_path, zero_of, QUESTIONS, manifest2)


class RecordingBudget:
    """The inner budget as a tiny ledger: a row per reservation at its reserved amount, replaced by the actual
    on settlement, kept at the reservation while pending or uncertain; `held` is the ledger figure per visitor."""

    def __init__(self):
        self.reserved, self.settled, self.rows_by_id = [], [], {}

    def reserve(self, amount, visitor, kind, model):
        self.reserved.append((Decimal(str(amount)), visitor, kind, model))
        rid = f"r{len(self.reserved)}"
        self.rows_by_id[rid] = [visitor, Decimal(str(amount)), "pending"]
        return rid

    def settle(self, rid, actual, usage):
        self.settled.append((rid, actual))
        self.rows_by_id[rid][1:] = [Decimal(str(actual)), "settled"]

    def uncertain(self, rid, reason):
        self.rows_by_id[rid][2] = "uncertain"

    def held(self, visitor):
        return sum((amount for who, amount, _ in self.rows_by_id.values() if who == visitor), Decimal(0))


def test_the_allowance_is_checked_on_every_reservation_and_other_visitors_never_widen_it():
    inner = RecordingBudget()
    budget = AllowanceBudget(inner, "arm-visitor", "0.025", inner.held)
    from observatory.budget import LimitReached

    assert budget.reserve("0.010", "arm-visitor", "generation", "m") == "r1"
    assert budget.reserve("0.010", "arm-visitor", "generation", "m") == "r2"
    other = budget.reserve("0.50", "someone-else", "generation", "m")  # another visitor holds, then releases 0.40 ...
    budget.settle(other, "0.10", {})  # ... which never widens the arm's own figure
    with pytest.raises(LimitReached, match="allowance 0.025 would be passed: 0.020 held plus up to 0.010"):
        budget.reserve("0.010", "arm-visitor", "generation", "m")
    assert len(inner.reserved) == 3 and budget.refused[0]["asked"] == "0.010"  # refused before the inner budget saw it
    assert inner.held("someone-else") == Decimal("0.10") and inner.held("arm-visitor") == Decimal("0.020")
    assert budget.reserve("0.005", "arm-visitor", "embedding", "e") == "r4"  # exactly the allowance still fits
    assert budget.reserve("1", "someone-else", "generation", "m") == "r5"  # other visitors keep the inner budget's rules only
    budget.settle("r1", 0.001, {})  # delegated
    assert ("r1", 0.001) in inner.settled  # delegated (the other visitor's settlement is in the list too)


def test_the_allowance_check_is_atomic_across_threads():
    import threading

    inner = RecordingBudget()
    budget = AllowanceBudget(inner, "arm-visitor", "0.035", inner.held)
    from observatory.budget import LimitReached

    barrier, outcomes = threading.Barrier(8), []

    def contend():
        barrier.wait(10)
        try:
            outcomes.append(budget.reserve("0.010", "arm-visitor", "generation", "m"))
        except LimitReached:
            outcomes.append(None)

    threads = [threading.Thread(target=contend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sum(1 for o in outcomes if o) == 3 and inner.held("arm-visitor") == Decimal("0.030")  # never past 0.035


def test_an_unverified_cap_is_not_a_success():
    assert exit_status({"cap_usd": "0.20", "cap_exceeded": None, "stopped": None}) == 3
    assert exit_status({"cap_usd": "0.20", "cap_exceeded": False, "stopped": None}) == 0
    assert exit_status({"cap_usd": None, "cap_exceeded": None, "stopped": None}) == 0


def test_a_judge_reservation_is_counted_at_its_true_maximum():
    # The Decisions judge reserves price(bytes // 3 + 400) and bills input only; a token is at least a byte,
    # so the call can settle at up to three times its reservation: the allowance check counts that maximum.
    inner = RecordingBudget()
    budget = AllowanceBudget(inner, "arm-visitor", "0.0010", inner.held)
    from observatory.budget import LimitReached

    assert BOUND_FACTORS == {"gpt-6-luna": Decimal("3")}
    assert AllowanceBudget.maximum("0.0003", "gpt-6-luna") == Decimal("0.0009") and AllowanceBudget.maximum("0.0003", "gpt-5.6-luna") == Decimal("0.0003")
    assert budget.reserve("0.0003", "arm-visitor", "generation", "gpt-6-luna") == "r1"  # 0 + 0.0009 fits
    assert inner.reserved[0][0] == Decimal("0.0009")  # recorded in the ledger at its maximum, not the estimate
    with pytest.raises(LimitReached, match="plus up to 0.0009"):
        budget.reserve("0.0003", "arm-visitor", "generation", "gpt-6-luna")  # 0.0009 held + 0.0009 > 0.0010
    assert budget.refused[0]["maximum"] == "0.0009"
    with pytest.raises(LimitReached, match="plus up to 0.0007"):
        budget.reserve("0.0007", "arm-visitor", "generation", "gpt-5.6-luna")  # 0.0009 still held: 0.0016 > 0.0010
    budget.settle("r1", "0.0002", {})  # the judge settles below its maximum: the difference is released
    assert inner.held("arm-visitor") == Decimal("0.0002")
    assert budget.reserve("0.0007", "arm-visitor", "generation", "gpt-5.6-luna") == "r2"  # 0.0002 + 0.0007 fits now
    budget.uncertain("r2", "Timeout")  # an uncertain call keeps its whole hold
    assert inner.held("arm-visitor") == Decimal("0.0009")
    with pytest.raises(LimitReached):
        budget.reserve("0.0002", "arm-visitor", "generation", "gpt-5.6-luna")  # 0.0009 + 0.0002 > 0.0010


def test_concurrent_judges_hold_their_maxima_until_they_settle():
    import threading

    inner = RecordingBudget()
    budget = AllowanceBudget(inner, "arm-visitor", "0.0020", inner.held)
    from observatory.budget import LimitReached

    barrier, admitted, refused = threading.Barrier(6), [], []

    def judge():
        barrier.wait(10)
        try:
            admitted.append(budget.reserve("0.0003", "arm-visitor", "generation", "gpt-6-luna"))  # maximum 0.0009 each
        except LimitReached:
            refused.append(True)

    threads = [threading.Thread(target=judge) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert len(admitted) == 2 and len(refused) == 4 and inner.held("arm-visitor") == Decimal("0.0018")  # 2 x 0.0009 <= 0.0020
    for rid in admitted:
        budget.settle(rid, "0.0009", {})  # each settles at its maximum: still within the allowance
    assert inner.held("arm-visitor") == Decimal("0.0018") <= Decimal("0.0020")


def test_only_selects_named_questions_in_the_scripts_order_and_rejects_unknown_labels():
    assert list(select_questions(None, QUESTIONS)) == ["la", "lb"]
    assert list(select_questions("lb", QUESTIONS)) == ["lb"] and list(select_questions("lb, la", QUESTIONS)) == ["la", "lb"]
    with pytest.raises(RunStopped, match="unknown labels: \\['lc'\\]"):
        select_questions("lc", QUESTIONS)
    with pytest.raises(RunStopped, match="names no label"):
        select_questions(" , ", QUESTIONS)


def test_a_subset_block_runs_only_its_question_with_a_denominator_from_the_validated_inputs(tmp_path, monkeypatch):
    # The remainder of a stopped arm: temporary labels and map, no runtime map anywhere; only the named question
    # runs and the expected pairs and positives come from these inputs, not from the frozen constants.
    monkeypatch.chdir(tmp_path)  # nothing here but the temporary inputs
    doc_map = tmp_path / "doc_map.json"
    doc_map.write_text(json.dumps(DOC_MAP), encoding="utf-8")
    _, doc_of = load_doc_map(doc_map)
    subset = select_questions("lb", QUESTIONS)
    assert cohort_for(QUESTIONS, LABELS, doc_of, COHORT, QUESTIONS) == COHORT  # the full run keeps the frozen figures
    assert cohort_for(subset, LABELS, doc_of, COHORT, QUESTIONS) == {"articles": 2, "pairs": 2, "human_positive": 1}
    service = FakeListService()
    summary = run(service, LABELS, doc_of, strategy="confirmed", run_dir=tmp_path / "run", block="rest",
                  out=tmp_path / "run" / "out.json", questions=subset, cohort=cohort_for(subset, LABELS, doc_of, COHORT, QUESTIONS))
    assert [c[0] for c in service.calls] == [QUESTIONS["lb"]] * 2 and summary["questions_total"] == 1
    assert (summary["pairs"], summary["pairs_expected"], summary["human_positive"], summary["human_positive_expected"]) == (2, 2, 1, 1)
    assert sorted(p.name for p in (tmp_path / "run" / "rest").iterdir()) == ["lb.card.json", "lb.judgment.json", "lb.row.json"]
