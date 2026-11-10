"""Per-question-type answer norms with worked examples, kept outside the public repository.

The norms file is private (the repository is public and its examples come from
client questions). It is read from OBS_ANSWER_NORMS_PATH, from
OBS_ANSWER_NORMS_B64 (gzip + base64, for hosts without a private file), or from
config/private/answer_norms.json. Without one, every prompt stays unchanged.
NATIVEADS_* names work too (config.apply_public_env_names).

Prompts follow the r1_zero baseline: the model writes its reasoning inside
<think></think> and then the answer inside <answer></answer>. A type with
worked examples uses r1_zero_three_shot, which puts three complete examples
before the question. A list question outside the known types uses r1_zero
with the general list norm; a question that is not a list gets the general
"overview first, then enumerate" norm.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "private" / "answer_norms.json"
LIST_TYPES = ("disclosure", "sponsor_claim", "framing", "mention")
GENERAL_LIST = "general_list"
GENERAL = "general"

_LIST = re.compile(r"^\s*(which|what|list|find|show)\b.*\b(ads?|advertisements?|advertorials?|posts?|articles?)\b", re.I)
_RULES = (
    ("disclosure", re.compile(r"\bdisclos|\b(label|labell?ed|marked|identif\w*) (as |the item as )?(paid|sponsored|advertis)", re.I)),
    ("sponsor_claim", re.compile(r"\b(their|its|the|a) sponsor(?:'s|’s)?\b|\bsponsor(?:'s|’s)\b", re.I)),
    ("framing", re.compile(r"\b(position|present|offer|frame|portray|acknowledg|assert|suggest|claim|recommend|"
                           r"point(?:s)? out|attempt|argue|highlight|depict|describe\w* .* as|promot|blame|redirect)", re.I)),
    ("mention", re.compile(r"\b(mention|refer|talk|discuss|cite|name|include)", re.I)),
)


def question_type(question: str) -> str:
    """One of LIST_TYPES, GENERAL_LIST (a list question of another kind) or GENERAL."""
    # Only the question itself decides; a definition after it (Q15 style) can use any verb.
    text = (question or "").split("?", 1)[0]
    if _RULES[0][1].search(text):
        return "disclosure"
    if not _LIST.search(text):
        return GENERAL
    for name, pattern in _RULES[1:]:
        if pattern.search(text):
            return name
    return GENERAL_LIST


def _read(environ):
    if environ.get("OBS_ANSWER_NORMS", "").lower() in ("off", "false", "0"):
        return None
    if environ.get("OBS_ANSWER_NORMS_B64"):
        return gzip.decompress(base64.b64decode(environ["OBS_ANSWER_NORMS_B64"])).decode("utf-8")
    path = Path(environ["OBS_ANSWER_NORMS_PATH"]) if environ.get("OBS_ANSWER_NORMS_PATH") else DEFAULT_PATH
    return path.read_text(encoding="utf-8") if path.is_file() else None


def parse_norms(text: str) -> dict:
    data = json.loads(text)
    templates = data.get("templates") or {}
    if not {"r1_zero", "r1_zero_three_shot"} <= templates.keys():
        raise ValueError("Norms need r1_zero and r1_zero_three_shot templates")
    for name, spec in (data.get("types") or {}).items():
        if not spec.get("norm"):
            raise ValueError(f"Type {name} has no norm")
        if len(spec.get("examples") or []) not in (0, 3):
            raise ValueError(f"Type {name} needs exactly three worked examples or none")
    data["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return data


@lru_cache(maxsize=1)
def _cached(text):
    return parse_norms(text)


def load_norms(environ=None):
    """The parsed norms, or None when no norms file is configured or it is invalid."""
    try:
        text = _read(os.environ if environ is None else environ)
        return _cached(text) if text else None
    except Exception as exc:  # noqa: BLE001 - a broken private file must not stop answers.
        log.warning("Answer norms not loaded: %s", type(exc).__name__)
        return None


def norms_tag(norms):
    return f"{norms.get('version', 'answer-norms')}:{norms['sha256'][:12]}" if norms else None


def _example_text(example):
    user = json.dumps({"question": example["question"], "ads": example["ads"]}, ensure_ascii=False)
    answer = json.dumps(example["answer"], ensure_ascii=False)
    return f"User: {user}\nAssistant: <think> {example['think']} </think> <answer> {answer} </answer>"


def screening_prompt(norms, question, payload):
    """(type, template name, user prompt) for one screening batch."""
    kind = question_type(question)
    types = norms.get("types") or {}
    spec = types.get(kind) or types.get(GENERAL_LIST)
    if spec is None:
        return kind, None, None
    examples = spec.get("examples") or []
    name = "r1_zero_three_shot" if len(examples) == 3 else "r1_zero"
    prompt = norms["templates"][name].format(
        norm=spec["norm"], examples="\n\n".join(_example_text(e) for e in examples), question=payload)
    return kind, name, prompt


_ANSWER = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.S)
_THINK = re.compile(r"<think>\s*(.*?)\s*</think>", re.S)


def split_tagged(text):
    """(reasoning, answer JSON text) from '<think>..</think> <answer>..</answer>'; answer None if absent."""
    text = text or ""
    answer = _ANSWER.findall(text)
    think = _THINK.findall(text)
    if think:
        reasoning = think[-1]
    elif "</think>" in text:
        # The prompt already ends with "Assistant: <think>", so the model usually
        # continues straight into its reasoning without repeating the opening tag.
        reasoning = text.split("</think>", 1)[0].strip()
    else:
        # Some replies skip the closing tag too; whatever precedes <answer> is the reasoning.
        reasoning = text.split("<answer>", 1)[0].replace("<think>", "").strip() if "<answer>" in text else ""
    return reasoning, (answer[-1] if answer else None)


def general_norm(norms, question):
    """Extra writer instructions for a question outside the list types, or ''."""
    if not norms or question_type(question) != GENERAL:
        return ""
    spec = (norms.get("types") or {}).get(GENERAL)
    return ("\n" + spec["norm"]) if spec else ""
