"""/depth-demo: how deep a list should read, shown from Decisions-API scores (demo, no model calls).

A list question reads its ranked candidates in order and stops by 120 at most. A
saved run of scripts/decisions_depth_demo.py scored the first 400 ranked native
ads of each question with the Decisions judge (gpt-6-luna, about $0.00025 an
ad). This page draws those scores against the retrieval rank, so a reader sees
where likely matches thin out and how many sit past the current stopping point.

The groups are the judge's alone: "likely" when P(meets) >= PASS_AT, "unlikely"
when relevance_triage.excludable, else "unsure". That is model confidence, not
accuracy: a listed ad still needs screening's verified sentence. The page only
reads the saved result. Off unless OBS_DEPTH_DEMO_ENABLED=true; the result path
is OBS_DEPTH_DEMO_RESULT or .runtime/decisions_depth_demo/result.json.
"""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

from flask import jsonify

from .relevance_triage import PASS_AT, excludable

DEFAULT_RESULT = Path(__file__).resolve().parents[2] / ".runtime" / "decisions_depth_demo" / "result.json"
# Ranks where the current list reading pauses (MAX_CANDIDATES) and stops (MAX_WIDENED).
FIRST_READ, STOP_AT = 40, 120
GROUPS = ("likely", "unsure", "unlikely", "not_scored")
GROUP_NAMES = {"likely": "Likely", "unsure": "Unsure", "unlikely": "Unlikely", "not_scored": "Not scored"}


def group_of(numbers):
    """The judge's group for one ad from its numbers alone."""
    if numbers is None:
        return "not_scored"
    if excludable(numbers):
        return "unlikely"
    return "likely" if numbers["meets"] >= PASS_AT else "unsure"


def bands(depth):
    """(first rank, last rank) of each reading band up to `depth`."""
    return [(lo, min(hi, depth)) for lo, hi in ((1, FIRST_READ), (FIRST_READ + 1, STOP_AT), (STOP_AT + 1, depth)) if lo <= depth]


def band_counts(ads, depth):
    """Per band: ads and how many fall in each group."""
    out = []
    for lo, hi in bands(depth):
        inside = [ad for ad in ads if lo <= ad["rank"] <= hi]
        out.append({"from": lo, "to": hi, "ads": len(inside),
                    **{group: sum(ad["group"] == group for ad in inside) for group in GROUPS}})
    return out


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


# ---------- drawing ----------

W, H, LEFT, RIGHT, TOP, BOTTOM = 960, 316, 56, 16, 32, 40
COLORS = {"likely": "var(--likely)", "unsure": "var(--unsure)", "unlikely": "var(--unlikely)", "not_scored": "var(--muted)"}


def _x(rank, depth):
    return LEFT + (rank - 0.5) / max(depth, 1) * (W - LEFT - RIGHT)


def _y(value, top_value):
    return TOP + (1 - value / top_value) * (H - TOP - BOTTOM) if top_value else H - BOTTOM


def _rank_axis(depth):
    ticks = [1, *range(50, depth + 1, 50)] if depth >= 50 else [1, depth]
    parts = [f'<line x1="{LEFT}" y1="{H - BOTTOM}" x2="{W - RIGHT}" y2="{H - BOTTOM}" class="axis"/>']
    for t in ticks:
        x = _x(t, depth)
        parts.append(f'<text x="{x:.1f}" y="{H - BOTTOM + 18}" text-anchor="middle" class="tick">{t}</text>')
    parts.append(f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{H - 4}" text-anchor="middle" class="label">Retrieval rank</text>')
    for rank, name in ((FIRST_READ, f"first {FIRST_READ} read"), (STOP_AT, f"reading stops by {STOP_AT}")):
        if rank < depth:
            x = _x(rank + 0.5, depth)
            parts.append(f'<line x1="{x:.1f}" y1="{TOP}" x2="{x:.1f}" y2="{H - BOTTOM}" class="cut"/>'
                         f'<text x="{x + 6:.1f}" y="{TOP - 12}" class="cutlabel">{name}</text>')
    return "".join(parts)


def scatter(ads, depth):
    """P(meets) of every scored ad against its retrieval rank."""
    parts = [_rank_axis(depth)]
    for value in (0, 0.5, 1):
        y = _y(value, 1)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}" class="grid"/>'
                     f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{value:g}</text>')
    parts.append(f'<text x="14" y="{(TOP + H - BOTTOM) / 2:.0f}" transform="rotate(-90 14 {(TOP + H - BOTTOM) / 2:.0f})" '
                 'text-anchor="middle" class="label">P(meets the rules)</text>')
    for ad in ads:
        if ad["numbers"] is None:
            continue
        x, y = _x(ad["rank"], depth), _y(ad["numbers"]["meets"], 1)
        ring = ' class="coded"' if ad.get("human") is not None else ""
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{COLORS[ad["group"]]}"{ring}>'
                     f'<title>#{ad["rank"]} {escape(ad["title"] or "")}: P(meets) {ad["numbers"]["meets"]:.2f}</title></circle>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Judge score by retrieval rank, {len(ads)} ads">'
            + "".join(parts) + "</svg>")


def cumulative(ads, depth):
    """How many 'likely' ads have been found by each rank."""
    if depth < 1:
        return '<p class="placeholder">No ranked ads.</p>'
    found, points = 0, []
    by_rank = {ad["rank"]: ad for ad in ads}
    for rank in range(1, depth + 1):
        found += by_rank.get(rank, {}).get("group") == "likely"
        points.append((rank, found))
    total = found or 1
    parts = [_rank_axis(depth)]
    for value in sorted({0, total}):
        y = _y(value, total)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}" class="grid"/>'
                     f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" class="tick">{value}</text>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{_x(rank, depth):.1f},{_y(n, total):.1f}" for i, (rank, n) in enumerate(points))
    parts.append(f'<path d="{path}" class="line"/>')
    for rank in (FIRST_READ, STOP_AT, depth):
        if rank <= depth:
            n = points[rank - 1][1]
            parts.append(f'<circle cx="{_x(rank, depth):.1f}" cy="{_y(n, total):.1f}" r="4.5" class="mark"/>'
                         f'<text x="{_x(rank, depth) - 6:.1f}" y="{_y(n, total) - 9:.1f}" text-anchor="end" class="value">{n}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Likely ads found by rank: '
            f'{points[min(STOP_AT, depth) - 1][1]} by rank {min(STOP_AT, depth)}, {found} by rank {depth}">'
            + "".join(parts) + "</svg>")


def rule_rows(question, ads):
    """Per inclusion rule: ads whose rule probability is at least 0.5, within and past the stopping rank."""
    rows = []
    for n, rule in enumerate(question["criterion"]["counts"]):
        hits = [ad for ad in ads if ad["numbers"] and len(ad["numbers"]["rules"]) > n and ad["numbers"]["rules"][n] >= 0.5]
        rows.append({"rule": rule, "within": sum(ad["rank"] <= STOP_AT for ad in hits),
                     "past": sum(ad["rank"] > STOP_AT for ad in hits)})
    return rows


# ---------- page ----------

def _ad_row(ad):
    meets = "—" if ad["numbers"] is None else f'{ad["numbers"]["meets"]:.2f}'
    source = " · ".join(escape(str(v)) for v in (ad.get("publisher"), ad.get("sponsor"), ad.get("date")) if v)
    human = {True: "relevant", False: "not relevant", None: ""}[ad.get("human")]
    judge = {"cap": "Not scored (cost cap)", "failed": "Call failed"}.get(ad.get("status"), GROUP_NAMES[ad["group"]])
    live = {True: "yes", False: "no", None: "not checked"}[ad.get("in_live_top")]
    return (f'<tr><td class="num">{ad["rank"]}</td><td class="num">{meets}</td>'
            f'<td><a href="/records/{escape(ad["record_id"])}" target="_blank" rel="noopener">{escape(ad["title"] or "Record")}</a>'
            f'<div class="src">{source}</div></td><td>{judge}</td><td>{human}</td><td>{live}</td></tr>')


def _table(ads, empty):
    if not ads:
        return f'<p class="placeholder">{empty}</p>'
    return ('<div class="scroll"><table><thead><tr><th>Rank</th><th>P(meets)</th><th>Ad</th><th>Judge</th>'
            f'<th>Hand-coded</th><th>In the search\'s {STOP_AT}</th></tr></thead><tbody>' + "".join(_ad_row(ad) for ad in ads) + "</tbody></table></div>")


def _question_section(index, question, depth, result_chars, pass_at=PASS_AT, checked=None):
    ads = question["ads"]
    counts = band_counts(ads, depth)
    past = [ad for ad in ads if ad["rank"] > STOP_AT and ad["group"] == "likely"]
    past.sort(key=lambda ad: -ad["numbers"]["meets"])
    coded = [ad for ad in ads if ad.get("human") is not None]
    rules = "".join(f'<li>{escape(rule)}</li>' for rule in question["criterion"]["counts"])
    exclusions = "".join(f'<li>{escape(rule)}</li>' for rule in question["criterion"].get("does_not_count") or [])
    band_cells = "".join(
        f'<div class="tile"><div class="tile-n">{c["likely"]}</div><div class="tile-l">likely in ranks {c["from"]}–{c["to"]}'
        f'</div><div class="tile-s">{c["unsure"]} unsure · {c["unlikely"]} unlikely'
        + (f' · {c["not_scored"]} not scored' if c["not_scored"] else "") + "</div></div>" for c in counts)
    rule_list = "".join(f'<tr><td>{escape(r["rule"])}</td><td class="num">{r["within"]}</td><td class="num">{r["past"]}</td></tr>'
                        for r in rule_rows(question, ads))
    if any("in_live_top" in ad for ad in past):
        missed = sum(ad["in_live_top"] is False for ad in past)
        live_note = (f"{missed} of them are not among the {question['shallow_ranked']} ads the answer's search returns "
                     f"for this wording of the question (checked {escape(checked or 'after the run')} on the same collection). "
                     f"A list reads at most those {STOP_AT}, so it would not reach them; a reworded query ranks differently.")
    else:
        live_note = (f"A live answer ranks its own {question['shallow_ranked']} ads, and they share "
                     f"{question['top_overlap']} with the first {STOP_AT} here, so some of these may still be read; "
                     "this run did not record which.")
    hidden = "" if index == 0 else " hidden"
    return f"""<section class="question" id="q{index}" role="tabpanel" aria-labelledby="t{index}"{hidden}>
  <h2>{escape(question["question"])}</h2>
  <details class="rules"><summary>Rules the judge scored against ({len(question["criterion"]["counts"])} rules{
      f', {len(question["criterion"].get("does_not_count") or [])} exclusions' if exclusions else ""})</summary>
    <ol>{rules}</ol>{f'<p class="sub">Does not count:</p><ul>{exclusions}</ul>' if exclusions else ""}
    <p class="sub">Drafted by a model from the question for the 24 Oct validation run; not confirmed by a researcher.</p></details>
  <p class="sub">Scored {question["scored"]} of {question["ranked"]} ranked ads{
      f', {question["failed"]} calls failed' if question["failed"] else ""}{
      f', {question["not_scored_cap"]} not scored (cost cap)' if question["not_scored_cap"] else ""}.
    {question["truncated"]} long articles were cut at {result_chars:,} characters, as in a live answer.
    The first {STOP_AT} ranks here share {question["top_overlap"]} ads with the {question["shallow_ranked"]} a live answer would rank.</p>
  <div class="tiles">{band_cells}</div>
  <figure><figcaption>Judge score of each ad, in the order search ranked them. Ringed dots are hand-coded articles.</figcaption>
    {scatter(ads, depth)}
    <div class="legend"><span><i style="background:var(--likely)"></i>Likely (P ≥ {pass_at:g})</span>
      <span><i style="background:var(--unsure)"></i>Unsure</span><span><i style="background:var(--unlikely)"></i>Unlikely</span></div></figure>
  <figure><figcaption>Likely ads found so far, reading down the ranking.</figcaption>{cumulative(ads, depth)}</figure>
  <h3>Which rules the ads meet</h3>
  <div class="scroll"><table><thead><tr><th>Rule</th><th>Ranks 1–{STOP_AT}</th><th>Past {STOP_AT}</th></tr></thead>
    <tbody>{rule_list}</tbody></table></div>
  <h3>Likely ads past rank {STOP_AT} in this ranking ({len(past)})</h3>
  <p class="sub">{live_note}</p>
  {_table(past, "None: the judge rates no ad past this rank as likely.")}
  <details><summary>Hand-coded articles in this ranking ({len(coded)})</summary>
    {_table(coded, "None of the hand-coded articles is in this ranking.")}</details>
</section>"""


def page_html(result):
    if not result:
        body = ('<p class="placeholder">No scoring run has been saved yet. Run '
                '<code>scripts/decisions_depth_demo.py</code> to create one.</p>')
        tabs = summary = meta = ""
        reach = "the ranked ads"
    else:
        questions = result["questions"]
        # A scope smaller than the asked depth is ranked whole: draw to its last rank.
        depth = min(result["depth"], max((q["ranked"] for q in questions), default=result["depth"]))
        first = questions[0] if questions else {"ranked": 0, "scope_total": 0}
        reach = (f"every native ad with searchable text ({first['ranked']} of the {first['scope_total']:,} in this collection)"
                 if depth < result["depth"] else f"the first {depth} ranked native ads")
        tabs = "".join(f'<button type="button" role="tab" id="t{i}" aria-controls="q{i}" aria-selected="{str(i == 0).lower()}">'
                       f'{escape(q["short"])}</button>' for i, q in enumerate(questions))
        rows = []
        for q in questions:
            c = band_counts(q["ads"], depth)
            cells = "".join(f'<td class="num">{b["likely"]}</td>' for b in c)
            rows.append(f'<tr><td>{escape(q["short"])}</td>{cells}<td class="num">{q["scored"]} / {q["ranked"]}</td>'
                        f'<td class="num">{q["scope_total"]:,}</td><td class="num">${q["cost_usd"]:.3f}</td></tr>')
        heads = "".join(f'<th>Likely, ranks {lo}–{hi}</th>' for lo, hi in bands(depth))
        summary = (f'<div class="scroll"><table class="summary"><thead><tr><th>Question</th>{heads}<th>Scored / ranked</th>'
                   f'<th>Ads in scope</th><th>Cost</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
        checked = (result.get("live_top_checked_utc") or "")[:10] or None
        body = "".join(_question_section(i, q, depth, result["max_ad_chars"], result.get("pass_at", PASS_AT), checked)
                       for i, q in enumerate(questions))
        uncertain = (f', of which ${result["uncertain_usd"]:.4f} is held for calls whose usage was not reported'
                     if result.get("uncertain_usd") else "")
        meta = (f'Scored {result["run_date"]} with {escape(result["model"])} · {reach} per question · '
                f'${result["cost_usd"]:.3f} spent{uncertain}; cap ${result["cap_usd"]:.2f}.')
        if result.get("data_version_after", result.get("data_version")) != result.get("data_version"):
            meta += " The collection changed while this run was scoring; ranks may mix two versions."
    return PAGE.replace("{{REACH}}", escape(reach)).replace("{{TABS}}", tabs).replace("{{SUMMARY}}", summary).replace("{{BODY}}", body).replace("{{META}}", meta)


def register_depth_demo(server):
    if os.environ.get("OBS_DEPTH_DEMO_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
        return
    path = Path(os.environ.get("OBS_DEPTH_DEMO_RESULT") or DEFAULT_RESULT)

    @server.get("/depth-demo")
    def depth_demo_page():
        return page_html(load(path)), 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}

    @server.get("/api/depth-demo")
    def depth_demo_data():
        result = load(path)
        return (jsonify(result), 200) if result else (jsonify({"error": "No scoring run saved yet."}), 404)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>How Deep to Read</title>
<style>
:root {
  --bg: #f5f7f8; --panel: #ffffff; --ink: #18232b; --muted: #5b6a74; --line: #d9e1e6;
  --accent: #0f6e78; --likely: #1f5fa8; --unsure: #d9822b; --unlikely: #b7c0c7; --cut: #8a5a00;
  --display: "Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, sans-serif;
  --body: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root {
  --bg: #0f171c; --panel: #16222a; --ink: #e4ecf0; --muted: #9aabb5; --line: #2a3a44;
  --accent: #5cc3cc; --likely: #6aa8f0; --unsure: #f0a35a; --unlikely: #4a5963; --cut: #e0b44c; color-scheme: dark } }
* { box-sizing: border-box }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 var(--body) }
.wrap { max-width: 1120px; margin: 0 auto; padding-block: 28px 64px; padding-inline: max(16px, env(safe-area-inset-left, 0px)); display: grid; gap: 20px }
h1, h2, h3 { font-family: var(--display); margin: 0; text-wrap: balance }
h1 { font-size: clamp(1.7rem, 4vw, 2.4rem); line-height: 1.1 }
h2 { font-size: 1.3rem } h3 { font-size: 1.05rem; margin-top: 8px }
.lede { color: var(--muted); max-width: 75ch; margin: 8px 0 0 }
.panel, .question { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; display: grid; gap: 14px; min-width: 0 }
.question[hidden] { display: none }
.tabs { display: flex; flex-wrap: wrap; gap: 8px }
.tabs button { font: 600 .9rem var(--body); color: var(--accent); background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 6px 14px; cursor: pointer }
.tabs button[aria-selected="true"] { color: #fff; background: var(--accent); border-color: var(--accent) }
button:focus-visible, a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px }
.tile { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px }
.tile-n { font: 700 1.9rem var(--display); color: var(--likely) }
.tile-l { font-weight: 600 } .tile-s, .sub, .src, figcaption { color: var(--muted); font-size: .88rem }
figure { margin: 0; display: grid; gap: 6px }
svg { width: 100%; height: auto; display: block }
svg .axis { stroke: var(--muted) } svg .grid { stroke: var(--line) }
svg .cut { stroke: var(--cut); stroke-dasharray: 5 4; stroke-width: 1.5 }
svg .cutlabel { fill: var(--cut); font-size: 13px } svg .tick { fill: var(--muted); font-size: 12px }
svg .label { fill: var(--muted); font-size: 13px } svg .value { fill: var(--ink); font-size: 13px; font-weight: 600 }
svg .line { fill: none; stroke: var(--likely); stroke-width: 2.5 } svg .mark { fill: var(--likely) }
svg circle.coded { stroke: var(--ink); stroke-width: 1.6 }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: .88rem; color: var(--muted) }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: 0 }
.scroll { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-size: .92rem }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top }
th { color: var(--muted); font-weight: 600 } td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap }
a { color: var(--accent) } .placeholder { color: var(--muted); font-style: italic; margin: 0 }
details summary { cursor: pointer; color: var(--accent); font-weight: 600 }
.rules ol, .rules ul { margin: 6px 0; padding-left: 22px }
footer { color: var(--muted); font-size: .88rem; max-width: 85ch; display: grid; gap: 4px } footer p { margin: 0 }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>How deep should a list read?</h1>
    <p class="lede">A list question ranks the ads by search, reads them in that order and today stops by rank 120. Here a cheaper judge (OpenAI's Decisions API) scored {{REACH}} against each question's rules, so you can see where likely matches thin out, and how many sit past rank 120 in this ranking.</p>
  </header>
  <div class="panel"><h2>Across the five questions</h2>{{SUMMARY}}<p class="sub">{{META}}</p></div>
  <div class="tabs" role="tablist">{{TABS}}</div>
  {{BODY}}
  <footer>
    <p><b>What this is not.</b> “Likely” is the judge's own confidence, not accuracy. Apart from the 15 hand-coded articles, nobody has labelled these ads, so a likely ad past rank 120 is worth a look, not a confirmed miss. A listed ad in a real answer still needs a sentence quoted from it and checked word for word.</p>
    <p>No model is called when this page is opened: it shows one saved scoring run.</p>
  </footer>
</div>
<script>
document.querySelectorAll('[role="tab"]').forEach(tab => tab.addEventListener("click", () => {
  document.querySelectorAll('[role="tab"]').forEach(t => t.setAttribute("aria-selected", String(t === tab)));
  document.querySelectorAll(".question").forEach(s => { s.hidden = s.id !== tab.getAttribute("aria-controls"); });
}));
</script>
</body>
</html>
"""
