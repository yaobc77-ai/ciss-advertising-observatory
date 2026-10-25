"""Freeze unpaid embedding inputs from the local active profile; never execute them.

No provider client, vector insertion, budget reservation or index activation is
available here. JSONL text is private runtime material, not a source artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from observatory.budget import price  # noqa: E402
from observatory.chunking import _tokens  # noqa: E402
from observatory.db import Database  # noqa: E402
from observatory.indexing import active_profile, profile_snapshot  # noqa: E402

SCHEMA = "embedding-backfill-preparation-v1"
SETTLEMENT_SCHEMA = "embedding-backfill-settlement-v1"
SETTLEMENT_FIELDS = ("plan_sha256", "batch_id", "request_sha256", "response_sha256", "model", "dimensions")
MODEL = "text-embedding-3-small"
INPUT_STRATEGY = "original-chunk-text-v1"
API_LIMITS = {"input_tokens": 8192, "inputs_per_request": 2048, "request_tokens": 300_000}
OFFICIAL_SOURCES = {
    "price": "https://developers.openai.com/api/docs/models/text-embedding-3-small",
    "limits": "https://developers.openai.com/api/reference/resources/embeddings/methods/create",
    "checked_on": "2026-10-08",
}
CODE_PATHS = (
    "scripts/prepare_embedding_backfill.py", "src/observatory/db.py",
    "src/observatory/indexing.py", "src/observatory/chunking.py",
    "src/observatory/segmentation.py", "src/observatory/social_source_retrieval.py",
    "src/observatory/budget.py",
)
STATE_TABLES = (
    "records", "record_versions", "chunks", "chunk_profile_membership",
    "retrieval_profiles", "retrieval_state", "embeddings", "usage_ledger",
)
BINDING_FIELDS = (
    "chunk_id", "dataset", "record_id", "version_id", "body_hash",
    "start_char", "end_char", "source_observation_id", "source_version_id",
    "source_body_hash",
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def code_hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in CODE_PATHS}


class ReadOnlyDb(Database):
    def connect(self, vector=False):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row

        settings = conninfo_to_dict(self.url)
        if settings.get("host", "") not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Preparation only accepts an explicit loopback database")
        if settings.get("hostaddr", "") not in {"", "127.0.0.1", "::1"}:
            raise ValueError("A remote hostaddr is not allowed")
        # Server enforcement applies even if an imported helper accidentally writes.
        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5,
                              options="-c default_transaction_read_only=on")


def read_state(conn, model):
    snapshot = profile_snapshot(conn)
    profile = conn.execute(
        "SELECT definition,definition_hash FROM retrieval_profiles WHERE profile_id=%s",
        (snapshot["active_profile"],),
    ).fetchone()
    if (profile["definition"].get("embedding_input") != INPUT_STRATEGY
            or profile["definition"].get("embedding_model") != model
            or sha(canonical(profile["definition"])) != profile["definition_hash"]):
        raise ValueError("Unsupported or modified model/profile/input definition")
    tables = {}
    for table in STATE_TABLES:
        # Table names are a fixed allowlist. Only aggregate hashes leave PostgreSQL.
        tables[table] = conn.execute(
            f"SELECT count(*) AS rows,md5(COALESCE(string_agg(md5(row_to_json(t)::text),"
            f"',' ORDER BY md5(row_to_json(t)::text)),'')) AS fingerprint FROM {table} t"
        ).fetchone()
    cache = conn.execute(
        "SELECT text_hash,md5(embedding::text) AS vector_hash FROM embeddings WHERE model=%s ORDER BY text_hash",
        (model,),
    ).fetchall()
    return {"snapshot": snapshot, "profile": dict(profile), "tables": tables,
            "cache": {row["text_hash"]: row["vector_hash"] for row in cache},
            "code_sha256": code_hashes(), "model": model,
            "transaction_read_only": conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"]}


def validate_chunk(row, source, observations=None):
    """Reject changed source text/ranges; do not reconstruct or normalize input."""
    if (source["record_id"] != row["record_id"] or source["version_id"] != row["version_id"]
            or source["dataset"] != row["dataset"] or source["body_hash"] != row["body_hash"]):
        raise ValueError("Chunk record/version/body binding changed")
    body = source["body"]
    if row.get("source_observation_id") is not None:
        observation = (observations or {}).get(row["source_observation_id"])
        if not observation or any(row[field] != observation[field]
                                  for field in ("source_version_id", "source_body_hash")):
            raise ValueError("Source observation identity changed")
        body = observation["body"]
    elif row.get("source_version_id") is not None or row.get("source_body_hash") is not None:
        raise ValueError("Partial observation identity")
    start, end = row["start_char"], row["end_char"]
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body)
            or body[start:end] != row["text"] or sha(row["text"]) != row["text_hash"]):
        raise ValueError("Chunk is not the unchanged original source interval")
    tokens = _tokens(row["text"])
    if not row["text"].strip() or tokens != row["token_count"] or not 1 <= tokens <= API_LIMITS["input_tokens"]:
        raise ValueError("Empty, changed or oversized embedding input")


def collect(db, model=MODEL):
    from observatory.social_source_retrieval import validated_observations

    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        state = read_state(conn, model)
        if state["transaction_read_only"] != "on":
            raise ValueError("A server-enforced read-only transaction is required")
        profile_id = active_profile(conn)
        sources = conn.execute(
            "SELECT r.record_id,r.dataset,v.version_id,v.body,v.body_hash,v.payload FROM records r "
            "JOIN record_versions v ON v.version_id=r.current_version AND v.record_id=r.record_id WHERE r.active"
        ).fetchall()
        by_id, observations = {}, {}
        for source in sources:
            payload = source["payload"]
            if (sha(source["body"]) != source["body_hash"] or payload.get("body") != source["body"]
                    or sha(canonical(payload)) != source["version_id"]
                    or payload.get("record_id") != source["record_id"] or payload.get("dataset") != source["dataset"]):
                raise ValueError("Current source body or complete payload was modified")
            by_id[source["record_id"]] = source
        rows = conn.execute(
            "SELECT c.*,r.dataset,v.body_hash FROM chunks c "
            "JOIN chunk_profile_membership m ON m.chunk_id=c.chunk_id "
            "JOIN records r ON r.record_id=c.record_id AND r.current_version=c.version_id "
            "JOIN record_versions v ON v.record_id=r.record_id AND v.version_id=r.current_version "
            "WHERE r.active AND m.profile_id=%s ORDER BY c.text_hash,c.chunk_id", (profile_id,)
        ).fetchall()
        for row in rows:
            source = by_id[row["record_id"]]
            if source["payload"].get("countable") is not True or source["payload"].get("retrievable") is not True:
                raise ValueError("Active chunk has no current retrieval permission")
            if row.get("source_observation_id") and row["record_id"] not in observations:
                observations[row["record_id"]] = {o["source_observation_id"]: o
                                                 for o in validated_observations(source["payload"])}
            validate_chunk(row, source, observations.get(row["record_id"]))
        # Full membership, including stale members, was read by profile_snapshot.
        if len(rows) != state["snapshot"]["chunks"]:
            raise ValueError("Active profile contains stale or missing current members")
    pending = db.pending_embeddings(model, profile_id=profile_id)
    missing = {r["text_hash"]: r["text"] for r in rows if r["text_hash"] not in state["cache"]}
    if missing != {r["text_hash"]: r["text"] for r in pending}:
        raise ValueError("pending_embeddings differs from frozen cache/membership")
    return state, rows


def batch_inputs(inputs, batch_size=32, max_batch_tokens=100_000):
    if (type(batch_size) is not int or not 1 <= batch_size <= API_LIMITS["inputs_per_request"]
            or type(max_batch_tokens) is not int or not 1 <= max_batch_tokens <= API_LIMITS["request_tokens"]):
        raise ValueError("Batch limits exceed the API contract")
    batches, group = [], []
    for item in inputs:
        if not 1 <= item["input_tokens"] <= min(API_LIMITS["input_tokens"], max_batch_tokens):
            raise ValueError("Input exceeds the selected token limit")
        if group and (len(group) >= batch_size or sum(i["input_tokens"] for i in group) + item["input_tokens"] > max_batch_tokens):
            batches.append(group)
            group = []
        group.append(item)
    if group:
        batches.append(group)
    result = []
    for number, group in enumerate(batches, 1):
        hashes = [item["text_hash"] for item in group]
        tokens = sum(item["input_tokens"] for item in group)
        upper = sum(item["utf8_bytes"] for item in group) + 100
        request = {"model": MODEL, "dimensions": 1536, "input": [item["text"] for item in group]}
        result.append({"batch_id": f"batch-{number:05d}", "text_hashes": hashes, "input_tokens": tokens,
                       "request_sha256": sha(canonical(request)), "estimated_usd": str(price(MODEL, tokens)),
                       "existing_rag_reservation_upper_usd": str(price(MODEL, upper))})
    return result


def prepare(state, rows, batch_size=32, max_batch_tokens=100_000):
    if state["model"] != MODEL:
        raise ValueError("Only the existing configured embedding model is supported")
    unique, counts, cached_counts = {}, Counter(), Counter()
    for row in rows:
        counts[row["dataset"]] += 1
        if row["text_hash"] in state["cache"]:
            cached_counts[row["dataset"]] += 1
            continue
        tokens = _tokens(row["text"])
        if sha(row["text"]) != row["text_hash"] or tokens != row["token_count"] or not row["text"].strip():
            raise ValueError("Changed input hash/token count")
        item = unique.setdefault(row["text_hash"], {"text_hash": row["text_hash"], "text": row["text"],
                                 "input_tokens": tokens, "utf8_bytes": len(row["text"].encode("utf-8")), "bindings": []})
        if item["text"] != row["text"]:
            raise ValueError("Conflicting texts share a hash")
        binding = {key: row.get(key) for key in BINDING_FIELDS}
        if binding in item["bindings"]:
            raise ValueError("Duplicate chunk binding")
        item["bindings"].append(binding)
    inputs = [unique[key] for key in sorted(unique)]
    for item in inputs:
        item["bindings"].sort(key=lambda binding: binding["chunk_id"])
    batches = batch_inputs(inputs, batch_size, max_batch_tokens)
    summary = {}
    for dataset in ("native", "social"):
        selected = [item for item in inputs if any(b["dataset"] == dataset for b in item["bindings"])]
        tokens = sum(item["input_tokens"] for item in selected)
        summary[dataset] = {"active_chunks": counts[dataset], "cached_chunks": cached_counts[dataset],
                            "missing_chunks": counts[dataset] - cached_counts[dataset],
                            "unique_missing_texts": len(selected), "input_tokens": tokens,
                            "estimated_usd": str(price(MODEL, tokens))}
    tokens = sum(item["input_tokens"] for item in inputs)
    manifest = {"schema": SCHEMA, "status": "prepared_unpaid", "model": MODEL, "dimensions": 1536,
                "embedding_input": INPUT_STRATEGY, "metadata_prefix": False, "tokenizer": "cl100k_base",
                "tiktoken_version": version("tiktoken"), "frozen_state": state, "by_dataset": summary,
                "unique_missing_texts": len(inputs), "input_tokens": tokens, "estimated_usd": str(price(MODEL, tokens)),
                "existing_rag_reservation_upper_usd": str(sum(
                    (Decimal(batch["existing_rag_reservation_upper_usd"]) for batch in batches), Decimal(0))),
                "batches": len(batches), "batch_size": batch_size, "max_batch_tokens": max_batch_tokens,
                "api_limits": API_LIMITS, "official_sources": OFFICIAL_SOURCES,
                "api_calls": 0, "completed_vectors": 0, "database_writes": 0, "index_activated": False,
                "paid_authorization": None, "retry_policy": "no_automatic_retry; pending_or_uncertain_blocks_resume",
                "resume_contract": {"settlement_schema": SETTLEMENT_SCHEMA,
                                    "ledger_binding_path": "usage.embedding_backfill",
                                    "binding_fields": list(SETTLEMENT_FIELDS),
                                    "reservation_reuse": "forbidden"},
                "cost_scope": "unique uncached original text; dataset costs may overlap; standard synchronous API price"}
    return manifest, inputs, batches


def write_bundle(directory, manifest, inputs, batches):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for filename, rows in (("inputs.jsonl", inputs), ("batches.jsonl", batches)):
        data = "".join(canonical(row) + "\n" for row in rows).encode("utf-8")
        (directory / filename).write_bytes(data)
        artifacts[filename] = {"sha256": sha(data), "rows": len(rows)}
    manifest = {**manifest, "artifacts": artifacts}
    manifest["plan_sha256"] = sha(canonical(manifest))
    manifest["prepared_at_utc"] = datetime.now(timezone.utc).isoformat()
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def read_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    frozen = {key: value for key, value in manifest.items() if key not in {"plan_sha256", "prepared_at_utc"}}
    if manifest.get("schema") != SCHEMA or sha(canonical(frozen)) != manifest.get("plan_sha256"):
        raise ValueError("Manifest changed")
    rows = {}
    for name in ("inputs.jsonl", "batches.jsonl"):
        data = (directory / name).read_bytes()
        if sha(data) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Frozen private artifact changed")
        rows[name] = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        if len(rows[name]) != manifest["artifacts"][name]["rows"]:
            raise ValueError("Frozen artifact count changed")
    expected = batch_inputs(rows["inputs.jsonl"], manifest["batch_size"], manifest["max_batch_tokens"])
    if expected != rows["batches.jsonl"]:
        raise ValueError("Frozen batch membership or token limits changed")
    for item in rows["inputs.jsonl"]:
        if sha(item["text"]) != item["text_hash"] or _tokens(item["text"]) != item["input_tokens"]:
            raise ValueError("Frozen text or token count changed")
    return manifest, rows["inputs.jsonl"], rows["batches.jsonl"]


def assert_unchanged(manifest, live_state):
    if manifest["frozen_state"] != live_state:
        raise ValueError("Source/profile/cache/ledger/code drift: prepare a new immutable bundle")


def resume_remaining(manifest, inputs, live_state, checkpoints, settlements):
    """Plan future remaining hashes only; this does not execute or certify vectors.

    A later approved executor must read actual ledger rows, including their
    reservation identity and usage.embedding_backfill request/response binding.
    One reservation can certify exactly one batch, never two paid requests.
    """
    before = manifest["frozen_state"]
    for key in ("snapshot", "profile", "code_sha256", "model"):
        if live_state[key] != before[key]:
            raise ValueError("Source/profile/code/model drift")
    for table in STATE_TABLES:
        if table not in {"embeddings", "usage_ledger"} and live_state["tables"][table] != before["tables"][table]:
            raise ValueError("Stored source or membership drift")
    for text_hash, vector_hash in before["cache"].items():
        if live_state["cache"].get(text_hash) != vector_hash:
            raise ValueError("An existing cached vector changed")
    expected = {item["text_hash"] for item in inputs}
    batch_lookup = {batch["batch_id"]: batch for batch in batch_inputs(
        inputs, manifest["batch_size"], manifest["max_batch_tokens"])}
    completed, reservations = set(), set()
    for event in checkpoints:
        if event.get("state") in {"pending", "uncertain"}:
            raise ValueError("Unknown paid attempt blocks resume; do not resend")
        reservation_id = event.get("reservation_id")
        if not isinstance(reservation_id, str) or not reservation_id.strip() or reservation_id in reservations:
            raise ValueError("Missing or duplicate reservation cannot certify another batch")
        reservations.add(reservation_id)
        ledger = settlements.get(reservation_id)
        usage = ledger.get("usage") if isinstance(ledger, dict) else None
        binding = usage.get("embedding_backfill") if isinstance(usage, dict) else None
        required_binding = {key: event.get(key) for key in SETTLEMENT_FIELDS}
        required_binding["schema"] = SETTLEMENT_SCHEMA
        try:
            actual = Decimal(str(ledger.get("actual_usd"))) if ledger else Decimal("NaN")
        except (InvalidOperation, ValueError):
            actual = Decimal("NaN")
        hashes = event.get("vector_hashes") or {}
        batch = batch_lookup.get(event.get("batch_id"))
        if (event.get("state") != "settled_cached" or event.get("plan_sha256") != manifest["plan_sha256"]
                or event.get("model") != MODEL or event.get("dimensions") != 1536
                or not re.fullmatch(r"[0-9a-f]{64}", event.get("response_sha256", ""))
                or not hashes or not set(hashes) <= expected or completed.intersection(hashes)
                or not batch or set(hashes) != set(batch["text_hashes"])
                or event.get("request_sha256") != batch["request_sha256"]
                or not ledger or ledger.get("state") != "settled" or ledger.get("kind") != "embedding"
                or ledger.get("reservation_id") != reservation_id or ledger.get("model") != MODEL
                or not actual.is_finite() or actual < 0
                or not isinstance(binding, dict)
                or any(binding.get(key) != value for key, value in required_binding.items())
                or any(live_state["cache"].get(h) != v for h, v in hashes.items())):
            raise ValueError("Checkpoint is not bound to a settled request and live cache")
        completed.update(hashes)
    added = set(live_state["cache"]) - set(before["cache"])
    if added != completed:
        raise ValueError("Unaccounted cache additions require a new preparation")
    return sorted(expected - completed)


def private_directory(path):
    path = Path(path).resolve()
    private_root = (ROOT / ".runtime" / "embedding_backfill_20261008").resolve()
    if private_root not in path.parents:
        raise ValueError("Private artifacts must stay below .runtime/embedding_backfill_20261008/")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--verify", type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-batch-tokens", type=int, default=100_000)
    args = parser.parse_args(argv)
    from observatory.config import Settings

    settings = Settings.from_env()
    if settings.embedding_model != MODEL:
        raise ValueError("Current model differs from the approved project price/dimension contract")
    db = ReadOnlyDb(settings.database_url)
    target = private_directory(args.output or args.verify)
    if args.verify:
        manifest, _, _ = read_bundle(target)
        with db.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            assert_unchanged(manifest, read_state(conn, MODEL))
        print(canonical({"status": "verified_prepared_unpaid", "plan_sha256": manifest["plan_sha256"], "api_calls": 0}))
        return 0
    state, rows = collect(db)
    manifest, inputs, batches = prepare(state, rows, args.batch_size, args.max_batch_tokens)
    manifest = write_bundle(target, manifest, inputs, batches)
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        after = read_state(conn, MODEL)
    assert_unchanged(manifest, after)
    receipt = {"status": "verified_prepared_unpaid", "plan_sha256": manifest["plan_sha256"],
               "source_cache_ledger_unchanged": True, "transaction_read_only": after["transaction_read_only"],
               "api_calls": 0, "database_writes": 0, "completed_vectors": 0, "index_activated": False}
    (target / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(canonical({**receipt, "by_dataset": manifest["by_dataset"], "input_tokens": manifest["input_tokens"],
                     "estimated_usd": manifest["estimated_usd"], "batches": manifest["batches"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
