"""Web latency round 1 (2026-11-05): faster without changing what an answer says.

Fictional data only. Covers the background health keeper (readers' cache path unchanged), the
screening pool size as a setting (the widening wave stays WIDEN_WAVE), the writer's concurrent
shards with budget reserved in shard order and parts merged in shard order, generate()'s
reservation hook, and the keeper thread.
"""
import json
import logging
import threading
import time
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from observatory import cli as cli_module
from observatory import db as db_module
from observatory import list_screening
from observatory import rag as rag_module
from observatory import service as service_module
from observatory.budget import LimitReached
from observatory.config import Settings
from observatory.db import Database
from observatory.list_screening import list_answer
from observatory.models import Answer, Citation, CitedStatement, Evidence
from observatory.rag import Rag, reserve_through
from observatory.service import Service

# --- the health keeper refreshes the cached digest without touching the readers' path ---

class _Conn:
    def __init__(self, counters):
        self.counters = counters

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        writes = self.counters["writes"]
        return SimpleNamespace(fetchone=lambda: {"writes": writes, "tables": 12})


def _database(counters, computed, read_cache=True):
    database = Database("postgresql://example.invalid/test", read_cache=read_cache)
    database.connect = lambda vector=False: _Conn(counters)

    def compute():
        computed.append(1)
        return {"status": "ok", "record_counts": {"native": len(computed)}}

    database._compute_health = compute
    return database


def _clock(monkeypatch, start=1000.0):
    clock = [start]
    monkeypatch.setattr(db_module.time, "monotonic", lambda: clock[0])
    return clock


def test_a_refresh_renews_the_entry_and_readers_keep_their_window(monkeypatch):
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    clock = _clock(monkeypatch)

    assert database.health()["record_counts"]["native"] == 1
    clock[0] += db_module.HEALTH_REFRESH_SECONDS
    assert database.refresh_health()["record_counts"]["native"] == 2
    assert len(computed) == 2

    assert database.health()["record_counts"]["native"] == 2  # fresh from the refresh, no computation
    assert len(computed) == 2
    clock[0] += db_module.READ_CACHE_SECONDS + 1  # past the window since the refresh: readers compute as before
    assert database.health()["record_counts"]["native"] == 3


def test_a_slow_refresh_never_replaces_a_fresher_value(monkeypatch):
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    clock = _clock(monkeypatch)
    started, release = threading.Event(), threading.Event()
    first = database._compute_health

    def slow():
        started.set()
        assert release.wait(5)
        return {"status": "ok", "record_counts": {"native": "stale refresh"}}

    database._compute_health = slow
    thread = threading.Thread(target=database.refresh_health)
    thread.start()
    assert started.wait(5)
    database._compute_health = first
    clock[0] += 1
    assert database.health()["record_counts"]["native"] == 1  # a reader computed meanwhile (no entry yet)
    release.set()
    thread.join(5)

    assert database.health()["record_counts"]["native"] == 1  # the older refresh did not overwrite it
    assert database.refresh_health()["record_counts"]["native"] == 2  # a later refresh does renew it
    assert database.health()["record_counts"]["native"] == 2


def test_a_refresh_does_not_block_a_reader():
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    database.health()
    started, release = threading.Event(), threading.Event()
    first = database._compute_health

    def slow():
        started.set()
        assert release.wait(5)
        return first()

    database._compute_health = slow
    thread = threading.Thread(target=database.refresh_health)
    thread.start()
    assert started.wait(5)
    before = time.perf_counter()
    assert database.health()["record_counts"]["native"] == 1  # served from the cache while the refresh runs
    assert time.perf_counter() - before < 1
    release.set()
    thread.join(5)
    assert database.health()["record_counts"]["native"] == 2


def test_a_changed_marker_still_recomputes_for_the_reader():
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    database.refresh_health()
    counters["writes"] = 11
    assert database.health()["record_counts"]["native"] == 2


def test_with_the_cache_off_a_refresh_just_computes():
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed, read_cache=False)
    assert database.refresh_health()["record_counts"]["native"] == 1
    assert database._read_cache == {}  # nothing stored
    assert database.health()["record_counts"]["native"] == 2


def test_the_keeper_refreshes_at_its_interval_and_logs_a_failure(caplog):
    calls, stop = [], threading.Event()
    service = SimpleNamespace(db=SimpleNamespace(refresh_health=lambda: calls.append(1), read_cache=True))
    thread = cli_module.start_health_keeper(service, interval=0.01, stop=stop)
    deadline = time.time() + 5
    while len(calls) < 3 and time.time() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(5)
    assert len(calls) >= 3 and thread.daemon and not thread.is_alive()

    attempts, stop = [], threading.Event()

    def failing():
        attempts.append(1)
        raise RuntimeError("database unavailable")

    with caplog.at_level(logging.WARNING, logger="observatory.cli"):
        thread = cli_module.start_health_keeper(SimpleNamespace(db=SimpleNamespace(refresh_health=failing, read_cache=True)),
                                                interval=0.01, stop=stop)
        deadline = time.time() + 5
        while len(attempts) < 2 and time.time() < deadline:
            time.sleep(0.01)
        stop.set()
        thread.join(5)
    assert len(attempts) >= 2  # a failure is logged and the keeper goes on
    assert "Health refresh failed (RuntimeError); the next request computes it" in caplog.text


def test_the_keeper_interval_sits_inside_the_cache_window():
    assert 0 < db_module.HEALTH_REFRESH_SECONDS < db_module.READ_CACHE_SECONDS


def test_no_keeper_without_the_read_cache():
    calls = []
    assert cli_module.start_health_keeper(SimpleNamespace(db=SimpleNamespace(refresh_health=lambda: calls.append(1), read_cache=False)),
                                          interval=0.01) is None
    time.sleep(0.05)
    assert calls == []


def test_a_request_that_started_earlier_does_not_overwrite_a_later_refresh():
    # A cold start: nothing cached yet, the request's computation starts first (and holds the key
    # lock), the keeper's starts later and finishes first: the keeper's value is kept, the request's
    # own result does not replace it, and both used the one guard and generation counter made in
    # the constructor (no lazy initialisation to race on).
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    guard = database._read_cache_guard
    started, release = threading.Event(), threading.Event()
    first = database._compute_health

    def slow_then_first():
        started.set()
        assert release.wait(5)
        return first()

    database._compute_health = slow_then_first
    seen = {}
    reader = threading.Thread(target=lambda: seen.update(reader=database.health()))
    reader.start()
    assert started.wait(5)
    database._compute_health = first  # the keeper computes at once
    assert database.refresh_health()["record_counts"]["native"] == 1
    release.set()
    reader.join(5)

    assert seen["reader"]["record_counts"]["native"] == 2  # the request got its own (later-finished) result
    assert database.health()["record_counts"]["native"] == 1  # the cache kept the later-started computation
    assert database._read_cache_guard is guard and database._read_cache_generation == 2


# --- screening: the pool size is a setting; the widening wave past `limit` stays WIDEN_WAVE ---

def _passages(count):
    return [SimpleNamespace(record_id=f"ad-{n:03d}", evidence_id=f"ev-{n:03d}", text=f"Ad {n} text") for n in range(count)]


def _counting_judge(matching, in_flight, lock, pause=0.12):
    """A fake judge that records how many batches run at once when each starts."""
    def judge(rag, question, batch, first, phrases, visitor, stage):
        with lock:
            in_flight["now"] += 1
            in_flight["peaks"].append((first, in_flight["now"]))
        time.sleep(pause)
        with lock:
            in_flight["now"] -= 1
        found = [{"record_id": group[0].record_id,
                  "decision": "matches" if group[0].record_id in matching else "does_not_match"} for group in batch]
        return found, Decimal("0.001")
    return judge


def _screen(monkeypatch, rag, matching, count=72, limit=40):
    in_flight, lock = {"now": 0, "peaks": []}, threading.Lock()
    monkeypatch.setattr(list_screening, "WIDEN_WINDOW", 4)
    monkeypatch.setattr(list_screening, "_judge", _counting_judge(matching, in_flight, lock))
    results, cost = list_screening.screen(rag, "Which ads mention kites?", _passages(count), "visitor",
                                          limit=limit, widen_to=count, verify=False)
    return results, cost, in_flight["peaks"]


def test_the_pool_size_comes_from_the_settings_and_falls_back_to_the_module_constant():
    assert Settings().screen_workers == 0  # unset: the code's SCREEN_WORKERS, whatever that branch sets it to
    assert list_screening._workers(None) == list_screening.SCREEN_WORKERS
    assert list_screening._workers(SimpleNamespace()) == list_screening.SCREEN_WORKERS
    assert list_screening._workers(SimpleNamespace(settings=Settings())) == list_screening.SCREEN_WORKERS
    assert list_screening._workers(SimpleNamespace(settings=Settings(screen_workers=16))) == 16


def test_screen_workers_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("OBS_SCREEN_WORKERS", "16")
    assert Settings.from_env().screen_workers == 16
    monkeypatch.delenv("OBS_SCREEN_WORKERS")
    assert Settings.from_env().screen_workers == 0


def test_a_larger_pool_runs_the_first_wave_in_one_round_and_the_same_ads_are_listed(monkeypatch):
    matching = {f"ad-{n:03d}": True for n in (1, 9, 21, 33, 41, 45)}  # matches continue a little past the limit
    narrow = SimpleNamespace(settings=Settings(screen_workers=8))
    wide = SimpleNamespace(settings=Settings(screen_workers=16))

    results_narrow, _, peaks_narrow = _screen(monkeypatch, narrow, matching)
    results_wide, _, peaks_wide = _screen(monkeypatch, wide, matching)

    assert results_wide == results_narrow  # same decisions in the same order
    first_wave = [peak for first, peak in peaks_wide if first <= 40]
    assert len(first_wave) == 10 and max(first_wave) > 8  # the ten batches within the limit ran together
    assert max(peak for first, peak in peaks_narrow if first <= 40) <= 8
    # Past the limit the waves are WIDEN_WAVE batches whatever the pool size.
    later = [peak for first, peak in peaks_wide if first > 40]
    assert later and max(later) <= list_screening.WIDEN_WAVE


def test_the_widening_stop_rule_does_not_depend_on_the_pool_size(monkeypatch):
    matching = {"ad-001": True}  # no match past the limit: widening stops after one wave
    narrow, _, peaks_narrow = _screen(monkeypatch, SimpleNamespace(settings=Settings(screen_workers=8)), matching)
    wide, _, peaks_wide = _screen(monkeypatch, SimpleNamespace(settings=Settings(screen_workers=16)), matching)
    assert wide == narrow
    assert sorted(first for first, _ in peaks_wide if first > 40) == sorted(first for first, _ in peaks_narrow if first > 40)
    assert len([first for first, _ in peaks_wide if first > 40]) == list_screening.WIDEN_WAVE


# --- the writer: shards at once, reservations in shard order, merged in shard order ---

ASK = "What do Tidal Co's ads say about kites? Cite each ad that mentions it."


def _ad(record, text):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="native",
                    title=f"Kite notice {record}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=0, end=len(text))


def _twelve():
    ads = [_ad(f"m{n:02d}", f"Kite model {n} lifts the harbor buoy.") for n in range(12)]
    results = [{"record_id": e.record_id, "evidence_id": e.evidence_id, "decision": "matches", "quote": e.text,
                "reason": "", "title": e.title, "publisher": e.publisher, "sponsor": e.sponsor,
                "published_at": date(2021, 5, 4)} for e in ads]
    return ads, list_answer(ASK, results, ads, scope_total=len(ads)), results


def _written(evidence, cost=0.002):
    return Answer(status="answered", answer="", cost_usd=cost,
                  citations=[Citation(evidence_id=e.evidence_id, quote=e.text) for e in evidence],
                  cited_claims=[CitedStatement(text=f"The ad says: {e.text}", citation_indices=[n])
                                for n, e in enumerate(evidence, 1)])


class _WriterRag:
    """A fake writer that reserves through generate()'s hook and settles, as Rag.generate does, and records
    the model-call interval (after the reservation) per shard."""

    AMOUNT = Decimal("0.010")

    def __init__(self, budget, delays=(), fail=()):
        self.budget, self.delays, self.fail = budget, dict(delays), set(fail)
        self.calls, self.lock = [], threading.Lock()
        self.settings = Settings()

    def generate(self, question, evidence, visitor, **kwargs):
        shard = evidence[0].record_id
        reserve = rag_module._RESERVE_HOOK.get() or self.budget.reserve
        rid = reserve(self.AMOUNT, visitor, "generation", "gpt-5.6-luna")  # LimitReached propagates from here
        started = time.perf_counter()
        time.sleep(self.delays.get(shard, 0.0))
        with self.lock:
            self.calls.append({"shard": shard, "records": [e.record_id for e in evidence], "rid": rid,
                               "start": started, "end": time.perf_counter(), "thread": threading.get_ident()})
        if shard in self.fail:
            self.budget.uncertain(rid, "ValueError")
            raise ValueError("Unverifiable citation")
        self.budget.settle(rid, Decimal("0.002"), {})
        return _written(evidence)


class _RecordingBudget:
    """Reservations numbered in order; every reservation numbered >= refuse_from is refused."""

    def __init__(self, refuse_from=None):
        self.order, self.refuse_from, self.lock = [], refuse_from, threading.Lock()

    def reserve(self, amount, visitor, kind, model):
        with self.lock:
            number = len(self.order) + 1
            if self.refuse_from is not None and number >= self.refuse_from:
                self.order.append(("refused", number))
                raise LimitReached("Monthly API budget reached.")
            self.order.append(("reserved", number))
            return f"rid-{number}"

    def settle(self, rid, actual, usage):
        pass

    def uncertain(self, rid, error_type):
        pass


class _HoldingBudget:
    """A budget with in-flight holds: a reservation needs its whole amount free; settlement releases the hold
    and spends the actual cost (the ledger's arithmetic in miniature)."""

    def __init__(self, available):
        self.available, self.holds, self.refusals, self.lock = Decimal(available), {}, 0, threading.Lock()
        self.order = []

    def reserve(self, amount, visitor, kind, model):
        with self.lock:
            if self.available - sum(self.holds.values(), Decimal(0)) < amount:
                self.refusals += 1
                raise LimitReached("Monthly API budget reached.")
            rid = f"rid-{len(self.order) + 1}"
            self.holds[rid] = amount
            self.order.append(rid)
            return rid

    def settle(self, rid, actual, usage):
        with self.lock:
            self.holds.pop(rid)
            self.available -= Decimal(actual)

    def uncertain(self, rid, error_type):
        with self.lock:
            self.available -= self.holds.pop(rid)


def _service(rag):
    return Service(Settings(), db=SimpleNamespace(), rag=rag)


def test_shards_are_written_at_once_merged_in_shard_order_and_reserved_in_order():
    ads, listed, results = _twelve()
    budget = _RecordingBudget()
    rag = _WriterRag(budget, delays={"m00": 0.25, "m04": 0.05, "m08": 0.15})

    merged, cost = _service(rag)._read_matched_sources(ASK, listed, results, ads, "offline")

    shards = sorted((c for c in rag.calls if len(c["records"]) == 4), key=lambda c: c["shard"])
    assert [c["shard"] for c in shards] == ["m00", "m04", "m08"]
    # The model calls (after each reservation) overlapped: all three started before the first one ended.
    assert max(c["start"] for c in shards) < min(c["end"] for c in shards)
    assert len({c["thread"] for c in shards}) == 3
    # Merged in shard order whatever the finishing order: citations m00..m11, claims numbered 1..12.
    assert [c.evidence_id for c in merged.citations] == [e.evidence_id for e in ads]
    assert [c.citation_indices for c in merged.cited_claims] == [[n] for n in range(1, 13)]
    assert merged.research_trace["content_zones"] == [
        {"records": [e.record_id for e in ads[0:4]], "kind": "shard", "status": "answered"},
        {"records": [e.record_id for e in ads[4:8]], "kind": "shard", "status": "answered"},
        {"records": [e.record_id for e in ads[8:12]], "kind": "shard", "status": "answered"}]
    assert merged.structured_result["content_reading"]["status"] == "complete"
    assert abs(cost - 0.006) < 1e-9
    assert [c["rid"] for c in shards] == ["rid-1", "rid-2", "rid-3"]  # reserved in shard order


def _skipping(rag, question, evidence, visitor, **kwargs):
    """The fake call, but a 4-ad shard's last ad is left uncited (the follow-up round reads it)."""
    part = _WriterRag.generate(rag, question, evidence, visitor, **kwargs)
    if len(evidence) == 4:
        return part.model_copy(update={"citations": part.citations[:3], "cited_claims": part.cited_claims[:3]})
    return part


def test_the_follow_up_round_runs_after_every_shard():
    ads, listed, results = _twelve()
    rag = _WriterRag(_RecordingBudget(), delays={"m00": 0.1, "m04": 0.1, "m08": 0.1})
    rag.generate = Mock(side_effect=lambda q, evidence, visitor, **k: _skipping(rag, q, evidence, visitor, **k))

    merged, _ = _service(rag)._read_matched_sources(ASK, listed, results, ads, "offline")

    shards = [c for c in rag.calls if len(c["records"]) == 4]
    follow_up = [c for c in rag.calls if len(c["records"]) == 3]
    assert len(shards) == 3 and len(follow_up) == 1
    assert follow_up[0]["start"] >= max(c["end"] for c in shards)
    assert follow_up[0]["records"] == ["m03", "m07", "m11"]
    assert merged.research_trace["content_zones"][-1] == {"records": ["m03", "m07", "m11"], "kind": "follow_up", "status": "answered"}
    assert merged.structured_result["content_reading"]["status"] == "complete"
    assert len(merged.citations) == 12


def test_a_failed_shard_is_recorded_and_the_other_shards_are_still_merged():
    ads, listed, results = _twelve()
    rag = _WriterRag(_RecordingBudget(), fail={"m04"})

    merged, cost = _service(rag)._read_matched_sources(ASK, listed, results, ads, "offline")

    assert [zone["status"] for zone in merged.research_trace["content_zones"][:3]] == ["answered", "failed", "answered"]
    assert merged.research_trace["content_zones"][1]["reason"] == "ValueError"
    assert [c.evidence_id for c in merged.citations][:8] == [e.evidence_id for e in [*ads[0:4], *ads[8:12]]]
    assert merged.structured_result["content_reading"]["status"] == "partial"
    assert "screening quote only" in merged.answer
    assert abs(cost - 0.004) < 1e-9


def test_a_tight_budget_completes_exactly_as_the_sequential_writer_would():
    # 0.015 free, 0.010 reserved per call, 0.002 settled: one after another all three shards fit;
    # at once the second and third reservations are refused while earlier holds stand, so they wait
    # for the earlier shards to settle and ask again.
    ads, listed, results = _twelve()
    budget = _HoldingBudget("0.015")
    rag = _WriterRag(budget, delays={"m00": 0.1, "m04": 0.1, "m08": 0.1})

    merged, cost = _service(rag)._read_matched_sources(ASK, listed, results, ads, "offline")

    assert [zone["status"] for zone in merged.research_trace["content_zones"]] == ["answered", "answered", "answered"]
    assert budget.order == ["rid-1", "rid-2", "rid-3"] and budget.refusals == 2
    assert budget.available == Decimal("0.009") and budget.holds == {}
    assert abs(cost - 0.006) < 1e-9


def test_a_final_refusal_stops_the_later_shards_before_they_reserve_and_marks_them_limited():
    # Since the per-question cap (a14d3a0) a limit no longer ends the answer: the refused shard and
    # the ones after it keep their screening quotes, and no follow-up call is tried.
    ads, listed, results = _twelve()
    budget = _RecordingBudget(refuse_from=2)  # every reservation after the first is refused, retries included
    rag = _WriterRag(budget, delays={"m00": 0.1})
    sink = []

    merged, cost = _service(rag)._read_matched_sources(ASK, listed, results, ads, "offline", cost_sink=sink)

    # Shard 2: refused, waited for shard 1 to finish, refused again (final). Shard 3 never reached the budget.
    assert budget.order == [("reserved", 1), ("refused", 2), ("refused", 3)]
    assert [c["shard"] for c in rag.calls] == ["m00"]  # the dispatched first shard finished and was paid
    assert sink == [0.002] and abs(cost - 0.002) < 1e-9
    assert merged.research_trace["content_zones"] == [
        {"records": [e.record_id for e in ads[0:4]], "kind": "shard", "status": "answered"},
        {"records": [e.record_id for e in ads[4:8]], "kind": "shard", "status": "limited", "reason": "LimitReached"},
        {"records": [e.record_id for e in ads[8:12]], "kind": "shard", "status": "limited"}]
    assert merged.structured_result["content_reading"]["status"] == "partial"
    assert "screening quote only" in merged.answer


def _reserve_in_thread(turnstile, index, out):
    def run():
        try:
            out[index] = turnstile.hook(index)(Decimal("0.01"), "v", "generation", "m")
        except LimitReached as exc:
            out[index] = exc
    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_a_shard_that_fails_before_reserving_passes_its_turn_without_skipping_an_earlier_one():
    turnstile = service_module._OrderedReservations(_RecordingBudget())
    out = {}
    third = _reserve_in_thread(turnstile, 2, out)
    turnstile.release(1)  # shard 1 failed before reserving while shard 0 is still preparing
    time.sleep(0.1)
    assert 2 not in out  # shard 2 keeps waiting for shard 0
    first = _reserve_in_thread(turnstile, 0, out)
    first.join(2)
    third.join(2)
    assert out == {0: "rid-1", 2: "rid-2"}  # shard 0 reserved first


def test_a_refusal_of_the_first_shard_is_final_for_the_later_ones():
    budget = _RecordingBudget(refuse_from=1)
    turnstile = service_module._OrderedReservations(budget)
    out = {}
    _reserve_in_thread(turnstile, 0, out).join(2)
    _reserve_in_thread(turnstile, 1, out).join(2)
    assert isinstance(out[0], LimitReached) and isinstance(out[1], LimitReached)
    assert budget.order == [("refused", 1), ("refused", 2)]  # shard 0 asked twice; shard 1 never asked


def test_a_refused_shard_waits_for_the_earlier_calls_to_settle_before_asking_again():
    budget = _HoldingBudget("0.015")
    turnstile = service_module._OrderedReservations(budget)
    out = {}
    _reserve_in_thread(turnstile, 0, out).join(2)
    assert out[0] == "rid-1"
    second = _reserve_in_thread(turnstile, 1, out)
    time.sleep(0.1)
    assert 1 not in out and budget.refusals == 1  # refused once, waiting for shard 0 to settle
    budget.settle("rid-1", Decimal("0.002"), {})
    turnstile.release(0)
    second.join(2)
    assert out[1] == "rid-2"


# --- generate() takes the reservation hook for the current thread ---

def _rag_with_fakes(reservations):
    class FakeDB:
        def validate_evidence(self, evidence):
            return True

        @contextmanager
        def connect(self):
            yield SimpleNamespace(execute=lambda *args: None)

    def parse(**request):
        item = json.loads(request["input"][1]["content"])["evidence"][0]
        primary = next(iter(item["quote_catalog"]))
        supports = [pid for pid in item["passage_context"][primary]["sentence_context_passage_ids"] if pid != primary]
        output = request["text_format"].model_validate({
            "status": "answered",
            "claims": [{"passage_id": primary, "text": "The notice says kites supply power.", "support_passage_ids": supports}],
            "summary": [{"text": "Kites supply power.", "citation_indices": [1]}],
            "sections": [{"title": "Kites", "citation_indices": [1]}],
        })
        usage = SimpleNamespace(input_tokens=200, output_tokens=90, input_tokens_details=SimpleNamespace(cached_tokens=0),
                                model_dump=lambda: {"input_tokens": 200, "output_tokens": 90})
        return SimpleNamespace(status="completed", output_parsed=output, usage=usage, model="gpt-5.6-luna")

    rag = Rag(FakeDB(), SimpleNamespace(generation_model="gpt-5.6-luna", max_output_tokens=512),
              client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    rag.budget = SimpleNamespace(reserve=lambda *args: reservations.append(("budget", args)) or "budget-rid",
                                 settle=lambda *args: None, uncertain=lambda *args: None, cancel_unsent=lambda *args: None)
    return rag


def test_generate_reserves_through_the_hook_only_inside_the_block():
    reservations = []
    rag = _rag_with_fakes(reservations)
    hooked = []
    evidence = [_ad("r1", "Tidal kites will supply cheap power to the harbor.")]

    with reserve_through(lambda *args: hooked.append(args) or "hook-rid"):
        inside = rag.generate("What do the ads say about kites?", evidence, "offline")
    outside = rag.generate("What do the ads say about kites?", evidence, "offline")

    assert inside.status == outside.status == "answered"
    assert len(hooked) == 1 and hooked[0][1:] == ("offline", "generation", "gpt-5.6-luna") and hooked[0][0] > 0
    assert [kind for kind, _ in reservations] == ["budget"]  # the call outside the block used the budget itself


def test_the_hook_is_per_thread():
    seen = {}

    def other():
        seen["other"] = rag_module._RESERVE_HOOK.get()

    with reserve_through(lambda *args: "hook-rid"):
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
        seen["inside"] = rag_module._RESERVE_HOOK.get() is not None
    assert seen == {"other": None, "inside": True}
    assert rag_module._RESERVE_HOOK.get() is None
