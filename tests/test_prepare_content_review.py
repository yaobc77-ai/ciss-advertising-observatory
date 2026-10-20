"""Preparation invariants; synthetic fixtures do not establish semantic quality."""

import csv
import importlib.util
import io
import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location("prepare_content_review", Path(__file__).parents[1] / "scripts/prepare_content_review.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def definitions():
    return {"status": "draft_requires_client_confirmation", "questions": [
        {"question_id": f"Q{i:02d}", "question_exact": f"Original question {i}",
         "query_question": f"Question {i}?", "source_ref": f"PD3-P{291+i}",
         "source_paragraph_exact": f"Original question {i}", "candidate_search_terms": ["CCS", "blue hydrogen"]}
        for i in range(1, 25)]}


def source(rid="one", body="A company proposes CCS. A critic disputes it.", **values):
    row = {"record_id": rid, "version_id": "version:" + rid, "dataset": "native", "body": body,
           "countable": True, "retrievable": True, "title": "Title", "url": "https://example.org/ad"}
    row.update(values)
    return row


def build(rows):
    questions = definitions()
    return review.build_files(review.normalize_records(rows), questions, review.encoded(questions), {"mode": "synthetic"})


def units(files):
    return list(csv.DictReader(io.StringIO(files["review_units.csv"].decode("utf-8-sig"))))


def test_every_selected_pair_is_unknown_even_without_any_hint():
    files = build([source(), source("unmatched", "No terms used."), source("empty", "", retrievable=False)])
    rows = units(files)
    assert len(rows) == 72
    assert {r["record_id"] for r in rows} == {"one", "unmatched", "empty"}
    assert all(r["membership"] == "unknown" and r["review_status"] == "unreviewed" for r in rows)
    assert all(not r["reviewer"] and not r["support_quote"] for r in rows)
    assert b"still awaiting full-context review" in files["questions/Q01.html"]
    summary = json.loads(files["preparation_summary.json"])
    assert summary["reviewed_units"] == 0 and summary["quality_scores"] is None
    assert summary["questions"][0]["records_with_literal_hints"] == 1
    assert summary["questions"][0]["complete_gold"] is False


def test_scope_uses_admission_and_activity_without_silent_alias_or_duplicate_merge():
    files = build([source("one"), source("same-body"), source("held", countable=False),
                   source("inactive", active=False), source("social", dataset="social")])
    assert {r["record_id"] for r in units(files)} == {"one", "same-body"}
    assert json.loads(files["source_snapshot.json"])["records"][2]["dataset"] == "native"
    groups = list(csv.DictReader(io.StringIO(files["article_groups.draft.csv"].decode("utf-8-sig"))))
    assert groups[0]["exact_body_group_hint"] == groups[1]["exact_body_group_hint"]
    assert all(r["near_duplicate_review"] == "pending" for r in groups)


def test_literal_hints_keep_unicode_offsets_context_and_word_boundaries():
    body = "中文💡—ccs — blue\n hydrogen; unrelated acronymXCCS."
    matches = review.hint_matches(body, ["CCS", "blue hydrogen"])
    assert len(matches) == 2
    for match in matches:
        assert body[match["start"]:match["end"]] == match["quote"]
        assert body[match["context_start"]:match["context_end"]] == match["context"]
    assert matches[1]["quote"] == "blue\n hydrogen"


def test_full_retained_body_and_quality_metadata_preserved_beyond_searchable_range():
    row = source(body="Trusted. Footer CCS.", retrieval_end=8, issues=[{"code": "body_truncated_suspected"}],
                 raw={"body_recovery": {"coverage": "partial"}})
    files = build([row])
    snapshot = json.loads(files["source_snapshot.json"])["records"][0]
    assert snapshot["body"] == row["body"]
    assert snapshot["retrieval_ranges"] == [[0, 8]]
    assert snapshot["payload"]["raw"]["body_recovery"]["coverage"] == "partial"
    assert snapshot["extraction_completeness"] == "not_verified_by_this_preparer"
    assert b"Footer CCS." in files["articles/" + review.article_name(snapshot)]
    # Hint evidence can occur outside the searchable body; it remains a reading
    # aid, not certified evidence or an automatic membership decision.
    assert units(files)[0]["membership"] == "unknown"


@pytest.mark.parametrize("change", [
    {"record_id": ""}, {"version_id": None}, {"body": None}, {"countable": "true"},
    {"retrievable": 1}, {"active": "false"}, {"dataset": "all"}, {"body_hash": "wrong"},
    {"retrieval_ranges": [[0, 900]]},
])
def test_invalid_identity_hash_flags_or_range_refused(change):
    with pytest.raises((ValueError, TypeError)):
        review.normalize_records([source(**change)])


def test_duplicate_source_ids_refused_instead_of_collapsed():
    with pytest.raises(ValueError, match="duplicate"):
        review.normalize_records([source(), source()])


@pytest.mark.parametrize("mutate", [
    lambda q: q.update(status="approved"),
    lambda q: q["questions"].pop(),
    lambda q: q["questions"][0].update(question_id="Q02"),
    lambda q: q["questions"][0].update(source_ref=""),
    lambda q: q["questions"][0].update(candidate_search_terms=[42]),
])
def test_missing_source_ambiguous_ids_or_approved_template_refused(mutate):
    questions = definitions()
    mutate(questions)
    with pytest.raises(ValueError):
        review.validate_questions(questions)


def test_html_escapes_source_content_and_disallows_unsafe_links_and_paths():
    row = source("../../outside", body="<script>alert('x')</script>", title="<img src=x onerror=x>",
                 url="javascript:alert('x')", archive_url="https://user:secret@example.org/ad")
    files = build([row])
    articles = [name for name in files if name.startswith("articles/")]
    assert len(articles) == 1 and ".." not in articles[0]
    page = files[articles[0]].decode("utf-8")
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<img src" not in page and "href='javascript:" not in page
    assert "href='https://user:" not in page
    assert "Content-Security-Policy" in page


def test_csv_source_formula_prefix_is_inert_and_snapshot_remains_exact():
    rows = [{"record_id": "=HYPERLINK()", "note": " @formula"}, {"record_id": "safe", "note": "ordinary"}]
    result = list(csv.DictReader(io.StringIO(review.csv_bytes(rows, ["record_id", "note"]).decode("utf-8-sig"))))
    assert result[0]["record_id"].startswith("'=") and result[0]["note"].startswith("' @")
    assert result[1] == rows[1]


def test_existing_destination_rejected_before_input_or_database(tmp_path, monkeypatch):
    acquire = MagicMock(side_effect=AssertionError("must not read database"))
    monkeypatch.setattr(review, "acquire_database", acquire)
    with pytest.raises(ValueError, match="already_exists"):
        review.prepare(None, Path("absent"), tmp_path, database=True)
    acquire.assert_not_called()


def test_offline_packet_manifest_binds_every_file_and_never_approves(tmp_path, monkeypatch):
    acquire = MagicMock(side_effect=AssertionError("offline must not read DB"))
    monkeypatch.setattr(review, "acquire_database", acquire)
    questions, sources, out = tmp_path / "q.json", tmp_path / "s.json", tmp_path / "out"
    questions.write_bytes(review.encoded(definitions()))
    sources.write_bytes(review.encoded([source()]))
    result = review.prepare(sources, questions, out)
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert result["review_units"] == 24 and result["reviewed_units"] == 0
    assert manifest["customer_approved"] is False and manifest["semantic_gold"] is False
    for name, fingerprint in manifest["input_sha256"].items():
        assert review.digest((out / name).read_bytes()) == fingerprint
    acquire.assert_not_called()


def test_cli_failure_never_prints_driver_secrets(tmp_path, monkeypatch, capsys):
    q = tmp_path / "q.json"
    q.write_bytes(review.encoded(definitions()))
    monkeypatch.setattr(review, "acquire_database", MagicMock(side_effect=RuntimeError("password=private")))
    assert review.main(["--database", "--questions", str(q), "--output", str(tmp_path / "out")]) == 2
    assert "private" not in capsys.readouterr().out


def test_empty_body_does_not_suggest_shared_duplicate_group():
    groups = list(csv.DictReader(io.StringIO(build([source("one", ""), source("two", "")])["article_groups.draft.csv"].decode("utf-8-sig"))))
    assert groups[0]["exact_body_group_hint"] != groups[1]["exact_body_group_hint"]


def test_questions_and_source_objects_are_not_modified():
    rows, questions = [source()], definitions()
    before = deepcopy((rows, questions))
    review.build_files(review.normalize_records(rows), questions, review.encoded(questions), {})
    assert (rows, questions) == before


def test_database_capture_requires_payload_version_and_body_ownership():
    payload = source()
    payload.pop("version_id")
    row = {"record_id": payload["record_id"], "dataset": payload["dataset"],
           "version_id": review.canonical_digest(payload), "body": payload["body"], "payload": payload}
    records = review.normalize_records([row])
    review.validate_database_identities(records)
    changed = deepcopy(records)
    changed[0]["payload"]["publisher"] = "changed in place"
    with pytest.raises(ValueError, match="payload_version"):
        review.validate_database_identities(changed)
    changed = deepcopy(records)
    changed[0]["body"] = "changed body"
    with pytest.raises(ValueError, match="payload_version"):
        review.validate_database_identities(changed)


@pytest.mark.parametrize("field,value", [("record_id", "wrong"), ("dataset", "social")])
def test_canonical_payload_hash_does_not_override_record_ownership(field, value):
    payload = source()
    payload.pop("version_id")
    payload[field] = value
    row = {"record_id": "one", "dataset": "native", "body": payload["body"], "payload": payload,
           "version_id": review.canonical_digest(payload)}
    with pytest.raises(ValueError, match="identity_mismatch"):
        review.validate_database_identities(review.normalize_records([row]))
