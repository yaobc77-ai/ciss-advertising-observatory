"""observatory.depth_eval_ui: the "how deep should a list read" section of the Evaluation page.
Saved runs only; no model call; fictional ads."""
import json

import plotly
from dash import dcc

from observatory.depth_eval_ui import depth_section


def numbers(meets, does_not_meet=0.0):
    return {"meets": meets, "borderline": 0.0, "does_not_meet": does_not_meet, "rules": [meets], "exclusions": []}


def ad(rank, rid, meets=0.9, group="likely", **extra):
    return {"rank": rank, "record_id": rid, "title": f"Tidal kites {rid}", "publisher": "Harbor Times",
            "sponsor": "Tidewater Energy", "date": "2020-05-01", "numbers": None if meets is None else numbers(meets),
            "group": group, "status": "scored" if meets is not None else "cap", "human": None, **extra}


def run(ads, **extra):
    question = {"label": "tides", "short": "Tides", "question": "Which ads mention tides?",
                "criterion": {"counts": ["Mentions tides"], "does_not_count": ["Weather only"]},
                "scope_total": 263, "ranked": 232, "top_overlap": 118, "shallow_ranked": 120,
                "scored": sum(a["numbers"] is not None for a in ads), "failed": 0,
                "not_scored_cap": sum(a["status"] == "cap" for a in ads), "truncated": 0, "cost_usd": 0.05, "ads": ads}
    return {"run_date": "2026-10-29", "model": "gpt-6-luna", "depth": 400, "cap_usd": 0.6, "cost_usd": 0.05,
            "uncertain_usd": 0.0, "max_ad_chars": 12000, "data_version": "v1", "data_version_after": "v1",
            "pass_at": 0.5, "questions": [question], **extra}


def text(component):
    return json.dumps(component.to_plotly_json(), cls=plotly.utils.PlotlyJSONEncoder, ensure_ascii=False)


def test_no_saved_run_no_section(tmp_path, monkeypatch):
    monkeypatch.setenv("OBS_DEPTH_DEMO_RESULT", str(tmp_path / "missing.json"))
    assert depth_section() is None


def test_a_damaged_run_leaves_a_note_instead_of_breaking_the_page(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("OBS_DEPTH_DEMO_RESULT", str(path))
    assert "could not be read" in text(depth_section())
    assert "could not be read" in text(depth_section({"questions": [{"label": "x"}]}))
    monkeypatch.setenv("OBS_DEPTH_DEMO_RESULT", str(tmp_path))  # a directory: reading it raises an OSError
    assert "could not be read" in text(depth_section())


def test_section_draws_bands_tabs_and_deep_ads_with_record_links():
    ads = [ad(1, "r1", human=True), ad(150, "r2", 0.8, in_live_top=False), ad(151, "r3", 0.7, in_live_top=True),
           ad(152, "r4", None, group="not_scored")]
    page = text(depth_section(run(ads, live_top_checked_utc="2026-10-29T08:00:00+00:00")))
    assert "How deep should a list read?" in page and "every native ad with searchable text (232 of the 263" in page
    assert "Likely, ranks 121–232" in page and "Likely ads past rank 120 in this ranking (2)" in page
    assert '"/records/r2"' in page and "Hand-coded articles in this ranking (1)" in page
    assert "1 of them are not among the 120 ads the answer's search returns" in page and "checked 2026-10-29" in page
    assert "Likely (P ≥ 0.5)" in page and "not confirmed by a researcher" in page


def test_membership_not_recorded_stays_not_checked():
    page = text(depth_section(run([ad(150, "r2", 0.8)])))
    assert "this run did not record which" in page and "not checked" in page
    assert "would not reach them" not in page


def test_one_tab_per_question_with_the_saved_threshold():
    result = run([ad(1, "r1", 0.55)], pass_at=0.6)
    result["questions"].append({**result["questions"][0], "label": "kites", "short": "Kites"})
    section = depth_section(result)
    tabs = [c for c in section.children if isinstance(c, dcc.Tabs)]
    assert len(tabs) == 1 and [t.value for t in tabs[0].children] == ["tides", "kites"]
    assert "Likely (P ≥ 0.6)" in text(section)


def test_an_empty_ranking_still_renders():
    result = run([])
    result["questions"][0]["ranked"] = 0
    page = text(depth_section(result))
    assert "No ranked ads." in page and "could not be read" not in page
