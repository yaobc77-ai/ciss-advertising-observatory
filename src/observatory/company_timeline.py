"""One company's native ads and social posts on a shared time axis.

The organization registry maps a company name to the exact source spellings in
each collection (native sponsor values, social affiliation values). Counts are
SQL counts of active countable records by source publication date; records
without a source date are counted separately and never placed in a period.
Activity in the same period is a lead for study, not evidence of one campaign
or of causation (client meeting, 2026-10-09).
"""

from __future__ import annotations

from datetime import date

from .entities import registry

GRANULARITIES = {"month": "month", "quarter": "quarter", "year": "year"}
SERIES = {"native": "native ads by sponsor", "social": "social posts by listed company affiliation"}


def _period_label(day: date, granularity: str) -> str:
    if granularity == "year":
        return f"{day.year}"
    if granularity == "quarter":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    return f"{day.year}-{day.month:02d}"


def _periods(first: date, last: date, granularity: str) -> list[str]:
    """Every period from first to last, so a gap shows as zero rather than vanishing."""
    step = {"month": 1, "quarter": 3, "year": 12}[granularity]
    start_month = (first.month - 1) // step * step + 1 if granularity != "year" else 1
    year, month, labels = first.year, start_month, []
    while (year, month) <= (last.year, last.month):
        labels.append(_period_label(date(year, month, 1), granularity))
        month += step
        year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return labels


def company_timeline(db, company: str, *, granularity: str = "month",
                     date_from: date | None = None, date_to: date | None = None) -> dict:
    if granularity not in GRANULARITIES:
        raise ValueError("Use month, quarter or year")
    entity = registry().entity_of(company, "sponsor")
    if entity is None:
        return {"status": "not_found", "company": company,
                "message": "No organization in the registry matches this name; no spelling is guessed."}
    spellings = {dataset: sorted(entity.values_for("sponsor", (dataset,))) for dataset in SERIES}
    counts, unknown = {}, {}
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for dataset, values in spellings.items():
            if not values:
                counts[dataset], unknown[dataset] = {}, 0
                continue
            rows = conn.execute(
                """SELECT date_trunc(%s,(v.payload->>'published_at')::date)::date AS period,count(*) AS n
                FROM records r JOIN record_versions v ON v.version_id=r.current_version AND v.record_id=r.record_id
                WHERE r.active AND r.dataset=%s AND v.payload->'countable'='true'::jsonb
                  AND v.payload->>'sponsor'=ANY(%s) AND v.payload->>'published_at' IS NOT NULL
                  AND (%s::date IS NULL OR (v.payload->>'published_at')::date>=%s::date)
                  AND (%s::date IS NULL OR (v.payload->>'published_at')::date<=%s::date)
                GROUP BY 1 ORDER BY 1""",
                (GRANULARITIES[granularity], dataset, values, date_from, date_from, date_to, date_to),
            ).fetchall()
            counts[dataset] = {_period_label(row["period"], granularity): row["n"] for row in rows}
            unknown[dataset] = conn.execute(
                """SELECT count(*) AS n FROM records r JOIN record_versions v
                ON v.version_id=r.current_version AND v.record_id=r.record_id
                WHERE r.active AND r.dataset=%s AND v.payload->'countable'='true'::jsonb
                  AND v.payload->>'sponsor'=ANY(%s) AND v.payload->>'published_at' IS NULL""",
                (dataset, values),
            ).fetchone()["n"]
    found = [label for series in counts.values() for label in series]
    if found:
        bounds = [date_from, date_to]
        first = bounds[0] or min(_label_start(label) for label in found)
        last = bounds[1] or max(_label_start(label) for label in found)
        axis = _periods(first, last, granularity)
    else:
        axis = []
    return {
        "status": "ok" if found else "no_dated_records",
        "company": entity.name, "organization": entity.id, "review_status": entity.review_status,
        "granularity": granularity, "periods": axis,
        "series": {dataset: {"label": SERIES[dataset], "counts": [counts[dataset].get(label, 0) for label in axis],
                             "source_spellings": spellings[dataset], "undated_records": unknown[dataset]}
                   for dataset in SERIES},
        "axes": {"x": f"publication {granularity} (source date)", "y": "number of records"},
        "date_basis": "Source publication dates only; supplemented or conflicting dates are left out and counted as undated.",
        "interpretation": "Activity in the same period is a lead for study, not evidence of one campaign or of causation.",
    }


def _label_start(label: str) -> date:
    if "-Q" in label:
        year, quarter = label.split("-Q")
        return date(int(year), (int(quarter) - 1) * 3 + 1, 1)
    if "-" in label:
        year, month = label.split("-")
        return date(int(year), int(month), 1)
    return date(int(label), 1, 1)
