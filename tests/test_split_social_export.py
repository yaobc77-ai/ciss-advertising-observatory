"""Splitting a large social export: posts stay whole, shards stay within the limit, rows reconcile."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("split_social_export", ROOT / "scripts" / "split_social_export.py")
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)


def tweet(row_id, uid, url=None, body="Fictional kite post."):
    return {"id": row_id, "platform": "Twitter", "post_text": body, "post": {"junkipedia_uid": uid},
            "urls": {"post_url": url or f"https://twitter.com/kites/status/{uid}"}}


def other(row_id, platform, uid):
    return {"id": row_id, "platform": platform, "post_text": "Fictional boat post.",
            "post": {"junkipedia_uid": uid}, "urls": {"post_url": f"https://example.org/{uid}"}}


def export(tmp_path, rows):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def shard_rows(out):
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(out.glob("*.shard-*.json"))}


def test_rows_of_one_post_land_in_one_shard_and_platforms_are_separate(tmp_path):
    rows = [tweet(str(n), str(1000 + n)) for n in range(40)]
    rows += [tweet("dup-a", "77", "https://twitter.com/Kites/status/77"),
             tweet("dup-b", "77", "https://x.com/kites/status/77/")]
    rows += [other("fb1", "Facebook", "123_456"), other("ig1", "Instagram", "AbC9")]
    manifest = split.split_export(export(tmp_path, rows), tmp_path / "out", shards=4)
    assert manifest["input_rows"] == manifest["rows_written"] == len(rows)
    shards = shard_rows(tmp_path / "out")
    holding = [name for name, items in shards.items() if {"dup-a", "dup-b"} & {r["id"] for r in items}]
    assert len(holding) == 1 and {"dup-a", "dup-b"} <= {r["id"] for r in shards[holding[0]]}
    assert all(".shard-" in name and name.split(".")[1] in {"twitter", "facebook", "instagram"} for name in shards)
    assert sorted(r["id"] for items in shards.values() for r in items) == sorted(r["id"] for r in rows)


def test_a_shard_over_the_limit_fails_and_asks_for_more_shards(tmp_path):
    rows = [tweet(str(n), str(2000 + n), body="x" * 200) for n in range(20)]
    with pytest.raises(ValueError, match="more --shards"):
        split.split_export(export(tmp_path, rows), tmp_path / "out", shards=1, limit=1000)
    assert json.loads((tmp_path / "out/manifest.json").read_text(encoding="utf-8"))["too_big"]


def test_body_with_line_separator_survives_the_split(tmp_path):
    rows = [tweet("1", "3001", body="Line one line two")]
    split.split_export(export(tmp_path, rows), tmp_path / "out", shards=2)
    [items] = shard_rows(tmp_path / "out").values()
    assert items[0]["post_text"] == "Line one line two"


@pytest.mark.parametrize("text", ['{"a": 1}', '[{"a": 1, "a": 2}]', '[{"a": NaN}]', '[{"a": 1}] [', '[1]'])
def test_malformed_or_ambiguous_exports_are_refused(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        split.split_export(path, tmp_path / "out", shards=2)


def test_existing_output_directory_is_not_reused(tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(FileExistsError):
        split.split_export(export(tmp_path, [tweet("1", "5")]), tmp_path / "out", shards=2)


def published_shards(out):
    return sorted(path.name for path in out.iterdir() if path.name != "manifest.json")


@pytest.mark.parametrize("tail", [', {"id": "bad"', ', {"id": "big", "n": 1e400}]'])
def test_a_failure_after_valid_rows_publishes_no_shard(tmp_path, tail):
    path = tmp_path / "export.json"
    good = json.dumps([tweet(str(n), str(4000 + n)) for n in range(5)], ensure_ascii=False)
    path.write_text(good[:-1] + tail, encoding="utf-8")
    with pytest.raises(ValueError):
        split.split_export(path, tmp_path / "out", shards=2)
    assert published_shards(tmp_path / "out") == []
    manifest = json.loads((tmp_path / "out/manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed_no_shards_published" and manifest["failure"]


def test_an_oversize_shard_publishes_no_shard(tmp_path):
    rows = [tweet(str(n), str(2000 + n), body="x" * 200) for n in range(20)]
    with pytest.raises(ValueError):
        split.split_export(export(tmp_path, rows), tmp_path / "out", shards=1, limit=1000)
    assert published_shards(tmp_path / "out") == []


def _fail(*args, **kwargs):
    raise OSError("injected failure")


def leftovers(tmp_path):
    return sorted(path.name for path in tmp_path.iterdir() if ".staging-" in path.name)


def test_a_failed_publish_rename_leaves_no_output_directory(tmp_path, monkeypatch):
    rows = [tweet(str(n), str(6000 + n)) for n in range(20)]
    source = export(tmp_path, rows)
    monkeypatch.setattr(split.os, "rename", _fail)
    with pytest.raises(OSError, match="injected"):
        split.split_export(source, tmp_path / "out", shards=4)
    assert not (tmp_path / "out").exists() and leftovers(tmp_path) == []


def test_a_failed_manifest_write_leaves_no_output_directory(tmp_path, monkeypatch):
    source = export(tmp_path, [tweet(str(n), str(6100 + n)) for n in range(20)])
    monkeypatch.setattr(split, "_write_manifest", _fail)
    with pytest.raises(OSError, match="injected"):
        split.split_export(source, tmp_path / "out", shards=4)
    assert not (tmp_path / "out").exists() and leftovers(tmp_path) == []


def test_a_write_error_on_a_later_shard_leaves_no_output_directory(tmp_path, monkeypatch):
    source = export(tmp_path, [tweet(str(n), str(6200 + n)) for n in range(20)])
    opened = []
    real_open = split.Path.open

    def open_twice(self, *args, **kwargs):
        if self.name.endswith(".json") and ".shard-" in self.name:
            opened.append(self.name)
            if len(opened) == 2:
                raise OSError("injected failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(split.Path, "open", open_twice)
    with pytest.raises(OSError, match="injected"):
        split.split_export(source, tmp_path / "out", shards=4)
    assert not (tmp_path / "out").exists() and leftovers(tmp_path) == []


def test_a_successful_split_leaves_no_staging_directory(tmp_path):
    split.split_export(export(tmp_path, [tweet("1", "6300")]), tmp_path / "out", shards=2)
    assert leftovers(tmp_path) == [] and (tmp_path / "out/manifest.json").exists()


def test_x_and_twitter_rows_of_one_post_share_a_shard(tmp_path):
    rows = [tweet("t", "88"), {**tweet("x", "88", "https://x.com/kites/status/88"), "platform": "X"}]
    split.split_export(export(tmp_path, rows), tmp_path / "out", shards=4)
    [items] = shard_rows(tmp_path / "out").values()
    assert {r["id"] for r in items} == {"t", "x"}
