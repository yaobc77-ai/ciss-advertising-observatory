"""count_public counts without reading any payload: the lean count SQL and migration 0009.

Unit checks use a fake connection; the integration check needs an explicit private cluster
(OBS_TEST_DATABASE_URL) and works in a schema of its own, never in public tables.
"""

import re
from uuid import uuid4

import pytest
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql
from psycopg.conninfo import make_conninfo

from observatory.db import Database
from observatory.migrations import discover_migrations, run_migrations
from observatory.models import Filters

COUNTABLE_TERM = "(v.payload->>'countable')::boolean"
INDEX_NAME = "record_versions_countable"
COUNT_PREFIX = ("SELECT count(*) AS n FROM records r "
                "JOIN record_versions v ON v.version_id=r.current_version WHERE ")


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    """Answers the read cache's write-marker query; records every other statement."""

    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        if "pg_stat_user_tables" in statement:
            return _Result({"writes": self.database.writes, "tables": 12})
        self.database.statements.append((statement, params))
        return _Result({"n": 7})


class _Database(Database):
    def __init__(self, read_cache=False):
        super().__init__("postgresql://example.invalid/test", read_cache=read_cache)
        self.statements = []
        self.writes = 10

    def connect(self, vector=False):
        return _Connection(self)


def test_counts_the_current_versions_without_the_lateral_join_or_projection():
    database = _Database()

    assert database.count_public(Filters(dataset="social")) == 7

    [(statement, params)] = database.statements
    where, expected = Database.where(Filters(dataset="social"))
    assert statement == COUNT_PREFIX + where
    assert params == expected
    assert COUNTABLE_TERM in statement and "r.active" in statement
    for absent in ("LATERAL", "date_inferences", "payload->>'title'", "retrievable", "labels"):
        assert absent not in statement


@pytest.mark.parametrize("filters", [
    Filters(dataset="all"),
    Filters(dataset="native", publishers=["Publisher A"], date_from="2020-01-01", include_unknown_dates=False),
    Filters(dataset="social", replies=["reply"], accounts=["Account A"], date_presence="known"),
    Filters(dataset="all", include_inferred_dates=True, date_to="2021-12-31"),
    Filters(dataset="native", labels=["ff_labels.fossil_fuel_binary"], record_ids=["r1", "r2"]),
])
def test_every_filter_term_and_parameter_reaches_the_count(filters):
    database = _Database()
    database.count_public(filters)
    [(statement, params)] = database.statements
    where, expected = Database.where(filters)
    assert statement == COUNT_PREFIX + where
    assert params == expected


def test_scope_validation_still_refuses_before_any_statement():
    database = _Database()
    # model_copy bypasses the model validator; where() checks the scope again.
    with pytest.raises(ValueError, match="Account filters"):
        database.count_public(Filters(dataset="native").model_copy(update={"accounts": ["x"]}))
    assert database.statements == []


def test_count_is_reused_until_a_source_table_is_written():
    database = _Database(read_cache=True)

    assert database.count_public(Filters(dataset="social")) == 7
    assert database.count_public(Filters(dataset="social")) == 7
    assert len(database.statements) == 1

    database.count_public(Filters(dataset="all"))
    assert len(database.statements) == 2  # another scope is another key

    database.writes += 1
    database.count_public(Filters(dataset="social"))
    assert len(database.statements) == 3


def test_migration_0009_creates_the_index_the_count_can_use():
    ninth = discover_migrations()[8]
    assert ninth.version == 9 and ninth.name == "0009_countable_version_index.sql"
    statements = [s.strip() for s in re.sub(r"--[^\n]*", "", ninth.sql).split(";") if s.strip()]
    assert len(statements) == 1
    match = re.fullmatch(
        r"CREATE INDEX IF NOT EXISTS (\w+)\s+ON record_versions\s*\(version_id\)\s+WHERE\s+(.+)",
        statements[0], re.S,
    )
    assert match and match[1] == INDEX_NAME
    # The predicate is the count's own countable term, so the planner can drop that filter.
    assert match[2].strip() == COUNTABLE_TERM.replace("v.payload", "payload")


@pytest.fixture()
def private_schema():
    url = configured_test_url()
    schema = "obs_count_index_" + uuid4().hex
    with verified_test_connection(url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield url, schema
    finally:
        with verified_test_connection(url) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


SYNTHETIC_RECORDS = [
    # record_id, dataset, current_version, active, versions: (version_id, payload)
    ("n-counted", "native", "v-n-counted", True, [("v-n-counted", '{"countable": true}')]),
    ("n-not-countable", "native", "v-n-no", True, [("v-n-no", '{"countable": false}')]),
    ("n-retired", "native", "v-n-retired", False, [("v-n-retired", '{"countable": true}')]),
    ("n-revised", "native", "v-n-revised-2", True, [("v-n-revised-1", '{"countable": true}'),
                                                   ("v-n-revised-2", '{"countable": true}')]),
    ("s-counted", "social", "v-s-counted", True, [("v-s-counted", '{"countable": true, "published_at": "2021-03-04"}')]),
    ("s-missing-flag", "social", "v-s-missing", True, [("v-s-missing", '{"platform": "Example"}')]),
    ("s-not-countable", "social", "v-s-no", True, [("v-s-no", '{"countable": false}')]),
]
EXPECTED = {"native": 2, "social": 1, "all": 3}


@pytest.mark.integration
def test_migrated_schema_counts_the_same_rows_as_public_rows_and_uses_the_index(private_schema):
    url, schema = private_schema
    with verified_test_connection(url, schema) as conn:
        run_migrations(conn)
        for record_id, dataset, current, active, versions in SYNTHETIC_RECORDS:
            conn.execute("INSERT INTO records(record_id,dataset,current_version,active) VALUES (%s,%s,%s,%s)",
                         (record_id, dataset, current, active))
            for version_id, payload in versions:
                conn.execute("INSERT INTO record_versions(version_id,record_id,body,body_hash,payload) "
                             "VALUES (%s,%s,'fabricated text','synthetic-hash',%s::jsonb)",
                             (version_id, record_id, payload))
        conn.execute("ANALYZE records")
        conn.execute("ANALYZE record_versions")

    database = Database(make_conninfo(url, options=f"-c search_path={schema},public"))
    for dataset, expected in EXPECTED.items():
        scope = Filters(dataset=dataset)
        assert database.count_public(scope) == len(database.public_rows(scope)) == expected

    recorder = _Database()
    recorder.count_public(Filters(dataset="social"))
    [(statement, params)] = recorder.statements
    with verified_test_connection(url, schema) as conn:
        conn.execute("SET LOCAL enable_seqscan = off")
        plan = "\n".join(row["QUERY PLAN"] for row in conn.execute("EXPLAIN " + statement, params))
    assert INDEX_NAME in plan, plan
