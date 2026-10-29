"""Saved list answers replayed on the Query page, so a reader can see each cited ad's relevance score.

The answers are the 2026-10-24 validation run of five labelling questions (not the
customer's held-out questions) over the 15 hand-coded articles: whole Service
results, with the Decisions judge's numbers per ad. Replaying one calls no model
and writes nothing: the reader-check buttons and the list charts are left out.
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


def scope_size(result):
    """How many records the saved question was limited to, when it was."""
    filters = (result.get("research_trace") or {}).get("base_filters") or {}
    ids = filters.get("record_ids")
    return len(ids) if isinstance(ids, list) and ids else None
