"""C22 (client meeting MT6-009): posts with exactly the same text, in lists and in an answer's search.

A list judges every post and counts every post; it writes posts with the same text on one line,
by the earliest published, with how many more there are and their accounts (user 2026-11-08).
Ads, posts with their own text and blank texts are never grouped. Fictional posts only.
"""
from datetime import date
from types import SimpleNamespace

from observatory.db import _same_text_key
from observatory.list_screening import DISPLAY_LIMIT, list_answer
from observatory.models import Evidence

QUESTION = "Which posts present tidal kites as a source of jobs?"
SHARED = "Tidal kites bring jobs to the harbor."


def post(record, text, account, published_at, body_hash, dataset="social"):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset=dataset,
                    title="" if dataset == "social" else f"Kite notice {record}", publisher="" if dataset == "social"
                    else "Harbor Daily", sponsor="", account=account, published_at=published_at, text=text, start=0,
                    end=len(text), body_hash=body_hash)


def row(item):
    return {"record_id": item.record_id, "dataset": item.dataset, "title": item.title,
            "publisher": item.publisher or item.account,
            "sponsor": item.sponsor, "published_at": item.published_at, "decision": "matches",
            "evidence_id": item.evidence_id, "quote": item.text}


def answer(items, question=QUESTION):
    return list_answer(question, [row(item) for item in items], items, scope_total=40)


def test_posts_with_the_same_text_share_one_line_written_by_the_earliest():
    items = [post("s1", SHARED, "Kite Guild", date(2021, 3, 1), "h1"),
             post("s2", "Kite farms hire harbor crews.", "Harbor Fest", date(2022, 1, 1), "h2"),
             post("s3", SHARED, "Harbor Watch", date(2020, 5, 1), "h1"),
             post("s4", SHARED, "Tide Club", None, "h1")]
    result = answer(items)
    lines = [line for line in result.answer.split("\n") if line[:2] in ("1.", "2.", "3.")]
    assert lines == [
        "1. Post by Harbor Watch, 2020-05-01: “Tidal kites bring jobs to the harbor.” [3] — 2 more posts with the "
        "same text: Kite Guild, Tide Club",
        "2. Post by Harbor Fest, 2022-01-01: “Kite farms hire harbor crews.” [2]"]
    # Counted by post: four matches, four citations; the page shows the two written lines.
    assert result.answer.startswith("4 of the 4 ads that were read match the question.")
    assert len(result.citations) == 4 and result.structured_result["matches"] == 4
    assert result.structured_result["display_citations"] == [3, 2]
    assert "not shown here" not in result.answer
    chinese = answer(items, "哪些帖子把潮汐风筝说成能带来就业？").answer
    assert "（另有 2 条帖子正文相同：Kite Guild、Tide Club）" in chinese


def test_ads_own_texts_and_blank_texts_are_never_grouped():
    ads = [post("n1", SHARED, "", date(2021, 1, 1), "h1", dataset="native"),
           post("n2", SHARED, "", date(2020, 1, 1), "h1", dataset="native")]
    assert "same text" not in answer(ads).answer
    assert answer(ads).structured_result["display_citations"] == [1, 2]
    own = [post("s1", SHARED, "Kite Guild", date(2021, 1, 1), "h1"),
           post("s2", SHARED, "Harbor Watch", date(2020, 1, 1), "h2")]
    assert "same text" not in answer(own).answer
    # A blank text is no text to share (empty-bodied posts all hash alike).
    assert not _same_text_key({"dataset": "social", "body_hash": "h0", "text": "  "})
    assert not _same_text_key({"dataset": "native", "body_hash": "h1", "text": SHARED})
    assert _same_text_key({"dataset": "social", "body_hash": "h1", "text": SHARED})


def test_the_lines_shown_cover_their_groups_and_the_rest_is_counted_by_post():
    items = []
    for n in range(DISPLAY_LIMIT + 2):  # twelve texts, each posted twice
        text = f"Tidal kite farm {n} brings jobs."
        items += [post(f"a{n}", text, f"Guild {n}", date(2021, 1, 1), f"h{n}"),
                  post(f"b{n}", text, f"Watch {n}", date(2020, 1, 1), f"h{n}")]
    result = answer(items)
    written = [line for line in result.answer.split("\n") if line.split(". ", 1)[0].isdigit()]
    assert len(written) == DISPLAY_LIMIT and all("1 more post with the same text" in line for line in written)
    assert "4 more matching ads not shown here." in result.answer  # two texts, two posts each
    assert len(result.structured_result["display_citations"]) == DISPLAY_LIMIT
    by_year = {chart["id"]: chart for chart in result.structured_result["charts"]}["by_year"]
    assert dict(zip(by_year["labels"], by_year["values"])) == {"2020": 12, "2021": 12}  # every post counted


def test_a_list_through_the_service_keeps_the_text_identity_and_writes_one_line():
    import json
    from unittest.mock import Mock

    from test_list_screening import screening_service

    from observatory.list_screening import Batch, Decision
    from observatory.models import Filters

    posts = [post("s1", SHARED, "Kite Guild", date(2021, 3, 1), "h1"),
             post("s2", SHARED, "Harbor Watch", date(2020, 5, 1), "h1")]

    def all_match(**request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        decisions = [Decision(ref=ad["ref"], decision="matches", passage_id=f"{ad['ref']}.1",
                              quote=ad["passages"][0]["text"]) for ad in ads]
        return SimpleNamespace(status="completed", model="offline-fictional", output_parsed=Batch(decisions=decisions),
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                     input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                                     model_dump=lambda: {"input_tokens": 10, "output_tokens": 5}))

    service, parse, db = screening_service([])
    parse.side_effect = all_match
    db.search = Mock(return_value=posts)
    db.public_rows = lambda scope: [{"record_id": "x", "title": "", "dataset": "social"}] * 40
    service.rag.embed = Mock(return_value=[[0.0]])
    result = service._answer_evidence(QUESTION, Filters(dataset="social"), "offline", audit=False)
    assert "fold_same_text" in db.search.call_args.kwargs and db.search.call_args.kwargs["fold_same_text"] is False
    # The earliest post's line carries the note (a one-collection list writes a post like an ad today).
    line = next(line for line in result.answer.split("\n") if line.startswith("1. "))
    assert "Harbor Watch" in line and "2020-05-01" in line
    assert line.endswith("[2] — 1 more post with the same text: Kite Guild")
    assert result.structured_result["matches"] == 2  # both posts judged and counted


def test_a_post_bound_to_another_source_text_stays_on_its_own():
    import hashlib

    from observatory.db import _exact_passages, _first_per_text

    digest = hashlib.sha256(b"other").hexdigest()
    other = post("s2", SHARED, "Harbor Watch", date(2020, 1, 1), "h1").model_copy(update={
        "source_observation_id": "obs-s2", "source_version_id": digest, "source_body_hash": digest})
    items = [post("s1", SHARED, "Kite Guild", date(2021, 1, 1), "h1"), other]
    assert "same text" not in answer(items).answer
    assert not _same_text_key({"dataset": "social", "body_hash": "h1", "text": SHARED, "source_body_hash": digest})
    # Each ranked queue keeps the first post of each text; posts without a key all stay.
    assert _first_per_text(["s1", "s2", "n1", "s3"], {"s1": "h1", "s2": "h1", "s3": "h2"}) == ["s1", "n1", "s3"]
    # The citation moves only to passages with exactly the chosen texts; an overlap is not enough,
    # since it can leave out the sentence the search found.
    rows = [{"text": "Kites bring jobs.", "start": 0, "end": 17}, {"text": "More kites.", "start": 18, "end": 29}]
    assert _exact_passages(rows, [SimpleNamespace(text="More kites."), SimpleNamespace(text="Kites bring jobs.")]) == [
        rows[1], rows[0]]
    assert _exact_passages(rows, [SimpleNamespace(text="More kites."), SimpleNamespace(text="Kites, re-cut.")]) is None


def test_the_service_keeps_the_other_posts_and_hides_the_hash():
    from types import SimpleNamespace as Settings

    from observatory.models import SameTextPost
    from observatory.service import Service

    item = post("s2", SHARED, "Harbor Watch", date(2020, 1, 1), "h1").model_copy(update={
        "same_text_posts": [SameTextPost(record_id="s1", account="Kite Guild", published_at=date(2021, 1, 1))]})
    service = Service.__new__(Service)
    service.settings = Settings(show_source_links=False)
    (public,) = service._public_evidence([item])
    assert public.body_hash == "h1" and public.same_text_posts == item.same_text_posts
    dumped = public.model_dump(mode="json")
    assert "body_hash" not in dumped
    assert dumped["same_text_posts"] == [{"record_id": "s1", "account": "Kite Guild", "platform": "",
                                          "published_at": "2021-01-01"}]
