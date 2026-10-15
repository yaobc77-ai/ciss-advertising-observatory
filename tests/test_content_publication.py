"""Synthetic publication contracts only; no semantic quality or customer approval."""

import hashlib
import json
from copy import deepcopy

import pytest

from observatory.content_assessment import QUESTION_IDS, QUESTION_TEXTS
from observatory.content_publication import (
    Publication,
    build_publication,
    load_publication,
    make_review_template,
    read_match_page,
    validate_review,
)
from observatory.evaluate import canonical_digest

APPROVAL = {"status": "approved", "reviewer": "Synthetic named reviewer",
            "reviewed_at": "2026-10-06T08:00:00-04:00", "approval_record": "Synthetic assertion, not authentication."}
BODY = "🙂 Sponsor states that CCS may lower emissions. A researcher questions the proposal. " * 4


def source_for(ids=("one", "two"), *, body=BODY, retrievable=True, ranges=None):
    definitions = {"status": "draft_requires_client_confirmation", "questions": [
        {"question_id": qid, "question_exact": text, "source_paragraph_exact": text,
         "query_question": text, "source_ref": f"synthetic-P{i}",
         "status": "draft_requires_client_confirmation", "definition_draft": "Synthetic rule pending client review."}
        for i, (qid, text) in enumerate(zip(QUESTION_IDS, QUESTION_TEXTS, strict=True), 1)
    ]}
    records = []
    for rid in sorted(ids):
        payload = {"record_id": rid, "dataset": "native", "body": body, "countable": True,
                   "retrievable": retrievable, "issues": [], "raw": {"private": "C:/private/raw"}}
        if ranges is not None:
            payload["retrieval_ranges"] = ranges
        digest = canonical_digest(payload)
        records.append({"record_id": rid, "dataset": "native", "active": True,
                        "body": body, "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        "version_id": digest, "payload_sha256": digest, "payload": payload,
                        "retrieval_ranges": ranges if ranges is not None else ([[0, len(body)]] if body else [])})
    return {"selected": records, "definitions": definitions, "manifest_sha256": "a" * 64,
            "summary": {"selection_sha256": canonical_digest([
                {k: r[k] for k in ("record_id", "version_id", "body_sha256")} for r in records])}}


def mark(review, rid="one", qid="Q06", membership="relevant", *, evidence=None):
    slot = next(s for s in review["slots"] if s["record_id"] == rid and s["question_id"] == qid)
    slot.update(final_membership=membership, review=deepcopy(APPROVAL),
                speaker="Sponsor", treatment="reported", temporal_status="planned",
                rationale="Synthetic adjudication, not an external truth assessment.")
    if membership == "relevant":
        start, end = BODY.index("CCS"), BODY.index("CCS") + 3
        slot["support_evidence"] = evidence if evidence is not None else [{"start": start, "end": end, "quote": "CCS"}]
    elif membership == "not_relevant":
        slot["original_source_complete"] = slot["full_text_reviewed"] = True
    return slot


def publication_for(source, *, all_positive=False):
    review = make_review_template(source)
    review["definition_review"] = deepcopy(APPROVAL)
    review["publication_review"] = deepcopy(APPROVAL)
    mark(review)
    if all_positive:
        for r in source["selected"]:
            mark(review, r["record_id"])
    return build_publication(source, review, review_sha256=canonical_digest(review)), review


def current_rows(source):
    return [{"record_id": r["record_id"], "version_id": r["version_id"], "dataset": "native",
             "body": r["body"], "body_hash": r["body_sha256"], "retrievable": r["payload"]["retrievable"],
             "retrieval_ranges": r["retrieval_ranges"], "retrieval_end": None,
             "publicmetadata": {"title": "Current synthetic title", "publisher": "Current publisher",
                                "sponsor": "Current sponsor", "url": "https://example.org/one",
                                "archive_url": "https://archive.example.org/one", "date": "2026-01-02",
                                "raw": "C:/private/raw", "reviewer": "private reviewer"}}
            for r in source["selected"]]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def test_template_retains_all_scope_and_q15_separate_uncertainty():
    source = source_for(("one", "two", "no-match"))
    review = make_review_template(source)
    assert len(review["slots"]) == 72
    assert {s["record_id"] for s in review["slots"]} == {"one", "two", "no-match"}
    assert all(s["final_membership"] == "pending" for s in review["slots"])
    assert review["definition_review"]["status"] == review["publication_review"]["status"] == "pending"
    assert validate_review(source, review)["reviewed_units"] == 0
    with pytest.raises(ValueError):
        build_publication(source, review, review_sha256=canonical_digest(review))


def test_partial_publication_uses_current_metadata_and_omits_private_fields():
    source = source_for()
    publication, _ = publication_for(source)
    result = read_match_page(publication, current_rows(source), "Q06")
    assert result["status"] == "ok" and result["available"]
    assert result["totals"] == {"scope_records": 2, "relevant": 1, "not_relevant": 0, "unknown": 1}
    assert result["coverage"]["unknown_reasons"] == {"new": 0, "stale": 0, "pending": 1, "insufficient": 0}
    assert result["coverage"]["reviewed_records"] == 1
    assert result["coverage"]["scope_matches_frozen"] and not result["coverage"]["classification_complete"]
    assert result["page_complete"] and result["next_offset"] is None
    row = result["records"][0]
    assert row["title"] == "Current synthetic title"
    assert row["support_evidence"][0]["quote"] == "CCS"
    assert not row["original_source_complete"] and not row["full_text_reviewed"]
    rendered = json.dumps(result)
    assert "C:/private" not in rendered and "reviewer" not in rendered
    assert "definitions_document" not in rendered and "request_sha256" not in rendered


def test_explicit_negative_and_reviewed_unknown_remain_distinct():
    source = source_for(("one", "two", "unknown"))
    publication, review = publication_for(source)
    mark(review, "two", membership="not_relevant")
    mark(review, "unknown", membership="unknown")
    publication = build_publication(source, review, review_sha256=canonical_digest(review))
    result = read_match_page(publication, current_rows(source), "Q06")
    assert result["totals"] == {"scope_records": 3, "relevant": 1, "not_relevant": 1, "unknown": 1}
    assert result["coverage"]["reviewed_records"] == 3
    assert result["coverage"]["unknown_reasons"]["insufficient"] == 1
    assert not result["coverage"]["classification_complete"]


def test_complete_current_subset_does_not_claim_full_frozen_scope():
    source = source_for()
    publication, review = publication_for(source)
    mark(review, "two", membership="not_relevant")
    publication = build_publication(source, review, review_sha256=canonical_digest(review))
    result = read_match_page(publication, current_rows(source)[1:], "Q06")
    assert result["totals"] == {"scope_records": 1, "relevant": 0, "not_relevant": 1, "unknown": 0}
    assert result["coverage"]["classification_complete"] and not result["coverage"]["scope_matches_frozen"]
    assert result["coverage"]["frozen_not_in_selection"] == 1
    assert result["page_complete"] and result["records"] == []


@pytest.mark.parametrize("field,value", [
    ("body_hash", "c" * 64), ("version_id", "c" * 64), ("body", BODY + " Changed."),
    ("retrieval_ranges", [[0, 5]]), ("retrieval_ranges", [[True, len(BODY)]]),
    ("retrieval_ranges", []), ("retrievable", False), ("retrievable", 1), ("dataset", "social"),
])
def test_same_identity_with_bad_current_source_is_unknown(field, value):
    source = source_for()
    publication, _ = publication_for(source)
    rows = current_rows(source)
    rows[0][field] = value
    result = read_match_page(publication, rows, "Q06")
    assert result["totals"]["relevant"] == result["totals"]["not_relevant"] == 0
    assert result["totals"]["unknown"] == 2 and result["coverage"]["unknown_reasons"]["stale"] == 1
    assert result["records"] == [] and not result["coverage"]["scope_matches_frozen"]


def test_new_record_is_unknown_and_current_row_duplicates_fail():
    source = source_for()
    publication, _ = publication_for(source)
    rows = current_rows(source)
    rows.append({**rows[0], "record_id": "new"})
    result = read_match_page(publication, rows, "Q06")
    assert result["totals"]["unknown"] == 2 and result["coverage"]["unknown_reasons"]["new"] == 1
    with pytest.raises(ValueError, match="unique_current"):
        read_match_page(publication, rows + [rows[0]], "Q06")


def test_pagination_is_not_scope_classification_and_final_page_not_full_list():
    source = source_for()
    publication, _ = publication_for(source, all_positive=True)
    first = read_match_page(publication, current_rows(source), "Q06", limit=1)
    last = read_match_page(publication, current_rows(source), "Q06", offset=1, limit=1)
    assert first["totals"]["relevant"] == last["totals"]["relevant"] == 2
    assert first["next_offset"] == 1 and last["next_offset"] is None
    assert not first["page_complete"] and not last["page_complete"]
    assert first["coverage"]["classification_complete"]


@pytest.mark.parametrize("mutation", ["slots_missing", "duplicate", "foreign", "request", "version", "body", "definition", "scope", "wording", "extra"])
def test_binding_changes_and_missing_unmatched_units_are_rejected(mutation):
    source = source_for()
    _, review = publication_for(source)
    if mutation == "slots_missing":
        review["slots"].pop()
    elif mutation == "duplicate":
        review["slots"][-1] = deepcopy(review["slots"][0])
    elif mutation == "foreign":
        review["slots"][0]["record_id"] = "not-in-scope"
    elif mutation in {"request", "version", "body", "definition"}:
        field = {"request": "request_sha256", "version": "version_id", "body": "body_sha256", "definition": "definitions_sha256"}[mutation]
        review["slots"][0][field] = "c" * 64
    elif mutation == "scope":
        review["scope_sha256"] = "c" * 64
    elif mutation == "wording":
        source["definitions"]["questions"][0]["question_exact"] = "A different question"
    else:
        review["slots"][0]["automatic_approved"] = True
    with pytest.raises(ValueError):
        build_publication(source, review, review_sha256=canonical_digest(review))


@pytest.mark.parametrize("field", ["original_source_complete", "full_text_reviewed"])
def test_negative_requires_both_independent_completeness_assertions(field):
    source = source_for()
    _, review = publication_for(source)
    slot = mark(review, "two", membership="not_relevant")
    slot[field] = False
    with pytest.raises(ValueError, match="negative_requires"):
        build_publication(source, review, review_sha256=canonical_digest(review))
    slot[field] = True
    slot["final_membership"] = "not_found"
    with pytest.raises(ValueError):
        build_publication(source, review, review_sha256=canonical_digest(review))


@pytest.mark.parametrize("body", ["", "video", "Error fetching article: failed"])
def test_missing_placeholder_sources_never_become_negatives(body):
    source = source_for(("one",), body=body, retrievable=False)
    review = make_review_template(source)
    review["definition_review"] = review["publication_review"] = deepcopy(APPROVAL)
    mark(review, membership="not_relevant")
    with pytest.raises(ValueError, match="cannot_be_negative"):
        build_publication(source, review, review_sha256=canonical_digest(review))


@pytest.mark.parametrize("evidence", [
    {"start": True, "end": 3, "quote": "CCS"},
    {"start": 24, "end": 27, "quote": "fabricated"},
    {"start": -1, "end": 3, "quote": "CCS"},
    {"start": 0, "end": 3, "quote": "🙂 "},
])
def test_evidence_uses_exact_unicode_character_bounds(evidence):
    source = source_for()
    _, review = publication_for(source)
    mark(review, evidence=[evidence])
    with pytest.raises(ValueError):
        build_publication(source, review, review_sha256=canonical_digest(review))


def test_outside_allowed_ranges_rejected_even_if_exact_original_quote():
    source = source_for(ranges=[[60, len(BODY)]])
    review = make_review_template(source)
    review["definition_review"] = review["publication_review"] = deepcopy(APPROVAL)
    mark(review)
    with pytest.raises(ValueError, match="allowed_original_source"):
        build_publication(source, review, review_sha256=canonical_digest(review))


def test_q15_consensus_has_separate_evidence_and_is_not_a_fact_verdict():
    source = source_for()
    publication, review = publication_for(source)
    slot = mark(review, qid="Q15")
    slot["consensus_position"] = "consistent_with_consensus"
    with pytest.raises(ValueError, match="consensus_requires"):
        build_publication(source, review, review_sha256=canonical_digest(review))
    slot["consensus_evidence"] = deepcopy(slot["support_evidence"])
    publication = build_publication(source, review, review_sha256=canonical_digest(review))
    result = read_match_page(publication, current_rows(source), "Q15")
    assert result["records"][0]["consensus_position"] == "consistent_with_consensus"
    assert len(result["records"][0]["consensus_evidence"]) == 1
    assert result["question"]["question_exact"] == QUESTION_TEXTS[14]


def test_links_toggle_and_unsafe_links_do_not_leak_into_metadata():
    source = source_for()
    publication, _ = publication_for(source)
    rows = current_rows(source)
    result = read_match_page(publication, rows, "Q06", show_source_links=False)
    assert "url" not in result["records"][0] and "archive_url" not in result["records"][0]
    rows[0]["publicmetadata"].update(url="javascript:alert(1)", archive_url="file:///C:/private/source.pdf")
    result = read_match_page(publication, rows, "Q06")
    assert "url" not in result["records"][0] and "archive_url" not in result["records"][0]


def test_loader_pins_raw_file_and_review_sha_and_detects_mutation(tmp_path):
    source = source_for()
    publication, _ = publication_for(source)
    data, path = encoded(publication), tmp_path / "publication.json"
    path.write_bytes(data)
    loaded = load_publication(path, hashlib.sha256(data).hexdigest(), publication["review_sha256"])
    assert read_match_page(loaded, current_rows(source), "Q06")["publication_version"] == hashlib.sha256(data).hexdigest()
    for pub_sha, review_sha in [("b" * 64, publication["review_sha256"]), (hashlib.sha256(data).hexdigest(), "c" * 64)]:
        with pytest.raises(ValueError):
            load_publication(path, pub_sha, review_sha)
    loaded["slots"][0]["rationale"] = "Changed after validation"
    with pytest.raises(ValueError, match="mutated"):
        read_match_page(loaded, current_rows(source), "Q06")


@pytest.mark.parametrize("mutation", ["slot", "approval", "review_hash", "embedded_review"])
def test_review_sha_binds_original_review_content_not_just_a_string(tmp_path, mutation):
    source = source_for()
    publication, _ = publication_for(source)
    if mutation == "slot":
        publication["slots"][0]["rationale"] = "Different adjudication with old review SHA"
    elif mutation == "approval":
        publication["publication_review"]["reviewer"] = "Someone else"
    elif mutation == "review_hash":
        publication["review_sha256"] = "c" * 64
    else:
        publication["review_json_utf8"] += " "
    data = encoded(publication)
    path = tmp_path / "modified.json"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        load_publication(path, hashlib.sha256(data).hexdigest(), publication["review_sha256"])


def test_build_requires_real_review_bytes_sha_and_exact_json_agreement():
    source = source_for()
    _, review = publication_for(source)
    with pytest.raises(ValueError, match="original_review_bytes"):
        build_publication(source, review, review_sha256="c" * 64)
    other = deepcopy(review)
    other["publication_review"]["reviewer"] = "A different reviewer"
    raw = encoded(other)
    with pytest.raises(ValueError, match="original_review_bytes"):
        build_publication(source, review, review_sha256=hashlib.sha256(raw).hexdigest(), review_bytes=raw)


def test_empty_current_selection_does_not_claim_full_frozen_corpus():
    source = source_for()
    publication, _ = publication_for(source)
    result = read_match_page(publication, [], "Q06")
    assert result["totals"] == {"scope_records": 0, "relevant": 0, "not_relevant": 0, "unknown": 0}
    assert not result["coverage"]["scope_matches_frozen"]
    assert result["coverage"]["frozen_not_in_selection"] == 2
    assert "current selection only" in result["page_note"]


@pytest.mark.parametrize("raw", [b'{"format_version":1,"format_version":2}', b'{"value":NaN}', b'{"value":Infinity}'])
def test_duplicate_json_and_nonfinite_values_are_rejected(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        load_publication(path, hashlib.sha256(raw).hexdigest(), "c" * 64)


@pytest.mark.parametrize("approval", [
    {**APPROVAL, "reviewer": ""}, {**APPROVAL, "reviewed_at": "2026-10-06"},
    {**APPROVAL, "approval_record": ""}, {**APPROVAL, "authenticated": True},
])
def test_approval_is_named_timezone_assertion_not_authentication(approval):
    source = source_for()
    _, review = publication_for(source)
    review["definition_review"] = approval
    with pytest.raises(ValueError):
        build_publication(source, review, review_sha256=canonical_digest(review))


def test_artifact_coverage_flags_cannot_be_invented():
    source = source_for()
    publication, _ = publication_for(source)
    for field, value in (("classification_complete", True), ("status", "complete"),
                         ("reviewed_units", 48), ("semantic_gold", True), ("quality_scores", {"f1": 1})):
        changed = deepcopy(publication)
        changed[field] = value
        with pytest.raises(ValueError):
            Publication.model_validate(changed)


def test_literal_boolean_coercion_and_nested_nan_are_forbidden():
    source = source_for()
    publication, _ = publication_for(source)
    publication["semantic_gold"] = 0
    with pytest.raises(ValueError):
        Publication.model_validate(publication)
    publication["semantic_gold"] = False
    publication["definitions_document"]["unexpected_nonfinite"] = float("nan")
    publication["definitions_sha256"] = canonical_digest(publication["definitions_document"])
    with pytest.raises(ValueError):
        Publication.model_validate(publication)


@pytest.mark.parametrize("arguments", [{"offset": True}, {"offset": -1}, {"limit": True}, {"limit": 101},
                                        {"show_source_links": "yes"}])
def test_public_paging_parameters_are_strict(arguments):
    source = source_for()
    publication, _ = publication_for(source)
    with pytest.raises(ValueError):
        read_match_page(publication, current_rows(source), "Q06", **arguments)
