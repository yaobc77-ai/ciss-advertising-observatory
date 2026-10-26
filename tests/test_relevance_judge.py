"""Independent relevance judge (Decisions API) and its evaluation views (fictional data)."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from observatory.budget import price
from observatory.relevance_eval_ui import judge_view, validation_section
from observatory.relevance_judge import (
    ads_from_passages,
    judge_answer,
    kappa,
    summarize,
    verdict,
)


def answers(probability, score=2.0, support=None):
    items = [{"type": "predicate", "name": "belongs", "probability": probability},
             {"type": "score", "name": "degree", "score": score,
              "probabilities": [{"value": 0, "label": "Not related", "probability": 0.1},
                                {"value": 2, "label": "Clearly discusses", "probability": 0.9}]}]
    if support is not None:
        items.append({"type": "predicate", "name": "quote_supports", "probability": support})
    return {"answers": items, "usage": {"input_tokens": 1000}}


def rag_answering(by_text):
    posted = []

    def post(path, body, cast_to):
        posted.append((path, body))
        reply = by_text(body["input"])
        if isinstance(reply, Exception):
            raise reply
        return reply

    budget = SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock())
    return SimpleNamespace(client=SimpleNamespace(post=post), budget=budget), posted


ADS = [
    {"record_id": "k1", "title": "Kites over Marlow Bay", "decision": "matches", "quote": "Tidal kites cut noise.",
     "text": "Tidal kites cut noise."},
    {"record_id": "k2", "title": "Harbor food fair", "decision": "matches", "quote": "Food stalls.", "text": "Food stalls."},
    {"record_id": "k3", "title": "Kite school opens", "decision": "does_not_match", "text": "A kite school opens."},
    {"record_id": "k4", "title": "Ferry timetable", "decision": "does_not_match", "text": "Ferries leave at nine."},
    {"record_id": "k5", "title": "Empty", "decision": "unclear", "text": ""},
]


def by_text(text):
    if "Tidal" in text:
        return answers(0.9, 3.0, support=0.8)
    if "Food" in text:
        return answers(0.2, 0.0, support=0.1)
    if "school" in text:
        return answers(0.7)
    return answers(0.05, 0.0)


def test_each_ad_gets_a_verdict_group_and_the_call_is_paid_and_settled():
    rag, posted = rag_answering(by_text)
    report = judge_answer(rag, "Which ads mention tidal kites?", ADS, "visitor")
    groups = {row["record_id"]: row["verdict"] for row in report["ads"]}
    assert groups == {"k1": "confirmed", "k2": "doubted", "k3": "possible_miss", "k4": "agreed_out", "k5": "not_judged"}
    assert len(posted) == 4 and all(path == "/decisions" for path, _ in posted)  # the empty ad is not sent
    first = next(body for _, body in posted if "Tidal" in body["input"])
    assert [q["name"] for q in first["questions"]] == ["belongs", "degree", "quote_supports"]
    assert "Tidal kites cut noise." in first["questions"][2]["instructions"]
    assert rag.budget.reserve.call_args.args[2:] == ("generation", "gpt-6-luna")
    assert rag.budget.settle.call_count == 4
    k1 = next(row for row in report["ads"] if row["record_id"] == "k1")
    assert k1["degree_label"] == "Clearly discusses" and k1["quote_support"] == 0.8
    summary = report["summary"]
    assert summary["judged"] == 4 and summary["agreement"] == 0.5
    assert summary["quotes_checked"] == 2 and summary["quotes_supported"] == 1
    assert abs(summary["cost_usd"] - 0.0004) < 1e-9


def test_a_failed_or_refused_call_leaves_the_ad_unjudged():
    rag, _ = rag_answering(lambda text: RuntimeError("boom") if "Tidal" in text else
                           {"answers": [{"type": "refusal", "name": "belongs"}], "usage": {"input_tokens": 10}})
    report = judge_answer(rag, "Which ads mention tidal kites?", ADS[:2], "visitor")
    assert [row["verdict"] for row in report["ads"]] == ["not_judged", "not_judged"]
    assert report["ads"][0]["error"] == "RuntimeError" and rag.budget.uncertain.call_count == 1


def test_verdict_kappa_and_price():
    assert verdict("matches", 0.5) == "confirmed" and verdict("unclear", 0.6) == "possible_miss"
    assert verdict("matches", None) == "not_judged"
    assert kappa([(True, True), (False, False)]) == 1.0 and kappa([]) is None
    assert kappa([(True, True), (True, True)]) is None  # chance agreement is total: undefined
    assert price("gpt-6-luna", 1_000_000, output_tokens=500) == Decimal("0.10")
    assert summarize([])["agreement"] is None


def test_ads_are_built_from_passages_in_order():
    passages = [SimpleNamespace(record_id="k1", text="First.", title="Kites", publisher="Harbor Daily", sponsor="Tidal Co"),
                SimpleNamespace(record_id="k1", text="Second.", title="Kites", publisher="Harbor Daily", sponsor="Tidal Co")]
    [ad] = ads_from_passages([{"record_id": "k1", "decision": "matches", "quote": "First."}], passages)
    assert ad["text"] == "First.\nSecond." and ad["title"] == "Kites" and ad["quote"] == "First."


def text(component):
    if component is None or isinstance(component, (str, int, float)):
        return "" if component is None else str(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(text(child) for child in children)
    return text(children)


def test_the_views_show_counts_flags_and_validation():
    rag, _ = rag_answering(by_text)
    shown = text(judge_view(judge_answer(rag, "Which ads mention tidal kites?", ADS, "visitor")))
    assert "Listed, but the judge doubts it" in shown and "Harbor food fair" in shown
    assert "Kite school opens" in shown and "Ferry timetable" not in shown  # only disagreements are tabled
    data = {"run_date": "2026-01-01", "note": "", "articles": [{"doc": 0, "title": "Kites"}, {"doc": 1, "title": "Food"}],
            "questions": [{"short": "Kites", "human_positive": [0], "screening_listed": [0, 1],
                           "judge_probability": {"0": 0.9, "1": 0.2},
                           "screening": {"f1": 0.67, "precision": 0.5, "recall": 1.0},
                           "judge": {"f1": 1.0, "precision": 1.0, "recall": 1.0}}],
            "micro": {"screening": {"f1": 0.67, "precision": 0.5, "recall": 1.0},
                      "judge": {"f1": 1.0, "precision": 1.0, "recall": 1.0}, "agreement": 0.5, "ndcg10": 0.76,
                      "disagreements": 1, "disagreements_screening_right": 0, "both_listed": 1, "both_listed_human_yes": 1}}
    section = text(validation_section(data))
    assert "Relevance check against human labels" in section and "90%" in section
    assert "sides with the screening 0 times and with the judge 1 times" in section


def test_a_reply_without_usage_stays_uncertain_at_the_reserved_amount_instead_of_settling_at_zero(caplog):
    # Known defect (2026-10-25): a Decisions reply without usage settled the call at $0.
    def no_usage(_text):
        return {"answers": answers(0.9)["answers"]}

    rag, _ = rag_answering(no_usage)
    rag.budget.reserve = Mock(return_value="r-1")
    with caplog.at_level("WARNING", logger="observatory.relevance_judge"):
        report = judge_answer(rag, "Which ads mention tidal kites?", ADS[:1], "visitor")
    assert rag.budget.settle.call_count == 0
    assert rag.budget.uncertain.call_args_list == [(("r-1", "usage_missing"),)]
    reserved = float(rag.budget.reserve.call_args_list[0].args[0])
    assert reserved > 0
    assert abs(report["ads"][0]["cost_usd"] - reserved) < 1e-9
    assert abs(report["summary"]["cost_usd"] - round(reserved, 6)) < 1e-9
    assert "without usage" in caplog.text and "tidal" not in caplog.text


def test_a_settlement_failure_after_a_paid_call_keeps_the_reservation_uncertain():
    rag, _ = rag_answering(by_text)
    rag.budget.settle = Mock(side_effect=RuntimeError("ledger down"))
    report = judge_answer(rag, "Which ads mention tidal kites?", ADS[:1], "visitor")
    # judge_ad turns the propagated error into a not_judged row; the ledger row is marked uncertain.
    assert report["ads"][0]["error"] == "RuntimeError" and report["ads"][0]["verdict"] == "not_judged"
    assert rag.budget.uncertain.call_args_list == [(("r", "RuntimeError"),)]
    assert rag.budget.settle.call_count == 1


def test_a_normal_reply_settles_exactly_once_and_is_never_marked_uncertain():
    rag, _ = rag_answering(by_text)
    judge_answer(rag, "Which ads mention tidal kites?", ADS[:1], "visitor")
    assert rag.budget.settle.call_count == 1 and rag.budget.uncertain.call_count == 0
