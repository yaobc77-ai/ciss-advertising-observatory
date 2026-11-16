"""Report-only review and fingerprint-bound imports of batches that need no approval (fictional data, no database)."""

import contextlib
import json

import pytest

from observatory.import_review import (
    Approval,
    ImportReviewMismatch,
    ImportReviewRequired,
    plan_import,
    review_gate,
    reviewed_import,
)
from observatory.models import ImportBatch, RecordInput
from tests.test_import_review import FakeConnection


def record(record_id, body="Fictional body."):
    return RecordInput(record_id=record_id, dataset="native", url=f"https://example.org/{record_id}", body=body)


class FakeDb:
    """Opens the fake connection; any import attempt is recorded so a test can assert that none happened."""

    def __init__(self, conn):
        self.conn, self.imports = conn, []

    @contextlib.contextmanager
    def connect(self):
        yield self.conn

    def import_batch(self, batch, snapshot_dataset=None, review=None):
        records, receipt = review(self.conn, batch)
        self.imports.append([r.record_id for r in records])
        return {"imported": [r.record_id for r in records], "review": receipt}


class ReadOnlyConnection(FakeConnection):
    def execute(self, query, params=None):
        if query.startswith("SET TRANSACTION"):
            return None
        return super().execute(query, params)


def existing(record_id, body):
    from observatory.db import record_payload_version

    old = record(record_id, body=body)
    _, version = record_payload_version(old)
    return {"record_id": record_id, "dataset": "native", "current_version": version,
            "active": True, "payload": old.model_dump(mode="json")}


def test_report_only_never_imports_a_batch_that_only_adds_records(tmp_path):
    db = FakeDb(ReadOnlyConnection([]))
    batch = ImportBatch(records=[record("b"), record("a")])
    code, report = reviewed_import(db, batch, review_dir=tmp_path / "review", review_only=True)
    assert code == 0 and db.imports == []
    assert report["status"] == "report_only" and report["written"] is False
    assert report["needs_approval"] is False and report["counts"]["new"] == 2
    assert json.loads((tmp_path / "review/new_records.json").read_text(encoding="utf-8")) == ["a", "b"]
    saved = json.loads((tmp_path / "review/report.json").read_text(encoding="utf-8"))
    assert saved["fingerprint"] == report["fingerprint"] and saved["new_records"] == ["a", "b"]


def test_report_only_marks_a_batch_that_changes_records_and_still_writes_nothing(tmp_path):
    db = FakeDb(ReadOnlyConnection([existing("a", "Old fictional body.")]))
    batch = ImportBatch(records=[record("a"), record("b")])
    code, report = reviewed_import(db, batch, review_dir=tmp_path / "review", review_only=True)
    assert code == 0 and db.imports == [] and report["needs_approval"] is True
    assert report["counts"]["change"] == 1 and report["counts"]["new"] == 1
    assert (tmp_path / "review/decisions.template.json").exists()


@pytest.mark.parametrize("extra", [{"approve": "all-latest", "fingerprint": "f" * 64}, {"fingerprint": "f" * 64},
                                   {"approve_retire": True, "fingerprint": "f" * 64}])
def test_report_only_refuses_an_approval_or_fingerprint(tmp_path, extra):
    db = FakeDb(ReadOnlyConnection([]))
    with pytest.raises(ValueError, match="--review-only"):
        reviewed_import(db, ImportBatch(records=[record("a")]), review_dir=tmp_path / "r", review_only=True, **extra)
    assert db.imports == [] and not (tmp_path / "r").exists()


def test_a_reviewed_fingerprint_imports_a_new_only_batch_while_it_still_matches(tmp_path):
    conn = ReadOnlyConnection([])
    batch = ImportBatch(records=[record("a")])
    _, report = reviewed_import(FakeDb(conn), batch, review_dir=tmp_path / "r", review_only=True)
    db = FakeDb(conn)
    code, result = reviewed_import(db, batch, review_dir=tmp_path / "r2", fingerprint=report["fingerprint"])
    assert code == 0 and db.imports == [["a"]] and result["review"]["approval"] == "automatic"
    assert not (tmp_path / "r2").exists()


def test_a_reviewed_fingerprint_refuses_after_the_database_changed(tmp_path):
    batch = ImportBatch(records=[record("a")])
    _, report = reviewed_import(FakeDb(ReadOnlyConnection([])), batch, review_dir=tmp_path / "r", review_only=True)
    # Meanwhile another import added "a" with other text: the batch would now change it.
    changed = FakeDb(ReadOnlyConnection([existing("a", "Other fictional body.")]))
    with pytest.raises(ImportReviewMismatch):
        reviewed_import(changed, batch, review_dir=tmp_path / "r2", fingerprint=report["fingerprint"])
    assert changed.imports == []


def test_an_automatic_approval_still_stops_when_the_matching_plan_has_changes():
    conn = ReadOnlyConnection([existing("a", "Old fictional body.")])
    batch = ImportBatch(records=[record("a")])
    plan = plan_import(conn, batch)
    with pytest.raises(ImportReviewRequired):
        review_gate(Approval(plan["fingerprint"], "automatic"))(conn, batch)


def test_every_cli_import_command_offers_review_only(monkeypatch, capsys):
    import sys

    from observatory import cli

    for command in ("import-native", "import-social", "import-records"):
        monkeypatch.setattr(sys, "argv", ["observatory", command, "--help"])
        with pytest.raises(SystemExit):
            cli.main()
        assert "--review-only" in capsys.readouterr().out
