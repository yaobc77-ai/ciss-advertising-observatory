"""Reader checks of list answers: buttons, saving, limits and the summary (fictional data)."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dash.exceptions import PreventUpdate

from observatory.relevance_eval_ui import reader_reviews_view, save_vote, vote_buttons
from observatory.service import Service


def text(component):
    if component is None or isinstance(component, (str, int, float)):
        return "" if component is None else str(component)
    children = getattr(component, "children", None)
    return " ".join(text(c) for c in children) if isinstance(children, (list, tuple)) else text(children)


def test_buttons_only_for_listed_and_to_check_records():
    row = vote_buttons("Which ads mention tidal kites?", "k1", "pass")
    ids = [child.id for child in row.children if getattr(child, "id", None) and child.id["type"] == "rel-vote"]
    assert [i["v"] for i in ids] == ["relevant", "not_relevant"] and ids[0]["rid"] == "k1" and ids[0]["route"] == "pass"
    assert vote_buttons("Which ads mention tidal kites?", "k1", "exclude") is None
    assert vote_buttons("", "k1", "pass") is None


def test_save_vote_reports_saved_limited_and_unavailable():
    clicked = {"type": "rel-vote", "q": "x", "rid": "k1", "route": "review", "v": "not_relevant"}
    service = SimpleNamespace(review_relevance=Mock(return_value=True))
    assert "Saved: not relevant" in save_vote(service, "Which ads mention kites?", clicked, "visitor")
    service.review_relevance.assert_called_once_with("Which ads mention kites?", "k1", "review", "not_relevant", "visitor")
    assert "Daily limit" in save_vote(SimpleNamespace(review_relevance=Mock(return_value=False)), "Q?", clicked, "v")
    broken = SimpleNamespace(review_relevance=Mock(side_effect=RuntimeError("no table")))
    assert "not available" in save_vote(broken, "Q?", clicked, "v")
    with pytest.raises(PreventUpdate):
        save_vote(service, "Q?", {"type": "rel-vote", "v": "maybe"}, "v")


def test_service_hashes_the_visitor_and_checks_the_values():
    service = Service.__new__(Service)
    service.db = SimpleNamespace(save_relevance_review=Mock(return_value=True))
    assert service.review_relevance(" Which ads mention kites? ", "k1", "pass", "relevant", "visitor-1")
    visitor_hash, question, record, route, verdict, policy = service.db.save_relevance_review.call_args.args
    assert len(visitor_hash) == 64 and "visitor-1" not in visitor_hash
    assert (question, record, route, verdict, policy) == ("Which ads mention kites?", "k1", "pass", "relevant",
                                                          "relevance-triage-v1")
    with pytest.raises(ValueError):
        service.review_relevance("Q?", "k1", "pass", "maybe", "visitor-1")


def test_summary_counts_each_route():
    shown = text(reader_reviews_view({("pass", "relevant"): 3, ("pass", "not_relevant"): 1, ("review", "relevant"): 1}))
    assert "Passed both machine checks: 4 checked, 3 relevant (75%)" in shown
    assert "Needs a human check: 1 checked, 1 relevant (100%)" in shown
    assert "No reader checks yet" in text(reader_reviews_view({}))
