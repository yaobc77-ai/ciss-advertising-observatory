"""The answer page prints how each screened ad was judged (fictional data)."""
from observatory.app import _relevance_reasoning


def decision(record, verdict, reasoning, quote=""):
    item = {"record_id": record, "decision": verdict, "evidence_id": f"{record}-e"}
    if quote:
        item["quote"] = quote
    if reasoning:
        item["screening_reasoning"] = reasoning
    return item


def text(component):
    if component is None or isinstance(component, (str, int)):
        return "" if component is None else str(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(text(child) for child in children)
    return text(children)


def test_decisions_are_grouped_by_call_with_titles_quotes_and_reasoning():
    first = "A1 says kites cut noise. A2 is about food."
    decisions = [decision("kite-1", "matches", first, "Tidal kites cut harbor noise"),
                 decision("kite-2", "does_not_match", first),
                 decision("kite-3", "unclear", "")]
    result = {"research_trace": {"list_screening": {"decisions": decisions}},
              "evidence": [{"record_id": "kite-1", "title": "Kites over Marlow Bay"},
                           {"record_id": "kite-2", "title": "Harbor food fair"}]}
    [details] = _relevance_reasoning(result)
    shown = text(details)
    assert "How relevance was judged (3 ads read, 1 listed)" in shown
    assert "Kites over Marlow Bay" in shown and "Tidal kites cut harbor noise" in shown
    assert shown.count(first) == 1  # one reasoning per call, not per ad
    assert "No reasoning text came back for this call." in shown
    assert "kite-3" in shown  # an ad without evidence falls back to its record id


def test_answers_without_screening_show_nothing():
    assert _relevance_reasoning({"research_trace": {}}) == []
    assert _relevance_reasoning({}) == []
