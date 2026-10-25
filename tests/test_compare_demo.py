"""Fictional /compare demo: the plain side is budgeted like any call; the RAG side shows checked sources."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from flask import Flask

from observatory.budget import LimitReached
from observatory.compare_demo import register_compare_demo
from observatory.config import Settings
from observatory.models import Answer, Citation, Evidence

KITE = Evidence(evidence_id="r1-e1", record_id="r1", version_id="r1-v", dataset="native", title="Kite notice",
                publisher="Harbor Daily", sponsor="Tidal Co", published_at=date(2021, 5, 4),
                url="https://example.invalid/kites", text="Tidal kites will supply cheap power.", start=0, end=36)


def client(enabled=True, answer=None, create=None, reserve=None):
    usage = SimpleNamespace(input_tokens=40, output_tokens=20, input_tokens_details=SimpleNamespace(cached_tokens=0),
                            model_dump=lambda: {"input_tokens": 40, "output_tokens": 20})
    budget = SimpleNamespace(reserve=reserve or Mock(return_value="kite-reservation"), settle=Mock(), uncertain=Mock())
    rag = SimpleNamespace(settings=Settings(), budget=budget, client=SimpleNamespace(responses=SimpleNamespace(
        create=create or Mock(return_value=SimpleNamespace(output_text="Tidal Co spent R999 million.", status="completed",
                                                           usage=usage)))))
    service = SimpleNamespace(rag=rag, answer=Mock(return_value=answer))
    server = Flask(__name__)
    server.secret_key = "fictional"
    register_compare_demo(server, service, Settings(compare_demo_enabled=enabled))
    return server.test_client(), service


def test_the_page_is_off_unless_enabled():
    web, _ = client(enabled=False)
    assert web.get("/compare").status_code == 404
    assert web.post("/api/compare/plain", json={"question": "Kites?"}).status_code == 404


def test_the_page_opens_in_english_with_examples():
    web, _ = client()
    page = web.get("/compare").get_data(as_text=True)
    assert "With and Without RAG" in page and "Ask both" in page and 'class="example"' in page


def test_the_plain_answer_sends_only_the_question_and_is_settled_on_the_budget():
    web, service = client()
    reply = web.post("/api/compare/plain", json={"question": "How much did Tidal Co spend?"}).get_json()
    assert reply["answer"] == "Tidal Co spent R999 million." and reply["cost_usd"] > 0
    sent = service.rag.client.responses.create.call_args.kwargs
    assert [m["content"] for m in sent["input"]][1] == "How much did Tidal Co spend?" and "tools" not in sent
    budget = service.rag.budget
    assert budget.reserve.call_args.args[2] == "generation"  # visitor limits and the monthly cap apply
    assert budget.settle.call_args.args[0] == "kite-reservation"
    assert budget.settle.call_args.args[2]["observatory_request"]["stage"] == "compare_demo_plain"


def test_a_limit_or_a_bad_question_is_reported_not_raised():
    web, _ = client(reserve=Mock(side_effect=LimitReached("Your question limit has been reached.")))
    assert web.post("/api/compare/plain", json={"question": "Kites?"}).status_code == 429
    assert web.post("/api/compare/plain", json={"question": " "}).status_code == 400
    assert web.post("/api/compare/rag", json={"question": "Kites?", "dataset": "elsewhere"}).status_code == 400


def test_a_failed_provider_call_is_marked_uncertain():
    web, service = client(create=Mock(side_effect=TimeoutError()))
    assert web.post("/api/compare/plain", json={"question": "Kites?"}).status_code == 503
    service.rag.budget.uncertain.assert_called_once_with("kite-reservation", "TimeoutError")


def test_the_rag_answer_carries_each_quote_with_its_record_and_original_page():
    answer = Answer(status="answered", answer="Tidal Co says kites supply cheap power. [1]", evidence=[KITE],
                    citations=[Citation(evidence_id=KITE.evidence_id, quote="kites will supply cheap power")], cost_usd=0.01)
    web, service = client(answer=answer)
    reply = web.post("/api/compare/rag", json={"question": "What do Tidal Co ads say?", "dataset": "native"}).get_json()
    assert service.answer.call_args.args[1].dataset == "native"
    (cite,) = reply["citations"]
    assert cite["quote"] == "kites will supply cheap power" and cite["detail_url"] == "/records/r1"
    assert cite["url"] == "https://example.invalid/kites" and cite["date"] == "2021-05-04"
