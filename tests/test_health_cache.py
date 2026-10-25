from observatory import db as db_module
from observatory.db import Database
from observatory.models import Filters


class _Conn:
    def __init__(self, counters):
        self.counters = counters

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        assert "pg_stat_user_tables" in sql
        assert set(params[0]) == set(db_module.READ_CACHE_VOLATILE_TABLES)
        writes = self.counters["writes"]

        class _Result:
            def fetchone(self):
                return {"writes": writes, "tables": 12}

        return _Result()


def _database(counters, computed):
    database = Database("postgresql://example.invalid/test", read_cache=True)
    database.connect = lambda vector=False: _Conn(counters)

    def compute():
        computed.append(1)
        return {"status": "ok", "record_counts": {"native": len(computed)}}

    database._compute_health = compute
    return database


def test_health_is_reused_while_source_tables_are_unchanged():
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)

    first = database.health()
    second = database.health()

    assert len(computed) == 1
    assert first == second
    second["record_counts"]["native"] = 99
    assert database.health()["record_counts"]["native"] == 1


def test_health_recomputes_after_a_source_write():
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)

    database.health()
    counters["writes"] = 11

    assert database.health()["record_counts"]["native"] == 2


def test_health_recomputes_after_the_cache_window(monkeypatch):
    counters, computed = {"writes": 10}, []
    database = _database(counters, computed)
    clock = [1000.0]
    monkeypatch.setattr(db_module.time, "monotonic", lambda: clock[0])

    database.health()
    clock[0] += db_module.READ_CACHE_SECONDS + 1

    assert database.health()["record_counts"]["native"] == 2


def test_dashboard_results_are_kept_apart_by_filters_and_page():
    counters, calls = {"writes": 10}, []
    database = _database(counters, [])

    def compute(filters, offset, limit, sort_by, descending):
        calls.append((filters.dataset, offset))
        return {"dataset": filters.dataset, "offset": offset}

    database._compute_dashboard = compute
    native, social = Filters(dataset="native"), Filters(dataset="social")

    assert database.dashboard(native)["dataset"] == "native"
    assert database.dashboard(social)["dataset"] == "social"
    assert database.dashboard(native, offset=20)["offset"] == 20
    assert database.dashboard(native)["dataset"] == "native"
    assert calls == [("native", 0), ("social", 0), ("native", 20)]


def test_social_source_version_is_reused_per_filter():
    counters = {"writes": 10}
    database = _database(counters, [])
    calls = []

    def compute(filters):
        calls.append(filters.sponsors)
        return f"version-{len(calls)}"

    database._compute_social_source_state_version = compute
    everyone = Filters(dataset="social")
    one_company = Filters(dataset="social", sponsors=["Example Energy"])

    assert database.social_source_state_version(everyone) == "version-1"
    assert database.social_source_state_version(one_company) == "version-2"
    assert database.social_source_state_version(everyone) == "version-1"
    counters["writes"] = 11
    assert database.social_source_state_version(everyone) == "version-3"


def test_failed_reads_are_not_cached():
    counters = {"writes": 10}
    database = _database(counters, [])
    attempts = []

    def compute(dataset):
        attempts.append(dataset)
        if len(attempts) == 1:
            raise RuntimeError("database unavailable")
        return {"sponsors": ["Example Energy"]}

    database._compute_facets = compute
    try:
        database.facets("native")
    except RuntimeError:
        pass

    assert database.facets("native") == {"sponsors": ["Example Energy"]}
    assert attempts == ["native", "native"]


def test_tools_and_tests_read_live_by_default():
    database = Database("postgresql://example.invalid/test")
    calls = []
    database.connect = lambda vector=False: (_ for _ in ()).throw(AssertionError("no marker read"))
    database._compute_health = lambda: calls.append(1) or {"status": "ok"}

    database.health()
    database.health()

    assert calls == [1, 1]
