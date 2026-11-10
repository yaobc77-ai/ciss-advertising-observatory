"""Spending caps and question limits that a new visitor id or cookie cannot reset (2026-10-30).

Fictional ads only (Tidal Co, Harbor Daily). No database and no model: the gate is tested
directly, Budget.reserve with its database step replaced, and list screening with a fake
client and a budget that refuses after a set number of reservations.
"""
import json
import threading
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from observatory import budget as budget_module
from observatory import list_screening
from observatory import service as service_module
from observatory.budget import (
    WRITER_SHARE,
    Budget,
    ContextPool,
    LimitReached,
    QuestionCapReached,
    QuestionGate,
    reading,
)
from observatory.config import Settings
from observatory.list_screening import Batch, Decision, list_answer, screen
from observatory.models import Evidence
from observatory.relevance_triage import triaged_screen


def _settings(**changes):
    values = dict(requests_per_minute=5, requests_per_day=30, concurrency=2, question_budget_usd=Decimal("0.50"),
                  address_requests_per_minute=10, address_requests_per_day=60)
    values.update(changes)
    return SimpleNamespace(**values)


# --- one question's spending --------------------------------------------------------------


def test_a_settled_call_counts_at_its_cost_not_its_reservation():
    gate, settings = QuestionGate(), _settings()
    with gate.question("visitor-a") as qid:
        gate.hold("r1", Decimal("0.30"), "visitor-a", settings)
        gate.settle("r1", Decimal("0.05"))  # reservations run 5-8x the settled cost
        gate.hold("r2", Decimal("0.30"), "visitor-a", settings)
        assert gate.spent(qid) == Decimal("0.35")
        with pytest.raises(QuestionCapReached):
            gate.hold("r3", Decimal("0.20"), "visitor-a", settings)
        gate.release("r2")  # never sent
        gate.hold("r3", Decimal("0.20"), "visitor-a", settings)
        assert gate.spent(qid) == Decimal("0.25")


def test_reading_stops_early_and_leaves_room_to_write_the_answer():
    gate, settings = QuestionGate(), _settings()
    reading_limit = Decimal("0.50") * (1 - WRITER_SHARE)
    with gate.question("visitor-a"):
        gate.hold("r1", reading_limit - Decimal("0.01"), "visitor-a", settings)
        with reading(), pytest.raises(QuestionCapReached):
            gate.hold("r2", Decimal("0.02"), "visitor-a", settings)
        gate.hold("writer", Decimal("0.02"), "visitor-a", settings)  # the answer itself may use the rest
        with pytest.raises(QuestionCapReached):
            gate.hold("more", Decimal("0.10"), "visitor-a", settings)


def test_calls_outside_a_question_are_not_held_and_a_late_settlement_is_ignored():
    gate, settings = QuestionGate(), _settings()
    gate.hold("free", Decimal("5"), "visitor-a", settings)  # no open question: only the ledger limits apply
    with gate.question("visitor-a") as qid:
        gate.hold("r1", Decimal("0.10"), "visitor-a", settings)
    gate.settle("r1", Decimal("0.01"))  # the question closed first: nothing to update, no error
    gate.release("r1")
    assert gate.spent(qid) == 0


def test_two_questions_of_one_visitor_keep_their_own_spending():
    gate, settings = QuestionGate(), _settings()
    spent, ready, done = {}, threading.Barrier(2), threading.Barrier(2)

    def ask(name, amount):
        with gate.question("visitor-a") as qid:
            ready.wait()
            with ContextPool(max_workers=2) as pool:  # workers run in this question's context
                list(pool.map(lambda n: gate.hold(f"{name}-{n}", amount, "visitor-a", settings), range(2)))
            spent[name] = gate.spent(qid)
            done.wait()

    threads = [threading.Thread(target=ask, args=("one", Decimal("0.20"))),
               threading.Thread(target=ask, args=("two", Decimal("0.01")))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert spent == {"one": Decimal("0.40"), "two": Decimal("0.02")}


def test_reserve_holds_before_the_ledger_and_releases_when_the_ledger_refuses(monkeypatch):
    gate = QuestionGate()
    monkeypatch.setattr(budget_module, "QUESTIONS", gate)
    budget = Budget(db=None, settings=_settings())
    refused = Mock(side_effect=LimitReached("Today's API budget reached."))
    monkeypatch.setattr(budget, "_reserve", refused)
    with gate.question("visitor-a") as qid:
        with pytest.raises(LimitReached):
            budget.reserve(Decimal("0.10"), "visitor-a", "generation", "gpt-5.6-luna")
        assert gate.spent(qid) == 0
        monkeypatch.setattr(budget, "_reserve", Mock())
        rid = budget.reserve(Decimal("0.10"), "visitor-a", "generation", "gpt-5.6-luna")
        assert gate.spent(qid) == Decimal("0.10") and len(rid) == 32
        with pytest.raises(QuestionCapReached):
            budget.reserve(Decimal("0.45"), "visitor-a", "generation", "gpt-5.6-luna")


# --- limits per address --------------------------------------------------------------------


def test_a_new_visitor_id_from_the_same_address_is_still_counted():
    gate, settings = QuestionGate(), _settings(address_requests_per_day=2)
    for n in range(2):
        with gate.question(f"api:rotated-{n}", "203.0.113.7"):
            assert gate.admit(f"api:rotated-{n}", settings)
    with gate.question("api:rotated-2", "203.0.113.7"), pytest.raises(LimitReached):
        gate.admit("api:rotated-2", settings)
    # Another address, and a caller without one (command line, scripts), are not affected.
    with gate.question("api:rotated-3", "198.51.100.4"):
        assert gate.admit("api:rotated-3", settings)
    with gate.question("cli"):
        assert gate.admit("cli", settings)


def test_the_address_minute_limit_and_the_visitor_limits_both_apply():
    gate, settings = QuestionGate(), _settings(address_requests_per_minute=1, requests_per_day=1)
    with gate.question("web-1", "203.0.113.7"):
        gate.admit("web-1", settings)
    with gate.question("web-2", "203.0.113.7"), pytest.raises(LimitReached):
        gate.admit("web-2", settings)
    with gate.question("web-1", "198.51.100.4"), pytest.raises(LimitReached):
        gate.admit("web-1", settings)  # the visitor's own day limit


def test_a_cap_that_is_not_a_positive_amount_is_refused(monkeypatch):
    for value in ("0", "-1", "lots", "NaN"):
        monkeypatch.setenv("OBS_QUESTION_BUDGET_USD", value)
        with pytest.raises(ValueError, match="OBS_QUESTION_BUDGET_USD"):
            Settings.from_env()
    monkeypatch.setenv("OBS_QUESTION_BUDGET_USD", "0.75")
    monkeypatch.setenv("OBS_DAILY_BUDGET_USD", "4")
    settings = Settings.from_env()
    assert (settings.question_budget_usd, settings.daily_budget_usd) == (Decimal("0.75"), Decimal("4"))


# --- a list stopped by the cap -------------------------------------------------------------


def ad(n, text="Tidal kites will supply cheap power to the harbor."):
    return Evidence(evidence_id=f"r{n}-e1", record_id=f"r{n}", version_id=f"r{n}-v", dataset="native",
                    title=f"Kite notice {n}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=0, end=len(text))


def fake_rag(allowed_reservations, *, refused=()):
    """Every ad matches by quoting its first passage; reservations past `allowed_reservations`, or
    numbered in `refused`, hit the cap."""
    count = {"n": 0}

    def reserve(*_):
        count["n"] += 1
        if count["n"] > allowed_reservations or count["n"] in refused:
            raise QuestionCapReached("cap")
        return f"reservation-{count['n']}"

    def parse(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        decisions = [Decision(ref=item["ref"], decision="matches", passage_id=item["passages"][0]["passage_id"],
                              quote=item["passages"][0]["text"][:40]) for item in ads]
        return SimpleNamespace(status="completed", output_parsed=Batch(decisions=decisions), usage=SimpleNamespace(
            input_tokens=10, output_tokens=5, input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
            model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    budget = SimpleNamespace(reserve=Mock(side_effect=reserve), settle=Mock(), uncertain=Mock())
    return SimpleNamespace(settings=Settings(), budget=budget,
                           client=SimpleNamespace(responses=SimpleNamespace(parse=parse))), count


@pytest.fixture(autouse=True)
def plain_screening(monkeypatch):
    monkeypatch.setenv("OBS_ANSWER_NORMS", "off")  # the structured screening call, as in CI
    # Batches one after another, so the refused reservation is a known batch (ContextPool is tested above).
    monkeypatch.setattr(list_screening, "_run_batches", lambda calls, workers=None: [call() for call in calls])


def test_screening_stopped_by_the_cap_leaves_the_unread_ads_for_a_human_check():
    rag, _ = fake_rag(allowed_reservations=1)
    evidence = [ad(n) for n in range(1, 10)]  # three batches of up to four
    results, _ = screen(rag, "Which ads mention tidal kites?", evidence, "visitor-a", limit=9, widen_to=9)
    read = [item for item in results if item.get("reason") != "question_cap"]
    unread = [item for item in results if item.get("reason") == "question_cap"]
    assert len(read) == 4 and all(item["decision"] == "matches" for item in read)
    assert [item["record_id"] for item in unread] == [f"r{n}" for n in range(5, 10)]
    assert all(item["decision"] == "unclear" for item in unread)


def test_a_reread_or_second_check_cut_by_the_cap_never_lists_the_ad():
    # Reread: r1 is ruled out on its shown passage; reading it whole is refused by the cap.
    rag, _ = fake_rag(allowed_reservations=1)
    text = "The festival program lists food stalls and music."
    shown = ad(1, text)
    hidden = Evidence(**{**shown.model_dump(), "evidence_id": "r1-e2", "text": "Kites by night.", "end": 15})

    def no_match(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        return SimpleNamespace(status="completed", output_parsed=Batch(decisions=[
            Decision(ref=a["ref"], decision="does_not_match", passage_id=a["passages"][0]["passage_id"], quote="")
            for a in ads]), usage=SimpleNamespace(input_tokens=1, output_tokens=1, input_tokens_details=SimpleNamespace(
                cached_tokens=0, cache_write_tokens=0), model_dump=lambda: {}))

    rag.client.responses.parse = no_match
    results, _ = screen(rag, "Which ads mention kites?", [shown], "visitor-a", limit=1,
                        reread=lambda ids: [shown, hidden])
    assert results[0]["decision"] == "unclear" and results[0]["reason"] == "question_cap"
    assert results[0]["reread_from"] == "does_not_match" and results[0]["route"] == "review"
    # Second check: the listed ads it could not reach are not listed.
    rag, _ = fake_rag(allowed_reservations=1)
    results, _ = screen(rag, "Which ads mention tidal kites?", [ad(1), ad(2)], "visitor-a", limit=2, verify=True)
    assert [(item["decision"], item["reason"], item["verified_from"]) for item in results] == [
        ("unclear", "question_cap", "matches")] * 2


def test_a_triage_cut_by_the_cap_sends_the_unjudged_ads_to_review_unscreened(monkeypatch):
    from observatory import relevance_triage

    def triage(rag, question, criterion, groups, visitor, cost_sink=None, capped=None):
        capped.update(group[0].record_id for group in groups[1:])
        return {groups[0][0].record_id: {"meets": 0.9, "borderline": 0.1, "does_not_meet": 0.0, "rules": [0.9],
                                         "exclusions": []}}, 0.0

    monkeypatch.setattr(relevance_triage, "triage", triage)
    screened = []

    def screen_stub(rag, question, evidence, visitor, **options):
        screened.extend(item.record_id for item in evidence)
        return [{"record_id": item.record_id, "title": item.title, "decision": "matches",
                 "evidence_id": item.evidence_id, "quote": item.text[:20]} for item in evidence], 0.0

    results, _, summary = triaged_screen(screen_stub, None, "Which ads mention tidal kites?", [ad(1), ad(2), ad(3)],
                                         "visitor-a", criterion={"counts": ["Mentions tidal kites."]})
    assert screened == ["r1"]
    routes = {item["record_id"]: (item["route"], item.get("reason")) for item in results}
    assert routes == {"r1": ("pass", None), "r2": ("review", "question_cap"), "r3": ("review", "question_cap")}
    assert summary["question_cap"] == 2


def test_the_answer_says_the_cap_stopped_reading_and_does_not_count_the_unread_as_checked():
    rag, _ = fake_rag(allowed_reservations=1)
    evidence = [ad(n) for n in range(1, 7)]
    results, _ = screen(rag, "Which ads mention tidal kites?", evidence, "visitor-a", limit=6, widen_to=6)
    answer = list_answer("Which ads mention tidal kites?", results, evidence, scope_total=6)
    head, *lines = answer.answer.split("\n\n")
    # The plain opening line (MT6-016, 1d4587c) with the spending-cap case (merged 2026-11-10).
    assert head == ("4 of the 4 ads that were read match the question. Your selection has 6 ads; this question "
                    "reached its spending limit after 4 were read, so there may be more matches. Narrowing the "
                    "selection (company, date or platform) lets a larger share be read.")
    # Without the triage the unchecked ads are still listed for a human check, apart from the judge's unclear ones.
    assert lines[-3:] == ["This question reached its spending limit before 2 ads were fully checked; they need a human check:",
                          "- Kite notice 5", "- Kite notice 6"]
    assert "(all checked)" not in answer.answer and "machine checks were not clear" not in answer.answer
    trace = answer.research_trace["list_screening"]
    assert trace["examined"] == 4 and trace["question_cap"] == 2 and trace["review"] == 2
    both = list_answer("Which ads mention tidal kites?", [{**item, "dataset": "native"} for item in results], evidence,
                       scope_total=10, scopes={"native": 6, "social": 4})
    assert both.answer.startswith("Found 4 matching ads and 0 matching posts. Read: 4 of the 6 native ads, then the "
                                  "question's spending limit stopped the reading (2 not finished);")


def test_a_batch_read_beside_a_refused_one_is_kept_and_no_later_wave_starts():
    rag, count = fake_rag(allowed_reservations=99, refused={1})
    evidence = [ad(n) for n in range(1, 18)]  # first wave: batches from the first nine ads; no widening wave
    results, _ = screen(rag, "Which ads mention tidal kites?", evidence, "visitor-a", limit=9, widen_to=17)
    decisions = {item["record_id"]: (item["decision"], item.get("route")) for item in results}
    assert decisions == {**{f"r{n}": ("unclear", "review") for n in range(1, 5)},
                         **{f"r{n}": ("matches", None) for n in range(5, 13)}}
    assert count["n"] == 3


# --- the accounting fixes from the first review (2026-10-30) -------------------------------------


def test_once_reading_is_refused_the_question_reads_no_more_but_can_still_write():
    gate, settings = QuestionGate(), _settings()
    with gate.question("visitor-a"):
        gate.hold("r1", Decimal("0.39"), "visitor-a", settings)
        with reading():
            with pytest.raises(QuestionCapReached):
                gate.hold("r2", Decimal("0.02"), "visitor-a", settings)
            gate.settle("r1", Decimal("0.01"))  # a settlement frees room ...
            with pytest.raises(QuestionCapReached):  # ... but the list stops at one point
                gate.hold("r3", Decimal("0.01"), "visitor-a", settings)
        gate.hold("writer", Decimal("0.30"), "visitor-a", settings)


def test_cancelling_a_settled_call_leaves_its_cost_on_the_question(monkeypatch):
    gate = QuestionGate()
    monkeypatch.setattr(budget_module, "QUESTIONS", gate)
    rows = {"cancelled": 0}
    conn = Mock()
    conn.execute.side_effect = lambda *_: SimpleNamespace(rowcount=rows["cancelled"])
    budget = Budget(db=SimpleNamespace(connect=lambda: nullcontext(conn)), settings=_settings())
    monkeypatch.setattr(budget, "_reserve", Mock())
    with gate.question("visitor-a") as qid:
        settled = budget.reserve(Decimal("0.30"), "visitor-a", "generation", "gpt-5.6-luna")
        gate.settle(settled, Decimal("0.30"))
        budget.cancel_unsent(settled)  # the ledger row is no longer pending: nothing cancelled
        assert gate.spent(qid) == Decimal("0.30")
        with pytest.raises(QuestionCapReached):
            budget.reserve(Decimal("0.30"), "visitor-a", "generation", "gpt-5.6-luna")
        rows["cancelled"] = 1
        unsent = budget.reserve(Decimal("0.10"), "visitor-a", "generation", "gpt-5.6-luna")
        budget.cancel_unsent(unsent)
        assert gate.spent(qid) == Decimal("0.30")


def test_the_two_phases_of_a_confirmed_list_share_one_cap():
    gate, settings = QuestionGate(), _settings()
    with gate.question("visitor-a"):
        gate.carry(Decimal("0.45"))
        with pytest.raises(QuestionCapReached):
            gate.hold("r1", Decimal("0.10"), "visitor-a", settings)
        gate.hold("r1", Decimal("0.05"), "visitor-a", settings)
    gate.carry(Decimal("1"))  # outside a question there is nothing to count it in


def test_a_confirmed_list_carries_what_phase_one_spent_into_phase_two(monkeypatch):
    from test_criterion_confirmation import DRAFT, card_for, continue_with

    gate = QuestionGate()
    monkeypatch.setattr(service_module, "QUESTIONS", gate)
    monkeypatch.setattr(gate, "spent", lambda qid=None: Decimal("0.42"))
    carried = []
    monkeypatch.setattr(gate, "carry", carried.append)
    service, _, card, _, _ = card_for("native_triage", monkeypatch)
    assert carried == []
    assert continue_with(service, card, DRAFT).status == "answered"
    assert carried == [Decimal("0.42")]


def test_a_cap_while_widening_keeps_the_matches_and_says_why_reading_stopped():
    rag, _ = fake_rag(allowed_reservations=99, refused={2})  # the first ranked four, then the widening batch
    evidence = [ad(n) for n in range(1, 9)]
    results, _ = screen(rag, "Which ads mention tidal kites?", evidence, "visitor-a", limit=4, widen_to=8)
    assert [(item["record_id"], item["decision"]) for item in results] == [
        *((f"r{n}", "matches") for n in range(1, 5)), *((f"r{n}", "unclear") for n in range(5, 9))]
    answer = list_answer("Which ads mention tidal kites?", results, evidence, scope_total=8)
    assert "spending limit before 4 ads were fully checked" in answer.answer


def test_a_list_without_its_written_summary_says_so_where_the_page_shows_it():
    from observatory.app import _grounded_answer_parts
    from observatory.list_screening import summary_limited_line
    from observatory.service import Service

    rag, _ = fake_rag(allowed_reservations=99)
    evidence = [ad(n) for n in range(1, 3)]
    question = "Which ads mention tidal kites?"
    results, _ = screen(rag, question, evidence, "visitor-a", limit=2)
    listed = list_answer(question, results, evidence, scope_total=2)
    writer = SimpleNamespace(rag=SimpleNamespace(generate=Mock(side_effect=QuestionCapReached("cap"))))
    limited, cost = Service._summarize_list(writer, question, listed, results, evidence, "visitor-a")
    assert cost == 0.0 and limited.research_trace["list_summary"] == {"status": "limited", "reason": "QuestionCapReached"}

    def texts(node):
        if isinstance(node, str):
            return [node]
        if isinstance(node, (list, tuple)):
            return [text for item in node for text in texts(item)]
        return texts(getattr(node, "children", None) or [])

    summary, findings = _grounded_answer_parts(limited.model_dump(mode="json"), limited.answer)
    shown = "\n".join(texts([summary, findings]))
    assert shown.count(summary_limited_line(question)) == 1 and "Kite notice 1" in shown
