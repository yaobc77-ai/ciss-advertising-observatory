"""Compare an import batch with the database and require a person's approval before it changes records.

An import may replace the current version of records that already exist (a new export of the same
posts), re-activate retired records, or, in snapshot mode, retire every record missing from the
batch. None of that happens without an approval bound to the exact reviewed plan:

- ``all-latest``: every changed record takes the batch's version;
- ``per-item``: a decisions file says "latest" or "keep" for each changed record ("keep" leaves the
  current version, and its active state, as it is, and keeps the record out of a snapshot's
  retirements).

"Latest" means the version in this batch, not a judgement that the incoming data is newer or more
complete; the report lists what each change would lose. Retiring records in snapshot mode needs its
own explicit approval of the same plan, and a batch prepared from one shard of a split export is
refused in snapshot mode, because it would retire the posts in the other shards.

The plan's fingerprint covers the database, dataset, mode, batch hashes, every record's current and
new version and the exact retirement set; ``Database.import_batch`` re-plans on its own transaction,
under the import lock, and writes nothing when the fingerprint no longer matches.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .db import digest, record_payload_version
from .import_records import _unique_object

ACTIONS = ("new", "unchanged", "reactivate", "change")
NEEDS_APPROVAL = ("reactivate", "change")
FIELDS = ("body", "title", "sponsor", "account", "platform", "url", "archive_url", "published_at",
          "countable", "retrievable")
DECISIONS = ("latest", "keep")
SHARD = re.compile(r"\.shard-\d+-of-\d+\.")


class ImportReviewRequired(ValueError):
    """The batch changes, re-activates or retires records and no approval was given."""


class ImportReviewMismatch(ValueError):
    """The database or batch differs from the plan that was approved; nothing was written."""


@dataclass(frozen=True)
class Approval:
    fingerprint: str
    kind: str  # "automatic" (nothing to approve), "all-latest", "per-item" or "retire-only"
    decisions: dict = field(default_factory=dict)
    reviewer: str = ""
    decided_at: str = ""
    retire_approved: bool = False


def _labels(payload):
    """Label values per annotation version; provenance keys (source file, row, hashes) are left out."""
    return sorted(
        json.dumps({"version": item.get("version"), "values": item.get("values"),
                    "labels": item.get("labels")}, sort_keys=True, ensure_ascii=False)
        for item in payload.get("annotations") or [] if isinstance(item, dict)
    )


def _variants(payload):
    variants = (payload.get("raw") or {}).get("source_variants")
    return len(variants) if isinstance(variants, list) else None


def compare_payloads(old, new):
    """Field-level differences between the current and the incoming payload, plus what would be lost."""
    fields = {name: {"old": old.get(name), "new": new.get(name)}
              for name in FIELDS if old.get(name) != new.get(name)}
    if _labels(old) != _labels(new):
        fields["annotation_labels"] = {"old": _labels(old), "new": _labels(new)}
    elif old.get("annotations") != new.get("annotations"):
        fields["annotation_provenance"] = {"old": len(old.get("annotations") or []),
                                           "new": len(new.get("annotations") or [])}
    if _variants(old) != _variants(new):
        fields["source_variants"] = {"old": _variants(old), "new": _variants(new)}
    losses = []
    if old.get("archive_url") and not new.get("archive_url"):
        losses.append("archive_url")
    for flag in ("retrievable", "countable"):
        if old.get(flag) and not new.get(flag):
            losses.append(flag)
    if (old.get("body") or "").strip() and not (new.get("body") or "").strip():
        losses.append("body")
    if (_variants(old) or 0) > (_variants(new) or 0):
        losses.append("source_variants")
    return fields, losses


def _database_identity(conn):
    """The cluster's system identifier, the database's name and oid, and the tables the unqualified
    names resolve to: another cluster, a recreated database or another schema (search_path) cannot
    reuse an approval."""
    try:
        with conn.transaction():
            row = conn.execute(
                "SELECT (SELECT system_identifier::text FROM pg_control_system()) AS cluster, "
                "current_database() AS name, "
                "(SELECT oid::text FROM pg_database WHERE datname=current_database()) AS oid, "
                "'records'::regclass::oid::text AS records_table, "
                "'record_versions'::regclass::oid::text AS versions_table").fetchone()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Cannot identify the target database; an import review cannot be bound to it") from exc
    if not all(row.values()):
        raise ValueError("Cannot identify the target database; an import review cannot be bound to it")
    return dict(row)


def _shard_sources(batch):
    names = set(batch.source_hashes)
    for record in batch.records:
        for item in record.provenance:
            if isinstance(item, dict):
                names.update(str(item.get(key) or "") for key in ("source", "source_member"))
    return sorted(name for name in names if SHARD.search(name))


def plan_import(conn, batch, snapshot_dataset=None):
    """Read-only: what importing ``batch`` would do on this connection, and its fingerprint."""
    ids = [record.record_id for record in batch.records]
    if snapshot_dataset is not None and _shard_sources(batch):
        raise ValueError("A batch prepared from one shard of a split export cannot run as a snapshot: it would "
                         f"retire the other shards' records ({_shard_sources(batch)[:2]}). Use --mode upsert.")
    current = {
        row["record_id"]: row for row in conn.execute(
            "SELECT r.record_id,r.dataset,r.current_version,r.active,v.payload FROM records r "
            "LEFT JOIN record_versions v ON v.version_id=r.current_version WHERE r.record_id=ANY(%s)",
            (ids,),
        ).fetchall()
    }
    table, changes = [], []
    for record in batch.records:
        payload, version = record_payload_version(record)
        row = current.get(record.record_id)
        if row is None:
            action = "new"
        elif row["dataset"] != record.dataset:
            raise ValueError(f"A record ID cannot change datasets: {record.record_id}")
        elif row["current_version"] == version:
            action = "unchanged" if row["active"] else "reactivate"
        else:
            action = "change"
        table.append([record.record_id, row and row["current_version"], row and row["active"],
                      version, action])
        if action in NEEDS_APPROVAL:
            fields, losses = compare_payloads(row["payload"] or {}, payload)
            changes.append({"record_id": record.record_id, "action": action,
                            "active": row["active"], "current_version": row["current_version"],
                            "new_version": version, "fields": fields, "losses": losses})
    retire = []
    if snapshot_dataset is not None:
        retire = [[row["record_id"], row["current_version"]] for row in conn.execute(
            "SELECT record_id,current_version FROM records WHERE dataset=%s AND active "
            "AND NOT (record_id=ANY(%s)) ORDER BY record_id", (snapshot_dataset, ids),
        ).fetchall()]
    basis = {
        "database": _database_identity(conn), "mode": "snapshot" if snapshot_dataset else "upsert",
        "snapshot_dataset": snapshot_dataset, "datasets": sorted({r.dataset for r in batch.records}),
        "source_hashes": batch.source_hashes, "records": sorted(table), "retire": retire,
    }
    fingerprint = digest(json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                    default=str))
    counts = {action: sum(row[4] == action for row in table) for action in ACTIONS}
    field_counts, loss_counts = {}, {}
    for change in changes:
        for name in change["fields"]:
            field_counts[name] = field_counts.get(name, 0) + 1
        for loss in change["losses"]:
            loss_counts[loss] = loss_counts.get(loss, 0) + 1
    return {
        "fingerprint": fingerprint, "mode": basis["mode"], "snapshot_dataset": snapshot_dataset,
        "database": basis["database"], "source_hashes": batch.source_hashes,
        "counts": counts | {"retire": len(retire)}, "changed_fields": field_counts,
        "losses": loss_counts, "changes": changes, "retire": retire,
    }


def needs_approval(plan):
    return [change["record_id"] for change in plan["changes"]], plan["retire"]


def alert(plan, review_dir=None):
    """The plain-language warning printed when an import needs a person's decision."""
    pending, retire = needs_approval(plan)
    lines = ["IMPORT STOPPED: nothing was written. A person must decide before this import runs."]
    counts = plan["counts"]
    lines.append(f"  new {counts['new']}, unchanged {counts['unchanged']}, changed {counts['change']}, "
                 f"re-activated {counts['reactivate']}, retired by snapshot {counts['retire']}")
    if pending:
        lines.append("  Changed fields: " + ", ".join(f"{k} {v}" for k, v in sorted(plan["changed_fields"].items())))
    if plan["losses"]:
        lines.append("  Would lose: " + ", ".join(f"{k} {v}" for k, v in sorted(plan["losses"].items())))
    if retire:
        lines.append(f"  Snapshot mode would retire {len(retire)} active records missing from this batch; that "
                     "needs --approve-retire as well. When a dataset is split into shards, import every "
                     "shard with --mode upsert.")
    if review_dir:
        lines.append(f"  Review: {Path(review_dir) / 'report.json'}; decide per record in "
                     f"{Path(review_dir) / 'decisions.template.json'} (save as a new file).")
    lines.append(f"  Then rerun with --approve all-latest --fingerprint {plan['fingerprint']} "
                 "(the batch's version for every changed record), or with --decisions <file>.")
    return "\n".join(lines)


def write_review(review_dir, plan):
    """Write the full report and a per-item decisions template into a new directory."""
    review_dir = Path(review_dir)
    review_dir.mkdir(parents=True, exist_ok=False)
    (review_dir / "report.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    template = {
        "fingerprint": plan["fingerprint"], "mode": "per-item", "reviewer": "", "decided_at": "",
        "allowed": list(DECISIONS), "approve_retirements": False, "retirements": len(plan["retire"]),
        "decisions": {change["record_id"]: "undecided" for change in plan["changes"]},
    }
    (review_dir / "decisions.template.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return review_dir


def load_decisions(path):
    """A per-item decisions file; every value must already be "latest" or "keep"."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    if (not isinstance(data, dict) or data.get("mode") != "per-item"
            or not isinstance(data.get("fingerprint"), str) or not isinstance(data.get("decisions"), dict)):
        raise ValueError("A decisions file needs mode 'per-item', the reviewed fingerprint and decisions")
    if not str(data.get("reviewer") or "").strip() or not str(data.get("decided_at") or "").strip():
        raise ValueError("A decisions file must name its reviewer and decision time")
    undecided = sorted(k for k, v in data["decisions"].items() if v not in DECISIONS)
    if undecided:
        raise ValueError(f"{len(undecided)} records are not decided as 'latest' or 'keep', e.g. {undecided[:3]}")
    if not isinstance(data.get("approve_retirements", False), bool):
        raise ValueError("approve_retirements must be true or false")
    return Approval(data["fingerprint"], "per-item", dict(data["decisions"]),
                    str(data["reviewer"]), str(data["decided_at"]), data.get("approve_retirements", False))


def review_gate(approval, snapshot_dataset=None):
    """The ``review`` callback for ``Database.import_batch``: re-plan inside the import transaction."""
    def check(conn, batch):
        plan = plan_import(conn, batch, snapshot_dataset)
        if plan["fingerprint"] != approval.fingerprint:
            raise ImportReviewMismatch(
                "The database or batch changed since the reviewed plan; nothing was written. Review again.")
        pending, retire = needs_approval(plan)
        if approval.kind in ("automatic", "retire-only") and pending:
            raise ImportReviewRequired(alert(plan))
        if retire and not approval.retire_approved:
            raise ImportReviewRequired(alert(plan))
        if approval.kind == "per-item":
            if any(value not in DECISIONS for value in approval.decisions.values()):
                raise ImportReviewMismatch("Every decision must be 'latest' or 'keep'; nothing was written.")
            decided = set(approval.decisions)
            if decided != set(pending):
                missing, extra = sorted(set(pending) - decided), sorted(decided - set(pending))
                raise ImportReviewMismatch(
                    f"Decisions must cover exactly the {len(pending)} changed records "
                    f"(missing {len(missing)}, not in the plan {len(extra)}); nothing was written.")
        elif approval.kind not in ("automatic", "all-latest", "retire-only"):
            raise ValueError(f"Unknown approval kind: {approval.kind}")
        elif approval.decisions:
            raise ImportReviewMismatch(f"A {approval.kind} approval carries no per-item decisions; nothing was written.")
        keep = {key for key, value in approval.decisions.items() if value == "keep"}
        records = [record for record in batch.records if record.record_id not in keep]
        receipt = {
            "fingerprint": plan["fingerprint"], "approval": approval.kind,
            "reviewer": approval.reviewer, "decided_at": approval.decided_at,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "counts": plan["counts"], "losses": plan["losses"],
            "kept_at_current_version": sorted(keep),
            "took_latest": sorted(set(pending) - keep),
            "retired": len(retire),
        }
        return records, receipt
    return check


def reviewed_import(db, batch, snapshot_dataset=None, *, review_dir, approve=None, fingerprint=None,
                    decisions=None, approve_retire=False):
    """The CLI path: plan and stop for a decision, or import under an approval.

    Returns (exit code, report). Code 3 means a decision is needed and nothing was written.
    """
    if decisions is not None and approve is not None:
        raise ValueError("Use either --approve all-latest or --decisions, not both")
    if approve is not None and approve != "all-latest":
        raise ValueError(f"Unknown approval: {approve}")
    if decisions is not None:
        approval = load_decisions(decisions)
        if approve_retire and not approval.retire_approved:
            raise ValueError("Approve retirements in the decisions file itself (approve_retirements: true)")
    elif approve == "all-latest" or approve_retire:
        if not fingerprint:
            raise ValueError("An approval needs the reviewed --fingerprint")
        approval = Approval(fingerprint, approve or "retire-only", retire_approved=approve_retire)
    else:
        with db.connect() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            plan = plan_import(conn, batch, snapshot_dataset)
        write_review(review_dir, plan)
        pending, retire = needs_approval(plan)
        if pending or retire:
            return 3, {"status": "approval_required", "fingerprint": plan["fingerprint"],
                       "counts": plan["counts"], "changed_fields": plan["changed_fields"],
                       "losses": plan["losses"], "review_dir": str(review_dir),
                       "alert": alert(plan, review_dir)}
        approval = Approval(plan["fingerprint"], "automatic")
    return 0, db.import_batch(batch, snapshot_dataset, review=review_gate(approval, snapshot_dataset))
