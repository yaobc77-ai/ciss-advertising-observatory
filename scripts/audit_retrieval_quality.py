"""Read-only corpus audit. Never classify, repair, deduplicate or call a model.

Run with the configured OBS_DATABASE_URL, or supply Settings to collect(). Each
run uses one Repeatable Read/READ ONLY snapshot and writes a new output directory.
Only bounded review items contain public source titles, short text or metadata;
raw payloads, database credentials and saved questions/answers are never emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from observatory.chunking import retrieval_spans
from observatory.config import Settings
from observatory.quality import PLACEHOLDERS

CURRENT = """WITH current AS (
    SELECT r.record_id,r.dataset,r.current_version,v.version_id,v.record_id AS version_record_id,v.body,v.body_hash,v.payload
    FROM records r LEFT JOIN record_versions v ON v.version_id=r.current_version
    WHERE r.active
), eligible AS (SELECT * FROM current WHERE payload->'countable'='true'::jsonb)
"""
OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=60000 -c lock_timeout=3000"
ACTIONS = {
    "not_retrievable": "Keep metadata counts; review preserved assets before adding text. Do not infer content absence.",
    "partial_capture": "Review saved source and retained scope; preserve the current version. A stored suspicion alone does not prove truncation.",
    "historical_annotations_prior_body": "Keep prior-body labels separate; review the recovered source before publishing new content labels.",
    "metadata_conflict": "Retain source-observation values and unresolved canonical fields; do not select a value automatically.",
    "duplicate_body_candidate": "Compare URL, provenance and repetition context. Do not automatically merge or delete records.",
    "source_coverage_failure": "Review immutable source and chunk bindings before preparing a new index; do not patch source text in place.",
    "excluded_unique_prose": "Compare the excluded interval with the saved page; if it is article text, publish a new reviewed version with corrected ranges. Never edit ranges in place.",
}
# A reviewed exclusion should hold navigation, captions or repeated pull quotes.
# Sentence-length lines that occur nowhere in the retained text are a signal
# that article text was excluded (P64: a 2,742-character Dunkirk passage).
PROSE_LINE_CHARACTERS = 160
PROSE_SIGNAL_CHARACTERS = 300


def _rows(conn, sql, params=()):
    return conn.execute(CURRENT + sql, params).fetchall()


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def coverage(body, chunks, *, ranges=None, retrieval_end=None, observation=False):
    """Check exact Unicode intervals, counting each expected character once.

    Whitespace outside chunks is allowed. Native reviewed ranges define expected
    scope; full saved observation text defines social scope. Neither proves that
    the saved source is complete or that a claim is semantically supported.
    """
    expected = retrieval_spans(body, retrieval_ranges=ranges, retrieval_end=retrieval_end)
    marked = bytearray(len(body))
    invalid = text_mismatch = hash_mismatch = 0
    for chunk in chunks:
        start, end = chunk["start_char"], chunk["end_char"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body):
            invalid += 1
            continue
        text = chunk["text"]
        if text != body[start:end] or _hash(text) != chunk["text_hash"]:
            text_mismatch += 1
            continue
        if observation and chunk["source_body_hash"] != _hash(body):
            hash_mismatch += 1
            continue
        marked[start:end] = b"\1" * (end - start)
    expected_nonspace = uncovered = 0
    for start, end in expected:
        for pos in range(start, end):
            if not body[pos].isspace():
                expected_nonspace += 1
                uncovered += not marked[pos]
    return {"source_characters": len(body), "expected_nonwhitespace_characters": expected_nonspace,
            "uncovered_nonwhitespace_characters": uncovered, "chunks": len(chunks),
            "invalid_offset_chunks": invalid, "text_or_text_hash_mismatch_chunks": text_mismatch,
            "source_body_hash_mismatch_chunks": hash_mismatch}


def excluded_unique_prose(body, ranges, retrieval_end=None):
    """Excluded intervals whose sentence-length lines are absent from retained text.

    A signal for review, not a judgement: a long caption can trigger it and a
    short excluded paragraph cannot.
    """
    retained = retrieval_spans(body, retrieval_ranges=ranges, retrieval_end=retrieval_end)
    kept = " ".join(body[start:end] for start, end in retained)
    gaps, previous = [], 0
    for start, end in [*retained, (len(body), len(body))]:
        if start > previous:
            gaps.append((previous, start))
        previous = max(previous, end)
    result = []
    for start, end in gaps:
        lines = [line.strip() for line in body[start:end].splitlines()]
        prose = [line for line in lines if len(line) >= PROSE_LINE_CHARACTERS
                 and re.search(r"[.!?]", line) and line[:PROSE_LINE_CHARACTERS] not in kept]
        if sum(map(len, prose)) >= PROSE_SIGNAL_CHARACTERS:
            result.append({"excluded_start": start, "excluded_end": end,
                           "unique_prose_characters": sum(map(len, prose)), "first_line": prose[0][:160]})
    return result


def bounded_queue(categories, limit):
    """Round-robin categories so a large category cannot hide other review needs."""
    if type(limit) is not int or not 0 <= limit <= 50:
        raise ValueError("review_limit must be an integer from 0 to 50")
    result, seen = [], set()
    for index in range(max((len(items) for items in categories), default=0)):
        for items in categories:
            if index >= len(items):
                continue
            item = items[index]
            identity = (item["record_id"], item["reason"], item.get("source_observation_id"))
            if identity not in seen and len(result) < limit:
                result.append(item)
                seen.add(identity)
    return result


def _review_items(conn, limit):
    categories = []
    criteria = [
        ("not_retrievable", "payload->'retrievable' IS DISTINCT FROM 'true'::jsonb"),
        ("partial_capture", "EXISTS(SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'issues')='array' THEN payload->'issues' ELSE '[]'::jsonb END) i "
         "WHERE i->>'code' IN ('body_source_partial','body_partial_recovery') "
         "OR (i->>'code'='body_truncated_suspected' AND COALESCE(i->>'detail','') NOT LIKE 'Previous CSV body:%%'))"),
        ("historical_annotations_prior_body", "EXISTS(SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'issues')='array' THEN payload->'issues' ELSE '[]'::jsonb END) i "
         "WHERE i->>'code'='historical_annotations_prior_body')"),
    ]
    for reason, predicate in criteria:
        items = _rows(conn, """SELECT record_id,version_id,dataset,left(payload->>'title',180) AS title,
            char_length(body) AS stored_body_characters,payload->'retrievable' AS retrievable,
            payload->'retrieval_ranges' AS retrieval_ranges,payload->'retrieval_end' AS retrieval_end,
            COALESCE((SELECT jsonb_agg(i->>'code') FROM jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'issues')='array' THEN payload->'issues' ELSE '[]'::jsonb END) i),'[]') AS issue_codes,
            COALESCE((SELECT jsonb_agg(jsonb_build_object('code',i->>'code','severity',i->>'severity',
                'detail',left(i->>'detail',240),'body_scope',CASE WHEN i->>'detail' LIKE 'Previous CSV body:%%'
                    THEN 'historical_previous_body' ELSE 'current_or_unspecified' END))
                FROM jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'issues')='array' THEN payload->'issues' ELSE '[]'::jsonb END) i
                WHERE i->>'code' LIKE 'body_%%' OR i->>'code'='historical_annotations_prior_body'),'[]') AS body_issue_details,
            greatest(char_length(body)-160,0) AS excerpt_start,char_length(body) AS excerpt_end,
            right(body,160) AS source_excerpt,
            EXISTS(SELECT 1 FROM annotations a WHERE a.version_id=eligible.version_id
                AND a.payload->>'version'='claims-calibrated') AS has_current_calibrated_annotation
            FROM eligible WHERE dataset='native' AND """ + predicate + " ORDER BY record_id LIMIT %s", (limit,))
        categories.append([{**item, "reason": reason, "recommended_action": ACTIONS[reason]} for item in items])
    items = _rows(conn, """SELECT record_id,version_id,dataset,left(payload->>'title',180) AS title,
        payload#>'{raw,social_admission,conflicting_fields}' AS conflicting_fields,
        payload->>'account' AS current_account,payload->>'sponsor' AS current_sponsor,
        jsonb_array_length(payload#>'{raw,source_variants}') AS total_source_observations,
        8 AS observation_metadata_display_limit,
        (SELECT jsonb_agg(jsonb_build_object('source_observation_id',o->>'source_record_id',
            'account',left(o#>>'{source_record,account}',160),'sponsor',left(o#>>'{source_record,sponsor}',160)))
            FROM (SELECT value AS o FROM jsonb_array_elements(CASE WHEN jsonb_typeof(payload#>'{raw,source_variants}')='array'
                THEN payload#>'{raw,source_variants}' ELSE '[]'::jsonb END) WITH ORDINALITY
                ORDER BY ordinality LIMIT 8) bounded) AS observation_metadata
        FROM eligible WHERE dataset='social'
        AND CASE WHEN jsonb_typeof(payload#>'{raw,social_admission,conflicting_fields}')='array'
            THEN jsonb_array_length(payload#>'{raw,social_admission,conflicting_fields}')>0 ELSE false END
        ORDER BY record_id LIMIT %s""", (limit,))
    categories.append([{**item, "reason": "metadata_conflict", "recommended_action": ACTIONS["metadata_conflict"]} for item in items])
    items = _rows(conn, """, duplicated AS (
        SELECT dataset,body_hash,count(*) AS group_members FROM eligible WHERE btrim(body)<>''
        GROUP BY dataset,body_hash HAVING count(*)>1)
        SELECT e.record_id,e.version_id,e.dataset,left(e.payload->>'title',180) AS title,d.group_members
        FROM eligible e JOIN duplicated d USING(dataset,body_hash)
        ORDER BY e.dataset,e.record_id LIMIT %s""", (limit,))
    categories.append([{**item, "reason": "duplicate_body_candidate", "recommended_action": ACTIONS["duplicate_body_candidate"]} for item in items])
    items = []
    for row in _rows(conn, """SELECT record_id,version_id,dataset,left(payload->>'title',180) AS title,body,
            payload->'retrieval_ranges' AS retrieval_ranges,payload->'retrieval_end' AS retrieval_end
            FROM eligible WHERE dataset='native' AND jsonb_typeof(payload->'retrieval_ranges')='array'
            ORDER BY record_id"""):
        try:
            gaps = excluded_unique_prose(row["body"], row["retrieval_ranges"], row["retrieval_end"])
        except (ValueError, TypeError):
            continue  # Invalid scopes are reported by the coverage check.
        if gaps and len(items) < limit:
            items.append({**{k: row[k] for k in ("record_id", "version_id", "dataset", "title")},
                          "excluded_intervals": gaps, "reason": "excluded_unique_prose",
                          "recommended_action": ACTIONS["excluded_unique_prose"]})
    categories.append(items)
    return categories


def _source_coverage(conn, profile, limit):
    sources = _rows(conn, """SELECT record_id,version_id,dataset,left(payload->>'title',180) AS title,
        body,payload->'retrieval_ranges' AS retrieval_ranges,payload->'retrieval_end' AS retrieval_end,
        NULL::text AS source_observation_id FROM eligible
        WHERE dataset='native' AND payload->'retrievable'='true'::jsonb
        UNION ALL SELECT e.record_id,e.version_id,e.dataset,left(e.payload->>'title',180),
        o#>>'{source_record,body}',NULL,NULL,o->>'source_record_id'
        FROM eligible e CROSS JOIN LATERAL jsonb_array_elements(CASE
            WHEN jsonb_typeof(e.payload#>'{raw,source_variants}')='array'
            THEN e.payload#>'{raw,source_variants}' ELSE '[]'::jsonb END) o
        WHERE e.dataset='social' AND e.payload->'retrievable'='true'::jsonb""")
    chunks = _rows(conn, """SELECT e.dataset,left(e.payload->>'title',180) AS title,
        c.record_id,c.version_id,c.source_observation_id,c.source_body_hash,
        c.start_char,c.end_char,c.text,c.text_hash
        FROM eligible e JOIN chunks c ON c.record_id=e.record_id AND c.version_id=e.version_id
        JOIN chunk_profile_membership m ON m.chunk_id=c.chunk_id AND m.profile_id=%s""", (profile,))
    index = defaultdict(list)
    for chunk in chunks:
        index[(chunk["record_id"], chunk["version_id"], chunk["source_observation_id"])].append(chunk)
    aggregates, failures, seen = defaultdict(Counter), [], set()
    for source in sources:
        key = (source["record_id"], source["version_id"], source["source_observation_id"])
        bucket = aggregates[source["dataset"]]
        bucket["duplicate_source_identity_rows"] += key in seen
        seen.add(key)
        bucket["source_units"] += 1
        source_chunks = index.get(key, [])
        bucket["source_units_without_active_chunks"] += not source_chunks
        try:
            checked = coverage(source["body"], source_chunks, ranges=source["retrieval_ranges"],
                               retrieval_end=source["retrieval_end"], observation=source["dataset"] == "social")
        except (ValueError, TypeError):
            bucket["invalid_source_scope_units"] += 1
            checked = {"invalid_source_scope": True}
        bucket.update({k: v for k, v in checked.items() if type(v) is int})
        failed = checked.get("invalid_source_scope") or any(checked.get(key, 0) for key in (
            "uncovered_nonwhitespace_characters", "invalid_offset_chunks", "text_or_text_hash_mismatch_chunks",
            "source_body_hash_mismatch_chunks"))
        bucket["source_units_with_coverage_or_binding_failure"] += bool(failed)
        bucket["empty_expected_scope_units"] += checked.get("expected_nonwhitespace_characters") == 0
        if failed and len(failures) < limit:
            failures.append({k: source[k] for k in ("record_id", "version_id", "dataset", "title", "source_observation_id")})
            failures[-1].update(reason="source_coverage_failure", checks=checked,
                                recommended_action=ACTIONS["source_coverage_failure"])
    for key, source_chunks in index.items():
        if key not in seen:
            # Count unexplained current-profile chunks; never resolve them by deletion.
            dataset = source_chunks[0]["dataset"]
            aggregates[dataset]["chunks_without_expected_source_unit"] += len(source_chunks)
            if len(failures) < limit:
                failures.append({"record_id": key[0], "version_id": key[1], "dataset": dataset,
                    "title": source_chunks[0]["title"], "source_observation_id": key[2],
                    "reason": "source_coverage_failure", "checks": {"chunks_without_expected_source_unit": len(source_chunks)},
                    "recommended_action": ACTIONS["source_coverage_failure"]})
    return [{"dataset": dataset, **dict(counts)} for dataset, counts in sorted(aggregates.items())], failures


def collect_snapshot(conn, *, embedding_model, review_limit=12):
    if type(review_limit) is not int or not 0 <= review_limit <= 50:
        raise ValueError("review_limit must be an integer from 0 to 50")
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    if conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] != "on":
        raise RuntimeError("Database audit requires a read-only transaction")
    result = {"purpose": "read_only_current_corpus_quality_audit", "at_utc": datetime.now(timezone.utc).isoformat(),
              "model_calls": 0, "writes_to_database": 0, "question_or_answer_tables_read": False,
              "counting_rules": {"native": "active current-version records with countable=true",
                                 "social": "same admission filter; canonical original-post units, not observation rows",
                                 "source_observations": "each preserved source_variant under a counted social post",
                                 "duplicates": "exact stored nonempty text/URL or normalized-title candidates, never automatic deletions",
                                 "coverage": "saved non-whitespace characters inside authorized source scope; not original-source completeness"}}
    result["snapshot"] = conn.execute("""SELECT transaction_timestamp()::text AS snapshot_at,
        current_setting('transaction_isolation') AS isolation,current_setting('transaction_read_only') AS read_only""").fetchone()
    result["source_fingerprint"] = _rows(conn, "SELECT md5(COALESCE(string_agg(current_version,',' ORDER BY record_id),'')) AS active_current_versions FROM current")[0]
    result["profile"] = conn.execute("SELECT active_profile FROM retrieval_state WHERE singleton").fetchone()
    profile = result["profile"]["active_profile"]
    result["collections"] = _rows(conn, """SELECT dataset,count(*) AS active_records,
        count(*) FILTER(WHERE payload->'countable'='true'::jsonb) AS countable_records,
        count(*) FILTER(WHERE payload->'countable' IS DISTINCT FROM 'true'::jsonb) AS uncountable_or_unknown_records,
        count(*) FILTER(WHERE payload->'countable'='true'::jsonb AND payload->'retrievable'='true'::jsonb) AS retrievable_records
        FROM current GROUP BY dataset ORDER BY dataset""")
    result["missing_metadata"] = _rows(conn, """SELECT dataset,field,count(*) AS denominator,
        count(*) FILTER(WHERE value IS NULL OR btrim(value)='' OR lower(btrim(value))=ANY(%s)) AS missing_by_quality_rule
        FROM eligible CROSS JOIN LATERAL (VALUES ('title',payload->>'title'),('publisher',payload->>'publisher'),
        ('sponsor',payload->>'sponsor'),('published_at',payload->>'published_at'),('url',payload->>'url'),
        ('account',payload->>'account'),('keyword',payload->>'keyword'),('disclosure',payload->>'disclosure')) AS m(field,value)
        GROUP BY dataset,field ORDER BY dataset,field""", (sorted(PLACEHOLDERS),))
    result["body_flags"] = _rows(conn, """SELECT dataset,count(*) AS denominator,
        count(*) FILTER(WHERE body IS NULL OR btrim(body)='') AS empty_body,
        count(*) FILTER(WHERE lower(btrim(body))='video') AS video_placeholder,
        count(*) FILTER(WHERE lower(btrim(body))=ANY(%s)) AS missing_literal_body,
        count(*) FILTER(WHERE body ~ '^[[:space:]]*[+-]?[0-9]+([.,][0-9]+)?[[:space:]]*$') AS numeric_body,
        count(*) FILTER(WHERE body ~ '‚Ä|â€|ï»¿|�') AS known_garbled_marker,
        count(*) FILTER(WHERE payload->'retrievable' IS DISTINCT FROM 'true'::jsonb) AS not_retrievable
        FROM eligible GROUP BY dataset ORDER BY dataset""", (sorted(PLACEHOLDERS),))
    result["stored_issue_codes"] = _rows(conn, """SELECT dataset,issue->>'code' AS code,issue->>'severity' AS severity,
        CASE WHEN issue->>'detail' LIKE 'Previous CSV body:%%' THEN 'historical_previous_body' ELSE 'current_or_unspecified' END AS body_scope,
        count(DISTINCT record_id) AS records,
        count(DISTINCT record_id) FILTER(WHERE payload->'retrievable'='true'::jsonb) AS retrievable_records
        FROM eligible CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'issues')='array'
            THEN payload->'issues' ELSE '[]'::jsonb END) issue
        GROUP BY dataset,issue->>'code',issue->>'severity',body_scope ORDER BY dataset,records DESC,code,severity,body_scope""")
    result["native_text_scope"] = _rows(conn, """, flags AS(
        SELECT e.record_id,e.payload->'retrievable'='true'::jsonb AS retrievable,
        bool_or(i->>'code'='body_truncated_suspected' AND COALESCE(i->>'detail','') NOT LIKE 'Previous CSV body:%%') AS current_truncation_suspicion,
        bool_or(i->>'code'='body_truncated_suspected' AND i->>'detail' LIKE 'Previous CSV body:%%') AS historical_truncation_suspicion,
        bool_or(i->>'code' IN ('body_source_partial','body_partial_recovery')) AS current_partial_capture
        FROM eligible e CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(e.payload->'issues')='array'
            THEN e.payload->'issues' ELSE '[]'::jsonb END) i WHERE e.dataset='native' GROUP BY e.record_id,e.payload)
        SELECT count(*) FILTER(WHERE current_truncation_suspicion) AS current_truncation_suspected_records,
        count(*) FILTER(WHERE current_truncation_suspicion AND retrievable) AS retrievable_current_truncation_suspected,
        count(*) FILTER(WHERE historical_truncation_suspicion) AS historical_truncation_flag_records,
        count(*) FILTER(WHERE current_partial_capture) AS current_partial_capture_records,
        count(*) FILTER(WHERE current_partial_capture AND retrievable) AS retrievable_current_partial_capture,
        count(*) FILTER(WHERE current_partial_capture OR current_truncation_suspicion) AS current_partial_or_suspected_records
        FROM flags""")[0]
    result["source_integrity"] = _rows(conn, """SELECT dataset,
        count(*) FILTER(WHERE version_id IS NULL) AS missing_current_version,
        count(*) FILTER(WHERE version_record_id IS DISTINCT FROM record_id) AS wrong_version_record,
        count(*) FILTER(WHERE payload->>'record_id' IS DISTINCT FROM record_id) AS wrong_payload_record,
        count(*) FILTER(WHERE payload->>'dataset' IS DISTINCT FROM dataset) AS wrong_payload_dataset,
        count(*) FILTER(WHERE body_hash IS DISTINCT FROM encode(sha256(convert_to(body,'UTF8')),'hex')) AS body_hash_mismatch
        FROM current GROUP BY dataset ORDER BY dataset""")
    result["source_scope_shapes"] = _rows(conn, """SELECT dataset,
        count(*) FILTER(WHERE jsonb_typeof(payload->'issues') IS DISTINCT FROM 'array') AS missing_or_nonarray_issue_lists,
        count(*) FILTER(WHERE dataset='social' AND jsonb_typeof(payload#>'{raw,source_variants}') IS DISTINCT FROM 'array') AS missing_or_nonarray_observation_lists,
        count(*) FILTER(WHERE dataset='social' AND payload#>'{raw,source_variants}'='[]'::jsonb) AS empty_observation_lists
        FROM eligible GROUP BY dataset ORDER BY dataset""")
    result["duplicate_candidates"] = _rows(conn, """, vals AS (
        SELECT dataset,record_id,'body_hash' AS dimension,body_hash AS value FROM eligible WHERE btrim(body)<>''
        UNION ALL SELECT dataset,record_id,'retrievable_body_hash',body_hash FROM eligible
            WHERE btrim(body)<>'' AND payload->'retrievable'='true'::jsonb
        UNION ALL SELECT dataset,record_id,'url',payload->>'url' FROM eligible WHERE COALESCE(btrim(payload->>'url'),'')<>''
        UNION ALL SELECT dataset,record_id,'normalized_title',lower(regexp_replace(btrim(payload->>'title'),'[[:space:]]+',' ','g'))
            FROM eligible WHERE COALESCE(btrim(payload->>'title'),'')<>''),
        groups AS(SELECT dataset,dimension,value,count(*) AS members FROM vals GROUP BY 1,2,3 HAVING count(*)>1)
        SELECT dataset,dimension,count(*) AS repeated_value_groups,sum(members)::bigint AS records_in_repeated_groups,
        sum(members-1)::bigint AS excess_records_if_values_were_identity FROM groups GROUP BY 1,2 ORDER BY 1,2""")
    result["native_annotations"] = _rows(conn, """, counts AS(SELECT e.record_id,e.payload,count(a.version_id) AS n
        FROM eligible e LEFT JOIN annotations a ON a.version_id=e.version_id AND a.payload->>'version'='claims-calibrated'
        WHERE e.dataset='native' GROUP BY e.record_id,e.payload)
        SELECT count(*) AS denominator,count(*) FILTER(WHERE n=0) AS no_current_calibrated_annotation,
        count(*) FILTER(WHERE n=0 AND payload#>'{raw,previous_body_annotations}' IS NOT NULL) AS prior_body_annotations_preserved,
        count(*) FILTER(WHERE n>1) AS multiple_current_calibrated_annotations FROM counts""")[0]
    result["date_inferences"] = _rows(conn, """SELECT e.dataset,d.tier,d.precision,d.review_state,
        count(*) AS current_inference_rows,count(DISTINCT e.record_id) AS current_records,
        count(*) FILTER(WHERE NULLIF(e.payload->>'published_at','') IS NULL) AS source_date_missing,
        count(*) FILTER(WHERE d.tier='C' AND d.review_state<>'accepted' AND d.evidence->>'host_match' IS DISTINCT FROM 'true') AS unaccepted_without_host_match
        FROM eligible e JOIN date_inferences d ON d.version_id=e.version_id
        GROUP BY e.dataset,d.tier,d.precision,d.review_state ORDER BY 1,2,3,4""")
    result["social_units"] = _rows(conn, """SELECT count(*) AS counted_social_records,
        count(*) FILTER(WHERE payload#>>'{raw,social_admission,scheme}'='collected-company-posts-unique-url-v1'
        AND payload#>>'{raw,social_admission,scope}'='collected_company_posts'
        AND payload#>>'{raw,social_admission,count_unit}'='platform_canonical_original_post_url') AS admitted_unique_post_units,
        COALESCE(sum(CASE WHEN jsonb_typeof(payload#>'{raw,source_variants}')='array' THEN jsonb_array_length(payload#>'{raw,source_variants}') ELSE 0 END),0)::bigint AS preserved_source_observations,
        count(*) FILTER(WHERE payload#>>'{raw,social_admission,paid_ad_status}'='unknown') AS admission_paid_status_unknown
        FROM eligible WHERE dataset='social'""")[0]
    result["social_conflict_counts"] = _rows(conn, """SELECT conflict,count(DISTINCT record_id) AS records
        FROM eligible CROSS JOIN LATERAL jsonb_array_elements_text(CASE
        WHEN jsonb_typeof(payload#>'{raw,social_admission,conflicting_fields}')='array'
        THEN payload#>'{raw,social_admission,conflicting_fields}' ELSE '[]'::jsonb END) conflict
        WHERE dataset='social' GROUP BY conflict ORDER BY records DESC,conflict""")
    result["index_counts"] = conn.execute("""WITH indexed AS (
        SELECT r.dataset,r.active,r.current_version=c.version_id AS current_version,
        v.payload->'countable'='true'::jsonb AS countable,c.text_hash,
        EXISTS(SELECT 1 FROM chunk_profile_membership m WHERE m.chunk_id=c.chunk_id AND m.profile_id=%s) AS active_profile,
        EXISTS(SELECT 1 FROM embeddings emb WHERE emb.text_hash=c.text_hash AND emb.model=%s) AS cached_embedding
        FROM chunks c JOIN records r ON r.record_id=c.record_id JOIN record_versions v ON v.version_id=c.version_id)
        SELECT dataset,count(*) AS all_stored_chunks,
        count(*) FILTER(WHERE active AND current_version) AS active_current_version_chunks_all_profiles,
        count(*) FILTER(WHERE active AND current_version AND active_profile) AS active_profile_current_chunks,
        count(*) FILTER(WHERE active AND current_version AND active_profile AND countable) AS counted_active_profile_current_chunks,
        count(*) FILTER(WHERE active AND current_version AND active_profile AND countable AND cached_embedding) AS cached_counted_active_profile_chunks,
        count(DISTINCT text_hash) FILTER(WHERE active AND current_version AND active_profile AND countable) AS distinct_active_chunk_texts,
        count(DISTINCT text_hash) FILTER(WHERE active AND current_version AND active_profile AND countable AND cached_embedding) AS distinct_cached_active_chunk_texts
        FROM indexed GROUP BY dataset ORDER BY dataset""", (profile, embedding_model)).fetchall()
    result["embedding_cache"] = conn.execute("""SELECT count(*) AS total_cached_vector_rows,
        count(*) FILTER(WHERE model=%s) AS configured_model_cached_vector_rows FROM embeddings""", (embedding_model,)).fetchone()
    result["embedding_cache"]["model"] = embedding_model
    result["source_coverage"], failures = _source_coverage(conn, profile, review_limit)
    result["review_queue"] = bounded_queue([failures, *_review_items(conn, review_limit)], review_limit)
    result["review_limit"] = review_limit
    result["limits"] = ["No semantic answer accuracy, original-source completeness or paid-ad status is verified.",
                        "Exact duplicate text is a review candidate, not proof of duplicate articles or posts.",
                        "Missing fields must be interpreted per collection; social publisher/disclosure and native account may be inapplicable.",
                        "Current source-version hash and observation full-JSON version hash are not recomputed here.",
                        "Cached vector coverage does not measure keyword retrieval quality or authorize embedding calls."]
    return result


def collect(*, settings=None, review_limit=12):
    if type(review_limit) is not int or not 0 <= review_limit <= 50:
        raise ValueError("review_limit must be an integer from 0 to 50")
    settings = settings or Settings.from_env()
    if not settings.database_url:
        raise RuntimeError("Read-only database configuration is unavailable")
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5, options=OPTIONS) as conn:
        return collect_snapshot(conn, embedding_model=settings.embedding_model, review_limit=review_limit)


def run_audit(out, *, settings=None, review_limit=12):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    try:
        result = collect(settings=settings, review_limit=review_limit)
    except Exception as exc:
        failure = {"status": "failed", "error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None),
                   "dsn_and_source_text_omitted": True}
        (out / "failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        return 1
    queue = result.pop("review_queue")
    (out / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "review_queue.json").write_text(json.dumps({"source_fingerprint": result["source_fingerprint"],
        "snapshot": result["snapshot"], "status": "review_only_no_changes_applied", "items": queue}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New output directory; existing evidence is never overwritten")
    parser.add_argument("--review-limit", type=int, default=12, choices=range(51), metavar="0..50")
    args = parser.parse_args(argv)
    status = run_audit(args.out, review_limit=args.review_limit)
    print("Read-only audit complete." if status == 0 else "Read-only audit failed; inspect sanitized failure.json.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
