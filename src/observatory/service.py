"""Shared filtered-record service for the UI, export and evidence queries."""

import logging
import re
import time
from collections import Counter
from urllib.parse import urlsplit

from .budget import LimitReached, price
from .db import Database
from .models import Answer, Filters
from .rag import Rag

log = logging.getLogger(__name__)


def safe_url(value):
    try:
        p = urlsplit(value or "")
        return (
            value
            if p.scheme in ("http", "https")
            and p.hostname
            and not p.username
            and not p.password
            else ""
        )
    except ValueError:
        return ""


def summarize(rows):
    total = len(rows)

    def group(field):
        counts = Counter(r.get(field) or "(Unknown)" for r in rows)
        return [
            {"name": k, "count": v, "percent": 100 * v / total if total else 0}
            for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]

    timeline = Counter((r["date"][:7] if r.get("date") else "Unknown") for r in rows)
    relationships = Counter(
        (r.get("sponsor") or "(Unknown)", r.get("publisher") or "(Unknown)")
        for r in rows
    )
    return {
        "total": total,
        "retrievable": sum(r["retrievable"] for r in rows),
        "unknown_dates": sum(not r.get("date") for r in rows),
        **{
            f: group(f[:-1] if f != "keywords" else "keyword")
            for f in ["publishers", "sponsors", "platforms", "keywords"]
        },
        "timeline": [{"month": k, "count": v} for k, v in sorted(timeline.items())],
        "relationships": [
            {"sponsor": s, "publisher": p, "count": n}
            for (s, p), n in sorted(relationships.items(), key=lambda x: (-x[1], x[0]))
        ],
    }


class Service:
    def __init__(self, settings, db=None, rag=None):
        self.settings = settings
        self.db = db or Database(settings.database_url)
        self.rag = rag or Rag(self.db, settings)

    def browse(self, filters):
        rows = self.db.public_rows(filters)
        for row in rows:
            for key in ["url", "archive_url"]:
                row[key] = (
                    safe_url(row.get(key)) if self.settings.show_source_links else ""
                )
        return rows

    def statistics(self, filters):
        return summarize(self.browse(filters))

    def facets(self, dataset):
        rows = self.browse(Filters(dataset=dataset))
        result = {
            name: sorted({r.get(field) or "(Unknown)" for r in rows})
            for name, field in [
                ("publishers", "publisher"),
                ("sponsors", "sponsor"),
                ("platforms", "platform"),
                ("keywords", "keyword"),
            ]
        }
        result["labels"] = sorted({label for row in rows for label in row["labels"]})
        return result

    def health(self):
        try:
            return self.db.health()
        except Exception:
            return {
                "status": "unavailable",
                "record_counts": {},
                "data_version": "unavailable",
            }

    def _public_evidence(self, evidence):
        return [
            e.model_copy(
                update={
                    "url": safe_url(e.url) if self.settings.show_source_links else "",
                    "archive_url": safe_url(e.archive_url)
                    if self.settings.show_source_links
                    else "",
                }
            )
            for e in evidence
        ]

    def search(self, question, filters, limit=5):
        if not 1 <= len(question.strip()) <= 2000:
            return []
        filters = self._title_scope(question, filters)
        return self._public_evidence(
            self.db.search(question, filters, limit=min(limit, 10))
        )

    def search_report(self, question, filters, limit=5):
        """Free search with keyword coverage of the same filtered index snapshot."""
        if not 1 <= len(question.strip()) <= 2000:
            return {
                "evidence": [],
                "diagnostics": {
                    "status": "unavailable", "operator": "OR", "terms": [],
                    "reason": "Enter a question of 1–2,000 characters.",
                },
            }
        filters = self._title_scope(question, filters)
        report = self.db.search_report(question, filters, limit=min(limit, 10))
        report["evidence"] = self._public_evidence(report["evidence"])
        return report

    def _title_scope(self, question, filters):
        """A full explicitly named title narrows retrieval within existing filters."""

        def normal(text):
            return " ".join(re.findall(r"\w+", text.lower()))

        query = normal(question)
        rows = self.db.public_rows(filters)
        matches = [
            r["record_id"]
            for r in rows
            if len(normal(r["title"])) >= 20 and normal(r["title"]) in query
        ]
        return (
            filters.model_copy(update={"record_ids": matches}) if matches else filters
        )

    def answer(self, question, filters, visitor):
        start = time.monotonic()
        evidence = []
        reservation = None
        dispatched = False
        version = "unavailable"
        embedding_cost = []
        if not 1 <= len(question.strip()) <= 2000:
            return Answer(
                status="insufficient_evidence",
                answer="Please enter a question of 1–2,000 characters.",
            )
        normalized = question.strip().lower().rstrip("?.!")
        if normalized in {
            "how many records",
            "how many records are there",
            "how many records match the current filters",
            "count records",
            "当前筛选有多少条记录",
            "当前有多少条记录",
        }:
            counts = {
                d: self.statistics(filters.model_copy(update={"dataset": d}))["total"]
                for d in (
                    ["native", "social"]
                    if filters.dataset == "all"
                    else [filters.dataset]
                )
            }
            return Answer(
                status="answered",
                answer="Current filtered record counts: "
                + "; ".join(f"{d}: {n}" for d, n in counts.items())
                + ". These are dataset records; social posts and native articles are separate units.",
            )
        if re.search(
            r"\b(how many|count|percentage|percent|total number)\b|多少|占比|百分比",
            normalized,
        ):
            return Answer(
                status="insufficient_evidence",
                answer="Use the dashboard filters and counts for quantitative questions. The supported count question is: How many records match the current filters? Retrieved passages cannot establish corpus totals.",
            )
        try:
            version = self.db.health()["data_version"]
            filters = self._title_scope(question, filters)
            # Keyword search always runs first so failures can return usable evidence.
            evidence = self.search(question, filters)
            price(self.settings.generation_model, 1, 1)
            # Admission covers the whole paid question, before query embedding.
            # This exceeds the maximum generation cost under the 100k-byte prompt cap.
            reservation = self.rag.budget.reserve(
                "0.04", visitor, "generation", self.settings.generation_model
            )
            vector = self.rag.embed(
                [question], visitor=visitor, cost_sink=embedding_cost
            )[0]
            evidence = self._public_evidence(
                self.db.search(
                    question,
                    filters,
                    vector=vector,
                    model=self.settings.embedding_model,
                    chunks_per_record=3,
                )
            )
            if self.db.health()["data_version"] != version:
                evidence = []
                version = self.db.health()["data_version"]
                raise ValueError(
                    "Data changed during retrieval; retry on a consistent version"
                )
            dispatched = True
            result = self.rag.generate(
                question, evidence, visitor, reservation=reservation
            )
            final_version = self.db.health()["data_version"]
            if final_version != version:
                # A dispatched call remains charged and audited, but an answer
                # from an index superseded during generation is not published.
                evidence = []
                version = final_version
                raise ValueError(
                    "Data changed during generation; retry on a consistent version"
                )
        except LimitReached as exc:
            result = Answer(status="limited", answer=str(exc), evidence=evidence)
        except Exception as exc:
            log.warning("Answer failed: %s", type(exc).__name__)
            known = {
                "Unverifiable citation": "citation_mismatch",
                "Citation exceeds short-quote limit": "quote_too_long",
                "Missing or excessive claims": "invalid_claim_count",
                "Evidence failed original-version validation": "evidence_version_mismatch",
                "Data changed during generation; retry on a consistent version": "data_changed_during_generation",
            }
            reason = known.get(str(exc), type(exc).__name__)
            result = Answer(
                status="service_unavailable",
                answer="The answer service is unavailable. Browse the evidence below or use keyword search.",
                evidence=evidence,
                failure_reason=reason,
            )
        finally:
            if reservation and not dispatched:
                self.rag.budget.cancel_unsent(reservation)
        result.latency_ms = int((time.monotonic() - start) * 1000)
        if reservation:
            result.cost_usd = self.rag.budget.reservation_cost(reservation) + sum(
                embedding_cost
            )
        try:
            self.db.save_answer(question, filters, result, version)
        except Exception:
            log.warning("Answer audit log unavailable")
        return result
