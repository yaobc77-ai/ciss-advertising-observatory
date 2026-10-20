"""Knowledge maps panel: prebuilt co-occurrence projections with saved coordinates."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

VIEWS = [
    {"label": "Hashtags", "value": "hashtags"},
    {"label": "Post constellation", "value": "post_constellation"},
    {"label": "Companies", "value": "companies"},
    {"label": "Mentions", "value": "mentions"},
    {"label": "Historical labels", "value": "historical_labels"},
    {"label": "Name similarity", "value": "semantic"},
]
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC"]
EDGE_RECORDS = 30


def maps_dir():
    default = Path(__file__).resolve().parents[2] / ".runtime" / "knowledge_maps"
    return Path(os.getenv("OBS_KNOWLEDGE_MAPS_DIR", str(default)))


@lru_cache(maxsize=2)
def _load(path, mtime):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_maps(directory=None):
    """The most recently built knowledge-map file, or None."""
    files = sorted(Path(directory or maps_dir()).glob("*/knowledge_maps.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    return _load(str(files[-1]), files[-1].stat().st_mtime)


def maps_panel():
    return html.Section([
        html.H2("Knowledge maps"),
        html.P("Each map projects one evidence matrix: an edge means the two ends occur in the same posts or ads, "
               "weighted by Jaccard and kept when either end ranks it in its top k. The name-similarity map is "
               "different: it shows names with similar meaning, not co-occurrence.", className="chart-note"),
        html.Div([
            dcc.RadioItems(id="maps-view", options=VIEWS, value="hashtags", inline=True, className="knowledge-layer"),
            dcc.RadioItems(id="maps-colour", options=[{"label": "Colour by community", "value": "community_id"},
                                                     {"label": "Colour by topic", "value": "topic_id"}],
                           value="community_id", inline=True, className="knowledge-layer"),
        ], className="network-toolbar"),
        html.Div(id="maps-summary", className="chart-note"),
        dcc.Graph(id="maps-figure", config={"displaylogo": False}, style={"height": "720px"}),
        html.Div(id="maps-detail", className="knowledge-inspector"),
    ], className="panel", id="knowledge-maps")


def _colour(value, keys):
    if value is None:
        return "#BBBBBB"
    return PALETTE[keys.index(value) % len(PALETTE)]


def figure_for(view, colour_by):
    """Plotly figure using the saved coordinates; edge midpoints carry the edge index for clicks."""
    nodes = view["nodes"]
    position = {node["id"]: (node["x"], node["y"]) for node in nodes}
    fig = go.Figure()
    if view.get("view") != "semantic":
        xs, ys, mx, my, index = [], [], [], [], []
        for number, edge in enumerate(view["edges"]):
            (x0, y0), (x1, y1) = position[edge["source"]], position[edge["target"]]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
            mx.append((x0 + x1) / 2)
            my.append((y0 + y1) / 2)
            index.append(number)
        fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", hoverinfo="skip", line={"width": 0.5, "color": "#CCCCCC"},
                                   name="edges"))
        fig.add_trace(go.Scattergl(x=mx, y=my, mode="markers", customdata=[["edge", n] for n in index],
                                   marker={"size": 6, "opacity": 0.05}, hoverinfo="skip", name="edge handles"))
    field = colour_by if colour_by in ("community_id", "topic_id") else "community_id"
    if view.get("view") == "semantic":
        field = "kind"
    keys = sorted({node.get(field) for node in nodes if node.get(field) is not None}, key=str)
    fig.add_trace(go.Scattergl(
        x=[node["x"] for node in nodes], y=[node["y"] for node in nodes], mode="markers",
        text=[node["label"] for node in nodes], hovertemplate="%{text}<extra></extra>",
        customdata=[["node", node["id"]] for node in nodes],
        marker={"size": [min(18, 5 + (node.get("n") or 1) ** 0.4) for node in nodes],
                "color": [_colour(node.get(field), keys) for node in nodes], "line": {"width": 0}},
        name="nodes"))
    fig.update_layout(showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10}, plot_bgcolor="white",
                      xaxis={"visible": False}, yaxis={"visible": False}, clickmode="event")
    return fig


def summary_for(maps, view):
    if view.get("view") == "semantic":
        return [html.Strong(view["label"]), f" · {view['counts']['items']} names · {view['method']}"] + [
            html.Div(note) for note in view.get("notes", [])]
    counts, params = view["counts"], view["params"]
    return [html.Div(f"Nodes: {view['node_kind']}; edge: {view['edge_meaning']}; unit: {view['unit_kind']}."),
            html.Div(f"Corpus {counts['corpus_units']} units · candidate nodes {counts['candidate_nodes']} · final nodes "
                     f"{counts['final_nodes']} · candidate edges {counts['candidate_edges']} · kept edges {counts['kept_edges']}."),
            html.Div(f"Minimum co-occurrence {params['min_co']}, top k {params['top_k']}, Louvain resolution "
                     f"{params['resolution']}, seed {params['seed']}. Data version {maps['data_version'][:16]}.")] + [
        html.Div(note) for note in view.get("notes", [])]


def detail_for(view, point):
    if not point:
        return "Click an edge midpoint or a node for details."
    kind, key = point
    if view.get("view") == "semantic":
        node = next((n for n in view["nodes"] if n["id"] == key), None)
        if node is None:
            return ""
        return [html.Strong(node["label"]), html.Div("Nearest names (cosine; name similarity, not co-occurrence):"),
                html.Ul([html.Li(f"{item['id']} · {item['cosine']}") for item in node["neighbours"]])]
    if kind == "node":
        node = next((n for n in view["nodes"] if n["id"] == key), None)
        return [html.Strong(node["label"]), html.Div(f"Occurs in {node['n']} units; community {node['community_id']}; "
                                                     f"topic {node['topic_id']}.")] if node else ""
    if kind != "edge" or not str(key).isdigit() or int(key) >= len(view["edges"]):
        return "Click an edge midpoint or a node for details."
    edge = view["edges"][int(key)]
    refs = edge.get("unit_refs") or edge["units"]
    links = [html.Li(html.A(ref, href=ref) if str(ref).startswith("/records/") else ref) for ref in refs[:EDGE_RECORDS]]
    return [
        html.Strong(f"{edge['source']} — {edge['target']}"),
        html.Div(f"n_A = {edge['n_a']}, n_B = {edge['n_b']}, co-occurrence = {edge['co']}"),
        html.Div(f"Jaccard = co / (n_A + n_B − co) = {edge['co']} / ({edge['n_a']} + {edge['n_b']} − {edge['co']}) = {edge['jaccard']:.3f}"),
        html.Div(f"Lift = co·N / (n_A·n_B) = {edge['lift']:.3f} (below 1: rarer than chance)"),
        html.Div(f"Co-occurring units ({len(refs)}{'; first ' + str(EDGE_RECORDS) if len(refs) > EDGE_RECORDS else ''}):"),
        html.Ul(links),
    ]


def register_cooccurrence_maps(app):
    @app.callback(Output("maps-figure", "figure"), Output("maps-summary", "children"),
                  Input("maps-view", "value"), Input("maps-colour", "value"))
    def draw(view_name, colour_by):
        maps = latest_maps()
        if maps is None:
            return go.Figure(), "No knowledge map has been built for this deployment."
        view = maps["semantic"] if view_name == "semantic" else maps["views"].get(view_name)
        if not view:
            return go.Figure(), "This map is not available in the current build."
        return figure_for(view, colour_by), summary_for(maps, view)

    @app.callback(Output("maps-detail", "children"), Input("maps-figure", "clickData"), Input("maps-view", "value"))
    def detail(click, view_name):
        maps = latest_maps()
        if maps is None:
            return ""
        view = maps["semantic"] if view_name == "semantic" else maps["views"].get(view_name)
        point = None
        if click and click.get("points") and click["points"][0].get("customdata"):
            point = click["points"][0]["customdata"]
        return detail_for(view, point) if view else ""
