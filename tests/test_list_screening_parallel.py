import threading
from decimal import Decimal
from types import SimpleNamespace

from observatory import list_screening


def _passages(count):
    return [SimpleNamespace(record_id=f"ad-{n:03d}", evidence_id=f"ev-{n:03d}", text=f"Ad {n} text")
            for n in range(count)]


def _fake_judge(matching, calls, lock):
    def judge(rag, question, batch, first, phrases, visitor, stage):
        with lock:
            calls.append(first)
        found = [{"record_id": group[0].record_id,
                  "decision": "matches" if group[0].record_id in matching else "does_not_match"}
                 for group in batch]
        return found, Decimal("0.001")
    return judge


def _run(monkeypatch, workers, matching, count=60, limit=8, widen_to=60):
    calls, lock = [], threading.Lock()
    monkeypatch.setattr(list_screening, "SCREEN_WORKERS", workers)
    monkeypatch.setattr(list_screening, "WIDEN_WINDOW", 4)
    monkeypatch.setattr(list_screening, "_judge", _fake_judge(matching, calls, lock))
    results, cost = list_screening.screen(None, "Which ads mention kites?", _passages(count), "visitor",
                                          limit=limit, widen_to=widen_to, verify=False)
    return results, cost, calls


def test_parallel_screening_lists_exactly_what_sequential_screening_lists(monkeypatch):
    # Matches continue to ad 13, then stop: widening must end at the same point.
    matching = {f"ad-{n:03d}" for n in (1, 5, 9, 13)}

    sequential, _, _ = _run(monkeypatch, 1, matching)
    parallel, parallel_cost, calls = _run(monkeypatch, 8, matching)

    assert parallel == sequential
    assert [item["record_id"] for item in parallel][-1] == "ad-019"
    # Discarded batches past the stop point were still paid for.
    assert parallel_cost == float(Decimal("0.001") * len(calls))


def test_ads_inside_the_limit_are_always_read(monkeypatch):
    results, _, _ = _run(monkeypatch, 8, set(), limit=8)

    assert [item["record_id"] for item in results] == [f"ad-{n:03d}" for n in range(8)]
