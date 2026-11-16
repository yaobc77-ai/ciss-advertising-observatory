"""Offline checks of the import review: field comparison, losses and decisions files (no database)."""

import json

import pytest

from observatory.import_review import (
    ImportReviewMismatch,
    compare_payloads,
    load_decisions,
    review_gate,
)
from observatory.models import ImportBatch, RecordInput


def payload(**changes):
    base = {
        "record_id": "social-post:kite", "dataset": "social", "body": "Fictional kite festival post.",
        "sponsor": "Example Kites", "account": "kites", "platform": "Twitter",
        "url": "https://twitter.com/kites/status/1", "archive_url": "https://archive.example/1",
        "countable": True, "retrievable": True,
        "annotations": [{"version": "v1", "values": {"green": True}, "labels": ["green"],
                         "source_sha256": "a" * 64, "source_row": 4}],
        "raw": {"source_variants": [{"id": 1}, {"id": 2}]},
    }
    return base | changes


def test_identical_payloads_have_no_differences():
    assert compare_payloads(payload(), payload()) == ({}, [])


def test_new_export_without_archive_link_and_fewer_variants_is_reported_as_loss():
    new = payload(archive_url="", raw={"source_variants": [{"id": 1}]})
    fields, losses = compare_payloads(payload(), new)
    assert fields["archive_url"] == {"old": "https://archive.example/1", "new": ""}
    assert fields["source_variants"] == {"old": 2, "new": 1}
    assert losses == ["archive_url", "source_variants"]


def test_annotation_provenance_change_is_separate_from_a_label_change():
    moved = payload(annotations=[{**payload()["annotations"][0], "source_sha256": "b" * 64, "source_row": 9}])
    fields, losses = compare_payloads(payload(), moved)
    assert "annotation_provenance" in fields and "annotation_labels" not in fields and losses == []
    relabelled = payload(annotations=[{**payload()["annotations"][0], "values": {"green": False}, "labels": []}])
    fields, _ = compare_payloads(payload(), relabelled)
    assert "annotation_labels" in fields and "annotation_provenance" not in fields


def test_body_sponsor_and_retrievability_changes_show_old_and_new_values():
    new = payload(body="", sponsor="Other Kites", retrievable=False)
    fields, losses = compare_payloads(payload(), new)
    assert fields["sponsor"] == {"old": "Example Kites", "new": "Other Kites"}
    assert fields["body"]["old"] == "Fictional kite festival post." and fields["body"]["new"] == ""
    assert set(losses) == {"retrievable", "body"}


def decisions_file(tmp_path, **changes):
    data = {"fingerprint": "f" * 64, "mode": "per-item", "reviewer": "Reviewer A",
            "decided_at": "2026-11-05T12:00:00Z", "decisions": {"a": "latest", "b": "keep"}} | changes
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("changes", [
    {"decisions": {"a": "latest", "b": "undecided"}},
    {"decisions": {"a": "newest"}},
    {"mode": "all-latest"},
    {"reviewer": ""},
    {"decided_at": " "},
    {"fingerprint": None},
])
def test_incomplete_or_ambiguous_decisions_files_are_refused(tmp_path, changes):
    with pytest.raises(ValueError):
        load_decisions(decisions_file(tmp_path, **changes))


def test_valid_decisions_file_keeps_each_choice(tmp_path):
    approval = load_decisions(decisions_file(tmp_path))
    assert approval.kind == "per-item" and approval.decisions == {"a": "latest", "b": "keep"}
    assert approval.reviewer == "Reviewer A"


class FakeConnection:
    """Enough of a psycopg connection for plan_import: current records and other active records."""

    def __init__(self, rows, active_others=(), cluster="7000"):
        self.rows, self.active_others, self.cluster = rows, dict(active_others), cluster

    def execute(self, query, params=None):
        class Result:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0]

        if "pg_control_system" in query:
            return Result([{"cluster": self.cluster, "name": "obs_test", "oid": "16385",
                            "records_table": "20001", "versions_table": "20002"}])
        if "FROM records r" in query:
            return Result([row for row in self.rows if row["record_id"] in params[0]])
        if "ORDER BY record_id" in query:
            return Result([{"record_id": rid, "current_version": version}
                           for rid, version in sorted(self.active_others.items()) if rid not in params[1]])
        raise AssertionError(query)

    def transaction(self):
        import contextlib
        return contextlib.nullcontext()


def record(record_id, body="Fictional body."):
    return RecordInput(record_id=record_id, dataset="native", url=f"https://example.org/{record_id}", body=body)


def test_gate_refuses_a_plan_that_no_longer_matches_and_keeps_records_out_on_keep():
    from observatory.db import record_payload_version
    from observatory.import_review import Approval, plan_import

    old = record("a", body="Old fictional body.")
    _, old_version = record_payload_version(old)
    conn = FakeConnection([{"record_id": "a", "dataset": "native", "current_version": old_version,
                            "active": True, "payload": old.model_dump(mode="json")}])
    batch = ImportBatch(records=[record("a"), record("b")])
    plan = plan_import(conn, batch)
    assert plan["counts"] == {"new": 1, "unchanged": 0, "reactivate": 0, "change": 1, "retire": 0}
    keep = Approval(plan["fingerprint"], "per-item", {"a": "keep"}, "R", "now")
    records, receipt = review_gate(keep)(conn, batch)
    assert [r.record_id for r in records] == ["b"] and receipt["kept_at_current_version"] == ["a"]
    with pytest.raises(ImportReviewMismatch):
        review_gate(Approval("0" * 64, "all-latest"))(conn, batch)
    with pytest.raises(ImportReviewMismatch):
        review_gate(Approval(plan["fingerprint"], "per-item", {"a": "keep", "z": "latest"}, "R", "now"))(conn, batch)


def test_snapshot_plan_binds_the_exact_retirement_set_and_versions_not_its_size():
    from observatory.import_review import plan_import

    batch = ImportBatch(records=[record("a")])
    first = plan_import(FakeConnection([], active_others={"c": "v1"}), batch, "native")
    other_record = plan_import(FakeConnection([], active_others={"d": "v1"}), batch, "native")
    updated_meanwhile = plan_import(FakeConnection([], active_others={"c": "v2"}), batch, "native")
    other_cluster = plan_import(FakeConnection([], active_others={"c": "v1"}, cluster="7001"), batch, "native")
    assert first["counts"]["retire"] == other_record["counts"]["retire"] == 1
    assert len({first["fingerprint"], other_record["fingerprint"], updated_meanwhile["fingerprint"],
                other_cluster["fingerprint"]}) == 4


def test_all_latest_alone_does_not_approve_retirements():
    from observatory.import_review import Approval, ImportReviewRequired, plan_import

    conn = FakeConnection([], active_others={"c": "v1"})
    batch = ImportBatch(records=[record("a")])
    plan = plan_import(conn, batch, "native")
    with pytest.raises(ImportReviewRequired, match="--approve-retire"):
        review_gate(Approval(plan["fingerprint"], "all-latest"), "native")(conn, batch)
    records, receipt = review_gate(Approval(plan["fingerprint"], "retire-only", retire_approved=True),
                                   "native")(conn, batch)
    assert [r.record_id for r in records] == ["a"] and receipt["retired"] == 1


def test_a_batch_from_one_shard_of_a_split_export_cannot_run_as_a_snapshot():
    from observatory.import_review import plan_import

    shard = record("a").model_copy(update={"provenance": [{"source": "claims.shard-02-of-08.json", "row": 4}]})
    with pytest.raises(ValueError, match="one shard"):
        plan_import(FakeConnection([]), ImportBatch(records=[shard]), "native")
    assert plan_import(FakeConnection([]), ImportBatch(records=[shard]))["counts"]["new"] == 1


def test_cli_stops_with_exit_code_3_and_prints_the_alert(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    from observatory import cli, import_review

    seen = {}

    def fake(db, batch, snapshot_dataset, **kwargs):
        seen.update(kwargs, snapshot_dataset=snapshot_dataset)
        return 3, {"status": "approval_required", "alert": "IMPORT STOPPED: nothing was written."}

    monkeypatch.setattr(import_review, "reviewed_import", fake)
    args = SimpleNamespace(review_dir=tmp_path / "review", approve=None, fingerprint=None, decisions=None,
                           approve_retire=False, out=str(tmp_path / "out.json"))
    with pytest.raises(SystemExit) as stopped:
        cli.run_import(object(), ImportBatch(), "social", args)
    assert stopped.value.code == 3 and "IMPORT STOPPED" in capsys.readouterr().out
    assert seen["snapshot_dataset"] == "social" and seen["review_dir"] == tmp_path / "review"
    assert (tmp_path / "out.json").exists()


@pytest.mark.parametrize("command", ["import-native", "import-social", "import-records"])
def test_every_cli_import_command_takes_the_review_options(command, monkeypatch, capsys):
    import sys

    from observatory import cli

    monkeypatch.setattr(sys, "argv", ["observatory", command, "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    text = capsys.readouterr().out
    assert all(option in text for option in ("--review-dir", "--approve", "--fingerprint", "--decisions",
                                             "--approve-retire"))


def test_a_decisions_file_with_a_repeated_record_is_refused(tmp_path):
    path = tmp_path / "decisions.json"
    path.write_text('{"fingerprint": "' + "f" * 64 + '", "mode": "per-item", "reviewer": "R", "decided_at": "now", '
                    '"decisions": {"a": "keep", "a": "latest"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_decisions(path)


def test_the_gate_itself_refuses_undecided_or_stray_decisions():
    from observatory.db import record_payload_version
    from observatory.import_review import Approval, plan_import

    old = record("a", body="Old fictional body.")
    _, old_version = record_payload_version(old)
    conn = FakeConnection([{"record_id": "a", "dataset": "native", "current_version": old_version,
                            "active": True, "payload": old.model_dump(mode="json")}])
    batch = ImportBatch(records=[record("a")])
    plan = plan_import(conn, batch)
    with pytest.raises(ImportReviewMismatch):
        review_gate(Approval(plan["fingerprint"], "per-item", {"a": "undecided"}, "R", "now"))(conn, batch)
    with pytest.raises(ImportReviewMismatch):
        review_gate(Approval(plan["fingerprint"], "all-latest", {"a": "keep"}))(conn, batch)


def test_another_schema_with_the_same_rows_gives_another_fingerprint():
    from observatory.import_review import plan_import

    class OtherSchema(FakeConnection):
        def execute(self, query, params=None):
            result = super().execute(query, params)
            if "pg_control_system" in query:
                result.fetchone()["records_table"] = "99999"
            return result

    batch = ImportBatch(records=[record("a")])
    assert plan_import(FakeConnection([]), batch)["fingerprint"] != plan_import(OtherSchema([]), batch)["fingerprint"]
