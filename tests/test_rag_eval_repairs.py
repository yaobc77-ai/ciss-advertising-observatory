"""Generic repairs found by the 8 October RAG test: correctable rejections, collection-first
fallback, collection-scoped name checks, collection-only questions and source quotations."""

from types import SimpleNamespace

import pytest
from test_masked_repair import Catalog, ScriptedAgent, plan, stats

from observatory.language import check_claim_languages, language_hint
from observatory.models import Filters
from observatory.question_policy import (
    content_search_question,
    literal_scope_preserved,
    question_contract,
)
from observatory.research_agent import (
    CONTENT_ROUTES,
    _clarification_in_question_language,
    _step_definitions,
)
from observatory.service import _COLLECTION_ONLY, _collection_search_applies

QUESTION = "Count native records"
# Plans are offered only for questions with several read tasks.
COMPOUND = "Count native records and count social records"


def duplicate_plan():
    part = {"question_part": "Count native records", "dataset": "native"}
    return {"tasks": [{**part, "route": "statistics"}, {**part, "route": "metadata"}]}


def test_invalid_plan_is_returned_once_for_correction():
    catalog = Catalog({"record_statistics": lambda args: stats(args["filters"]["dataset"], 7)})
    agent = ScriptedAgent([("set_research_plan", duplicate_plan()), ("set_research_plan", plan()),
                           ("record_statistics", {"filters": {"dataset": "native"}}),
                           ("record_statistics", {"filters": {"dataset": "social"}})], catalog, repairs=1)
    run = agent.run(COMPOUND, Filters(dataset="all"), "synthetic")
    assert not run.failure_reason and run.tool_trace[1]["status"] == "ok"
    assert run.tool_trace[0]["status"] == "invalid_request" and run.tool_trace[0]["repair"] == "returned_to_model"
    feedback = agent.sent[1]["input"][-1]
    assert feedback["type"] == "function_call_output" and "Plan rejected" in feedback["output"]


def test_a_second_invalid_plan_still_ends_the_run():
    agent = ScriptedAgent([("set_research_plan", duplicate_plan()), ("set_research_plan", duplicate_plan())], repairs=1)
    run = agent.run(COMPOUND, Filters(dataset="all"), "synthetic")
    assert run.route == "clarify" and run.failure_reason == "research_plan_invalid"


def test_title_lookup_without_a_match_points_to_text_search_once():
    catalog = Catalog({"find_records": {"status": "not_found", "records": []},
                       "record_statistics": stats("native", 3)})
    agent = ScriptedAgent([("find_records", {"title": "Imaginary Harbour", "filters": {"dataset": "native"}}),
                           ("record_statistics", {"filters": {"dataset": "native"}})], catalog, repairs=1)
    run = agent.run(QUESTION, Filters(dataset="native"), "synthetic")
    assert run.tool_trace[0]["repair"] == "returned_to_model"
    assert "search_records" in agent.sent[1]["input"][-1]["output"]


def test_account_names_cannot_make_a_native_question_ambiguous():
    context = {"sponsors": [{"value": "bp"}], "accounts": [{"value": "BP"}]}
    for dataset, expected in (("native", True), ("all", False)):
        diagnostics = {}
        kept = literal_scope_preserved("How many BP advertisements are there?", context,
                                       {"dataset": dataset, "sponsors": ["bp"]}, {"dataset": "all"},
                                       diagnostics=diagnostics)
        assert kept is expected, (dataset, diagnostics)


def run_ending(reason, tools=(), metadata_only=False):
    return SimpleNamespace(failure_reason=reason, tool_trace=list(tools),
                           question_contract={"original_metadata_only": metadata_only})


def test_repairs_are_off_unless_the_service_enables_them():
    agent = ScriptedAgent([("set_research_plan", duplicate_plan())])
    run = agent.run(COMPOUND, Filters(dataset="all"), "synthetic")
    assert run.failure_reason == "research_plan_invalid" and "repair" not in run.tool_trace[0]


def test_collection_search_follows_plan_and_title_failures_only():
    assert _collection_search_applies(run_ending("research_plan_invalid"))
    assert _collection_search_applies(run_ending("original_source_record_unresolved"))
    assert not _collection_search_applies(run_ending("statistics_question_scope_missing"))
    assert not _collection_search_applies(run_ending("research_plan_invalid", metadata_only=True))
    assert not _collection_search_applies(run_ending("research_plan_invalid", [{"tool": "record_statistics"}]))
    count_plan = {"tool": "set_research_plan", "arguments": {"tasks": [{"route": "statistics"}, {"route": "statistics"}]}}
    assert not _collection_search_applies(run_ending("research_plan_invalid", [count_plan]))


def test_collection_only_wording_is_recognised():
    assert _COLLECTION_ONLY.search("Only use social posts published between 2040-01-01 and 2040-12-31")
    assert _COLLECTION_ONLY.search("仅使用当前筛选中发表的原生广告")
    assert not _COLLECTION_ONLY.search("What do ExxonMobil ads say about biofuels?")


def test_verbatim_source_quotations_do_not_count_as_wrong_language():
    target = language_hint("这则原生广告怎样描述贝类监测水质？请引用原文。")
    source = ("They are extremely sensitive to the quality of their environment. When they detect any "
              "chemical stress or change in water turbidity1, their behavior changes.")
    claim = ("广告称贝类对环境质量极其敏感，检测到压力或浑浊度变化时行为会改变。原文：“They are extremely sensitive "
             "to the quality of their environment. When they detect any chemical stress or change in water "
             "turbidity, their behavior changes.”")
    assert check_claim_languages([claim], target, source_texts=[source])["status"] != "mismatch"
    invented = "广告称：“This sentence was invented and does not appear in the selected source text.”"
    assert check_claim_languages([invented], target, source_texts=[source])["status"] == "mismatch"


@pytest.mark.parametrize("question,expected", [
    ("What did RWE UK say about the purpose of its Didcot B maintenance work? Cite the post.", True),
    ("Which project was under construction at the Altamira yard visited by BPTT? Cite the social post.", True),
    ("SPIC 的社交帖子说，截至 2025 年 5 月底清洁能源装机容量有多少？请引用帖子。", True),
    ("PETRONAS 的印度品牌电影叫什么？请给出来源。", True),
    ("How many ads from NYT in 2020?", False),
    ("资料中2018年有多少个唯一公司社交帖子？", False),
    ("What are the publisher, sponsor, and publication date recorded for the advertisement titled \"BP Supercomputer\"?", False),
    ("广告“Recycling waste”用什么文字披露其广告身份？按原Excel逐字给出。", False),
    ("Which ads mention tidal kites?", False),
    ("Which publishers is ExxonMobil working with?", False),
    ("Compare records published by Cedar Ledger in 1996 versus 1997.", False),
    ("Describe the Pineglass opening arrangements and read its stored source metadata.", False),
])
def test_content_questions_are_told_apart_from_counts_fields_and_lists(question, expected):
    assert content_search_question(question) is expected


def test_citation_requests_do_not_make_a_question_compound():
    contract = question_contract("What digital system did ONGC announce in December 2024? Cite the post.")
    assert contract["content_search"] and not contract["compound_read_request"]


@pytest.mark.parametrize("question", [
    "What exploration work does BP assign to its Houston supercomputer, and what improvement in testing time does the advertisement claim? Cite the ad.",
    "According to Total's native ad about LNG shipping, what sulfur limit took effect in 2020, and what three options did it describe for shipowners?",
    "What digital system did ONGC announce it had pre-launched in December 2024, and which operational services was it meant to support? Cite the post.",
])
def test_several_questions_about_one_source_are_one_search_not_a_plan(question):
    contract = question_contract(question)
    assert contract["content_search"] and not contract["compound_read_request"]
    offered = {item["name"] for item in _step_definitions(ALL_TOOLS, contract, [], [])}
    assert "search_records" in offered and "set_research_plan" not in offered


def test_counting_two_things_still_needs_a_plan():
    contract = question_contract("For BP, how many native advertisements and how many social posts are in the current collections?")
    assert contract["compound_read_request"] and not contract["content_search"]


def definitions_named(*names):
    return [{"name": name, "parameters": {"properties": {}, "required": []}} for name in names]


ALL_TOOLS = definitions_named("set_research_plan", "search_records", "find_records", "get_record",
                              "get_record_metadata", "record_statistics", "resolve_entity", "request_clarification")


def test_content_questions_only_get_search_tools():
    contract = question_contract("What did RWE UK say about Didcot B? Cite the post.")
    offered = {item["name"] for item in _step_definitions(ALL_TOOLS, contract, [], [])}
    assert offered == {"search_records", "resolve_entity", "request_clarification"}
    titled = question_contract('What does the ad "Blue Hydrogen Now" say about costs?')
    offered = {item["name"] for item in _step_definitions(ALL_TOOLS, titled, [], [])}
    assert {"search_records", "find_records", "get_record"} <= offered and "set_research_plan" not in offered


def test_a_content_plan_part_may_search_the_text():
    from observatory.research_agent import _ResearchTask
    task = _ResearchTask(question_part="What did the post announce", dataset="social", route="record")
    contract = question_contract(task.question_part)
    offered = {item["name"] for item in _step_definitions(ALL_TOOLS, contract, [task], [])}
    assert "search_records" in offered and "record" in CONTENT_ROUTES


def test_a_name_stated_once_covers_every_plan_part():
    context = {"sponsors": [{"value": "bp"}, {"value": "BP"}]}
    part = "and how many social posts are in the current collections?"
    assert not literal_scope_preserved(part, context, {"dataset": "social", "sponsors": ["BP"]}, {"dataset": "all"})
    assert literal_scope_preserved(part, context, {"dataset": "social", "sponsors": ["BP"]}, {"dataset": "all"},
                                   shared_question="For BP, how many native advertisements " + part)
    # A name absent from the whole question is still a dropped or added condition.
    assert not literal_scope_preserved(part, context, {"dataset": "social", "sponsors": ["BP"]}, {"dataset": "all"},
                                       shared_question="For Shell, how many native advertisements " + part)


def test_a_company_name_in_social_is_the_company_unless_account_is_said():
    context = {"sponsors": [{"value": "BP"}], "accounts": [{"value": "BP"}]}
    assert literal_scope_preserved("How many BP posts are there?", context,
                                   {"dataset": "social", "sponsors": ["BP"]}, {"dataset": "social"})
    assert literal_scope_preserved("How many posts did the account BP publish?", context,
                                   {"dataset": "social", "accounts": ["BP"]}, {"dataset": "social"})


def test_clarifications_in_another_language_are_replaced_by_a_fixed_one():
    from types import SimpleNamespace as NS
    english = "Where and on which dates did GPCA announce its 14th Plastics Conference would take place?"
    arabic = NS(message="لم أعثر على عنوان مخزّن مطابق؛ هل تريدني أن أبحث في نص المنشورات الاجتماعية عن المؤتمر الرابع عشر للبلاستيك؟",
                reason="missing_context")
    assert _clarification_in_question_language(arabic, english).startswith("The question needs one more detail")
    chinese_question = "SPIC 的社交帖子说清洁能源装机容量有多少？请引用帖子。"
    assert _clarification_in_question_language(arabic, chinese_question).startswith("需要补充")
    same = NS(message="Which BP advertisement do you mean? Please give its title or outlet.", reason="ambiguous_entity")
    assert _clarification_in_question_language(same, english) == same.message


def test_long_passages_are_trimmed_to_the_writer_budget_in_rank_order():
    from observatory.models import Evidence
    from observatory.service import _fit_evidence_budget

    def passage(i, size):
        return Evidence(evidence_id=f"e{i}", record_id=f"r{i}", version_id="v", dataset="native",
                        title="t", text="x" * size, start=0, end=size)
    evidence = [passage(i, 3000) for i in range(15)]
    kept, dropped = _fit_evidence_budget(evidence, budget=30_000)
    assert [e.evidence_id for e in kept] == [f"e{i}" for i in range(10)] and dropped == 5
    # One oversized passage is still sent rather than answering nothing.
    kept, dropped = _fit_evidence_budget([passage(0, 50_000), passage(1, 10)], budget=30_000)
    assert [e.evidence_id for e in kept] == ["e0"] and dropped == 1
