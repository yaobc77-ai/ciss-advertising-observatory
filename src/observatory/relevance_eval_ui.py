"""Visual relevance evaluation: the judge's check of one list answer, and the human-label validation.

Two views, both plain enough for a reader without the method:
- criterion_card / review_section / judge_numbers: under a list answer, the
  rules written before reading, the records sent for a human check, and the
  Decisions judge's numbers per record (relevance_triage); readers can mark a
  record relevant or not (vote_buttons, saved by migration 0008).
- judge_view: the independent judge's check of a whole list (offline scripts).
- validation_section: on the Evaluation page, how the screening and the judge
  each compare with human labels on the hand-coded articles (frozen run in
  relevance_validation.v1.json, written by scripts/relevance_judge_validation.py).
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import plotly.graph_objects as go
from dash import MATCH, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate
from flask import session

from .relevance_judge import THRESHOLD, VERDICTS

VALIDATION_PATH = Path(__file__).with_name("relevance_validation.v1.json")
VERDICT_COLORS = {"confirmed": "#2f7d4f", "doubted": "#b8402f", "possible_miss": "#c98a1b",
                  "agreed_out": "#8a94a3", "not_judged": "#c9ced6"}
DECISION_ROWS = {"matches": "Listed", "unclear": "Unclear", "does_not_match": "Not listed"}
MAX_REVIEW_ROWS = 40


def _pct(value):
    return "–" if value is None else f"{value:.0%}"


def _tiles(counts):
    order = ("confirmed", "doubted", "possible_miss", "agreed_out")
    return html.Div([html.Div([html.Span(f"{counts.get(name, 0):,}", className="judge-tile-number"),
                               html.Span(VERDICTS[name], className="judge-tile-label")],
                              className="judge-tile", style={"borderLeftColor": VERDICT_COLORS[name]})
                     for name in order], className="judge-tiles")


def _dot_chart(rows):
    """Each ad is a dot: across, the judge's probability; down, the screening decision."""
    figure = go.Figure()
    jitter = random.Random(7)  # spread the dots of one row so they do not hide each other
    lanes = {"does_not_match": 0, "unclear": 1, "matches": 2}
    for name in ("confirmed", "doubted", "possible_miss", "agreed_out"):
        group = [row for row in rows if row["verdict"] == name]
        if not group:
            continue
        figure.add_scatter(
            x=[row["probability"] for row in group],
            y=[lanes.get(row.get("decision"), 1) + jitter.uniform(-0.25, 0.25) for row in group],
            mode="markers", name=VERDICTS[name], marker={"color": VERDICT_COLORS[name], "size": 9, "opacity": 0.8},
            customdata=[[row.get("title") or row.get("record_id"), row.get("degree_label") or ""] for row in group],
            hovertemplate="%{customdata[0]}<br>Judge: %{x:.0%} · %{customdata[1]}<extra></extra>",
        )
    figure.add_vline(x=THRESHOLD, line_dash="dot", line_color="#687587",
                     annotation_text="judge's line", annotation_position="top")
    figure.update_layout(template="plotly_white", height=260, margin={"l": 16, "r": 16, "t": 30, "b": 40},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         xaxis={"title": "Judge's probability that the ad belongs", "range": [-0.03, 1.03],
                                "tickformat": ".0%"},
                         yaxis={"tickvals": [0, 1, 2], "ticktext": ["Not listed", "Unclear", "Listed"],
                                "range": [-0.5, 2.5], "zeroline": False},
                         legend={"orientation": "h", "y": -0.35})
    return dcc.Graph(figure=figure, config={"displayModeBar": False}, className="judge-chart")


def _review_table(rows):
    flagged = sorted((row for row in rows if row["verdict"] in ("doubted", "possible_miss")),
                     key=lambda row: abs((row["probability"] or 0) - THRESHOLD), reverse=True)[:MAX_REVIEW_ROWS]
    if not flagged:
        return html.P("No disagreements: every ad the judge could read agrees with the screening.", className="scope-note")
    body = []
    for row in flagged:
        reasoning = row.get("screening_reasoning")
        body.append(html.Tr([
            html.Td(html.Span(VERDICTS[row["verdict"]], className="judge-flag",
                              style={"color": VERDICT_COLORS[row["verdict"]]})),
            html.Td([html.Strong(row.get("title") or row.get("record_id")),
                     html.Blockquote(row["quote"], className="screen-quote") if row.get("quote") else None,
                     html.Details([html.Summary("Screening reasoning"), html.P(reasoning)]) if reasoning else None]),
            html.Td(_pct(row["probability"])),
            html.Td(row.get("degree_label") or "–"),
            html.Td(_pct(row.get("quote_support")) if row.get("quote") else "–"),
        ]))
    return html.Div(html.Table([
        html.Caption(f"Ads worth a second look ({len(flagged)}; strongest disagreement first)"),
        html.Thead(html.Tr([html.Th(name, scope="col") for name in
                            ("Group", "Ad", "Judge: belongs", "Judge: how strongly", "Quote alone shows it")])),
        html.Tbody(body),
    ]), className="statistics-table")


def judge_view(report):
    summary, rows = report["summary"], report["ads"]
    judged = [row for row in rows if row["verdict"] != "not_judged"]
    if not judged:
        return html.P("The judge could not read these ads.", className="scope-note")
    kappa = summary.get("kappa")
    lines = [f"The judge agrees with the screening on {_pct(summary['agreement'])} of the {summary['judged']} ads it read"
             + (f" (Cohen's κ {kappa:.2f}; 1 is full agreement, 0 is chance)." if kappa is not None else ".")]
    if summary["quotes_checked"]:
        lines.append(f"For {summary['quotes_supported']} of {summary['quotes_checked']} listed ads, the judge says the "
                     "copied sentence alone shows the ad belongs.")
    if summary["counts"].get("not_judged"):
        lines.append(f"{summary['counts']['not_judged']} ads were not judged (no text or no answer).")
    lines.append(f"Cost ${summary['cost_usd']:.4f}.")
    validation = load_validation()
    return html.Div([
        _tiles(summary["counts"]),
        html.P(" ".join(lines), className="judge-summary"),
        _dot_chart(judged),
        html.P(_meaning(validation["micro"]), className="scope-note") if validation and
        validation.get("micro", {}).get("disagreements") is not None else None,
        html.P("How to read it: green and grey dots are agreements. A red dot is an ad the screening listed that the judge "
               "doubts; an orange dot is an ad the screening left out that the judge thinks belongs. Dots near the dotted "
               "line are close calls.", className="scope-note"),
        _review_table(judged),
    ], className="judge-result")


# Evaluation page --------------------------------------------------------------

def load_validation(path=VALIDATION_PATH):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _score_bars(questions):
    figure = go.Figure()
    names = [item["short"] for item in questions]
    for who, color in (("screening", "#003262"), ("judge", "#a86b25")):
        figure.add_bar(x=names, y=[item[who]["f1"] for item in questions], name=f"{who.title()} F1", marker_color=color,
                       text=[f"{item[who]['f1']:.2f}" if item[who]["f1"] is not None else "" for item in questions],
                       textposition="outside",
                       customdata=[[item[who]["precision"], item[who]["recall"]] for item in questions],
                       hovertemplate="%{x}<br>F1 %{y:.2f} · precision %{customdata[0]:.2f} · recall %{customdata[1]:.2f}"
                                     "<extra>" + who + "</extra>")
    figure.update_layout(template="plotly_white", barmode="group", height=320, yaxis={"range": [0, 1.12], "title": "F1"},
                         margin={"l": 16, "r": 16, "t": 20, "b": 60}, legend={"orientation": "h", "y": -0.3},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return dcc.Graph(figure=figure, config={"displayModeBar": False})


def _grid(item, articles):
    """One row per question, one cell per article: human label vs screening vs judge."""
    cells = []
    for doc in articles:
        human = doc["doc"] in item["human_positive"]
        system = doc["doc"] in item["screening_listed"]
        probability = item["judge_probability"].get(str(doc["doc"]))
        state = ("hit" if human and system else "false-alarm" if system else "miss" if human else "correct-out")
        cells.append(html.Td(f"{probability:.0%}" if probability is not None else "–",
                             className=f"grid-cell grid-{state}",
                             title=f"{doc['title']} · human: {'yes' if human else 'no'} · screening: "
                                   f"{'listed' if system else 'not listed'} · judge: "
                                   f"{'–' if probability is None else f'{probability:.0%}'}"))
    return html.Tr([html.Th(item["short"], scope="row"), *cells])


def _meaning(micro):
    """What the measured numbers say about using the judge, in one plain sentence."""
    return (f"What this means: when screening and judge both list an article, humans agree "
            f"{micro['both_listed_human_yes']} of {micro['both_listed']} times. When they disagree "
            f"({micro['disagreements']} cases), the human label sides with the screening "
            f"{micro['disagreements_screening_right']} times and with the judge "
            f"{micro['disagreements'] - micro['disagreements_screening_right']} times. So agreement raises "
            "confidence, and a disagreement is a reason to read the ad, not a correction.")


def _triage_record(triage):
    """Pass / human check / excluded, each split by what the coders said."""
    if not triage:
        return []
    names = {"pass": "Passed both machine checks", "review": "Needs a human check", "exclude": "Excluded by the judge"}
    figure = go.Figure()
    order = ["exclude", "review", "pass"]
    figure.add_bar(y=[names[r] for r in order], x=[triage[f"{r}_human_yes"] for r in order], orientation="h",
                   name="Relevant to the coders", marker_color="#2f7d4f",
                   text=[triage[f"{r}_human_yes"] or "" for r in order], textposition="inside")
    figure.add_bar(y=[names[r] for r in order], x=[triage[r] - triage[f"{r}_human_yes"] for r in order],
                   orientation="h", name="Not relevant to the coders", marker_color="#c9ced6",
                   text=[(triage[r] - triage[f"{r}_human_yes"]) or "" for r in order], textposition="inside")
    figure.update_layout(template="plotly_white", barmode="stack", height=230, margin={"l": 16, "r": 16, "t": 10, "b": 40},
                         xaxis={"title": "Article–question pairs"}, legend={"orientation": "h", "y": -0.4},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return [
        html.H3("Three routes: listed, human check, excluded"),
        html.P(f"The full answer path ({triage['run_date']}): rules written from each question, the Decisions judge "
               f"reading every article against them, and screening with a verified quote. Of {triage['human_positive']} "
               f"pairs the coders marked relevant, {triage['pass_human_yes']} were listed, "
               f"{triage['review_human_yes']} went to a human check and {triage['exclude_human_yes']} were excluded. "
               f"Cost ${triage['cost_usd']:.3f} for {len(triage.get('questions') or [])} questions.",
               className="judge-summary"),
        dcc.Graph(figure=figure, config={"displayModeBar": False}),
    ]


def validation_section(data=None):
    data = data if data is not None else load_validation()
    if not data:
        return None
    questions, articles = data["questions"], data["articles"]
    micro = data["micro"]
    return html.Section([
        html.H2("Relevance check against human labels"),
        html.P(f"{len(articles)} hand-coded articles, {len(questions)} questions, run {data['run_date']}. Humans marked "
               "each sentence; an article counts as relevant to a question when humans marked any of its sentences "
               "with that label. The screening (what the answer lists) and the independent judge are each scored "
               "against the human marks.", className="scope-note"),
        html.Div([
            html.Div([html.Span(f"{micro['screening']['f1']:.2f}", className="judge-tile-number"),
                      html.Span(f"Screening F1 (precision {micro['screening']['precision']:.2f}, "
                                f"recall {micro['screening']['recall']:.2f})", className="judge-tile-label")],
                     className="judge-tile", style={"borderLeftColor": "#003262"}),
            html.Div([html.Span(f"{micro['judge']['f1']:.2f}", className="judge-tile-number"),
                      html.Span(f"Judge F1 (precision {micro['judge']['precision']:.2f}, "
                                f"recall {micro['judge']['recall']:.2f})", className="judge-tile-label")],
                     className="judge-tile", style={"borderLeftColor": "#a86b25"}),
            html.Div([html.Span(_pct(micro["agreement"]), className="judge-tile-number"),
                      html.Span("Screening and judge agree", className="judge-tile-label")],
                     className="judge-tile", style={"borderLeftColor": "#2f7d4f"}),
            html.Div([html.Span(f"{micro['ndcg10']:.2f}", className="judge-tile-number"),
                      html.Span("Retrieval NDCG@10 (earlier AI-judged run)", className="judge-tile-label")],
                     className="judge-tile", style={"borderLeftColor": "#8a94a3"}),
        ], className="judge-tiles"),
        _score_bars(questions),
        html.Div(html.Table([
            html.Caption("Each cell is one article; the number is the judge's probability. Colour compares the "
                         "screening with the human label: green hit, red false alarm, orange miss, white correctly left out."),
            html.Thead(html.Tr([html.Th("Question", scope="col"),
                                *[html.Th(str(n + 1), scope="col", title=doc["title"]) for n, doc in enumerate(articles)]])),
            html.Tbody([_grid(item, articles) for item in questions]),
        ], className="relevance-grid"), className="statistics-table"),
        html.P(_meaning(micro), className="judge-summary") if micro.get("disagreements") is not None else None,
        *_triage_record(data.get("triage")),
        html.H3("Readers' checks"),
        html.Div(id="reader-reviews"),
        html.P(data.get("note", ""), className="scope-note"),
    ], **{"aria-label": "Relevance validation"})


# Triage views (relevance_triage) ----------------------------------------------

ROUTE_NAMES = {"pass": "Passed both machine checks", "review": "Needs a human check", "exclude": "Excluded by the judge"}
ROUTE_COLORS = {"pass": "#2f7d4f", "review": "#c98a1b", "exclude": "#8a94a3"}


def judge_numbers(numbers, criterion=None):
    """The Decisions judge's answers for one ad, in words and percentages."""
    if not numbers:
        return html.Span("Judge: no answer (screening alone decided).", className="judge-numbers")
    parts = [f"meets {numbers['meets']:.0%}", f"borderline {numbers['borderline']:.0%}",
             f"does not meet {numbers['does_not_meet']:.0%}"]
    if numbers.get("strength_label"):
        parts.append(f"how much: {numbers['strength_label']}")
    rules = [f"rule {n} {p:.0%}" for n, p in enumerate(numbers.get("rules") or [], 1)]
    exclusions = [f"exclusion {n} {p:.0%}" for n, p in enumerate(numbers.get("exclusions") or [], 1)]
    return html.Span("Judge: " + " · ".join(parts + rules + exclusions), className="judge-numbers")


def route_badge(route):
    if not route:
        return None
    return html.Span(ROUTE_NAMES.get(route, route), className="route-badge",
                     style={"borderColor": ROUTE_COLORS.get(route), "color": ROUTE_COLORS.get(route)})


def _track_record(validation):
    """One plain sentence on how the routes did against human coding, when a triage run is published."""
    record = (validation or {}).get("triage")
    if not record:
        return None
    return html.P(
        f"Tested against the research team's hand coding ({record['pairs']} article–question pairs): of "
        f"{record['pass']} ads that passed both checks, {record['pass_human_yes']} were relevant to the coders; of "
        f"{record['review']} sent to a human check, {record['review_human_yes']} were; of {record['exclude']} excluded, "
        f"{record['exclude_human_yes']} were. A small test set; see the Evaluation page.", className="scope-note")


def criterion_card(trace, validation=None):
    """The rules written before reading, and what the judge did with them."""
    criterion = trace.get("criterion")
    if not criterion:
        return []
    triage = trace.get("triage") or {}
    blocks = [html.H5("What counts for this question"),
              html.P("Written from the question before any record was read. The judge checks every record against "
                     "these rules; separately, screening must copy a sentence from the record that answers the question. "
                     "A record is listed only when both checks agree.", className="scope-note"),
              html.Ol([html.Li(rule) for rule in criterion["counts"]], className="criterion-rules")]
    if criterion.get("does_not_count"):
        blocks += [html.P(html.Strong("Does not count:")),
                   html.Ol([html.Li(rule) for rule in criterion["does_not_count"]], className="criterion-exclusions")]
    if triage:
        blocks.append(html.P(
            f"The Decisions judge (gpt-6-luna) read {triage.get('triaged', 0):,} records against these rules: "
            f"{triage.get('pass', 0):,} passed both machine checks (judge and a verified quote), "
            f"{triage.get('review', 0):,} need a human check, {triage.get('exclude', 0):,} "
            f"{'was' if triage.get('exclude', 0) == 1 else 'were'} excluded.",
            className="judge-summary"))
    blocks.append(_track_record(validation if validation is not None else load_validation()))
    return [html.Div(blocks, className="criterion-card")]


def review_section(trace):
    """Records neither listed nor excluded: shown so a person can decide."""
    review = [d for d in trace.get("decisions") or [] if d.get("route") == "review"]
    if not review:
        return []
    rows = []
    for item in review:
        why = ("screening found a sentence but the judge was unsure" if item.get("decision") == "matches" else
               "not screened (too many records)" if item.get("reason") == "not_screened" else
               "the judge did not rule it out, but screening found no qualifying sentence")
        rows.append(html.Li([html.Strong(item.get("title") or item.get("record_id")), html.Span(f" · {why}"),
                             html.Blockquote(item["quote"], className="screen-quote")
                             if item.get("quote") and item.get("decision") == "matches" else None,
                             html.Div(judge_numbers(item.get("triage"))),
                             vote_buttons(trace.get("question"), item.get("record_id"), "review")]))
    return [html.Details([
        html.Summary(f"Needs a human check ({len(review)})"),
        html.P("Not listed above and not excluded: the machine checks did not agree clearly enough.", className="scope-note"),
        html.Ul(rows, className="screen-call-list"),
    ], open=len(review) <= 10, className="review-section")]


# Reader checks (migration 0008) -------------------------------------------------

def _question_key(question):
    return hashlib.sha1((question or "").encode("utf-8")).hexdigest()[:12]


def vote_buttons(question, record_id, route):
    """"Relevant" / "Not relevant" for one record; the click is saved, the answer is not changed."""
    if not question or not record_id or route not in ("pass", "review"):
        return None
    key = {"q": _question_key(question), "rid": record_id}
    return html.Span([
        html.Span("Your check: ", className="judge-numbers"),
        *[html.Button(label, id={"type": "rel-vote", **key, "route": route, "v": verdict}, n_clicks=0,
                      className="vote-button") for verdict, label in (("relevant", "Relevant"), ("not_relevant", "Not relevant"))],
        dcc.Store(id={"type": "rel-question", **key}, data=question),
        html.Span(id={"type": "rel-vote-status", **key}, className="judge-numbers"),
    ], className="vote-row")


def save_vote(service, question, triggered, visitor):
    """The status text after a click; `triggered` is the clicked button's id."""
    if not isinstance(triggered, dict) or triggered.get("v") not in ("relevant", "not_relevant"):
        raise PreventUpdate
    try:
        saved = service.review_relevance(question, triggered["rid"], triggered["route"], triggered["v"], visitor)
    except Exception:  # noqa: BLE001 - public boundary; e.g. the reviews table is not migrated yet.
        return " Saving checks is not available right now."
    if not saved:
        return " Daily limit for checks reached."
    return " Saved: " + ("relevant" if triggered["v"] == "relevant" else "not relevant") + ". Thank you."


def reader_reviews_view(counts):
    """What readers' own checks say about each route so far."""
    if not counts:
        return html.P("No reader checks yet. Under each list answer, a reader can mark a listed record or a record "
                      "sent for a human check as relevant or not; the checks are counted here.", className="scope-note")
    items = []
    for route in ("pass", "review"):
        yes, no = counts.get((route, "relevant"), 0), counts.get((route, "not_relevant"), 0)
        if yes + no:
            items.append(html.Li(f"{ROUTE_NAMES[route]}: {yes + no} checked, {yes} relevant ({yes / (yes + no):.0%})."))
    return html.Div([html.P("Readers' own checks so far (each reader counted once per question and record):",
                            className="judge-summary"), html.Ul(items)])


def register_reviews(app, service):
    from dash import ALL, ctx

    @app.callback(
        Output({"type": "rel-vote-status", "q": MATCH, "rid": MATCH}, "children"),
        Input({"type": "rel-vote", "q": MATCH, "rid": MATCH, "route": ALL, "v": ALL}, "n_clicks"),
        State({"type": "rel-question", "q": MATCH, "rid": MATCH}, "data"),
        prevent_initial_call=True,
    )
    def vote(clicks, question):
        if not any(isinstance(n, int) and n > 0 for n in clicks or []):
            raise PreventUpdate
        return save_vote(service, question, ctx.triggered_id, session.get("visitor_id") or "anonymous")

    @app.callback(Output("reader-reviews", "children"), Input("page-location", "pathname"))
    def reader_reviews(pathname):
        if not (pathname or "").rstrip("/").endswith("evaluation"):
            raise PreventUpdate
        try:
            return reader_reviews_view(service.relevance_review_counts())
        except Exception:  # noqa: BLE001 - table missing or database unavailable.
            return html.P("Reader checks are not available right now.", className="scope-note")
