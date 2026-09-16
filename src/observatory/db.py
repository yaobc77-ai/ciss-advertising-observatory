"""Small PostgreSQL repository. Every public read follows records.current_version."""

import hashlib
import json
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
        with self.connect() as conn:
            conn.execute(
                Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
            )

    def import_batch(self, batch: ImportBatch, snapshot_dataset=None):
        from .chunking import chunk_retrieval_body, retrieval_spans

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
                if record.retrievable:
                    for chunk in chunk_retrieval_body(
                        record.body,
                        retrieval_end=record.retrieval_end,
                        retrieval_ranges=record.retrieval_ranges,
                    ):
                        assert (
                            record.body[chunk["start"] : chunk["end"]] == chunk["text"]
                        )
                        cid = digest(f"{version}:{chunk['start']}:{chunk['end']}")
                        conn.execute(
                            "INSERT INTO chunks(chunk_id,record_id,version_id,text,text_hash,start_char,end_char,paragraph_ids,token_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (
                                cid,
                                record.record_id,
                                version,
                                chunk["text"],
                                digest(chunk["text"]),
                                chunk["start"],
                                chunk["end"],
                                Jsonb(chunk["paragraph_ids"]),
                                chunk["token_count"],
                            ),
                        )
                report["new_versions"] += 1
            if snapshot_dataset:
                retired = conn.execute(
                    "UPDATE records SET active=false WHERE dataset=%s AND active AND NOT (record_id=ANY(%s)) RETURNING record_id",
                    (snapshot_dataset, [r.record_id for r in batch.records]),
                ).fetchall()
                report["deactivated"] = [r["record_id"] for r in retired]
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
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT dataset,count(*) AS n FROM records WHERE active GROUP BY dataset"
            ).fetchall()
            version = conn.execute(
                "SELECT md5(COALESCE(string_agg(current_version,',' ORDER BY record_id),'')) AS value FROM records WHERE active"
            ).fetchone()["value"]
            n = conn.execute(
                "SELECT count(*) AS n FROM chunks c JOIN records r ON r.current_version=c.version_id WHERE r.active"
            ).fetchone()["n"]
        return {
            "status": "ok",
            "record_counts": {r["dataset"]: r["n"] for r in rows},
            "data_version": version,
            "chunks": n,
        }

    def search(
        self,
        query: str,
        filters: Filters,
        limit=5,
        vector=None,
        model="text-embedding-3-small",
        chunks_per_record=1,
    ):
        where, params = self.where(filters)
        select = """SELECT c.chunk_id AS evidence_id,c.record_id,c.version_id,r.dataset,
        v.payload->>'title' AS title,v.payload->>'publisher' AS publisher,v.payload->>'sponsor' AS sponsor,
        v.payload->>'url' AS url,v.payload->>'archive_url' AS archive_url,c.text,
        c.start_char AS start,c.end_char AS end,c.paragraph_ids"""
        join = " FROM chunks c JOIN records r ON r.current_version=c.version_id JOIN record_versions v ON v.version_id=c.version_id "
        # OR query enables question-style lexical retrieval; ranking still rewards overlap.
        import re

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
        for rows in [lexical, semantic]:
            for rank, row in enumerate(rows, 1):
                eid = row["evidence_id"]
                ranking[eid] = ranking.get(eid, 0) + 1 / (60 + rank)
                by_id[eid] = row
        # Rank distinct records first, then retain several ranked passages within
        # those same records. Article hit alone does not guarantee answer coverage.
        selected = {}
        for eid in sorted(ranking, key=lambda k: (-ranking[k], k)):
            row = by_id[eid]
            rid = row["record_id"]
            if rid not in selected and len(selected) >= limit:
                continue
            group = selected.setdefault(rid, [])
            if len(group) >= chunks_per_record:
                continue
            row["score"] = ranking[eid]
            group.append(Evidence(**row))
        return [
            evidence
            for group in selected.values()
            for evidence in sorted(group, key=lambda e: e.start)
        ]

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
