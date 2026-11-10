"""The reader's retrieval score, the per-route lines on each ad and the step-by-step account under
an answer's first sentence. No database, no model call; fictional ads."""
import json
import math
import re

import plotly
import pytest
from dash import html

from observatory.app import _evidence_cards, _render_answer_result
from observatory.query_demo import recompute_retrieval, replay
from observatory.relevance_eval_ui import CARD_WORDS, save_vote
from observatory.relevance_judge import MAX_AD_CHARS
from observatory.retrieval_explain import (
    complete,
    explanations,
    group_explain,
    list_ndcg,
    ndcg,
    passage_score,
    rag_scores,
    route_points,
    searches,
)

RUN = ["keyword", "vector", "title"]
CRITERION = {"counts": ["Mentions tidal power"], "does_not_count": []}


def text(component):
    if isinstance(component, (list, tuple)):
        component = html.Div([c for c in component if c is not None])
    return json.dumps(component.to_plotly_json(), cls=plotly.utils.PlotlyJSONEncoder, ensure_ascii=False)


def routes(**found):
    return {"run": RUN, **found}


def evidence(rid, eid=None, found=None, version="v1", dataset="native"):
    return {"evidence_id": eid or f"e-{rid}", "record_id": rid, "version_id": version, "dataset": dataset,
            "title": f"Tidal kites {rid}", "publisher": "Harbor Times", "sponsor": "Tidewater Energy",
            "published_at": "2020-05-01", "text": "Tidewater builds tidal turbines.", "start": 0, "end": 31,
            "score": 0.03,
            "retrieval_routes": routes(**(found if found is not None else {
                "keyword": {"rank": 2, "terms": ["tidal", "turbines"]},
                "vector": {"rank": 10, "similarity": 0.61}, "title": {"rank": 1, "terms": ["tidal", "kites"]}})),
            "retrieval_search": {"terms": ["which", "tidal", "turbines", "kites"], "dropped": ["ads", "the"],
                                 "unindexed": ["which"]}}


def test_points_follow_the_published_rule():
    assert route_points(1, RUN) == pytest.approx(100 / 3)
    assert route_points(10, RUN) == pytest.approx(100 / 3 * 61 / 70)
    assert route_points(1, ["keyword", "vector"]) == pytest.approx(50)
    full = passage_score(routes(keyword={"rank": 1}, vector={"rank": 1}, title={"rank": 1}))
    assert full["score"] == pytest.approx(100) and full["missed"] == []


def test_the_score_is_the_fusion_score_rescaled():
    fused = 1 / 62 + 1 / 70  # keyword place 2, vector place 10, not found by title
    explained = passage_score(routes(keyword={"rank": 2}, vector={"rank": 10}))
    assert explained["score"] == pytest.approx(fused * 61 / 3 * 100)
    assert explained["missed"] == ["title"] and sum(p["points"] for p in explained["parts"]) == explained["score"]


@pytest.mark.parametrize("bad", [None, {}, {"run": []}, {"run": ["unknown"]}])
def test_no_routes_no_score(bad):
    assert passage_score(bad) is None


def test_a_record_takes_its_best_passage_and_keeps_its_words():
    low = evidence("r1", "e-low", {"vector": {"rank": 40, "similarity": 0.3}})
    high = evidence("r1", "e-high")
    explain = group_explain([low, high, {"record_id": "r2", "retrieval_routes": {}}])
    assert list(explain["records"]) == ["r1", "r2"] and explain["records"]["r1"]["evidence_id"] == "e-high"
    assert explain["records"]["r2"]["run"] is None and explain["partial"]  # returned, without detail
    assert explain["terms"] == ["which", "tidal", "turbines", "kites"] and explain["runs"] == {"native": RUN}
    bare = group_explain([{"record_id": "r3", "score": 0.02}])
    assert bare["records"]["r3"]["rag_score"] == 0.02 and bare["runs"] == {} and bare["partial"]


def answer(found=None, list_answer=True):
    items = [evidence("r1", found=found)]
    result = {
        "status": "answered", "answer_mode": "rag", "answer": "Found 1 matching ad.",
        "summary": [{"text": "Found 1 matching ad among the 3 in your selection (all checked).", "citation_indices": []},
                    {"text": "Tidewater builds turbines.", "citation_indices": [1]}],
        "structured_result": {"kind": "list", "groups": [{"query": "tidal turbines kites",
                                                          "retrieval_explain": group_explain(items)}]},
        "research_trace": {"original_question": "Which ads mention tidal turbines?"},
        "citations": [{"evidence_id": "e-r1", "quote": "Tidewater builds tidal turbines."}],
        "evidence": items,
    }
    if list_answer:
        result["research_trace"]["list_screening"] = {
            "question": "Which ads mention tidal turbines?", "criterion": CRITERION, "scope_total": 3, "examined": 3,
            "decisions": [{"record_id": "r1", "decision": "matches", "route": "pass", "triage": {
                "meets": 0.9, "borderline": 0.1, "does_not_meet": 0.0, "strength_label": "Clear",
                "rules": [0.95], "exclusions": []}}]}
    return result


def test_the_account_sits_under_the_first_sentence_and_lists_only_elements():
    page = text(_render_answer_result(answer(), True, None))
    first, block, second = (page.index("Found 1 matching ad"), page.index("What the scores are based on"),
                            page.index("Tidewater builds turbines."))
    assert first < block < second and page.count("What the scores are based on") == 1
    assert "Search wording, written from your question: “tidal turbines kites”" in page
    assert "Search words: tidal, turbines, kites" in page
    assert "Left out (too common or one letter): ads, the, which" in page
    assert "Ways used: Words in the text, Similar meaning, Words in the title" in page
    assert "against the rules under “What counts for this question”" in page
    assert f"first {MAX_AD_CHARS:,} characters" in page and "Ads read: 3 of 3 in this selection." in page
    for formula in ("÷", "× 61", "60 +", "keeps", "Listed when", "Order.", "take turns"):  # elements, not rules
        assert formula not in page


def test_the_account_and_each_ad_s_detail_open_on_a_click_and_the_scores_stay_in_view():
    page = json.loads(text(_render_answer_result(answer(), True, None)))
    found = {}

    def walk(node, folded=False):
        if isinstance(node, dict):
            props = node.get("props") or {}
            if node.get("type") == "Details":
                found.setdefault("details", []).append(props.get("open"))
                folded = True
            if isinstance(props.get("children"), str):
                found.setdefault(props["children"], folded)
            walk(props.get("children"), folded)
        elif isinstance(node, list):
            for child in node:
                walk(child, folded)
    walk(page)
    assert found["details"] and not any(found["details"])  # all start closed
    assert found["What the scores are based on"] and found["Matched by the search"] and found["Related to (1)"]
    assert not found["NDCG share 100.0 of 100.0"] and not found["Accuracy 90/100 · Clear"]


def test_each_ad_shows_both_scores_and_what_each_way_matched():
    page = text(_render_answer_result(answer(), True, None))
    assert "NDCG share 100.0 of 100.0" in page and "Accuracy 90/100 · Clear" in page
    assert "Words in the text: tidal, turbines — place 2" in page
    assert "Words in the title: tidal, kites — place 1" in page
    assert "Similar meaning: similarity 0.61 — place 10" in page
    assert "→ +" not in page and "Retrieval rank 1" not in page


def test_a_way_that_missed_says_so_and_an_ordinary_answer_is_not_assessed():
    page = text(_render_answer_result(answer({"keyword": {"rank": 3, "terms": ["tidal"]}}, list_answer=False), True, None))
    assert "Similar meaning: not returned by this way" in page and "Words in the title: not returned" in page
    assert "no match" not in page
    assert "Accuracy score: not assessed" in page and "Accuracy 90/100" not in page


def test_an_ad_read_without_being_found_by_the_search_is_said_so():
    card = text(_evidence_cards([evidence("r9")], True, (), retrieval={}, read_all=True))
    assert "The search did not place this ad; it was read because every ad in the selection is read." in card
    card = text(_evidence_cards([evidence("r9")], True, (), retrieval={}))
    assert "No search detail was recorded for this ad." in card


def test_an_answer_without_searches_or_rules_has_no_account():
    result = answer(list_answer=False)
    result["structured_result"]["groups"] = []
    page = text(_render_answer_result(result, True, None))
    assert "What the scores are based on" not in page and explanations(result) == {}


def test_a_search_without_detail_is_not_called_a_search_that_found_nothing():
    result = answer()
    result["structured_result"]["groups"] = [{"query": "tidal"}]
    assert searches(result) == [("Search", "tidal", None)] and not complete(result)
    page = text(_render_answer_result(result, True, None))
    assert "No search detail was recorded for this search." in page and "found no ads" not in page
    assert "NDCG score: not shown" in page and "Accuracy score:" in page and "Accuracy 90/100" in page
    assert "No search detail was recorded for this ad." in page and "did not place this ad" not in page
    assert "Retrieval rank 1" not in page


def test_three_searches_one_empty_one_without_detail():
    result = answer()
    first = group_explain([evidence("r1", found={"keyword": {"rank": 4, "terms": ["tidal"]}})])
    second = group_explain([evidence("r1"), evidence("r2")])
    second["terms"] = ["wave", "kites"]
    result["structured_result"]["groups"] = [
        {"label": "Tidal", "query": "tidal turbines", "retrieval_explain": first},
        {"label": "Empty", "query": "lagoon", "retrieval_explain": group_explain([])},
        {"label": "Old", "query": "harbor", "retrieval_explain": None},
        {"label": "Wave", "query": "wave kites", "retrieval_explain": second}]
    assert [label for label, _, _ in searches(result)] == ["Tidal", "Empty", "Old", "Wave"]
    explained = explanations(result)
    assert explained["r1"]["search"] == "Tidal" and explained["r1"]["parts"][0]["place"] == 4
    assert explained["r2"]["search"] == "Wave" and not complete(result)
    page = text(_render_answer_result(result, True, None))
    assert "Search “Tidal”" in page and "Search “Wave”" in page and "Search words: wave, kites" in page
    assert "This search found no ads." in page and "No search detail was recorded for this search." in page
    assert "Matched by the search for “Tidal”" in page


def test_mixed_native_and_social_list_the_ways_of_each_collection():
    result = answer()
    social = evidence("s1", dataset="social", found={"keyword": {"rank": 1, "terms": ["tidal"]}})
    social["retrieval_routes"]["run"] = ["keyword", "vector"]
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain([evidence("r1"), social])
    page = text(_render_answer_result(result, True, None))
    assert ("Ways used: native ads: Words in the text, Similar meaning, Words in the title; "
            "social posts: Words in the text, Similar meaning") in page


def test_searches_that_returned_nothing_are_not_called_missing_detail():
    result = answer()
    result["structured_result"]["groups"] = [{"query": "lagoon", "retrieval_explain": group_explain([])},
                                             {"query": "reef", "retrieval_explain": group_explain([])}]
    page = text(_render_answer_result(result, True, None))
    assert page.count("This search found no ads.") == 2 and "NDCG score: none, as the search returned no ads." in page
    assert "no search detail was recorded" not in page.lower()
    result["structured_result"]["groups"][1]["retrieval_explain"] = None
    page = text(_render_answer_result(result, True, None))
    assert "NDCG score: none, as the searches returned no ads or kept no detail." in page


def test_a_search_with_some_passages_without_detail_is_not_complete():
    result = answer()
    explain = group_explain([evidence("r1"), {"record_id": "r2", "retrieval_routes": {}}])
    assert explain["partial"] and list(explain["records"]) == ["r1", "r2"] and explain["records"]["r2"]["run"] is None
    result["structured_result"]["groups"][0]["retrieval_explain"] = explain
    assert not complete(result)
    full = answer()
    assert complete(full) and not full["structured_result"]["groups"][0]["retrieval_explain"]["partial"]


def test_words_past_the_cap_are_named_for_word_and_title_matching_only():
    result = answer()
    result["structured_result"]["groups"][0]["retrieval_explain"]["cut"] = ["harbor", "lagoon"]
    page = text(_render_answer_result(result, True, None))
    assert "Not used for word and title matching (only the first 40 words are): harbor, lagoon" in page


class FakeDb:
    def __init__(self, cached=True, version="v1"):
        self.cached, self.version, self.calls = cached, version, []

    def connect(self, vector=False):
        db = self

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params):
                assert sql.lstrip().upper().startswith("SELECT")  # a cache read, never a write or an API call
                return self

            def fetchone(self):
                return {"embedding": type("V", (), {"to_list": lambda self: [0.1] * 3})()} if db.cached else None
        return Conn()

    def search(self, query, filters, vector=None, model=None, limit=5, chunks_per_record=1):
        self.calls.append((query, vector is not None, limit))
        return [evidence("r1", version=self.version)]


def test_a_replay_recomputes_retrieval_on_today_collection_from_the_cache_only():
    saved = answer()
    saved["structured_result"]["groups"][0]["retrieval_explain"] = None
    saved["structured_result"]["groups"][0]["filters"] = {"dataset": "native"}
    db = FakeDb()
    result = recompute_retrieval(replay(saved), db, today=__import__("datetime").date(2026, 10, 29))
    assert db.calls == [("tidal turbines kites", True, 120)]
    page = text(_render_answer_result(result, True, None))
    assert "recomputed on today's collection (2026-10-29)" in page and "NDCG share 100.0 of 100.0" in page
    assert "changed since the answer was saved" not in page
    changed = recompute_retrieval(replay(saved), FakeDb(cached=False, version="v2"))
    page = text(_render_answer_result(changed, True, None))
    assert "changed since the answer was saved" in page


class EmptyDb(FakeDb):
    def search(self, query, filters, vector=None, model=None, limit=5, chunks_per_record=1):
        return []


def test_a_replay_that_finds_nothing_today_does_not_keep_the_saved_scores():
    saved = answer()
    saved["structured_result"]["groups"][0]["filters"] = {"dataset": "native"}
    result = recompute_retrieval(replay(saved), EmptyDb(), today=__import__("datetime").date(2026, 10, 29))
    group = result["structured_result"]["groups"][0]["retrieval_explain"]
    assert group["records"] == {} and explanations(result) == {}
    page = text(_render_answer_result(result, True, None))
    assert "This search found no ads." in page and "NDCG share 100.0 of 100.0" not in page


class FailingDb(FakeDb):
    def search(self, query, filters, vector=None, model=None, limit=5, chunks_per_record=1):
        if query == "wave":
            raise RuntimeError("search failed")
        return super().search(query, filters, vector, model, limit, chunks_per_record)


def test_a_replay_that_fails_part_way_changes_nothing():
    saved = answer()
    saved["structured_result"]["groups"].append({"label": "Wave", "query": "wave", "retrieval_explain": None})
    result = replay(saved)
    before = __import__("copy").deepcopy(result["structured_result"]["groups"])
    with pytest.raises(RuntimeError):
        recompute_retrieval(result, FailingDb())
    assert result["structured_result"]["groups"] == before



def ids_and_checks(page):
    """Every component id, and each card check's (open, buttons) in page order."""
    ids, checks = [], []

    def walk(node, check=None):
        if isinstance(node, dict):
            props = node.get("props") or {}
            if "id" in props:
                ids.append(json.dumps(props["id"], sort_keys=True))
                if check is not None and isinstance(props["id"], dict) and props["id"].get("type") == "rel-card-vote":
                    check["buttons"].append(props["id"])
            if node.get("type") == "Details" and "your-check" in str(props.get("className")):
                check = {"open": props.get("open"), "buttons": []}
                checks.append(check)
            walk(props.get("children"), check)
        elif isinstance(node, list):
            for child in node:
                walk(child, check)
    walk(json.loads(page))
    return ids, checks


def test_each_listed_ad_has_a_folded_right_or_wrong_choice_after_its_accuracy():
    result = answer()
    result["research_trace"]["list_screening"]["decisions"][0]["screening_reasoning"] = "Mentions turbines."
    page = text(_render_answer_result(result, True, None))
    assert page.index("Accuracy 90/100") < page.index("Related to (1)") < page.index(
        "Your check: is this ad right for the question?")
    assert "Right" in page and "Wrong" in page and "mark it right or wrong" in page
    ids, checks = ids_and_checks(page)
    assert len(checks) == 1 and not checks[0]["open"]
    assert [(b["rid"], b["route"], b["v"]) for b in checks[0]["buttons"]] == [("r1", "pass", "relevant"),
                                                                             ("r1", "pass", "not_relevant")]
    assert not any('"rel-vote"' in i for i in ids)  # one place per ad: the decision list points to the card
    assert "Your check is under this ad's card below." in page
    assert len(ids) == len(set(ids))  # no id twice on the page


def test_a_replay_offers_the_choice_on_the_cards_only():
    page = text(_render_answer_result(replay(answer()), True, None))
    ids, checks = ids_and_checks(page)
    assert len(checks) == 1 and checks[0]["buttons"]
    assert not any('"rel-vote"' in i for i in ids)


def test_an_ad_sent_for_a_check_keeps_its_route_and_an_ordinary_answer_has_no_choice():
    result = answer()
    result["research_trace"]["list_screening"]["decisions"][0]["route"] = "review"
    _, checks = ids_and_checks(text(_render_answer_result(result, True, None)))
    assert {b["route"] for b in checks[0]["buttons"]} == {"review"}
    page = text(_render_answer_result(answer(list_answer=False), True, None))
    assert "Your check" not in page and "mark it right or wrong" not in page


def test_a_card_choice_is_saved_with_its_own_words():
    from types import SimpleNamespace
    from unittest.mock import Mock

    service = SimpleNamespace(review_relevance=Mock(return_value=True))
    clicked = {"type": "rel-card-vote", "q": "x", "rid": "r1", "route": "pass", "v": "not_relevant"}
    assert save_vote(service, "Which ads mention tidal turbines?", clicked, "visitor", CARD_WORDS) == \
        " Saved: wrong. Thank you."
    service.review_relevance.assert_called_once_with("Which ads mention tidal turbines?", "r1", "pass",
                                                     "not_relevant", "visitor")


def test_ndcg_uses_each_shown_ad_s_rag_score_at_its_shown_place():
    explained = {"a": 0.03, "b": 0.05}
    total, shares = ndcg(["a", "b"], explained)
    ideal = 0.05 / 1 + 0.03 / math.log2(3)
    assert total == pytest.approx(100 * (0.03 / 1 + 0.05 / math.log2(3)) / ideal)
    assert shares["a"] == pytest.approx(100 * 0.03 / ideal) and sum(shares.values()) == pytest.approx(total)
    assert ndcg(["b", "a"], explained)[0] == pytest.approx(100)
    # An ad the search did not score still takes its place, with no gain.
    total, shares = ndcg(["x", "b"], explained)
    assert "x" not in shares and total == pytest.approx(100 / math.log2(3))
    assert ndcg(["x"], explained) == (None, {})


def test_each_card_shows_its_ndcg_share_rag_score_and_shown_place():
    result = answer()
    second = evidence("r2", found={"keyword": {"rank": 1, "terms": ["tidal"]}})
    second["score"] = 0.05
    result["evidence"].append(second)
    result["citations"].append({"evidence_id": "e-r2", "quote": "Tidewater builds tidal turbines."})
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain(result["evidence"])
    total, shares = ndcg(["r1", "r2"], {"r1": 0.03, "r2": 0.05})
    page = text(_render_answer_result(result, True, None))
    assert f"NDCG share {shares['r1']:.1f} of {total:.1f}" in page and f"NDCG share {shares['r2']:.1f} of {total:.1f}" in page
    assert "RAG score 0.0300, shown at place 1" in page and "RAG score 0.0500, shown at place 2" in page
    assert f"NDCG score of this list: {total:.1f}/100." in page and not re.search(r"Retrieval [0-9.]+/100", page)
    assert "compares the order the ads are shown in with the same ads ordered by their RAG scores" in page


def test_a_lone_card_s_share_is_its_list_s_whole_ndcg_and_its_rag_score_is_shown_as_is():
    page = text(_render_answer_result(answer(), True, None))
    assert "NDCG share 100.0 of 100.0" in page and "RAG score 0.0300, shown at place 1" in page


def test_a_raw_rag_score_without_route_detail_still_counts_and_an_unknown_score_withholds_ndcg():
    result = answer()
    bare = {**evidence("r2"), "score": 0.05, "retrieval_routes": {}}
    result["evidence"].append(bare)
    result["citations"].append({"evidence_id": "e-r2", "quote": "Tidewater builds tidal turbines."})
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain([evidence("r1"), bare])
    assert rag_scores(result) == {"r1": 0.03, "r2": 0.05}
    total, shares = ndcg(["r1", "r2"], {"r1": 0.03, "r2": 0.05})
    page = text(_render_answer_result(result, True, None))
    assert f"NDCG score of this list: {total:.1f}/100." in page
    # Both cards show their raw score and share; the one without routes says they were not recorded.
    assert f"NDCG share {shares['r1']:.1f} of {total:.1f}" in page and f"NDCG share {shares['r2']:.1f} of {total:.1f}" in page
    assert "RAG score 0.0300, shown at place 1" in page and "RAG score 0.0500, shown at place 2" in page
    assert page.count("Which words or ways found this ad was not recorded.") == 1
    # A shown ad with no recorded score, while a search kept no detail: its score is unknown.
    result["structured_result"]["groups"].append({"label": "Old", "query": "harbor", "retrieval_explain": None})
    result["evidence"].append(evidence("r3"))
    result["citations"].append({"evidence_id": "e-r3", "quote": "Tidewater builds tidal turbines."})
    page = text(_render_answer_result(result, True, None))
    assert "NDCG score: not computed, as some shown ads have no recorded RAG score." in page
    assert "NDCG share" not in page


def test_a_search_that_kept_only_scores_still_scores_every_card():
    result = answer()
    bare = [{**evidence("r1"), "retrieval_routes": {}}, {**evidence("r2"), "score": 0.05, "retrieval_routes": {}}]
    result["evidence"] = bare
    result["citations"].append({"evidence_id": "e-r2", "quote": "Tidewater builds tidal turbines."})
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain(bare)
    total, shares = ndcg(["r1", "r2"], {"r1": 0.03, "r2": 0.05})
    page = text(_render_answer_result(result, True, None))
    assert "This search's words and ways were not recorded; its RAG scores were." in page
    assert "found no ads" not in page and "NDCG score: none" not in page
    assert f"NDCG score of this list: {total:.1f}/100." in page
    assert f"NDCG share {shares['r1']:.1f} of {total:.1f}" in page and f"NDCG share {shares['r2']:.1f} of {total:.1f}" in page
    assert "RAG score 0.0300, shown at place 1" in page and "RAG score 0.0500, shown at place 2" in page
    assert page.count("Which words or ways found this ad was not recorded.") == 2


def test_a_record_s_score_and_detail_come_from_one_search_and_one_passage():
    # Two searches: the first returned r1 with a low score and no routes, the second with a high
    # score and routes. The card shows the first search's score and says its routes were not kept.
    result = answer()
    first = group_explain([{**evidence("r1"), "score": 0.01, "retrieval_routes": {}}])
    second = group_explain([{**evidence("r1"), "score": 0.05}])
    result["structured_result"]["groups"] = [{"label": "Tidal", "query": "tidal", "retrieval_explain": first},
                                             {"label": "Wave", "query": "wave", "retrieval_explain": second}]
    explained = explanations(result)["r1"]
    assert (explained["search"], explained["rag_score"], explained["run"]) == ("Tidal", 0.01, None)
    assert rag_scores(result) == {"r1": 0.01}
    page = text(_render_answer_result(result, True, None))
    assert "Matched by the search for “Tidal”" in page and "RAG score 0.0100, shown at place 1" in page
    assert "RAG score 0.0500" not in page and "Which words or ways found this ad was not recorded." in page
    # One search, two passages of r1: the higher-scoring passage gives both the score and the detail.
    high_bare = {**evidence("r1", "e-bare"), "score": 0.05, "retrieval_routes": {}}
    low_routed = {**evidence("r1", "e-routed"), "score": 0.02}
    record = group_explain([low_routed, high_bare])["records"]["r1"]
    assert (record["evidence_id"], record["rag_score"], record["run"]) == ("e-bare", 0.05, None)
    record = group_explain([{**high_bare, "retrieval_routes": low_routed["retrieval_routes"]},
                            {**low_routed, "retrieval_routes": {}}])["records"]["r1"]
    assert (record["evidence_id"], record["rag_score"], record["run"]) == ("e-bare", 0.05, RUN)


def test_a_shown_ad_returned_without_a_score_withholds_ndcg():
    result = answer()
    unscored = {**evidence("r2"), "score": None}
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain([evidence("r1"), unscored])
    assert complete(result) and list_ndcg(result, ["r1", "r2"]) == (None, {}, True)
    # An ad no search returned, when every search kept its detail, takes its place with no gain.
    total, shares, unknown = list_ndcg(result, ["r3", "r1"])
    assert not unknown and total == pytest.approx(100 / math.log2(3)) and list(shares) == ["r1"]


def test_two_passages_of_one_listed_ad_keep_their_quotes_and_one_set_of_scores_and_choice():
    result = answer()
    second = {**evidence("r1", "e-r1b"), "text": "Tidewater also tests tidal kites.", "score": 0.02}
    result["evidence"].append(second)
    result["citations"].append({"evidence_id": "e-r1b", "quote": "Tidewater also tests tidal kites."})
    result["summary"][1]["citation_indices"] = [1, 2]
    result["structured_result"]["groups"][0]["retrieval_explain"] = group_explain(result["evidence"])
    tree = json.loads(text(_render_answer_result(result, True, None)))
    page = json.dumps(tree, ensure_ascii=False)
    assert "Tidewater builds tidal turbines." in page and "Tidewater also tests tidal kites." in page
    assert "answer-citation-1" in page and "answer-citation-2" in page
    assert page.count("NDCG share 100.0 of 100.0") == 1 and page.count("Accuracy 90/100 · Clear") == 1
    assert page.count("Your check: is this ad right for the question?") == 1
    assert page.count("Another passage of the ad above; its scores and your check are on that card.") == 1
    ids = []

    def walk(node):
        if isinstance(node, dict):
            props = node.get("props") or {}
            if "id" in props:
                ids.append(json.dumps(props["id"], sort_keys=True))
            walk(props.get("children"))
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(tree)
    assert ids and len(ids) == len(set(ids))


def test_a_listed_ad_without_a_card_keeps_its_check_in_the_decision_list():
    result = answer()
    screening = result["research_trace"]["list_screening"]
    screening["decisions"].append({**screening["decisions"][0], "record_id": "r5"})
    ids, checks = ids_and_checks(text(_render_answer_result(result, True, None)))
    assert [b["rid"] for b in checks[0]["buttons"]] == ["r1", "r1"]
    listed = [json.loads(i) for i in ids if '"rel-vote"' in i]
    assert {i["rid"] for i in listed} == {"r5"}  # r1 is checked on its card only


def test_the_registered_card_callback_saves_the_reader_s_choice():
    from types import SimpleNamespace

    from test_app import FakeService
    from test_criterion_ui import post_pattern_callback

    from observatory.app import create_app
    from observatory.relevance_eval_ui import _question_key

    question = "Which ads mention tidal turbines?"
    service, saved = FakeService(), []
    service.review_relevance = lambda q, rid, route, verdict, visitor: saved.append((q, rid, route, verdict)) or True
    app = create_app(service, SimpleNamespace(show_source_links=True, cookie_secret="test-cookie-secret",
                                              monthly_budget_usd=100, criterion_confirmation="ask"))
    client = app.server.test_client()
    for rid, verdict, word in (("r1", "relevant", "right"), ("r2", "not_relevant", "wrong"), ("r1", "not_relevant", "wrong")):
        clicks = [({"route": "pass", "v": v}, int(v == verdict)) for v in ("relevant", "not_relevant")]
        response = post_pattern_callback(app, client, "rel-card-vote", {"q": _question_key(question), "rid": rid},
                                         {"rel-card-vote.n_clicks": clicks, "rel-card-question.data": question},
                                         ({"route": "pass", "v": verdict}, "n_clicks"))
        assert f"Saved: {word}. Thank you." in json.dumps(response)
    assert saved == [(question, "r1", "pass", "relevant"), (question, "r2", "pass", "not_relevant"),
                     (question, "r1", "pass", "not_relevant")]
