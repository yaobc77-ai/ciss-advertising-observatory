"""Keyword coverage scope counts are reused in the application process until data changes."""

from contextlib import nullcontext

from observatory.db import Database
from observatory.models import Filters


class Rows(list):
    def fetchall(self):
        return self

    def fetchone(self):
        return self[0] if self else None


HIT = {"evidence_id": "n1-0", "record_id": "n1", "version_id": "v1", "dataset": "native",
       "title": "Fictional", "text": "Harbor ferry timetable.", "start": 0, "end": 23,
       "paragraph_ids": ["p1"], "score": 1}


class Connection:
    """Scripted rows for one keyword search with coverage; this is not a SQL engine."""

    def __init__(self):
        self.calls, self.writes = [], 1

    def commit(self):
        pass

    def execute(self, sql, params=None):
        self.calls.append(sql)
        if "pg_stat_user_tables" in sql:
            return Rows([{"writes": self.writes, "tables": 3}])
        if not params or "set_config" in sql:
            return Rows()
        if "lexical_coverage" in sql:
            return Rows([dict(HIT)])
        if "AS scope_records" in sql:
            return Rows([{"scope_records": 7, "scope_chunks": 9}])
        if "to_tsvector('english',term)" in sql:
            return Rows([{"term": term, "lexemes": [term]} for term in params[0]])
        if "matching_records" in sql:
            return Rows([{"term": term, "matching_records": 1, "returned_ids": ["n1-0"]} for term in params[0]])
        return Rows()


def database(connection, read_cache):
    db = Database("", read_cache=read_cache)
    db.connect = lambda **kwargs: nullcontext(connection)
    return db


def scope_reads(connection):
    return sum("AS scope_records" in sql for sql in connection.calls)


def report(db):
    return db.search_report("harbor ferry", Filters(dataset="native"))["diagnostics"]


def test_the_application_counts_a_scope_once_while_data_is_unchanged():
    connection = Connection()
    db = database(connection, read_cache=True)
    first, second = report(db), report(db)
    assert scope_reads(connection) == 1
    assert (first["scope_records"], first["scope_chunks"]) == (second["scope_records"], second["scope_chunks"]) == (7, 9)
    assert first["term_details"] == second["term_details"]


def test_a_write_counts_the_scope_again():
    connection = Connection()
    db = database(connection, read_cache=True)
    report(db)
    connection.writes += 1
    report(db)
    assert scope_reads(connection) == 2


def test_the_write_counters_are_read_before_the_retrieval_snapshot():
    connection = Connection()
    report(database(connection, read_cache=True))
    marker = next(i for i, sql in enumerate(connection.calls) if "pg_stat_user_tables" in sql)
    snapshot = next(i for i, sql in enumerate(connection.calls) if "REPEATABLE READ" in sql)
    assert marker < snapshot


def test_tools_and_tests_count_live_in_each_snapshot():
    connection = Connection()
    db = database(connection, read_cache=False)
    report(db), report(db)
    assert scope_reads(connection) == 2
    assert not any("pg_stat_user_tables" in sql for sql in connection.calls)


def test_a_count_older_than_the_read_cache_lifetime_is_recounted(monkeypatch):
    import observatory.db as db_module

    connection = Connection()
    db = database(connection, read_cache=True)
    now = [100.0]
    monkeypatch.setattr(db_module.time, "monotonic", lambda: now[0])
    report(db)
    now[0] += db_module.READ_CACHE_SECONDS + 1
    report(db)
    assert scope_reads(connection) == 2


def test_different_filters_do_not_share_a_count():
    connection = Connection()
    db = database(connection, read_cache=True)
    db.search_report("harbor ferry", Filters(dataset="native"))
    db.search_report("harbor ferry", Filters(dataset="social"))
    db.search_report("harbor ferry", Filters(dataset="native"))
    assert scope_reads(connection) == 2


def test_the_least_recently_used_count_is_dropped_past_the_entry_limit(monkeypatch):
    import observatory.db as db_module

    monkeypatch.setattr(db_module, "SCOPE_COUNT_ENTRIES", 1)
    connection = Connection()
    db = database(connection, read_cache=True)
    db.search_report("harbor ferry", Filters(dataset="native"))
    db.search_report("harbor ferry", Filters(dataset="social"))
    db.search_report("harbor ferry", Filters(dataset="native"))
    assert scope_reads(connection) == 3
