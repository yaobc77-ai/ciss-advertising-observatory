"""Build the versioned knowledge maps from a private read-only database copy.

usage: python scripts/build_cooccurrence_maps.py --cluster kg_maps_1019 --database kg_1019 [--embed]

Reads current countable records only; never writes to the database. Output goes to
.runtime/knowledge_maps/<data version>/knowledge_maps.json (one file per data version).
--embed adds the semantic map (name embeddings, paid; the spend is printed and capped).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from observatory.cooccurrence_maps import SCHEMA_VERSION, project, semantic_projection  # noqa: E402
from observatory.entities import registry  # noqa: E402

CURRENT = ("FROM records r JOIN record_versions v ON v.version_id=r.current_version "
           "WHERE r.active AND COALESCE((v.payload->>'countable')::boolean,false) AND r.dataset=%s")
# Post constellation: a reverse projection over posts. Only posts with at least
# this many hashtags, and only hashtags used by at most this many posts (a very
# common tag links hundreds of posts to each other and says little).
CONSTELLATION_MIN_TAGS = 3
CONSTELLATION_MAX_TAG_POSTS = 60
EMBED_CAP_USD = 0.05


def connect(cluster, database, runtime):
    import psycopg
    from psycopg.rows import dict_row
    base = Path(runtime) / "private_test_postgres" / cluster
    state = json.loads((base / "cluster.json").read_text())
    cred = json.loads((base / "credentials.json").read_text())
    if state["port"] in (5432, 55432):
        raise SystemExit("Refusing a main-database port")
    conn = psycopg.connect(host="127.0.0.1", port=state["port"], dbname=database, user=cred["admin_user"],
                           password=cred["admin_password"], row_factory=dict_row)
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return conn


def values(value):
    items = value if isinstance(value, list) else [value]
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def data_version(conn):
    """Fingerprint of the current versions read (record and version IDs)."""
    digest = hashlib.sha256()
    for row in conn.execute("SELECT r.record_id, r.current_version FROM records r WHERE r.active ORDER BY 1"):
        digest.update(f"{row['record_id']}\t{row['current_version']}\n".encode())
    return digest.hexdigest()


def load(conn):
    posts = conn.execute(
        "SELECT r.record_id, v.payload->>'sponsor' AS sponsor, v.payload->>'account' AS account, "
        "v.payload#>'{raw,source_row,post.hashtags_identified}' AS hashtags, "
        "v.payload#>'{raw,source_row,engagement,username_mentions}' AS mentions, "
        "v.payload#>'{raw,source_row,parent_entity_info}' AS profile " + CURRENT, ["social"]).fetchall()
    ads = conn.execute(
        "SELECT r.record_id, v.payload->>'sponsor' AS sponsor, a.payload->'labels' AS labels " + CURRENT.replace(
            "WHERE", "LEFT JOIN annotations a ON a.version_id=v.version_id AND a.payload->>'version'='claims-calibrated' WHERE"),
        ["native"]).fetchall()
    return posts, ads


def company(dataset, sponsor):
    """Registry organization when listed (unreviewed AI-proposed), else the exact source spelling."""
    owner = registry().for_source(dataset, "sponsor", sponsor)
    return (owner.id, owner.name) if owner else (f"{dataset}:{sponsor}", sponsor)


def build(conn, out_dir, embed):
    version = data_version(conn)
    posts, ads = load(conn)
    ref = {row["record_id"]: f"/records/{row['record_id']}" for row in [*posts, *ads]}
    tags = {row["record_id"]: {"#" + t.lstrip("#").casefold() for t in values(row["hashtags"]) if t.lstrip("#")} for row in posts}
    mentions = {row["record_id"]: {"@" + h.lstrip("@").casefold() for h in values(row["mentions"]) if h.lstrip("@")} for row in posts}
    labels = {row["record_id"]: {str(label) for label in (row["labels"] or []) if isinstance(label, str)} for row in ads}
    coverage = {"social_posts": len(posts), "posts_with_hashtags": sum(bool(v) for v in tags.values()),
                "posts_with_mentions": sum(bool(v) for v in mentions.values()), "native_ads": len(ads),
                "ads_with_calibrated_labels": sum(bool(v) for v in labels.values())}
    views = {}
    views["hashtags"] = project({k: v for k, v in tags.items() if v}, view="hashtags", unit_kind="X post",
                                node_kind="hashtag", edge_meaning="two hashtags listed on the same post",
                                unit_refs=ref, notes=["Hashtags as the source row lists them, compared without case."])
    # Reverse projection: posts are nodes, a shared hashtag is the unit.
    usage = Counter(tag for v in tags.values() for tag in v)
    sampled = {post: {t for t in v if usage[t] <= CONSTELLATION_MAX_TAG_POSTS} for post, v in tags.items()}
    sampled = {post: v for post, v in sampled.items() if len(v) >= CONSTELLATION_MIN_TAGS}
    by_tag = defaultdict(set)
    for post, v in sampled.items():
        for tag in v:
            by_tag[tag].add(post)
    views["post_constellation"] = project(
        dict(by_tag), view="post_constellation", unit_kind="hashtag", node_kind="X post",
        edge_meaning="two posts sharing hashtags", unit_refs={t: t for t in by_tag},
        labels={row["record_id"]: f"{row['account'] or row['sponsor'] or 'post'} · {row['record_id'][-6:]}"
                for row in posts if row["record_id"] in sampled},
        notes=[f"Sampled: posts with at least {CONSTELLATION_MIN_TAGS} hashtags, counting only hashtags used by at most "
               f"{CONSTELLATION_MAX_TAG_POSTS} posts; {len(sampled)} of {len(posts)} posts qualify."])
    # Company map: companies are nodes; a shared hashtag or historical label is the unit.
    features, names, profile_type = defaultdict(set), {}, {}
    for row in posts:
        key, name = company("social", row["sponsor"] or "")
        if not row["sponsor"]:
            continue
        names[key] = name
        if isinstance(row["profile"], dict) and row["profile"].get("type"):
            profile_type.setdefault(key, row["profile"]["type"])
        for tag in tags[row["record_id"]]:
            features[tag].add(key)
    for row in ads:
        if not row["sponsor"]:
            continue
        key, name = company("native", row["sponsor"])
        names[key] = name
        for label in labels[row["record_id"]]:
            features["label:" + label].add(key)
    views["companies"] = project(
        dict(features), view="companies", unit_kind="hashtag or historical label", node_kind="company",
        edge_meaning="two companies using the same hashtags (posts) or historical labels (ads)",
        labels=names, topics=profile_type, unit_refs={f: f for f in features},
        notes=["Companies join native sponsor and social affiliation spellings through the unreviewed AI-proposed "
               "entity registry; an unlisted spelling stays its own node.",
               "topic_id is the social source's own company type (unverified), not a community."])
    views["mentions"] = project({k: v for k, v in mentions.items() if v}, view="mentions", unit_kind="X post",
                                node_kind="@handle", edge_meaning="two handles mentioned in the same post",
                                unit_refs=ref, notes=["Mentions only; explicit replies, quotes and reposts are a "
                                                      "separate relation type in the knowledge graph."])
    views["historical_labels"] = project({k: v for k, v in labels.items() if v}, view="historical_labels",
                                         unit_kind="native ad", node_kind="historical label",
                                         edge_meaning="two labels assigned to the same ad", unit_refs=ref,
                                         notes=["claims-calibrated historical automatic labels; unverified."])
    semantic, spend = None, 0.0
    if embed:
        semantic, spend = semantic_view(views)
    result = {"schema_version": SCHEMA_VERSION, "built_at": datetime.now(timezone.utc).isoformat(),
              "data_version": version, "source": "private read-only restore of observatory-full-20261019T015537Z.dump",
              "coverage": coverage, "views": views, "semantic": semantic, "embedding_spend_usd": round(spend, 6),
              "omitted": {"claims": "ad x CLAIMS2 subclaim map waits for published CLAIMS2 assignments"}}
    out = out_dir / version[:16]
    out.mkdir(parents=True, exist_ok=True)
    (out / "knowledge_maps.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return out / "knowledge_maps.json", result


def semantic_view(views):
    """Hashtag-map hashtags and historical labels; CLAIMS2 names join when a taxonomy bundle is available."""
    from openai import OpenAI
    items = [{"id": node["id"], "label": node["label"], "kind": "hashtag"} for node in views["hashtags"]["nodes"]]
    items += [{"id": node["id"], "label": node["label"].replace("_", " "), "kind": "historical label"}
              for node in views["historical_labels"]["nodes"]]
    texts = [item["label"] for item in items]
    estimate = sum(len(text) for text in texts) / 3 * 0.02 / 1_000_000
    if estimate > EMBED_CAP_USD:
        raise SystemExit(f"Embedding estimate ${estimate:.4f} exceeds the ${EMBED_CAP_USD} cap")
    client = OpenAI(timeout=60, max_retries=1)
    vectors, tokens = [], 0
    for start in range(0, len(texts), 500):
        response = client.embeddings.create(model="text-embedding-3-small", input=texts[start:start + 500])
        vectors += [item.embedding for item in response.data]
        tokens += response.usage.total_tokens
    spend = tokens * 0.02 / 1_000_000
    view = semantic_projection(items, vectors)
    view["notes"] = ["CLAIMS2 subclaim and superclaim names are not included: no taxonomy bundle is available in "
                     "this checkout or in the restored database (claims2_taxonomies is empty)."]
    view["embedding"] = {"model": "text-embedding-3-small", "tokens": tokens, "usd": round(spend, 6)}
    return view, spend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--runtime", default=str(ROOT / ".runtime"), help="Directory holding private_test_postgres")
    parser.add_argument("--out", default=str(ROOT / ".runtime" / "knowledge_maps"))
    parser.add_argument("--embed", action="store_true")
    args = parser.parse_args()
    if args.embed:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    with connect(args.cluster, args.database, args.runtime) as conn:
        path, result = build(conn, Path(args.out), args.embed)
    print(path)
    print(json.dumps({"data_version": result["data_version"][:16], "coverage": result["coverage"],
                      "views": {name: view["counts"] for name, view in result["views"].items()},
                      "semantic": result["semantic"] and result["semantic"]["counts"],
                      "embedding_spend_usd": result["embedding_spend_usd"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
