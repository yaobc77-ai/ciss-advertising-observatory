"""Click a year in a timeline chart to list that year's records below it (client item C16).

The year narrows the current selection; it never widens it. "Unknown" lists
records without a publication date, and only while unknown dates are included.
"""

import logging
from datetime import date
from urllib.parse import quote

from dash import Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate

YEAR_ROWS = 10
EXCERPT_CHARS = 160
COLLECTIONS = {"native": "Native ads", "social": "Company social posts"}
UNKNOWN = "Unknown"
log = logging.getLogger(__name__)


def clicked_year(click):
    """The year label of a clicked timeline bar, or None."""
    points = click.get("points") if isinstance(click, dict) else None
    point = points[0] if isinstance(points, list) and points and isinstance(points[0], dict) else {}
    year = str(point.get("x", ""))
    return year if year == UNKNOWN or (year.isdigit() and len(year) == 4) else None


def year_filters(filters, year):
    """The current filters narrowed to one year, or None when the year lies outside them."""
    if year == UNKNOWN:
        if not filters.include_unknown_dates or filters.date_presence == "known":
            return None
        return filters.model_copy(update={"date_from": None, "date_to": None, "date_presence": "missing"})
    start, end = date(int(year), 1, 1), date(int(year), 12, 31)
    start = max(start, filters.date_from) if filters.date_from else start
    end = min(end, filters.date_to) if filters.date_to else end
    if start > end or filters.date_presence == "missing":
        return None
    return filters.model_copy(update={"date_from": start, "date_to": end, "include_unknown_dates": False})


def year_records(service, filters, year, limit=YEAR_ROWS):
    """Totals and newest records of one year, per collection in the selection."""
    narrowed = year_filters(filters, year)
    datasets = list(COLLECTIONS) if filters.dataset == "all" else [filters.dataset]
    collections = []
    for dataset in datasets:
        if narrowed is None:
            collections.append({"dataset": dataset, "total": 0, "rows": []})
            continue
        scoped = narrowed.model_copy(update={"dataset": dataset})
        page = service.page(scoped, offset=0, limit=limit, sort_by="date", descending=True)
        rows = [{key: row.get(key) for key in ("record_id", "version_id", "title", "date", "sponsor", "publisher",
                                               "platform", "account")} for row in page["rows"]]
        if dataset == "social":
            # Social titles are only "Twitter post · <id>"; the post text says what it is about.
            excerpts = _excerpts(service, [row["version_id"] for row in rows if row.get("version_id")])
            for row in rows:
                row["excerpt"] = excerpts.get(row.get("version_id"), "")
        collections.append({"dataset": dataset, "total": page["total"], "rows": rows})
    return {"year": year, "date_from": narrowed.date_from if narrowed else None,
            "date_to": narrowed.date_to if narrowed else None, "collections": collections}


def _excerpts(service, version_ids, length=EXCERPT_CHARS):
    """First characters of each cited version's stored text; empty when unavailable."""
    db = getattr(service, "db", None)
    if not version_ids or db is None or not hasattr(db, "connect"):
        return {}
    try:
        with db.connect() as conn:
            rows = conn.execute("SELECT version_id, left(body, %s) AS excerpt FROM record_versions "
                                "WHERE version_id = ANY(%s)", (length, version_ids)).fetchall()
        return {row["version_id"]: " ".join((row["excerpt"] or "").split()) for row in rows}
    except Exception as exc:  # noqa: BLE001 - excerpts are optional; titles still show.
        log.warning("Year excerpts unavailable: %s", type(exc).__name__)
        return {}


def year_detail(result):
    """Dash children listing one year's records under the timeline."""
    year = result["year"]
    total = sum(item["total"] for item in result["collections"])
    heading = f"{'Unknown publication date' if year == UNKNOWN else year}: {total:,} record{'s' if total != 1 else ''}"
    blocks = []
    for item in result["collections"]:
        name = COLLECTIONS[item["dataset"]]
        shown = len(item["rows"])
        note = (f"{item['total']:,} {name.lower()}" + (f" · newest {shown} shown" if item["total"] > shown else ""))
        rows = [html.Li([
            html.A(_label(row), href="/records/" + quote(str(row["record_id"]), safe=""),
                   target="_blank", rel="noopener"),
            html.Span(" · ".join(str(part) for part in (
                row.get("date") or "Date unknown", row.get("sponsor") or "",
                row.get("publisher") if item["dataset"] == "native" else row.get("account") or row.get("platform"),
            ) if part), className="muted year-record-meta"),
        ]) for row in item["rows"]]
        blocks.append(html.Div([html.H4(name), html.P(note, className="scope-note"),
                                html.Ol(rows, className="year-record-list") if rows else html.P("No records.", className="muted")],
                               className=f"year-collection year-{item['dataset']}"))
    return [html.H3(heading), html.Div(blocks, className="year-collections"),
            html.P("Click another year to switch; use “Browse all” to open the full list with this year as the date filter.",
                   className="scope-note")]


def _label(row):
    excerpt = row.get("excerpt") or ""
    if excerpt:
        return excerpt + ("…" if len(excerpt) >= EXCERPT_CHARS else "")
    return str(row.get("title") or "Untitled record")[:EXCERPT_CHARS]


def year_panel(prefix):
    """Empty container placed under a timeline chart."""
    return html.Section([
        html.Div(id=f"{prefix}-year-detail", children=html.P("Click a year in the chart above to list that year's records here.",
                                                             className="scope-note")),
        html.Button("Browse all records from this year", id=f"{prefix}-year-browse", n_clicks=0,
                    className="button button-quiet", hidden=True),
    ], className="chart-card chart-wide year-drilldown", id=f"{prefix}-year-panel")


def register_year_drilldown(app, service, prefix, filter_inputs, build_filters, view_id):
    """Wire one timeline chart: click → list below; Browse all → date filter + records tab."""
    filter_count = len(filter_inputs(State))

    @app.callback(Output(f"{prefix}-year-detail", "children"), Output(f"{prefix}-year-browse", "hidden"),
                  Input(f"{prefix}-timeline-chart", "clickData"), *filter_inputs(Input),
                  prevent_initial_call=True)
    def show_year(click, *values):
        if ctx.triggered_id != f"{prefix}-timeline-chart":
            return html.P("Click a year in the chart above to list that year's records here.", className="scope-note"), True
        year = clicked_year(click)
        if year is None:
            raise PreventUpdate
        try:
            return year_detail(year_records(service, build_filters(*values[:filter_count]), year)), False
        except Exception as exc:  # noqa: BLE001 - keep the page usable; never show service details.
            log.warning("Year drilldown failed: %s", type(exc).__name__)
            return html.P("This year's records are temporarily unavailable. Try again.", className="scope-note"), True

    @app.callback(Output(f"{prefix}-dates", "start_date", allow_duplicate=True),
                  Output(f"{prefix}-dates", "end_date", allow_duplicate=True),
                  Output(f"{prefix}-unknown-dates", "value", allow_duplicate=True),
                  Output(view_id, "value", allow_duplicate=True),
                  Input(f"{prefix}-year-browse", "n_clicks"), State(f"{prefix}-timeline-chart", "clickData"),
                  *filter_inputs(State), prevent_initial_call=True)
    def browse_year(clicks, click, *values):
        year = clicked_year(click)
        if not clicks or year is None:
            raise PreventUpdate
        narrowed = year_filters(build_filters(*values[:filter_count]), year)
        if narrowed is None or year == UNKNOWN:
            # The date picker cannot express "unknown only"; keep the list above instead.
            raise PreventUpdate
        return narrowed.date_from.isoformat(), narrowed.date_to.isoformat(), [], "records"
