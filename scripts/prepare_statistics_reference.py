"""Independently enumerate G01-G03 references from exact source metadata.

No application statistics/filter functions are used. This creates an observed
development reference, not approved customer policy, semantic gold or a score.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def strict_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate_json_key")
            value[key] = item
        return value

    def invalid(_):
        raise ValueError("nonfinite_json_number")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def iso_date(value):
    if value in (None, ""):
        return None
    if type(value) is not str or len(value) != 10:
        raise ValueError("date_must_be_source_ISO_date_or_null")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date_must_be_source_ISO_calendar_date")
    return parsed


def normalize_rows(rows):
    """Accept canonical records or DB-style {record_id,dataset,payload} rows."""
    if not isinstance(rows, list):
        raise ValueError("source_records_must_be_list")
    result, seen = [], set()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("source_record_must_be_object")
        payload = item.get("payload", item)
        if not isinstance(payload, dict):
            raise ValueError("source_payload_must_be_object")
        rid = item.get("record_id", payload.get("record_id"))
        dataset = item.get("dataset", payload.get("dataset"))
        if type(rid) is not str or not rid.strip() or rid in seen:
            raise ValueError("blank_or_duplicate_record_id")
        seen.add(rid)
        if dataset not in {"native", "social"}:
            raise ValueError("unknown_source_dataset")
        for field, outer in (("record_id", rid), ("dataset", dataset)):
            if field in payload and payload[field] != outer:
                raise ValueError("source_envelope_identity_conflict")
        if type(payload.get("countable")) is not bool or type(item.get("active", True)) is not bool:
            raise ValueError("countable_and_active_must_be_explicit_booleans")
        retrievable = payload.get("retrievable")
        if retrievable is not None and type(retrievable) is not bool:
            raise ValueError("retrievable_must_be_boolean_or_unknown")
        keys = {}
        for field in ("sponsor", "publisher"):
            value = payload.get(field)
            if value is not None and type(value) is not str:
                raise ValueError("entity_key_must_be_string_or_null")
            # Preserve case, spacing and source identity; no inferred aliases.
            keys[field] = None if value in (None, "") else value
        when = iso_date(payload.get("published_at"))
        version = item.get("version_id")
        if version is not None and (type(version) is not str or not version.strip()):
            raise ValueError("version_id_must_be_nonblank_string_or_null")
        result.append({"record_id": rid, "dataset": dataset, "version_id": version,
                       "active": item.get("active", True), "countable": payload["countable"],
                       "retrievable": retrievable,
                       "sponsor": keys["sponsor"], "publisher": keys["publisher"],
                       "published_at": when.isoformat() if when else None})
    return sorted(result, key=lambda row: row["record_id"])


def read_source(path):
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    identity = {}
    if path.suffix.lower() == ".jsonl":
        rows = [strict_json(line) for line in text.splitlines() if line.strip()]
    else:
        value = strict_json(text)
        if isinstance(value, list):
            rows = value
        elif isinstance(value, dict) and isinstance(value.get("records"), list):
            rows = value["records"]
            identity = value.get("observed_identity", {})
            if not isinstance(identity, dict):
                raise ValueError("observed_identity_must_be_object")
        else:
            raise ValueError("snapshot_requires_full_records_not_only_hashes")
    return normalize_rows(rows), {"source_kind": "offline_file", "input_sha256": digest(data),
                                  "supplied_identity_unverified": identity}


def acquire_database():
    """Read one repeatable-read source snapshot; never execute writes or analytics."""
    import psycopg
    from psycopg.rows import dict_row

    from observatory.config import Settings

    settings = Settings.from_env()
    if not settings.database_url:
        raise ValueError("database_url_unavailable")
    with psycopg.connect(settings.database_url, connect_timeout=10, row_factory=dict_row,
                         options="-c default_transaction_read_only=on") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        if conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] != "on":
            raise ValueError("read_only_transaction_required")
        version_query = (
            "SELECT md5(COALESCE(string_agg(current_version, ',' ORDER BY record_id), '')) AS version "
            "FROM records WHERE active"
        )
        before = conn.execute(version_query).fetchone()["version"]
        rows = conn.execute(
            "SELECT r.record_id,r.dataset,v.version_id,v.payload "
            "FROM records r JOIN record_versions v ON v.version_id=r.current_version "
            "WHERE r.active ORDER BY r.record_id"
        ).fetchall()
        after = conn.execute(version_query).fetchone()["version"]
        if before != after:
            raise ValueError("source_identity_changed_within_snapshot")
    return normalize_rows(rows), {"source_kind": "database_read_only_repeatable_read",
                                  "observed_source_version_md5": before,
                                  "identity_before": before, "identity_after": after,
                                  "identity_check_scope": "Same repeatable-read transaction; not a claim that future writes cannot occur.",
                                  "contains_active_records_only": True}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("config_must_be_object")
    allowed = {"dataset", "counting_unit", "scope_label", "filters", "periods", "allow_period_overlap"}
    if set(config) - allowed:
        raise ValueError("unsupported_config_field")
    if config.get("dataset") not in {"native", "social"}:
        raise ValueError("one_explicit_dataset_required")
    if config.get("counting_unit") != "source_record_id":
        raise ValueError("only_source_record_id_counting_supported")
    if type(config.get("scope_label")) is not str or not config["scope_label"].strip():
        raise ValueError("explicit_scope_label_required")
    filters = config.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {
        "sponsors", "publishers", "date_from", "date_to", "include_unknown_dates", "date_presence"
    }:
        raise ValueError("unsupported_filter")
    for field in ("sponsors", "publishers"):
        values = filters.get(field, [])
        if not isinstance(values, list) or any(type(value) is not str or not value.strip() for value in values):
            raise ValueError("exact_source_key_list_required")
        if len(values) != len(set(values)):
            raise ValueError("duplicate_filter_key")
    if type(filters.get("include_unknown_dates")) is not bool:
        raise ValueError("explicit_unknown_date_selection_policy_required")
    if filters.get("date_presence", "any") not in {"any", "known", "missing"}:
        raise ValueError("unknown_date_presence_policy")
    lower, upper = iso_date(filters.get("date_from")), iso_date(filters.get("date_to"))
    if lower and upper and lower > upper:
        raise ValueError("reversed_selection_dates")
    periods = config.get("periods")
    if not isinstance(periods, list) or len(periods) != 2:
        raise ValueError("exactly_two_explicit_periods_required")
    ids = set()
    intervals = []
    for period in periods:
        if not isinstance(period, dict) or set(period) != {"id", "date_from", "date_to", "unknown_dates"}:
            raise ValueError("explicit_period_fields_required")
        name = period["id"]
        if type(name) is not str or not name.strip() or name in ids:
            raise ValueError("unique_period_id_required")
        ids.add(name)
        start, end = iso_date(period["date_from"]), iso_date(period["date_to"])
        if start is None or end is None or start > end:
            raise ValueError("valid_period_endpoints_required")
        if period["unknown_dates"] != "unassigned":
            raise ValueError("unknown_dates_cannot_be_assigned_to_a_period")
        intervals.append((start, end))
    allow_overlap = config.get("allow_period_overlap")
    if type(allow_overlap) is not bool:
        raise ValueError("explicit_period_overlap_policy_required")
    if max(start for start, _ in intervals) <= min(end for _, end in intervals) and not allow_overlap:
        raise ValueError("overlapping_periods_not_allowed_by_config")
    return config


def select_rows(rows, config):
    filters = config["filters"]
    start, end = iso_date(filters.get("date_from")), iso_date(filters.get("date_to"))
    selected = []
    for row in rows:
        if row["dataset"] != config["dataset"] or not row["active"] or not row["countable"]:
            continue
        if any(filters.get(key + "s") and row[key] not in filters[key + "s"] for key in ("sponsor", "publisher")):
            continue
        when = iso_date(row["published_at"])
        presence = filters.get("date_presence", "any")
        if when is None:
            if not filters["include_unknown_dates"] or presence == "known":
                continue
        elif presence == "missing" or (start and when < start) or (end and when > end):
            continue
        selected.append(row)
    return selected


def ids(rows):
    return sorted(row["record_id"] for row in rows)


def group_summary(rows, field):
    groups = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    return [{"key": key, "count": len(items), "record_ids": ids(items)}
            for key, items in sorted(groups.items(), key=lambda pair: (pair[0] is None, pair[0] or ""))]


def timeline(rows):
    groups = defaultdict(list)
    unknown = []
    for row in rows:
        if row["published_at"] is None:
            unknown.append(row)
        else:
            groups[int(row["published_at"][:4])].append(row)
    maximum = max((len(items) for items in groups.values()), default=None)
    return {"total": len(rows), "known_date_count": len(rows) - len(unknown),
            "unknown_date_count": len(unknown), "unknown_date_record_ids": ids(unknown),
            "years": [{"year": year, "count": len(items), "record_ids": ids(items)}
                      for year, items in sorted(groups.items())],
            "maximum_known_year_count": maximum,
            "all_maximum_years": sorted(year for year, items in groups.items() if len(items) == maximum)}


def build_reference(rows, config):
    validate_config(config)
    selected = select_rows(rows, config)
    cells = defaultdict(list)
    for row in selected:
        cells[row["sponsor"], row["publisher"]].append(row)
    sponsors = group_summary(selected, "sponsor")
    outlets = group_summary(selected, "publisher")
    matrix = [{"source_sponsor": sponsor["key"], "outlet": outlet["key"],
               "count": len(cells[sponsor["key"], outlet["key"]]),
               "record_ids": ids(cells[sponsor["key"], outlet["key"]])}
              for sponsor, outlet in itertools.product(sponsors, outlets)]
    relationships = [{"dataset": config["dataset"], "predicate": "source_listed_sponsor_at_outlet",
                      "source": {"type": "source_sponsor", "key": cell["source_sponsor"]},
                      "target": {"type": "source_publisher", "key": cell["outlet"]},
                      "record_count": cell["count"], "record_ids": cell["record_ids"]}
                     for cell in matrix if cell["count"] and cell["source_sponsor"] is not None and cell["outlet"] is not None]
    groups = {}
    for field in ("sponsor", "publisher"):
        groups[field] = [{"key": group["key"], **timeline([row for row in selected if row[field] == group["key"]])}
                         for group in group_summary(selected, field)]
    periods = []
    for period in config["periods"]:
        matching = [row for row in selected if row["published_at"] is not None
                    and period["date_from"] <= row["published_at"] <= period["date_to"]]
        periods.append({**period, "count": len(matching), "record_ids": ids(matching),
                        "by_source_sponsor": group_summary(matching, "sponsor"),
                        "by_outlet": group_summary(matching, "publisher")})
    period_entities = {}
    for field in ("sponsor", "publisher"):
        period_entities[field] = []
        for group in group_summary(selected, field):
            members = [row for row in selected if row[field] == group["key"]]
            period_entities[field].append({
                "key": group["key"],
                "periods": [{"period_id": period["id"],
                             "record_ids": sorted(set(ids(members)) & set(period["record_ids"])),
                             "count": len(set(ids(members)) & set(period["record_ids"]))}
                            for period in periods],
                "unassigned_unknown_record_ids": ids([row for row in members if row["published_at"] is None]),
            })
    first, second = (period["count"] for period in periods)
    return {"format_version": 1, "reference_id": "G01-G03", "status": "observed_development_reference",
            "customer_approved": False, "semantic_gold": False, "unseen_evaluation": False,
            "scope": config, "source_record_count": len(rows), "selected_count": len(selected),
            "selected_record_ids": ids(selected),
            "G01_company_outlet": {"cells": matrix, "source_sponsor_totals": sponsors, "outlet_totals": outlets},
            "G02_source_relationships": {"relationships": relationships,
                                         "missing_entity_record_ids": ids([row for row in selected if row["sponsor"] is None or row["publisher"] is None]),
                                         "meaning": "Observed source-listed metadata only; not proof of payment, partnership or a business contract."},
            "G03_dates": {"overall": timeline(selected), "by_entity": groups,
                          "period_comparison": {"periods": periods, "second_minus_first": second - first,
                                                "by_entity": period_entities,
                                                "change_percentage": 100 * (second - first) / first if first else None,
                                                "overlap_record_ids": sorted(set(periods[0]["record_ids"]) & set(periods[1]["record_ids"])),
                                                "unassigned_unknown_record_ids": ids([row for row in selected if row["published_at"] is None])}},
            "limits": ["Counts exact source record IDs under the stated observed admission and source-key rules, not market-wide ads.",
                       "No entity aliases, inferred dates, duplicate-post mergers, paid-ad status or customer approval are invented.",
                       "Periods intersect the base selection; inclusive endpoints and unassigned unknown dates are explicit.",
                       "Metadata membership is independent of application analytics; this does not score any live answer or establish semantic accuracy."]}


def prepare(source, config_path, output, *, database=False):
    if output.exists():
        raise ValueError("output_directory_already_exists")
    config_bytes = config_path.read_bytes()
    config = validate_config(strict_json(config_bytes.decode("utf-8-sig")))
    rows, identity = acquire_database() if database else read_source(source)
    result = build_reference(rows, config)
    result["built_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["source_identity"] = identity
    snapshot = {"records": rows, "observed_identity": identity}
    snapshot_bytes = encoded(snapshot)
    result["source_metadata_sha256"] = digest(snapshot_bytes)
    files = {"source_metadata.json": snapshot_bytes, "reference.json": encoded(result), "config.json": config_bytes}
    manifest = {"format_version": 1, "status": result["status"], "customer_approved": False,
                "script_sha256": digest(Path(__file__).read_bytes()),
                "input_sha256": {name: digest(data) for name, data in files.items()},
                "source_identity": identity, "selected_count": result["selected_count"],
                "limits": "A version-bound development reference; no approvals, semantic verdicts or evaluation scores."}
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "manifest.json").write_bytes(encoded(manifest))
    return {"status": result["status"], "source_record_count": len(rows),
            "selected_count": result["selected_count"], "unknown_dates": result["G03_dates"]["overall"]["unknown_date_count"],
            "matrix_cells": len(result["G01_company_outlet"]["cells"]),
            "relationships": len(result["G02_source_relationships"]["relationships"]),
            "output": str(output), "source_metadata_sha256": result["source_metadata_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--input", type=Path, help="Canonical JSONL or full metadata JSON snapshot")
    sources.add_argument("--database", action="store_true", help="Acquire active source records in a read-only transaction")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private directory; existing directories are rejected")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.input, args.config, args.output, database=args.database)
    except Exception as exc:
        # Database exception text may contain credentials or private endpoint names.
        reason = str(exc) if isinstance(exc, ValueError) and not args.database else "source_or_output_operation_failed"
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "reason": reason}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
