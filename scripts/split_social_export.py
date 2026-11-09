"""Split a large Junkipedia social export into shards the importer accepts; no database or model calls.

    python scripts/split_social_export.py EXPORT.json --out NEW_DIR [--shards N]

The export is streamed (one JSON object at a time), so a file far above the preparation size limit
never has to be loaded whole. Rows are grouped per platform, and every row of one post goes to the same
shard: Twitter rows by the canonical original-post URL the admission step counts by, other platforms by
platform plus the supplied post ID. So no post's observations are split across shards, and importing the
shards one after another with ``--mode upsert`` cannot overwrite one shard's post with another's.

Each shard is named ``<stem>.<platform>.shard-NN-of-NN.json`` (X rows count as Twitter). The importer refuses such a batch in
snapshot mode, because a snapshot of one shard would retire the posts in the others. Rows are written
re-serialized (same JSON values, not the original bytes); manifest.json reconciles row counts and records
the input's SHA-256. All shards and the manifest are written into a staging directory next to NEW_DIR,
which is renamed to NEW_DIR in one step only after the whole export parsed and every shard is within
the preparation limit. On a failure the staging directory is removed and NEW_DIR, if it can be created,
holds only the failure manifest, so no importable prefix is ever published.

Facebook and Instagram posts are counted per post ID, but one post can appear under two IDs with the
same URL, and those two IDs can land in different shards. So the whole export is scanned for post IDs
sharing a URL, and the list is written as identity_conflicts.json, bound to the export's and every
shard's SHA-256. scripts/prepare_social_admission.py needs it (--identity-conflicts) for any shard
with Facebook/Instagram rows, and pauses retrieval of every listed post.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from observatory.social_admission import (
    IDENTITY_CONFLICTS_SCHEMA,
    canonical_post_url,
    export_uid_entry,
    shared_url_keys,
)
from observatory.social_archive import (
    MAX_JSON_BYTES,
    _invalid_constant,
    _original_url,
    _unique_object,
)

WS = " \t\r\n"


def iter_array(stream, chunk=1 << 20):
    """Yield the objects of a top-level JSON array of objects, one at a time, from a text stream."""
    dec = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    state = {"buf": "", "pos": 0}

    def fill():
        more = stream.read(chunk)
        if not more:
            return False
        state["buf"] = state["buf"][state["pos"]:] + more
        state["pos"] = 0
        return True

    def skip_ws():
        while True:
            buf, pos = state["buf"], state["pos"]
            while pos < len(buf) and buf[pos] in WS:
                pos += 1
            state["pos"] = pos
            if pos < len(buf) or not fill():
                return

    fill()
    if state["buf"].startswith("﻿"):
        state["pos"] = 1
    skip_ws()
    if state["buf"][state["pos"]:state["pos"] + 1] != "[":
        raise ValueError("The export is not a JSON array")
    state["pos"] += 1
    first = True
    while True:
        skip_ws()
        buf, pos = state["buf"], state["pos"]
        if pos >= len(buf):
            raise ValueError("Unexpected end of the export")
        if buf[pos] == "]":
            rest = buf[pos + 1:]
            while True:
                if rest.strip(WS):
                    raise ValueError("Trailing data after the JSON array")
                rest = stream.read(chunk)
                if not rest:
                    return
        if not first:
            if buf[pos] != ",":
                raise ValueError("Expected ',' between array elements")
            state["pos"] = pos + 1
            skip_ws()
        if state["buf"][state["pos"]:state["pos"] + 1] != "{":
            raise ValueError("Only arrays of JSON objects are supported")
        while True:
            try:
                obj, end = dec.raw_decode(state["buf"], state["pos"])
                break
            except json.JSONDecodeError:
                if not fill():
                    raise
        yield obj
        state["pos"] = end
        first = False


def post_key(row):
    """The identity a post is counted by; rows without one go together under 'unidentified'."""
    platform = row.get("platform") if isinstance(row.get("platform"), str) else ""
    if platform.casefold() in {"twitter", "x"}:
        try:
            canonical = canonical_post_url(platform, _original_url(row))
        except ValueError:
            canonical = None
        if canonical:
            return platform, "twitter\n" + canonical
    post = row.get("post") if isinstance(row.get("post"), dict) else {}
    uid = post.get("junkipedia_uid")
    if isinstance(uid, str) and uid:
        return platform, f"{platform.casefold()}\n{uid}"
    return platform, "unidentified"


def _safe(platform):
    if platform.casefold() in {"twitter", "x"}:
        return "twitter"
    return "".join(ch for ch in platform.casefold() if ch.isalnum()) or "unknown"


def _write_shards(source, staging, shards):
    """Write every row into its shard under ``staging``.

    Returns (shard names, row counts, rows, failure, Facebook/Instagram (key, URL) entries).
    """
    handles, counts, rows, entries = {}, Counter(), 0, []
    failure = None
    try:
        with source.open(encoding="utf-8") as stream:
            for row in iter_array(stream):
                rows += 1
                platform, key = post_key(row)
                if _safe(platform) != "twitter" and (entry := export_uid_entry(row)) is not None:
                    entries.append(entry)
                bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % shards
                name = f"{source.stem}.{_safe(platform)}.shard-{bucket + 1:02d}-of-{shards:02d}.json"
                # allow_nan=False: an overflowing number such as 1e400 parses to inf and must not
                # be written back as the non-JSON token Infinity.
                text = json.dumps(row, ensure_ascii=False, allow_nan=False)
                if name not in handles:
                    handles[name] = (staging / name).open("x", encoding="utf-8", newline="\n")
                    handles[name].write("[")
                else:
                    handles[name].write(",\n")
                handles[name].write(text)
                counts[name] += 1
    except (ValueError, UnicodeDecodeError) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        for handle in handles.values():
            if failure is None:
                handle.write("]\n")
            handle.close()
    return sorted(handles), counts, rows, failure, entries


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as raw:
        for block in iter(lambda: raw.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_identity_conflicts(staging, names, export_sha, entries):
    """Write identity_conflicts.json; return its manifest entry."""
    ambiguous = dict(sorted(shared_url_keys(entries).items()))
    listing = {
        "schema_version": IDENTITY_CONFLICTS_SCHEMA, "export_sha256": export_sha,
        "shard_sha256": {name: _file_sha256(staging / name) for name in names},
        "basis": "Facebook/Instagram post IDs whose post URL (host without www./web./m., path without a "
                 "trailing slash, query kept, case kept) also belongs to another post ID in the whole export",
        "ambiguous": ambiguous,
    }
    path = staging / "identity_conflicts.json"
    path.write_text(json.dumps(listing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"file": path.name, "sha256": _file_sha256(path), "post_id_rows": len(entries),
            "ambiguous_post_ids": len(ambiguous)}


def _write_manifest(directory, manifest):
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")


def split_export(source, out, shards, limit=MAX_JSON_BYTES):
    source, out = Path(source), Path(out)
    if shards < 1:
        raise ValueError("--shards must be at least 1")
    if out.exists() or out.is_symlink():
        raise FileExistsError(f"{out} already exists; split into a new directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as raw:
        for block in iter(lambda: raw.read(1 << 20), b""):
            digest.update(block)
    # Same parent as NEW_DIR, so publishing is one directory rename on one volume: either every shard
    # and the manifest appear under NEW_DIR, or none do.
    staging = out.parent / f".{out.name}.staging-{uuid4().hex}"
    staging.mkdir()
    try:
        names, counts, rows, failure, entries = _write_shards(source, staging, shards)
        sizes = {name: (staging / name).stat().st_size for name in names}
        too_big = sorted(name for name, size in sizes.items() if size > limit)
        if failure is None and too_big:
            failure = (f"{len(too_big)} shards exceed the {limit}-byte preparation limit; split again into a "
                       "new directory with more --shards")
        if failure is None and sum(counts.values()) != rows:
            failure = "Row counts do not reconcile"
        manifest = {
            "input": source.name, "input_sha256": digest.hexdigest(), "input_rows": rows,
            "shards": shards, "limit_bytes": limit, "rows_written": sum(counts.values()),
            "status": "complete" if failure is None else "failed_no_shards_published", "failure": failure,
            "files": {name: {"rows": counts[name], "bytes": sizes[name]} for name in names},
            "key": "Twitter/X: canonical original-post URL; other platforms: platform + post.junkipedia_uid",
            "serialization": "re-serialized JSON values (ensure_ascii=False), not original bytes",
            "too_big": too_big,
        }
        if failure is None:
            manifest["identity_conflicts"] = _write_identity_conflicts(staging, names, manifest["input_sha256"],
                                                                       entries)
            _write_manifest(staging, manifest)
            os.rename(staging, out)
            return manifest
    finally:
        # Any failure, including an OSError or an interrupt, leaves NEW_DIR without shards.
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    if staging.exists():
        manifest["staging_not_removed"] = staging.name
    out.mkdir()
    _write_manifest(out, manifest)
    raise ValueError(failure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="New directory for the shards and manifest")
    parser.add_argument("--shards", type=int, default=4, help="Shards per platform (default 4)")
    args = parser.parse_args(argv)
    manifest = split_export(args.export, args.out, args.shards)
    print(json.dumps({k: manifest[k] for k in ("input_rows", "rows_written", "shards")} |
                     {"files": len(manifest["files"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
