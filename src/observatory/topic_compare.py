"""C15: how often one company's native ads and social posts mention a topic, over time.

A topic is a reviewed keyword list (topics.v1.json): a record is on the topic
when its saved text contains one of the terms as whole words, ignoring case.
This is a reproducible screen, not a judgment of what the record argues; the
examples link to the matched words in the full text so a reader can check.

Companies come from the organization registry, which maps a name to the exact
source spellings in each collection (native sponsor, social company
affiliation); nothing is matched by guessing. Counts are SQL counts of active
countable records. Records without a source date count toward totals but never
toward a period, and a date range leaves them out. The two collections differ
in kind (paid placements vs. collected company posts), so the view gives plain
counts: how many times the topic's keywords occur, and in how many records. A
count is a lead for study, not evidence of a campaign.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from .company_timeline import GRANULARITIES, _label_start, _period_label, _periods
from .entities import registry

TOPICS_PATH = Path(__file__).with_name("topics.v1.json")
DATASETS = {"native": "Native ads (sponsor)", "social": "Company social posts (listed company affiliation)"}
EXAMPLES = 5
SNIPPET = 220
MAX_TOPICS = 6


@lru_cache(maxsize=1)
def topic_table() -> dict:
    raw = TOPICS_PATH.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    ids = [topic["id"] for topic in data["topics"]]
    if len(set(ids)) != len(ids) or any(not topic.get("terms") or not topic.get("label") for topic in data["topics"]):
        raise ValueError("Topic table needs unique ids, labels and terms")
    data["sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def topics_by_id() -> dict:
    return {topic["id"]: topic for topic in topic_table()["topics"]}


def _term(term: str, word_start: str, word_end: str, letters: str) -> str:
    stem = term[:-1] if term.endswith("*") else term
    escaped = "".join(ch if ch.isalnum() else ("\\s+" if ch == " " else "\\" + ch) for ch in stem)
    return word_start + escaped + (letters + "*" if term.endswith("*") else word_end)


def topic_pattern(terms, flavor: str = "pg") -> str:
    """One case-insensitive whole-word pattern for PostgreSQL (~*) or Python (re.I)."""
    start, end, letters = ("\\m", "\\M", "\\w") if flavor == "pg" else ("(?<!\\w)", "(?!\\w)", "\\w")
    return "(" + "|".join(_term(t, start, end, letters) for t in terms) + ")"


def first_match(text: str, terms) -> tuple[int, int] | None:
    found = re.search(topic_pattern(terms, "py"), text or "", re.I)
    return found.span() if found else None


def _snippet(body: str, span) -> dict:
    start, end = span
    left = max(0, start - SNIPPET // 2)
    right = min(len(body), end + SNIPPET // 2)
    return {"before": ("…" if left else "") + body[left:start], "match": body[start:end],
            "after": body[end:right] + ("…" if right < len(body) else "")}


def company_choices() -> list[dict]:
    """Registry organizations with source spellings in at least one collection."""
    choices = []
    for entity in registry().entities.values():
        if entity.kind != "organization":
            continue
        present = [d for d in DATASETS if entity.values_for("sponsor", (d,))]
        if present:
            choices.append({"label": entity.name, "value": entity.name, "collections": present})
    return sorted(choices, key=lambda c: (len(c["collections"]) != 2, c["label"].casefold()))


def ask_question(company: str, topic_ids) -> str:
    labels = [topics_by_id()[t]["label"].lower() for t in topic_ids if t in topics_by_id()]
    subject = ", ".join(labels[:-1]) + (" and " if len(labels) > 1 else "") + labels[-1] if labels else "this topic"
    return (f"How do {company}'s native ads and its social posts discuss {subject}? "
            "Compare the two channels and quote the records.")


def _base(dataset_filter_from, dataset_filter_to):
    dated = ("(%s::date IS NULL AND %s::date IS NULL) OR ((v.payload->>'published_at') IS NOT NULL"
             " AND (%s::date IS NULL OR (v.payload->>'published_at')::date>=%s::date)"
             " AND (%s::date IS NULL OR (v.payload->>'published_at')::date<=%s::date))")
    params = [dataset_filter_from, dataset_filter_to, dataset_filter_from, dataset_filter_from,
              dataset_filter_to, dataset_filter_to]
    sql = ("FROM records r JOIN record_versions v ON v.version_id=r.current_version AND v.record_id=r.record_id "
           "WHERE r.active AND r.dataset=%s AND v.payload->'countable'='true'::jsonb "
           "AND v.payload->>'sponsor'=ANY(%s) AND (" + dated + ")")
    return sql, params


def compare_topics(db, company: str, topic_ids, *, granularity: str = "year",
                   date_from: date | None = None, date_to: date | None = None, examples: int = EXAMPLES) -> dict:
    if granularity not in GRANULARITIES:
        raise ValueError("Use month, quarter or year")
    known = topics_by_id()
    topic_ids = list(dict.fromkeys(topic_ids or []))
    if not topic_ids or len(topic_ids) > MAX_TOPICS or any(t not in known for t in topic_ids):
        raise ValueError(f"Choose 1–{MAX_TOPICS} topics from the topic table")
    if date_from and date_to and date_from > date_to:
        raise ValueError("The start date is after the end date")
    entity = registry().entity_of(company, "sponsor")
    if entity is None:
        return {"status": "not_found", "company": company,
                "message": "No organization in the registry matches this name; no spelling is guessed."}
    topics = [known[t] for t in topic_ids]
    patterns = [topic_pattern(t["terms"]) for t in topics]
    spellings = {dataset: sorted(entity.values_for("sponsor", (dataset,))) for dataset in DATASETS}
    where, base_params = _base(date_from, date_to)
    period = "date_trunc(%s,(v.payload->>'published_at')::date)::date"
    results, labels = {}, set()
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for dataset, values in spellings.items():
            if not values:
                results[dataset] = {"total": 0, "undated": 0, "by_period": {}, "topics": {}}
                continue
            flags = ",".join(f"count(*) FILTER (WHERE v.body ~* %s) AS t{i},"
                             f"coalesce(sum(regexp_count(v.body,%s,1,'i')),0) AS m{i}" for i in range(len(topics)))
            rows = conn.execute(
                f"SELECT {period} AS period,count(*) AS total,{flags} {where} GROUP BY 1",
                [GRANULARITIES[granularity], *[p for pattern in patterns for p in (pattern, pattern)],
                 dataset, values, *base_params],
            ).fetchall()
            by_period = {}
            entry = {"total": 0, "undated": 0, "by_period": by_period,
                     "topics": {t["id"]: {"matched": 0, "undated": 0, "mentions": 0, "by_period": {},
                                          "mentions_by_period": {}} for t in topics}}
            for row in rows:
                entry["total"] += row["total"]
                label = _period_label(row["period"], granularity) if row["period"] else None
                if label is None:
                    entry["undated"] += row["total"]
                else:
                    labels.add(label)
                    by_period[label] = row["total"]
                for i, topic in enumerate(topics):
                    item = entry["topics"][topic["id"]]
                    item["matched"] += row[f"t{i}"]
                    item["mentions"] += row[f"m{i}"]
                    if label is None:
                        item["undated"] += row[f"t{i}"]
                    else:
                        item["by_period"][label] = row[f"t{i}"]
                        item["mentions_by_period"][label] = row[f"m{i}"]
            for i, topic in enumerate(topics):
                found = conn.execute(
                    f"SELECT r.record_id,v.version_id,v.body,v.payload->>'title' AS title,v.payload->>'url' AS url,"
                    f"v.payload->>'published_at' AS published_at,v.payload->>'account' AS account,"
                    f"v.payload->>'publisher' AS publisher {where} AND v.body ~* %s "
                    f"ORDER BY (v.payload->>'published_at') DESC NULLS LAST,r.record_id LIMIT %s",
                    [dataset, values, *base_params, patterns[i], examples],
                ).fetchall()
                entry["topics"][topic["id"]]["examples"] = [_example(row, topic["terms"]) for row in found]
            results[dataset] = entry
    axis = []
    if labels:
        first = date_from or min(_label_start(label) for label in labels)
        last = date_to or max(_label_start(label) for label in labels)
        axis = _periods(first, last, granularity)
    datasets = {}
    for dataset, entry in results.items():
        totals = [entry["by_period"].get(label, 0) for label in axis]
        datasets[dataset] = {
            "label": DATASETS[dataset], "source_spellings": spellings[dataset],
            "total": entry["total"], "undated": entry["undated"], "period_totals": totals,
            "topics": {tid: {"mentions": item.get("mentions", 0),
                             "mention_counts": [item.get("mentions_by_period", {}).get(label, 0) for label in axis],
                             "matched": item["matched"], "undated": item["undated"],
                             "counts": [item["by_period"].get(label, 0) for label in axis],
                             "examples": item.get("examples", [])}
                       for tid, item in entry["topics"].items()},
        }
    table = topic_table()
    return {
        "status": "ok" if any(d["total"] for d in datasets.values()) else "no_records",
        "company": entity.name, "organization": entity.id, "review_status": entity.review_status,
        "topics": [{k: t[k] for k in ("id", "label", "label_zh", "terms")} for t in topics],
        "topic_table": {"version": table["version"], "status": table["status"], "sha256": table["sha256"][:16]},
        "granularity": granularity, "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None, "periods": axis, "datasets": datasets,
        "ask": ask_question(entity.name, topic_ids),
        "method": table["method"],
        "date_basis": "Source publication dates only; undated records count toward totals, never toward a period, "
                      "and are left out when a date range is set.",
        "measure": "Counts: how many times the topic's keywords occur (mentions) and in how many records (matched).",
        "interpretation": "Native ads are paid placements; social posts are collected company posts whose paid status "
                          "is unknown. A keyword match shows a topic is mentioned, not what the record claims about it.",
    }


def _example(row, terms) -> dict:
    body = row["body"] or ""
    span = first_match(body, terms)
    query = {"v": row["version_id"], **({"hl": f"{span[0]}-{span[1]}"} if span else {})}
    href = f"/records/{quote(row['record_id'], safe='')}?{urlencode(query)}" + ("#quote-1" if span else "")
    return {"record_id": row["record_id"], "title": row["title"] or "", "date": row["published_at"],
            "source": row["publisher"] or row["account"] or "", "url": row["url"] or "",
            "snippet": _snippet(body, span) if span else None, "record_url": href}
