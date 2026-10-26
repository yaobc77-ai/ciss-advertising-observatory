"""Answer norms: typing, private loading, r1_zero prompts and the tagged screening call (fictional data)."""
import base64
import gzip
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from observatory import answer_norms
from observatory.answer_norms import (
    general_norm,
    load_norms,
    parse_norms,
    question_type,
    screening_prompt,
    split_tagged,
)
from observatory.config import Settings
from observatory.list_screening import Batch, Decision, screen
from observatory.models import Evidence

HEAD = "Rules:\n{norm}\n"


def example(n):
    return {"question": f"Which ads mention tidal kites {n}?", "ads": [{"ref": "A1", "passages": []}],
            "think": f"Reason {n}.", "answer": {"decisions": [{"ref": "A1", "decision": "does_not_match",
                                                               "passage_id": "A1.1", "quote": ""}]}}


NORMS = {
    "version": "answer-norms-test",
    "templates": {"r1_zero": HEAD + "User: {question}\nAssistant: <think>",
                  "r1_zero_three_shot": HEAD + "{examples}\nUser: {question}\nAssistant: <think>"},
    "types": {
        "mention": {"norm": "Mention rule.", "examples": [example(1), example(2), example(3)]},
        "general_list": {"norm": "Generic list rule.", "examples": []},
        "general": {"norm": "Overview first, then list.", "examples": []},
    },
}
TEXT = json.dumps(NORMS)


@pytest.mark.parametrize("question, kind", [
    ("What disclosure language marks the paid post?", "disclosure"),
    ("Which ads mention tidal kites?", "mention"),
    ("Which ads position kites as essential to quiet harbors?", "framing"),
    ("Which ads position their sponsor as lowering noise?", "sponsor_claim"),
    ("Which ads mention a sponsor’s kite school?", "sponsor_claim"),
    ("Which ads mention kite science? A coder assessed whether it presented doubt.", "mention"),
    ("Which ads feature a podcast?", "general_list"),
    ("How do harbor companies talk about kites?", "general"),
])
def test_question_type(question, kind):
    assert question_type(question) == kind


def test_three_examples_use_three_shot_and_others_fall_back_to_zero_shot():
    norms = parse_norms(TEXT)
    kind, name, prompt = screening_prompt(norms, "Which ads mention tidal kites?", '{"ads": []}')
    assert (kind, name) == ("mention", "r1_zero_three_shot")
    assert prompt.count("<think> Reason") == 3 and prompt.endswith('User: {"ads": []}\nAssistant: <think>')
    assert "Mention rule." in prompt
    kind, name, prompt = screening_prompt(norms, "Which ads position kites as quiet?", "{}")
    assert (kind, name) == ("framing", "r1_zero") and "Generic list rule." in prompt


def test_norms_need_both_templates_and_zero_or_three_examples():
    with pytest.raises(ValueError):
        parse_norms(json.dumps({**NORMS, "templates": {"r1_zero": "x"}}))
    broken = json.loads(TEXT)
    broken["types"]["mention"]["examples"] = [example(1)]
    with pytest.raises(ValueError):
        parse_norms(json.dumps(broken))


def test_loading_from_path_inline_or_off(tmp_path):
    path = tmp_path / "norms.json"
    path.write_text(TEXT, encoding="utf-8")
    assert load_norms({"OBS_ANSWER_NORMS_PATH": str(path)})["version"] == "answer-norms-test"
    packed = base64.b64encode(gzip.compress(TEXT.encode())).decode()
    assert load_norms({"OBS_ANSWER_NORMS_B64": packed})["sha256"]
    assert load_norms({"OBS_ANSWER_NORMS": "off", "OBS_ANSWER_NORMS_PATH": str(path)}) is None
    assert load_norms({"OBS_ANSWER_NORMS_PATH": str(tmp_path / "missing.json")}) is None
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    assert load_norms({"OBS_ANSWER_NORMS_PATH": str(tmp_path / "bad.json")}) is None


def test_split_tagged_and_general_norm():
    assert split_tagged("<think> a </think> <answer> {\"x\": 1} </answer>") == ("a", '{"x": 1}')
    assert split_tagged("no tags")[1] is None
    # The prompt ends with "<think>", so the reply may start inside the reasoning.
    assert split_tagged(" A1 is about kites. </think> <answer> {} </answer>") == ("A1 is about kites.", "{}")
    assert split_tagged("A1 is about kites. <answer> {} </answer>") == ("A1 is about kites.", "{}")
    assert split_tagged("<answer> {} </answer>") == ("", "{}")
    norms = parse_norms(TEXT)
    assert "Overview first" in general_norm(norms, "How do harbor companies talk about kites?")
    assert general_norm(norms, "Which ads mention kites?") == "" and general_norm(None, "How?") == ""


def passage(record, text):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="native",
                    title=f"Kite notice {record}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=0, end=len(text))


ADS = [passage("r1", "Tidal kites will supply cheap power to the harbor."), passage("r2", "Food stalls and music.")]
USAGE = SimpleNamespace(input_tokens=10, output_tokens=5, model_dump=lambda: {},
                        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0))
GOOD = Batch(decisions=[Decision(ref="A1", decision="matches", passage_id="A1.1",
                                 quote="Tidal kites will supply cheap power to the harbor."),
                        Decision(ref="A2", decision="does_not_match", passage_id="A2.1", quote="")])


def rag_with(create_text):
    created, parsed = [], []

    def create(**request):
        created.append(request)
        return SimpleNamespace(status="completed", output_text=create_text, usage=USAGE)

    def parse(**request):
        parsed.append(request)
        return SimpleNamespace(status="completed", output_parsed=GOOD, usage=USAGE)

    rag = SimpleNamespace(settings=Settings(), client=SimpleNamespace(responses=SimpleNamespace(create=create, parse=parse)),
                          budget=SimpleNamespace(reserve=Mock(return_value="r"), settle=Mock(), uncertain=Mock()))
    return rag, created, parsed


@pytest.fixture
def private_norms(monkeypatch):
    monkeypatch.setattr(answer_norms, "load_norms", lambda environ=None: parse_norms(TEXT))
    monkeypatch.setattr("observatory.list_screening.load_norms", lambda: parse_norms(TEXT))


def test_tagged_screening_lists_verified_quotes_and_keeps_the_reasoning(private_norms):
    text = f"<think> A1 says kites supply power. A2 is about food. </think> <answer> {GOOD.model_dump_json()} </answer>"
    rag, created, parsed = rag_with(text)
    results, _ = screen(rag, "Which ads mention tidal kites?", ADS, "offline")
    assert [item["decision"] for item in results] == ["matches", "does_not_match"]
    assert results[0]["screening_reasoning"].startswith("A1 says kites")
    assert len(created) == 1 and not parsed
    assert created[0]["input"][-1]["content"].count("<think> Reason") == 3
    settled = rag.budget.settle.call_args.args[2]["observatory_request"]
    assert settled["type"] == "mention" and settled["template"] == "r1_zero_three_shot"
    # The relevance reasoning and quote are kept in the answer's trace for later reading.
    from observatory.list_screening import list_answer
    trace = list_answer("Which ads mention tidal kites?", results, ADS, scope_total=2).research_trace["list_screening"]
    assert trace["decisions"][0]["screening_reasoning"].startswith("A1 says kites")
    assert trace["decisions"][0]["quote"] == "Tidal kites will supply cheap power to the harbor"  # edge punctuation trimmed


def test_a_malformed_answer_tag_falls_back_to_the_structured_call(private_norms):
    rag, created, parsed = rag_with("<think> unsure </think> the answer was forgotten")
    results, _ = screen(rag, "Which ads mention tidal kites?", ADS, "offline")
    assert len(created) == 1 and len(parsed) == 1
    assert [item["decision"] for item in results] == ["matches", "does_not_match"]
    assert rag.budget.settle.call_count == 2  # both calls are paid and recorded
    assert results[0]["screening_fallback"] is True
    assert results[0]["screening_reasoning"] == "(first call; its answer could not be read) unsure"


def test_a_fenced_json_answer_is_read_without_fallback(private_norms):
    text = f"A1 supplies power. </think> <answer>```json\n{GOOD.model_dump_json()}\n```</answer>"
    rag, created, parsed = rag_with(text)
    results, _ = screen(rag, "Which ads mention tidal kites?", ADS, "offline")
    assert len(created) == 1 and not parsed
    assert results[0]["screening_reasoning"] == "A1 supplies power." and "screening_fallback" not in results[0]


def test_without_norms_the_structured_call_is_unchanged():
    rag, created, parsed = rag_with("")
    screen(rag, "Which ads mention tidal kites?", ADS, "offline")
    assert not created and len(parsed) == 1
