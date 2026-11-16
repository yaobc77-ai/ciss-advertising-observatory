"""scripts/decisions_final_demo.py: the judge-alone route, the replay against labels and the tally.
No model call; fictional ads and labels."""
import pytest

from scripts.decisions_final_demo import final_route, replay, report, tally


def numbers(meets, does_not_meet=0.0, rules=(0.0,)):
    return {"meets": meets, "borderline": 0.0, "does_not_meet": does_not_meet, "rules": list(rules), "exclusions": []}


def answers_of(*decisions):
    return {"tides": {"research_trace": {"list_screening": {"criterion": None, "decisions": list(decisions)}}}}


def test_judge_alone_passes_without_screening():
    assert final_route(numbers(0.9)) == "pass"
    assert final_route(numbers(0.5)) == "pass"  # the threshold itself passes
    assert final_route(numbers(0.4, does_not_meet=0.5)) == "review"


def test_exclusion_keeps_the_rule_guard():
    assert final_route(numbers(0.0, does_not_meet=0.95)) == "exclude"
    assert final_route(numbers(0.0, does_not_meet=0.95, rules=(0.4,))) == "review"


def test_no_judgment_goes_to_a_person():
    assert final_route(None) == "review"


def test_replay_and_tally_against_labels():
    answers = {"tides": {"research_trace": {"list_screening": {"criterion": None, "decisions": [
        {"record_id": "r1", "title": "Tidal kites", "decision": "matches", "triage": numbers(0.9)},
        {"record_id": "r2", "title": "Harbor jobs", "decision": "does_not_match", "triage": numbers(0.8)},
        {"record_id": "r3", "title": "Bakery", "decision": "does_not_match", "triage": numbers(0.0, does_not_meet=0.99)},
    ]}}}}
    rows = replay(answers, {"tides": {1, 2}}, {"r1": 1, "r2": 2, "r3": 3})
    assert [(r["current"], r["decisions_final"]) for r in rows] == [("pass", "pass"), ("review", "pass"), ("exclude", "exclude")]
    current, final = tally(rows, "current"), tally(rows, "decisions_final")
    assert current["pass"] == {"ads": 1, "human_yes": 1} and current["pass_recall"] == 0.5
    assert final["pass"] == {"ads": 2, "human_yes": 2} and final["pass_recall"] == 1.0 and final["exclude"]["ads"] == 1


def test_an_ad_without_a_label_stops_the_replay():
    with pytest.raises(SystemExit, match="No labelled article"):
        replay(answers_of({"record_id": "r9", "decision": "matches", "triage": numbers(0.9)}), {"tides": {1}}, {"r1": 1})


def test_report_without_judgments_or_positives_says_not_available():
    rows = replay(answers_of({"record_id": "r1", "title": "Bakery", "decision": "does_not_match", "triage": None}),
                  {"tides": set()}, {"r1": 1})
    assert [r["decisions_final"] for r in rows] == ["review"]
    assert report(rows).count("| N/A | N/A |") == 2
    passed = replay(answers_of({"record_id": "r1", "title": "Bakery", "decision": "matches", "triage": numbers(0.9)}),
                    {"tides": set()}, {"r1": 1})
    assert tally(passed, "decisions_final")["pass_recall"] is None and "| 0% | N/A |" in report(passed)
