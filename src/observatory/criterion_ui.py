"""The web's criterion card (pipeline step 3, S3-d): confirm what counts before any ad is judged.

Renders the pending answer of criterion_confirmation (design 3.10 and 3.4): the drafted rules
with one verbatim example sentence each and "Counts" / "Does not count" buttons, the
exclusions, two editable boxes, "Judge by these rules" and "Browse the candidates without
judging". Every component id carries the question hash and the flow id, so a click on a
card that a newer submission replaced cannot touch the newer card. The example and browse
callbacks registered here never call the service: an example click adds a draft line to the
right box, in the researcher's own words (user decision 2 of 2026-10-27), and browse only
replaces its own button with a note (the Judge button and the boxes stay, so a judgment
already started can still be shown). The continue callback lives in app.create_app beside the research
callback, because it shares that callback's progress registry, session and rendering; its
notices go to the fixed "criterion-notice" slot above the results (Dash refuses a callback
whose outputs mix MATCH wildcards with plain ids), and the outcome of the last continuation,
with the criterion it submitted, to the fixed "criterion-flow-state" store: a retry after
"being judged" resends exactly that criterion (so the finished judgment is replayed), and
browse reads that state, never the notice's wording.
"""

from __future__ import annotations

import hashlib

from dash import ALL, MATCH, Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from .criterion_confirmation import (
    MAX_EXCLUSIONS,
    MAX_RULES,
    chinese,
    example_choice_line,
)

# Conditions whose card drafted (or tried to draft) rules: nothing is judged without rules.
RULES_REQUIRED = frozenset({"draft", "draft_failed"})
# Refusals a continuation can bring back while the card stays usable or at least readable: shown in
# the card's notice, so the rules the researcher typed, the token and the candidates are untouched.
NOTICE_REASONS = frozenset({"criterion_invalid", "continuation_in_progress", "continuation_invalid", "continuation_conflict"})
REFUSAL_TITLES = {
    "criterion_confirmation_required": "Confirm what counts first",
    "continuation_invalid": "This confirmation is no longer valid",
    "continuation_conflict": "Already judged by other rules",
    "continuation_in_progress": "Being judged",
    "criterion_invalid": "The rules could not be used",
    "confirmation_registry_full": "Too many confirmations in progress",
    "confirmation_unavailable": "The confirmation could not be prepared",
}
_HINTS = {
    "continuation_in_progress": "Wait a moment, then select Judge again: the finished judgment is shown without a new charge.",
    "criterion_invalid": "Correct the rules and select Judge again; this card is still valid.",
    "continuation_invalid": "Ask the question again for a new card; the candidates below stay as retrieval found them.",
    "continuation_conflict": "Ask the question again to judge by different rules.",
}
REFUSAL_NEXT_STEPS = {
    "criterion_confirmation_required": "Confirm the rules on the card, or ask the question again.",
    "continuation_invalid": "Ask the question again for a new card; the candidates stay as retrieval found them.",
    "continuation_conflict": "Ask the question again to judge by different rules.",
    "continuation_in_progress": "Wait a moment, then select Judge again: the finished judgment is shown without a new charge.",
    "criterion_invalid": "Correct the rules and select Judge again; the card is still valid.",
    "confirmation_registry_full": "Try again in a few minutes; nothing was drafted or judged.",
    "confirmation_unavailable": "Ask the question again; nothing was judged.",
}
# What takes the browse button's place, by the flow state the last continuation left (the fixed
# "criterion-flow-state" store): a judgment may exist for the card, so browse must say so.
_BROWSE_NOTES = {
    "continuation_in_progress": ("A judgment for this card is running. ",
                                 "Select Judge again to see its result without a new charge; nothing else was screened."),
    "continuation_conflict": ("This card was already judged with other rules. ",
                              "Ask the question again for a new card; nothing else was screened."),
    "continuation_invalid": ("This confirmation is no longer valid. ",
                             "Ask the question again for a new card; the candidates below stay as retrieval found them."),
}


def question_key(question):
    return hashlib.sha1((question or "").encode("utf-8")).hexdigest()[:12]


def card_key(question, flow_id):
    """The two ids every card component carries: the question's hash and the flow."""
    return {"q": question_key(question), "f": str(flow_id or "")}


def component_id(kind, key, **extra):
    return {"type": f"criterion-{kind}", **key, **extra}


def parse_lines(text):
    """One rule per line: trimmed, blank lines dropped, inner whitespace collapsed."""
    return [" ".join(line.split()) for line in str(text or "").splitlines() if line.strip()]


def criterion_from_text(rules_text, exclusions_text, *, condition, limits=None):
    """(criterion or None, problem or None) from the two boxes, decided before any request.

    None without a problem means the researcher confirms the stated condition without rules,
    which only a card that drafted none allows (quoted phrases, a relation hint, the triage off).
    """
    limits = limits or {}
    max_rules, max_exclusions = limits.get("max_rules", MAX_RULES), limits.get("max_exclusions", MAX_EXCLUSIONS)
    rules, exclusions = parse_lines(rules_text), parse_lines(exclusions_text)
    if not rules and exclusions:
        return None, "Add at least one rule: exclusions alone cannot judge an ad."
    if not rules and condition in RULES_REQUIRED:
        return None, "Write at least one rule, or browse the candidates without judging; nothing is judged without rules."
    if len(rules) > max_rules:
        return None, f"At most {max_rules} rules; shorten the list."
    if len(exclusions) > max_exclusions:
        return None, f"At most {max_exclusions} exclusions; shorten the list."
    if not rules:
        return None, None
    return {"counts": rules, "does_not_count": exclusions}, None


def append_example(rules_text, exclusions_text, sentence, choice, is_chinese=False):
    """Add the example's draft line to the right box, once; the researcher may edit or delete it."""
    line = example_choice_line(sentence, choice, is_chinese)
    target = rules_text if choice == "counts" else exclusions_text
    if line in parse_lines(target):
        return rules_text, exclusions_text
    joined = (str(target or "").rstrip("\n") + "\n" + line).lstrip("\n")
    return (joined, exclusions_text) if choice == "counts" else (rules_text, joined)


def rules_notice(problem):
    return html.Div([html.Strong("Check the rules. "), problem], className="criterion-notice", role="alert")


def refusal_notice(result):
    """The server's refusal of a continuation, inside the card: what happened and what to do."""
    reason = result.get("failure_reason") or ""
    return html.Div([html.Strong(REFUSAL_TITLES.get(reason, "Not judged") + ". "),
                     str(result.get("answer") or "").strip(), " ", _HINTS.get(reason, "")],
                    className="criterion-notice", role="alert")


def browse_note(state=None):
    """What takes the browse button's place; the Judge button stays, so a judgment can still be made or shown."""
    head, rest = _BROWSE_NOTES.get(state, (
        "Not judged from this card. ",
        "The retrieved candidates below are what retrieval found; nothing was screened. "
        "You can still judge by selecting the button on the left."))
    return [html.Span([html.Strong(head), rest], className="scope-note")]


def flow_state_for(flow_state, flow_id):
    """The state the last continuation left for this flow, or None when the store is about another card."""
    if isinstance(flow_state, dict) and flow_state.get("flow_id") == flow_id:
        return flow_state.get("state")
    return None


def card_store(result, submission):
    """What a click on the card sends back: the token, the flow, the question and scope of the card."""
    data = result.get("structured_result") or {}
    examples = data.get("examples") or []
    return {"token": data.get("continuation"), "flow_id": data.get("flow_id"),
            "question": submission.get("question") or "", "filters": submission.get("filters") or {},
            "condition": (data.get("condition") or {}).get("kind") or "draft",
            "limits": data.get("limits") or {"max_rules": MAX_RULES, "max_exclusions": MAX_EXCLUSIONS},
            "examples": [str(item.get("sentence") or "") for item in examples]}


def card(result, submission):
    """The pending answer as a card; `submission` is the question and filters it was asked with."""
    data = result.get("structured_result") or {}
    key = card_key(submission.get("question") or "", data.get("flow_id"))
    criterion = data.get("criterion") or {}
    rules, exclusions = list(criterion.get("counts") or []), list(criterion.get("does_not_count") or [])
    examples = data.get("examples") or []
    condition = (data.get("condition") or {}).get("kind") or "draft"
    limits = data.get("limits") or {}
    max_rules, max_exclusions = limits.get("max_rules", MAX_RULES), limits.get("max_exclusions", MAX_EXCLUSIONS)

    def example_rows(number):
        rows = []
        for index, item in enumerate(examples):
            if item.get("rule") != number:
                continue
            source = " · ".join(str(part) for part in (item.get("title") or item.get("publisher"), item.get("published_at")) if part)
            rows.append(html.Div([
                html.Blockquote(str(item.get("sentence") or ""), className="screen-quote"),
                html.Span(source, className="criterion-source"),
                html.Span([
                    html.Span("Use this sentence: ", className="judge-numbers"),
                    html.Button("Counts", id=component_id("example", key, n=index, choice="counts"), n_clicks=0,
                                className="vote-button", title="Add a rule saying that a statement like this also counts"),
                    html.Button("Does not count", id=component_id("example", key, n=index, choice="does_not_count"), n_clicks=0,
                                className="vote-button", title="Add an exclusion saying that a statement like this does not count"),
                ], className="vote-row"),
            ], className="criterion-example"))
        return rows

    body = [html.P(part, className="criterion-prose") for part in str(result.get("answer") or "").split("\n\n") if part.strip()]
    if rules:
        body.append(html.P(html.Strong("Drafted rules (from the question alone; not confirmed yet)")))
        body.append(html.Ol([html.Li([rule, *example_rows(number)]) for number, rule in enumerate(rules, 1)],
                            className="criterion-rules"))
    if exclusions:
        body.append(html.P(html.Strong("Does not count:")))
        body.append(html.Ol([html.Li(rule) for rule in exclusions], className="criterion-exclusions"))
    if condition == "draft_failed":
        body.append(html.P("The rules could not be drafted. Write them below, or browse the candidates without judging; "
                           "nothing is judged without rules.", className="scope-note"))
    elif condition not in RULES_REQUIRED:
        body.append(html.P("No rules were drafted for this condition. Confirm it as stated (screening then looks for a "
                           "sentence that answers the question), or write rules below.", className="scope-note"))
    editor = html.Div([
        html.Label(f"Rules: one per line, at most {max_rules}. Quoting a sentence from an ad is allowed."),
        dcc.Textarea(id=component_id("rules", key), value="\n".join(rules), rows=4, maxLength=4000, className="criterion-box"),
        html.Label(f"Does not count: one per line, at most {max_exclusions}."),
        dcc.Textarea(id=component_id("exclusions", key), value="\n".join(exclusions), rows=3, maxLength=2000, className="criterion-box"),
    ], className="criterion-editor")
    label = ("Judge by these rules" if rules else "Judge by my rules" if condition in RULES_REQUIRED else "Confirm and judge")
    actions = html.Div([
        html.Button(label, id=component_id("continue", key), n_clicks=0, className="button button-primary",
                    title="The paid step: every ad in the stated scope is judged by the rules in the boxes"),
        # Browse replaces only this span, so the Judge button and the boxes stay for a later judgment or a replay.
        html.Span([html.Button("Browse the candidates without judging", id=component_id("browse", key), n_clicks=0,
                               className="button", title="Free: keep the retrieved candidates below as they are; nothing is judged")],
                  id=component_id("body", key)),
        html.Span("Judging is the paid step; nothing has been judged yet.", className="criterion-meta"),
    ], className="criterion-actions")
    meta = html.P(f"This card can be continued until {data.get('expires_at') or 'its expiry'} (UTC) on the same data version "
                  f"({str(data.get('data_version') or '')[:12]}).", className="criterion-meta")
    return html.Div([
        html.H4("Confirm what counts before any ad is judged"),
        html.Div([*body, editor, actions, meta]),
        dcc.Store(id=component_id("card", key), data=card_store(result, submission)),
        dcc.Store(id=component_id("choices", key), data=[]),
    ], className="criterion-confirm")


def register_criterion_card(app):
    """The card's free callbacks: an example click drafts a line; browse closes the card."""

    @app.callback(
        Output({"type": "criterion-rules", "q": MATCH, "f": MATCH}, "value"),
        Output({"type": "criterion-exclusions", "q": MATCH, "f": MATCH}, "value"),
        Output({"type": "criterion-choices", "q": MATCH, "f": MATCH}, "data"),
        Input({"type": "criterion-example", "q": MATCH, "f": MATCH, "n": ALL, "choice": ALL}, "n_clicks"),
        State({"type": "criterion-rules", "q": MATCH, "f": MATCH}, "value"),
        State({"type": "criterion-exclusions", "q": MATCH, "f": MATCH}, "value"),
        State({"type": "criterion-choices", "q": MATCH, "f": MATCH}, "data"),
        State({"type": "criterion-card", "q": MATCH, "f": MATCH}, "data"),
        prevent_initial_call=True,
    )
    def pick_example(clicks, rules, exclusions, choices, card_data):
        if not any(isinstance(n, int) and n > 0 for n in clicks or []):
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not isinstance(card_data, dict):
            raise PreventUpdate
        sentences = card_data.get("examples") or []
        index, choice = triggered.get("n"), triggered.get("choice")
        if not isinstance(index, int) or not 0 <= index < len(sentences) or choice not in ("counts", "does_not_count"):
            raise PreventUpdate
        rules, exclusions = append_example(rules, exclusions, sentences[index], choice, chinese(card_data.get("question")))
        return rules, exclusions, [*(choices or []), {"example": index, "choice": choice}]

    @app.callback(
        Output({"type": "criterion-body", "q": MATCH, "f": MATCH}, "children"),
        Input({"type": "criterion-browse", "q": MATCH, "f": MATCH}, "n_clicks"),
        State("criterion-flow-state", "data"),
        prevent_initial_call=True,
    )
    def browse(clicks, flow_state):
        if not isinstance(clicks, int) or isinstance(clicks, bool) or clicks <= 0:
            raise PreventUpdate
        triggered = ctx.triggered_id
        flow_id = triggered.get("f") if isinstance(triggered, dict) else None
        return browse_note(flow_state_for(flow_state, flow_id))
