"""Evaluation page: how deep a list should read, from a saved Decisions-judge run (no model calls).

A list question ranks the ads by search, reads them in that order and stops by
rank 120. scripts/decisions_depth_demo.py scored every ranked native ad of five
label questions (team hand coding, not the customer's questions) with the
Decisions judge and saved the result; this section draws it next to the
relevance check. No saved run, no section. The groups are the judge's own
confidence, not accuracy (depth_demo.group_of).
"""

from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html

from .depth_demo import FIRST_READ, GROUP_NAMES, STOP_AT, band_counts, bands, load
from .relevance_triage import PASS_AT

GROUP_COLORS = {"likely": "#2f7d4f", "unsure": "#c98a1b", "unlikely": "#8a94a3", "not_scored": "#c9ced6"}
LIVE = {True: "yes", False: "no", None: "not checked"}


def _depth(result):
    """A scope smaller than the asked depth is ranked whole: draw to its last rank."""
    ranked = [q["ranked"] for q in result["questions"]]
    return min(result["depth"], max(ranked, default=result["depth"]))


def _layout(figure, height, x_title, y_title, depth):
    figure.update_layout(template="plotly_white", height=height, margin={"l": 16, "r": 16, "t": 36, "b": 40},
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         xaxis={"title": x_title, "range": [0, depth + 1]}, yaxis={"title": y_title},
                         legend={"orientation": "h", "y": -0.3})
    for rank, name in ((FIRST_READ, f"first {FIRST_READ} read"), (STOP_AT, f"reading stops by {STOP_AT}")):
        if rank < depth:
            # Labels sit above the plot so they never cover a dot.
            figure.add_vline(x=rank + 0.5, line_dash="dot", line_color="#687587")
            figure.add_annotation(x=rank + 0.5, y=1, yref="paper", yanchor="bottom", xanchor="left", text=name,
                                  showarrow=False, font={"size": 12, "color": "#687587"})
    return dcc.Graph(figure=figure, config={"displayModeBar": False})


def _scatter(ads, depth, pass_at):
    """P(meets) of every scored ad against its retrieval rank; hand-coded articles ringed."""
    figure = go.Figure()
    scored = [ad for ad in ads if ad["numbers"] is not None]
    for group in ("likely", "unsure", "unlikely"):
        dots = [ad for ad in scored if ad["group"] == group]
        if dots:
            figure.add_scatter(x=[ad["rank"] for ad in dots], y=[ad["numbers"]["meets"] for ad in dots], mode="markers",
                               name=GROUP_NAMES[group] + (f" (P ≥ {pass_at:g})" if group == "likely" else ""),
                               marker={"color": GROUP_COLORS[group], "size": 7, "opacity": 0.85},
                               customdata=[ad["title"] or ad["record_id"] for ad in dots],
                               hovertemplate="#%{x} %{customdata}<br>P(meets) %{y:.0%}<extra></extra>")
    coded = [ad for ad in scored if ad.get("human") is not None]
    if coded:
        figure.add_scatter(x=[ad["rank"] for ad in coded], y=[ad["numbers"]["meets"] for ad in coded], mode="markers",
                           name="Hand-coded article", marker={"symbol": "circle-open", "size": 13, "color": "#003262"},
                           customdata=[[ad["title"] or ad["record_id"], "relevant" if ad["human"] else "not relevant"]
                                       for ad in coded],
                           hovertemplate="#%{x} %{customdata[0]}<br>Coders: %{customdata[1]}<extra></extra>")
    graph = _layout(figure, 320, "Retrieval rank", "P(meets the rules)", depth)
    figure.update_yaxes(range=[-0.04, 1.04], tickformat=".0%")
    return graph


def _cumulative(ads, depth):
    """How many 'likely' ads have been found by each rank."""
    if depth < 1:
        return html.P("No ranked ads.", className="scope-note")
    by_rank = {ad["rank"]: ad for ad in ads}
    found, xs, ys = 0, [], []
    for rank in range(1, depth + 1):
        found += by_rank.get(rank, {}).get("group") == "likely"
        xs.append(rank)
        ys.append(found)
    figure = go.Figure()
    figure.add_scatter(x=xs, y=ys, mode="lines", name="Likely ads found", line={"color": "#003262", "width": 2.5},
                       hovertemplate="By rank %{x}: %{y} likely<extra></extra>")
    marks = [rank for rank in (FIRST_READ, STOP_AT, depth) if rank <= depth]
    figure.add_scatter(x=marks, y=[ys[rank - 1] for rank in marks], mode="markers+text", showlegend=False,
                       text=[str(ys[rank - 1]) for rank in marks], textposition="top left",
                       marker={"color": "#003262", "size": 9}, hoverinfo="skip")
    graph = _layout(figure, 260, "Retrieval rank", "Likely ads found", depth)
    figure.update_yaxes(range=[0, max(ys[-1], 1) * 1.18])
    return graph


def _tile(number, label, color):
    return html.Div([html.Span(number, className="judge-tile-number"), html.Span(label, className="judge-tile-label")],
                    className="judge-tile", style={"borderLeftColor": color})


def _table(caption, heads, rows):
    return html.Div(html.Table([html.Caption(caption), html.Thead(html.Tr([html.Th(h, scope="col") for h in heads])),
                                html.Tbody(rows)]), className="statistics-table")


def _ad_rows(ads):
    rows = []
    for ad in ads:
        judge = {"cap": "Not scored (cost cap)", "failed": "Call failed"}.get(ad.get("status"), GROUP_NAMES[ad["group"]])
        human = {True: "relevant", False: "not relevant", None: ""}[ad.get("human")]
        source = " · ".join(str(v) for v in (ad.get("publisher"), ad.get("sponsor"), ad.get("date")) if v)
        rows.append(html.Tr([
            html.Td(ad["rank"]), html.Td("–" if ad["numbers"] is None else f"{ad['numbers']['meets']:.0%}"),
            html.Td([html.A(ad["title"] or "Record", href=f"/records/{ad['record_id']}", target="_blank", rel="noopener"),
                     html.Div(source, className="scope-note") if source else None]),
            html.Td(judge), html.Td(human), html.Td(LIVE[ad.get("in_live_top")])]))
    return rows


AD_HEADS = ("Rank", "P(meets)", "Ad", "Judge", "Hand-coded", f"In the search's {STOP_AT}")


def _rule_rows(question, ads):
    rows = []
    for n, rule in enumerate(question["criterion"]["counts"]):
        hits = [ad for ad in ads if ad["numbers"] and len(ad["numbers"]["rules"]) > n and ad["numbers"]["rules"][n] >= 0.5]
        rows.append(html.Tr([html.Td(rule), html.Td(sum(ad["rank"] <= STOP_AT for ad in hits)),
                             html.Td(sum(ad["rank"] > STOP_AT for ad in hits))]))
    return rows


def _live_note(question, past, checked):
    if any("in_live_top" in ad for ad in past):
        missed = sum(ad.get("in_live_top") is False for ad in past)
        return (f"{missed} of them are not among the {question['shallow_ranked']} ads the answer's search returns for "
                f"this wording of the question (checked {checked or 'after the run'} on the same collection). A list "
                f"reads at most those {STOP_AT}, so it would not reach them; a reworded query ranks differently.")
    return (f"A live answer ranks its own {question['shallow_ranked']} ads, and they share {question['top_overlap']} "
            f"with the first {STOP_AT} here, so some of these may still be read; this run did not record which.")


def _question_tab(question, depth, result):
    ads = question["ads"]
    pass_at = result.get("pass_at", PASS_AT)
    checked = (result.get("live_top_checked_utc") or "")[:10] or None
    past = sorted((ad for ad in ads if ad["rank"] > STOP_AT and ad["group"] == "likely"),
                  key=lambda ad: -ad["numbers"]["meets"])
    coded = [ad for ad in ads if ad.get("human") is not None]
    criterion = question["criterion"]
    coverage = [f"Scored {question['scored']} of {question['ranked']} ranked ads"]
    if question.get("failed"):
        coverage.append(f"{question['failed']} calls failed")
    if question.get("not_scored_cap"):
        coverage.append(f"{question['not_scored_cap']} not scored (cost cap)")
    tiles = [_tile(f"{c['likely']}", f"likely in ranks {c['from']}–{c['to']} ({c['unsure']} unsure, "
                   f"{c['unlikely']} unlikely" + (f", {c['not_scored']} not scored" if c["not_scored"] else "") + ")",
                   GROUP_COLORS["likely"] if c["to"] <= STOP_AT else "#a86b25")
             for c in band_counts(ads, depth)]
    return dcc.Tab(label=question["short"], value=question["label"], className="data-tab",
                   selected_className="data-tab-selected", children=html.Div([
        html.H4(question["question"]),
        html.Details([
            html.Summary(f"Rules the judge scored against ({len(criterion['counts'])} rules"
                         + (f", {len(criterion.get('does_not_count') or [])} exclusions)" if criterion.get("does_not_count") else ")")),
            html.Ol([html.Li(rule) for rule in criterion["counts"]], className="criterion-rules"),
            html.P(html.Strong("Does not count:")) if criterion.get("does_not_count") else None,
            html.Ol([html.Li(rule) for rule in criterion.get("does_not_count") or []], className="criterion-exclusions"),
            html.P("Drafted by a model from the question for the 24 Oct validation run; not confirmed by a researcher.",
                   className="scope-note"),
        ]),
        html.P(", ".join(coverage) + f". {question.get('truncated', 0)} long articles were cut at "
               f"{result['max_ad_chars']:,} characters, as in a live answer. The first {STOP_AT} ranks here share "
               f"{question['top_overlap']} ads with the {question['shallow_ranked']} a live answer's search returns.",
               className="scope-note"),
        html.Div(tiles, className="judge-tiles"),
        html.H3("Judge score of each ad, in the order search ranked them"),
        _scatter(ads, depth, pass_at),
        html.H3("Likely ads found so far, reading down the ranking"),
        _cumulative(ads, depth),
        _table("Ads whose probability for a rule is at least 50%, within and past the stopping rank",
               ("Rule", f"Ranks 1–{STOP_AT}", f"Past {STOP_AT}"), _rule_rows(question, ads)),
        html.H3(f"Likely ads past rank {STOP_AT} in this ranking ({len(past)})"),
        html.P(_live_note(question, past, checked), className="scope-note") if past else None,
        _table("Strongest first; the title opens the record", AD_HEADS, _ad_rows(past)) if past
        else html.P("None: the judge rates no ad past this rank as likely.", className="scope-note"),
        html.Details([html.Summary(f"Hand-coded articles in this ranking ({len(coded)})"),
                      _table("The research team's coding next to the judge", AD_HEADS, _ad_rows(coded))])
        if coded else None,
    ], className="depth-question"))


def _summary(result, depth):
    heads = ["Question", *[f"Likely, ranks {lo}–{hi}" for lo, hi in bands(depth)],
             f"Of those past {STOP_AT}, not in the search's {STOP_AT}", "Scored / ranked", "Cost"]
    rows = []
    for q in result["questions"]:
        past = [ad for ad in q["ads"] if ad["rank"] > STOP_AT and ad["group"] == "likely"]
        missed = (sum(ad.get("in_live_top") is False for ad in past) if any("in_live_top" in ad for ad in past)
                  else "not checked" if past else 0)
        rows.append(html.Tr([html.Td(q["short"]), *[html.Td(b["likely"]) for b in band_counts(q["ads"], depth)],
                             html.Td(missed), html.Td(f"{q['scored']} / {q['ranked']}"), html.Td(f"${q['cost_usd']:.3f}")]))
    return _table("Ads the judge rates likely to meet each question's rules, by retrieval rank", heads, rows)


def _section(result):
    questions = result["questions"]
    depth = _depth(result)
    first = questions[0] if questions else {"ranked": 0, "scope_total": 0}
    reach = (f"every native ad with searchable text ({first['ranked']} of the {first['scope_total']:,} in the collection)"
             if depth < result["depth"] else f"the first {depth} ranked native ads")
    uncertain = (f", of which ${result['uncertain_usd']:.4f} is held for calls whose usage was not reported"
                 if result.get("uncertain_usd") else "")
    meta = (f"Scored {result['run_date']} with {result['model']}; ${result['cost_usd']:.3f} spent{uncertain}; "
            f"cap ${result['cap_usd']:.2f}.")
    if result.get("data_version_after", result.get("data_version")) != result.get("data_version"):
        meta += " The collection changed while this run was scoring; ranks may mix two versions."
    return html.Section([
        html.H2("How deep should a list read?"),
        html.P(f"A list question ranks the ads by search, reads them in that order and stops by rank {STOP_AT}. Here the "
               f"Decisions judge (about $0.00025 an ad) scored {reach} against each question's rules, so you can see "
               f"where likely matches thin out and how many sit past rank {STOP_AT}. The questions are the five of the "
               "hand-coded check above.", className="scope-note"),
        _summary(result, depth),
        dcc.Tabs(value=questions[0]["label"] if questions else None, mobile_breakpoint=0, className="data-tabs",
                 parent_className="data-tabs-container",
                 children=[_question_tab(q, depth, result) for q in questions]),
        html.P([html.Strong("What this is not. "),
                "“Likely” is the judge's own confidence, not accuracy. Apart from the 15 hand-coded articles nobody has "
                f"labelled these ads, so a likely ad past rank {STOP_AT} is worth a look, not a confirmed miss. A listed "
                "ad in a real answer still needs a sentence quoted from it and checked word for word."],
               className="judge-summary"),
        html.P(meta, className="scope-note"),
    ], className="depth-section", **{"aria-label": "How deep a list should read"})


def depth_section(result=None):
    """The section for the Evaluation page, or None when no run is saved."""
    try:
        result = result if result is not None else load()
        return _section(result) if result else None
    except (OSError, ValueError, KeyError, TypeError, IndexError):  # a damaged or unreadable file must not break the page
        return html.Section([html.H2("How deep should a list read?"),
                             html.P("The saved scoring run could not be read.", className="scope-note")],
                            className="depth-section")
