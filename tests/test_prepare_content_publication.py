"""File-backed synthetic review preparation; never calls providers or a database."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_content_publication import APPROVAL, BODY, current_rows, mark

from observatory.content_publication import load_publication, read_match_page

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "prepare_content_publication", Path(__file__).parents[1] / "scripts/prepare_content_publication.py"
)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


@pytest.fixture
def packet(tmp_path):
    import prepare_content_review as original

    from observatory.content_assessment import QUESTION_IDS, QUESTION_TEXTS
    from observatory.evaluate import canonical_digest

    definitions = {"status": "draft_requires_client_confirmation", "questions": [
        {"question_id": qid, "question_exact": text, "source_paragraph_exact": text,
         "query_question": text, "source_ref": f"synthetic-P{i}",
         "status": "draft_requires_client_confirmation", "definition_draft": "Synthetic rule pending client review.",
         "candidate_search_terms": ["CCS"]}
        for i, (qid, text) in enumerate(zip(QUESTION_IDS, QUESTION_TEXTS, strict=True), 1)
    ]}
    records = []
    for rid, body, retrievable in (("one", BODY, True), ("two", BODY, True), ("empty", "", False)):
        payload = {"record_id": rid, "dataset": "native", "body": body, "countable": True,
                   "retrievable": retrievable, "issues": [], "raw": {"private": "C:/private/raw"}}
        records.append({"record_id": rid, "dataset": "native", "active": True,
                        "body": body, "version_id": canonical_digest(payload), "payload": payload})
    qpath, spath, packet = tmp_path / "q.json", tmp_path / "s.json", tmp_path / "packet"
    qpath.write_bytes(original.encoded(definitions))
    spath.write_bytes(original.encoded(records))
    original.prepare(spath, qpath, packet)
    return packet


def review_file(packet, tmp_path):
    path = tmp_path / "review.json"
    cli.write_review_template(packet, path)
    value = json.loads(path.read_bytes())
    value["definition_review"] = deepcopy(APPROVAL)
    value["publication_review"] = deepcopy(APPROVAL)
    mark(value)
    path.write_bytes(cli.encoded(value))
    return path, value


def test_real_source_packet_all_pending_stays_unpublishable_and_unchanged(packet, tmp_path):
    before = {p.relative_to(packet): p.read_bytes() for p in packet.rglob("*") if p.is_file()}
    path = tmp_path / "review.json"
    summary = cli.write_review_template(packet, path)
    assert summary["review_units"] == 72 and summary["reviewed_units"] == summary["publications"] == 0
    validated = cli.validate_review_file(packet, path)
    assert validated["membership_counts"] == {"pending": 72} and not validated["publication_ready"]
    out = tmp_path / "unapproved"
    with pytest.raises(ValueError):
        cli.prepare_publication(packet, path, out)
    assert not out.exists()
    assert before == {p.relative_to(packet): p.read_bytes() for p in packet.rglob("*") if p.is_file()}


def test_reviewed_partial_artifact_preserves_review_bytes_and_loads_pins(packet, tmp_path):
    path, review = review_file(packet, tmp_path)
    source = cli.load_content_packet(packet)
    out = tmp_path / "new_artifact"
    result = cli.prepare_publication(packet, path, out)
    assert result["classification_complete"] is False and result["publication_status"] == "partial"
    assert result["reviewed_units"] == 1 and result["review_units"] == 72
    assert result["model_calls"] == result["database_writes"] == result["server_activations"] == 0
    assert (out / "review.json").read_bytes() == path.read_bytes()
    publication = load_publication(out / "publication.json", result["publication_sha256"], result["review_sha256"])
    rows = current_rows(source)
    page = read_match_page(publication, rows, "Q06")
    assert page["totals"] == {"scope_records": 3, "relevant": 1, "not_relevant": 0, "unknown": 2}
    assert page["question"]["question_id"] == "Q06" and publication["semantic_gold"] is False
    assert json.loads((out / "preparation_summary.json").read_bytes()) == result
    assert review["slots"] == json.loads((out / "review.json").read_bytes())["slots"]


def test_missing_unmatched_record_or_modified_review_binding_cannot_prepare(packet, tmp_path):
    path, review = review_file(packet, tmp_path)
    review["slots"] = [s for s in review["slots"] if s["record_id"] != "two"]
    path.write_bytes(cli.encoded(review))
    out = tmp_path / "invalid"
    with pytest.raises(ValueError, match="complete_record_times_24"):
        cli.prepare_publication(packet, path, out)
    assert not out.exists()


def test_existing_outputs_and_source_packet_are_never_overwritten(packet, tmp_path):
    path, _ = review_file(packet, tmp_path)
    with pytest.raises(ValueError, match="new_review"):
        cli.write_review_template(packet, path)
    with pytest.raises(ValueError, match="inside_original"):
        cli.write_review_template(packet, packet / "new_review.json")
    with pytest.raises(ValueError, match="inside_original"):
        cli.prepare_publication(packet, path, packet / "new_artifact")
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(ValueError, match="new_output"):
        cli.prepare_publication(packet, path, out)


def test_unsafe_json_review_and_source_drift_fail_before_output(packet, tmp_path):
    path, _ = review_file(packet, tmp_path)
    path.write_bytes(b'{"slots":[],"slots":[]}')
    with pytest.raises(ValueError):
        cli.prepare_publication(packet, path, tmp_path / "unsafe")
    assert not (tmp_path / "unsafe").exists()
    raw = (packet / "source_snapshot.json").read_bytes()
    (packet / "source_snapshot.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="artifact_changed"):
        cli.validate_review_file(packet, path)


def test_cli_template_validate_and_prepare_commands(packet, tmp_path, capsys):
    path = tmp_path / "review.json"
    assert cli.main(["template", "--packet", str(packet), "--out", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "pending_review_template"
    assert cli.main(["validate", "--packet", str(packet), "--review", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["reviewed_units"] == 0
    value = json.loads(path.read_bytes())
    value["definition_review"] = value["publication_review"] = deepcopy(APPROVAL)
    mark(value)
    path.write_bytes(cli.encoded(value))
    assert cli.main(["prepare", "--packet", str(packet), "--review", str(path), "--out", str(tmp_path / "out")]) == 0
    assert json.loads(capsys.readouterr().out)["publication_status"] == "partial"
