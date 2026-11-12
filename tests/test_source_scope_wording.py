"""Fictional wordings of "this source's posts from this date" (2026-11-12). A question that opens on one
dated source ("According to X's September 2024 post", "What do X's October 10, 2022 posts say") binds the
read to X and that day or month, singular or plural. Everything else keeps the earlier rules; when the
question states two periods, a range or joined dates, no period is added (the rule cannot tell which is the
publication date) and the model's own filters decide."""
from datetime import date, timedelta

import pytest

from observatory.question_policy import question_source_scope, restricts_to_named_source

CONTEXT = {"sponsors": ["Brightwater Ferries"], "accounts": ["Tallow Creek Power", "Osprey Lane Gas"]}
SEPTEMBER = {"date_from": "2024-09-01", "date_to": "2024-09-30"}


@pytest.mark.parametrize("question, dataset, expected", [
    # One post or several, straight or curly apostrophe.
    ("According to Tallow Creek Power's September 2024 post, what award did it win?", "social",
     {"accounts": ["Tallow Creek Power"], **SEPTEMBER}),
    ("What did Tallow Creek Power’s September 2024 posts say about the award?", "social",
     {"accounts": ["Tallow Creek Power"], **SEPTEMBER}),
    ("What did Osprey Lane Gas's September 2024 tweet say?", "social", {"accounts": ["Osprey Lane Gas"], **SEPTEMBER}),
    # A day: month-day-year and day-month-year.
    ("What do Osprey Lane Gas’s October 10, 2022 posts say about the parade?", "social",
     {"accounts": ["Osprey Lane Gas"], "date_from": "2022-10-10", "date_to": "2022-10-10"}),
    ("What did Osprey Lane Gas's 3 March 2021 post announce?", "social",
     {"accounts": ["Osprey Lane Gas"], "date_from": "2021-03-03", "date_to": "2021-03-03"}),
    # One native ad; "May" is the month here.
    ("What did Brightwater Ferries' May 2019 ad say about night crossings?", "native",
     {"sponsors": ["Brightwater Ferries"], "date_from": "2019-05-01", "date_to": "2019-05-31"}),
])
def test_the_named_source_and_the_date_naming_its_posts_are_the_scope(question, dataset, expected):
    assert question_source_scope(question, CONTEXT, dataset) == expected


@pytest.mark.parametrize("question, expected", [
    # The post is from April 2025 and talks about 2024: the source is kept, no period is guessed.
    ("According to Tallow Creek Power's April 2025 post, how much did it spend on training in 2024?",
     {"accounts": ["Tallow Creek Power"]}),
    # Two publication periods compared (Codex review 2026-11-12).
    ("How did Tallow Creek Power's April 2024 posts differ from those in May 2024?",
     {"accounts": ["Tallow Creek Power"]}),
    ("How did Tallow Creek Power's April 2024 posts differ from its posts in May 2024?",
     {"accounts": ["Tallow Creek Power"]}),
    # Joined dates and ranges.
    ("What did Tallow Creek Power's April 2025 and May 2025 posts say?", {}),
    ("What did the April and May 2025 posts say about ferries?", {}),
    ("What did Tallow Creek Power's posts from 2019 to 2021 say about turbines?", {"accounts": ["Tallow Creek Power"]}),
    ("What did the posts from April 2019 to June 2020 say about turbines?", {}),
])
def test_two_periods_a_range_or_joined_dates_add_no_period(question, expected):
    assert question_source_scope(question, CONTEXT, "social") == expected


def test_one_stated_period_and_a_target_year_keep_the_old_rules():
    assert question_source_scope("What did Tallow Creek Power post in March 2023 about turbines?", CONTEXT, "social") == {
        "accounts": ["Tallow Creek Power"], "date_from": "2023-03-01", "date_to": "2023-03-31"}
    assert question_source_scope("What do Tallow Creek Power's posts say about net zero in 2050?", CONTEXT, "social") == {
        "accounts": ["Tallow Creek Power"]}


def test_a_future_date_naming_the_post_is_not_used():
    later = date.today() + timedelta(days=400)
    question = f"What will Tallow Creek Power's {later:%B %Y} post say?"
    assert question_source_scope(question, CONTEXT, "social") == {"accounts": ["Tallow Creek Power"]}


@pytest.mark.parametrize("question, restricted", [
    ("According to Tallow Creek Power's September 2024 post, what award did it win?", True),
    ("What do Tallow Creek Power’s October 10, 2022 posts say?", True),
    ("What did Tallow Creek Power's the October 10, 2022 ad say?", True),
    # The name is what the posts talk about, a verb, or a hyphenated word: not a source role.
    ("Which posts mention Tallow Creek Power?", False),
    ("What do posts say about Tallow Creek Power's post-merger plans?", False),
    ("Which posts mention Tallow Creek Power's plans to post job openings?", False),
    ("Which posts mention Tallow Creek Power's comments on the advertisement?", False),
])
def test_a_source_role_with_one_post_or_a_day(question, restricted):
    assert restricts_to_named_source(question, "Tallow Creek Power") is restricted


@pytest.mark.parametrize("question", [
    # A dated ad the posts talk about (Codex review 2026-11-12, rounds 3 and 4).
    "Which posts mention the September 2024 advertisement?",
    "Which posts by other accounts criticized Tallow Creek Power's September 2024 ad?",
    "What did Tallow Creek Power say about the September 2024 advertisement?",
    "What did the posts about Tallow Creek Power's September 2024 ad say?",
    # Round 5: another name before the dated ad, and "ad" modifying "spending".
    "What did Tallow Creek Power think of Brightwater Ferries' September 2024 advertisement?",
    "What was Tallow Creek Power's April 2025 ad spending?",
])
def test_a_dated_source_the_posts_talk_about_adds_no_period(question):
    assert "date_from" not in question_source_scope(question, CONTEXT, "social")


def test_a_publication_period_and_a_dated_ad_the_posts_discuss():
    assert question_source_scope(
        "Which posts published by Tallow Creek Power in April 2025 discuss the September 2024 advertisement?",
        CONTEXT, "social") == {"accounts": ["Tallow Creek Power"], "date_from": "2025-04-01", "date_to": "2025-04-30"}


def test_two_named_sources_compared_are_both_kept():
    question = "Compare Tallow Creek Power's posts with Osprey Lane Gas's posts."
    assert restricts_to_named_source(question, "Tallow Creek Power") and restricts_to_named_source(question, "Osprey Lane Gas")
    assert question_source_scope(question, CONTEXT, "social") == {"accounts": ["Tallow Creek Power", "Osprey Lane Gas"]}


def test_a_verb_or_a_content_mention_adds_no_scope():
    assert question_source_scope("Which posts mention Tallow Creek Power's plans to post job openings?",
                                 CONTEXT, "social") == {}
    assert question_source_scope("Which posts mention Tallow Creek Power's comments on the advertisement?",
                                 CONTEXT, "social") == {}


@pytest.mark.parametrize("question", [
    # Several dated sources: this rule reads none of them rather than only the first (Codex round 6).
    "What did Tallow Creek Power's April 2025 post and Osprey Lane Gas's April 2025 post say about hiring?",
    "Summarize Tallow Creek Power's September 2024 post and its October 2024 post.",
    "According to Tallow Creek Power's April 2025 post, and Osprey Lane Gas's May 2025 post, what changed?",
])
def test_several_dated_sources_add_no_name_or_period_from_the_dated_form(question):
    scope = question_source_scope(question, CONTEXT, "social")
    assert "date_from" not in scope
    assert scope.get("accounts") in (None, ["Tallow Creek Power", "Osprey Lane Gas"])


def test_a_day_month_year_date_is_one_period_not_a_day_and_its_month():
    assert question_source_scope("What do Osprey Lane Gas's 3 March 2021 posts say?", CONTEXT, "social") == {
        "accounts": ["Osprey Lane Gas"], "date_from": "2021-03-03", "date_to": "2021-03-03"}


def test_two_periods_one_with_a_day_add_no_period():
    # Codex round 7: "3 March 2021 posts" is a second period (that day), not dropped.
    assert question_source_scope("Compare Tallow Creek Power's April 2024 posts with its 3 March 2021 posts.",
                                 CONTEXT, "social") == {"accounts": ["Tallow Creek Power"]}


def test_a_dated_source_compared_with_another_source_adds_no_name_or_period():
    question = ("How did Tallow Creek Power's April 2025 post describe recruitment compared with "
                "Osprey Lane Gas's latest post?")
    assert question_source_scope(question, CONTEXT, "social") == {}


def test_the_post_and_each_post_refer_back_to_the_dated_source():
    assert question_source_scope(
        "According to Tallow Creek Power's September 2024 post, what award did it win? Cite the post.",
        CONTEXT, "social") == {"accounts": ["Tallow Creek Power"], **SEPTEMBER}
    assert question_source_scope(
        "According to Tallow Creek Power's September 2024 post, what award did it win? Also list its latest post.",
        CONTEXT, "social") == {}


def test_a_number_before_a_month_elsewhere_is_a_count_not_a_day():
    # Codex round 8: as before this change, "3 March 2021 posts" outside a named source is the month.
    assert question_source_scope("Find exactly 3 March 2021 posts about turbines.", CONTEXT, "social") == {
        "date_from": "2021-03-01", "date_to": "2021-03-31"}


@pytest.mark.parametrize("question", [
    "Summarize Tallow Creek Power's April 2025 post, as well as the posts by other accounts.",
    # Codex round 9: "the posts that ..." may be other sources too.
    "Summarize Tallow Creek Power's April 2025 post, as well as the posts that other accounts published.",
    # Codex round 10: a citation request that names other sources.
    "Summarize Tallow Creek Power's April 2025 post. Cite all posts that discuss it and were published by other accounts.",
])
def test_other_posts_beside_the_dated_source_are_other_sources(question):
    assert "date_from" not in question_source_scope(question, CONTEXT, "social")
    assert restricts_to_named_source(question, "Tallow Creek Power") is False


def test_a_citation_request_refers_back_to_the_dated_source():
    assert question_source_scope(
        "What do Osprey Lane Gas's October 10, 2022 posts say about the parade? Cite each post that mentions it.",
        CONTEXT, "social") == {"accounts": ["Osprey Lane Gas"], "date_from": "2022-10-10", "date_to": "2022-10-10"}
