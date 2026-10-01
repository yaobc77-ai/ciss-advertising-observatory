"""Offline citation-binding checks; these do not measure semantic correctness."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from openai.lib._pydantic import to_strict_json_schema

from observatory.config import Settings
from observatory.language import language_hint
from observatory.models import Answer, Evidence
from observatory.rag import (
    Rag,
    materialize_selections,
    quote_catalog,
    selection_schema,
    validate_answer,
)


def sources():
    rows = []
    for number, (sponsor, text) in enumerate([
        ("Company A", "Company A says it plans carbon capture for its industrial plant."),
        ("Company B", "Company B says it plans renewable energy investment."),
    ], 1):
        rows.append(Evidence(
            evidence_id=f"e{number}", record_id=f"r{number}",
            version_id=f"v{number}", dataset="native", title=f"Ad {number}",
            sponsor=sponsor, text=text, start=20, end=20 + len(text),
        ))
    return rows


def selected():
    return {
        "status": "answered",
        "claims": [
            {"passage_id": "Q1", "text": "Company A's advertisement describes a planned industrial carbon-capture project."},
            {"passage_id": "Q2", "text": "Company B's advertisement describes planned renewable-energy investment."},
        ],
        "summary": [{
            "text": "In these retrieved advertisements, Company A emphasizes planned industrial carbon capture, while Company B emphasizes planned renewable-energy investment.",
            "citation_indices": [1, 2],
        }],
        "sections": [
            {"title": "Company A", "citation_indices": [1]},
            {"title": "Company B", "citation_indices": [2]},
        ],
    }


def validate_payload(payload):
    ev = sources()
    catalog = quote_catalog(ev)
    parsed = selection_schema(catalog).model_validate(payload)
    return validate_answer(materialize_selections(parsed, catalog), ev)


def test_summary_and_sections_reference_exact_original_citations():
    evidence = sources()
    before = [e.model_dump() for e in evidence]
    catalog = quote_catalog(evidence)
    parsed = selection_schema(catalog).model_validate(selected())
    answer = validate_answer(materialize_selections(parsed, catalog), evidence, 0.003)

    assert answer.summary[0].citation_indices == [1, 2]
    assert [s.title for s in answer.sections] == ["Company A", "Company B"]
    assert [p.citation_indices for p in answer.cited_claims] == [[1], [2]]
    assert answer.cited_claims[0].text + " [1]" in answer.answer
    assert [c.quote for c in answer.citations] == [e.text for e in evidence]
    assert [c.evidence_id for c in answer.citations] == ["e1", "e2"]
    assert [e.model_dump() for e in evidence] == before
    assert answer.cost_usd == 0.003
    assert answer.external_research == {}


@pytest.mark.parametrize("refs", [[], [0], [3], [1, 1], [-1]])
def test_summary_rejects_missing_duplicate_or_out_of_range_citations(refs):
    payload = selected()
    payload["summary"][0]["citation_indices"] = refs
    with pytest.raises(ValueError, match="citation"):
        validate_payload(payload)


@pytest.mark.parametrize("refs", [[True], ["1"], [1.0]])
def test_structure_citation_numbers_are_strict_integers(refs):
    payload = selected()
    payload["summary"][0]["citation_indices"] = refs
    with pytest.raises(ValueError):
        validate_payload(payload)


@pytest.mark.parametrize("sections", [
    [{"title": "Only A", "citation_indices": [1]}],
    [{"title": "A", "citation_indices": [1, 2]}, {"title": "B", "citation_indices": [2]}],
    [{"title": "A", "citation_indices": [1]}, {"title": "A", "citation_indices": [2]}],
    [{"title": "  ", "citation_indices": [1, 2]}],
])
def test_sections_cannot_omit_duplicate_or_hide_claims(sections):
    payload = selected()
    payload["sections"] = sections
    with pytest.raises(ValueError):
        validate_payload(payload)


def test_summary_cannot_omit_a_company_that_has_an_answer_section():
    payload = selected()
    payload["summary"][0]["citation_indices"] = [1]
    with pytest.raises(ValueError, match="omits"):
        validate_payload(payload)


@pytest.mark.parametrize("field", ["summary", "sections"])
def test_new_explicit_output_cannot_drop_its_structure(field):
    payload = selected()
    payload[field] = []
    with pytest.raises(ValueError, match="Incomplete"):
        validate_payload(payload)


def test_summary_cannot_invent_inline_citation_numbers():
    payload = selected()
    payload["summary"][0]["text"] += " [999]"
    with pytest.raises(ValueError, match="structured references"):
        validate_payload(payload)


def test_historical_selection_fixture_and_saved_answer_remain_loadable():
    payload = selected()
    del payload["summary"]
    del payload["sections"]
    answer = validate_payload(payload)
    assert answer.status == "answered"
    assert answer.summary == [] and answer.sections == []
    restored = Answer.model_validate({
        "status": "answered", "answer": "A historical answer."
    })
    assert restored.summary == [] and restored.external_research == {}


def test_new_api_schema_requires_summary_and_sections():
    schema = to_strict_json_schema(selection_schema(quote_catalog(sources())))
    assert set(schema["required"]) == {"status", "claims", "summary", "sections"}
    assert schema["additionalProperties"] is False


def test_insufficient_evidence_never_publishes_summary_or_sections():
    payload = selected()
    payload["status"] = "insufficient_evidence"
    answer = validate_payload(payload)
    assert answer.status == "insufficient_evidence"
    assert answer.summary == answer.sections == answer.cited_claims == []
    assert not answer.citations


def test_foreign_language_summary_is_blocked_even_when_claims_match():
    payload = selected()
    payload["summary"][0]["text"] = (
        "Selon cette publicité, le projet de captage du carbone reste à l'étude "
        "et ses coûts de construction sont encore incertains."
    )
    ev = sources()
    parsed = selection_schema(quote_catalog(ev)).model_validate(payload)
    answer = validate_answer(
        materialize_selections(parsed, quote_catalog(ev)), ev,
        target=language_hint("How do the advertisements describe the planned projects?"),
    )
    assert answer.failure_reason == "answer_language_mismatch"
    assert answer.summary == [] and answer.citations == []


@pytest.mark.parametrize("listener_fails", [False, True])
def test_generation_persists_structure_and_emits_real_validation_stage(listener_fails):
    ev = sources()
    connection = MagicMock()

    def respond(**request):
        return SimpleNamespace(
            status="completed", model="offline-fixture",
            output_parsed=request["text_format"].model_validate(selected()),
            usage=SimpleNamespace(
                input_tokens=10, output_tokens=5,
                input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                model_dump=lambda: {"input_tokens": 10, "output_tokens": 5},
            ),
        )

    rag = Rag(SimpleNamespace(
        validate_evidence=lambda e: True, connect=lambda: connection,
    ), Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=Mock(side_effect=respond))))
    rag.budget = SimpleNamespace(settle=Mock(), uncertain=Mock())
    progress = []

    def notify(stage):
        progress.append(stage)
        if listener_fails:
            raise RuntimeError("Disconnected browser")

    answer = rag.generate("Compare the advertisements.", ev, "test", "reserved", progress=notify)
    assert progress == ["citations"]
    assert answer.summary and answer.sections
    saved = connection.__enter__.return_value.execute.call_args.args[1][2].obj
    assert saved["summary"] == selected()["summary"]
    assert saved["sections"] == selected()["sections"]
    rag.budget.uncertain.assert_not_called()
