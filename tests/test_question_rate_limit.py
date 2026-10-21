from types import SimpleNamespace

import pytest

from observatory.budget import LimitReached, QuestionGate


def _settings(per_minute=2, per_day=30, concurrency=2):
    return SimpleNamespace(requests_per_minute=per_minute, requests_per_day=per_day,
                           concurrency=concurrency)


def test_many_paid_calls_in_one_question_count_once():
    gate, settings = QuestionGate(), _settings(per_minute=1)

    with gate.question("visitor-a"):
        assert all(gate.admit("visitor-a", settings) for _ in range(40))

    with gate.question("visitor-a"), pytest.raises(LimitReached):
        gate.admit("visitor-a", settings)


def test_calls_outside_a_question_use_the_per_call_limits():
    gate = QuestionGate()

    assert gate.admit("visitor-a", _settings()) is False


def test_a_free_question_is_not_counted():
    gate, settings = QuestionGate(), _settings(per_minute=1)

    with gate.question("visitor-a"):
        pass
    with gate.question("visitor-a"):
        assert gate.admit("visitor-a", settings)


def test_concurrent_paid_questions_are_capped_across_visitors():
    gate, settings = QuestionGate(), _settings(concurrency=1)

    with gate.question("visitor-a"):
        gate.admit("visitor-a", settings)
        with gate.question("visitor-b"), pytest.raises(LimitReached):
            gate.admit("visitor-b", settings)
    with gate.question("visitor-b"):
        assert gate.admit("visitor-b", settings)


def test_the_question_closes_when_the_answer_fails():
    from observatory.budget import QUESTIONS
    from observatory.models import Filters
    from observatory.service import Service

    service = Service.__new__(Service)
    service._answer_question = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed"))

    with pytest.raises(RuntimeError):
        service.answer("Which ads mention kites?", Filters(), "visitor-closing")

    assert QUESTIONS.admit("visitor-closing", _settings()) is False
