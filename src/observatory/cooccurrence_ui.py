"""Knowledge maps panel: prebuilt co-occurrence projections with saved coordinates."""
from __future__ import annotations

import json
import math
import os
import re
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
# Name-similarity word cloud: canvas in pixels, font sizes, words shown.
CLOUD_W, CLOUD_H, CLOUD_MARGIN = 1200, 680, 40
CLOUD_FONT = (11, 46)
CLOUD_WORDS = 150
TOPICS_PATH = Path(__file__).with_name("hashtag_topics.v1.json")
OTHER = "other"


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


def name_counts(maps):
    """How many posts use each hashtag and how many ads carry each historical label (from the co-occurrence views)."""
    counts = {}
    for name in ("hashtags", "historical_labels"):
        for node in ((maps or {}).get("views", {}).get(name) or {}).get("nodes", []):
            counts[node["id"]] = node.get("n") or 0
    return counts


def _overlaps(box, boxes):
    left, top, right, bottom = box
    return any(left < b[2] and b[0] < right and top < b[3] and b[1] < bottom for b in boxes)


@lru_cache(maxsize=1)
def name_topics():
    """Reviewed topic rules for hashtags and labels (hashtag_topics.v1.json)."""
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def _squash(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


@lru_cache(maxsize=1)
def _organizations():
    from .entities import registry

    return frozenset(_squash(form) for entity in registry().entities.values() if entity.kind == "organization"
                     for form in entity.surface_forms() if len(_squash(form)) >= 3)


def name_topic(node):
    """The first topic whose rules match the name, or "other"."""
    name = _squash(node["label"])
    for topic in name_topics()["topics"]:
        if topic.get("kinds"):
            if node.get("kind") in topic["kinds"]:
                return topic["id"]
            continue
        if name in topic.get("exact", []) or any(fragment in name for fragment in topic.get("fragments", [])):
            return topic["id"]
        if topic.get("registry") and any(name == org or (len(org) >= 4 and name.startswith(org))
                                         for org in _organizations()):
            return topic["id"]
    return OTHER


def topic_style():
    """Topic id -> (label, colour), in rule order, with Other last."""
    style = {t["id"]: (t["label"], PALETTE[i % len(PALETTE)]) for i, t in enumerate(name_topics()["topics"])}
    style[OTHER] = ("Other", "#9A9A9A")
    return style


def _split(items, rect):
    """Treemap: split rect between (key, area) items in proportion to area, along its longer side."""
    if len(items) == 1:
        return {items[0][0]: rect}
    total = sum(area for _, area in items)
    half, running, cut = total / 2, 0, 1
    for i, (_, area) in enumerate(items[:-1]):
        running += area
        cut = i + 1
        if running >= half:
            break
    first, rest = items[:cut], items[cut:]
    share = sum(area for _, area in first) / total
    x0, y0, x1, y1 = rect
    if x1 - x0 >= (y1 - y0) * 1.4:
        mid = x0 + (x1 - x0) * share
        return {**_split(first, (x0, y0, mid, y1)), **_split(rest, (mid, y0, x1, y1))}
    mid = y0 + (y1 - y0) * share
    return {**_split(first, (x0, y0, x1, mid)), **_split(rest, (x0, mid, x1, y1))}


def _size(n, low, top):
    return CLOUD_FONT[0] + (CLOUD_FONT[1] - CLOUD_FONT[0]) * ((math.sqrt(n) - low) / ((top - low) or 1))


@lru_cache(maxsize=4)
def _cloud(key, view_json, counts_json, limit):
    view, counts = json.loads(view_json), json.loads(counts_json)
    nodes = sorted((n for n in view["nodes"] if counts.get(n["id"])), key=lambda n: (-counts[n["id"]], n["id"]))[:limit]
    if not nodes:
        return []
    top, low = math.sqrt(counts[nodes[0]["id"]]), math.sqrt(counts[nodes[-1]["id"]])
    groups = {}
    for node in nodes:
        groups.setdefault(name_topic(node), []).append(node)
    # Each topic gets its own rectangle, sized by the room its words need, so one colour stays in one place.
    need = [(topic, sum((0.56 * _size(counts[n["id"]], low, top) * len(n["label"]) + 4) * 1.2
                        * _size(counts[n["id"]], low, top) for n in members))
            for topic, members in sorted(groups.items(), key=lambda kv: (kv[0] == OTHER, -len(kv[1]), kv[0]))]
    rects = _split(need, (0, 0, CLOUD_W, CLOUD_H))
    placed, boxes = [], []
    for topic, members in groups.items():
        rect = rects[topic]
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        for node in members:
            n = counts[node["id"]]
            size, spot = _size(n, low, top), None
            while spot is None and size >= CLOUD_FONT[0] * 0.6:
                spot = _spot(cx, cy, 0.56 * size * len(node["label"]) + 4, 1.2 * size, boxes, rect)
                if spot is None:
                    size *= 0.85  # a name that does not fit in its topic's area is shown smaller
            if spot is None:
                continue
            boxes.append(spot[2])
            placed.append({"id": node["id"], "label": node["label"], "n": n, "x": spot[0], "y": spot[1],
                           "size": size, "topic": topic,
                           "near": [item["id"] for item in node.get("neighbours", [])[:3]]})
    return placed


def _spot(cx, cy, width, height, boxes, rect):
    """First free position inside rect on an Archimedean spiral out from (cx, cy), or None."""
    aspect = max(0.3, (rect[3] - rect[1]) / max(1, rect[2] - rect[0]))
    for step in range(6000):
        angle = 0.3 * step
        px, py = cx + 1.2 * angle * math.cos(angle), cy + 1.2 * aspect * angle * math.sin(angle)
        box = (px - width / 2, py - height / 2, px + width / 2, py + height / 2)
        if box[0] < rect[0] - 2 * width and box[2] > rect[2] + 2 * width:
            return None  # the spiral has left the rectangle on both sides: no room
        if (box[0] >= rect[0] and box[1] >= rect[1] and box[2] <= rect[2] and box[3] <= rect[3]
                and not _overlaps(box, boxes)):
            return px, py, box
    return None


def word_cloud(view, counts, limit=CLOUD_WORDS):
    """The most used names, sized by use, grouped and coloured by topic, never overlapping."""
    key = (len(view["nodes"]), sum(counts.values()))
    return _cloud(key, json.dumps(view, sort_keys=True), json.dumps(counts, sort_keys=True), limit)


def cloud_figure(words):
    style = topic_style()
    fig = go.Figure()
    for topic, (label, colour) in style.items():
        group = [w for w in words if w["topic"] == topic]
        if not group:
            continue
        fig.add_trace(go.Scatter(
            x=[w["x"] for w in group], y=[w["y"] for w in group], mode="text", text=[w["label"] for w in group],
            textfont={"size": [w["size"] for w in group], "color": colour},
            customdata=[["node", w["id"], w["n"], ", ".join(w["near"])] for w in group],
            hovertemplate=f"%{{text}}: used %{{customdata[2]:,}} times · {label}<br>similar: %{{customdata[3]}}"
                          "<extra></extra>",
            name=f"{label} ({len(group)})"))
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.02, "itemclick": "toggleothers"},
                      margin={"l": 10, "r": 10, "t": 10, "b": 10}, plot_bgcolor="white",
                      xaxis={"visible": False, "range": [0, CLOUD_W]},
                      yaxis={"visible": False, "range": [CLOUD_H, 0]}, clickmode="event")
    return fig


def figure_for(view, colour_by, counts=None):
    """Plotly figure using the saved coordinates; edge midpoints carry the edge index for clicks."""
    if view.get("view") == "semantic" and counts:
        return cloud_figure(word_cloud(view, counts))
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
        # Maps built before 2026-10-22 carry a Chinese label; the page is English.
        return [html.Strong("Similar names (not co-occurrence)"),
                f" · word cloud of the {CLOUD_WORDS} most used of {view['counts']['items']} names. Size: how many "
                "posts use a hashtag, or ads carry a historical label. Colour: topic, from a reviewed keyword list "
                f"({name_topics()['version']}); each topic sits in one place. Click a topic in the legend to show it "
                "alone; hover a word for its closest names; click it for details."]
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
    kind, key = point[0], point[1]
    if view.get("view") == "semantic":
        node = next((n for n in view["nodes"] if n["id"] == key), None)
        if node is None:
            return ""
        used = [html.Div(f"Used {point[2]:,} times (posts for a hashtag, ads for a historical label).")] if len(point) > 2 else []
        return [html.Strong(node["label"]), *used, html.Div("Nearest names (cosine; name similarity, not co-occurrence):"),
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
        return figure_for(view, colour_by, name_counts(maps)), summary_for(maps, view)

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
