"""Fictional lists over both collections: ads and posts are screened separately and counted apart."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from test_list_screening import passage, screening_service

from observatory.list_screening import Batch, Decision, list_answer, list_charts
from observatory.models import Evidence, Filters
from observatory.service import _list_over_selection

QUESTION = "Which ads present tidal kites as a source of jobs?"


def post(record, text, account="Kite Guild"):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="social",
                    title="", publisher="", sponsor="", account=account, published_at=date(2023, 7, 1),
                    text=text, start=0, end=len(text))


AD_JOBS = passage("r1", 1, "Tidal kites will bring 400 jobs to the harbor.")
AD_OTHER = passage("r2", 1, "Tidal kites are quiet at night.")
POST_JOBS = post("s1", "Every tidal kite farm hires local crews: jobs for the harbor.")
POST_OTHER = post("s2", "Our kite festival starts on Friday.", account="Harbor Fest")


def row(item, decision, quote=""):
    return {"record_id": item.record_id, "dataset": item.dataset, "title": item.title,
            "publisher": item.publisher or item.account, "sponsor": item.sponsor, "published_at": item.published_at,
            "decision": decision, **({"evidence_id": item.evidence_id, "quote": quote} if quote else {})}


def test_the_opening_line_counts_what_was_read_and_found_in_each_collection():
    results = [row(AD_OTHER, "does_not_match"), row(POST_JOBS, "matches", "jobs for the harbor."),
               row(POST_OTHER, "does_not_match")]
    answer = list_answer(QUESTION, results, [AD_OTHER, POST_JOBS, POST_OTHER], scope_total=268,
                         scopes={"native": 263, "social": 5})
    # Plain wording (client meeting MT6-016): found, read and not read in each collection, and what to do.
    assert answer.answer.startswith(
        "Found 0 matching ads and 1 matching post. Read: the 1 native ad closest to the question, out of 263 "
        "(262 not read); the 2 company social posts closest to the question, out of 5 (3 not read). Those not "
        "read may hold more matches. Narrowing the selection (company, date or platform) lets a larger share "
        "be read.\n\n")
    assert "Post by Kite Guild, 2023-07-01: “jobs for the harbor.” [1]" in answer.answer
    assert answer.structured_result["by_dataset"] == {
        "native": {"scope_total": 263, "examined": 1, "matches": 0},
        "social": {"scope_total": 5, "examined": 2, "matches": 1}}
    chinese = list_answer("哪些广告把潮汐风筝说成能带来就业？", results, [AD_OTHER, POST_JOBS, POST_OTHER],
                          scope_total=268, scopes={"native": 263, "social": 5}).answer
    assert chinese.startswith("找到符合的原生广告 0 篇、公司社交帖子 1 条。看过的范围：263 篇原生广告中和问题最接近的 1 篇"
                              "（其余 262 篇没有看）；5 条公司社交帖子中和问题最接近的 2 条（其余 3 条没有看）。"
                              "没看的里面可能还有符合的；缩小范围（公司、日期或平台）可以看得更全。\n\n")


def test_the_opening_line_says_what_was_left_unread_when_one_collection_was_read_whole():
    # Ads read whole, posts not reached by the search at all: the unread posts still get the note.
    results = [row(AD_JOBS, "does_not_match"), row(AD_OTHER, "does_not_match")]
    scopes = {"native": 2, "social": 40}
    english = list_answer(QUESTION, results, [AD_JOBS, AD_OTHER], scope_total=42, scopes=scopes).answer
    assert english == (
        "Found 0 matching ads and 0 matching posts. Read: all 2 native ads; none of the 40 company social posts "
        "(the search found nothing related). Those not read may hold more matches. Narrowing the selection "
        "(company, date or platform) lets a larger share be read. If you expected matches, try asking the "
        "question another way.")
    chinese = list_answer("哪些广告把潮汐风筝说成能带来就业？", results, [AD_JOBS, AD_OTHER], scope_total=42,
                          scopes=scopes).answer
    assert chinese == ("找到符合的原生广告 0 篇、公司社交帖子 0 条。看过的范围：全部 2 篇原生广告；"
                       "公司社交帖子一条也没看（40 条里检索没找到相关的）。没看的里面可能还有符合的；"
                       "缩小范围（公司、日期或平台）可以看得更全。如果觉得应该有结果，可以换个问法再问。")
    # Posts read in part, ads whole: only the posts' unread count is named.
    results = [row(AD_OTHER, "does_not_match"), row(POST_JOBS, "matches", "jobs for the harbor.")]
    english = list_answer(QUESTION, results, [AD_OTHER, POST_JOBS], scope_total=11,
                          scopes={"native": 1, "social": 10}).answer
    assert english.startswith(
        "Found 0 matching ads and 1 matching post. Read: the 1 native ad; the 1 company social post closest to "
        "the question, out of 10 (9 not read). Those not read may hold more matches.")
    assert "try asking the question another way" not in english
    # Read whole by the triage: records without text are not "not read".
    whole = list_answer(QUESTION, results, [AD_OTHER, POST_JOBS], scope_total=13,
                        scopes={"native": 3, "social": 10},
                        triage={"by_dataset": {"native": {"whole_scope": True}, "social": {"whole_scope": True}}}).answer
    assert whole.startswith("Found 0 matching ads and 1 matching post. Read: the 1 native ad with text (2 have none); "
                            "the 1 company social post with text (9 have none).\n\n")


def test_shown_matches_keep_a_fair_share_of_posts_when_ads_are_many():
    ads = [passage(f"r{n}", 1, f"Kite jobs {n}.") for n in range(12)]
    posts = [post(f"s{n}", f"Kite crews {n}.") for n in range(3)]
    results = [*(row(a, "matches", a.text) for a in ads), *(row(p, "matches", p.text) for p in posts)]
    answer = list_answer(QUESTION, results, [*ads, *posts], scope_total=300, scopes={"native": 263, "social": 37})
    shown = answer.structured_result["display_citations"]
    assert len(shown) == 10
    shown_records = {answer.evidence[[e.evidence_id for e in answer.evidence].index(answer.citations[n - 1].evidence_id)].record_id
                     for n in shown}
    assert {"s0", "s1", "s2"} <= shown_records  # all three posts are shown beside seven ads
    assert "5 more matching items not shown here." in answer.answer


def test_charts_split_each_category_by_collection():
    matched = [{"dataset": "native", "sponsor": "Tidal Co", "publisher": "Harbor Daily", "published_at": date(2021, 1, 1)},
               {"dataset": "native", "sponsor": "Tidal Co", "publisher": "Harbor Daily", "published_at": date(2023, 1, 1)},
               {"dataset": "social", "sponsor": "Tidal Co", "publisher": "TidalCo", "published_at": date(2023, 5, 1)},
               {"dataset": "social", "sponsor": "", "publisher": "Kite Guild", "published_at": date(2023, 6, 1)}]
    by_year = {chart["id"]: chart for chart in list_charts(matched, both=True)}["by_year"]
    assert by_year["labels"] == ["2021", "2023"] and by_year["values"] == [1, 3]
    assert [(s["dataset"], s["values"]) for s in by_year["series"]] == [("native", [1, 1]), ("social", [0, 2])]
    by_company = {chart["id"]: chart for chart in list_charts(matched, both=True)}["by_sponsor"]
    assert "Kite Guild" in by_company["labels"]  # a post without a sponsor counts under its account
    assert all("series" not in chart for chart in list_charts(matched))


def test_a_list_over_both_collections_screens_ads_and_posts_separately():
    def jobs_decisions(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        decisions = [Decision(ref=ad["ref"], decision="matches", passage_id=f"{ad['ref']}.1",
                              quote=ad["passages"][0]["text"])
                     if "jobs" in ad["passages"][0]["text"] else
                     Decision(ref=ad["ref"], decision="does_not_match", passage_id=f"{ad['ref']}.1", quote="")
                     for ad in ads]
        return SimpleNamespace(status="completed", model="offline-fictional", output_parsed=Batch(decisions=decisions),
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                     input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                                     model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    service, parse, db = screening_service([])
    parse.side_effect = jobs_decisions
    db.search = Mock(side_effect=lambda query, scope, **_: [AD_OTHER] if scope.dataset == "native" else [POST_JOBS, POST_OTHER])
    db.public_rows = lambda scope: [{"record_id": "x", "title": "", "dataset": scope.dataset}] * (
        263 if scope.dataset == "native" else 5)
    service.rag.embed = Mock(return_value=[[0.0], [0.0]])
    result = service._answer_evidence(QUESTION, Filters(dataset="all"), "offline", audit=False)
    assert parse.call_count == 2  # one batch per collection
    assert result.answer.startswith("Found 0 matching ads and 1 matching post. Read: the 1 native ad closest to "
                                    "the question, out of 263 (262 not read); the 2 company social posts closest to the "
                                    "question, out of 5 (3 not read).")
    assert [c.evidence_id for c in result.citations] == [POST_JOBS.evidence_id]
    assert [g["label"] for g in result.structured_result["groups"]] == ["Native ads", "Company posts"]


def test_the_planner_narrowing_a_list_to_ads_keeps_posts_when_both_are_selected():
    listing = {"answer_shape": "every_matching_source"}
    both = Filters(dataset="all")
    assert _list_over_selection(QUESTION, Filters(dataset="native"), both, listing).dataset == "all"
    assert _list_over_selection(QUESTION, Filters(dataset="native", date_from=date(2022, 1, 1)), both,
                                listing).date_from == date(2022, 1, 1)
    # An outlet belongs to the ads; the user's ads-only selection stays ads only.
    assert _list_over_selection(QUESTION, Filters(dataset="native", publishers=["Harbor Daily"]), both,
                                listing).dataset == "native"
    assert _list_over_selection(QUESTION, Filters(dataset="native"), Filters(dataset="native"), listing).dataset == "native"
    assert _list_over_selection("What do kite ads say?", Filters(dataset="native"), both, {}).dataset == "native"


def test_the_page_draws_ads_and_posts_in_two_colours_on_one_axis():
    from observatory.app import LIST_SERIES_COLORS, _list_chart_cards

    chart = {"id": "by_year", "title": "Listed ads and posts by publication year", "labels": ["2021", "2023"],
             "values": [1, 3], "series": [{"dataset": "native", "name": "Native ads", "values": [1, 1]},
                                          {"dataset": "social", "name": "Company posts", "values": [0, 2]}]}
    cards = _list_chart_cards({"charts": [chart]})
    figure = cards[1].children[0].children[1].figure
    assert [trace.marker.color for trace in figure.data] == [LIST_SERIES_COLORS["native"], LIST_SERIES_COLORS["social"]]
    assert figure.layout.barmode == "stack"
    assert list(figure.data[0].x) == list(figure.data[1].x) == ["2021", "2023"]
