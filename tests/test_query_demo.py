"""Accuracy score per cited ad on a list answer, and the saved demo answers on the Query page.
No model call; fictional ads."""
import json

import plotly
import pytest
from dash import html

from observatory.app import _demo_row, _evidence_cards, _render_answer_result
from observatory.query_demo import demo_answers, replay, scope_size
from observatory.relevance_eval_ui import record_scores, relevance_lines

CRITERION = {"counts": ["Mentions tidal power", "Mentions kite farms"], "does_not_count": ["Weather reports only"]}


def text(component):
    if isinstance(component, (list, tuple)):
        component = html.Div([c for c in component if c is not None])
    return json.dumps(component.to_plotly_json(), cls=plotly.utils.PlotlyJSONEncoder, ensure_ascii=False)


def numbers(meets=0.9, rules=(0.95, 0.2), exclusions=(0.0,), label="Clear"):
    return {"choice": "meets", "meets": meets, "borderline": round(1 - meets, 3), "does_not_meet": 0.0,
            "strength_label": label, "rules": list(rules), "exclusions": list(exclusions)}


def evidence(rid, quote):
    return {"evidence_id": f"e-{rid}", "record_id": rid, "dataset": "native", "title": f"Harbor kites {rid}",
            "publisher": "Harbor Times", "sponsor": "Tidewater Energy", "published_at": "2020-05-01",
            "text": f"Intro. {quote} Outro.", "start": 0, "end": 40, "version_id": "v1", "score": 0.03}


def answer(decisions, *, charts=True):
    quote = "Tidewater builds tidal turbines."
    return {
        "status": "answered", "answer_mode": "rag", "answer": "Found 1 matching ad. [1]",
        "structured_result": {"kind": "list", "display_citations": [1],
                              **({"charts": [{"id": "by_publisher", "title": "By publisher", "labels": ["Harbor Times"],
                                              "values": [1], "total": 1}]} if charts else {})},
        "research_trace": {"original_question": "Which ads mention tidal power?",
                           "base_filters": {"record_ids": ["r1", "r2", "r3"]},
                           "list_screening": {"question": "Which ads mention tidal power?", "criterion": CRITERION,
                                              "triage": {"triaged": 3, "pass": 1, "review": 0, "exclude": 2},
                                              "decisions": decisions}},
        "citations": [{"evidence_id": "e-r1", "quote": quote}],
        "evidence": [evidence("r1", quote)],
    }


def passed(rid="r1", triage="default"):
    return {"record_id": rid, "title": f"Harbor kites {rid}", "decision": "matches", "route": "pass",
            "quote": "Tidewater builds tidal turbines.", "triage": numbers() if triage == "default" else triage}


def test_score_and_related_rules_follow_the_rules_shown():
    score, related = relevance_lines(numbers(), CRITERION)
    assert text(score).count("Accuracy 90/100 · Clear") == 1
    assert "Mentions tidal power" in text(related) and " 95/100" in text(related) and "kite farms" not in text(related)


def test_no_rule_over_the_line_and_an_exclusion_are_said_in_words():
    _, related = relevance_lines(numbers(meets=0.3, rules=(0.4, 0.1), exclusions=(0.5,)), CRITERION)
    assert "no single rule is shown for this ad" in text(related) and "reached" not in text(related)
    assert "Exclusion that may apply (1)" in text(related) and "Weather reports only" in text(related) and " 50/100" in text(related)


@pytest.mark.parametrize("bad", [None, {"meets": "high"}, numbers(rules=(0.9,)), numbers(meets=1.4),
                                 numbers(exclusions=()), {**numbers(), "rules": [True, 0.1]},
                                 {**numbers(), "borderline": 0.9, "does_not_meet": 0.9}])
def test_missing_or_unusable_numbers_give_no_score(bad):
    assert record_scores({"criterion": CRITERION, "decisions": [passed(triage=bad)]}) == {}
    score, related = relevance_lines(None, CRITERION)
    assert "Accuracy: not assessed" in text(score) and related is None


@pytest.mark.parametrize("exclusions", ["missing", None, []])
def test_no_exclusion_rules_need_an_empty_list(exclusions):
    criterion = {"counts": CRITERION["counts"]}
    triage = numbers(exclusions=())
    if exclusions == "missing":
        triage.pop("exclusions")
    else:
        triage["exclusions"] = exclusions
    scores = record_scores({"criterion": criterion, "decisions": [passed(triage=triage)]})
    assert scores == ({"r1": triage} if exclusions == [] else {})
    if scores:
        score, related = relevance_lines(scores["r1"], criterion)
        assert "Accuracy 90/100" in text(score) and "Exclusion" not in text(related)


def test_two_different_sets_for_one_ad_give_no_score():
    trace = {"criterion": CRITERION, "decisions": [passed(), passed(triage=numbers(meets=0.6))]}
    assert record_scores(trace) == {}
    assert record_scores({"criterion": CRITERION, "decisions": [passed(), passed()]}) == {"r1": numbers()}


def test_card_shows_score_after_title_and_related_instead_of_rank_note():
    card = text(_evidence_cards([evidence("r1", "Tidewater builds tidal turbines.")], True,
                                [{"evidence_id": "e-r1", "quote": "Tidewater builds tidal turbines."}],
                                {"r1": numbers()}, CRITERION))
    assert "Accuracy 90/100" in card and "Related to (1)" in card
    assert "rank is not a confidence score" not in card
    plain = text(_evidence_cards([evidence("r1", "x")], True))
    assert "Accuracy" not in plain and "rank is not a confidence score" in plain


def test_list_answer_shows_the_accuracy_score_and_ordinary_answers_do_not():
    page = text(_render_answer_result(answer([passed()]), True, None))
    assert "Accuracy 90/100" in page
    ordinary = answer([passed()])
    ordinary["research_trace"].pop("list_screening")
    assert "Accuracy 90/100" not in text(_render_answer_result(ordinary, True, None))


class NoService:
    def __getattr__(self, name):
        raise AssertionError(f"a replay must not use the service ({name})")


def test_replay_has_no_charts_checks_only_on_cards_and_leaves_the_saved_answer_alone():
    saved = answer([passed(), {**passed("r2"), "decision": "unclear", "route": "review"}])
    before = json.dumps(saved, sort_keys=True)
    page = text(_render_answer_result(replay(saved), True, NoService()))
    assert "rel-vote" not in page and "By publisher" not in page and "Accuracy 90/100" in page
    assert "rel-card-vote" in page  # a reader may still mark a listed ad right or wrong on its card
    assert json.dumps(saved, sort_keys=True) == before
    live = text(_render_answer_result(answer([passed()]), True, None))
    assert "rel-card-vote" in live and "By publisher" in live
    assert "Your check is under this ad's card below." in live  # one place per ad


def test_saved_answers_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OBS_QUERY_DEMO_ANSWERS", str(tmp_path / "missing.json"))
    assert demo_answers() == [] and _demo_row([], False) is None
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"labels.tidal_power": answer([passed()])}), encoding="utf-8")
    monkeypatch.setenv("OBS_QUERY_DEMO_ANSWERS", str(path))
    [demo] = demo_answers()
    assert demo["name"] == "Tidal power" and demo["question"] == "Which ads mention tidal power?"
    assert demo["saved"] is None  # only the known run has a date; a file's own time is not trusted
    assert scope_size(demo["result"]) == 3 and "Tidal power" in text(_demo_row([demo], False))
    for broken in ("{oops", "[]", json.dumps({"x": {"research_trace": {}}})):
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError):
            demo_answers()
    assert "could not be read" in text(_demo_row([], True))
