"""Data helpers for the "how deep should a list read" run (scripts/decisions_depth_demo.py).

A list question reads its ranked candidates in order and stops by 120 at most. A
saved run of scripts/decisions_depth_demo.py scored the first ranked native ads
of each label question with the Decisions judge (gpt-6-luna, about $0.00025 an
ad). The Evaluation page (depth_eval_ui) draws that saved result; nothing here
calls a model.

The groups are the judge's alone: "likely" when P(meets) >= PASS_AT, "unlikely"
when relevance_triage.excludable, else "unsure". That is model confidence, not
accuracy: a listed ad still needs screening's verified sentence. The result path
is OBS_DEPTH_DEMO_RESULT or .runtime/decisions_depth_demo/result.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def result_path():
    return Path(os.environ.get("OBS_DEPTH_DEMO_RESULT") or DEFAULT_RESULT)


def load(path=None):
    """The saved run, or None when there is none. Invalid JSON raises ValueError."""
    try:
        return json.loads(Path(path or result_path()).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
