"""Migration 0007: the database itself enforces version identity and references."""

from uuid import uuid4

import psycopg
import pytest
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql

from observatory.migrations import run_migrations

pytestmark = pytest.mark.integration


@pytest.fixture()
def connection():
    url = configured_test_url()
    schema = "obs_integrity_test_" + uuid4().hex
    with verified_test_connection(url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        with verified_test_connection(url, schema) as conn:
            run_migrations(conn)
            with conn.transaction():
                conn.execute("INSERT INTO records VALUES ('r1','native','v1',true),('r2','native','v2',true)")
                conn.execute("INSERT INTO record_versions(version_id,record_id,body,body_hash,payload) VALUES "
                             "('v1','r1','one','h1','{}'),('v2','r2','two','h2','{}')")
            yield conn
    finally:
        with verified_test_connection(url) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.parametrize("statement", [
    "UPDATE record_versions SET payload='{\"title\":\"edited\"}' WHERE version_id='v1'",
    "UPDATE record_versions SET body='edited' WHERE version_id='v1'",
    "DELETE FROM record_versions WHERE version_id='v1'",
])
def test_a_stored_version_cannot_be_rewritten_or_removed(connection, statement):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="immutable"):
        with connection.transaction():
            connection.execute(statement)


def test_a_new_version_is_the_way_to_change_a_record(connection):
    with connection.transaction():
        connection.execute("INSERT INTO record_versions(version_id,record_id,body,body_hash,payload) "
                           "VALUES ('v1b','r1','one edited','h3','{}')")
        connection.execute("UPDATE records SET current_version='v1b' WHERE record_id='r1'")
    assert connection.execute("SELECT current_version FROM records WHERE record_id='r1'").fetchone()["current_version"] == "v1b"


@pytest.mark.parametrize("statement", [
    "UPDATE records SET current_version='v2' WHERE record_id='r1'",       # another record's version
    "UPDATE records SET current_version='missing' WHERE record_id='r1'",  # no such version
])
def test_a_record_points_only_to_its_own_existing_version(connection, statement):
    # The check is deferred to commit (a record and its first version are written
    # together); checking immediately shows the same rule.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection.transaction():
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            connection.execute(statement)


def test_a_chunk_cannot_mix_one_records_id_with_anothers_version(connection):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection.transaction():
            connection.execute("INSERT INTO chunks(chunk_id,record_id,version_id,text,text_hash,start_char,end_char,"
                               "paragraph_ids,token_count) VALUES ('c1','r1','v2','two','t',0,3,'[]',1)")
