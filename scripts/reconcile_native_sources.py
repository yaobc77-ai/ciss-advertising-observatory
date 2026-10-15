"""Read-only reconciliation of native-ad dates and names across raw sources and the database.

Each source value is reported as found; nothing is chosen, repaired or written to
the database. Sources are matched to records by normalized URL:

- baseline: sources/FA25_SP26/final_dataset_cleaned.csv (day/month/year)
- combined: sources/Native Advertising Data/combined_ads_12-4-25.csv
- review: sources/Native Advertising Data/native_ad_dataset.xlsx
- scrape: sources/pdf_archive_20260915/pdfs/*/jsonl/*.jsonl
- url: a date embedded in the article URL

Outputs (new directory): reconciliation.csv (one row per record), summary.json,
and dashboard_native_export.csv (database values plus the date status, for a
dashboard that should not read a raw CSV directly).
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

from observatory.config import Settings
from observatory.date_inference import url_date

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("baseline", "combined", "review", "scrape", "url")
# The online native-ad collection is not expected before 2013 (client, 10-09).
PLAUSIBLE = (date(2013, 1, 1), date(2026, 12, 31))


def normal_url(url) -> str:
    parts = urlsplit(str(url or "").strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}".lower() if host else ""


def normal_name(name) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(name or "").casefold()))


def parse_date(value, *, day_first=False):
    """Return (date, precision) or (None, reason). Never guesses a missing part."""
    if isinstance(value, datetime):
        return value.date(), "day"
    if isinstance(value, date):
        return value, "day"
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return None, "missing"
    try:
        if day_first and (m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)):
            return date(int(m[3]), int(m[2]), int(m[1])), "day"
        if m := re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text):
            return date(int(m[1]), int(m[2]), int(m[3])), "day"
        if m := re.fullmatch(r"(\d{4})-(\d{2})", text):
            return date(int(m[1]), int(m[2]), 1), "month"
        if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", text):
            return date(int(m[1]), int(m[2]), int(m[3])), "day"
    except ValueError:
        return None, "invalid"
    return None, "unparsed"


def agree(left, right) -> str:
    """Compare two (date, precision) values at the coarser precision."""
    (a, pa), (b, pb) = left, right
    if "month" in (pa, pb):
        return "same" if (a.year, a.month) == (b.year, b.month) else "different"
    if a == b:
        return "same"
    # Timestamps were cut to their UTC date; a one-day gap is a time-zone
    # difference, not a different publication.
    return "one_day" if abs(a - b) <= timedelta(days=1) else "different"


def date_status(values: dict) -> dict:
    """Classify the dated sources of one record without choosing a value."""
    found = {name: value for name, value in values.items() if value[0] is not None}
    implausible = sorted(name for name, (day, _) in found.items()
                         if not PLAUSIBLE[0] <= day <= PLAUSIBLE[1])
    plausible = {name: value for name, value in found.items() if name not in implausible}
    names = sorted(plausible)
    pairs = [agree(plausible[a], plausible[b]) for i, a in enumerate(names) for b in names[i + 1:]]
    if not plausible:
        status = "none"
    elif len(plausible) == 1:
        status = "single_source"
    elif "different" in pairs:
        status = "conflict"
    elif "one_day" in pairs:
        status = "agree_within_one_day"
    else:
        status = "agree"
    return {"status": status, "dated_sources": names, "implausible_sources": implausible}


def db_agreement(db_value, values: dict) -> str:
    if db_value is None:
        return "db_unknown"
    db = (db_value, "day")
    others = [value for value in values.values()
              if value[0] is not None and PLAUSIBLE[0] <= value[0] <= PLAUSIBLE[1]]
    if not others:
        return "db_only"
    results = {agree(db, value) for value in others}
    if results <= {"same"}:
        return "matches_all"
    if "different" not in results:
        return "matches_within_one_day"
    return "matches_some" if results & {"same", "one_day"} else "matches_none"


def _raw_sources(root: Path):
    found = {name: {} for name in SOURCES if name != "url"}
    with (root / "sources/FA25_SP26/final_dataset_cleaned.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            found["baseline"].setdefault(normal_url(row.get("url")), row)
    with (root / "sources/Native Advertising Data/combined_ads_12-4-25.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            found["combined"].setdefault(normal_url(row.get("url")), row)
    import openpyxl

    sheet = openpyxl.load_workbook(root / "sources/Native Advertising Data/native_ad_dataset.xlsx",
                                   read_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell or "").strip().lower() for cell in next(rows)]
    for values in rows:
        row = dict(zip(header, values))
        if row.get("url"):
            found["review"].setdefault(normal_url(row["url"]), row)
    for path in sorted(glob.glob(str(root / "sources/pdf_archive_20260915/pdfs/*/jsonl/*.jsonl"))):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            found["scrape"].setdefault(normal_url(row.get("url")), row)
    return found


def reconcile(records, raw) -> list[dict]:
    rows = []
    for record in records:
        payload = record["payload"]
        key = normal_url(payload.get("url"))
        matched = {name: raw[name].get(key) for name in raw}
        values = {
            name: parse_date((row or {}).get("date"), day_first=name == "baseline") if row else (None, "no_row")
            for name, row in matched.items()
        }
        found_url = url_date(payload.get("url"))
        values["url"] = (found_url, "day") if found_url else (None, "missing")
        published = payload.get("published_at")
        db_date = date.fromisoformat(published[:10]) if published else None
        status = date_status(values)
        names = {"publisher": {}, "sponsor": {}}
        for name, row in matched.items():
            for field in names:
                if row and row.get(field):
                    names[field][name] = str(row[field]).strip()
        rows.append({
            "record_id": record["record_id"], "title": payload.get("title"), "url": payload.get("url"),
            "countable": payload.get("countable"),
            "db_published_at": db_date.isoformat() if db_date else "",
            "db_date_basis": (payload.get("raw") or {}).get("date_source") or "",
            "db_date_precision": (payload.get("raw") or {}).get("date_precision") or "",
            **{f"{name}_date": (value[0].isoformat() if value[0] else value[1]) for name, value in values.items()},
            "date_status": status["status"], "implausible_sources": " ".join(status["implausible_sources"]),
            "db_vs_sources": db_agreement(db_date, values),
            "db_publisher": payload.get("publisher"), "db_sponsor": payload.get("sponsor"),
            **{f"{field}_variants": json.dumps(found, ensure_ascii=False, sort_keys=True)
               for field, found in names.items()},
            **{f"{field}_differs": len({normal_name(v) for v in [payload.get(field), *found.values()] if v}) > 1
               for field, found in names.items()},
        })
    return rows


def summarize(rows) -> dict:
    countable = [row for row in rows if row["countable"]]
    return {
        "records": len(rows), "countable_records": len(countable),
        "date_status": dict(Counter(row["date_status"] for row in countable)),
        "db_vs_sources": dict(Counter(row["db_vs_sources"] for row in countable)),
        "records_with_implausible_source_date": sum(bool(row["implausible_sources"]) for row in countable),
        "implausible_source_dates": dict(Counter(source for row in countable
                                                 for source in row["implausible_sources"].split())),
        "db_dates_outside_plausible_range": sum(
            bool(row["db_published_at"]) and not PLAUSIBLE[0].isoformat() <= row["db_published_at"] <= PLAUSIBLE[1].isoformat()
            for row in countable),
        "publisher_name_variants": sum(row["publisher_differs"] for row in countable),
        "sponsor_name_variants": sum(row["sponsor_differs"] for row in countable),
        "plausible_range": [d.isoformat() for d in PLAUSIBLE],
        "writes_to_database": 0,
    }


def collect(dsn, root=ROOT):
    with psycopg.connect(dsn, row_factory=dict_row,
                         options="-c default_transaction_read_only=on -c statement_timeout=60000") as conn:
        records = conn.execute("""SELECT r.record_id::text AS record_id,v.payload FROM records r
            JOIN record_versions v ON v.version_id=r.current_version
            WHERE r.active AND r.dataset='native' ORDER BY r.record_id""").fetchall()
    return reconcile(records, _raw_sources(root))


def write(rows, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    with (out / "reconciliation.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    export = ["record_id", "title", "url", "db_publisher", "db_sponsor", "db_published_at", "date_status", "db_vs_sources"]
    with (out / "dashboard_native_export.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=export)
        writer.writeheader()
        writer.writerows({key: row[key] for key in export} for row in rows if row["countable"])
    summary = summarize(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(write(collect(Settings.from_env().database_url), args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
