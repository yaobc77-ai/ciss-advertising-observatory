"""Surface-cue safety checks; these are not semantic classification accuracy."""

import pytest

from observatory.question_policy import question_contract


@pytest.mark.parametrize("question,task", [
    ("Which ads mention tidal kites?", "content_mentions"),
    ("How many refinery posts discuss worker safety?", "content_mentions"),
    ("Which articles are about public health?", "content_mentions"),
    ("哪些广告提到碳捕集？", "content_mentions"),
    ("How many ExxonMobil ads present tidal kites as a quiet power source?", "content_framing"),
    ("Which posts make composting claims?", "content_framing"),
    ("How many ads acknowledge negative health consequences?", "content_framing"),
    ("Which ads highlight the benefits of clean water for a coastal town?", "content_framing"),
    ("How do Company A and Company B describe their efforts to reduce emissions?", "content_framing"),
    ("How many articles say consumers must recycle?", "content_framing"),
    ("Which ads state that independent monitoring is necessary?", "content_framing"),
    ("Which ads state ‘limitations apply’?", "content_framing"),
    ("Which articles stated their safety goals?", "content_framing"),
    ("哪些广告将个人行动作为解决方案？", "content_framing"),
    ("有多少文章强调食品安全？", "content_framing"),
    ("哪些广告指出公众交通的好处？", "content_framing"),
    ("两家公司如何描述其产品改进？", "content_framing"),
    ("有多少广告表示将提高生产安全？", "content_framing"),
    ("哪些广告表述了对消费者责任的观点？", "content_framing"),
    ("What disclosure language identifies this advertisement?", "disclosure"),
    ("多少篇广告披露赞助关系？", "disclosure"),
])
def test_explicit_content_predicates_never_become_metadata_conditions(question, task):
    contract = question_contract(question)
    assert contract["task"] == task
    assert contract["content_condition"] is True
    assert contract["coverage"] == "retrieved_examples_only"


@pytest.mark.parametrize("question", [
    "How many native ads are from the New York Times?",
    "How many ads are sponsored by Shell, from 2020 through 2022?",
    "Which publishers is ExxonMobil working with?",
    "What percentage of Shell's ads ran in The Washington Post?",
    "Which years have the highest count of ads?",
    "Compare the ad counts before 2020 and after 2021.",
    "How many ads have no publication date?",
    "How many ads with the historical label 'climate_science' are from NYT?",
    "How many ads have label ‘mention’ at NYT?",
    "How many ads labeled false_solutions are in the collection?",
    "How many published NC_12 assignments exist?",
    "How many ads have keyword 'mention' in the collection?",
    "How many ads were published by ‘Claim News’?!",
    "How many ads were published by ‘Say Something Media’?!",
    "How many ads with the historical label 'describe' are in the collection?",
    "How many native ads are in the United States collection?",
    "How many ads are from New York state?",
    "纽约时报有多少篇原生广告？",
    "埃克森美孚和哪些媒体合作？",
    "壳牌在2020年至2022年共有多少广告？",
    "多少广告有历史标签“提及气候”？",
])
def test_metadata_and_literal_label_requests_remain_tool_defined(question):
    contract = question_contract(question)
    assert contract["content_condition"] is False
    assert contract["task"] == "metadata_or_unspecified"
    assert contract["coverage"] == "tool_defined"


@pytest.mark.parametrize("question", [
    "How many ads with label climate_science also mention transport?",
    "How many ads have historical label climate_science and mention transport?",
    "How many ads with label 'viable_solutions' make policy recommendations?",
    "多少广告有历史标签‘climate_science’并提及运输？",
])
def test_literal_labels_do_not_hide_a_separate_content_predicate(question):
    assert question_contract(question)["content_condition"] is True


def test_list_and_quantity_limits_are_distinct_and_preserve_detection_limit():
    listed = question_contract("Which ads mention grid resilience?")
    counted = question_contract("How many ads mention grid resilience?")
    assert listed["requires_complete_list"] is True
    assert listed["requires_content_count"] is False
    assert counted["requires_complete_list"] is False
    assert counted["requires_content_count"] is True
    assert "not_general_semantic_classification" in counted["detection"]


@pytest.mark.parametrize("question, listed", [
    ("In the Pineglass ad about canals, which river does the ad describe? Cite the ad.", False),
    ("Which company does this advertisement name as its partner?", False),
    ("Which ads mention canal dredging?", True),
    ("Which Pineglass ads describe the river?", True),
    ("List the posts that mention harbor grants.", True),
])
def test_asking_about_a_thing_inside_one_source_is_not_a_list_request(question, listed):
    assert question_contract(question)["requires_complete_list"] is listed


@pytest.mark.parametrize("question", [
    "Which country has the largest reserves according to the Pineglass ad? Cite the ad.",
    "Find the native ad whose title mentions canals.",
])
def test_a_question_about_one_source_gets_no_list_contract(question):
    assert question_contract(question)["requires_complete_list"] is False


@pytest.mark.parametrize("question", [
    "Which of the Pineglass ads mention canal dredging?",
    "Which native Pineglass CNBC advertisements describe river transport?",
    "Show the posts that mention harbor grants.",
    "哪些广告提到运河？",
])
def test_selecting_sources_keeps_the_list_contract(question):
    assert question_contract(question)["requires_complete_list"] is True


@pytest.mark.parametrize("question", [
    "Which ads quote an outside expert such as an academic?",
    "Which Pineglass ads appeal to national pride?",
    "Which ads tell the personal story of a named engineer?",
    "Which ads published before 2018 cite projections from the Harbor Energy Agency?",
    "Which Pineglass ads express support for the canal treaty?",
    "哪些广告认为运河运输还不能取代铁路？",
    "Harbor Times 上的哪些原生广告把 Pineglass 塑造成技术创新者？",
    "哪些 Pineglass 广告描绘 2050 年的运河图景？",
    "哪些广告突出与大学的合作？",
])
def test_unlisted_predicate_in_a_source_selection_is_presumed_content(question):
    # B1K: predicates outside the verb lists silently took the few-examples path.
    contract = question_contract(question)
    assert contract["content_condition"] is True
    assert contract["requires_complete_list"] is True
    assert contract["selects_sources"] is True


@pytest.mark.parametrize("question", [
    "Which ads were published by pineglass in 2019?",
    "Which ads ran in The Harbor Times before 2018?",
    "Which Pineglass ads were published on Canal News?",
    "Which ads are from March 2020?",
    "Which native ads have no publication date?",
    "Which ads were sponsored by Kestrel Ridge Energy?",
    "Which Pineglass ads appeared in Canal News between 2015 and 2017?",
    "Which posts did the account Pineglass Energy publish in May 2023?",
    "Which ads have the title Rising Tides?",
    "哪些广告发表于2019年？",
    "哪些 Pineglass 广告是在 Canal News 上发布的？",
    "Pineglass 在 2019 年有哪些广告？",
    "哪些广告没有日期？",
])
def test_selection_by_stored_fields_stays_metadata(question):
    contract = question_contract(question)
    assert contract["task"] == "metadata_or_unspecified"
    assert contract["requires_complete_list"] is False
    # Still a selection: an answer built from a few retrieved passages is labelled.
    assert contract["selects_sources"] is True


@pytest.mark.parametrize("question, listed", [
    ("Find every Pineglass ad that touches on ferries.", True),
    ("Do any Larkfield ads present canals as cheaper than rail? List them.", True),
    ("列出所有涉及运河疏浚的广告。", True),
    ("Pineglass 的广告里，哪些讲了引航员的故事？", True),
    ("所有提到渡轮的广告都有哪些？", True),
    ("AGA 在 2031 年 2 月的帖子中，提到了哪些周日餐食？", False),
    ("关于运河运输，广告有哪些说法？", False),
])
def test_generic_selection_cues_are_a_floor_not_a_phrase_list(question, listed):
    # B1K-N: new wording slipped past the phrase list; the planner's declared shape is the main detector.
    assert question_contract(question)["requires_complete_list"] is listed
