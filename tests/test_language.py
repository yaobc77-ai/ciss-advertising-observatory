"""Offline language regressions; these checks do not judge factual support."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from lingua import Language

import observatory.language as language_module
from observatory.language import check_claim_languages, language_hint
from observatory.models import Evidence
from observatory.rag import GroundedClaim, ModelAnswer, validate_answer

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "language_regressions.json").read_text(
        encoding="utf-8"
    )
)
ENGLISH_QUESTION = (
    "Please explain the proposed carbon capture project and its stated limitations."
)
CHINESE_QUESTION = "请说明这篇广告如何描述项目计划，以及它对成本和减排效果提出了哪些限制。"
ENGLISH_CLAIM = (
    "The advertisement describes a proposed carbon capture project and explains "
    "that its costs and actual emissions reductions remain uncertain."
)
CHINESE_CLAIM = (
    "这篇广告描述了一项仍在规划中的碳捕集项目，"
    "并指出项目的建设成本和实际减排效果仍然存在不确定性。"
)
FRENCH_CLAIM = (
    "Selon cette publicité, le projet de captage du carbone reste à l'étude "
    "et ses coûts de construction sont encore incertains."
)
ENGLISH_QUOTE = (
    "The advertisement describes a proposed carbon capture project. "
    "Its costs and actual emissions reductions remain uncertain."
)
CHINESE_QUOTE = "广告描述了一项仍在规划中的碳捕集项目，并指出建设成本和实际减排效果仍存在不确定性。"


def evidence(text):
    return Evidence(
        evidence_id="language-evidence",
        record_id="selected-record",
        version_id="preserved-version",
        dataset="native",
        title="Synthetic language-only fixture",
        text=text,
        start=117,
        end=117 + len(text),
        url="",  # Preserve an already applied source-link visibility setting.
    )


def model_answer(text, ev):
    return ModelAnswer(
        status="answered",
        claims=[GroundedClaim(text=text, evidence_id=ev.evidence_id, quote=ev.text)],
    )


def historical_claims(case):
    """Remove only the displayed citation suffix; preserve the original fixture."""
    blocks = case["answer"].split("\n\n")
    assert len(blocks) == len(case["citations"])
    claims = []
    for number, (block, citation) in enumerate(zip(blocks, case["citations"]), 1):
        suffix = f" [{number}]"
        assert block.endswith(suffix)
        claims.append(GroundedClaim(text=block[: -len(suffix)], **citation))
    return claims


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_recorded_wrong_language_is_blocked_without_changing_cost_or_evidence(case):
    # These are three specific observed failures, not an estimated error rate.
    assert re.fullmatch(r"[0-9a-f]{64}", FIXTURE["source_sha256"])
    target = language_hint(case["question"])
    assert target["code"] == case["expected_question_language"] == "en"
    assert language_hint(case["answer"])["code"] == case["observed_answer_language"]
    parsed = ModelAnswer(status="answered", claims=historical_claims(case))
    before = parsed.model_dump()
    selected = [Evidence.model_validate(e) for e in case["cited_evidence"]]
    evidence_before = [e.model_dump() for e in selected]

    result = validate_answer(
        parsed, selected, case["reported_answer_cost_usd"], target=target
    )

    assert result.status == "service_unavailable"
    assert result.failure_reason == "answer_language_mismatch"
    assert result.language_check["status"] == "mismatch"
    assert result.cost_usd == case["reported_answer_cost_usd"]
    assert result.citations == []
    assert [e.model_dump() for e in result.evidence] == evidence_before
    assert parsed.model_dump() == before  # The unmodified generation stays auditable.
    assert all(c.text not in result.answer for c in parsed.claims)


@pytest.mark.parametrize(
    "question,claim,quote,expected",
    [
        (ENGLISH_QUESTION, ENGLISH_CLAIM, ENGLISH_QUOTE, "en"),
        (CHINESE_QUESTION, CHINESE_CLAIM, ENGLISH_QUOTE, "zh"),
        (ENGLISH_QUESTION, ENGLISH_CLAIM, CHINESE_QUOTE, "en"),
        (CHINESE_QUESTION, CHINESE_CLAIM, CHINESE_QUOTE, "zh"),
    ],
    ids=["en-en", "zh-en-source", "en-zh-source", "zh-zh"],
)
def test_only_generated_claim_language_is_checked_and_source_quote_is_unchanged(
    question, claim, quote, expected
):
    target = language_hint(question)
    assert target["code"] == expected
    ev = evidence(quote)
    before = ev.model_dump()

    result = validate_answer(model_answer(claim, ev), [ev], 0.0123, target=target)

    assert result.status == "answered"
    assert result.language_check["status"] == "match"
    assert result.citations[0].quote == quote
    assert result.evidence[0].model_dump() == before
    assert result.cost_usd == 0.0123


def test_one_french_claim_is_not_hidden_by_five_english_claims():
    audit = check_claim_languages(
        [ENGLISH_CLAIM] * 5 + [FRENCH_CLAIM], language_hint(ENGLISH_QUESTION)
    )
    assert all(hint["code"] == "en" for hint in audit["claims"][:5])
    assert audit["claims"][-1]["code"] == "fr"
    assert audit["status"] == "mismatch"


def test_foreign_claim_blocks_even_when_the_combined_hint_matches(monkeypatch):
    target = language_hint(ENGLISH_QUESTION)

    def controlled_hint(text):
        code = "fr" if text == FRENCH_CLAIM else "en"
        return {"code": code, "name": code, "letters": 100, "margin": 0.8}

    monkeypatch.setattr(language_module, "language_hint", controlled_hint)
    audit = check_claim_languages([ENGLISH_CLAIM, FRENCH_CLAIM], target)
    assert audit["combined"]["code"] == "en"
    assert audit["status"] == "mismatch"


@pytest.mark.parametrize("text", ["CCS?", "2025 20% CO2", "为什么？", "用中文解释", "", "  "])
def test_short_acronyms_numbers_and_chinese_do_not_force_a_language(text, monkeypatch):
    def detector_must_not_run():
        raise AssertionError("A short input must stay inconclusive before detection")

    monkeypatch.setattr(language_module, "detector", detector_must_not_run)
    hint = language_hint(text)
    assert hint["code"] is None and hint["margin"] is None
    assert hint["letters"] == sum(c.isalpha() for c in text)


def test_unicode_letters_are_counted_without_using_utf8_byte_length():
    text = "请说明这篇广告如何描述项目计划以及成本和减排效果的限制"
    assert len(text) >= 20
    hint = language_hint(text)
    assert hint["letters"] == len(text)
    assert hint["code"] == "zh"


def test_low_margin_is_inconclusive_even_when_english_is_top_ranked(monkeypatch):
    # Synthetic detector outputs exercise uncertainty handling, not accuracy.
    monkeypatch.setattr(
        language_module,
        "detector",
        lambda: SimpleNamespace(
            compute_language_confidence_values=lambda _: [
                SimpleNamespace(language=Language.ENGLISH, value=0.54),
                SimpleNamespace(language=Language.FRENCH, value=0.46),
            ]
        ),
    )
    hint = language_hint(ENGLISH_CLAIM)
    assert hint["code"] is None and hint["name"] is None
    assert hint["margin"] == pytest.approx(0.08)
    audit = check_claim_languages(
        [ENGLISH_CLAIM], {"code": "en", "name": "English"}
    )
    assert audit["status"] == "inconclusive"


def test_english_proper_names_do_not_cause_a_false_language_rejection():
    text = (
        "According to Patrick Pouyanné, TotalEnergies proposes a carbon capture "
        "project at Lacq."
    )
    # Names are removed before detection, so the remaining prose reads as English.
    audit = check_claim_languages([text], language_hint(ENGLISH_QUESTION))
    assert audit["status"] in {"match", "inconclusive"}
    ev = evidence(ENGLISH_QUOTE)
    result = validate_answer(
        model_answer(text, ev), [ev], target=language_hint(ENGLISH_QUESTION)
    )
    assert result.status == "answered"
    assert result.language_check["status"] in {"match", "inconclusive"}


def test_chinese_prose_with_english_company_names_keeps_its_language():
    text = (
        "这篇广告介绍了 TotalEnergies 在 Baytown 的 blue hydrogen 项目，"
        "并明确说明它仍处于规划阶段。"
    )
    audit = check_claim_languages([text], language_hint(CHINESE_QUESTION))
    assert audit["status"] == "match"
    assert audit["claims"][0]["code"] == "zh"


@pytest.mark.parametrize("target", [None, language_hint("CCS?"), language_hint("用中文解释")])
def test_unknown_target_remains_inconclusive_instead_of_claiming_validation(target):
    audit = check_claim_languages([FRENCH_CLAIM], target)
    assert audit["status"] == "inconclusive"
    ev = evidence(ENGLISH_QUOTE)
    result = validate_answer(model_answer(FRENCH_CLAIM, ev), [ev], target=target)
    assert result.status == "answered"
    assert result.language_check["status"] == "inconclusive"
    assert result.citations[0].quote == ev.text


def test_short_claim_is_not_certified_by_a_longer_matching_claim():
    audit = check_claim_languages(
        [ENGLISH_CLAIM, "CO2"], language_hint(ENGLISH_QUESTION)
    )
    assert audit["combined"]["code"] == "en"
    assert audit["claims"][1]["code"] is None
    assert audit["status"] == "inconclusive"


def test_model_language_declaration_does_not_override_its_actual_prose():
    ev = evidence(ENGLISH_QUOTE)
    parsed = ModelAnswer.model_validate(
        {
            "status": "answered",
            "language": "en",  # Untrusted extra model metadata is no proof.
            "claims": [
                {"text": FRENCH_CLAIM, "evidence_id": ev.evidence_id, "quote": ev.text}
            ],
        }
    )
    result = validate_answer(parsed, [ev], target=language_hint(ENGLISH_QUESTION))
    assert result.status == "service_unavailable"
    assert result.language_check["status"] == "mismatch"


def test_inconclusive_language_does_not_bypass_citation_validation():
    ev = evidence(ENGLISH_QUOTE)
    parsed = model_answer("CO2", ev)
    parsed.claims[0].quote = "This invented quote is absent from the source."
    with pytest.raises(ValueError, match="Unverifiable citation"):
        validate_answer(parsed, [ev], target=language_hint("CCS?"))


QUOTED_TITLE = "Embracing Net Zero Carbon Emissions Aspirations"


def test_quoted_english_title_does_not_flag_english_claim():
    # v1 misread this English claim as Latin because of the quoted title.
    claim = (f"The advertisement “{QUOTED_TITLE}” mentions carbon capture and "
             "storage (CCS) as an emissions-abatement solution.")
    target = language_hint(ENGLISH_QUESTION)
    assert check_claim_languages([claim], target, source_titles=[QUOTED_TITLE])["status"] == "match"


@pytest.mark.parametrize("claim", [
    f"El anuncio “{QUOTED_TITLE}” menciona la captura y almacenamiento de carbono (CCS) como solución.",
    f"该广告“{QUOTED_TITLE}”提到碳捕集与封存（CCS）是一种减排方案，并说明了项目限制。",
])
def test_quoted_title_does_not_hide_a_real_language_switch(claim):
    target = language_hint(ENGLISH_QUESTION)
    assert check_claim_languages([claim], target, source_titles=[QUOTED_TITLE])["status"] == "mismatch"


def test_english_title_inside_chinese_claim_still_matches_chinese():
    claim = f"这篇广告“{QUOTED_TITLE}”把碳捕集与封存描述为一种减排方案，但没有说明实际减排量。"
    target = language_hint(CHINESE_QUESTION)
    assert check_claim_languages([claim], target, source_titles=[QUOTED_TITLE])["status"] == "match"


def test_foreign_generated_quote_is_checked_independently_of_english_framing():
    claim = ENGLISH_CLAIM * 5 + f' “{FRENCH_CLAIM}”'
    audit = check_claim_languages([claim], language_hint(ENGLISH_QUESTION))
    assert audit["quoted_prose"][0]["code"] == "fr"
    assert audit["title_spans_ignored"] == 0
    assert audit["status"] == "mismatch"


def test_untrusted_short_quote_does_not_receive_a_language_certification():
    claim = ENGLISH_CLAIM + ' “Bonjour tout le monde”'
    audit = check_claim_languages([claim], language_hint(ENGLISH_QUESTION))
    assert audit["quoted_prose"][0]["code"] is None
    assert audit["status"] == "inconclusive"


def test_only_exact_selected_source_title_is_exempt():
    claim = ENGLISH_CLAIM + f' “{FRENCH_CLAIM}”'
    target = language_hint(ENGLISH_QUESTION)
    assert check_claim_languages([claim], target, source_titles=[FRENCH_CLAIM])["status"] == "match"
    assert check_claim_languages([claim], target, source_titles=[FRENCH_CLAIM + " revised"])["status"] == "mismatch"


def test_validation_passes_selected_titles_without_exempting_generated_quotes():
    ev = evidence(ENGLISH_QUOTE)
    ev.title = QUOTED_TITLE
    claim = f'The advertisement “{QUOTED_TITLE}” describes a proposed carbon capture project.'
    result = validate_answer(model_answer(claim, ev), [ev], target=language_hint(ENGLISH_QUESTION))
    assert result.status == "answered"
    assert result.language_check["title_spans_ignored"] == 1
    foreign = validate_answer(model_answer(claim + f' “{FRENCH_CLAIM}”', ev), [ev], target=language_hint(ENGLISH_QUESTION))
    assert foreign.status == "service_unavailable"
    assert foreign.failure_reason == "answer_language_mismatch"


def test_fully_quoted_foreign_claim_is_still_checked():
    claim = "“El anuncio menciona la captura y almacenamiento de carbono como una solución para reducir emisiones.”"
    assert check_claim_languages([claim], language_hint(ENGLISH_QUESTION))["status"] == "mismatch"


REPETITIVE_ENGLISH_CLAIMS = [
    "The advertisement “CCUS, the industry that will change industry” mentions carbon capture and storage technologies.",
    "The advertisement “Creating a Net-Zero World” mentions innovations in carbon capture, utilization and storage.",
    "The advertisement “Can R&D solve the daunting challenges of taking carbon out of the equation?” mentions carbon capture, utilization and storage technology.",
    "The advertisement “Embracing Net Zero Carbon Emissions Aspirations” mentions carbon capture and storage as an emissions-abatement solution.",
    "The advertisement “Moving Toward Net Zero Carbon Emissions” mentions carbon capture and storage.",
    "The advertisement “Moving Toward Net Zero Carbon Emissions” mentions pursuing carbon capture and storage to reduce emissions.",
]


def test_joined_repetitive_english_claims_are_not_rejected_as_latin():
    # Recorded 2026-10-01: each claim English, joined title-free text read as Latin.
    titles = [claim.split("“")[1].split("”")[0] for claim in REPETITIVE_ENGLISH_CLAIMS]
    target = language_hint("How many ads mention carbon capture?")
    result = check_claim_languages(REPETITIVE_ENGLISH_CLAIMS, target, source_titles=titles)
    assert result["status"] == "match"


def test_one_switched_claim_among_english_claims_is_still_a_mismatch():
    claims = [*REPETITIVE_ENGLISH_CLAIMS[:3],
              "El anuncio menciona la captura y el almacenamiento de carbono como una solución para reducir emisiones."]
    target = language_hint("How many ads mention carbon capture?")
    assert check_claim_languages(claims, target)["status"] == "mismatch"


def test_short_inconclusive_claims_fall_back_to_the_joined_text():
    claims = ["Shell: CCS.", "BP: hydrogen.", "Eni: biofuels."]
    result = check_claim_languages(claims, language_hint(ENGLISH_QUESTION))
    assert all(h["code"] is None for h in result["claims"])
    combined = result["combined"]["code"]
    expected = "inconclusive" if combined is None else ("match" if combined == "en" else "mismatch")
    assert result["status"] == expected


def test_a_names_heavy_english_summary_is_not_read_as_another_language():
    text = ("Episode 1 guests: Bernard Looney of bp and Alison Rose of NatWest Group. "
            "Episode 2 guests: Søren Skou of Maersk and Charles Haskell of Lloyd's Register.")
    assert check_claim_languages([text], language_hint(ENGLISH_QUESTION))["status"] != "mismatch"


def test_prose_in_another_language_is_still_rejected_after_names_are_removed():
    text = "La publicité de TotalEnergies dit que le gaz naturel est important pour la transition énergétique."
    assert check_claim_languages([text], language_hint(ENGLISH_QUESTION))["status"] == "mismatch"
    chinese = "这则由 Chevron 赞助的原生广告说，女性占美国劳动力的百分之四十八，但只占科学技术工程数学岗位的四分之一左右。"
    assert check_claim_languages([chinese], language_hint(ENGLISH_QUESTION))["status"] == "mismatch"


def test_inconclusive_latin_question_requires_the_english_interface_default(monkeypatch):
    from observatory.language import answer_language

    question = "Which posters show tidal kites as cheap power?"
    original = language_module.language_hint
    monkeypatch.setattr(language_module, "language_hint",
                        lambda text: {**original(text), "code": None, "name": None} if text == question else original(text))
    target = answer_language(question)
    assert target["basis"] == "interface_default"
    assert target["code"] == "en"
    spanish = "El cartel presenta las cometas de marea como una fuente de energía barata para la ciudad."
    assert check_claim_languages([spanish], target)["status"] == "mismatch"


def test_inconclusive_non_latin_question_is_not_forced_into_english(monkeypatch):
    from observatory.language import answer_language

    monkeypatch.setattr(language_module, "language_hint",
                        lambda text: {"code": None, "name": None, "letters": 9, "margin": None})
    assert answer_language("哪些海报提到潮汐风筝？")["code"] is None


@pytest.mark.parametrize("source, quote", [
    ("Harbor kites &amp; ferry lines carry the whole town every summer.",
     "Harbor kites & ferry lines carry the whole town every summer."),
    ("The partnership is establishing theNorth Canal Kite Centre for the whole region.",
     "The partnership is establishing the North Canal Kite Centre for the whole region."),
    ("This content is custom content commissioned by Pineglass Energy for the harbor.",
     "This content is custom content commissioned by [赞助商] for the harbor."),
])
def test_a_verbatim_english_source_quote_in_a_chinese_answer_is_source_text(source, quote):
    # B1K: entities, a lost space or a bracketed edit made a quoted source sentence read as generated English.
    claim = f"这篇广告说港口风筝线路覆盖全镇，并且明确写道：“{quote}”这句话说明了它的定位。"
    audit = check_claim_languages([claim], language_hint(CHINESE_QUESTION), source_texts=[source])
    assert audit["quoted_prose"] == [] and audit["title_spans_ignored"] == 1
    assert audit["status"] != "mismatch"


def test_an_altered_english_quote_is_still_checked_as_generated_prose():
    source = "Harbor kites will carry the whole town every summer, the pilots say."
    claim = "这篇广告说港口风筝覆盖全镇：“Harbor kites will carry every village and the whole region in winter.”"
    audit = check_claim_languages([claim], language_hint(CHINESE_QUESTION), source_texts=[source])
    assert audit["quoted_prose"][0]["code"] == "en"
    assert audit["status"] == "mismatch"
