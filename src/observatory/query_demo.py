"""Saved list answers replayed on the Query page, so a reader can see each cited ad's relevance score.

The answers are the 2026-10-24 validation run of five labelling questions (not the
customer's held-out questions) over the 15 hand-coded articles: whole Service
results, with the Decisions judge's numbers per ad. Replaying one calls no model;
the list charts are left out, and a reader's checks are offered on the ad cards only.
The file is OBS_QUERY_DEMO_ANSWERS or the run's triage_answers.json under
.runtime; without it the Query page shows no demo row.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULT_ANSWERS = (Path(__file__).resolve().parents[2] / ".runtime" / "rag_validation_20261023"
                   / "triage_answers.json")
# The saved answers carry no date of their own; the default file's run is known (work.md, 2026-10-24).
DEFAULT_SAVED = "2026-10-24"


def answers_path():
    return Path(os.environ.get("OBS_QUERY_DEMO_ANSWERS") or DEFAULT_ANSWERS)


def _name(label):
    return label.rsplit(".", 1)[-1].replace("_", " ").capitalize()


def demo_answers(path=None):
    """[{"label", "name", "question", "saved", "result"}]; [] when there is no saved file. "saved"
    is the run date when known (the default file), else None; a file's own time is not used, as a
    copy changes it. A file that cannot be read or has the wrong shape raises ValueError."""
    path = Path(path or answers_path())
    saved = DEFAULT_SAVED if path.resolve() == DEFAULT_ANSWERS.resolve() else None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ValueError(f"saved answers unreadable: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or not data:
        raise ValueError("saved answers must be a non-empty object")
    out = []
    for label, result in data.items():
        trace = result.get("research_trace") if isinstance(result, dict) else None
        question = trace.get("original_question") if isinstance(trace, dict) else None
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"saved answer {label!r} has no question")
        out.append({"label": label, "name": _name(label), "question": question, "saved": saved, "result": result})
    return out


def replay(result):
    """A copy to render: marked as a replay (no reader checks) and without the list charts."""
    result = copy.deepcopy(result)
    result["replay"] = True
    if isinstance(result.get("structured_result"), dict):
        result["structured_result"].pop("charts", None)
    return result


def cached_vector(db, text, model="text-embedding-3-small"):
    """The text's vector from the embeddings cache, or None; never an API call."""
    from .rag import digest

    with db.connect(vector=True) as conn:
        row = conn.execute("SELECT embedding FROM embeddings WHERE text_hash=%s AND model=%s",
                           (digest(text), model)).fetchone()
    return row["embedding"].to_list() if row else None


def recompute_retrieval(result, db, today=None):
    """Give a replayed answer today's retrieval explanation: its saved searches run again on the
    current collection (free: the question's vector from the cache, else no meaning search).
    Records whose text has changed since the answer was saved are marked. Changes `result`."""
    from datetime import date

    from .models import Filters
    from .retrieval_explain import group_explain

    saved = {item.get("record_id"): item.get("version_id") for item in result.get("evidence") or []}
    groups = [group for group in (result.get("structured_result") or {}).get("groups") or []
              if isinstance(group, dict) and group.get("query")]
    fresh = []
    for group in groups:  # every search first, then all at once: no mix of saved and today's detail
        vector = cached_vector(db, group["query"])
        found = db.search(group["query"], Filters.model_validate(group.get("filters") or {}), vector=vector,
                          model="text-embedding-3-small", limit=120, chunks_per_record=2)
        explain = group_explain(found)
        if explain is not None:
            for rid, item in explain["records"].items():
                item["changed"] = rid in saved and saved[rid] != item.get("version_id")
            explain = {**explain, "recomputed": (today or date.today()).isoformat(), "vector": vector is not None}
        fresh.append(explain)
    for group, explain in zip(groups, fresh):
        group["retrieval_explain"] = explain
    return result


def scope_size(result):
    """How many records the saved question was limited to, when it was."""
    filters = (result.get("research_trace") or {}).get("base_filters") or {}
    ids = filters.get("record_ids")
    return len(ids) if isinstance(ids, list) and ids else None
