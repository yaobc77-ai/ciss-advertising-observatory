"""Offline checks of the embedding task cap and the dry run (fictional chunks, no database, no API)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from observatory.budget import Budget, LimitReached, price
from observatory.rag import Rag, pending_embedding_estimate

MODEL = "text-embedding-3-small"
ROWS = [{"text_hash": f"h{i}", "text": f"Fictional kite festival chunk number {i}."} for i in range(7)]


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def pending_embeddings(self, model, profile_id=None):
        assert model == MODEL
        return list(self.rows)


class NoClient:
    def __getattr__(self, name):
        raise AssertionError("A dry run must not touch the API client")


class FakeBudget:
    def __init__(self, spent=Decimal("0")):
        self.spent, self.reserved = spent, []

    def task_spent(self, visitor):
        return self.spent

    def task_caps(self, visitor):
        return ["1"]

    def reserve(self, *args, **kwargs):
        self.reserved.append((args, kwargs))
        raise AssertionError("A dry run must not reserve")


def rag(rows, budget=None):
    settings = SimpleNamespace(embedding_model=MODEL, monthly_budget_usd=Decimal("100"))
    instance = Rag(FakeDb(rows), settings, client=NoClient())
    instance.budget = budget or FakeBudget()
    return instance


def test_estimate_counts_calls_bytes_reservations_and_tokens():
    estimate = pending_embedding_estimate(ROWS, 3, MODEL)
    sizes = [len(row["text"].encode("utf-8")) for row in ROWS]
    expected = sum(price(MODEL, sum(sizes[i:i + 3]) + 100) for i in range(0, 7, 3))
    assert estimate["pending_chunks"] == 7 and estimate["calls"] == 3 and estimate["utf8_bytes"] == sum(sizes)
    assert estimate["reservation_total_usd"] == pytest.approx(float(expected))
    assert estimate["tokens"] > 0 and estimate["estimated_usd"] == pytest.approx(estimate["tokens"] * 0.02 / 1e6)
    assert estimate["estimated_usd"] < estimate["reservation_total_usd"]


def test_dry_run_calls_nothing_and_reports_the_task_total():
    budget = FakeBudget(Decimal("0.25"))
    result = rag(ROWS, budget).index(4, visitor="task:kites", max_usd=1.0, dry_run=True)
    assert result["dry_run"] is True and result["pending_chunks"] == 7 and result["calls"] == 2
    assert result["task"] == "task:kites" and result["task_spent_usd"] == 0.25 and result["max_usd"] == 1.0
    assert result["recorded_task_caps"] == ["1"] and budget.reserved == []


def test_capped_index_stops_before_the_call_that_would_pass_the_cap():
    instance = rag(ROWS, FakeBudget(Decimal("0.5")))
    calls = []

    def embed(texts, visitor="maintenance", cost_sink=None, *, task_cap=None):
        assert visitor == "task:kites" and task_cap == "1"
        if len(calls) == 2:
            raise LimitReached("Task cap reached")
        calls.append(texts)
        return [[0.0]] * len(texts)

    instance.embed = embed
    result = instance.index(3, visitor="task:kites", max_usd=1.0)
    assert result["embedded_chunks"] == 6 and result["remaining_chunks"] == 1
    assert result["stopped"] == "Task cap reached" and result["task_spent_usd"] == 0.5


def test_uncapped_index_still_raises_a_limit():
    instance = rag(ROWS)

    def embed(texts, visitor="maintenance", cost_sink=None, *, task_cap=None):
        assert task_cap is None
        raise LimitReached("Monthly API budget reached.")

    instance.embed = embed
    with pytest.raises(LimitReached):
        instance.index(3)


@pytest.mark.parametrize("visitor, cap", [("maintenance", 1), ("task:kites", 0), ("task:kites", -1),
                                         ("task:kites", float("inf")), ("task:kites", "NaN"),
                                         ("task:kites", "Infinity"), ("task:kites", None)])
def test_a_task_cap_needs_a_task_visitor_and_a_positive_finite_amount(visitor, cap):
    budget = Budget(db=None, settings=SimpleNamespace(monthly_budget_usd=Decimal("100")))
    with pytest.raises(ValueError, match="task cap"):
        budget.reserve(Decimal("0.01"), visitor, "embedding", MODEL, task_cap=cap)


@pytest.mark.parametrize("value, text", [(1, "1"), ("1.00", "1"), (0.5, "0.5"), ("100", "100")])
def test_equal_caps_have_one_text(value, text):
    from observatory.budget import task_cap_text

    assert task_cap_text(value) == text


@pytest.mark.parametrize("kwargs", [{"visitor": "task:kites"}, {"visitor": "task:kites", "max_usd": float("inf")},
                                    {"visitor": "maintenance", "max_usd": 1.0}])
def test_index_refuses_a_task_without_a_finite_cap_before_reading_anything(kwargs):
    class Untouched(FakeDb):
        def pending_embeddings(self, model, profile_id=None):
            raise AssertionError("must refuse first")

    instance = Rag(Untouched(ROWS), SimpleNamespace(embedding_model=MODEL, monthly_budget_usd=Decimal("100")),
                   client=NoClient())
    with pytest.raises(ValueError):
        instance.index(3, **kwargs)


def test_cli_refuses_a_task_without_its_cap(monkeypatch, capsys):
    import sys

    from observatory import cli

    monkeypatch.setattr(sys, "argv", ["observatory", "index", "--task", "kites"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--task needs its approved --max-usd" in capsys.readouterr().err


def test_cli_index_offers_the_cap_and_dry_run_options(monkeypatch, capsys):
    import sys

    from observatory import cli

    monkeypatch.setattr(sys, "argv", ["observatory", "index", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    text = capsys.readouterr().out
    assert all(option in text for option in ("--task", "--max-usd", "--dry-run", "--batch-size"))
