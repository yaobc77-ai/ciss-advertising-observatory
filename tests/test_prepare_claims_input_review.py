"""Synthetic source-lineage invariants; these tests do not approve real CLAIMS."""

import csv
import importlib.util
import io
import json
import stat
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook

SPEC = importlib.util.spec_from_file_location(
    "prepare_claims_input_review", Path(__file__).parents[1] / "scripts/prepare_claims_input_review.py"
)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)

HEADERS = ["id", "url", "publisher", "title", "sponsor", "notes", "date"]
PARAGRAPH = 'Company says its “clean” energy project could reduce emissions while remaining a proposed project.'
OTHER = "Another article describes its community program and preserves a different source identity."


def workbook_bytes(rows=None, *, headers=None, sheet_name="Sheet1", extra_sheet=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(HEADERS if headers is None else headers)
    for row in rows or []:
        sheet.append(row)
    if extra_sheet:
        workbook.create_sheet("Other")
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def metadata_rows():
    return [
        [0, "https://example.org/original", "Original Outlet", "Original title", "Company", "", datetime(2020, 1, 2)],
        [1, "https://example.org/other", "Other Outlet", "Other title", "Other company", "", None],
    ]


def source_zip(workbook, sources=None, *, extras=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(review.WORKBOOK_MEMBER, workbook)
        for name, raw in (sources or {}).items():
            archive.writestr(review.TEXT_PREFIX + name, raw)
        for name, raw in extras or []:
            archive.writestr(name, raw)
    return stream.getvalue()


def csv_data(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def notebook_bytes(source=None):
    if source is None:
        source = [
            "MIN_PARAGRAPH_LENGTH = 10\n",
            "MIN_WORD_COUNT = 3\n",
            # Two actual backslashes are intentional historical data. Correcting
            # them would change what the original cleaning program selected.
            r"JUNK_PATTERNS = [r'^literal\\s+$']" + "\n",
        ]
    return review.encoded({"cells": [{"cell_type": "code", "source": source}]})


def current_snapshot(*, dataset="native", active=True, url="https://example.org/original"):
    payload = {
        "record_id": "current-record", "dataset": dataset, "url": url, "title": "Current title",
        "publisher": "Current outlet", "sponsor": "Current sponsor", "body": "Different saved current body.",
        "countable": False, "retrievable": False,
    }
    row = {
        "record_id": payload["record_id"], "dataset": dataset, "active": active, "payload": payload,
        "body": payload["body"], "body_sha256": review.digest(payload["body"].encode("utf-8")),
        "version_id": review.canonical_digest(payload),
    }
    return {"records": [row], "observation": {"synthetic": True}}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    raw = (PARAGRAPH + "\r\n\r\n" + PARAGRAPH + "\r\n\r\nFooter\r\n").encode("utf-8")
    canonical = review.historical_cleaning(PARAGRAPH, {
        "MIN_PARAGRAPH_LENGTH": 10, "MIN_WORD_COUNT": 3, "JUNK_PATTERNS": [r"^literal\\s+$"],
    })[1][0]
    files = {
        "manual_zip": tmp_path / "manual.zip", "input_csv": tmp_path / "sampled.csv",
        "cleaned_csv": tmp_path / "cleaned.csv", "notebook": tmp_path / "clean.ipynb",
        "current_snapshot": tmp_path / "snapshot.json",
    }
    files["manual_zip"].write_bytes(source_zip(
        workbook_bytes(metadata_rows()), {"0.txt": raw, "1.txt": (OTHER + "\r\n").encode("utf-8")},
        extras=[("New/unselected.xlsx", workbook_bytes()), ("upstream.py", b"raise RuntimeError('must not run')")],
    ))
    files["input_csv"].write_bytes(csv_data(["id", "article_id", "text"], [["1", "0", canonical], ["2", "0", canonical]]))
    files["cleaned_csv"].write_bytes(csv_data(["id", "text"], [["0", canonical], ["0", canonical], ["1", OTHER]]))
    files["notebook"].write_bytes(notebook_bytes())
    files["current_snapshot"].write_bytes(review.encoded(current_snapshot()))
    monkeypatch.setattr(review, "UPSTREAM_NOTEBOOK_SHA256", review.digest(files["notebook"].read_bytes()))
    return SimpleNamespace(**files, raw=raw, canonical=canonical, output=tmp_path / "packet")


def prepare(item, **kwargs):
    return review.write_packet(item.manual_zip, item.input_csv, item.cleaned_csv, item.notebook,
                               item.output, current_snapshot=item.current_snapshot, **kwargs)


def test_real_packet_path_preserves_raw_bytes_crlf_and_every_repeated_location(inputs):
    summary = prepare(inputs)
    assert summary["source_articles"] == 2
    assert summary["metadata_records"] == 2
    assert summary["selected_article_groups"] == 1
    assert summary["selected_input_paragraphs"] == 2
    assert summary["selected_ordered_groups"] == 1
    assert summary["cleaned_sequences_reproduced"] == 2
    assert (inputs.output / "original/0.txt").read_bytes() == inputs.raw
    assert b"\r\n" in (inputs.output / "original/0.txt").read_bytes()
    rows = json.loads((inputs.output / "article_lineage.json").read_bytes())
    assert [p["input_id"] for p in rows[0]["paragraphs"]] == ["1", "2"]
    body = inputs.raw.decode("utf-8")
    for paragraph in rows[0]["paragraphs"]:
        spans = paragraph["locations"]
        assert len(spans) == 2
        assert spans[0]["start"] == 0
        assert spans[1]["start"] > spans[0]["end"]
        assert all(s["lossy"] for s in spans)
        for span in spans:
            assert body[span["start"]:span["end"]] == span["quote"]
            assert span["quote"] == PARAGRAPH
            assert "Footer" in span["context_after"]


def test_filename_id_crosswalk_uses_original_workbook_not_current_metadata(inputs):
    summary = prepare(inputs)
    assert summary["selected_groups_with_exact_current_url"] == 1
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["provided_metadata"]["source_row"] == 2
    assert row["provided_metadata"]["values"]["date"] == "2020-01-02T00:00:00"
    assert row["provided_metadata"]["values"]["publisher"] == "Original Outlet"
    candidate = row["current_exact_url_candidates"][0]
    assert candidate["publisher"] == "Current outlet"
    assert candidate["countable"] is False and candidate["retrievable"] is False
    assert candidate["body_sha256"] != row["decoded_text_sha256"]
    assert row["url_identity_review"] == "pending"


def test_complete_source_locations_and_matching_url_never_approve_or_publish(inputs):
    summary = prepare(inputs)
    assert summary["approved_source_associations"] == summary["results_published"] == 0
    assert summary["model_calls"] == summary["network_calls"] == summary["database_writes"] == 0
    assert summary["reviewer"] is None and summary["classification_quality_scores"] is None
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["source_association_approved"] is False
    assert row["classification_semantic_review"] == "pending"
    assert row["original_page_completeness"] == "unknown"
    assert row["input_is_complete_original_article"] is False
    assert row["publication_status"] == "hold"
    with (inputs.output / "pending_source_review.csv").open(encoding="utf-8-sig", newline="") as stream:
        pending = next(csv.DictReader(stream))
    assert pending["source_review"] == "pending" and pending["publication_status"] == "hold"
    assert pending["reviewer"] == pending["reviewed_at"] == ""


def test_manifest_binds_every_written_artifact_and_exact_original_inputs(inputs):
    summary = prepare(inputs)
    manifest = json.loads((inputs.output / "packet_manifest.json").read_bytes())
    assert manifest["complete"] is True
    assert manifest["source_associations_approved"] is manifest["labels_published"] is False
    actual = {p.relative_to(inputs.output).as_posix(): review.digest(p.read_bytes())
              for p in inputs.output.rglob("*") if p.is_file() and p.name != "packet_manifest.json"}
    assert actual == manifest["artifacts"]
    assert summary["source_file_sha256"]["source_archive.zip"] == review.digest(inputs.manual_zip.read_bytes())
    assert (inputs.output / "source_archive.zip").read_bytes() == inputs.manual_zip.read_bytes()
    assert (inputs.output / "cleaning_notebook.ipynb").read_bytes() == inputs.notebook.read_bytes()
    assert summary["cleaning_settings"]["JUNK_PATTERNS"] == [r"^literal\\s+$"]
    assert summary["ignored_archive_members"] == ["New/unselected.xlsx", "upstream.py"]
    assert summary["source_snapshot_scope"] == "supplied_frozen_file_not_live_database"


def test_notebook_literal_double_backslashes_are_not_rewritten(inputs):
    settings = review.notebook_settings(inputs.notebook.read_bytes())
    assert settings["JUNK_PATTERNS"][0].count("\\") == 2
    _, kept = review.historical_cleaning("literal whitespace is still a retained original paragraph.", settings)
    assert kept == ["literal whitespace is still a retained original paragraph."]


def test_reading_notebook_never_executes_cells_or_imports(tmp_path, monkeypatch):
    marker = tmp_path / "notebook-was-executed.txt"
    data = notebook_bytes([
        "MIN_PARAGRAPH_LENGTH = 10\n", "MIN_WORD_COUNT = 3\n", "JUNK_PATTERNS = ['never_match']\n",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        "raise RuntimeError('upstream code must not run')\n",
    ])
    monkeypatch.setattr(review, "UPSTREAM_NOTEBOOK_SHA256", review.digest(data))
    assert review.notebook_settings(data)["MIN_WORD_COUNT"] == 3
    assert not marker.exists()


def test_changed_notebook_pin_rejected(inputs):
    with pytest.raises(ValueError, match="notebook_differs_from_pinned_projection"):
        review.notebook_settings(inputs.notebook.read_bytes() + b" ")


@pytest.mark.parametrize("source,error", [
    (["MIN_PARAGRAPH_LENGTH = 10\n", "MIN_PARAGRAPH_LENGTH = 20\n"], "duplicate_cleaning_setting"),
    (["MIN_PARAGRAPH_LENGTH = True\n", "MIN_WORD_COUNT = 3\n", "JUNK_PATTERNS = []\n"], "literal_cleaning_settings_required"),
    (["MIN_PARAGRAPH_LENGTH = 10\n", "MIN_WORD_COUNT = 3\n", "JUNK_PATTERNS = [42]\n"], "literal_cleaning_settings_required"),
])
def test_ambiguous_or_nonliteral_cleaning_settings_refused(source, error, monkeypatch):
    data = notebook_bytes(source)
    monkeypatch.setattr(review, "UPSTREAM_NOTEBOOK_SHA256", review.digest(data))
    with pytest.raises(ValueError, match=error):
        review.notebook_settings(data)


@pytest.mark.parametrize("name", ["00.txt", "01.txt", "-1.txt", "1.0.txt", "one.txt", "0.TXT", "../0.txt", "nested/0.txt"])
def test_article_filenames_must_have_canonical_nonnegative_ids(name):
    archive = source_zip(workbook_bytes(metadata_rows()), {name: b"Original source"})
    with pytest.raises(ValueError, match="canonical_article_text_filename_required"):
        review.read_manual_archive(archive)


def test_duplicate_zip_members_refused_instead_of_last_value_winning():
    with pytest.warns(UserWarning, match="Duplicate name"):
        archive = source_zip(workbook_bytes(metadata_rows()), {"0.txt": b"First"},
                             extras=[(review.TEXT_PREFIX + "0.txt", b"Second")])
    with pytest.raises(ValueError, match="duplicate_or_oversize_archive_members"):
        review.read_manual_archive(archive)


def test_symlink_member_and_non_utf8_text_are_refused():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("untrusted-link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside")
    with pytest.raises(ValueError, match="encrypted_or_symlink_archive_member"):
        review.read_manual_archive(stream.getvalue())
    with pytest.raises(UnicodeError):
        review.read_manual_archive(source_zip(workbook_bytes(), {"0.txt": b"\xff"}))


def test_missing_article_texts_and_oversize_nested_workbook_are_refused(monkeypatch):
    with pytest.raises(ValueError, match="original_article_texts_required"):
        review.read_manual_archive(source_zip(workbook_bytes()))
    workbook = workbook_bytes(metadata_rows())
    monkeypatch.setattr(review, "MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="workbook_too_large"):
        review.read_metadata(workbook)


@pytest.mark.parametrize("identifier", ["0", True, -1, None])
def test_metadata_ids_are_unique_nonnegative_integers(identifier):
    rows = metadata_rows()
    rows[0][0] = identifier
    with pytest.raises(ValueError, match="unique_integer_metadata_id_required"):
        review.read_metadata(workbook_bytes(rows))


def test_duplicate_metadata_ids_and_ambiguous_sheets_are_refused():
    with pytest.raises(ValueError, match="unique_integer_metadata_id_required"):
        review.read_metadata(workbook_bytes([metadata_rows()[0], metadata_rows()[0]]))
    for options in ({"sheet_name": "Unexpected"}, {"extra_sheet": True}):
        with pytest.raises(ValueError, match="explicit_original_metadata_sheet_required"):
            review.read_metadata(workbook_bytes(metadata_rows(), **options))


def test_missing_or_duplicate_required_headers_are_refused():
    for headers in (["id", "url"], [*HEADERS, "url"]):
        with pytest.raises(ValueError, match="original_metadata_headers_required"):
            review.read_metadata(workbook_bytes(headers=headers))


@pytest.mark.parametrize("missing", ["metadata", "text", "sampled"])
def test_missing_id_correspondence_rejected_before_output_creation(inputs, missing):
    rows, sources = metadata_rows(), {"0.txt": inputs.raw, "1.txt": OTHER.encode("utf-8")}
    if missing == "metadata":
        rows.pop()
    elif missing == "text":
        sources.pop("1.txt")
    else:
        inputs.input_csv.write_bytes(csv_data(["id", "article_id", "text"], [["1", "9", inputs.canonical]]))
        inputs.cleaned_csv.write_bytes(csv_data(["id", "text"], [["9", inputs.canonical]]))
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(rows), sources))
    with pytest.raises(ValueError, match="article_filename_and_metadata_id_sets_differ"):
        prepare(inputs)
    assert not inputs.output.exists()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///private/source", "https://user:secret@example.org/ad",
                                 "https://example.org/a b", "https://example.org/\nsecret", "https://example.org:bad/ad", None])
def test_unsafe_supplied_urls_never_become_markdown_links(inputs, url):
    rows = metadata_rows()
    rows[0][1] = url
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(rows), {"0.txt": inputs.raw, "1.txt": OTHER.encode("utf-8")}))
    prepare(inputs)
    assert review.safe_url(url) is None
    article = (inputs.output / "articles/0.md").read_text("utf-8")
    assert "[原表 URL（未联网核验）]" not in article
    lineage = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert lineage["provided_metadata"]["values"]["url"] == url
    assert lineage["current_exact_url_candidates"] == []


def test_formula_url_is_preserved_as_source_but_never_linked_or_matched(inputs):
    rows = metadata_rows()
    rows[0][1] = '=HYPERLINK("https://example.org/original", "Source")'
    rows[0][3] = "@unsafe spreadsheet title"
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(rows), {"0.txt": inputs.raw, "1.txt": OTHER.encode("utf-8")}))
    prepare(inputs)
    lineage = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert lineage["provided_metadata"]["formula_fields"] == ["url"]
    assert lineage["provided_metadata"]["values"]["url"] == rows[0][1]
    assert lineage["current_exact_url_candidates"] == []
    assert "[原表 URL（未联网核验）]" not in (inputs.output / "articles/0.md").read_text("utf-8")
    with (inputs.output / "pending_source_review.csv").open(encoding="utf-8-sig", newline="") as stream:
        pending = next(csv.DictReader(stream))
    assert pending["url_as_supplied"].startswith("'=")
    assert pending["title_as_supplied"].startswith("'@")


def test_source_fences_cannot_end_literal_markdown_block():
    text = "before\r\n```\r\n<script>source only</script>\r\n```` after"
    block = review.code_block(text)
    assert block.startswith("`````text\n") and block.endswith("\n`````")
    assert text in block


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(body="changed"),
    lambda r: r.update(body_sha256="0" * 64),
    lambda r: r.update(version_id="0" * 64),
    lambda r: r["payload"].update(publisher="changed metadata"),
    lambda r: r.update(record_id="wrong-record"),
    lambda r: r.update(dataset="social"),
])
def test_snapshot_body_metadata_and_identity_drift_refused(mutate):
    snapshot = current_snapshot()
    mutate(snapshot["records"][0])
    with pytest.raises(ValueError, match="current_source_identity_mismatch"):
        review.load_current_snapshot(review.encoded(snapshot))


def test_snapshot_duplicates_refused_and_inactive_social_records_not_joined():
    snapshot = current_snapshot()
    snapshot["records"].append(deepcopy(snapshot["records"][0]))
    with pytest.raises(ValueError, match="current_source_identity_mismatch"):
        review.load_current_snapshot(review.encoded(snapshot))
    assert not review.load_current_snapshot(review.encoded(current_snapshot(active=False)))
    assert not review.load_current_snapshot(review.encoded(current_snapshot(dataset="social")))


def test_existing_output_refused_before_any_input_read(inputs, monkeypatch):
    inputs.output.mkdir()
    sentinel = inputs.output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    reader = MagicMock(side_effect=AssertionError("must not read inputs"))
    monkeypatch.setattr(review, "read_bytes", reader)
    with pytest.raises(ValueError, match="new_private_output_directory_required"):
        prepare(inputs)
    reader.assert_not_called()
    assert sentinel.read_text("utf-8") == "keep"


def test_input_changes_before_commit_leave_no_output(inputs, monkeypatch):
    original = review.read_bytes
    calls = {}

    def changing_read(path):
        path = Path(path)
        calls[path] = calls.get(path, 0) + 1
        data = original(path)
        return data + b" " if path == inputs.notebook and calls[path] > 1 else data

    monkeypatch.setattr(review, "read_bytes", changing_read)
    with pytest.raises(ValueError, match="input_changed_during_preparation"):
        prepare(inputs)
    assert not inputs.output.exists()


def prior_audit(inputs):
    directory = inputs.output.parent / "prior-audit"
    directory.mkdir()
    (directory / "claims_article_linkage.json").write_bytes(review.encoded([
        {"upstream_article_id": "0", "current_record_candidates": [], "located_paragraphs": 2,
         "association_is_approved": False},
    ]))
    current = current_snapshot()["records"][0]
    candidate = {"record_id": current["record_id"], "version_id": current["version_id"],
                 "body_hash": current["body_sha256"], "url": current["payload"]["url"],
                 "source_issues": ["body_truncated_suspected"], "current": True}
    (directory / "claims_source_linkage.json").write_bytes(review.encoded([
        {"upstream_article_id": "0", "source_result_id": str(i), "candidates": [candidate]}
        for i in [1, 2]
    ]))
    audit = SimpleNamespace(
        directory=directory, candidates=[], artifact_hashes={}, manifest_sha256=None,
        report={"input_file_sha256": {path.name: review.digest(path.read_bytes())
                                     for path in [inputs.input_csv, inputs.cleaned_csv, inputs.notebook]}},
    )
    rebind_audit(audit)
    return audit


def rebind_audit(audit):
    audit.artifact_hashes = {p.name: review.digest(p.read_bytes()) for p in audit.directory.glob("*.json")
                            if p.name != "audit_output_manifest.json"}
    manifest = review.encoded({"complete": True, "artifacts": audit.artifact_hashes})
    (audit.directory / "audit_output_manifest.json").write_bytes(manifest)
    audit.manifest_sha256 = review.digest(manifest)


def test_prior_audit_input_hash_mismatch_refused(inputs, monkeypatch):
    audit = prior_audit(inputs)
    audit.report["input_file_sha256"][inputs.input_csv.name] = "0" * 64
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    with pytest.raises(ValueError, match="input_files_differ_from_prior_audit"):
        prepare(inputs, source_audit=audit.directory)
    assert not inputs.output.exists()


def test_prior_audit_group_mismatch_refused(inputs, monkeypatch):
    audit = prior_audit(inputs)
    (audit.directory / "claims_article_linkage.json").write_bytes(review.encoded([]))
    rebind_audit(audit)
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    with pytest.raises(ValueError, match="prior_audit_article_groups_differ"):
        prepare(inputs, source_audit=audit.directory)
    assert not inputs.output.exists()


def test_prior_audit_manifest_drift_refused_before_output(inputs, monkeypatch):
    audit = prior_audit(inputs)
    changed = deepcopy(audit)
    changed.manifest_sha256 = "b" * 64
    loader = MagicMock(side_effect=[audit, changed])
    monkeypatch.setattr(review, "load_audit", loader)
    with pytest.raises(ValueError, match="prior_audit_changed_during_preparation"):
        prepare(inputs, source_audit=audit.directory)
    assert loader.call_count == 2
    assert not inputs.output.exists()


def test_matching_prior_audit_is_retained_as_history_and_not_publication(inputs, monkeypatch):
    audit = prior_audit(inputs)
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    summary = prepare(inputs, source_audit=audit.directory)
    assert summary["prior_audit_manifest_sha256"] == audit.manifest_sha256
    assert summary["prior_eligible_classification_candidates"] == 0
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["prior_source_audit"]["association_is_approved"] is False
    assert row["source_association_approved"] is False
    assert len(row["prior_current_text_candidates"]) == 1
    assert row["prior_current_text_candidates"][0]["current_snapshot_version_matches"] is True
    assert row["prior_current_text_candidates"][0]["matched_input_ids"] == ["1", "2"]
    assert row["prior_current_text_candidates"][0]["publisher"] == "Current outlet"
    assert "current_snapshot_candidate" not in row["prior_current_text_candidates"][0]
    for filename, fingerprint in audit.artifact_hashes.items():
        assert review.digest((inputs.output / "prior_audit" / filename).read_bytes()) == fingerprint
    assert (inputs.output / "prior_audit/audit_output_manifest.json").read_bytes() == (
        audit.directory / "audit_output_manifest.json").read_bytes()


def test_prior_audit_artifact_bytes_must_match_manifest_before_parsing(inputs, monkeypatch):
    audit = prior_audit(inputs)
    (audit.directory / "claims_source_linkage.json").write_bytes(b"not JSON")
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    with pytest.raises(ValueError, match="prior_audit_artifact_changed"):
        prepare(inputs, source_audit=audit.directory)
    assert not inputs.output.exists()


def test_prior_audit_manifest_bytes_are_pinned(inputs, monkeypatch):
    audit = prior_audit(inputs)
    (audit.directory / "audit_output_manifest.json").write_bytes(b"changed")
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    with pytest.raises(ValueError, match="prior_audit_manifest_changed"):
        prepare(inputs, source_audit=audit.directory)
    assert not inputs.output.exists()


def test_prior_text_candidate_version_drift_remains_visible_and_unapproved(inputs, monkeypatch):
    audit = prior_audit(inputs)
    path = audit.directory / "claims_source_linkage.json"
    rows = json.loads(path.read_bytes())
    for row in rows:
        row["candidates"][0]["version_id"] = "0" * 64
    path.write_bytes(review.encoded(rows))
    rebind_audit(audit)
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    prepare(inputs, source_audit=audit.directory)
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["prior_current_text_candidates"][0]["current_snapshot_version_matches"] is False
    assert row["source_association_approved"] is False and row["publication_status"] == "hold"


def test_drifted_prior_candidate_does_not_borrow_publisher_from_current_version(inputs, monkeypatch):
    audit = prior_audit(inputs)
    path = audit.directory / "claims_source_linkage.json"
    source_rows = json.loads(path.read_bytes())
    old_version = "0" * 64
    for source_row in source_rows:
        source_row["candidates"][0]["version_id"] = old_version
    path.write_bytes(review.encoded(source_rows))
    rebind_audit(audit)
    monkeypatch.setattr(review, "load_audit", lambda _: audit)
    prepare(inputs, source_audit=audit.directory)
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    historical = row["prior_current_text_candidates"][0]
    assert historical["version_id"] == old_version
    assert historical["publisher"] is None
    assert historical["current_snapshot_version_matches"] is False
    current = historical["current_snapshot_candidate"]
    expected = current_snapshot()["records"][0]
    assert current["version_id"] == expected["version_id"] != old_version
    assert current["body_sha256"] == expected["body_sha256"]
    assert current["url"] == expected["payload"]["url"]
    assert current["publisher"] == "Current outlet"
    assert current["title"] == "Current title" and current["sponsor"] == "Current sponsor"
    assert row["source_association_approved"] is False and row["publication_status"] == "hold"


def test_missing_or_reversed_retained_sequence_never_becomes_complete_input(inputs):
    inputs.input_csv.write_bytes(csv_data(["id", "article_id", "text"], [["1", "0", OTHER], ["2", "0", inputs.canonical]]))
    inputs.cleaned_csv.write_bytes(csv_data(["id", "text"], [["0", OTHER], ["0", inputs.canonical], ["1", OTHER]]))
    summary = prepare(inputs)
    assert summary["selected_ordered_groups"] == 0
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["located_paragraphs"] == 1
    assert row["reproduces_cleaned_sequence"] is False
    assert row["paragraphs"][0]["locations"] == []
    assert row["publication_status"] == "hold"


def test_all_paragraphs_located_in_wrong_order_do_not_prove_input_lineage(inputs):
    raw = (PARAGRAPH + "\r\n\r\n" + OTHER).encode("utf-8")
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(metadata_rows()), {"0.txt": raw, "1.txt": OTHER.encode("utf-8")}))
    inputs.input_csv.write_bytes(csv_data(["id", "article_id", "text"], [["1", "0", OTHER], ["2", "0", inputs.canonical]]))
    inputs.cleaned_csv.write_bytes(csv_data(["id", "text"], [["0", OTHER], ["0", inputs.canonical], ["1", OTHER]]))
    summary = prepare(inputs)
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["located_paragraphs"] == row["supplied_paragraphs"] == 2
    assert row["all_retained_paragraphs_in_order"] is False
    assert summary["selected_ordered_groups"] == 0
    assert row["source_association_approved"] is False


def test_single_original_occurrence_cannot_satisfy_two_retained_paragraphs(inputs):
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(metadata_rows()), {
        "0.txt": PARAGRAPH.encode("utf-8"), "1.txt": OTHER.encode("utf-8"),
    }))
    prepare(inputs)
    row = json.loads((inputs.output / "article_lineage.json").read_bytes())[0]
    assert row["located_paragraphs"] == 2
    assert all(len(p["locations"]) == 1 for p in row["paragraphs"])
    assert row["all_retained_paragraphs_in_order"] is False


def test_markdown_metadata_cannot_insert_images_links_or_html(inputs):
    rows = metadata_rows()
    rows[0][3] = "![track](https://example.org/track) <script>source</script> | extra"
    inputs.manual_zip.write_bytes(source_zip(workbook_bytes(rows), {"0.txt": inputs.raw, "1.txt": OTHER.encode("utf-8")}))
    prepare(inputs)
    article = (inputs.output / "articles/0.md").read_text("utf-8")
    assert "![track](" not in article and "<script>" not in article
    assert "\\!\\[track\\]" in article and "&lt;script&gt;" in article
    assert json.loads((inputs.output / "article_lineage.json").read_bytes())[0]["provided_metadata"]["values"]["title"] == rows[0][3]


def test_partial_write_failure_never_leaves_completed_manifest(inputs, monkeypatch):
    original = Path.write_bytes

    def failed_write(path, data):
        if path == inputs.output / "article_lineage.json":
            raise OSError("synthetic write failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", failed_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        prepare(inputs)
    assert not (inputs.output / "packet_manifest.json").exists()

