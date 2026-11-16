"""The Compare tab of the combined workspace (client item C15).

Choose a company and up to six keyword topics; the tab shows, for native ads
and social posts side by side, how many times each topic is mentioned and in
how many records, by period, and the newest examples with the matched words linked into the full
text. "Ask about this comparison" fills the question box and opens the
question page with both collections in scope; the paid answer is still the
visitor's own click.
"""

from __future__ import annotations

import logging
from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from .topic_compare import MAX_TOPICS, company_choices, compare_topics, topic_table

log = logging.getLogger(__name__)

CHANNELS = {"native": "Native ads", "social": "Social posts"}
DASH = {"native": "solid", "social": "dot"}
PALETTE = ("#456992", "#168477", "#b5651d", "#7b4f9d", "#a02c2c", "#5b6b2f")
DEFAULT_COMPANY = "ExxonMobil"
DEFAULT_TOPICS = ["carbon_capture"]


def compare_panel():
    companies = [{"label": c["label"] + ("" if len(c["collections"]) == 2 else
                                         f" ({CHANNELS[c['collections'][0]].lower()} only)"), "value": c["value"]}
                 for c in company_choices()]
    topics = [{"label": t["label"], "value": t["id"]} for t in topic_table()["topics"]]
    default = DEFAULT_COMPANY if any(c["value"] == DEFAULT_COMPANY for c in companies) else None
    return html.Div([
        html.P(["Count how many times one company's native ads and its social posts mention a topic, using the "
                "topic's keywords in the saved text, and in how many records. The date filter on the left applies; "
                "other filters do not. The two collections differ in size: each count shows how many records it "
                "comes from."],
               className="scope-note"),
        html.Div([
            html.Div([html.Label("Company", htmlFor="compare-company"),
                      dcc.Dropdown(id="compare-company", options=companies, value=default, clearable=False)]),
            html.Div([html.Label(f"Topics (up to {MAX_TOPICS})", htmlFor="compare-topics"),
                      dcc.Dropdown(id="compare-topics", options=topics, value=DEFAULT_TOPICS, multi=True)]),
            html.Div([html.Label("Period", htmlFor="compare-granularity"),
                      dcc.Dropdown(id="compare-granularity", options=[
                          {"label": "Year", "value": "year"}, {"label": "Quarter", "value": "quarter"}],
                          value="year", clearable=False, searchable=False)]),
        ], className="compare-controls"),
        dcc.Loading(html.Div(id="compare-result", role="region", **{"aria-live": "polite"}), type="circle"),
        html.Div([
            html.Button("Ask about this comparison", id="compare-ask", n_clicks=0, className="button button-primary"),
            html.Span(" Opens the question page with this question filled in; generating the answer uses the API budget.",
                      className="scope-note"),
        ], className="compare-ask"),
        html.Details([html.Summary("Keyword topics used"),
                      html.P(topic_table()["method"], className="scope-note"),
                      html.Ul([html.Li([html.Strong(t["label"]), ": ", ", ".join(t["terms"])])
                               for t in topic_table()["topics"]], className="compare-topic-list"),
                      html.P(f"Topic table {topic_table()['version']} · status: {topic_table()['status']}",
                             className="scope-note")]),
    ], id="all-compare", className="data-view compare-view", hidden=True)


def _figure_for(result):
    from .app import _figure

    figure = _figure()
    labels = {t["id"]: t["label"] for t in result["topics"]}
    for i, tid in enumerate(labels):
        for dataset, channel in CHANNELS.items():
            data = result["datasets"][dataset]
            if not data["total"]:
                continue
            item = data["topics"][tid]
            figure.add_trace(go.Scatter(
                x=result["periods"], y=item["mention_counts"],
                customdata=list(zip(item["counts"], data["period_totals"])), mode="lines+markers",
                name=f"{labels[tid]} · {channel}", line={"color": PALETTE[i % len(PALETTE)], "dash": DASH[dataset]},
                connectgaps=False,
                hovertemplate=("%{x}: %{y:,} mentions in %{customdata[0]:,} of %{customdata[1]:,} records"
                               "<extra>%{fullData.name}</extra>")))
    figure.update_layout(yaxis_title="mentions", xaxis_title=f"publication {result['granularity']}",
                         legend={"orientation": "h", "y": -0.25}, height=380, xaxis_type="category")
    return figure


def _examples(item):
    rows = []
    for ex in item["examples"]:
        snippet = ex["snippet"]
        text = ([snippet["before"], html.Mark(snippet["match"], className="cited-quote"), snippet["after"]]
                if snippet else [])
        rows.append(html.Li([
            html.A(ex["title"] or ex["record_id"], href=ex["record_url"], target="_blank"),
            html.Span(f" · {ex['date'] or 'date unknown'} · {ex['source']}", className="year-record-meta"),
            html.Blockquote(text, className="compare-snippet") if text else None,
        ]))
    return html.Ol(rows, className="year-record-list") if rows else html.P("No matching records.", className="scope-note")


def render(result):
    if result["status"] == "not_found":
        return html.P(result["message"], className="scope-note")
    cards, details = [], []
    for topic in result["topics"]:
        tid = topic["id"]
        cells = []
        for dataset, channel in CHANNELS.items():
            data = result["datasets"][dataset]
            item = data["topics"][tid]
            cells.append(html.Div([
                html.Span(channel, className="stat-label"),
                html.Strong(f"{item['mentions']:,}", className="stat-value"),
                html.Span(f"mentions · in {item['matched']:,} of {data['total']:,} records" +
                          (f" · {item['undated']:,} undated" if item["undated"] else ""), className="scope-note"),
            ], className="stat-card"))
        cards.append(html.Div([html.H4(topic["label"]), html.Div(cells, className="stats-grid")],
                              className="compare-topic"))
        details.append(html.Details([
            html.Summary(f"Newest examples: {topic['label']}"),
            html.Div([html.Div([html.H5(channel), _examples(result["datasets"][dataset]["topics"][tid])])
                      for dataset, channel in CHANNELS.items()], className="year-collections"),
        ], open=len(details) == 0))
    spell = "; ".join(f"{CHANNELS[d]}: {', '.join(v['source_spellings']) or 'none'}" for d, v in result["datasets"].items())
    return html.Div([
        html.H3(f"{result['company']}: native ads vs. social posts"),
        *cards,
        dcc.Graph(figure=_figure_for(result), config={"displayModeBar": False}) if result["periods"] else
        html.P("No dated records in this range.", className="scope-note"),
        *details,
        html.P([f"Source spellings used — {spell}. Organization match: {result['review_status'].replace('_', ' ')}. ",
                result["measure"], " ", result["date_basis"], " ", result["interpretation"]], className="scope-note"),
    ])


def _day(value):
    return date.fromisoformat(value[:10]) if value else None


def register_topic_compare(app, service):
    @app.callback(Output("compare-result", "children"),
                  Input("compare-company", "value"), Input("compare-topics", "value"),
                  Input("compare-granularity", "value"), Input("all-dates", "start_date"),
                  Input("all-dates", "end_date"), Input("all-view", "value"))
    def show_comparison(company, topics, granularity, start, end, view):
        if view != "compare":
            raise PreventUpdate
        if not company or not topics:
            return html.P("Choose a company and at least one topic.", className="scope-note")
        if len(topics) > MAX_TOPICS:
            return html.P(f"Choose at most {MAX_TOPICS} topics.", className="scope-note")
        try:
            return render(compare_topics(service.db, company, topics, granularity=granularity,
                                         date_from=_day(start), date_to=_day(end)))
        except ValueError as exc:
            return html.P(str(exc), className="scope-note")
        except Exception as exc:  # noqa: BLE001 - no internal details in the page.
            log.warning("Comparison failed: %s", type(exc).__name__)
            return html.P("The comparison is temporarily unavailable.", className="scope-note")


def register_compare_ask(app):
    """Registered last: the question box and page location belong to the question page."""
    @app.callback(Output("research-question", "value", allow_duplicate=True),
                  Output("search-scope", "value", allow_duplicate=True),
                  Output("page-location", "pathname", allow_duplicate=True),
                  Input("compare-ask", "n_clicks"), State("compare-company", "value"), State("compare-topics", "value"),
                  prevent_initial_call=True)
    def ask_about(clicks, company, topics):
        if not clicks or not company or not topics:
            raise PreventUpdate
        from .topic_compare import ask_question

        return ask_question(company, topics), "all", "/query"
