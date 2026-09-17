"""Small PostgreSQL repository. Every public read follows records.current_version."""

import hashlib
import json
import re
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Evidence, Filters, ImportBatch


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Database:
    def __init__(self, url: str):
        self.url = url

    def connect(self, vector=False):
        if not self.url:
            raise RuntimeError("OBS_DATABASE_URL is not configured")
        conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5)
        if vector:
            register_vector(conn)
        return conn

    def initialize(self):
        from .indexing import bootstrap

        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(54901)")
            conn.execute(
                Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
            )
            bootstrap(conn)

    def import_batch(self, batch: ImportBatch, snapshot_dataset=None):
        from .chunking import retrieval_spans
        from .indexing import active_profile, record_preparation, store_record_chunks

        report = {
            "input_records": len(batch.records),
            "new_versions": 0,
            "unchanged": 0,
            "rejected": [r.model_dump() for r in batch.rejected],
            "candidates": batch.candidates,
            "source_hashes": batch.source_hashes,
            "issues": [],
            "deactivated": [],
        }
        if snapshot_dataset is not None:
            if (
                snapshot_dataset not in ("native", "social")
                or not batch.records
                or any(r.dataset != snapshot_dataset for r in batch.records)
            ):
                raise ValueError(
                    "A dataset snapshot must contain nonempty records of one explicit dataset"
                )
        with self.connect() as conn:
            # Imports and reads share one atomic publication boundary.
            conn.execute("SELECT pg_advisory_xact_lock(54901)")
            profile_id = active_profile(conn)
            for record in batch.records:
                # Records are mutable after validation; reject invalid edited ranges
                # even when this particular record is not currently retrievable.
                if record.retrieval_ranges is not None:
                    retrieval_spans(record.body, retrieval_ranges=record.retrieval_ranges)
                payload = record.model_dump(mode="json")
                serialized = json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                version = digest(serialized)
                current = conn.execute(
                    "SELECT current_version FROM records WHERE record_id=%s",
                    (record.record_id,),
                ).fetchone()
                report["issues"].extend(
                    {"record_id": record.record_id, **i.model_dump()}
                    for i in record.issues
                )
                if current and current["current_version"] == version:
                    conn.execute(
                        "UPDATE records SET active=true WHERE record_id=%s",
                        (record.record_id,),
                    )
                    store_record_chunks(conn, profile_id, {
                        "record_id": record.record_id, "version_id": version,
                        "body": record.body, "payload": payload,
                    })
                    report["unchanged"] += 1
                    continue
                conn.execute(
                    "INSERT INTO records(record_id,dataset,current_version) VALUES (%s,%s,%s) ON CONFLICT(record_id) DO UPDATE SET current_version=excluded.current_version,active=true",
                    (record.record_id, record.dataset, version),
                )
                conn.execute(
                    "INSERT INTO record_versions(version_id,record_id,body,body_hash,payload) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        version,
                        record.record_id,
                        record.body,
                        digest(record.body),
                        Jsonb(payload),
                    ),
                )
                for i, ann in enumerate(record.annotations):
                    conn.execute(
                        "INSERT INTO annotations VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (version, i, Jsonb(ann)),
                    )
                store_record_chunks(conn, profile_id, {
                    "record_id": record.record_id, "version_id": version,
                    "body": record.body, "payload": payload,
                })
                report["new_versions"] += 1
            if snapshot_dataset:
                retired = conn.execute(
                    "UPDATE records SET active=false WHERE dataset=%s AND active AND NOT (record_id=ANY(%s)) RETURNING record_id",
                    (snapshot_dataset, [r.record_id for r in batch.records]),
                ).fetchall()
                report["deactivated"] = [r["record_id"] for r in retired]
            record_preparation(conn, profile_id)
            report["index_profile"] = profile_id
            conn.execute("INSERT INTO imports(report) VALUES (%s)", (Jsonb(report),))
        return report

    @staticmethod
    def where(filters: Filters):
        terms = ["r.active", "(v.payload->>'countable')::boolean"]
        params = []
        if filters.dataset != "all":
            terms.append("r.dataset=%s")
            params.append(filters.dataset)
        if filters.record_ids:
            terms.append("r.record_id=ANY(%s)")
            params.append(filters.record_ids)
        for field, values in [
            ("publisher", filters.publishers),
            ("sponsor", filters.sponsors),
            ("platform", filters.platforms),
            ("keyword", filters.keywords),
        ]:
            if values:
                terms.append(
                    f"COALESCE(NULLIF(v.payload->>'{field}',''),'(Unknown)')=ANY(%s)"
                )
                params.append(values)
        dates = []
        if filters.date_from:
            dates.append("(v.payload->>'published_at')::date>=%s")
            params.append(filters.date_from)
        if filters.date_to:
            dates.append("(v.payload->>'published_at')::date<=%s")
            params.append(filters.date_to)
        if dates:
            expression = " AND ".join(dates)
            if filters.include_unknown_dates:
                expression = f"(({expression}) OR v.payload->>'published_at' IS NULL)"
            terms.append(f"({expression})")
        elif not filters.include_unknown_dates:
            terms.append("v.payload->>'published_at' IS NOT NULL")
        if filters.labels:
            terms.append(
                "EXISTS (SELECT 1 FROM annotations a WHERE a.version_id=v.version_id AND a.payload->>'version'='claims-calibrated' AND (a.payload->'labels') ?| %s)"
            )
            params.append(filters.labels)
        return " AND ".join(terms), params

    def public_rows(self, filters: Filters):
        where, params = self.where(filters)
        # Explicit projection prevents raw data, disclosure and local paths escaping.
        sql = f"""SELECT r.record_id,r.dataset,v.version_id,
         v.payload->>'url' AS url,v.payload->>'archive_url' AS archive_url,
         v.payload->>'publisher' AS publisher,v.payload->>'title' AS title,
         v.payload->>'published_at' AS date,v.payload->>'sponsor' AS sponsor,
         v.payload->>'keyword' AS keyword,v.payload->>'platform' AS platform,
         v.payload->>'account' AS account,(v.payload->>'retrievable')::boolean AS retrievable,
         COALESCE((SELECT a.payload->'labels' FROM annotations a WHERE a.version_id=v.version_id AND a.payload->>'version'='claims-calibrated' LIMIT 1),'[]'::jsonb) AS labels
         FROM records r JOIN record_versions v ON v.version_id=r.current_version
         WHERE {where} ORDER BY v.payload->>'published_at' DESC NULLS LAST,r.record_id"""
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def health(self):
        from .indexing import profile_snapshot

        with self.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            rows = conn.execute(
                "SELECT dataset,count(*) AS n FROM records WHERE active GROUP BY dataset"
            ).fetchall()
            snapshot = profile_snapshot(conn)
        return {
            "status": "ok",
            "record_counts": {r["dataset"]: r["n"] for r in rows},
            **snapshot,
        }

    def pending_embeddings(self, model="text-embedding-3-small", profile_id=None):
        """Only current source chunks belonging to the requested or active profile."""
        from .indexing import active_profile

        with self.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            profile_id = profile_id or active_profile(conn)
            if not conn.execute(
                "SELECT 1 FROM retrieval_profiles WHERE profile_id=%s", (profile_id,)
            ).fetchone():
                raise ValueError("Profile has not been prepared")
            return conn.execute(
                "SELECT DISTINCT c.text_hash,c.text FROM chunks c "
                "JOIN chunk_profile_membership m USING(chunk_id) "
                "JOIN records r ON r.current_version=c.version_id AND r.record_id=c.record_id "
                "LEFT JOIN embeddings e ON e.text_hash=c.text_hash AND e.model=%s "
                "WHERE r.active AND m.profile_id=%s AND e.text_hash IS NULL ORDER BY c.text_hash",
                (model, profile_id),
            ).fetchall()

    def search(
        self,
        query: str,
        filters: Filters,
        limit=5,
        vector=None,
        model="text-embedding-3-small",
        chunks_per_record=1,
        _include_diagnostics=False,
    ):
        where, params = self.where(filters)
        select = """SELECT c.chunk_id AS evidence_id,c.record_id,c.version_id,r.dataset,
        v.payload->>'title' AS title,v.payload->>'publisher' AS publisher,v.payload->>'sponsor' AS sponsor,
        v.payload->>'url' AS url,v.payload->>'archive_url' AS archive_url,
        (v.payload->>'published_at')::date AS published_at,c.text,
        c.start_char AS start,c.end_char AS end,c.paragraph_ids"""
        join = (
            " FROM chunks c JOIN records r ON r.current_version=c.version_id "
            "AND r.record_id=c.record_id JOIN record_versions v ON v.version_id=c.version_id "
            "JOIN chunk_profile_membership m ON m.chunk_id=c.chunk_id "
            "JOIN retrieval_state s ON s.singleton AND s.active_profile=m.profile_id "
        )
        # OR query enables question-style lexical retrieval; ranking still rewards overlap.
        tokens = re.findall(r"[\w-]+", query.lower())
        stop = {
            "what",
            "which",
            "how",
            "does",
            "the",
            "a",
            "an",
            "is",
            "are",
            "of",
            "to",
            "in",
            "and",
            "for",
            "do",
            "about",
            "say",
            "these",
            "this",
            "with",
        }
        terms = [t for t in tokens if len(t) > 1 and t not in stop][:40]
        if not terms:
            if _include_diagnostics:
                return {"evidence": [], "diagnostics": self._unavailable_coverage(
                    "No meaningful search terms remain after stop-word filtering.", tokens
                )}
            return []
        lexical_query = " OR ".join('"' + t + '"' for t in terms)
        with self.connect(vector=vector is not None) as conn:
            # Vector adapter registration already starts a transaction; finish its
            # catalog lookup before establishing the retrieval snapshot.
            conn.commit()
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            lexical = conn.execute(
                select
                + ",ts_rank_cd(c.search_vector,websearch_to_tsquery('english',%s)) AS score"
                + join
                + f" WHERE {where} AND c.search_vector @@ websearch_to_tsquery('english',%s) ORDER BY score DESC,c.chunk_id LIMIT 50",
                [lexical_query, *params, lexical_query],
            ).fetchall()
            semantic = []
            if vector is not None:
                import numpy as np

                semantic = conn.execute(
                    select
                    + ", 1-(e.embedding <=> %s) AS score"
                    + join
                    + " JOIN embeddings e ON e.text_hash=c.text_hash AND e.model=%s "
                    + f"WHERE {where} ORDER BY e.embedding <=> %s,c.chunk_id LIMIT 50",
                    [np.array(vector), model, *params, np.array(vector)],
                ).fetchall()
            ranking = {}
            by_id = {}
            channels = {}
            for channel, rows in [("keyword", lexical), ("vector", semantic)]:
                for rank, row in enumerate(rows, 1):
                    eid = row["evidence_id"]
                    ranking[eid] = ranking.get(eid, 0) + 1 / (60 + rank)
                    by_id[eid] = row
                    channels.setdefault(eid, []).append(channel)
            # Rank distinct records first, then retain several ranked passages within
            # those same records. Article hit alone does not guarantee answer coverage.
            selected = {}
            for rank, eid in enumerate(sorted(ranking, key=lambda k: (-ranking[k], k)), 1):
                row = by_id[eid]
                rid = row["record_id"]
                if rid not in selected and len(selected) >= limit:
                    continue
                group = selected.setdefault(rid, [])
                if len(group) >= chunks_per_record:
                    continue
                row["score"] = ranking[eid]
                row["retrieval_rank"] = rank
                row["retrieval_sources"] = channels[eid]
                group.append(Evidence(**row))
            evidence = [
                evidence
                for group in selected.values()
                for evidence in sorted(group, key=lambda e: e.start)
            ]
            if _include_diagnostics:
                diagnostics = self._coverage(conn, terms, join, where, params, evidence)
                return {"evidence": evidence, "diagnostics": diagnostics}
            return evidence

    def search_report(self, query, filters, limit=5):
        """Read results and scoped keyword coverage within one retrieval snapshot."""
        return self.search(query, filters, limit=limit, _include_diagnostics=True)

    @staticmethod
    def _unavailable_coverage(reason, ignored_terms):
        return {
            "status": "unavailable", "operator": "OR", "configuration": "english",
            "terms": [], "returned_matched_terms": [], "missing_from_results": [],
            "missing_from_scope": [], "term_details": [],
            "ignored_terms": list(dict.fromkeys(ignored_terms)), "reason": reason,
            "scope_records": None, "scope_chunks": None,
        }

    @classmethod
    def _coverage(cls, conn, terms, join, where, params, evidence):
        """Use the index's exact English tsquery semantics, including stemming.

        Missing terms concern eligible indexed passages, never an entire article's
        unindexed body or a factual absence. Non-English text is not classified as
        absent by this English-only diagnostic.
        """
        supported = list(dict.fromkeys(
            term for term in terms if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", term)
        ))
        ignored = list(dict.fromkeys(term for term in terms if term not in supported))
        if not supported:
            return cls._unavailable_coverage(
                "Keyword coverage uses an English index and is unavailable for this query. "
                "No absence claim is made; try English keywords or semantic search.", terms
            )
        analyzed = conn.execute(
            "SELECT term,tsvector_to_array(to_tsvector('english',term)) AS lexemes "
            "FROM unnest(%s::text[]) WITH ORDINALITY AS input(term,ordinal) ORDER BY ordinal",
            (supported,),
        ).fetchall()
        meaningful = [row["term"] for row in analyzed if row["lexemes"]]
        ignored.extend(row["term"] for row in analyzed if not row["lexemes"])
        if not meaningful:
            return cls._unavailable_coverage(
                "No meaningful English search terms remain after index stop-word filtering.", ignored
            )
        scope = conn.execute(
            "SELECT count(DISTINCT r.record_id) AS scope_records,count(*) AS scope_chunks"
            + join + f" WHERE {where}", params,
        ).fetchone()
        coverage = conn.execute(
            "WITH scope AS MATERIALIZED (SELECT c.chunk_id,r.record_id,c.search_vector"
            + join + f" WHERE {where}) "
            "SELECT input.term,count(DISTINCT scope.record_id) AS matching_records,"
            "array_agg(DISTINCT scope.chunk_id) FILTER (WHERE scope.chunk_id=ANY(%s::text[])) "
            "AS returned_ids FROM unnest(%s::text[]) WITH ORDINALITY AS input(term,ordinal) "
            "LEFT JOIN scope ON scope.search_vector @@ "
            "websearch_to_tsquery('english', '\"' || input.term || '\"') "
            "GROUP BY input.term,input.ordinal ORDER BY input.ordinal",
            [*params, [row.evidence_id for row in evidence], meaningful],
        ).fetchall()
        lexemes = {row["term"]: row["lexemes"] for row in analyzed}
        for row in evidence:
            row.matched_terms = [
                match["term"] for match in coverage
                if row.evidence_id in (match["returned_ids"] or [])
            ]
            row.literal_matched_terms = [
                term for term in row.matched_terms
                if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", row.text, re.I)
            ]
        return {
            "status": "partial" if ignored else "available", "operator": "OR",
            "configuration": "english", "terms": meaningful, "term_limit": 40,
            "returned_matched_terms": [row["term"] for row in coverage if row["returned_ids"]],
            "missing_from_results": [row["term"] for row in coverage if not row["returned_ids"]],
            "missing_from_scope": [row["term"] for row in coverage if row["matching_records"] == 0],
            "term_details": [{
                "term": row["term"], "lexemes": lexemes[row["term"]],
                "matching_records": row["matching_records"]
            } for row in coverage],
            "ignored_terms": ignored, **scope,
            "reason": "Keywords are combined with OR, so a result need not match every term. "
            "Search considers at most the first 40 terms after basic stop-word filtering. "
            "Coverage uses English stemming in indexed body passages within the current selection; "
            "it is not a check of meaning or factual truth. Ranking scores are not confidence probabilities.",
        }

    def validate_evidence(self, evidence: Evidence):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.*,v.body FROM chunks c JOIN record_versions v USING(version_id) WHERE chunk_id=%s",
                (evidence.evidence_id,),
            ).fetchone()
        return bool(
            row
            and row["record_id"] == evidence.record_id
            and row["version_id"] == evidence.version_id
            and row["start_char"] == evidence.start
            and row["end_char"] == evidence.end
            and row["body"][evidence.start : evidence.end]
            == evidence.text
            == row["text"]
        )

    def save_answer(self, question, filters, result, data_version):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO answer_runs(question,filters,result,data_version) VALUES (%s,%s,%s,%s)",
                (
                    question,
                    Jsonb(filters.model_dump(mode="json")),
                    Jsonb(result.model_dump(mode="json")),
                    data_version,
                ),
            )
