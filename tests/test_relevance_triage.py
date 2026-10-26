"""Criterion + Decisions-API triage before list screening (fictional data)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from observatory import relevance_triage
from observatory.list_screening import list_answer
from observatory.models import Evidence
from observatory.relevance_eval_ui import criterion_card, review_section
from observatory.relevance_triage import (
    excludable,
    read_answers,
    route,
    triage_questions,
    triaged_screen,
)

CRITERION = {"counts": ["The ad mentions tidal kites.", "The ad mentions kite power."],
             "does_not_count": ["Kites as toys only."]}


def passage(record, text):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="native",
                    title=f"Kite notice {record}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=0, end=len(text))


def decision_answer(meets, borderline, not_meet, rules=(0.0, 0.0)):
    answers = [{"type": "choice", "name": "verdict", "choice": "meets" if meets >= max(borderline, not_meet) else "does_not_meet",
                "probabilities": [{"value": "meets", "probability": meets}, {"value": "borderline", "probability": borderline},
                                  {"value": "does_not_meet", "probability": not_meet}], "confidence": 0.9},
               {"type": "score", "name": "strength", "score": 2.0,
                "probabilities": [{"value": 2, "label": "Clear", "probability": 0.8}]}]
    answers += [{"type": "predicate", "name": f"rule_{n}", "probability": p} for n, p in enumerate(rules, 1)]
    answers.append({"type": "predicate", "name": "exclusion_1", "probability": 0.05})
    return {"answers": answers, "usage": {"input_tokens": 500}}


def test_questions_follow_the_official_shapes():
    items = triage_questions("Which ads mention tidal kites?", CRITERION)
    assert [item["type"] for item in items] == ["choice", "score", "predicate", "predicate", "predicate"]
    assert [c["value"] for c in items[0]["choices"]] == ["meets", "borderline", "does_not_meet"]
    assert "(1) The ad mentions tidal kites." in items[0]["instructions"] and len(items[1]["levels"]) == 4
    assert [item["name"] for item in items[2:]] == ["rule_1", "rule_2", "exclusion_1"]


def test_routes_exclude_only_when_every_dimension_agrees():
    sure_no = read_answers(decision_answer(0.02, 0.03, 0.95))
    assert sure_no["strength_label"] == "Clear" and sure_no["rules"] == [0.0, 0.0] and excludable(sure_no)
    # "does not meet" is sure, but one rule is not: the ad goes to a person, not out of the list.
    contradicted = read_answers(decision_answer(0.0, 0.03, 0.97, rules=(0.0, 0.49)))
    assert not excludable(contradicted) and route("does_not_match", contradicted) == "review"
    yes = read_answers(decision_answer(0.9, 0.05, 0.05, rules=(0.9, 0.1)))
    assert route("matches", yes) == "pass" and route("does_not_match", yes) == "review"
    unsure = read_answers(decision_answer(0.4, 0.4, 0.2))
    assert route("matches", unsure) == "review"
    assert route("matches", None) == "pass" and route("unclear", None) == "exclude"
    assert read_answers({"answers": [{"type": "refusal", "name": "verdict"}]}) is None


def test_triaged_screen_skips_excluded_ads_and_routes_the_rest():
    replies = {"k1": decision_answer(0.9, 0.05, 0.05, (0.9, 0.0)), "k2": decision_answer(0.01, 0.02, 0.97),
               "k3": decision_answer(0.4, 0.4, 0.2, (0.4, 0.0))}
    budget = SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock())
    rag = SimpleNamespace(client=SimpleNamespace(post=lambda path, body, cast_to: replies[body["input"].split("Kite notice ")[1][:2]]),
                          budget=budget)
    screened = []

    def screen(rag, question, evidence, visitor, *, limit, widen_to, reread):
        screened.append(sorted({e.record_id for e in evidence}))
        return [{"record_id": rid, "title": f"Kite notice {rid}", "publisher": "Harbor Daily", "sponsor": "Tidal Co",
                 "published_at": date(2021, 5, 4), "decision": "matches" if rid == "k1" else "does_not_match",
                 **({"evidence_id": "k1-e1", "quote": "Tidal kites power the harbor"} if rid == "k1" else {})}
                for rid in screened[-1]], 0.02

    evidence = [passage("k1", "Tidal kites power the harbor."), passage("k3", "Kites fly at the fair.")]
    results, cost, summary = triaged_screen(screen, rag, "Which ads mention tidal kites?", evidence, "visitor",
                                            criterion=CRITERION, extra=[passage("k2", "Ferries leave at nine.")])
    assert screened == [["k1", "k3"]]  # the excluded ad is not screened
    routes = {item["record_id"]: item["route"] for item in results}
    assert routes == {"k1": "pass", "k3": "review", "k2": "exclude"}
    assert summary["triaged"] == 3 and (summary["pass"], summary["review"], summary["exclude"]) == (1, 1, 1)
    assert abs(cost - (0.02 + 3 * 0.00005)) < 1e-9 and budget.settle.call_count == 3

    answer = list_answer("Which ads mention tidal kites?", results, [*evidence], scope_total=3,
                         criterion=CRITERION, triage=summary)
    assert answer.answer.startswith("Found 1 matching ad among the 3")
    assert "1 more need a human check" in answer.answer and "Kite notice k3" in answer.answer
    trace = answer.research_trace["list_screening"]
    assert trace["criterion"] == CRITERION and trace["review"] == 1
    assert {d["record_id"]: d["route"] for d in trace["decisions"]} == routes
    # Read in full by the triage: the records not read have no text, they were not skipped.
    whole = list_answer("Which ads mention tidal kites?", results, [*evidence], scope_total=5,
                        criterion=CRITERION, triage={**summary, "whole_scope": True})
    assert "all 3 with readable text were checked, the other 2 have no readable text" in whole.answer

    def text(component):
        if component is None or isinstance(component, (str, int, float)):
            return "" if component is None else str(component)
        children = getattr(component, "children", None)
        return " ".join(text(c) for c in children) if isinstance(children, (list, tuple)) else text(children)

    card = text(criterion_card(trace, validation={})[0])
    assert "What counts for this question" in card and "Kites as toys only." in card
    assert "1 passed both machine checks" in card and "1 was excluded" in card
    review = text(review_section(trace)[0])
    assert "Needs a human check (1)" in review and "Kite notice k3" in review and "meets 40%" in review


def test_triage_is_off_without_a_decisions_client_or_when_switched_off(monkeypatch):
    rag = SimpleNamespace(client=SimpleNamespace(responses=None), budget=None)
    assert relevance_triage.make_criterion(rag, "Which ads mention kites?", "visitor") == (None, 0.0)
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "off")
    assert not relevance_triage.enabled(SimpleNamespace(client=SimpleNamespace(post=lambda **_: None)))


def test_failed_criterion_and_triage_calls_are_logged_by_type_without_the_question(caplog, monkeypatch):
    # Known defect (2026-10-25): failures were swallowed silently.
    monkeypatch.setenv("OBS_RELEVANCE_TRIAGE", "on")
    budget = SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock())

    def parse(**_kwargs):
        raise TimeoutError("slow")

    rag = SimpleNamespace(budget=budget, client=SimpleNamespace(responses=SimpleNamespace(parse=parse), post=Mock()))
    monkeypatch.setattr(relevance_triage, "enabled", lambda _rag: True)
    with caplog.at_level("WARNING", logger="observatory.relevance_triage"):
        criterion, cost = relevance_triage.make_criterion(rag, "Which ads mention tidal kites?", "visitor")
    assert (criterion, cost) == (None, 0.0)
    assert "Criterion call failed (TimeoutError)" in caplog.text and "tidal" not in caplog.text

    def post(*_args, **_kwargs):
        raise ConnectionError("down")

    rag.client.post = post
    caplog.clear()
    with caplog.at_level("WARNING", logger="observatory.relevance_triage"):
        results, cost = relevance_triage.triage(rag, "Which ads mention tidal kites?", CRITERION,
                                                [[passage("k1", "Tidal kites cut noise.")]], "visitor", workers=1)
    assert cost == 0.0 and list(results.values()) == [None]
    assert "Triage call failed for record k1 (ConnectionError)" in caplog.text and "tidal kites" not in caplog.text
