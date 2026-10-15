import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score_answers.py"
spec = importlib.util.spec_from_file_location("score_answers", SCRIPT)
score_answers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_answers)


def review(qid, **fields):
    row = {"query_id": qid, "attempt_status": "completed", "checkable_claims": "", "supported_claims": "",
           "required_points": "", "covered_points": "", "context_supported_points": "", "citations": "",
           "correct_citations": "", "response_relevancy": "", "abstention_expected": "", "abstention_actual": ""}
    row.update({key: str(value) for key, value in fields.items()})
    return row


def test_ragas_style_ratios():
    report = score_answers.score([review("Q1", checkable_claims=4, supported_claims=3, required_points=2,
                                         covered_points=1, context_supported_points=2, citations=2,
                                         correct_citations=2, response_relevancy=0.8)], {"Q1": "content_single"})
    row = report["questions"][0]
    assert row["faithfulness"] == 0.75 and row["answer_correctness"] == 0.5
    assert row["context_recall"] == 1.0 and row["citation_precision"] == 1.0
    assert report["by_class"]["content_single"]["response_relevancy"]["mean"] == pytest.approx(0.8)


def test_answer_without_claims_is_unscored_not_perfect():
    row = score_answers.score([review("Q1", checkable_claims=0, supported_claims=0)], {})["questions"][0]
    assert row["faithfulness"] is None


def test_failed_attempt_stays_in_correctness_denominator():
    report = score_answers.score([review("Q1", attempt_status="error", required_points=2),
                                  review("Q2", required_points=2, covered_points=2)], {})
    assert report["overall"]["answer_correctness"]["mean"] == 0.5
    assert report["overall"]["failed"] == 1


def test_abstention_and_false_refusal():
    report = score_answers.score([review("N", abstention_expected="true", abstention_actual="true"),
                                  review("A", abstention_expected="false", abstention_actual="true")], {})
    assert report["overall"]["abstention_correct"] == {"rate": 1.0, "scored": 1}
    assert report["overall"]["false_refusal"] == {"rate": 1.0, "scored": 1}


@pytest.mark.parametrize("fields, message", [
    ({"checkable_claims": 1, "supported_claims": 2}, "exceeds"),
    ({"response_relevancy": 1.5}, "0..1"),
    ({"abstention_expected": "yes"}, "true/false"),
])
def test_invalid_reviews_rejected(fields, message):
    with pytest.raises(ValueError, match=message):
        score_answers.score([review("Q1", **fields)], {})


def test_duplicate_primary_rejected_and_retries_ignored():
    with pytest.raises(ValueError, match="more than one primary"):
        score_answers.score([review("Q1"), review("Q1")], {})
    report = score_answers.score([review("Q1"), review("Q1", is_primary="false")], {})
    assert report["overall"]["questions"] == 1
