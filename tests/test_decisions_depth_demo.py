"""scripts/decisions_depth_demo.py and observatory.depth_demo: the cap, the rounds and the groups.
No model call; fictional ads."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

import scripts.decisions_depth_demo as demo
from observatory.budget import LimitReached
from observatory.depth_demo import band_counts, group_of, load


def numbers(meets, does_not_meet=0.0, rules=(0.0,)):
    return {"meets": meets, "borderline": 0.0, "does_not_meet": does_not_meet, "rules": list(rules), "exclusions": []}


class Ledger:
    def __init__(self):
        self.calls, self.n = [], 0

    def reserve(self, amount, visitor, kind, model):
        self.n += 1
        self.calls.append(("reserve", amount))
        return f"r{self.n}"

    def settle(self, rid, actual, usage):
        self.calls.append(("settle", rid))

    def uncertain(self, rid, error_type):
        self.calls.append(("uncertain", rid))

    def cancel_unsent(self, rid):
        self.calls.append(("cancel", rid))


def ad(record_id, title="Tidal kites", text="Our kites cut harbor emissions."):
    return SimpleNamespace(record_id=record_id, title=title, publisher="Harbor Times", sponsor="Tidewater Energy",
                           published_at=date(2020, 5, 1), text=text)


def test_groups_come_from_the_judge_alone():
    assert group_of(None) == "not_scored"
    assert group_of(numbers(0.9)) == "likely"
    assert group_of(numbers(0.5)) == "likely"
    assert group_of(numbers(0.3, does_not_meet=0.5)) == "unsure"
    assert group_of(numbers(0.0, does_not_meet=0.95)) == "unlikely"
    assert group_of(numbers(0.0, does_not_meet=0.95, rules=(0.4,))) == "unsure"  # a rule says otherwise


def test_band_counts_split_at_the_reading_ranks():
    ads = [{"rank": r, "group": g} for r, g in ((1, "likely"), (40, "unsure"), (41, "likely"), (120, "unlikely"),
                                                 (121, "likely"), (400, "not_scored"))]
    counts = band_counts(ads, 400)
    assert [(c["from"], c["to"], c["ads"], c["likely"]) for c in counts] == [(1, 40, 2, 1), (41, 120, 2, 1), (121, 400, 2, 1)]
    assert counts[2]["not_scored"] == 1
    assert [c["to"] for c in band_counts([], 100)] == [40, 100]


def test_cap_holds_three_times_each_reservation_until_it_settles():
    ledger = Ledger()
    guard = demo.CapBudget(ledger, "0.030", earlier_usd="0.012")
    first = guard.reserve("0.003", "v", "generation", "m")  # held at 0.009
    assert ledger.calls[0] == ("reserve", Decimal("0.003"))  # the ledger keeps the judge's own estimate
    with pytest.raises(LimitReached):
        guard.reserve("0.004", "v", "generation", "m")  # 0.012 + 0.009 + 0.012 > 0.030
    assert guard.refused == 1
    guard.settle(first, Decimal("0.005"), {})  # above the estimate, within the hold
    assert guard.over_hold == 0 and guard.used() == Decimal("0.017")
    second = guard.reserve("0.004", "v", "generation", "m")
    guard.uncertain(second, "usage_missing")  # stays held at 0.012
    assert guard.used() == Decimal("0.029") and guard.remaining() == Decimal("0.001")
    with pytest.raises(LimitReached):
        guard.reserve("0.001", "v", "generation", "m")
    assert guard.refused == 2


def test_cancel_frees_the_hold_and_a_settlement_past_it_is_counted():
    guard = demo.CapBudget(Ledger(), "1")
    guard.cancel_unsent(guard.reserve("0.010", "v", "generation", "m"))
    assert guard.used() == 0
    guard.settle(guard.reserve("0.001", "v", "generation", "m"), Decimal("0.004"), {})
    assert guard.over_hold == 1


def rows(settled="0", uncertain="0", pending=0, pending_usd="0"):
    return {"settled": Decimal(settled), "uncertain": Decimal(uncertain), "pending": pending,
            "pending_usd": Decimal(pending_usd)}


def test_reconcile_names_every_mismatch():
    guard = demo.CapBudget(Ledger(), "0.020", earlier_usd="0.002")
    guard.settle(guard.reserve("0.001", "v", "generation", "m"), Decimal("0.001"), {})
    guard.uncertain(guard.reserve("0.002", "v", "generation", "m"), "usage_missing")  # held at 0.006
    assert demo.reconcile(guard, rows("0.001", "0.002")) == []
    assert "ledger settled" in demo.reconcile(guard, rows("0.003", "0.002"))[0]
    assert "uncertain" in demo.reconcile(guard, rows("0.001", "0.004"))[0]
    assert "1 ledger rows pending" in demo.reconcile(guard, rows("0.001", "0.002", 1, "0.001"))[0]
    assert demo.exposure(rows("0.001", "0.002", 1, "0.001")) == Decimal("0.010")
    empty = demo.CapBudget(Ledger(), "1")
    assert "ledger settled" in demo.reconcile(empty, rows("0.003"))[0]  # rows the run did not make
    guard.reserve("0.001", "v", "generation", "m")
    assert "1 reservations open" in demo.reconcile(guard, rows("0.001", "0.002"))[0]


def test_reconcile_flags_exposure_past_the_cap():
    guard = demo.CapBudget(Ledger(), "0.005", earlier_usd="0.004")
    guard.settle(guard.reserve("0.0003", "v", "generation", "m"), Decimal("0.002"), {})  # above its 0.0009 hold
    problems = demo.reconcile(guard, rows("0.002"))
    assert any("above their hold" in p for p in problems) and any("past the cap" in p for p in problems)


def test_fitting_takes_reservations_in_order():
    assert demo.fitting([Decimal("0.2"), Decimal("0.2"), Decimal("0.2")], Decimal("0.45")) == 2
    assert demo.fitting([Decimal("0.5")], Decimal("0.4")) == 0


def test_rounds_leave_every_question_its_first_ranks(monkeypatch):
    calls = []

    def fake_triage(rag, question, criterion, groups, visitor, cost_sink=None):
        calls.append((question, [g[0].record_id for g in groups]))
        cost_sink.append(0.01 * len(groups))
        return {g[0].record_id: (None if g[0].record_id == "b2" else numbers(0.9)) for g in groups}, 0.0

    guard = SimpleNamespace(left=Decimal("0.15"), refused=0)  # holds are 3 x 0.01 per ad
    guard.remaining = lambda: guard.left
    guard.used = lambda: Decimal("0.15") - guard.left
    prepared = [{"label": label, "question": label, "criterion": {"counts": ["r"]},
                 "groups": [[ad(f"{label}{i}")] for i in range(1, 4)], "estimates": [Decimal("0.01")] * 3}
                for label in ("a", "b")]
    costs = {"a": [], "b": []}

    def spend(rag, question, criterion, groups, visitor, cost_sink=None):
        out = fake_triage(rag, question, criterion, groups, visitor, cost_sink)
        guard.left -= Decimal("0.03") * len(groups)
        return out

    monkeypatch.setattr(demo, "triage", spend)
    got, status = demo.score(SimpleNamespace(rag=None), prepared, guard, "v", costs, batch=2)
    assert calls == [("a", ["a1", "a2"]), ("b", ["b1", "b2"]), ("a", ["a3"])]  # b3 no longer fits
    assert status["b"] == {"b1": "scored", "b2": "failed", "b3": "cap"}
    assert status["a"]["a3"] == "scored" and set(got["a"]) == {"a1", "a2", "a3"}


def test_a_question_keeps_a_scored_prefix_and_refusals_count_as_cap(monkeypatch):
    calls = []
    guard = SimpleNamespace(refused=0, room=iter([Decimal("0.03"), Decimal("9"), Decimal("9")]))
    guard.remaining = lambda: next(guard.room)
    guard.used = lambda: Decimal(0)

    def fake_triage(rag, question, criterion, groups, visitor, cost_sink=None):
        ids = [g[0].record_id for g in groups]
        calls.append(ids)
        if "b1" in ids:  # the guard refuses one of these calls inside triage
            guard.refused += 1
        return {rid: (None if rid in ("b1", "b2") else numbers(0.9)) for rid in ids}, 0.0

    monkeypatch.setattr(demo, "triage", fake_triage)
    prepared = [{"label": label, "question": label, "criterion": {"counts": ["r"]},
                 "groups": [[ad(f"{label}{i}")] for i in range(1, 5)], "estimates": [Decimal("0.01")] * 4}
                for label in ("a", "b")]
    _, status = demo.score(SimpleNamespace(rag=None), prepared, guard, "v", {"a": [], "b": []}, batch=2)
    # a: only a1 fits in round one; b: the guard refused inside the batch. Both stop there.
    assert calls == [["a1"], ["b1", "b2"]]
    assert status["a"] == {"a1": "scored", "a2": "cap", "a3": "cap", "a4": "cap"}
    assert status["b"] == {"b1": "cap", "b2": "cap", "b3": "cap", "b4": "cap"}


def test_question_result_keeps_status_truncation_and_labels():
    groups = [[ad("r1", text="x" * 20)], [ad("r2", text="y" * 13_000)]]
    p = {"label": "tides", "question": "Which ads?", "criterion": {"counts": ["r"]}, "scope": None, "groups": groups,
         "ranked": 2, "top_overlap": 2, "shallow": 2, "shallow_ids": ["r1", "r9"]}
    service = SimpleNamespace(_scope_count=lambda scope: 2063)
    out = demo.question_result(service, p, {"r1": numbers(0.9)}, {"r1": "scored", "r2": "cap"}, {"r1": True}, 0.01, 400)
    assert [(a["group"], a["status"], a["truncated"], a["human"], a["in_live_top"]) for a in out["ads"]] == [
        ("likely", "scored", False, True, True), ("not_scored", "cap", True, None, False)]
    assert (out["scored"], out["not_scored_cap"], out["truncated"], out["scope_total"]) == (1, 1, 1, 2063)


def result_of(ads):
    question = {"label": "tides", "short": "Tides", "question": "Which ads mention <tides>?",
                "criterion": {"counts": ["Mentions tides"], "does_not_count": ["Weather only"]},
                "scope_total": 2063, "ranked": 400, "top_overlap": 118, "shallow_ranked": 120,
                "scored": sum(a["numbers"] is not None for a in ads), "failed": 0, "not_scored_cap": 0, "truncated": 0,
                "cost_usd": 0.1, "ads": ads}
    return {"run_date": "2026-10-28", "model": "gpt-6-luna", "depth": 400, "cap_usd": 0.6, "cost_usd": 0.1,
            "uncertain_usd": 0.0, "max_ad_chars": 12000, "data_version": "v1", "data_version_after": "v1",
            "questions": [question]}


def test_load_reads_the_saved_run_or_none(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    monkeypatch.setenv("OBS_DEPTH_DEMO_RESULT", str(path))
    assert load() is None
    path.write_text('{"questions": []}', encoding="utf-8")
    assert load() == {"questions": []}
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        load()


def test_live_top_marks_membership_and_refuses_a_changed_ranking():
    result = result_of([{"rank": n, "record_id": f"r{n}", "numbers": None} for n in (1, 2, 3)])
    demo.mark_live_top(result, lambda q: (["r1", "r2", "r3"], ["r1", "r3"]))
    assert [ad["in_live_top"] for ad in result["questions"][0]["ads"]] == [True, False, True]
    for changed in (["r2", "r1", "r3"], ["new", "r1", "r2", "r3"], ["r1", "new", "r2"]):
        with pytest.raises(SystemExit):
            demo.mark_live_top(result, lambda q, order=changed: (order, ["r1"]))


def test_the_live_top_check_cannot_spend():
    with pytest.raises(LimitReached):
        demo.NoSpend(Ledger()).reserve("0.001", "v", "embedding", "m")
