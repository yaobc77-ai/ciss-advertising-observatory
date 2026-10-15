"""Question cues (a stated period, several sources) steer citation; no evidence is removed."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from observatory.config import Settings
from observatory.models import Evidence
from observatory.question_policy import (
    in_stated_period,
    several_sources_requested,
    stated_periods,
)
from observatory.rag import Rag


@pytest.mark.parametrize("question, expected", [
    ("What did the account post in September 2019?", [("2019-09-01", "2019-09-30")]),
    ("What did the account post in Sept. 2019?", [("2019-09-01", "2019-09-30")]),
    ("What did the company post on 23 September 2019?", [("2019-09-23", "2019-09-23")]),
    ("What was published September 25, 2019?", [("2019-09-25", "2019-09-25")]),
    ("Which ads ran in 2021?", [("2021-01-01", "2021-12-31")]),
    ("Compare ads in Feb 2020 and in 2021.", [("2020-02-01", "2020-02-29"), ("2021-01-01", "2021-12-31")]),
    ("该账号2019年9月发了什么？", [("2019-09-01", "2019-09-30")]),
])
def test_stated_periods_are_read_from_prepositional_dates(question, expected):
    assert [(p["date_from"], p["date_to"]) for p in stated_periods(question)] == expected


@pytest.mark.parametrize("question", [
    "What does the ad \"The 2015 Plan\" say?",           # year inside a quoted title
    "Submit proposals by 25 September 2019?",            # a deadline, not a period
    "Which ads ran in 2019-2021?",                        # ranges stay with the planner
    "What does the ad say about emissions?",
])
def test_no_period_without_a_stated_calendar_restriction(question):
    assert stated_periods(question) == []


def test_in_stated_period_is_unknown_for_undated_sources():
    periods = stated_periods("What was posted in September 2019?")
    assert in_stated_period(date(2019, 9, 23), periods) is True
    assert in_stated_period("2019-08-28", periods) is False
    assert in_stated_period(None, periods) is None
    assert in_stated_period(date(2019, 9, 23), []) is None


def _posts():
    text = "Submit your proposal by 25 September 2019."
    return [
        Evidence(evidence_id=f"e{n}", record_id=f"r{n}", version_id=f"v{n}", dataset="social",
                 title=f"Post {n}", sponsor="Company", account="Company", text=text,
                 start=0, end=len(text), published_at=day)
        for n, day in ((1, date(2019, 8, 28)), (2, date(2019, 9, 23)), (3, None))
    ]


def _generate(question):
    requests = []

    def respond(**request):
        requests.append(request)
        return SimpleNamespace(
            status="completed", model="offline-fixture",
            output_parsed=request["text_format"].model_validate({
                "status": "answered",
                "claims": [{"passage_id": "Q2", "text": "The post asks for proposals by 25 September 2019."}],
                "summary": [{"text": "The post gives a 25 September 2019 deadline.", "citation_indices": [1]}],
                "sections": [{"title": "Deadline", "citation_indices": [1]}],
            }),
            usage=SimpleNamespace(
                input_tokens=10, output_tokens=5,
                input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                model_dump=lambda: {"input_tokens": 10, "output_tokens": 5},
            ),
        )

    rag = Rag(SimpleNamespace(validate_evidence=lambda e: True, connect=lambda: MagicMock()),
              Settings(), client=SimpleNamespace(responses=SimpleNamespace(parse=Mock(side_effect=respond))))
    rag.budget = SimpleNamespace(settle=Mock(), uncertain=Mock())
    rag.generate(question, _posts(), "test", "reserved")
    (request,) = requests
    messages = request.get("input") or []
    system = request.get("instructions") or "".join(
        m["content"] for m in messages if m.get("role") in ("system", "developer"))
    payload = next(json.loads(m["content"]) for m in messages if m.get("role") == "user")
    return system, payload


def test_generation_marks_in_period_sources_and_keeps_all_evidence():
    system, payload = _generate("By what date did the account ask for proposals in September 2019?")
    assert payload["stated_periods"][0]["date_from"] == "2019-09-01"
    flags = {item["id"]: item.get("in_stated_period") for item in payload["evidence"]}
    assert flags == {"e1": False, "e2": True, "e3": None}
    assert "in_stated_period true" in system


def test_generation_without_a_period_is_unchanged():
    system, payload = _generate("By what date did the account ask for proposals?")
    assert "stated_periods" not in payload
    assert all("in_stated_period" not in item for item in payload["evidence"])
    assert "stated_periods" not in system


@pytest.mark.parametrize("question, expected", [
    ("What do the company's Forbes ads say about its chemicals unit? Cite each ad that describes it.", True),
    ("What does each post say about the deadline?", True),
    ("这些广告如何描述该项目？", True),
    ("该账号2031年5月发了哪些内容？", True),
    ("What does the advertisement say about the project?", False),
    ("What does \"Ads For Tomorrow\" say?", False),
])
def test_several_sources_requested(question, expected):
    assert several_sources_requested(question) is expected


def test_several_sources_instruction_only_when_several_records_are_supplied():
    system, _ = _generate("By what date do the posts ask for proposals?")
    assert "every supplied source that supports" in system
    system, _ = _generate("By what date does the post ask for proposals?")
    assert "every supplied source that supports" not in system
