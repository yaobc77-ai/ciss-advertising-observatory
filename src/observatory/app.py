"""Public Dash interface. Only explicitly selected public data reaches the browser."""

from __future__ import annotations

import csv
import secrets
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html
from flask import session

from observatory.models import Filters

UNKNOWN = "(Unknown)"
NATIVE_COLUMNS = ("url", "publisher", "title", "date", "sponsor", "keyword")
SOCIAL_COLUMNS = ("platform", "account", "sponsor", "title", "date", "url")
FILTER_NAMES = ("publishers", "sponsors", "platforms", "keywords", "labels")
COLORS = {"ink": "#173b3b", "teal": "#207b76", "muted": "#667772", "amber": "#b67c32"}


def _mapping(value):
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def _url(value):
    """Allow only web destinations, including when the service returns extra data."""
    try:
        value = str(value or "").strip()
        parsed = urlsplit(value)
        return (
            value
            if parsed.scheme.lower() in {"http", "https"} and parsed.netloc
            else ""
        )
    except ValueError:
        return ""


def _public_rows(rows, links_enabled):
    result = []
    for raw in rows:
        item = _mapping(raw)
        row = {
            name: str(item.get(name) or UNKNOWN)
            for name in (
                "publisher",
                "title",
                "date",
                "sponsor",
                "keyword",
                "platform",
                "account",
            )
        }
        row.update(
            {
                name: str(item.get(name) or "")
                for name in ("record_id", "version_id", "dataset")
            }
        )
        row["labels"] = [str(label) for label in (item.get("labels") or [])]
        row["retrievable"] = bool(item.get("retrievable"))
        row["url"] = _url(item.get("url")) if links_enabled else ""
        row["archive_url"] = _url(item.get("archive_url")) if links_enabled else ""
        result.append(row)
    return result


def _filters(
    dataset,
    publishers,
    sponsors,
    platforms,
    keywords,
    labels,
    date_from,
    date_to,
    unknown_dates,
):
    filters = Filters(
        dataset=dataset,
        publishers=publishers or [],
        sponsors=sponsors or [],
        platforms=platforms or [],
        keywords=keywords or [],
        labels=labels or [],
        date_from=date_from or None,
        date_to=date_to or None,
        include_unknown_dates="include" in (unknown_dates or []),
    )
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise ValueError("Start date must be on or before end date.")
    return filters


def _figure(message=None):
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": COLORS["ink"]},
        margin={"l": 16, "r": 18, "t": 18, "b": 35},
        height=290,
        xaxis={"gridcolor": "#e7eeea", "zeroline": False},
        yaxis={"gridcolor": "#e7eeea", "zeroline": False},
    )
    if message:
        figure.add_annotation(
            text=message,
            showarrow=False,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            font={"size": 13, "color": COLORS["muted"]},
        )
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
    return figure


def _bars(items, metric="count"):
    items = sorted(items or [], key=lambda item: item.get("count", 0), reverse=True)[
        :10
    ]
    if not items:
        return _figure("No records in this selection")
    items.reverse()
    figure = _figure()
    figure.add_bar(
        y=[str(item.get("name") or UNKNOWN) for item in items],
        x=[item.get(metric, 0) for item in items],
        orientation="h",
        marker_color=COLORS["teal"],
        customdata=[[item.get("count", 0), item.get("percent", 0)] for item in items],
        hovertemplate="%{y}<br>%{customdata[0]:,} records · %{customdata[1]:.1f}%<extra></extra>",
    )
    figure.update_xaxes(
        title="Share of selected records (%)" if metric == "percent" else "Records",
        rangemode="tozero",
    )
    figure.update_yaxes(automargin=True)
    return figure


def _timeline(items):
    if not items:
        return _figure("No dated records in this selection")
    figure = _figure()
    figure.add_scatter(
        x=[item["month"] for item in items],
        y=[item["count"] for item in items],
        mode="lines+markers",
        line={"color": COLORS["teal"], "width": 2.5},
        marker={"size": 6},
        fill="tozeroy",
        fillcolor="rgba(32,123,118,.09)",
        hovertemplate="%{x}<br>%{y:,} records<extra></extra>",
    )
    figure.update_xaxes(title="Publication month")
    figure.update_yaxes(
        title="Records",
        rangemode="tozero",
        dtick=1 if max(item["count"] for item in items) < 6 else None,
    )
    return figure


def _relationships(items):
    if not items:
        return _figure("No sponsor–outlet relationships in this selection")
    sponsors, publishers = {}, {}
    for item in items:
        sponsor, publisher = (
            item.get("sponsor") or UNKNOWN,
            item.get("publisher") or UNKNOWN,
        )
        sponsors[sponsor] = sponsors.get(sponsor, 0) + item["count"]
        publishers[publisher] = publishers.get(publisher, 0) + item["count"]
    ys = sorted(sponsors, key=sponsors.get, reverse=True)[:8]
    xs = sorted(publishers, key=publishers.get, reverse=True)[:8]
    cells = {
        (item.get("sponsor") or UNKNOWN, item.get("publisher") or UNKNOWN): item[
            "count"
        ]
        for item in items
    }
    figure = _figure()
    figure.add_heatmap(
        x=xs,
        y=ys,
        z=[[cells.get((y, x), 0) for x in xs] for y in ys],
        colorscale=[[0, "#edf3ee"], [1, COLORS["teal"]]],
        showscale=False,
        hovertemplate="%{y} → %{x}<br>%{z:,} records<extra></extra>",
    )
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True, autorange="reversed")
    return figure


def _notice(title, message, kind="info"):
    return html.Div(
        [html.Strong(title), html.P(message)],
        className=f"notice notice-{kind}",
        role="status",
    )


def _search_context(question, filters):
    collection = {
        "native": "Native advertising",
        "social": "Social advertising",
        "all": "Both collections · all eligible records",
    }[filters.dataset]
    selections = [collection]
    for name in FILTER_NAMES:
        values = getattr(filters, name)
        if values:
            selections.append(f"{name.replace('_', ' ').title()}: {', '.join(values)}")
    if filters.date_from or filters.date_to:
        selections.append(
            f"Dates: {filters.date_from or 'any'} to {filters.date_to or 'any'}"
        )
    selections.append(
        "Unknown dates included"
        if filters.include_unknown_dates
        else "Unknown dates excluded"
    )
    return html.Div(
        [
            html.Strong("Last submitted search"),
            html.P(question),
            html.P(" · ".join(selections)),
            html.Small(
                "Run a new search after changing the question, scope or filters."
            ),
        ],
        className="notice notice-info",
    )


def _summary(stats):
    values = [
        ("Selected records", stats.get("total", 0)),
        ("Searchable records", stats.get("retrievable", 0)),
        ("Unknown dates", stats.get("unknown_dates", 0)),
    ]
    return [
        html.Div(
            [
                html.Span(label, className="stat-label"),
                html.Strong(f"{int(value):,}", className="stat-value"),
            ],
            className="stat-card",
        )
        for label, value in values
    ]


def _source_links(item, enabled):
    if not enabled:
        return html.Span("Source links are disabled", className="source-muted")
    links = [
        html.A(
            label,
            href=url,
            target="_blank",
            rel="noopener noreferrer",
            className="source-link",
        )
        for label, value in [
            ("Original source ↗", item.get("url")),
            ("Archived source ↗", item.get("archive_url")),
        ]
        if (url := _url(value))
    ]
    return html.Div(
        links
        or [html.Span("No public source link available", className="source-muted")],
        className="source-links",
    )


def _evidence_cards(evidence, enabled, citations=()):
    citation_quotes = {}
    for citation in citations:
        citation = _mapping(citation)
        citation_quotes.setdefault(citation.get("evidence_id"), []).append(
            str(citation.get("quote") or "")
        )
    cards = []
    for value in evidence:
        item = _mapping(value)
        passage = str(item.get("text") or "")
        supported = [
            quote
            for quote in citation_quotes.get(item.get("evidence_id"), [])
            if quote and quote in passage
        ]
        excerpt = supported[0] if supported else passage
        excerpt = excerpt[:520] + ("…" if len(excerpt) > 520 else "")
        cards.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Span(
                                "Native advertising"
                                if item.get("dataset") == "native"
                                else "Social advertising",
                                className="dataset-chip",
                            ),
                            html.Span(
                                str(item.get("evidence_id") or ""),
                                className="evidence-code",
                            ),
                        ],
                        className="evidence-heading",
                    ),
                    html.H4(str(item.get("title") or "Untitled record")),
                    html.P(
                        " · ".join(
                            str(item.get(key) or UNKNOWN)
                            for key in ("publisher", "sponsor")
                        ),
                        className="muted",
                    ),
                    html.Blockquote(excerpt),
                    html.Details(
                        [
                            html.Summary("Read retrieved passage"),
                            html.P(passage, className="passage"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span(f"Record {item.get('record_id', '')}"),
                            html.Span(f"Version {item.get('version_id', '')}"),
                        ],
                        className="record-reference",
                    ),
                    _source_links(item, enabled),
                ],
                className="evidence-card",
            )
        )
    return cards


def _filter_inputs(dataset, dependency=Input):
    return [dependency(f"{dataset}-{name}", "value") for name in FILTER_NAMES] + [
        dependency(f"{dataset}-dates", "start_date"),
        dependency(f"{dataset}-dates", "end_date"),
        dependency(f"{dataset}-unknown-dates", "value"),
    ]


def _panel(dataset, facets, links_enabled):
    native = dataset == "native"
    names = {
        "publishers": "News outlet",
        "sponsors": "Sponsor / advertiser",
        "platforms": "Platform",
        "keywords": "Collection keyword",
        "labels": "Historical automated label",
    }
    controls = []
    for field in FILTER_NAMES:
        hidden = (native and field == "platforms") or (
            not native and field == "publishers"
        )
        controls.append(
            html.Div(
                [
                    html.Label(names[field], htmlFor=f"{dataset}-{field}"),
                    dcc.Dropdown(
                        id=f"{dataset}-{field}",
                        options=[
                            {"label": value, "value": value}
                            for value in facets.get(field, [])
                        ],
                        value=[],
                        multi=True,
                        placeholder="All",
                        className="filter-dropdown",
                    ),
                ],
                className="filter-field",
                style={"display": "none"} if hidden else {},
            )
        )
    controls += [
        html.Div(
            [
                html.Label("Publication date"),
                dcc.DatePickerRange(
                    id=f"{dataset}-dates",
                    clearable=True,
                    minimum_nights=0,
                    number_of_months_shown=1,
                    display_format="MMM D, YYYY",
                    start_date_placeholder_text="Start date",
                    end_date_placeholder_text="End date",
                ),
            ],
            className="filter-field date-filter",
        ),
        dcc.Checklist(
            id=f"{dataset}-unknown-dates",
            options=[{"label": " Include unknown dates", "value": "include"}],
            value=["include"],
            className="unknown-toggle",
        ),
        html.P(
            "Historical labels come from earlier automated classification runs. Collection keywords are separate from sponsors.",
            className="filter-note",
        ),
    ]
    columns = NATIVE_COLUMNS if native else SOCIAL_COLUMNS
    headers = {
        "url": "Source URL",
        "publisher": "News outlet",
        "title": "Title",
        "date": "Date",
        "sponsor": "Sponsor",
        "keyword": "Keyword",
        "platform": "Platform",
        "account": "Account",
    }
    column_defs = []
    for field in columns:
        column = {
            "field": field,
            "headerName": headers[field],
            "minWidth": 145,
            "flex": 1,
        }
        if field == "title":
            column.update({"minWidth": 260, "flex": 2, "tooltipField": "title"})
        if field == "url":
            column.update(
                {
                    "cellRenderer": "SourceLink",
                    "cellRendererParams": {"enabled": links_enabled},
                    "minWidth": 155,
                }
            )
        column_defs.append(column)
    graph_config = {"displayModeBar": False, "responsive": True}

    def chart(key, title, note=""):
        return html.Section(
            [
                html.H3(title),
                html.P(note, className="chart-note") if note else None,
                dcc.Graph(
                    id=f"{dataset}-{key}",
                    figure=_figure("Choose a collection to explore"),
                    config=graph_config,
                    style={"height": "300px", "width": "100%"},
                ),
            ],
            className="chart-card",
        )

    return html.Section(
        [
            html.Div(id=f"{dataset}-status", className="collection-status"),
            html.Div(
                [
                    html.Aside(
                        [
                            html.Div(
                                [
                                    html.Span("Refine collection", className="eyebrow"),
                                    html.H2("Filters"),
                                ]
                            ),
                            *controls,
                        ],
                        className="filters-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id=f"{dataset}-summary", className="stats-grid"),
                            html.Div(
                                [
                                    html.P(
                                        "Counts reflect eligible records in the current filtered selection.",
                                        className="selection-note",
                                    ),
                                    dcc.RadioItems(
                                        id=f"{dataset}-metric",
                                        options=[
                                            {"label": "Count", "value": "count"},
                                            {"label": "Percent", "value": "percent"},
                                        ],
                                        value="count",
                                        inline=True,
                                        className="metric-toggle",
                                    ),
                                ],
                                className="chart-toolbar",
                            ),
                            html.Div(
                                [
                                    chart(
                                        "primary-chart",
                                        "By news outlet" if native else "By platform",
                                        "Top 10 in this selection",
                                    ),
                                    chart(
                                        "sponsors-chart",
                                        "By sponsor",
                                        "Top 10 in this selection",
                                    ),
                                    chart(
                                        "timeline-chart",
                                        "Over time",
                                        "Unknown dates are counted separately",
                                    ),
                                    html.Div(
                                        chart(
                                            "relationships-chart",
                                            "Sponsors and news outlets",
                                            "Top 8 sponsors and outlets",
                                        ),
                                        style={} if native else {"display": "none"},
                                    ),
                                ],
                                className="charts-grid",
                            ),
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Explore the records",
                                                        className="eyebrow",
                                                    ),
                                                    html.H3("Source collection"),
                                                ]
                                            ),
                                            html.Button(
                                                "Download selected records ↓",
                                                id=f"{dataset}-export",
                                                n_clicks=0,
                                                className="button button-quiet",
                                            ),
                                        ],
                                        className="section-heading",
                                    ),
                                    html.P(
                                        id=f"{dataset}-record-count", className="muted"
                                    ),
                                    dag.AgGrid(
                                        id=f"{dataset}-grid",
                                        columnDefs=column_defs,
                                        rowData=[],
                                        defaultColDef={
                                            "sortable": True,
                                            "resizable": True,
                                            "filter": False,
                                        },
                                        dashGridOptions={
                                            "pagination": True,
                                            "paginationPageSize": 20,
                                            "paginationPageSizeSelector": [20, 50, 100],
                                            "rowHeight": 58,
                                            "animateRows": False,
                                            "suppressCellFocus": False,
                                        },
                                        className="ag-theme-quartz observatory-grid",
                                        style={"height": "510px"},
                                    ),
                                    dcc.Download(id=f"{dataset}-download"),
                                    html.Div(
                                        id=f"{dataset}-export-status", role="status"
                                    ),
                                ],
                                className="records-panel",
                            ),
                        ],
                        className="collection-content",
                    ),
                ],
                className="collection-layout",
            ),
        ],
        id=f"{dataset}-panel",
        style={} if native else {"display": "none"},
    )


def create_app(service, settings) -> Dash:
    """Build the UI against the small public Service contract."""
    enabled = bool(settings.show_source_links)
    app = Dash(
        __name__,
        assets_folder=str(Path(__file__).parent / "assets"),
        title="Advertising Observatory",
        update_title="Loading…",
        suppress_callback_exceptions=False,
    )
    app.server.secret_key = getattr(
        settings, "cookie_secret", None
    ) or secrets.token_hex(32)
    app.server.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax"
    )

    @app.server.get('/healthz')
    def health_endpoint():
        state=service.health()
        return state, (200 if state.get('status')=='ok' else 503)

    def layout():
        try:
            health = service.health()
        except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
            health = {"status": "unavailable"}
        facets = {}
        for dataset in ("native", "social"):
            try:
                facets[dataset] = service.facets(dataset)
            except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
                facets[dataset] = {}
        return html.Div(
            [
                html.Header(
                    [
                        html.A(
                            [
                                html.Span("AO", className="brand-mark"),
                                html.Span(
                                    "Advertising Observatory", className="brand-name"
                                ),
                            ],
                            href="#main",
                            className="brand",
                        ),
                        html.Span("Fossil fuel advertising", className="header-label"),
                    ],
                    className="site-header",
                ),
                html.Main(
                    [
                        html.Section(
                            [
                                html.Span(
                                    "A public research collection", className="eyebrow"
                                ),
                                html.H1("Explore fossil fuel advertising"),
                                html.P(
                                    "Compare sponsors and publishers, trace changes over time, and examine claims using the original advertising records.",
                                    className="hero-description",
                                ),
                            ],
                            className="hero",
                        ),
                        _notice(
                            "Data service unavailable",
                            "The collection could not be loaded. Please try again when the data service is available.",
                            "warning",
                        )
                        if health.get("status") == "unavailable"
                        else None,
                        dcc.Tabs(
                            id="active-dataset",
                            value="native",
                            className="collection-tabs",
                            children=[
                                dcc.Tab(
                                    label="Native advertising",
                                    value="native",
                                    className="collection-tab",
                                    selected_className="collection-tab-selected",
                                ),
                                dcc.Tab(
                                    label="Social advertising",
                                    value="social",
                                    className="collection-tab",
                                    selected_className="collection-tab-selected",
                                ),
                            ],
                        ),
                        _panel("native", facets["native"], enabled),
                        _panel("social", facets["social"], enabled),
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Span(
                                                    "Search the evidence",
                                                    className="eyebrow",
                                                ),
                                                html.H2("Ask a research question"),
                                            ]
                                        ),
                                        html.Span(
                                            "Grounded in collection records",
                                            className="search-badge",
                                        ),
                                    ],
                                    className="section-heading",
                                ),
                                html.P(
                                    "Use keyword search to find passages, or request a paid answer supported by retrieved records.",
                                    className="muted",
                                ),
                                html.Label(
                                    "Research question", htmlFor="research-question"
                                ),
                                dcc.Textarea(
                                    id="research-question",
                                    value="",
                                    placeholder="For example: What claims do sponsors make about carbon capture?",
                                    maxLength=2000,
                                    className="question-input",
                                ),
                                html.Div(
                                    [
                                        dcc.RadioItems(
                                            id="search-scope",
                                            options=[
                                                {
                                                    "label": "Current collection and its filters",
                                                    "value": "current",
                                                },
                                                {
                                                    "label": "Both collections · all eligible records",
                                                    "value": "all",
                                                },
                                            ],
                                            value="current",
                                            className="search-scope",
                                        ),
                                        html.Div(
                                            [
                                                html.Button(
                                                    "Search keywords",
                                                    id="search-free",
                                                    n_clicks=0,
                                                    className="button button-primary",
                                                ),
                                                html.Button(
                                                    "Generate paid answer",
                                                    id="answer-paid",
                                                    n_clicks=0,
                                                    className="button button-secondary",
                                                ),
                                            ],
                                            className="search-actions",
                                        ),
                                    ],
                                    className="search-controls",
                                ),
                                html.P(
                                    "Keyword search uses no paid model calls. Generated answers use the project's API budget. Maximum 2,000 characters.",
                                    className="search-help",
                                ),
                                dcc.Loading(
                                    html.Div(
                                        id="research-results",
                                        children=html.P(
                                            "Results and supporting evidence will appear here.",
                                            className="results-placeholder",
                                        ),
                                        **{"aria-live": "polite"},
                                    ),
                                    type="circle",
                                    color=COLORS["teal"],
                                ),
                            ],
                            className="research-panel",
                        ),
                    ],
                    id="main",
                    className="page-shell",
                ),
                html.Footer(
                    [
                        html.Span("Advertising Observatory · Research collection"),
                        html.Span(
                            "Source links enabled"
                            if enabled
                            else "Source links disabled"
                        ),
                    ],
                    className="site-footer",
                ),
            ]
        )

    app.layout = layout

    @app.callback(
        Output("native-panel", "style"),
        Output("social-panel", "style"),
        Input("active-dataset", "value"),
    )
    def change_collection(dataset):
        return (
            ({}, {"display": "none"})
            if dataset == "native"
            else ({"display": "none"}, {})
        )

    def register_collection(dataset):
        @app.callback(
            Output(f"{dataset}-grid", "rowData"),
            Output(f"{dataset}-summary", "children"),
            Output(f"{dataset}-primary-chart", "figure"),
            Output(f"{dataset}-sponsors-chart", "figure"),
            Output(f"{dataset}-timeline-chart", "figure"),
            Output(f"{dataset}-relationships-chart", "figure"),
            Output(f"{dataset}-status", "children"),
            Output(f"{dataset}-record-count", "children"),
            *_filter_inputs(dataset),
            Input(f"{dataset}-metric", "value"),
        )
        def update_collection(*values):
            try:
                filters = _filters(dataset, *values[:8])
                rows = _public_rows(service.browse(filters), enabled)
                stats = service.statistics(filters)
                health = service.health()
                empty_social = (
                    dataset == "social"
                    and health.get("record_counts", {}).get("social", 0) == 0
                )
                notice = (
                    _notice(
                        "Social advertising is not connected",
                        "This collection will become available when the project's social advertising dataset is added.",
                    )
                    if empty_social
                    else None
                )
                if not rows and not empty_social:
                    notice = _notice(
                        "No matching records",
                        "Try widening the dates or clearing a filter.",
                    )
                metric = "percent" if values[8] == "percent" else "count"
                return (
                    rows,
                    _summary(stats),
                    _bars(
                        stats.get("publishers" if dataset == "native" else "platforms"),
                        metric,
                    ),
                    _bars(stats.get("sponsors"), metric),
                    _timeline(stats.get("timeline")),
                    _relationships(stats.get("relationships")),
                    notice,
                    f"{len(rows):,} eligible records in the current selection. Download uses the same selection.",
                )
            except ValueError:
                message = _notice(
                    "Check the filters",
                    "Use a valid date range with the start date before the end date.",
                    "warning",
                )
            except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
                message = _notice(
                    "Collection temporarily unavailable",
                    "Your filters are preserved. Please try again when the data service is available.",
                    "warning",
                )
            return (
                [],
                _summary({}),
                _figure("Unavailable"),
                _figure("Unavailable"),
                _figure("Unavailable"),
                _figure("Unavailable"),
                message,
                "Records unavailable",
            )

        @app.callback(
            Output(f"{dataset}-download", "data"),
            Output(f"{dataset}-export-status", "children"),
            Input(f"{dataset}-export", "n_clicks"),
            *_filter_inputs(dataset, State),
            prevent_initial_call=True,
        )
        def export_collection(clicks, *values):
            try:
                rows = _public_rows(service.browse(_filters(dataset, *values)), enabled)
                fields = list(
                    NATIVE_COLUMNS if dataset == "native" else SOCIAL_COLUMNS
                ) + ["record_id", "version_id", "labels", "retrievable"]
                if enabled:
                    fields.append("archive_url")
                output = StringIO(newline="")
                writer = csv.DictWriter(
                    output, fieldnames=fields, extrasaction="ignore"
                )
                writer.writeheader()
                for row in rows:
                    row = dict(row, labels="; ".join(row["labels"]))
                    # Keep spreadsheet applications from interpreting source text as formulas.
                    writer.writerow(
                        {
                            k: "'" + v
                            if isinstance(v, str)
                            and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                            else v
                            for k, v in row.items()
                        }
                    )
                return {
                    "content": output.getvalue(),
                    "filename": f"{dataset}-advertising.csv",
                    "type": "text/csv",
                }, f"Downloaded {len(rows):,} selected records."
            except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
                return (
                    None,
                    "Download is unavailable. Your current filters are preserved.",
                )

    register_collection("native")
    register_collection("social")

    @app.callback(
        Output("research-results", "children"),
        Input("search-free", "n_clicks"),
        Input("answer-paid", "n_clicks"),
        State("research-question", "value"),
        State("search-scope", "value"),
        State("active-dataset", "value"),
        *_filter_inputs("native", State),
        *_filter_inputs("social", State),
        prevent_initial_call=True,
        running=[
            (Output("search-free", "disabled"), True, False),
            (Output("answer-paid", "disabled"), True, False),
        ],
    )
    def research(search_clicks, answer_clicks, question, scope, dataset, *values):
        question = (question or "").strip()
        if not question or len(question) > 2000:
            return _notice(
                "Enter a research question",
                "Use between 1 and 2,000 characters.",
                "warning",
            )
        try:
            filters = (
                Filters(dataset="all")
                if scope == "all"
                else _filters(
                    dataset, *(values[:8] if dataset == "native" else values[8:])
                )
            )
        except ValueError:
            return _notice(
                "Check the filters",
                "Use a valid date range before searching.",
                "warning",
            )
        context = _search_context(question, filters)
        if ctx.triggered_id == "search-free":
            try:
                evidence = service.search(question, filters, limit=5)
                return (
                    [
                        context,
                        _notice(
                            "Keyword search",
                            f"{len(evidence)} evidence passages found. No paid model call was made.",
                        ),
                        *_evidence_cards(evidence, enabled),
                    ]
                    if evidence
                    else [
                        context,
                        _notice(
                            "No matching evidence",
                            "Try a different term or widen the search scope.",
                        ),
                    ]
                )
            except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
                return [
                    context,
                    _notice(
                        "Search temporarily unavailable",
                        "The data service could not complete this search. Please try again later.",
                        "warning",
                    ),
                ]
        try:
            if "visitor_id" not in session:
                session["visitor_id"] = secrets.token_urlsafe(24)
            result = _mapping(
                service.answer(question, filters, visitor=session["visitor_id"])
            )
            status = result.get("status", "service_unavailable")
            labels = {
                "answered": "Answer with supporting evidence",
                "insufficient_evidence": "Insufficient evidence",
                "service_unavailable": "Answer service unavailable",
                "limited": "Paid answers temporarily limited",
            }
            if status not in labels:
                status = "service_unavailable"
            if status in {"service_unavailable", "limited"}:
                # Never surface provider exception strings, internal locations or configuration.
                message = (
                    "You can continue browsing the collection and using keyword search."
                )
            else:
                message = str(
                    result.get("answer")
                    or "The available records do not support an answer."
                )
            return [
                context,
                html.Div(
                    [
                        html.Span("Generated answer", className="eyebrow"),
                        html.H3(labels.get(status, labels["service_unavailable"])),
                        html.P(message, className="answer-text"),
                    ],
                    className="answer-card",
                ),
                *_evidence_cards(
                    result.get("evidence") or [], enabled, result.get("citations") or []
                ),
            ]
        except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
            try:
                evidence = service.search(question, filters, limit=5)
            except Exception:  # noqa: BLE001 - public boundary must hide unexpected service details.
                evidence = []
            return [
                context,
                _notice(
                    "Answer service unavailable",
                    "Keyword results are shown when available. You can continue browsing and searching.",
                    "warning",
                ),
                *_evidence_cards(evidence, enabled),
            ]

    return app
