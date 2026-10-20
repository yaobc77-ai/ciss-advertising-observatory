"""Verify trusted task limits reach generation and its receipt without real calls."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from observatory.config import Settings
from observatory.models import Evidence
from observatory.prompts import ANSWER_SYSTEM, PROMPT_POLICY_VERSION
from observatory.rag import Rag


@pytest.mark.parametrize("question,task", [
    ("Which ads mention a new fuel?", "content_mentions"),
    ("Which ads present a new fuel as clean burning?", "content_framing"),
    ("What disclosure language identifies this native ad?", "disclosure"),
])
def test_generation_carries_task_and_subset_limits_to_request_and_audit(question, task):
    original = "Company A says it is developing a new fuel."
    evidence = Evidence(
        evidence_id="e1", record_id="r1", version_id="v1", dataset="native",
        title="Ad A", text=original, start=15, end=15 + len(original),
    )
    connection = MagicMock()
    requests = []

    def respond(**request):
        requests.append(request)
        # Synthetic output verifies plumbing and source binding, not semantic quality.
        output = request["text_format"].model_validate({
            "status": "answered",
            "claims": [{"passage_id": "Q1", "text": "The advertisement describes a planned fuel."}],
            "summary": [{"text": "This retrieved advertisement describes a plan.", "citation_indices": [1]}],
            "sections": [{"title": "Retrieved evidence", "citation_indices": [1]}],
        })
        return SimpleNamespace(
            status="completed", model="offline-fixture", output_parsed=output,
            usage=SimpleNamespace(
                input_tokens=10, output_tokens=5,
                input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                model_dump=lambda: {"input_tokens": 10, "output_tokens": 5},
            ),
        )

    rag = Rag(
        SimpleNamespace(validate_evidence=lambda item: True, connect=lambda: connection),
        Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=Mock(side_effect=respond))),
    )
    rag.budget = SimpleNamespace(settle=Mock(), uncertain=Mock())

    answer = rag.generate(question, [evidence], "offline-test", "reserved")

    request = requests[0]
    context = json.loads(request["input"][1]["content"])
    assert request["input"][0]["content"].startswith(ANSWER_SYSTEM)
    assert context["task_contract"]["task"] == task
    assert context["task_contract"]["content_condition"]
    assert context["retrieval_scope"] == {
        "coverage": "retrieved_subset", "complete_matching_list": False,
        "reviewed_content_membership": False,
    }
    receipt = rag.budget.settle.call_args.args[2]["observatory_request"]
    assert receipt["task_contract"] == context["task_contract"]
    assert receipt["retrieval_scope"] == context["retrieval_scope"]
    assert receipt["prompt_policy"] == PROMPT_POLICY_VERSION
    assert answer.citations[0].quote == original
    assert answer.citations[0].evidence_id == evidence.evidence_id
    assert (evidence.start, evidence.end) == (15, 15 + len(original))
    rag.budget.uncertain.assert_not_called()
