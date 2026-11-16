"""Opt-in, real import-review checks in one owned disposable schema of the private test database.

Set OBS_RUN_IMPORT_REVIEW_INTEGRATION=1 and an explicit OBS_TEST_DATABASE_URL (private cluster from
scripts/private_test_postgres.py). Fictional rows only; no model calls; the schema is dropped afterwards.
"""

import os
import threading
import time
from uuid import uuid4

import pytest
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql

from observatory.db import Database
from observatory.import_review import (
    Approval,
    ImportReviewMismatch,
    ImportReviewRequired,
    plan_import,
    review_gate,
    reviewed_import,
)
from observatory.models import ImportBatch, RecordInput

pytestmark = pytest.mark.integration


class SchemaDatabase(Database):
    def __init__(self, url, schema):
        super().__init__(url)
        self.schema = schema

    def connect(self, vector=False):
        if vector:
            raise ValueError("Import review checks do not use vectors")
        return verified_test_connection(self.url, self.schema)


@pytest.fixture()
def db():
    if os.environ.get("OBS_RUN_IMPORT_REVIEW_INTEGRATION") != "1":
        pytest.skip("Explicit import-review integration opt-in is absent")
    url = configured_test_url()
    schema = f"obs_review_{uuid4().hex}"
    with verified_test_connection(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        database = SchemaDatabase(url, schema)
        database.initialize()
        yield database
    finally:
        with verified_test_connection(url, autocommit=True) as conn:
            owned = conn.execute("SELECT nspowner=current_user::regrole AS owned FROM pg_namespace "
                                 "WHERE nspname=%s", (schema,)).fetchone()
            if owned and owned["owned"]:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def rec(record_id, body="Fictional kite festival announcement.", **changes):
    fields = {"record_id": record_id, "dataset": "social", "platform": "Twitter",
              "url": f"https://example.invalid/{record_id}", "body": body, "sponsor": "Example Kites",
              "archive_url": f"https://archive.example.invalid/{record_id}", "countable": True,
              "retrievable": False}
    return RecordInput(**(fields | changes))


def batch(*records):
    return ImportBatch(records=list(records), source_hashes={"fictional.jsonl": "0" * 64})


def state(db, record_id):
    with db.connect() as conn:
        return conn.execute("SELECT r.active,v.body,v.payload->>'archive_url' AS archive FROM records r "
                            "JOIN record_versions v ON v.version_id=r.current_version WHERE r.record_id=%s",
                            (record_id,)).fetchone()


def imports(db):
    with db.connect() as conn:
        return conn.execute("SELECT count(*) AS n FROM imports").fetchone()["n"]


def test_new_and_unchanged_batches_import_without_a_decision(db, tmp_path):
    code, report = reviewed_import(db, batch(rec("a"), rec("b")), review_dir=tmp_path / "r1")
    assert code == 0 and report["new_versions"] == 2 and report["review"]["approval"] == "automatic"
    code, report = reviewed_import(db, batch(rec("a"), rec("b")), review_dir=tmp_path / "r2")
    assert code == 0 and report["unchanged"] == 2


def test_a_changed_record_stops_until_all_latest_is_approved(db, tmp_path):
    reviewed_import(db, batch(rec("a")), review_dir=tmp_path / "r0")
    before = imports(db)
    new = rec("a", body="Fictional kite festival, new date.", archive_url="")
    code, report = reviewed_import(db, batch(new), review_dir=tmp_path / "r1")
    assert code == 3 and report["status"] == "approval_required"
    assert "IMPORT STOPPED" in report["alert"] and report["losses"] == {"archive_url": 1}
    assert imports(db) == before and state(db, "a")["body"] == "Fictional kite festival announcement."
    assert (tmp_path / "r1/report.json").exists() and (tmp_path / "r1/decisions.template.json").exists()
    code, report = reviewed_import(db, batch(new), review_dir=tmp_path / "r2", approve="all-latest",
                                   fingerprint=report["fingerprint"])
    assert code == 0 and report["review"]["took_latest"] == ["a"]
    assert state(db, "a")["body"] == "Fictional kite festival, new date." and state(db, "a")["archive"] == ""


def test_per_item_keep_leaves_the_old_version_and_latest_takes_the_new_one(db, tmp_path):
    reviewed_import(db, batch(rec("a"), rec("b")), review_dir=tmp_path / "r0")
    changed = batch(rec("a", body="Changed fictional a."), rec("b", body="Changed fictional b."))
    _, report = reviewed_import(db, changed, review_dir=tmp_path / "r1")
    approval = Approval(report["fingerprint"], "per-item", {"a": "keep", "b": "latest"}, "Reviewer", "now")
    result = db.import_batch(changed, review=review_gate(approval))
    assert result["review"]["kept_at_current_version"] == ["a"] and result["new_versions"] == 1
    assert state(db, "a")["body"] == "Fictional kite festival announcement."
    assert state(db, "b")["body"] == "Changed fictional b."


def test_snapshot_keeps_a_kept_record_and_needs_its_own_retirement_approval(db, tmp_path):
    reviewed_import(db, batch(rec("a"), rec("b"), rec("c")), review_dir=tmp_path / "r0")
    snap = batch(rec("a", body="Changed fictional a."), rec("b"))
    _, report = reviewed_import(db, snap, "social", review_dir=tmp_path / "r1")
    assert report["counts"]["retire"] == 1
    keep_only = Approval(report["fingerprint"], "per-item", {"a": "keep"}, "Reviewer", "now")
    with pytest.raises(ImportReviewRequired):
        db.import_batch(snap, "social", review=review_gate(keep_only, "social"))
    approval = Approval(report["fingerprint"], "per-item", {"a": "keep"}, "Reviewer", "now", retire_approved=True)
    result = db.import_batch(snap, "social", review=review_gate(approval, "social"))
    assert result["deactivated"] == ["c"]
    assert state(db, "a")["active"] is True and state(db, "a")["body"] == "Fictional kite festival announcement."
    assert state(db, "c")["active"] is False


def test_reactivating_a_retired_record_needs_approval(db, tmp_path):
    reviewed_import(db, batch(rec("a"), rec("b")), review_dir=tmp_path / "r0")
    with db.connect() as conn:
        plan = plan_import(conn, batch(rec("a")), "social")
    db.import_batch(batch(rec("a")), "social", review=review_gate(
        Approval(plan["fingerprint"], "retire-only", retire_approved=True), "social"))
    code, report = reviewed_import(db, batch(rec("b")), review_dir=tmp_path / "r1")
    assert code == 3 and report["counts"]["reactivate"] == 1 and state(db, "b")["active"] is False


def test_disjoint_shards_reported_first_import_one_after_another_with_their_fingerprints(db, tmp_path):
    reviewed_import(db, batch(rec("old")), review_dir=tmp_path / "r0")
    first, second = batch(rec("s1-a"), rec("s1-b")), batch(rec("s2-a"), rec("old"))
    reports = [reviewed_import(db, shard, review_dir=tmp_path / f"report{n}", review_only=True)[1]
               for n, shard in enumerate((first, second))]
    assert [r["needs_approval"] for r in reports] == [False, False] and state(db, "s1-a") is None
    for n, (shard, report) in enumerate(zip((first, second), reports)):
        code, result = reviewed_import(db, shard, review_dir=tmp_path / f"import{n}", fingerprint=report["fingerprint"])
        assert code == 0 and result["review"]["approval"] == "automatic"
    assert all(state(db, rid)["active"] for rid in ("s1-a", "s1-b", "s2-a", "old"))


def test_a_reviewed_shard_fingerprint_is_refused_after_its_records_changed(db, tmp_path):
    shard = batch(rec("t-a"))
    _, report = reviewed_import(db, shard, review_dir=tmp_path / "report", review_only=True)
    reviewed_import(db, batch(rec("t-a", body="Another fictional text.")), review_dir=tmp_path / "other")
    with pytest.raises(ImportReviewMismatch):
        reviewed_import(db, shard, review_dir=tmp_path / "import", fingerprint=report["fingerprint"])
    assert state(db, "t-a")["body"] == "Another fictional text."


def test_a_change_made_after_the_review_aborts_the_approved_import(db, tmp_path):
    reviewed_import(db, batch(rec("a")), review_dir=tmp_path / "r0")
    changed = batch(rec("a", body="Reviewed fictional change."))
    _, report = reviewed_import(db, changed, review_dir=tmp_path / "r1")
    # Another writer takes the import lock, changes the record and commits while the approved import waits.
    with db.connect() as other:
        other.execute("SELECT pg_advisory_xact_lock(54901)")
        errors = []
        worker = threading.Thread(target=lambda: errors.append(_try(db, changed, report["fingerprint"])))
        worker.start()
        _wait_for_lock_waiter(db)
        other.execute("UPDATE records SET active=false WHERE record_id='a'")
        other.commit()
    worker.join(30)
    assert errors and isinstance(errors[0], ImportReviewMismatch)
    assert state(db, "a")["body"] == "Fictional kite festival announcement." and state(db, "a")["active"] is False


def _try(db, changed, fingerprint):
    try:
        db.import_batch(changed, review=review_gate(Approval(fingerprint, "all-latest")))
    except Exception as exc:  # noqa: BLE001 - returned for the assertion
        return exc
    return None


def _wait_for_lock_waiter(db, timeout=20):
    """Until another session is visibly waiting for import lock 54901 (not a fixed sleep)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.connect() as conn:
            if conn.execute("SELECT count(*) AS n FROM pg_locks WHERE locktype='advisory' AND objid=54901 "
                            "AND NOT granted").fetchone()["n"]:
                return
        time.sleep(0.05)
    raise AssertionError("The approved import never waited for the import lock")


def test_a_failure_after_the_first_write_rolls_back_records_and_receipt(db, tmp_path, monkeypatch):
    from observatory import indexing

    reviewed_import(db, batch(rec("a")), review_dir=tmp_path / "r0")
    before, versions = imports(db), _versions(db)
    changed = batch(rec("a", body="Changed fictional a."), rec("b"))
    _, report = reviewed_import(db, changed, review_dir=tmp_path / "r1")

    def fail(conn, profile_id):
        raise RuntimeError("injected failure after the record writes")

    monkeypatch.setattr(indexing, "record_preparation", fail)
    with pytest.raises(RuntimeError, match="injected"):
        db.import_batch(changed, review=review_gate(Approval(report["fingerprint"], "all-latest")))
    assert imports(db) == before and _versions(db) == versions
    assert state(db, "a")["body"] == "Fictional kite festival announcement." and state(db, "b") is None


def _versions(db):
    with db.connect() as conn:
        return conn.execute("SELECT count(*) AS n FROM record_versions").fetchone()["n"]
