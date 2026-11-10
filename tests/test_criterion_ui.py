"""Pipeline step 3, S3-d: the web's criterion card and its callbacks (fake service, no model call, no browser JS).

The card renders the pending answer (rules with verbatim example sentences and "Counts" /
"Does not count" buttons, two editable boxes, "Judge by these rules", "Browse the candidates
without judging"); the web asks for the card first by default; a click on the card continues
through service.answer(continuation=...) with the card's own question and scope; a local
check, a refusal from the server and a judgment in progress only change the card's notice; a
click on a card that a newer submission replaced is ignored; an example click drafts a line in
the right box and browse closes the card, both without a request; a page takes one submission at a
time.
"""
import json
import threading
from types import SimpleNamespace

import pytest
from dash._utils import stringify_id
from dash.dependencies import _Wildcard
from test_app import FakeService, callback, component_tree, research_values

from observatory import criterion_ui as ui
from observatory.app import _render_answer_result, create_app
from observatory.criterion_confirmation import example_choice_line, pending_confirmation
from observatory.models import Answer, Filters
from observatory.query_progress import ProgressRegistry

QUESTION = "carbon capture"  # research_values() submits this question
FLOW = "flow-abc123"
TOKEN = "signed.token.value"
RULES = ["The ad presents tidal kites as a source of jobs.", "The ad says kites hire local crews."]
EXAMPLE = "Tidal kites will bring 400 jobs to the harbor."
SECOND = "Quiet tidal kite farms hire local crews."
EXAMPLES = [{"rule": 1, "sentence": EXAMPLE, "record_id": "n2", "evidence_id": "n2-e1", "dataset": "native",
             "title": "Kite notice n2", "publisher": "Harbor Daily", "sponsor": "Tidal Co", "published_at": "2021-05-04",
             "overlap": 3, "basis": "word_overlap"},
            {"rule": 2, "sentence": SECOND, "record_id": "n5", "evidence_id": "n5-e1", "dataset": "native",
             "title": "Kite notice n5", "publisher": "Harbor Daily", "sponsor": "Tidal Co", "published_at": "2021-05-04",
             "overlap": 2, "basis": "word_overlap"}]
FILTERS = {"dataset": "native", "publishers": [], "sponsors": [], "platforms": [], "accounts": [], "keywords": [], "labels": [],
           "record_ids": [], "replies": [], "date_from": None, "date_to": None, "include_unknown_dates": True,
           "date_presence": "any", "include_inferred_dates": False}


def pending(condition="draft", criterion=None, examples=None, flow_id=FLOW, answer=None):
    if criterion is None and condition == "draft":
        criterion = {"counts": RULES, "does_not_count": ["Jobs unrelated to kites."]}
    structured = {"kind": "criterion_confirmation", "flow_id": flow_id,
                  "condition": {"kind": condition, "phrases": ["tidal kite"] if condition == "phrases" else [], "relations": None},
                  "criterion": criterion, "examples": EXAMPLES if examples is None and criterion else (examples or []),
                  "candidates": {"native": {"scope_total": 6, "retrieved": 3, "with_rules": "whole_scope", "condition_only": None}},
                  "continuation": TOKEN, "expires_at": "2026-10-27T21:00:00+00:00", "data_version": "test-version-1234",
                  "limits": {"max_rules": 4, "max_exclusions": 3}}
    text = answer or ("All 6 ads in your selection with readable text will be judged by the rules below; the example sentences "
                      "come from the most relevant ones.\n\nConfirm the rules below, or adjust them; nothing has been judged yet.")
    return Answer(status="insufficient_evidence", answer_mode="clarification", failure_reason="criterion_confirmation_required",
                  answer=text, evidence=[FakeService().evidence()], structured_result=structured,
                  research_trace={"question_plan": {"criterion_mode": "ask"}, "flow_id": flow_id})


class CardService(FakeService):
    """The fake web service with a two-phase list: a card first, then the judged answer or a refusal."""

    def __init__(self):
        super().__init__()
        self.pending = pending()
        self.continued = None  # an Answer to return on a continuation; None: the usual answered one
        self.options = []

    def answer(self, question, filters, visitor, progress=None, **options):
        self.options.append(options)
        if "continuation" in options:
            if self.continued is not None:
                self.answer_calls.append((question, filters, visitor))
                return self.continued
            return super().answer(question, filters, visitor)  # records the call itself
        if self.pending is not None:
            self.answer_calls.append((question, filters, visitor))
            return self.pending
        return super().answer(question, filters, visitor)


def card_app(mode="ask"):
    service = CardService()
    settings = SimpleNamespace(show_source_links=True, cookie_secret="test-cookie-secret", monthly_budget_usd=100,
                               criterion_confirmation=mode)
    app = create_app(service, settings)
    return app, app.server.test_client(), service


def serialized(component):
    return json.dumps(component, default=lambda item: item.to_plotly_json())


def refusal(reason, text="At most 4 rules."):
    status = {"confirmation_registry_full": "limited", "confirmation_unavailable": "service_unavailable"}.get(reason, "insufficient_evidence")
    return Answer(status=status, answer_mode="clarification", failure_reason=reason, answer=text,
                  structured_result={"kind": reason, "detail": "too_many_rules"})


# --- The Dash HTTP protocol for callbacks with pattern-matching ids -------------------------------------------


def find_callback(app, input_type):
    for key, spec in app.callback_map.items():
        for item in spec["inputs"]:
            if isinstance(item["id"], str) and item["id"].startswith("{") and json.loads(item["id"]).get("type") == input_type:
                return key, spec
    raise LookupError(input_type)


def concrete(pattern, key, extra=None):
    """A wildcard id (from the callback map or an Output) with this card's q/f filled in."""
    pattern = json.loads(pattern) if isinstance(pattern, str) else dict(pattern)
    result = {}
    for name, value in pattern.items():
        if isinstance(value, _Wildcard) or (isinstance(value, list) and value in (["MATCH"], ["ALL"])):
            result[name] = key.get(name) if name in key else (extra or {}).get(name)
        else:
            result[name] = value
    return result


def post_pattern_callback(app, client, input_type, key, values, changed, expected_status=200):
    """Post one request for a callback whose Input is a pattern-matching id.

    `values` maps "<type>.<property>" (pattern ids) or "<id>.<property>" (plain ids) to values; for
    an ALL-patterned input the value is a list of (extra id fields, value) pairs. `changed` is the
    (extra fields, property) of the clicked component.
    """
    map_key, spec = find_callback(app, input_type)
    outs = spec["output"]
    outputs = [{"id": concrete(o.component_id, key) if isinstance(o.component_id, dict) else o.component_id,
                "property": o.component_property} for o in (outs if isinstance(outs, list) else [outs])]
    if not isinstance(outs, list):
        outputs = outputs[0]

    def entries(items):
        rows = []
        for item in items:
            if isinstance(item["id"], str) and item["id"].startswith("{"):
                pattern = json.loads(item["id"])
                name = f"{pattern['type']}.{item['property']}"
                if any(value == ["ALL"] for value in pattern.values()):
                    rows.append([{"id": concrete(pattern, key, extra), "property": item["property"], "value": value}
                                 for extra, value in values.get(name, [])])
                else:
                    rows.append({"id": concrete(pattern, key), "property": item["property"], "value": values.get(name)})
            else:
                rows.append({"id": item["id"], "property": item["property"], "value": values.get(f"{item['id']}.{item['property']}")})
        return rows

    extra, prop = changed
    trigger = concrete(json.loads(spec["inputs"][0]["id"]), key, extra)
    body = {"output": map_key, "outputs": outputs, "inputs": entries(spec["inputs"]), "state": entries(spec["state"]),
            "changedPropIds": [stringify_id(trigger) + "." + prop]}
    response = client.post("/_dash-update-component", json=body)
    assert response.status_code == expected_status, response.get_data(as_text=True)
    return response.json["response"] if expected_status == 200 else {}


def card_values(card, rules="\n".join(RULES), exclusions="Jobs unrelated to kites.", choices=None, submitted=None, question=QUESTION):
    return research_values() | {
        "research-question.value": question,
        "research-progress-token.data": "progress-token-progress-token-1234",
        "criterion-continue.n_clicks": 1,
        "criterion-card.data": card, "criterion-rules.value": rules, "criterion-exclusions.value": exclusions,
        "criterion-choices.data": choices or [],
        "research-submission.data": submitted if submitted is not None else {"question": QUESTION, "filters": FILTERS, "flow_id": card["flow_id"]},
    }


def shown_card(app, client, service):
    """Generate answer -> the card; returns (rendered children, the card store data, the submission)."""
    values = research_values() | {"answer-paid.n_clicks": 1}
    response = callback(app, client, "research-results.children", values, "answer-paid.n_clicks")
    children = response["research-results"]["children"]
    stores = [node for node in component_tree(children) if node.get("type") == "Store"
              and isinstance(node["props"].get("id"), dict) and node["props"]["id"].get("type") == "criterion-card"]
    assert len(stores) == 1
    return children, stores[0]["props"]["data"], response["research-submission"]["data"]


# --- Rendering ------------------------------------------------------------------------------------------------


def test_the_card_shows_rules_examples_boxes_and_both_actions_and_keeps_the_token_in_its_store():
    result = pending().model_dump(mode="json") | {"card_submission": {"question": QUESTION, "filters": FILTERS}}
    children = _render_answer_result(result, True, FakeService())
    text = serialized(children)
    assert "Confirm what counts before any ad is judged" in text
    for rule in RULES:
        assert rule in text
    assert EXAMPLE in text and SECOND in text and "Kite notice n2" in text
    assert text.count('"Counts"') == 2 and text.count('"Does not count"') == 2  # one pair per example
    assert "Judge by these rules" in text and "Browse the candidates without judging" in text
    assert "Retrieved candidates (free to browse; nothing judged yet)" in text
    assert "proposes a carbon capture project" in text  # the candidate passage of the fake service
    payload = json.loads(text)
    nodes = list(component_tree(payload))
    boxes = {node["props"]["id"]["type"]: node["props"]["value"] for node in nodes
             if node.get("type") == "Textarea" and isinstance(node["props"].get("id"), dict)}
    assert boxes == {"criterion-rules": "\n".join(RULES), "criterion-exclusions": "Jobs unrelated to kites."}
    stores = [node for node in nodes if node.get("type") == "Store" and node["props"]["id"].get("type") == "criterion-card"]
    assert len(stores) == 1 and stores[0]["props"]["data"]["token"] == TOKEN
    assert text.count(TOKEN) == 1  # the token is in that store only, never in visible text
    key = ui.card_key(QUESTION, FLOW)
    assert stores[0]["props"]["id"] == {"type": "criterion-card", **key}
    assert stores[0]["props"]["data"] == {"token": TOKEN, "flow_id": FLOW, "question": QUESTION, "filters": FILTERS, "condition": "draft",
                                          "limits": {"max_rules": 4, "max_exclusions": 3}, "examples": [EXAMPLE, SECOND]}
    assert all(node["props"]["id"].get("f") == FLOW for node in nodes
               if isinstance(node["props"].get("id"), dict) and str(node["props"]["id"].get("type", "")).startswith("criterion-"))


@pytest.mark.parametrize("condition, label, note", [
    ("draft_failed", "Judge by my rules", "could not be drafted"),
    ("phrases", "Confirm and judge", "No rules were drafted for this condition"),
    ("triage_off", "Confirm and judge", "No rules were drafted for this condition"),
])
def test_cards_without_a_draft_say_so_and_offer_the_right_action(condition, label, note):
    result = pending(condition=condition, criterion=None).model_dump(mode="json") | {"card_submission": {"question": QUESTION, "filters": FILTERS}}
    text = serialized(_render_answer_result(result, True, FakeService()))
    assert label in text and note in text and '"Counts"' not in text
    boxes = [node["props"]["value"] for node in component_tree(json.loads(text)) if node.get("type") == "Textarea"]
    assert boxes == ["", ""]


def test_refusals_keep_their_own_title_explanation_and_next_step_whatever_their_status():
    for reason, title in ui.REFUSAL_TITLES.items():
        text = serialized(_render_answer_result(refusal(reason, "The server's own sentence.").model_dump(mode="json"), True, FakeService()))
        assert title in text and "The server's own sentence." in text and ui.REFUSAL_NEXT_STEPS[reason] in text
        assert "project API budget" not in text and "could not complete this request" not in text  # not the generic status text


def test_the_text_helpers():
    assert ui.parse_lines("  a  rule \n\n second\tone \n") == ["a rule", "second one"]
    assert ui.criterion_from_text("r1\nr2", "x", condition="draft") == ({"counts": ["r1", "r2"], "does_not_count": ["x"]}, None)
    assert ui.criterion_from_text("", "", condition="phrases") == (None, None)  # the stated condition is confirmed
    assert ui.criterion_from_text("", "", condition="draft")[1].startswith("Write at least one rule")
    assert ui.criterion_from_text("", "x", condition="phrases")[1].startswith("Add at least one rule")
    assert ui.criterion_from_text("\n".join("r" + str(n) for n in range(5)), "", condition="draft")[1] == "At most 4 rules; shorten the list."
    assert ui.criterion_from_text("r", "\n".join("x" + str(n) for n in range(4)), condition="draft")[1] == "At most 3 exclusions; shorten the list."
    assert ui.criterion_from_text("r", "", condition="draft", limits={"max_rules": 1, "max_exclusions": 0}) == ({"counts": ["r"], "does_not_count": []}, None)
    line = example_choice_line(EXAMPLE, "counts")
    assert ui.append_example("r1", "", EXAMPLE, "counts") == ("r1\n" + line, "")
    assert ui.append_example("r1\n" + line, "", EXAMPLE, "counts") == ("r1\n" + line, "")  # once
    assert ui.append_example("", "", EXAMPLE, "does_not_count") == ("", example_choice_line(EXAMPLE, "does_not_count"))
    assert ui.append_example("", "", "风筝带来工作。", "counts", is_chinese=True) == ("含有“风筝带来工作。”这样的说法也算", "")
    assert ui.card_key("q", "f1") != ui.card_key("q", "f2") and ui.card_key("a", "f") != ui.card_key("b", "f")


def test_progress_labels_for_the_two_new_stages():
    registry = ProgressRegistry()
    request_id = registry.begin("owner", "token-token-token-token-token")
    report = registry.reporter("owner", "token-token-token-token-token", request_id)
    report("drafting")
    assert registry.snapshot("owner", "token-token-token-token-token")["label"] == "Drafting the judging rules"
    report("judging")
    assert registry.snapshot("owner", "token-token-token-token-token")["label"] == "Judging each ad by the confirmed rules"


# --- Callbacks ------------------------------------------------------------------------------------------------


def test_generate_answer_asks_for_the_card_first_and_records_its_flow():
    app, client, service = card_app()
    children, card, submitted = shown_card(app, client, service)
    assert service.options == [{"criterion_confirmation": "ask", "address": "127.0.0.1"}]  # the web passes its address on
    assert card["token"] == TOKEN and card["question"] == QUESTION and card["filters"]["dataset"] == "native"
    assert "include_inferred_dates" not in card["filters"]  # left to the service's default, as in phase 1
    assert submitted["flow_id"] == FLOW and submitted["question"] == QUESTION
    assert "Judge by these rules" in json.dumps(children)
    app, client, service = card_app(mode="auto")
    callback(app, client, "research-results.children", research_values() | {"answer-paid.n_clicks": 1}, "answer-paid.n_clicks")
    assert service.options == [{"criterion_confirmation": "auto", "address": "127.0.0.1"}]


def test_a_fresh_card_is_not_marked_stale_by_its_flow_id():
    app, client, service = card_app()
    _, card, submitted = shown_card(app, client, service)
    values = research_values() | {"research-submission.data": submitted}
    response = callback(app, client, "research-stale.children", values, "research-submission.data")
    assert response["research-stale"]["children"] is None  # the controls did not move: no stale notice
    values["research-question.value"] = "another question"
    response = callback(app, client, "research-stale.children", values, "research-question.value")
    assert "Results are from an earlier selection" in json.dumps(response)


def test_a_click_on_the_card_continues_with_the_typed_rules_and_the_choices():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    key = ui.card_key(QUESTION, FLOW)
    choices = [{"example": 0, "choice": "counts"}]
    rules = "\n".join(RULES) + "\n" + example_choice_line(EXAMPLE, "counts")
    response = post_pattern_callback(app, client, "criterion-continue", key,
                                     card_values(card, rules=rules, choices=choices), ({}, "n_clicks"))
    assert service.options[-1] == {"continuation": {
        "token": TOKEN, "criterion": {"counts": [*RULES, example_choice_line(EXAMPLE, "counts")], "does_not_count": ["Jobs unrelated to kites."]},
        "example_choices": choices}, "address": "127.0.0.1"}
    assert service.answer_calls[-1][0] == QUESTION and service.answer_calls[-1][1].dataset == "native"
    assert "proposes a carbon capture project" in json.dumps(response["research-results"]["children"])
    assert response["research-submission"]["data"] == {"question": QUESTION, "filters": FILTERS}
    assert response["criterion-notice"]["children"] is None  # a judged answer clears the notice slot


def test_a_card_without_rules_confirms_the_stated_condition():
    app, client, service = card_app()
    service.pending = pending(condition="phrases", criterion=None)
    _, card, _ = shown_card(app, client, service)
    response = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW),
                                     card_values(card, rules="", exclusions=""), ({}, "n_clicks"))
    assert service.options[-1]["continuation"]["criterion"] is None and "research-results" in response


@pytest.mark.parametrize("rules, exclusions, message", [
    ("", "", "Write at least one rule"),
    ("", "Not kites.", "Add at least one rule"),
    ("\n".join(f"Rule {n}" for n in range(5)), "", "At most 4 rules"),
    ("Rule", "\n".join(f"No {n}" for n in range(4)), "At most 3 exclusions"),
])
def test_a_bad_rule_box_only_changes_the_notice_and_calls_nothing(rules, exclusions, message):
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    calls = len(service.answer_calls)
    response = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW),
                                     card_values(card, rules=rules, exclusions=exclusions), ({}, "n_clicks"))
    assert len(service.answer_calls) == calls and set(response) == {"criterion-notice"}  # the card itself is untouched
    assert message in json.dumps(response)


@pytest.mark.parametrize("reason, hint", [
    ("criterion_invalid", "Correct the rules and select Judge again"),
    ("continuation_in_progress", "select Judge again"),
    ("continuation_invalid", "Ask the question again for a new card"),
    ("continuation_conflict", "judge by different rules"),
])
def test_a_refusal_from_the_service_only_changes_the_notice(reason, hint):
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    service.continued = refusal(reason, "The server's sentence.")
    response = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card), ({}, "n_clicks"))
    assert set(response) == {"criterion-notice", "criterion-flow-state"}  # the card itself is untouched
    text = json.dumps(response)
    assert ui.REFUSAL_TITLES[reason] in text and "The server's sentence." in text and hint in text
    state = response["criterion-flow-state"]["data"]
    assert (state["flow_id"], state["state"]) == (FLOW, reason)
    assert state["criterion"] == {"counts": RULES, "does_not_count": ["Jobs unrelated to kites."]} and state["example_choices"] == []


def test_a_click_on_a_replaced_card_is_ignored():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    calls = len(service.answer_calls)
    stale = {"question": QUESTION, "filters": FILTERS, "flow_id": "flow-newer"}
    post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card, submitted=stale),
                          ({}, "n_clicks"), expected_status=204)
    post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card, submitted=None) | {"research-submission.data": None},
                          ({}, "n_clicks"), expected_status=204)
    assert len(service.answer_calls) == calls


def test_changed_controls_judge_in_the_cards_scope_and_say_so():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    response = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW),
                                     card_values(card, question="something else now"), ({}, "n_clicks"))
    assert service.answer_calls[-1][0] == QUESTION  # the card's question, not the edited box
    assert "Judged in the card's original scope" in json.dumps(response["research-results"]["children"])


def test_an_example_click_drafts_a_line_in_the_right_box_without_a_request():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    key = ui.card_key(QUESTION, FLOW)
    calls = len(service.answer_calls)
    buttons = [({"n": 0, "choice": "counts"}, 1), ({"n": 0, "choice": "does_not_count"}, 0),
               ({"n": 1, "choice": "counts"}, 0), ({"n": 1, "choice": "does_not_count"}, 0)]
    values = card_values(card) | {"criterion-example.n_clicks": buttons}
    response = post_pattern_callback(app, client, "criterion-example", key, values, ({"n": 0, "choice": "counts"}, "n_clicks"))
    rules = response[stringify_id({"type": "criterion-rules", **key})]["value"]
    assert rules == "\n".join(RULES) + "\n" + example_choice_line(EXAMPLE, "counts")
    assert response[stringify_id({"type": "criterion-exclusions", **key})]["value"] == "Jobs unrelated to kites."
    assert response[stringify_id({"type": "criterion-choices", **key})]["data"] == [{"example": 0, "choice": "counts"}]
    # The second example as an exclusion goes to the other box; the same choice twice adds one line.
    buttons = [({"n": 0, "choice": "counts"}, 1), ({"n": 0, "choice": "does_not_count"}, 0),
               ({"n": 1, "choice": "counts"}, 0), ({"n": 1, "choice": "does_not_count"}, 1)]
    values = card_values(card, rules=rules, choices=[{"example": 0, "choice": "counts"}]) | {"criterion-example.n_clicks": buttons}
    response = post_pattern_callback(app, client, "criterion-example", key, values, ({"n": 1, "choice": "does_not_count"}, "n_clicks"))
    assert response[stringify_id({"type": "criterion-exclusions", **key})]["value"] == "Jobs unrelated to kites.\n" + example_choice_line(SECOND, "does_not_count")
    assert response[stringify_id({"type": "criterion-rules", **key})]["value"] == rules
    assert len(service.answer_calls) == calls
    buttons = [({"n": 0, "choice": "counts"}, 2), ({"n": 0, "choice": "does_not_count"}, 0)]
    values = card_values(card, rules=rules) | {"criterion-example.n_clicks": buttons}
    response = post_pattern_callback(app, client, "criterion-example", key, values, ({"n": 0, "choice": "counts"}, "n_clicks"))
    assert response[stringify_id({"type": "criterion-rules", **key})]["value"] == rules
    # Buttons never clicked, or an example the card does not have, do nothing.
    buttons = [({"n": 0, "choice": "counts"}, 0), ({"n": 0, "choice": "does_not_count"}, 0)]
    post_pattern_callback(app, client, "criterion-example", key, card_values(card) | {"criterion-example.n_clicks": buttons},
                          ({"n": 0, "choice": "counts"}, "n_clicks"), expected_status=204)
    buttons = [({"n": 7, "choice": "counts"}, 1)]
    post_pattern_callback(app, client, "criterion-example", key, card_values(card) | {"criterion-example.n_clicks": buttons},
                          ({"n": 7, "choice": "counts"}, "n_clicks"), expected_status=204)


def test_browse_replaces_only_its_button_without_a_request_and_keeps_the_judgment_state():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    key = ui.card_key(QUESTION, FLOW)
    calls = len(service.answer_calls)
    response = post_pattern_callback(app, client, "criterion-browse", key, {"criterion-browse.n_clicks": 1}, ({}, "n_clicks"))
    body = json.dumps(response[stringify_id({"type": "criterion-body", **key})]["children"])
    assert "Not judged from this card" in body and "nothing was screened" in body and "You can still judge" in body
    assert len(service.answer_calls) == calls
    # After "being judged" or "already judged by other rules" (the flow-state store, not the notice's
    # wording), browse must not claim nothing was screened; the conflict promises no replay.
    state = {"flow_id": FLOW, "state": "continuation_in_progress", "criterion": {"counts": RULES, "does_not_count": []}, "example_choices": []}
    response = post_pattern_callback(app, client, "criterion-browse", key,
                                     {"criterion-browse.n_clicks": 2, "criterion-flow-state.data": state}, ({}, "n_clicks"))
    body = json.dumps(response[stringify_id({"type": "criterion-body", **key})]["children"])
    assert "A judgment for this card is running" in body and "Select Judge again" in body and "nothing was screened" not in body
    response = post_pattern_callback(app, client, "criterion-browse", key,
                                     {"criterion-browse.n_clicks": 3, "criterion-flow-state.data": {**state, "state": "continuation_conflict"}}, ({}, "n_clicks"))
    body = json.dumps(response[stringify_id({"type": "criterion-body", **key})]["children"])
    assert "already judged with other rules" in body and "Ask the question again" in body and "Select Judge again" not in body
    response = post_pattern_callback(app, client, "criterion-browse", key,
                                     {"criterion-browse.n_clicks": 4, "criterion-flow-state.data": {**state, "flow_id": "another-flow"}}, ({}, "n_clicks"))
    assert "Not judged from this card" in json.dumps(response[stringify_id({"type": "criterion-body", **key})]["children"])
    post_pattern_callback(app, client, "criterion-browse", key, {"criterion-browse.n_clicks": 0}, ({}, "n_clicks"), expected_status=204)
    # The Judge button and the boxes are outside the replaced span: still there in the rendered card.
    rendered = serialized(_render_answer_result(pending().model_dump(mode="json") | {"card_submission": {"question": QUESTION, "filters": FILTERS}}, True, FakeService()))
    payload = json.loads(rendered)
    span = next(node for node in component_tree(payload) if isinstance(node["props"].get("id"), dict) and node["props"]["id"].get("type") == "criterion-body")
    assert "criterion-browse" in json.dumps(span) and "criterion-continue" not in json.dumps(span) and "Textarea" not in json.dumps(span)


def test_a_service_failure_on_the_card_falls_back_to_keyword_evidence():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    service.fail_answer = True
    service.continued = None
    response = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card), ({}, "n_clicks"))
    text = json.dumps(response["research-results"]["children"])
    assert "Answer service unavailable" in text and "private-disclosure" not in text


def test_an_older_response_is_never_published_over_a_newer_submission(monkeypatch):
    # The progress registry's latest request wins: a response whose request is no longer current is dropped.
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    monkeypatch.setattr(ProgressRegistry, "is_current", lambda self, owner, token, request_id: False)
    calls = len(service.answer_calls)
    post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card), ({}, "n_clicks"),
                          expected_status=204)
    assert len(service.answer_calls) == calls + 1  # the judgment ran; only its publication was dropped
    values = research_values() | {"answer-paid.n_clicks": 1, "research-progress-token.data": "progress-token-progress-token-1234"}
    callback(app, client, "research-results.children", values, "answer-paid.n_clicks", expected_status=204)


def test_the_progress_registry_knows_its_latest_request():
    registry = ProgressRegistry()
    first = registry.begin("owner", "token-token-token-token-token")
    assert registry.is_current("owner", "token-token-token-token-token", first) is True
    second = registry.begin("owner", "token-token-token-token-token")
    assert registry.is_current("owner", "token-token-token-token-token", first) is False
    assert registry.is_current("owner", "token-token-token-token-token", second) is True
    registry.finish("owner", "token-token-token-token-token", second)
    assert registry.is_current("owner", "token-token-token-token-token", second) is True  # finished, still the latest
    assert registry.is_current("owner", "token-token-token-token-token", None) is True  # no token: never compared


def test_the_card_store_keeps_the_services_date_default_for_both_scopes(monkeypatch):
    # The real service over the golden fixtures: the web leaves include_inferred_dates unset, the service
    # defaults it in both phases; a store that pinned the dump's False would be refused as another scope.
    from test_list_criterion_mode import service_for

    for name, filters in (("both_triage", Filters(dataset="all")), ("native_triage", Filters(dataset="native", include_unknown_dates=True))):
        service, scenario, calls, _ = service_for(name, monkeypatch)
        first = service.answer(scenario.question, filters, "offline", criterion_confirmation="ask")
        assert pending_confirmation(first), first.failure_reason
        store = ui.card_store(first.model_dump(mode="json"),
                              {"question": scenario.question, "filters": filters.model_dump(mode="json", exclude_unset=True)})
        assert "include_inferred_dates" not in store["filters"]
        continuation = {"token": store["token"], "criterion": first.structured_result["criterion"], "example_choices": []}
        judged = service.answer(scenario.question, Filters.model_validate(store["filters"]), "offline", continuation=continuation)
        assert judged.status == "answered", judged.failure_reason
        assert judged.research_trace["list_screening"]["criterion_source"] == "confirmed"
    service, scenario, calls, _ = service_for("native_triage", monkeypatch)
    first = service.answer(scenario.question, Filters(dataset="native"), "offline", criterion_confirmation="ask")
    pinned = Filters.model_validate(Filters(dataset="native").model_dump(mode="json"))  # include_inferred_dates pinned to False
    refused = service.answer(scenario.question, pinned, "offline",
                             continuation={"token": first.structured_result["continuation"], "criterion": first.structured_result["criterion"]})
    assert (refused.failure_reason, refused.structured_result["detail"]) == ("continuation_invalid", "scope")


def test_a_retry_after_being_judged_resends_the_submitted_criterion():
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    key = ui.card_key(QUESTION, FLOW)
    service.continued = refusal("continuation_in_progress", "This list is being judged.")
    response = post_pattern_callback(app, client, "criterion-continue", key, card_values(card), ({}, "n_clicks"))
    state = response["criterion-flow-state"]["data"]
    assert state["state"] == "continuation_in_progress" and state["criterion"]["counts"] == RULES
    # Meanwhile the boxes were edited (an example click, a typo): the retry sends the submitted criterion.
    service.continued = None
    edited = card_values(card, rules="Something else entirely", exclusions="", choices=[{"example": 1, "choice": "counts"}])
    response = post_pattern_callback(app, client, "criterion-continue", key, edited | {"criterion-flow-state.data": state}, ({}, "n_clicks"))
    sent = service.options[-1]["continuation"]
    assert sent["criterion"] == {"counts": RULES, "does_not_count": ["Jobs unrelated to kites."]} and sent["example_choices"] == []
    assert "research-results" in response and response["criterion-flow-state"]["data"] is None  # judged: the state is cleared
    # A conflict leaves its state too; a local problem after it does not touch that state, so browse still knows.
    service.continued = refusal("continuation_conflict", "Already judged by other rules.")
    response = post_pattern_callback(app, client, "criterion-continue", key, card_values(card), ({}, "n_clicks"))
    conflict = response["criterion-flow-state"]["data"]
    assert conflict["state"] == "continuation_conflict"
    response = post_pattern_callback(app, client, "criterion-continue", key,
                                     card_values(card, rules="") | {"criterion-flow-state.data": conflict}, ({}, "n_clicks"))
    assert set(response) == {"criterion-notice"}  # the local problem changes the notice only
    response = post_pattern_callback(app, client, "criterion-browse", key,
                                     {"criterion-browse.n_clicks": 1, "criterion-flow-state.data": conflict}, ({}, "n_clicks"))
    assert "already judged with other rules" in json.dumps(response[stringify_id({"type": "criterion-body", **key})]["children"])
    # A new submission clears the flow state.
    response = callback(app, client, "research-results.children", research_values() | {"answer-paid.n_clicks": 2}, "answer-paid.n_clicks")
    assert response["criterion-flow-state"]["data"] is None


def test_a_slow_failure_fallback_is_not_published_once_a_newer_submission_began(monkeypatch):
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    service.fail_answer = True
    service.continued = None

    def search_while_a_newer_submission_begins(question, filters, limit=5):
        monkeypatch.setattr(ProgressRegistry, "is_current", lambda self, owner, token, request_id: False)
        return []

    service.search = search_while_a_newer_submission_begins
    post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card), ({}, "n_clicks"),
                          expected_status=204)


def test_a_submission_while_another_runs_is_refused_until_its_response_is_built():
    # Admission and registration happen under one lock, and the slot is held through the failure
    # fallback, the rendering and the freshness check: a Generate or a second Judge posted while a
    # judgment is still in its fallback keyword search is refused and calls nothing; once that
    # judgment's response is built, the next submission is admitted.
    app, client, service = card_app()
    _, card, _ = shown_card(app, client, service)
    service.fail_answer = True
    service.continued = None
    in_fallback, release = threading.Event(), threading.Event()

    def search_that_waits(question, filters, limit=5):
        in_fallback.set()
        assert release.wait(10)
        return []

    service.search = search_that_waits
    outcome = {}

    def judge():
        try:
            outcome["response"] = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW),
                                                        card_values(card), ({}, "n_clicks"))
        except BaseException as exc:  # noqa: BLE001 - reported by the test thread below
            outcome["error"] = exc

    worker = threading.Thread(target=judge)
    worker.start()
    values = research_values() | {"answer-paid.n_clicks": 1, "research-progress-token.data": "progress-token-progress-token-1234"}
    try:
        assert in_fallback.wait(10)
        calls = len(service.answer_calls)
        response = callback(app, client, "research-results.children", values, "answer-paid.n_clicks")
        assert set(response) == {"criterion-notice"} and "then submit again" in json.dumps(response)
        second = post_pattern_callback(app, client, "criterion-continue", ui.card_key(QUESTION, FLOW), card_values(card), ({}, "n_clicks"))
        assert set(second) == {"criterion-notice"} and "then select Judge again" in json.dumps(second)
        assert len(service.answer_calls) == calls  # neither reached the service
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and "error" not in outcome, outcome.get("error")
    assert "Answer service unavailable" in json.dumps(outcome["response"]["research-results"]["children"])
    service.fail_answer = False
    response = callback(app, client, "research-results.children", values, "answer-paid.n_clicks")  # admitted again
    assert "research-results" in response and len(service.answer_calls) == calls + 1


def test_the_progress_registry_admits_one_request_at_a_time():
    registry = ProgressRegistry()
    token = "token-token-token-token-token"
    admitted, first = registry.try_begin("owner", token)
    assert admitted and first
    assert registry.try_begin("owner", token) == (False, None)  # still running: refused, nothing changes
    assert registry.is_current("owner", token, first)
    registry.finish("owner", token, first)
    admitted, second = registry.try_begin("owner", token)
    assert admitted and second != first and registry.is_current("owner", token, second)
    registry.finish("owner", token, second, status="failed")
    assert registry.try_begin("owner", token)[0] is True  # a failed request frees the slot too
    assert registry.try_begin("owner", None) == (True, None)  # no valid token: nothing registered, not serialised
    assert registry.try_begin("other", token)[0] is True  # another visitor's page has its own slot
    # Contenders for one page token released together at a barrier: exactly one is admitted.
    registry = ProgressRegistry()
    barrier = threading.Barrier(8)
    outcomes = []

    def contend():
        barrier.wait(10)
        outcomes.append(registry.try_begin("owner", token))

    threads = [threading.Thread(target=contend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert len(outcomes) == 8 and sum(1 for admitted, _ in outcomes if admitted) == 1


def test_the_two_submission_callbacks_own_disjoint_busy_controls(monkeypatch):
    # A callback's `running` resets its outputs when it ends; two callbacks sharing them would undo
    # each other's busy state (seen in the browser), so each owns its buttons and progress block.
    app, client, service = card_app()
    running = {}
    for spec in client.get("/_dash-dependencies").json:  # the specs the browser receives, `running` included
        inputs = json.dumps(spec.get("inputs", []))
        if '"answer-paid"' in inputs:
            running["research"] = set(spec["running"]["running"])
        elif "criterion-continue" in inputs:
            running["continue"] = set(spec["running"]["running"])
    assert running["research"] and running["continue"] and not running["research"] & running["continue"]
    assert {"answer-paid.disabled", "search-free.disabled", "research-progress.style"} <= running["research"]
    assert {"criterion-progress.style", "criterion-progress-poll.disabled"} <= running["continue"]
    assert any("criterion-rules" in key for key in running["continue"])
    label = callback(app, client, "criterion-progress-label.children",
                     {"criterion-progress-poll.n_intervals": 1, "research-progress-token.data": "progress-token-progress-token-1234"},
                     "criterion-progress-poll.n_intervals")
    assert label["criterion-progress-label"]["children"] == "Judging each ad by the confirmed rules"
    # Before the judgment reports a stage, and in its failure fallback, the registry's generic label
    # would read "Preparing your search" under the card: the card keeps its judging text instead.
    for generic in ("Preparing your search", "Judging each ad by the confirmed rules"):
        monkeypatch.setattr(ProgressRegistry, "snapshot", lambda self, owner, token, generic=generic: {"status": "running", "label": generic})
        shown = callback(app, client, "criterion-progress-label.children",
                         {"criterion-progress-poll.n_intervals": 2, "research-progress-token.data": "progress-token-progress-token-1234"},
                         "criterion-progress-poll.n_intervals")
        assert shown["criterion-progress-label"]["children"] == "Judging each ad by the confirmed rules"
