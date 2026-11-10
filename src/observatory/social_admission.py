"""Prepare a reviewed company-post corpus without altering source rows or a DB.

A Twitter post is its supplied status URL; a Facebook or Instagram post is its
platform plus the supplied Junkipedia post uid (the 2026-11-06 export). Duplicate
observations are retained as source variants; disagreement never establishes a
company or text. A Facebook/Instagram post whose URL is shared with another uid
(possibly one post collected twice) is counted per uid but paused for retrieval.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .import_records import CanonicalRecord, jsonl_lines, load_records
from .models import Issue
from .quality import body_hash, social_text_blockers, valid_url
from .social_annotations import social_annotation_details
from .social_archive import (
    PLATFORMS,
    _invalid_constant,
    _original_url,
    _unique_object,
    platform_post_uid,
    platform_post_url,
)

SCHEME = "collected-company-posts-unique-url-v1"
_POST = re.compile(r"/([A-Za-z0-9_]+)/status/(\d+)/?")
# The client asked (2026-11-06 meeting) to filter cement companies out by the
# export's Carbon Majors commodity. "Coal, Cement" (Adani) also mines coal and stays.
OUT_OF_SCOPE_COMMODITIES = frozenset({"Cement"})
URL_UNIT = "platform_canonical_original_post_url"
UID_UNIT = "platform_source_post_uid"
COUNT_UNITS = frozenset({URL_UNIT, UID_UNIT})
IDENTITY_CONFLICTS_SCHEMA = "social-identity-conflicts-v1"
# Decision choices bound by admission (review data + event log). The 2026-10-06 Twitter-only
# choices still bind Twitter-only sources; Facebook/Instagram rows and any cement-company row
# need the 2026-11 decision record.
TWITTER_ONLY_CHOICES = {"D02": {"collected_posts", "collected_posts_all_platforms"},
                        "D03": {"unique_post", "unique_post_platform_uid"}}
ALL_PLATFORM_CHOICES = {"D02": {"collected_posts_all_platforms"}, "D03": {"unique_post_platform_uid"}}
COMMODITY_CHOICE = {"D09": {"exclude_cement_commodity"}}


def source_commodity(record):
    """The supplied parent_entity_info.commodity, or None when absent."""
    row = record.raw.get("source_row") if isinstance(record.raw, dict) else None
    info = row.get("parent_entity_info") if isinstance(row, dict) else None
    value = info.get("commodity") if isinstance(info, dict) else None
    return value if isinstance(value, str) else None


def file_sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def platform_name(platform):
    """The documented platform name ("X" counts as Twitter), or None."""
    if not isinstance(platform, str):
        return None
    return "Twitter" if platform.casefold() == "x" else PLATFORMS.get(platform.casefold())


def source_post_uid(record):
    """The supplied post.junkipedia_uid of a source record (model or dict), or None."""
    raw = record.get("raw") if isinstance(record, dict) else record.raw
    row = raw.get("source_row") if isinstance(raw, dict) else None
    post = row.get("post") if isinstance(row, dict) else None
    value = post.get("junkipedia_uid") if isinstance(post, dict) else None
    return value if isinstance(value, str) else None


def post_identity(platform, url, uid=None):
    """(identity key, canonical URL or None, count unit) of one supplied observation, or None.

    Twitter: the canonical status URL (unchanged since 2026-10-06, so record IDs are unchanged).
    Facebook/Instagram: platform + uid; the URL must be the platform's post URL but is not the
    identity, so the canonical URL is chosen per group (the displayed observation's URL).
    """
    name = platform_name(platform)
    if name == "Twitter":
        canonical = canonical_post_url(platform, url)
        return ("twitter\n" + canonical, canonical, URL_UNIT) if canonical else None
    if name in {"Facebook", "Instagram"}:
        uid = platform_post_uid(uid)
        if uid is None or not platform_post_url(name, url, uid):
            return None
        return (name.casefold() + "\n" + uid, None, UID_UNIT)
    return None


def identity_url(url):
    """A URL form for spotting one post under several uids: the host without www./web./m. and
    the path without a trailing slash. Path and query keep their case (uids are case-sensitive)."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    for prefix in ("www.", "web.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    return host + parsed.path.rstrip("/") + ("?" + parsed.query if parsed.query else "")


def shared_url_keys(entries):
    """{identity key: sorted shared URL forms} for keys whose URL also belongs to another key."""
    by_url = defaultdict(set)
    for key, url in entries:
        by_url[identity_url(url)].add(key)
    shared = defaultdict(set)
    for form, keys in by_url.items():
        if len(keys) > 1:
            for key in keys:
                shared[key].add(form)
    return {key: sorted(forms) for key, forms in shared.items()}


def export_uid_entry(row):
    """(identity key, post URL) of a supplied Facebook/Instagram export row with a valid post ID and
    URL, else None (Twitter/X rows and rows without a usable identity)."""
    post = row.get("post") if isinstance(row.get("post"), dict) else {}
    try:
        url = _original_url(row)
    except ValueError:
        return None
    identity = post_identity(row.get("platform"), url, post.get("junkipedia_uid"))
    return (identity[0], url) if identity and identity[2] == UID_UNIT else None


def verified_identity_conflicts(path):
    """The whole-export conflict list, checked against the shard files it lists.

    The shards must sit next to the list (the splitter's output directory), match their recorded
    SHA-256, be every shard file in that directory, and agree with its manifest.json; the shared-URL
    keys are then recomputed from the Facebook/Instagram rows of all shards and must equal the listed ones, so a
    list with entries removed (or added) is refused.
    """
    path = Path(path)
    listing = load_identity_conflicts(path)
    directory, names = path.parent, set(listing["shard_sha256"])
    if any(Path(name).name != name or ".shard-" not in name for name in names):
        raise ValueError("Invalid identity conflict list")
    present = {item.name for item in directory.glob("*.shard-*.json")}
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    if (present != names or set(manifest.get("files", {})) != names
            or manifest.get("input_sha256") != listing.get("export_sha256")
            or (manifest.get("identity_conflicts") or {}).get("sha256") != file_sha256(path)):
        raise ValueError("The identity conflict list does not match its split directory and manifest")
    entries = []
    for name in sorted(names):
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != listing["shard_sha256"][name]:
            raise ValueError("A shard listed in the identity conflict list is missing or changed")
        # Every shard is read whatever its name; each row's own platform decides (Twitter/X rows have
        # no post-ID identity).
        rows = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
        if not isinstance(rows, list):
            raise ValueError("A shard listed in the identity conflict list is not a JSON array")
        entries.extend(entry for row in rows if isinstance(row, dict)
                       and not (isinstance(row.get("platform"), str) and row["platform"].casefold() in {"twitter", "x"})
                       and (entry := export_uid_entry(row)))
    if dict(sorted(shared_url_keys(entries).items())) != listing["ambiguous"]:
        raise ValueError("The identity conflict list does not match its shards (entries removed or added)")
    return listing


def load_identity_conflicts(path):
    """The whole-export list written by scripts/split_social_export.py (shape only)."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    shards = data.get("shard_sha256") if isinstance(data, dict) else None
    ambiguous = data.get("ambiguous") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or data.get("schema_version") != IDENTITY_CONFLICTS_SCHEMA
            or not isinstance(shards, dict) or not shards
            or any(not isinstance(v, str) or len(v) != 64 for v in shards.values())
            or not isinstance(ambiguous, dict)
            or any(not isinstance(k, str) or not k.startswith(("facebook\n", "instagram\n"))
                   or not isinstance(v, list) or not v
                   or any(not isinstance(u, str) for u in v) for k, v in ambiguous.items())):
        raise ValueError("Invalid identity conflict list")
    return data


def canonical_post_url(platform, url):
    """Return a supplied URL's canonical identity, or None without guessing."""
    if not isinstance(platform, str) or platform.casefold() not in {"twitter", "x"}:
        return None
    if not isinstance(url, str) or url != url.strip() or not valid_url(url):
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    match = _POST.fullmatch(parsed.path)
    if (parsed.hostname not in {"twitter.com", "www.twitter.com", "x.com", "www.x.com"}
            or parsed.username or parsed.password or port not in {None, 80, 443}
            or parsed.query or parsed.fragment or not match):
        return None
    return f"https://twitter.com/{match[1].lower()}/status/{match[2]}"


def required_choices(platforms, any_out_of_scope_row):
    """Which confirmed decision choices an admission of these source rows needs."""
    required = dict(ALL_PLATFORM_CHOICES if set(platforms) - {"Twitter"} else TWITTER_ONLY_CHOICES)
    if any_out_of_scope_row:
        required.update(COMMODITY_CHOICE)
    return required


def _decision_binding(data_path, log_path, required=None):
    required = TWITTER_ONLY_CHOICES if required is None else required
    data_sha = file_sha256(data_path)
    data = json.loads(Path(data_path).read_text(encoding="utf-8-sig"))
    decisions = {item["id"]: item for item in data.get("decision_items", [])}
    latest = {}
    for line in jsonl_lines(Path(log_path).read_bytes().decode("utf-8-sig")):
        if line.strip():
            event = json.loads(line)
            if event.get("item_id") in required:
                latest[event["item_id"]] = event
    bound = {}
    for key, choices in sorted(required.items()):
        event, item = latest.get(key), decisions.get(key)
        choice = event.get("decision_choice") if event else None
        if (not event or not item or event.get("status") != "confirmed"
                or choice not in choices or event.get("source_data_sha256") != data_sha
                or choice not in {option["id"] for option in item["decision"]["options"]}):
            raise ValueError(f"Current, source-bound confirmed {key} selection is required "
                             f"(one of {sorted(choices)})")
        bound[key] = {name: event.get(name) for name in (
            "id", "item_id", "status", "decision_choice", "choice_label", "note",
            "source_data_sha256", "saved_at_utc", "revision", "reviewer_identity",
        )}
    return {"data_sha256": data_sha, "log_sha256": file_sha256(log_path), "selections": bound}


def _historical_signature(record):
    view = social_annotation_details({"dataset": "social", "body": record.body,
                                     "body_hash": body_hash(record.body), "annotations": record.annotations})
    return tuple((item["key"], item["state"]) for item in view["values"])


def _variant(record, source_sha, line):
    """Private preserved source plus a narrowly projected public view."""
    return {"source_record_id": record.record_id, "source_line": line,
            "source_sha256": source_sha, "source_record": record.model_dump(mode="json")}


def _public_url(value):
    if not valid_url(value) or value != value.strip():
        return ""
    parsed = urlsplit(value)
    return value if not parsed.username and not parsed.password else ""


def _admit_group(members, identity, source_sha, binding, shared_urls=()):
    """Admit one post. ``identity`` is a post_identity() triple, or (as before 2026-11) a Twitter
    canonical status URL."""
    # Stable choice is only an observation for display, never a resolution.
    if isinstance(identity, str):
        identity = ("twitter\n" + identity, identity, URL_UNIT)
    key, canonical, unit = identity
    ordered = sorted(members, key=lambda entry: entry[1].record_id)
    selected_line, selected = ordered[0]
    name = platform_name(selected.platform)
    if canonical is None:
        canonical = selected.url
    uid = key.split("\n", 1)[1] if unit == UID_UNIT else None
    payload = selected.model_dump(mode="json")
    fields = ("body", "sponsor", "account", "published_at", "platform")
    conflicts = [field for field in fields if len({getattr(record, field) for _, record in ordered}) > 1]
    signatures = {_historical_signature(record) for _, record in ordered}
    if len(signatures) > 1:
        conflicts.append("historical_labels")
    payload["record_id"] = "social-post:" + body_hash(key)
    payload["url"] = canonical
    payload["platform"] = name
    payload["title"] = f"{name} post · {uid if uid is not None else canonical.rsplit('/', 1)[-1]}"
    for field in ("sponsor", "account"):
        if field in conflicts:
            payload[field] = ""
    if "published_at" in conflicts:
        payload["published_at"] = None
    if "historical_labels" in conflicts or "body" in conflicts:
        payload["annotations"] = []
    # Excluded only when every observation names an out-of-scope commodity.
    commodities = {source_commodity(record) for _, record in ordered}
    out_of_scope = commodities <= OUT_OF_SCOPE_COMMODITIES
    # D09 (2026-11-09): a post whose observations name a cement company and another (or no)
    # commodity is kept and counted, with its company unknown.
    mixed_commodity = bool(commodities & OUT_OF_SCOPE_COMMODITIES) and not out_of_scope
    if mixed_commodity:
        payload["sponsor"] = ""
    blockers = social_text_blockers(selected.body)
    ambiguous = bool(shared_urls)
    retrievable = (bool(selected.body.strip()) and not blockers and "body" not in conflicts
                   and not out_of_scope and not ambiguous)
    payload["countable"] = not out_of_scope
    payload["retrievable"] = retrievable
    payload["retrieval_end"] = None
    payload["retrieval_ranges"] = None
    payload["issues"] = [issue for issue in payload["issues"] if issue["code"] != "social_admission_pending"]
    payload["issues"].append(Issue(
        code="social_collected_company_posts", severity="info",
        detail="User-approved collected company-post corpus; paid-ad status remains unknown. Counts use "
               + ("platform plus canonical original post URL." if unit == URL_UNIT
                  else "platform plus the supplied Junkipedia post ID."),
    ).model_dump())
    if conflicts:
        payload["issues"].append(Issue(
            code="social_source_variants_disagree", detail="Source observations disagree; affected public metadata is unknown, and differing bodies are excluded from retrieval.",
        ).model_dump())
    if mixed_commodity:
        payload["issues"].append(Issue(
            code="social_mixed_commodity_company_unknown", severity="info",
            detail="Source observations name a cement company and another company; the post is counted "
                   "and its company is unknown.",
        ).model_dump())
    if out_of_scope:
        payload["issues"].append(Issue(
            code="social_out_of_scope_commodity", severity="info",
            detail="The company's supplied commodity is outside the study scope; the post is kept but not counted or retrieved.",
        ).model_dump())
    if ambiguous:
        payload["issues"].append(Issue(
            code="social_identity_ambiguous",
            detail="Another post ID in the export has the same post URL, so this may be one post collected twice. "
                   "It is counted per post ID and paused for retrieval.",
        ).model_dump())
    payload["raw"]["admission_status"] = "user_confirmed_company_post_policy"
    payload["raw"]["social_admission"] = {
        "scheme": SCHEME, "scope": "collected_company_posts", "paid_ad_status": "unknown",
        "count_unit": unit, "canonical_url": canonical,
        # Twitter admissions keep their 2026-10 keys; only post-ID posts carry the identity details.
        **({"identity_basis": "platform_source_post_uid", "post_uid": uid, "identity_ambiguous": ambiguous}
           if unit == UID_UNIT else {}),
        **({"shared_urls": list(shared_urls)} if ambiguous else {}),
        **({"company_status": "unknown_mixed_commodity"} if mixed_commodity else {}),
        "member_count": len(ordered), "conflicting_fields": conflicts,
        "selected_source_record_id": selected.record_id, "selected_source_line": selected_line,
        "selection_basis": "lexicographically_first_source_id_for_display_only_not_adjudication",
        "source_sha256": source_sha, "review_data_sha256": binding["data_sha256"],
        "decision_event_ids": {key: item["id"] for key, item in binding["selections"].items()},
        "retrieval_status": "enabled_source_post_text_only" if retrievable else (
            "excluded_out_of_scope_commodity" if out_of_scope else
            "paused_identity_ambiguous" if ambiguous else
            "paused_body_disagreement" if "body" in conflicts else "paused_text_quality"),
        "scope_status": "out_of_scope_commodity" if out_of_scope else "in_scope",
        "source_commodities": sorted(value for value in commodities if value),
        "customer_acceptance": False,
    }
    # Duplicate records retain every complete observation, including old values
    # and reversible string encodings. Singletons already retain source_row.
    payload["raw"]["source_variants"] = [_variant(record, source_sha, line) for line, record in ordered]
    payload["provenance"].append({"role": "reviewed_company_post_unique_url_policy",
                                  "source_sha256": source_sha, "scheme": SCHEME,
                                  "review_data_sha256": binding["data_sha256"],
                                  **({"identity_conflicts_sha256": binding["identity_conflicts_sha256"]}
                                     if binding.get("identity_conflicts_sha256") else {})})
    return CanonicalRecord.model_validate_json(json.dumps(payload, ensure_ascii=False)), conflicts


def prepare_social_admission(source, *, review_data, reviews, out, identity_conflicts=None):
    """Write a new import-ready plan; zero DB/model/network operations.

    Invalid URLs remain in the byte-exact source snapshot and a separate
    quarantine file. They never receive an invented source identity.
    Facebook/Instagram rows need ``identity_conflicts``: the whole-export list of
    post IDs sharing a URL (scripts/split_social_export.py), bound to the shard
    files these rows were prepared from, so a pair split across shards is found.
    """
    source, review_data, reviews, out = map(Path, (source, review_data, reviews, out))
    if out.exists():
        raise ValueError("Admission output must be a new directory")
    inputs = [source, review_data, reviews] + ([Path(identity_conflicts)] if identity_conflicts else [])
    originals = {str(path.resolve()): file_sha256(path) for path in inputs}
    source_sha = originals[str(source.resolve())]
    groups, quarantined, seen = defaultdict(list), [], set()
    identities, platforms, any_out_of_scope, uid_urls, uid_shards = {}, set(), False, [], set()
    # CanonicalRecord permits a blank URL; quarantine preserves such rows while
    # valid output is subsequently checked by the ordinary import loader.
    for line_number, line in enumerate(jsonl_lines(source.read_bytes().decode("utf-8-sig")), 1):
        if not line.strip():
            continue
        record = CanonicalRecord.model_validate_json(line)
        if (record.record_id in seen or record.dataset != "social" or record.countable or record.retrievable
                or record.raw.get("body_sha256") != body_hash(record.body)):
            raise ValueError("Unique unadmitted, body-bound social source records are required")
        seen.add(record.record_id)
        any_out_of_scope |= source_commodity(record) in OUT_OF_SCOPE_COMMODITIES
        identity = post_identity(record.platform, record.url, source_post_uid(record))
        if identity is None:
            quarantined.append((line_number, record))
            continue
        platforms.add(platform_name(record.platform))
        if identity[2] == UID_UNIT:
            uid_urls.append((identity[0], record.url))
            prov = record.provenance[0] if record.provenance and isinstance(record.provenance[0], dict) else {}
            uid_shards.add(prov.get("json_sha256"))
        if identities.setdefault(identity[0], identity) != identity:
            raise ValueError("One post identity resolved to different canonical forms")
        groups[identity[0]].append((line_number, record))
    if not seen:
        raise ValueError("Source must contain social rows")
    binding = _decision_binding(review_data, reviews, required_choices(platforms, any_out_of_scope))
    shared = shared_url_keys(uid_urls)
    if uid_urls:
        if identity_conflicts is None:
            raise ValueError("Facebook/Instagram rows need the whole-export identity conflict list "
                             "(identity_conflicts.json from scripts/split_social_export.py)")
        listing = verified_identity_conflicts(identity_conflicts)
        if not uid_shards <= set(listing["shard_sha256"].values()):
            raise ValueError("Facebook/Instagram rows were not prepared from a shard of the listed export")
        for key, forms in listing["ambiguous"].items():
            shared[key] = sorted(set(shared.get(key, ())) | set(forms))
        binding["identity_conflicts_sha256"] = file_sha256(identity_conflicts)
    out.mkdir(parents=True)
    records_path = out / "records.jsonl"
    conflict_groups, count_conflicts, ambiguous_groups = [], Counter(), []
    source_members, unit_counts, platform_counts = {}, Counter(), Counter()
    countable, retrievable, out_of_scope = 0, 0, 0
    with records_path.open("x", encoding="utf-8", newline="\n") as stream:
        for key, members in sorted(groups.items()):
            record, conflicts = _admit_group(members, identities[key], source_sha, binding, shared.get(key, ()))
            stream.write(record.model_dump_json() + "\n")
            countable += int(record.countable)
            retrievable += int(record.retrievable)
            out_of_scope += record.raw["social_admission"]["scope_status"] != "in_scope"
            unit_counts[identities[key][2]] += 1
            platform_counts[record.platform] += 1
            source_members[record.record_id] = [item.record_id for _, item in members]
            if record.raw["social_admission"].get("identity_ambiguous") is True:
                ambiguous_groups.append({"record_id": record.record_id, "platform": record.platform,
                                         "post_uid": record.raw["social_admission"]["post_uid"],
                                         "shared_urls": record.raw["social_admission"]["shared_urls"]})
            if conflicts:
                count_conflicts.update(conflicts)
                conflict_groups.append({"record_id": record.record_id, "url": record.url,
                                        "conflicting_fields": conflicts,
                                        "source_record_ids": source_members[record.record_id]})
    with (out / "quarantined.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for line, record in quarantined:
            stream.write(json.dumps({"source_line": line, "reason": "No usable supplied post identity "
                                     "(Twitter status URL, or Facebook/Instagram post ID with its post URL)",
                                     "record": record.model_dump(mode="json")}, ensure_ascii=False) + "\n")
    # Byte preservation is independent from representative metadata decisions.
    (out / "source_records.original.jsonl").write_bytes(source.read_bytes())
    (out / "review_data.original.json").write_bytes(review_data.read_bytes())
    (out / "reviews.original.jsonl").write_bytes(reviews.read_bytes())
    if identity_conflicts:
        (out / "identity_conflicts.original.json").write_bytes(Path(identity_conflicts).read_bytes())
    (out / "members.json").write_text(json.dumps(source_members, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    valid = load_records(records_path, dataset="social") if groups else None
    if valid is not None and len(valid.records) != len(groups):
        raise ValueError("Canonical output validation did not reconcile all groups")
    if {str(path.resolve()): file_sha256(path) for path in inputs} != originals:
        raise ValueError("Source or review changed during preparation; do not import outputs")
    receipt = {
        "schema_version": SCHEME, "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_imported_or_published", "scope": "collected_company_posts_not_verified_paid_ads",
        "count_unit": "platform_canonical_original_post_url" if set(unit_counts) <= {URL_UNIT} else "per_platform",
        "count_units": dict(unit_counts), "platform_posts": dict(platform_counts), "source_records": len(seen),
        "unique_posts": len(groups), "quarantined_source_rows": len(quarantined),
        "duplicate_groups": sum(len(members) > 1 for members in groups.values()),
        "duplicate_rows": sum(len(members) for members in groups.values() if len(members) > 1),
        "countable_records": countable, "retrievable_records": retrievable,
        "out_of_scope_records": out_of_scope,
        "excluded_commodities": sorted(OUT_OF_SCOPE_COMMODITIES),
        "conflict_counts": dict(count_conflicts), "conflict_groups": conflict_groups,
        "identity_ambiguous_records": len(ambiguous_groups), "identity_ambiguous_groups": ambiguous_groups,
        "all_source_members_preserved": sum(map(len, source_members.values())) + len(quarantined) == len(seen),
        "originals": originals, "review_binding": binding,
        "canonical_sha256": file_sha256(records_path), "database_connections": 0, "model_calls": 0,
        "customer_acceptance": False, "local_application_import_executed": False,
        "rollback": "Remove only new canonical record IDs listed in members.json, retaining existing source/native rows; restore a verified pre-import backup if needed.",
    }
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def observation_matches(record, admission, platform):
    """Whether a preserved source observation (dict) belongs to the admitted post's identity.

    ``platform`` is the admitted post's platform: a Facebook and an Instagram observation that
    happen to share a uid are different posts.
    """
    identity = post_identity(record.get("platform"), record.get("url"), source_post_uid(record))
    if identity is None or identity[2] != admission.get("count_unit"):
        return False
    if identity[2] == URL_UNIT:
        return identity[1] == admission.get("canonical_url")
    name = platform_name(platform)
    return name is not None and identity[0] == name.casefold() + "\n" + str(admission.get("post_uid"))


def admitted_identity_ok(payload, admission):
    """The record ID, URL and platform agree with the admitted identity (both count units)."""
    unit, canonical = admission.get("count_unit"), admission.get("canonical_url")
    if unit == URL_UNIT:
        expected = canonical_post_url(payload.get("platform"), payload.get("url"))
        return (bool(expected) and expected == payload.get("url") == canonical
                and payload.get("record_id") == "social-post:" + body_hash("twitter\n" + expected))
    if unit == UID_UNIT:
        name, uid = platform_name(payload.get("platform")), platform_post_uid(admission.get("post_uid"))
        return (name in {"Facebook", "Instagram"} and uid is not None and payload.get("platform") == name
                and payload.get("url") == canonical and platform_post_url(name, canonical, uid)
                and payload.get("record_id") == "social-post:" + body_hash(name.casefold() + "\n" + uid))
    return False


def public_social_admission(value, *, current_body=None, current_url=None):
    """Project approved identity and exact observations; omit all private raw."""
    if not isinstance(value, dict):
        return None
    admission, variants = value.get("social_admission"), value.get("source_variants")
    if (not isinstance(admission, dict) or admission.get("scheme") != SCHEME
            or admission.get("scope") != "collected_company_posts"
            or admission.get("count_unit") not in COUNT_UNITS
            or not isinstance(variants, list) or not variants
            or admission.get("member_count") != len(variants)):
        return None
    unit = admission["count_unit"]
    platforms = {platform_name(entry["source_record"].get("platform")) for entry in variants
                 if isinstance(entry, dict) and isinstance(entry.get("source_record"), dict)}
    if len(platforms) != 1:
        return None
    platform = platforms.pop()
    public = []
    for entry in variants:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_record"), dict):
            return None
        record = entry["source_record"]
        if (record.get("dataset") != "social" or record.get("record_id") != entry.get("source_record_id")
                or not isinstance(record.get("body"), str)
                or not observation_matches(record, admission, platform)):
            return None
        body = record["body"]
        projection = social_annotation_details({"dataset": "social", "body": body,
                                                "body_hash": body_hash(body), "annotations": record.get("annotations", [])})
        public.append({"source_record_id": entry["source_record_id"],
                       "title": record.get("title", ""), "company": record.get("sponsor", ""),
                       "account": record.get("account", ""), "platform": record.get("platform", ""),
                       "published_at": record.get("published_at"), "body": body,
                       "url": _public_url(record.get("url", "")),
                       "archive_url": _public_url(record.get("archive_url", "")),
                       "historical_states": projection["values"], "body_sha256": body_hash(body)})
    selected = next((item for item in public if item["source_record_id"] == admission.get("selected_source_record_id")), None)
    if (selected is None or current_body is not None and selected["body"] != current_body
            or current_url is not None and current_url != admission.get("canonical_url")):
        return None
    return {"scope": "Collected company social posts", "paid_ad_status": "Unknown — not verified paid ads",
            "count_unit": ("One post per platform and canonical original post URL" if unit == URL_UNIT
                           else "One post per platform and Junkipedia post ID"),
            "member_count": len(public), "conflicting_fields": admission.get("conflicting_fields", []),
            "retrieval_status": admission.get("retrieval_status"), "variants": public,
            "selected_source_record_id": admission.get("selected_source_record_id"),
            "customer_acceptance": False}
