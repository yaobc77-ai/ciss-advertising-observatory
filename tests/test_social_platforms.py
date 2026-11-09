"""Facebook and Instagram posts from the 2026-11-06 export shape: identity, ambiguity across shards,
decision binding, retrieval checks and the public projection (fictional rows, no database, no API)."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from observatory.quality import body_hash
from observatory.social_admission import (
    UID_UNIT,
    URL_UNIT,
    file_sha256,
    identity_url,
    post_identity,
    prepare_social_admission,
    public_social_admission,
    shared_url_keys,
)
from observatory.social_archive import (
    SOCIAL_LABELS,
    platform_post_url,
    prepare_social_archive,
)
from observatory.social_source_retrieval import validated_observations

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("split_social_export_platforms", ROOT / "scripts" / "split_social_export.py")
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)

ALL_PLATFORMS = {"D02": "collected_posts_all_platforms", "D03": "unique_post_platform_uid",
                 "D09": "exclude_cement_commodity"}
TWITTER_ONLY = {"D02": "collected_posts", "D03": "unique_post", "D09": "exclude_cement_commodity"}


def row(source_id, platform, uid, url, body="Fictional harbour festival post.", commodity="Fictional oil"):
    return {
        "id": source_id, "channel_id": "42", "platform": platform, "post_text": body,
        "channel": {"name": "Harbour Example Co", "username": "harbour"},
        "parent_entity": "Harbour Example Parent", "parent_entity_info": {"commodity": commodity},
        "date_time": {"published_at": "2024-03-04T05:06:07Z"},
        "urls": {"post_url": [url]}, "post": {"junkipedia_uid": uid},
        **{label: label == "green_binary" for label in SOCIAL_LABELS},
    }


def fb(source_id, uid, url=None, **kwargs):
    return row(source_id, "Facebook", uid, url or f"https://www.facebook.com/harbour/posts/{uid}", **kwargs)


def ig(source_id, uid, url=None, **kwargs):
    return row(source_id, "Instagram", uid, url or f"https://www.instagram.com/p/{uid}/", **kwargs)


def tweet(source_id, uid, **kwargs):
    return row(source_id, "Twitter", uid, f"https://twitter.com/harbour/status/{uid}", **kwargs)


def decisions(tmp_path, choices):
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"decision_items": [
        {"id": key, "decision": {"options": [{"id": value} for value in sorted(set(ALL_PLATFORMS.values())
                                                                              | set(TWITTER_ONLY.values()))]}}
        for key in ("D02", "D03", "D09")]}), encoding="utf-8")
    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text("".join(json.dumps({"id": key + "-event", "item_id": key, "status": "confirmed",
                                           "decision_choice": choice, "source_data_sha256": file_sha256(data)}) + "\n"
                               for key, choice in choices.items()), encoding="utf-8")
    return data, reviews


def split_and_prepare(tmp_path, rows, shards=2, export_name="export.json"):
    """Split the export, then prepare every shard's source records; return (split dir, {shard: records.jsonl})."""
    export = tmp_path / export_name
    export.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "split"
    split.split_export(export, out, shards)
    prepared = {}
    for shard in sorted(out.glob("*.shard-*.json")):
        target = tmp_path / "prepared" / shard.stem
        prepare_social_archive(shard, out=target / "records.jsonl", report=target / "audit.json")
        prepared[shard.name] = target / "records.jsonl"
    return out, prepared


def admit(tmp_path, source, choices=ALL_PLATFORMS, conflicts=None, name="admitted"):
    data, reviews = decisions(tmp_path, choices)
    out = tmp_path / name
    receipt = prepare_social_admission(source, review_data=data, reviews=reviews, out=out, identity_conflicts=conflicts)
    rows = [json.loads(line) for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    return receipt, rows


def admit_all(tmp_path, rows, shards=2, choices=ALL_PLATFORMS):
    out, prepared = split_and_prepare(tmp_path, rows, shards)
    results = {}
    for index, (shard, source) in enumerate(prepared.items()):
        results[shard] = admit(tmp_path, source, choices, out / "identity_conflicts.json", name=f"admitted-{index}")
    return out, results


def uid_in_bucket(prefix, bucket, shards=2, platform="facebook"):
    """A fictional uid whose post lands in the given shard bucket."""
    for n in range(1000):
        uid = f"{prefix}{n}"
        if int(hashlib.sha256(f"{platform}\n{uid}".encode()).hexdigest(), 16) % shards == bucket:
            return uid
    raise AssertionError("no uid found")


# --- URL and identity rules ------------------------------------------------------------------

@pytest.mark.parametrize("url, ok", [
    ("https://www.facebook.com/harbour/posts/1", True),
    ("https://m.facebook.com/story.php?story_fbid=1&id=2", True),
    ("https://web.facebook.com/1", True),
    ("https://facebook.example.org/1", False),
    ("https://user@www.facebook.com/1", False),
    ("https://www.facebook.com/1#frag", False),
    ("https://www.facebook.com:8443/1", False),
    (" https://www.facebook.com/1", False),
])
def test_facebook_post_url_must_be_a_plain_facebook_url(url, ok):
    assert platform_post_url("Facebook", url, "1") is ok


@pytest.mark.parametrize("url, ok", [
    ("https://www.instagram.com/p/AbC9/", True),
    ("https://instagram.com/reel/AbC9", True),
    ("https://www.instagram.com/p/abc9/", False),
    ("https://www.instagram.com/p/AbC9/?igsh=x", False),
    ("https://www.instagram.com/harbour/", False),
])
def test_instagram_post_url_path_must_carry_the_same_case_sensitive_uid(url, ok):
    assert platform_post_url("Instagram", url, "AbC9") is ok


def test_identity_is_platform_plus_uid_and_uids_are_case_sensitive():
    upper = post_identity("Instagram", "https://www.instagram.com/p/AbC9/", "AbC9")
    lower = post_identity("Instagram", "https://www.instagram.com/p/abc9/", "abc9")
    assert upper == ("instagram\nAbC9", None, UID_UNIT) and lower[0] == "instagram\nabc9"
    assert post_identity("facebook", "https://www.facebook.com/x/posts/5", "5")[0] == "facebook\n5"
    assert post_identity("X", "https://x.com/harbour/status/7", None)[2] == URL_UNIT
    assert post_identity("Facebook", "https://example.org/5", "5") is None
    assert post_identity("Facebook", "https://www.facebook.com/5", "5 6") is None


def test_shared_url_forms_ignore_host_prefix_and_trailing_slash_but_keep_case():
    assert identity_url("https://m.facebook.com/Harbour/posts/1/") == "facebook.com/Harbour/posts/1"
    assert identity_url("https://www.facebook.com/story.php?id=2") == "facebook.com/story.php?id=2"
    entries = [("facebook\n1", "https://www.facebook.com/a/1"), ("facebook\n2", "https://m.facebook.com/a/1/"),
               ("facebook\n3", "https://www.facebook.com/A/1"), ("facebook\n1", "https://www.facebook.com/a/1")]
    assert shared_url_keys(entries) == {"facebook\n1": ["facebook.com/a/1"], "facebook\n2": ["facebook.com/a/1"]}


# --- Admission ---------------------------------------------------------------------------------

def test_rows_of_one_facebook_uid_count_once_with_every_observation(tmp_path):
    rows = [fb("201", "555_1"), fb("202", "555_1", "https://m.facebook.com/story.php?story_fbid=1&id=555"),
            ig("203", "Qx7"), ig("204", "qx7"), tweet("205", "9001")]
    _, results = admit_all(tmp_path, rows, shards=1)
    receipts = list(results.values())
    by_platform = {}
    for receipt, admitted in receipts:
        assert receipt["status"] == "prepared_not_imported_or_published"
        for item in admitted:
            by_platform.setdefault(item["platform"], []).append(item)
    [post] = by_platform["Facebook"]
    admission = post["raw"]["social_admission"]
    assert post["record_id"] == "social-post:" + body_hash("facebook\n555_1")
    assert admission["count_unit"] == UID_UNIT and admission["post_uid"] == "555_1"
    assert admission["member_count"] == 2 and admission["identity_ambiguous"] is False
    assert post["countable"] is True and post["retrievable"] is True
    assert sorted(item["raw"]["social_admission"]["post_uid"] for item in by_platform["Instagram"]) == ["Qx7", "qx7"]
    assert by_platform["Twitter"][0]["raw"]["social_admission"]["count_unit"] == URL_UNIT
    facebook_receipt = next(r for r, items in receipts if any(i["platform"] == "Facebook" for i in items))
    assert facebook_receipt["count_units"][UID_UNIT] >= 1 and facebook_receipt["count_unit"] == "per_platform"


def test_two_uids_sharing_a_url_in_different_shards_are_both_paused(tmp_path):
    first, second = uid_in_bucket("11_", 0), uid_in_bucket("22_", 1)
    url = "https://www.facebook.com/harbour/videos/77"
    rows = [fb("301", first, url), fb("302", second, "https://m.facebook.com/harbour/videos/77/"), fb("303", "33_1")]
    out, results = admit_all(tmp_path, rows, shards=2)
    listing = json.loads((out / "identity_conflicts.json").read_text(encoding="utf-8"))
    assert set(listing["ambiguous"]) == {f"facebook\n{first}", f"facebook\n{second}"}
    posts = {item["raw"]["social_admission"]["post_uid"]: item for _, admitted in results.values() for item in admitted}
    shards_holding = {shard for shard, (_, admitted) in results.items()
                      if {first, second} & {i["raw"]["social_admission"]["post_uid"] for i in admitted}}
    assert len(shards_holding) == 2
    for uid in (first, second):
        post = posts[uid]
        assert post["countable"] is True and post["retrievable"] is False
        assert post["raw"]["social_admission"]["retrieval_status"] == "paused_identity_ambiguous"
        assert post["raw"]["social_admission"]["shared_urls"] == ["facebook.com/harbour/videos/77"]
    assert posts["33_1"]["retrievable"] is True and posts["33_1"]["raw"]["social_admission"]["identity_ambiguous"] is False
    receipts = [receipt for receipt, _ in results.values()]
    assert sum(r["identity_ambiguous_records"] for r in receipts) == 2
    assert {r["review_binding"]["identity_conflicts_sha256"] for r in receipts} == {
        file_sha256(out / "identity_conflicts.json")}


def test_splitter_binds_the_conflict_list_to_the_export_and_every_shard(tmp_path):
    rows = [fb("401", "1_1"), ig("402", "Ab1"), tweet("403", "9002")]
    export = tmp_path / "export.json"
    export.write_text(json.dumps(rows), encoding="utf-8")
    manifest = split.split_export(export, tmp_path / "out", 2)
    listing = json.loads((tmp_path / "out/identity_conflicts.json").read_text(encoding="utf-8"))
    assert listing["schema_version"] == "social-identity-conflicts-v1" and listing["ambiguous"] == {}
    assert listing["export_sha256"] == manifest["input_sha256"] == file_sha256(export)
    assert listing["shard_sha256"] == {name: file_sha256(tmp_path / "out" / name) for name in manifest["files"]}
    assert manifest["identity_conflicts"]["sha256"] == file_sha256(tmp_path / "out/identity_conflicts.json")
    assert manifest["identity_conflicts"]["post_id_rows"] == 2


def test_facebook_rows_need_the_conflict_list_from_their_own_export(tmp_path):
    out, prepared = split_and_prepare(tmp_path, [fb("501", "5_5")], shards=1)
    [source] = prepared.values()
    with pytest.raises(ValueError, match="identity conflict list"):
        admit(tmp_path, source)
    other = tmp_path / "other"
    other.mkdir()
    split.split_export(_export(other, [fb("502", "6_6")]), other / "split", 1)
    with pytest.raises(ValueError, match="not prepared from a shard"):
        admit(tmp_path, source, conflicts=other / "split/identity_conflicts.json", name="again")
    assert not (tmp_path / "admitted").exists() and not (tmp_path / "again").exists()


def _export(directory, rows):
    path = directory / "export.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_facebook_rows_need_the_all_platform_decisions(tmp_path):
    out, prepared = split_and_prepare(tmp_path, [fb("601", "7_7")], shards=1)
    [source] = prepared.values()
    with pytest.raises(ValueError, match="D02"):
        admit(tmp_path, source, TWITTER_ONLY, out / "identity_conflicts.json")
    receipt, _ = admit(tmp_path, source, ALL_PLATFORMS, out / "identity_conflicts.json", name="ok")
    selections = receipt["review_binding"]["selections"]
    assert {key: item["decision_choice"] for key, item in selections.items()} == {
        "D02": "collected_posts_all_platforms", "D03": "unique_post_platform_uid"}


def test_one_cement_row_in_a_mixed_post_still_requires_the_cement_decision(tmp_path):
    rows = [tweet("701", "9100", commodity="Cement"), tweet("702", "9100", commodity="Fictional oil")]
    out, prepared = split_and_prepare(tmp_path, rows, shards=1)
    [source] = prepared.values()
    with pytest.raises(ValueError, match="D09"):
        admit(tmp_path, source, {"D02": "collected_posts", "D03": "unique_post"})
    receipt, [post] = admit(tmp_path, source, TWITTER_ONLY, name="ok")
    assert post["countable"] is True and receipt["out_of_scope_records"] == 0
    # Both rows name the same company, yet the D09 rule makes a mixed post's company unknown.
    assert post["sponsor"] == "" and post["raw"]["social_admission"]["company_status"] == "unknown_mixed_commodity"
    assert "social_mixed_commodity_company_unknown" in {issue["code"] for issue in post["issues"]}


def test_a_post_without_cement_keeps_its_company(tmp_path):
    out, prepared = split_and_prepare(tmp_path, [tweet("711", "9101"), tweet("712", "9101")], shards=1)
    [source] = prepared.values()
    _, [post] = admit(tmp_path, source, TWITTER_ONLY)
    assert post["sponsor"] == "Harbour Example Parent" and "company_status" not in post["raw"]["social_admission"]


def cross_shard_listing(tmp_path, export_name="export.json"):
    first, second = uid_in_bucket("11_", 0), uid_in_bucket("22_", 1)
    rows = [fb("961", first, "https://www.facebook.com/harbour/videos/78"),
            fb("962", second, "https://m.facebook.com/harbour/videos/78/"), fb("963", "96_3")]
    out, prepared = split_and_prepare(tmp_path, rows, shards=2, export_name=export_name)
    return out, prepared, out / "identity_conflicts.json"


def test_an_export_name_that_looks_like_a_twitter_shard_does_not_hide_facebook_rows(tmp_path):
    out, prepared, listing = cross_shard_listing(tmp_path, "client.twitter.shard-copy.json")
    assert all(".facebook.shard-" in name for name in prepared)
    receipt, _ = admit(tmp_path, next(iter(prepared.values())), conflicts=listing)
    assert receipt["identity_ambiguous_records"] == 1


def test_a_renamed_facebook_shard_cannot_hide_removed_conflicts(tmp_path):
    out, prepared, listing_path = cross_shard_listing(tmp_path)
    old = sorted(out.glob("*.facebook.shard-*.json"))[1]
    new = old.with_name(old.name.replace(".facebook.shard-", ".twitter.shard-"))
    old.rename(new)
    listing = json.loads(listing_path.read_text(encoding="utf-8"))
    listing["shard_sha256"][new.name] = listing["shard_sha256"].pop(old.name)
    listing["ambiguous"] = {}
    listing_path.write_text(json.dumps(listing), encoding="utf-8")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][new.name] = manifest["files"].pop(old.name)
    manifest["identity_conflicts"]["sha256"] = file_sha256(listing_path)
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match its shards"):
        admit(tmp_path, prepared[sorted(prepared)[0]], conflicts=listing_path)


def rewrite_listing(path, change):
    listing = json.loads(path.read_text(encoding="utf-8"))
    change(listing)
    path.write_text(json.dumps(listing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    manifest["identity_conflicts"]["sha256"] = file_sha256(path)  # a consistent forgery
    (path.parent / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("change", [
    lambda listing: listing.update(ambiguous={}),
    lambda listing: listing["ambiguous"].pop(sorted(listing["ambiguous"])[0]),
    lambda listing: listing["ambiguous"].update({"facebook\n96_3": ["facebook.com/harbour/posts/96_3"]}),
])
def test_a_conflict_list_with_entries_removed_or_added_is_refused(tmp_path, change):
    out, prepared, listing = cross_shard_listing(tmp_path)
    rewrite_listing(listing, change)
    source = next(iter(prepared.values()))
    with pytest.raises(ValueError, match="does not match its shards"):
        admit(tmp_path, source, conflicts=listing)


@pytest.mark.parametrize("damage", ["shard", "extra_shard", "manifest"])
def test_a_conflict_list_whose_directory_changed_is_refused(tmp_path, damage):
    out, prepared, listing = cross_shard_listing(tmp_path)
    shard = sorted(out.glob("*.shard-*.json"))[0]
    if damage == "shard":
        shard.write_text(shard.read_text(encoding="utf-8").replace("Fictional", "Fictitious"), encoding="utf-8")
    elif damage == "extra_shard":
        (out / "export.facebook.shard-09-of-09.json").write_text("[]", encoding="utf-8")
    else:
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        manifest["identity_conflicts"]["sha256"] = "0" * 64
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    source = next(iter(prepared.values()))
    with pytest.raises(ValueError, match="missing or changed|split directory"):
        admit(tmp_path, source, conflicts=listing)


# --- Retrieval checks and public projection ----------------------------------------------------

def facebook_post(tmp_path):
    rows = [fb("801", "8_8"), fb("802", "8_8", "https://m.facebook.com/harbour/posts/8")]
    out, prepared = split_and_prepare(tmp_path, rows, shards=1)
    [source] = prepared.values()
    _, [post] = admit(tmp_path, source, conflicts=out / "identity_conflicts.json")
    return post


def test_validated_observations_accept_a_facebook_post(tmp_path):
    post = facebook_post(tmp_path)
    observations = validated_observations(post)
    assert len(observations) == 2 and {o["url"] for o in observations} == {post["url"]}


@pytest.mark.parametrize("tamper", ["platform", "uid", "record_id", "observation_platform", "observation_uid"])
def test_validated_observations_refuse_a_changed_facebook_identity(tmp_path, tamper):
    post = deepcopy(facebook_post(tmp_path))
    first = post["raw"]["source_variants"][0]["source_record"]
    if tamper == "platform":
        post["platform"] = "Instagram"
    elif tamper == "uid":
        post["raw"]["social_admission"]["post_uid"] = "9_9"
    elif tamper == "record_id":
        post["record_id"] = "social-post:" + body_hash("facebook\n9_9")
    elif tamper == "observation_platform":
        first["platform"] = "Instagram"
    else:
        first["raw"]["source_row"]["post"]["junkipedia_uid"] = "9_9"
    with pytest.raises(ValueError):
        validated_observations(post)


def test_public_projection_names_the_post_id_unit_and_refuses_mixed_platforms(tmp_path):
    post = facebook_post(tmp_path)
    public = public_social_admission(post["raw"], current_body=post["body"], current_url=post["url"])
    assert public["count_unit"] == "One post per platform and Junkipedia post ID" and public["member_count"] == 2
    mixed = deepcopy(post["raw"])
    mixed["source_variants"][1]["source_record"]["platform"] = "Instagram"
    assert public_social_admission(mixed) is None


# --- Count-unit consumers ----------------------------------------------------------------------

@pytest.mark.parametrize("unit", [URL_UNIT, UID_UNIT, "source_record"])
def test_statistics_accept_both_post_units(unit):
    from observatory.intent_execution import _collections

    assert _collections([{"dataset": "social", "total": 3, "count_unit": unit}], "social") == {"social"}
    with pytest.raises(ValueError, match="count unit"):
        _collections([{"dataset": "social", "total": 3, "count_unit": "invented_unit"}], "social")


@pytest.mark.parametrize("status", ["paused_identity_ambiguous", "excluded_out_of_scope_commodity"])
def test_record_tool_shows_the_post_id_unit_and_the_new_paused_statuses(status):
    from test_research_tools import social_catalog

    catalog, _, row = social_catalog()
    row["retrievable"] = False
    row["social_admission"] = {
        "scheme": "collected-company-posts-unique-url-v1", "scope": "collected_company_posts",
        "count_unit": UID_UNIT, "paid_ad_status": "unknown", "member_count": 1, "conflicting_fields": [],
        "retrieval_status": status}
    result = catalog.call("get_record", {"record_id": row["record_id"]})
    assert result["record"]["social_admission"]["count_unit"] == UID_UNIT
    assert result["record"]["social_admission"]["retrieval_status"] == status


def test_twitter_admissions_keep_their_earlier_keys(tmp_path):
    _, results = admit_all(tmp_path, [tweet("901", "9300"), fb("902", "93_1")], shards=1)
    twitter = [item for _, admitted in results.values() for item in admitted if item["platform"] == "Twitter"]
    admission = twitter[0]["raw"]["social_admission"]
    assert not {"identity_basis", "post_uid", "identity_ambiguous", "shared_urls"} & set(admission)
    assert twitter[0]["title"] == "Twitter post · 9300"


def test_a_conflict_list_naming_a_twitter_post_is_refused(tmp_path):
    out, prepared = split_and_prepare(tmp_path, [fb("951", "95_1")], shards=1)
    listing = json.loads((out / "identity_conflicts.json").read_text(encoding="utf-8"))
    listing["ambiguous"] = {"twitter\nhttps://twitter.com/harbour/status/1": ["twitter.com/harbour/status/1"]}
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(listing), encoding="utf-8")
    [source] = prepared.values()
    with pytest.raises(ValueError, match="Invalid identity conflict list"):
        admit(tmp_path, source, conflicts=forged)
