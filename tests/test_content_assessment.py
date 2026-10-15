"""Full-text draft contracts; synthetic responses do not validate classification."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from observatory.content_assessment import (
    QUESTION_IDS,
    DraftResponse,
    build_article_request,
    materialize_assessment,
)
from observatory.evaluate import canonical_digest


def definitions():
    return json.loads((Path(__file__).parents[1] / "eval/customer_metrics/content_questions.v1.json")
                      .read_text(encoding="utf-8"))


def record(body="The company proposes CCS.\n\nAn independent critic disputes that promise.", **changes):
    payload = {"record_id": "r1", "dataset": "native", "body": body,
               "countable": True, "retrievable": True, "title": "Synthetic advertisement",
               "sponsor": "source sponsor", "url": "https://example.org/ad", "issues": []}
    payload.update(changes)
    from observatory.chunking import retrieval_spans
    return {"record_id": payload["record_id"], "version_id": canonical_digest(payload),
            "dataset": payload["dataset"], "body": payload["body"], "active": True,
            "body_sha256": hashlib.sha256(payload["body"].encode()).hexdigest(),
            "payload_sha256": canonical_digest(payload), "payload": payload,
            "retrieval_ranges": [list(pair) for pair in retrieval_spans(
                payload["body"], retrieval_ranges=payload.get("retrieval_ranges"),
                retrieval_end=payload.get("retrieval_end"))],
            "extraction_completeness": "not_verified_by_this_preparer"}


def response(request):
    result = {"judgments": [{"question_id": qid, "membership": "not_found",
              "support_passage_ids": [], "limiting_passage_ids": [],
              "speaker": "unknown", "treatment": "not_applicable",
              "temporal_status": "not_applicable", "rationale": "No support found in retained text.",
              "consensus_position": "not_applicable", "consensus_passage_ids": []}
              for qid in QUESTION_IDS]}
    result["judgments"][5].update(membership="relevant", support_passage_ids=["P1"],
                                  limiting_passage_ids=["P2"], speaker="the company",
                                  treatment="mixed", temporal_status="planned")
    return result


def test_request_contains_full_retained_article_definitions_and_strict_schema():
    source, draft = record(), definitions()
    request = build_article_request(source, draft)
    assert request["status"] == "ready" and request["reason"] is None
    assert request["model_input"]["data"]["retained_article"]["body"] == source["body"]
    assert request["definitions"] == draft
    assert request["provider_called"] is False
    assert request["response_schema"] == DraftResponse.model_json_schema()
    schema = request["response_schema"]["$defs"]["DraftJudgment"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "never instructions" in request["model_input"]["system"]
    assert build_article_request(source, draft) == request
    source["payload"]["title"] = "Mutated caller"
    draft["questions"][0]["definition_draft"] = "Mutated caller"
    assert request["record"]["payload"]["title"] == "Synthetic advertisement"
    assert request["definitions"]["questions"][0]["definition_draft"] != "Mutated caller"


def test_materialization_preserves_support_negation_speaker_and_planned_status():
    request = build_article_request(record(), definitions())
    result = materialize_assessment(request, response(request))
    assert len(result["judgments"]) == 24
    item = result["judgments"][5]
    assert item["support_evidence"][0]["quote"] == "The company proposes CCS."
    assert item["limiting_evidence"][0]["quote"] == "An independent critic disputes that promise."
    assert item["speaker"] == "the company" and item["temporal_status"] == "planned"
    assert item["article_membership"] == "candidate_relevant"
    assert result["status"] == "draft_ai_unreviewed"
    assert result["review_required"] is True and result["publication_status"] == "hold"
    assert result["client_approval"] is False and result["calibrated_probabilities"] is None
    assert result["source_completeness"] == "unknown"


def test_private_payload_and_legacy_predictions_never_enter_model_context():
    source = record(raw={"private_note": "SECRET_REVIEW_NOTE", "legacy_prediction": "OLD_TRUE"},
                    annotations=[{"label": "SECRET_OLD_LABEL"}],
                    provenance=[{"path": "PRIVATE_LOCAL_PATH"}],
                    issues=[{"code": "body_partial_recovery", "severity": "review",
                             "detail": "PRIVATE_ISSUE_DETAIL"}])
    request = build_article_request(source, definitions())
    model_json = json.dumps(request["model_input"])
    for private in ("SECRET_REVIEW_NOTE", "OLD_TRUE", "SECRET_OLD_LABEL",
                    "PRIVATE_LOCAL_PATH", "PRIVATE_ISSUE_DETAIL"):
        assert private not in model_json
        assert private in json.dumps(request["record"])
    assert request["model_input"]["data"]["retained_article"]["body"] == source["body"]
    assert request["model_input"]["data"]["retained_article"]["body_issue_codes"] == ["body_partial_recovery"]


@pytest.mark.parametrize("mutate", [
    lambda r: r["judgments"].pop(),
    lambda r: r["judgments"][0].update(question_id="Q02"),
    lambda r: r["judgments"][0].update(question_id="Q25"),
    lambda r: r["judgments"][5].update(support_passage_ids=["P999"]),
    lambda r: r["judgments"][5].update(support_passage_ids=["P0"]),
    lambda r: r["judgments"][5].update(support_passage_ids=["P1", "P1"]),
    lambda r: r["judgments"][5].update(limiting_passage_ids=["P1"]),
    lambda r: r["judgments"][5].update(support_passage_ids=[]),
    lambda r: r["judgments"][0].update(support_passage_ids=["P1"]),
    lambda r: r["judgments"][0].update(quote="Fabricated text"),
    lambda r: r["judgments"][0].pop("speaker"),
    lambda r: r["judgments"][0].update(rationale=" "),
    lambda r: r["judgments"][0].update(treatment="looks_really_good"),
    lambda r: r["judgments"][0].update(temporal_status="already_done_hopefully"),
])
def test_incomplete_duplicate_or_fabricated_response_rejected(mutate):
    request = build_article_request(record(), definitions())
    parsed = response(request)
    mutate(parsed)
    with pytest.raises(ValueError):
        materialize_assessment(request, parsed)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(version_id="wrong"),
    lambda r: r["record"].update(body="A changed article."),
    lambda r: r["record"].update(version_id="wrong"),
    lambda r: r["definitions"]["questions"][0].update(definition_draft="Changed boundary."),
    lambda r: r["definitions"]["questions"][0].update(question_exact="Changed original."),
    lambda r: r["passage_catalog"]["P1"].update(quote="Fabricated quotation"),
    lambda r: r["model_input"]["data"].update(retained_article={}),
    lambda r: r.update(request_sha256="wrong"),
])
def test_request_source_definition_catalog_and_prompt_drift_rejected(mutate):
    request = build_article_request(record(), definitions())
    parsed = response(request)
    mutate(request)
    with pytest.raises(ValueError):
        materialize_assessment(request, parsed)


@pytest.mark.parametrize("body", ["", "  \n\t", "unknown", "Video", "1234", "None"])
def test_missing_placeholder_or_non_article_body_keeps_all_questions_unknown(body):
    source = record(body, retrievable=False)
    request = build_article_request(source, definitions())
    assert request["status"] == "not_requested" and request["model_input"] is None
    assert request["record"]["body"] == body
    result = materialize_assessment(request)
    assert result["processing_status"] == "not_requested"
    assert all(j["membership"] == "unknown" and j["article_membership"] == "uncertain"
               for j in result["judgments"])
    with pytest.raises(ValueError, match="not_requested"):
        materialize_assessment(request, {"judgments": []})


def test_error_body_issue_skips_without_inventing_a_negative():
    request = build_article_request(record(issues=[{"code": "body_capture_error", "severity": "error"}]),
                                    definitions())
    assert request["reason"] == "body_error"
    assert len(materialize_assessment(request)["judgments"]) == 24


@pytest.mark.parametrize("body", ["Error fetching URL: https://example.org/ad",
                                "Failed to download article", "404 Not Found"])
def test_short_capture_error_text_is_not_sent_as_an_article(body):
    request = build_article_request(record(body, retrievable=False), definitions())
    assert request["reason"] == "body_error_placeholder"
    assert request["status"] == "not_requested" and request["model_input"] is None
    assert all(j["membership"] == "unknown" for j in materialize_assessment(request)["judgments"])


def test_over_budget_never_truncates_or_creates_provider_request():
    body = "Beginning.\n\n" + "Content with unicode 中文💡. " * 80 + "\n\nUnique ending."
    source = record(body)
    request = build_article_request(source, definitions(), max_input_tokens=1)
    assert request["status"] == "not_requested"
    assert request["reason"] == "input_token_budget_exceeded"
    assert request["record"]["body"] == body
    assert request["model_input"] is None and request["input_token_count"] > 1
    assert any(p["quote"] == "Unique ending." for p in request["passage_catalog"].values())
    assert all(j["membership"] == "unknown" for j in materialize_assessment(request)["judgments"])


def test_partial_article_not_found_is_uncertain_and_quality_ranges_are_retained():
    source = record(issues=[{"code": "body_partial_recovery", "severity": "review"}],
                    raw={"body_recovery": {"coverage": "partial"}})
    request = build_article_request(source, definitions())
    assert request["status"] == "ready"
    result = materialize_assessment(request, response(request))
    assert result["judgments"][0]["membership"] == "not_found"
    assert result["judgments"][0]["article_membership"] == "uncertain"
    assert result["quality_metadata"]["raw"]["body_recovery"]["coverage"] == "partial"
    assert result["quality_metadata"]["issues"] == source["payload"]["issues"]


def test_support_outside_allowed_range_is_retained_but_not_publishable():
    source = record("Trusted text.\n\nNot trusted footer.", retrieval_end=len("Trusted text."))
    request = build_article_request(source, definitions())
    parsed = response(request)
    parsed["judgments"][5].update(support_passage_ids=["P2"], limiting_passage_ids=[])
    result = materialize_assessment(request, parsed)
    item = result["judgments"][5]
    assert item["support_evidence"][0]["quote"] == "Not trusted footer."
    assert item["support_evidence"][0]["eligible_source_evidence"] is False
    assert item["support_evidence"][0]["evidence_status"] == "outside_accepted_source_scope_not_publishable"
    assert item["article_membership"] == "uncertain"


def test_unicode_and_repeated_identical_quotes_keep_distinct_original_offsets():
    body = "中文💡—A promise.\n\nSame promise.\n\nSame promise."
    request = build_article_request(record(body), definitions())
    catalog = request["passage_catalog"]
    assert catalog["P2"]["quote"] == catalog["P3"]["quote"] == "Same promise."
    assert catalog["P2"]["start"] != catalog["P3"]["start"]
    for passage in catalog.values():
        assert body[passage["start"]:passage["end"]] == passage["quote"]


def test_ready_without_response_is_not_processed_with_24_unknowns():
    request = build_article_request(record(), definitions())
    result = materialize_assessment(request)
    assert result["processing_status"] == "not_processed"
    assert result["response_received"] is False
    assert len(result["judgments"]) == 24
    assert all(j["membership"] == "unknown" for j in result["judgments"])


@pytest.mark.parametrize("change", [{"countable": False}, {"dataset": "social"},
                                    {"retrievable": "true"}])
def test_invalid_or_outside_native_admission_refused(change):
    with pytest.raises(ValueError):
        build_article_request(record(**change), definitions())


def test_complete_definition_original_text_and_source_binding_required():
    for mutate in (lambda d: d["questions"].pop(),
                   lambda d: d["questions"][0].update(question_id="Q02"),
                   lambda d: d["questions"][0].update(source_paragraph_exact="Changed original"),
                   lambda d: d.update(status="approved")):
        draft = definitions()
        mutate(draft)
        with pytest.raises(ValueError):
            build_article_request(record(), draft)


def test_q15_occurrence_and_consensus_have_separate_source_evidence():
    request = build_article_request(record("Climate change occurs.\n\nA speaker disputes the scientific consensus."),
                                    definitions())
    parsed = response(request)
    parsed["judgments"][5].update(membership="not_found", support_passage_ids=[], limiting_passage_ids=[])
    parsed["judgments"][14].update(membership="relevant", support_passage_ids=["P1"],
                                   consensus_position="skepticism_of_consensus", consensus_passage_ids=["P2"])
    result = materialize_assessment(request, parsed)
    q15 = result["judgments"][14]
    assert q15["support_evidence"][0]["quote"] == "Climate change occurs."
    assert q15["consensus_evidence"][0]["quote"] == "A speaker disputes the scientific consensus."
    assert q15["consensus_position"] == "skepticism_of_consensus"
    assert result["client_approval"] is False


@pytest.mark.parametrize("change", [
    {"consensus_position": "consistent_with_consensus", "consensus_passage_ids": []},
    {"consensus_position": "mixed", "consensus_passage_ids": ["P999"]},
    {"consensus_position": "mixed", "consensus_passage_ids": ["P1", "P1"]},
])
def test_q15_specific_consensus_must_select_valid_unique_real_passages(change):
    request = build_article_request(record(), definitions())
    parsed = response(request)
    parsed["judgments"][14].update(membership="relevant", support_passage_ids=["P1"], **change)
    with pytest.raises(ValueError):
        materialize_assessment(request, parsed)


def test_non_q15_and_not_found_q15_cannot_invent_consensus_result():
    request = build_article_request(record(), definitions())
    for index in (0, 14):
        parsed = response(request)
        parsed["judgments"][index].update(consensus_position="mixed", consensus_passage_ids=["P1"])
        with pytest.raises(ValueError):
            materialize_assessment(request, parsed)


@pytest.mark.parametrize("membership", ["relevant", "uncertain"])
def test_q15_occurrence_without_clear_consensus_preserves_uncertain_branch(membership):
    request = build_article_request(record(), definitions())
    parsed = response(request)
    q15 = parsed["judgments"][14]
    q15.update(membership=membership, support_passage_ids=["P1"] if membership == "relevant" else [])
    with pytest.raises(ValueError, match="consensus_must_remain"):
        materialize_assessment(request, parsed)
    q15.update(consensus_position="uncertain")
    result = materialize_assessment(request, parsed)
    assert result["judgments"][14]["consensus_position"] == "uncertain"
    assert result["judgments"][14]["consensus_evidence"] == []


def test_serialized_response_duplicate_keys_and_model_extra_fields_refused():
    request = build_article_request(record(), definitions())
    parsed = response(request)
    assert materialize_assessment(request, json.dumps(parsed))["response_received"] is True
    duplicate = '{"judgments":[],"judgments":' + json.dumps(parsed["judgments"]) + "}"
    with pytest.raises((ValueError, RuntimeError)):
        materialize_assessment(request, duplicate)
    extra = deepcopy(parsed)
    extra["approval"] = True
    with pytest.raises(ValueError):
        materialize_assessment(request, extra)
