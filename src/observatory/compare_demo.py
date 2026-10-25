"""/compare: one question answered twice, with and without retrieval (demo).

The plain side sends only the question to the same generation model: no
collection, no tools, no web. The RAG side is the ordinary `Service.answer`
path with its retrieval, screening and verbatim citation checks. Both sides
reserve and settle through the same budget ledger, so the visitor limits and
the monthly cap apply to the demo as to any other question. Off unless
OBS_COMPARE_DEMO_ENABLED=true.
"""

from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from flask import jsonify, request, session

from .budget import LimitReached, price
from .models import Filters

log = logging.getLogger(__name__)

PLAIN_SYSTEM = "You are a helpful research assistant. Answer the user's question as well as you can."
PLAIN_MAX_OUTPUT = 1500
DATASETS = {"native", "social", "all"}


def _usage_numbers(usage):
    details = getattr(usage, "input_tokens_details", None)
    return (usage.input_tokens, usage.output_tokens, getattr(details, "cached_tokens", 0) or 0,
            getattr(details, "cache_write_tokens", 0) or 0)


def plain_answer(rag, question, visitor):
    """The model's own answer from the question alone, reserved and settled like any call."""
    model = rag.settings.generation_model
    upper_input = len((PLAIN_SYSTEM + question).encode("utf-8")) + 256
    estimate = price(model, upper_input, PLAIN_MAX_OUTPUT) * Decimal("1.25")
    rid = rag.budget.reserve(estimate, visitor, "generation", model)
    try:
        response = rag.client.responses.create(
            model=model, input=[{"role": "system", "content": PLAIN_SYSTEM}, {"role": "user", "content": question}],
            reasoning={"effort": "low"}, max_output_tokens=PLAIN_MAX_OUTPUT, store=False)
        if response.usage is None:
            raise ValueError("Provider omitted usage")
        actual = price(model, *_usage_numbers(response.usage))
        rag.budget.settle(rid, actual, {**response.usage.model_dump(),
                                        "observatory_request": {"stage": "compare_demo_plain"}})
    except Exception as exc:
        rag.budget.uncertain(rid, type(exc).__name__)
        raise
    return {"answer": response.output_text or "", "status": response.status, "model": model,
            "cost_usd": float(actual)}


def rag_payload(answer):
    """What the page shows of a checked answer: text, citations with their sources."""
    by_id = {e.evidence_id: e for e in answer.evidence}
    citations = []
    for number, citation in enumerate(answer.citations, 1):
        source = by_id.get(citation.evidence_id)
        citations.append({
            "n": number, "quote": citation.quote,
            "title": getattr(source, "title", "") or "",
            "dataset": getattr(source, "dataset", "") or "",
            "publisher": getattr(source, "publisher", "") or getattr(source, "platform", "") or "",
            "sponsor": getattr(source, "sponsor", "") or getattr(source, "account", "") or "",
            "date": source.published_at.isoformat() if getattr(source, "published_at", None) else "",
            "url": getattr(source, "url", "") or "",
            "detail_url": f"/records/{source.record_id}" if source is not None else "",
        })
    return {"answer": answer.answer, "status": answer.status, "mode": answer.answer_mode,
            "failure_reason": answer.failure_reason, "cost_usd": answer.cost_usd, "citations": citations}


def _request_question():
    body = request.get_json(silent=True) or {}
    question = str(body.get("question") or "").strip()
    dataset = body.get("dataset") or "all"
    if not 1 <= len(question) <= 2000 or dataset not in DATASETS:
        return None, None
    return question, dataset


def _visitor():
    if "visitor_id" not in session:
        session["visitor_id"] = secrets.token_urlsafe(24)
    return session["visitor_id"]


def register_compare_demo(server, service, settings):
    if not getattr(settings, "compare_demo_enabled", False):
        return

    @server.get("/compare")
    def compare_page():
        _visitor()
        return PAGE, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}

    @server.post("/api/compare/plain")
    def compare_plain():
        question, _dataset = _request_question()
        if question is None:
            return jsonify({"error": "Enter a question of 1–2,000 characters."}), 400
        try:
            return jsonify(plain_answer(service.rag, question, _visitor()))
        except LimitReached as exc:
            return jsonify({"error": str(exc)}), 429
        except Exception as exc:
            log.warning("Plain comparison answer failed: %s", type(exc).__name__)
            return jsonify({"error": "The model could not answer just now. Please try again."}), 503

    @server.post("/api/compare/rag")
    def compare_rag():
        question, dataset = _request_question()
        if question is None:
            return jsonify({"error": "Enter a question of 1–2,000 characters."}), 400
        try:
            answer = service.answer(question, Filters(dataset=dataset), _visitor())
        except LimitReached as exc:
            return jsonify({"error": str(exc)}), 429
        except Exception as exc:
            log.warning("RAG comparison answer failed: %s", type(exc).__name__)
            return jsonify({"error": "The collection answer could not be produced just now. Please try again."}), 503
        return jsonify(rag_payload(answer))


EXAMPLES = [
    ("Made-up company", "What do Glenridding Power's native ads say about the International Energy Agency (IEA)? Cite the ads.", "native"),
    ("A fact in one post", "According to Sasol's April 2025 post, how much did it invest in education and skills development in 2024, and how many learners had it reached?", "social"),
    ("Posts in a month", "What do the PETRONAS posts from April 2018 say about the company's milestones or commitments, and what does each relevant post mention? Cite each post.", "social"),
    ("A count", "How many unique social posts did the account Tourmaline Oil Corp. publish in 2025?", "social"),
    ("A list", "List the CNBC native ads that highlight partnerships with universities or research institutes.", "native"),
    ("A whole-collection list", "I'm looking for ads that reference coal. Which ones are there?", "native"),
]

_EXAMPLE_BUTTONS = "".join(
    f'<button type="button" class="example" data-q="{q.replace(chr(34), "&quot;")}" data-d="{d}">{label}</button>'
    for label, q, d in EXAMPLES)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>With and Without RAG</title>
<style>
/* Layout: the question sits on top; the two answers sit side by side so they are compared across, sources fold out below. */
:root {
  --bg: #f5f7f8; --panel: #ffffff; --ink: #18232b; --muted: #5b6a74; --line: #d9e1e6;
  --accent: #0f6e78; --accent-soft: #e2f1f2; --quote: #eef3f5; --bad: #b3261e; --bad-bg: #fbe6e4;
  --display: "Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, sans-serif;
  --body: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root {
  --bg: #0f171c; --panel: #16222a; --ink: #e4ecf0; --muted: #9aabb5; --line: #2a3a44;
  --accent: #5cc3cc; --accent-soft: #163a3f; --quote: #1b2b34; --bad: #ff8a80; --bad-bg: #3a1c1a; color-scheme: dark } }
* { box-sizing: border-box }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 var(--body) }
.wrap { max-width: 1180px; margin: 0 auto; padding-block: 28px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 22px }
h1, h2, h3 { font-family: var(--display); text-wrap: balance; margin: 0 }
h1 { font-size: clamp(1.8rem, 4vw, 2.5rem); line-height: 1.1 }
.lede { color: var(--muted); max-width: 72ch; margin: 8px 0 0 }
form { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px; display: grid; gap: 12px }
label { font-weight: 600 }
textarea { width: 100%; min-height: 84px; resize: vertical; font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px }
textarea:focus-visible, select:focus-visible, button:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }
.row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between }
select { font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px }
.ask { font: 600 1rem var(--body); color: #fff; background: var(--accent); border: 0; border-radius: 8px; padding: 9px 20px; cursor: pointer }
.ask:disabled { opacity: .55; cursor: progress }
.examples { display: flex; flex-wrap: wrap; gap: 8px; align-items: center }
.examples span { color: var(--muted); font-size: .9rem }
.example { font: .88rem var(--body); color: var(--accent); background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; cursor: pointer }
.example:hover { border-color: var(--accent) }
.pair { display: grid; grid-template-columns: 1fr 1fr; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden }
.side { padding: 16px 20px 20px; min-width: 0; display: grid; gap: 10px; align-content: start }
.side.plain { border-right: 1px solid var(--line) }
.side.rag { background: linear-gradient(var(--accent-soft), transparent 160px) }
.side-head { display: grid; gap: 2px }
.side-head p { margin: 0; color: var(--muted); font-size: .88rem }
.answer { font-size: .96rem; overflow-wrap: anywhere }
.answer p { margin: 0 0 .6em }
.answer strong { background: var(--quote); padding: 0 2px; border-radius: 3px }
.ref { display: inline-block; min-width: 1.5em; text-align: center; font: 500 .72rem/1.4 var(--mono); color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 0 3px; margin: 0 1px; vertical-align: 1px }
.placeholder { color: var(--muted); font-style: italic; margin: 0 }
.error { color: var(--bad); background: var(--bad-bg); border-radius: 8px; padding: 8px 10px; margin: 0 }
.meta { color: var(--muted); font: .8rem var(--mono) }
.spin { display: inline-block; width: .9em; height: .9em; border: 2px solid var(--line); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; vertical-align: -2px; margin-right: 6px }
@keyframes spin { to { transform: rotate(360deg) } }
details { border-top: 1px dashed var(--line); padding-top: 8px }
summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: .92rem }
.cites { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 10px; max-height: 30rem; overflow: auto }
.cites li { display: grid; grid-template-columns: auto 1fr; gap: 8px; align-items: start }
.cites li > div { min-width: 0 }
blockquote { margin: 0; font-size: .9rem; background: var(--quote); border-radius: 6px; padding: 6px 9px; overflow-wrap: anywhere }
.src { font-size: .82rem; color: var(--muted); margin-top: 3px; overflow-wrap: anywhere }
.src a { color: var(--accent) }
footer { color: var(--muted); font-size: .88rem; max-width: 80ch; display: grid; gap: 4px }
footer p { margin: 0 }
@media (max-width: 760px) { .pair { grid-template-columns: 1fr } .side.plain { border-right: 0; border-bottom: 1px solid var(--line) } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>The same model, with and without RAG</h1>
    <p class="lede">Ask a question about the fossil-fuel native ads and company social posts in this collection. The left side sends only your question to the model. The right side runs the full system: it searches the collection, checks each candidate, writes the answer, and verifies every quote word for word against the source.</p>
  </header>
  <form id="ask-form">
    <label for="question">Your question</label>
    <textarea id="question" name="question" maxlength="2000" required>What do Glenridding Power's native ads say about the International Energy Agency (IEA)? Cite the ads.</textarea>
    <div class="examples"><span>Try:</span>""" + _EXAMPLE_BUTTONS + """</div>
    <div class="row">
      <div><label for="dataset">Search in</label>
        <select id="dataset" name="dataset">
          <option value="all">Native ads and social posts</option>
          <option value="native" selected>Native ads</option>
          <option value="social">Social posts</option>
        </select></div>
      <button class="ask" id="ask" type="submit">Ask both</button>
    </div>
  </form>
  <div class="pair" aria-live="polite">
    <section class="side plain">
      <div class="side-head"><h2>Without RAG</h2><p>The model alone, given only the question. No collection, no tools, no web.</p></div>
      <div id="plain"><p class="placeholder">The model's own answer will appear here.</p></div>
    </section>
    <section class="side rag">
      <div class="side-head"><h2>With RAG</h2><p>The same model, answering from the collection with checked citations.</p></div>
      <div id="rag"><p class="placeholder">The answer from the collection will appear here, with its sources.</p></div>
    </section>
  </div>
  <footer>
    <p>Both answers are live calls and count against the question limit and the monthly budget. Each source links to its record page, where you can read the full text, and to the original page.</p>
    <p>The "without RAG" answer may sound confident. Check its figures and sources yourself: it has no access to this collection.</p>
  </footer>
</div>
<script>
const $ = id => document.getElementById(id);
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function rich(text) {
  let t = esc(text).replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>").replace(/\\[(\\d+)\\]/g, '<span class="ref">$1</span>');
  return t.split(/\\n\\s*\\n/).filter(p => p.trim()).map(p => "<p>" + p.replace(/\\n/g, "<br>") + "</p>").join("");
}
function busy(text) { return '<p class="placeholder"><span class="spin" aria-hidden="true"></span>' + esc(text) + "</p>"; }
function sources(items) {
  if (!items.length) return "";
  const rows = items.map(c => {
    const src = [c.publisher, c.sponsor, c.date].filter(Boolean).map(esc).join(" · ");
    const record = c.detail_url ? `<a href="${esc(c.detail_url)}" target="_blank" rel="noopener">${esc(c.title || "Record")}</a>` : esc(c.title);
    const original = c.url ? ` · <a href="${esc(c.url)}" target="_blank" rel="noopener">original page</a>` : "";
    return `<li><span class="ref">${c.n}</span><div><blockquote>“${esc(c.quote)}”</blockquote><div class="src">${record}${src ? " — " + src : ""}${original}</div></div></li>`;
  }).join("");
  return `<details ${items.length <= 4 ? "open" : ""}><summary>Quoted sources (${items.length}, checked word for word)</summary><ol class="cites">${rows}</ol></details>`;
}
async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), credentials: "same-origin"});
  const data = await r.json().catch(() => ({error: "The server returned an unreadable reply."}));
  if (!r.ok) throw new Error(data.error || "Request failed.");
  return data;
}
document.querySelectorAll(".example").forEach(b => b.addEventListener("click", () => {
  $("question").value = b.dataset.q; $("dataset").value = b.dataset.d; $("question").focus();
}));
$("ask-form").addEventListener("submit", async e => {
  e.preventDefault();
  const body = {question: $("question").value.trim(), dataset: $("dataset").value};
  if (!body.question) return;
  $("ask").disabled = true;
  $("plain").innerHTML = busy("Asking the model…");
  $("rag").innerHTML = busy("Waiting for the first answer, then searching the collection…");
  try {
    const p = await post("/api/compare/plain", body);
    $("plain").innerHTML = `<div class="answer">${rich(p.answer)}</div><p class="meta">${esc(p.model)} · $${p.cost_usd.toFixed(4)}</p>`;
  } catch (err) { $("plain").innerHTML = `<p class="error">${esc(err.message)}</p>`; }
  $("rag").innerHTML = busy("Searching the collection and checking sources… lists can take a minute.");
  try {
    const r = await post("/api/compare/rag", body);
    $("rag").innerHTML = `<div class="answer">${rich(r.answer)}</div>${sources(r.citations)}<p class="meta">$${(r.cost_usd || 0).toFixed(4)}</p>`;
  } catch (err) { $("rag").innerHTML = `<p class="error">${esc(err.message)}</p>`; }
  $("ask").disabled = false;
});
</script>
</body>
</html>
"""
