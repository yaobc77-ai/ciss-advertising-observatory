"""scripts/rag_metrics_report.py: the metric definitions, the keyword rule in words and the per-question verdicts.
Free and offline; fictional ads, sponsors and questions."""
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

import scripts.rag_metrics_report as report
from scripts.rag_metrics_report import (
    b1k_content_row,
    b1k_list_row,
    b1k_title_row,
    cited_ids,
    depth_rows,
    depth_scores,
    disagreement,
    field_match,
    first_batch,
    in_scope,
    judge_order,
    keyword_forms,
    matched_forms,
    old_scorer_counts,
    old_scorer_differences,
    order_check,
    order_metrics,
    read_funnel,
    read_order,
    scope_words,
    scoring_time_verdict,
    searches,
    set_metrics,
    summarize,
)


def test_set_metrics_counts_a_list_against_its_truth():
    got = set_metrics({"a", "b", "c"}, {"a", "b", "d"})
    assert (got["tp"], got["fp"], got["fn"]) == (2, 1, 1)
    assert got["precision"] == pytest.approx(2 / 3)
    assert got["recall"] == pytest.approx(2 / 3)
    assert got["f1"] == pytest.approx(4 / 6)


def test_set_metrics_edge_cases():
    nothing_listed = set_metrics(set(), {"a"})
    assert (nothing_listed["precision"], nothing_listed["recall"], nothing_listed["f1"]) == (None, 0.0, 0.0)
    wrong_on_empty_truth = set_metrics({"a"}, set())
    assert (wrong_on_empty_truth["fp"], wrong_on_empty_truth["precision"], wrong_on_empty_truth["recall"]) == (1, 0.0, None)
    assert set_metrics(set(), set())["f1"] is None


def test_an_unlabelled_listed_ad_counts_neither_way():
    got = set_metrics({"a", "u"}, {"a"}, unknown={"u"})
    assert (got["tp"], got["fp"], got["unlabelled_listed"], got["precision"]) == (1, 0, 1, 1.0)


def test_order_metrics_follow_the_published_definitions():
    got = order_metrics(["x", "a", "y", "b"], {"a", "b", "c"}, (1, 2, 4))  # c was never read
    assert (got["first_relevant"], got["rr"]) == (2, 0.5)
    assert (got["hit@1"], got["hit@2"]) == (0.0, 1.0)
    assert (got["p@2"], got["pmax@2"], got["r@2"]) == (0.5, 1.0, pytest.approx(1 / 3))
    assert got["ndcg@2"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))
    assert (got["p@4"], got["pmax@4"], got["r@4"]) == (0.5, 0.75, pytest.approx(2 / 3))
    ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)  # three relevant ads, so the ideal fills three places
    assert got["ndcg@4"] == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / ideal)
    assert got["f1@4"] == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))


def test_order_metrics_without_a_found_ad_and_without_truth():
    missed = order_metrics(["x", "y"], {"a"}, (2,))
    assert (missed["rr"], missed["first_relevant"], missed["hit@2"], missed["ndcg@2"]) == (0.0, None, 0.0, 0.0)
    empty = order_metrics([], {"a"}, (2,))  # nothing read or retrieved: a 0, not a missing score
    assert (empty["rr"], empty["ndcg@2"], empty["r@2"]) == (0.0, 0.0, 0.0)
    assert order_metrics(["x"], set(), (2,)) is None


def test_an_unlabelled_ad_keeps_its_place_with_no_gain():
    got = order_metrics(["u", "a"], {"a"}, (2,), unknown={"u"})
    assert (got["rr"], got["unlabelled@2"]) == (0.5, 1)


def test_depth_scores_name_the_full_and_condensed_ranks_apart():
    ranked = [f"u{i}" for i in range(9)] + ["a", "b"]  # nobody coded u0 to u8
    got = depth_scores(ranked, relevant={"a"}, coded={"a", "b"})
    assert got["full_rank"]["rr"] == pytest.approx(0.1) and got["full_rank"]["unlabelled@10"] == 9
    assert got["condensed"]["rr"] == 1.0  # among the coded ads only, the relevant one is first


def test_a_relevant_ad_the_depth_ranking_left_out_still_counts():
    got = depth_scores(["a", "b"], relevant={"a", "c"}, coded={"a", "b", "c"})  # c was never ranked
    assert got["full_rank"]["r@10"] == 0.5 and got["condensed"]["r@10"] == 0.5
    assert got["condensed"]["ndcg@10"] == pytest.approx(1 / (1 + 1 / math.log2(3)))


def test_depth_rows_take_the_truth_from_the_hand_codes(tmp_path, monkeypatch):
    run = {"run_date": "2026-01-02", "data_version": "v-test", "questions": [{
        "label": "green.tidal", "question": "Which ads mention tidal power?", "scope_total": 4, "ranked": 3,
        "ads": [{"record_id": "u1", "rank": 2, "title": "Harbor Lights", "human": None},
                {"record_id": "a", "rank": 1, "title": "Tidal Futures", "human": True},
                {"record_id": "b", "rank": 3, "title": "Quiet Coast", "human": True}]}]}  # the run's copy of b is wrong
    path = tmp_path / "result.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(report, "DEPTH", path)
    truth = {"green.tidal": ({"a", "c"}, {"a", "b", "c"})}  # c is coded relevant but was never ranked
    rows, source = depth_rows({"a": 1, "b": 2, "c": 3}, truth)
    got = rows[0]
    assert (got["n_relevant"], got["n_coded"], got["not_ranked"], got["flag_mismatch"]) == (2, 3, ["c"], ["b"])
    assert [(a["record_id"], a["rank"], a["label"]) for a in got["ranks"]] == [
        ("a", 1, "relevant"), ("b", 3, "not_relevant"), ("c", None, "relevant")]
    assert got["full_rank"]["r@10"] == 0.5 and got["condensed"]["r@10"] == 0.5  # c stays in the denominator
    assert source["run_date"] == "2026-01-02"
    run["questions"][0]["ads"][2]["record_id"] = "a"  # one ad ranked twice
    path.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(AssertionError):
        depth_rows({}, truth)


def test_judge_order_sorts_by_probability_and_counts_what_the_saved_order_had_the_other_way_round():
    verdicts = {"a": {"triage": {"meets": 0.9}}, "b": {"triage": {"meets": 0.4}}, "c": {"triage": {"meets": 0.7}},
                "d": {"triage": {}}, "e": {"triage": {"meets": 0.7}}}
    ranked, how = judge_order(["a", "b", "c", "d", "e"], verdicts, relevant={"a", "c", "e"})
    assert ranked == ["a", "c", "e", "b", "d"]  # c and e tie and keep their saved order; d has no probability
    # b was saved before c and before e: two reversed pairs, both between a not-relevant and a relevant ad
    assert how == {"inversions": 2, "across_labels": 2, "without_probability": 1, "labels_moved": True}


def test_an_unchanged_label_sequence_can_still_hide_reversed_pairs_across_labels():
    verdicts = {"r1": {"triage": {"meets": 0.1}}, "n": {"triage": {"meets": 0.5}}, "r2": {"triage": {"meets": 0.9}}}
    saved = ["r1", "n", "r2"]
    ranked, how = judge_order(saved, verdicts, relevant={"r1", "r2"})
    assert ranked == ["r2", "n", "r1"]
    assert how == {"inversions": 3, "across_labels": 2, "without_probability": 0, "labels_moved": False}
    # the places of the relevant ads did not move, so no order score can change
    assert order_metrics(saved, {"r1", "r2"}, (1, 3)) == order_metrics(ranked, {"r1", "r2"}, (1, 3))
    words = _dashboard_tables().judge_text(how)
    assert "其中 2 对是一篇相关、一篇不相关" in words and words.endswith("所以排序指标不变")
    assert "都在人工标签相同的广告之间" not in words


def test_only_explicit_labels_disagree():
    assert disagreement("relevant", False) == "missed"
    assert disagreement("not_relevant", True) == "wrong"
    for label in ("disputed", "neutral", "unlabelled", "other"):  # "other": cited, but not a known source
        assert disagreement(label, True) is None and disagreement(label, False) is None
    assert disagreement("relevant", True) is None and disagreement("not_relevant", False) is None


def row(final, n_relevant, n_listed, order=None, **extra):
    return {"final": final, "n_relevant": n_relevant, "n_listed": n_listed, "order": order, **extra}


def test_summarize_pools_wrong_listings_of_empty_truth_questions():
    with_truth = row(set_metrics({"a", "b", "z"}, {"a", "b"}), 2, 3, order_metrics(["a", "z", "b"], {"a", "b"}, (2,)))
    listed_on_empty = row(set_metrics({"q"}, set()), 0, 1)
    empty_and_right = row(set_metrics(set(), set()), 0, 0)
    got = summarize([with_truth, listed_on_empty, empty_and_right], (2,))
    assert (got["questions"], got["with_truth"], got["empty_truth"], got["empty_truth_correct"]) == (3, 1, 2, 1)
    assert got["final_micro"]["precision"] == pytest.approx(2 / 4)  # the empty-truth listing is a wrong listing
    assert got["final_micro"]["recall"] == 1.0
    assert got["final_macro"]["precision"] == {"mean": pytest.approx(2 / 3), "n": 1}  # macro: questions with truth
    assert got["order_mean"]["rr"] == {"mean": 1.0, "n": 1}
    assert got["pooled_recall"]["r@2"] == 0.5
    assert (got["expected"], got["missing"], got["coverage"]) == (3, [], 1.0)


def test_an_empty_order_scores_zero_and_a_missing_question_is_listed():
    found = row(None, 1, 1, order_metrics(["a"], {"a"}, (2,)), n_read=1)
    nothing = row(None, 1, 0, order_metrics([], {"b"}, (2,)), n_read=0)  # answered, but retrieved nothing
    got = summarize([found, nothing], (2,), missing=["run:Q-3"])
    assert got["order_mean"]["rr"] == {"mean": 0.5, "n": 2}
    assert got["order_mean"]["ndcg@2"] == {"mean": 0.5, "n": 2}
    assert (got["questions"], got["expected"], got["missing"]) == (2, 3, ["run:Q-3"])
    assert got["coverage"] == pytest.approx(2 / 3) and got["empty_order"] == 1


def test_summarize_reports_every_keyword_basis():
    strict = set_metrics({"a", "s"}, {"a"})
    keyword = row(strict, 1, 2, order_metrics(["a", "s"], {"a"}, (2,)), final_reference=set_metrics({"a", "s"}, {"a"}, {"s"}),
                  final_old_scorer=old_scorer_counts({"a", "s"}, {"a", "s"}))
    got = summarize([keyword], (2,))
    assert got["final_micro"]["precision"] == 0.5
    assert got["final_reference_micro"]["precision"] == 1.0
    assert got["final_old_scorer_micro"]["tp"] == 2


def test_read_coverage_grows_and_the_final_list_can_keep_fewer():
    order = ["a", "n1", "b", "n2", "c"]  # the screening's read order
    got = read_funnel(order, {"a", "b", "c", "d"}, {"a", "b", "n2"}, ks=(1, 3))  # d was never read
    assert got == {"relevant": 4, "first_1": 1, "first_3": 2, "read": 3, "listed": 2, "read_not_listed": 1,
                   "listed_not_read": 0}
    assert read_funnel([], {"a"}, set()) == {"relevant": 1, "first_10": 0, "first_40": 0, "read": 0, "listed": 0,
                                             "read_not_listed": 0, "listed_not_read": 0}


def test_read_and_listed_relevant_ads_are_compared_as_sets():
    # b and c were read but not listed; e was listed by another route without being in the read record
    got = read_funnel(["a", "b", "c"], {"a", "b", "c", "e"}, {"a", "e"}, ks=())
    assert got == {"relevant": 4, "read": 3, "listed": 2, "read_not_listed": 2, "listed_not_read": 1}
    # the human runs read every coded ad they are given: no read-order stages
    assert set(read_funnel(["a", "b"], {"a"}, {"a"}, ks=())) == {"relevant", "read", "listed", "read_not_listed",
                                                               "listed_not_read"}


def test_an_unlabelled_ad_keeps_its_read_place_in_the_funnel():
    # u has no label: it is in no stage, but it still takes place 1, so a is not among the first 1
    got = read_funnel(["u", "a"], {"a"}, {"a"}, ks=(1, 2))
    assert (got["first_1"], got["first_2"]) == (0, 1)


def test_summarize_pools_the_funnel_and_its_last_stage_is_the_final_lists_true_positives():
    read_on = row(set_metrics({"a", "z"}, {"a", "b"}), 2, 2, order_metrics(["a", "z", "b"], {"a", "b"}, (2,)), n_read=3,
                  funnel=read_funnel(["a", "z", "b"], {"a", "b"}, {"a", "z"}, ks=(2,)))
    another_route = row(set_metrics({"c"}, {"c"}), 1, 1, order_metrics([], {"c"}, (2,)), n_read=0,
                        funnel=read_funnel([], {"c"}, {"c"}, ks=(2,)))
    got = summarize([read_on, another_route], (2,))
    assert {k: v for k, v in got["funnel"].items() if k != "rates"} == {
        "relevant": 3, "first_2": 1, "read": 2, "listed": 2, "read_not_listed": 1, "listed_not_read": 1}
    assert got["funnel"]["rates"]["listed"] == got["final_micro"]["recall"] == pytest.approx(2 / 3)
    # pooled over the question-ad pairs (2 of 3 read), not a mean of the questions' shares ((2/2 + 0/1) / 2)
    assert got["funnel"]["rates"]["read"] == pytest.approx(2 / 3) and got["max_read"] == 3
    nothing = row(set_metrics(set(), set()), 0, 0, None, n_read=0, funnel=read_funnel([], set(), set(), ks=(2,)))
    empty = summarize([nothing], (2,), missing=["run:Q-2"])
    assert empty["funnel"]["rates"] == {"first_2": None, "read": None, "listed": None, "read_not_listed": None,
                                        "listed_not_read": None}  # no relevant ads: no share
    assert empty["coverage"] == 0.5
    wrong = row(set_metrics({"a"}, {"a"}), 1, 1, order_metrics(["a"], {"a"}, (2,)), n_read=1,
                funnel=read_funnel(["a"], {"a"}, set(), ks=(2,)))  # a funnel that is not this list's
    with pytest.raises(AssertionError):
        summarize([wrong], (2,))


def test_old_scorer_counts_and_what_a_reconciliation_catches():
    got = old_scorer_counts({"a", "b", "n"}, {"a", "c"}, neutral={"n"})
    assert (got["tp"], got["n_pos"], got["n_judged_cited"], got["fp"], got["fn"]) == (1, 2, 2, 1, 1)
    assert (got["precision"], got["recall"]) == (0.5, 0.5)
    assert old_scorer_counts(set(), set())["precision"] == 1.0  # nothing to find and nothing listed: the old scorer gave 1
    old = {"tp": 1, "n_pos": 2, "n_judged_cited": 2, "precision": 0.5, "recall": 0.5}
    assert old_scorer_differences(got, old) == []
    # one more wrong listing on the old side and nothing else: the same tp and positives, but caught
    assert old_scorer_differences(got, {**old, "n_judged_cited": 3, "precision": 1 / 3}) == ["n_judged_cited", "precision"]


def test_scoring_time_verdict_reads_the_run_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "B1K", tmp_path)
    ad = {"title": "Hydrogen hubs", "chunks": ["We fly hydrogen planes.", "Northwind Energy builds hubs."]}
    criterion = "The ad mentions aviation (synonyms and closely related wording count)"
    user = f"Criterion: {criterion}\n\nAd title: {ad['title']}\n" + "\n".join(ad["chunks"])
    key = hashlib.sha256(json.dumps(["adjudicate", report.ADJUDICATE_MODEL, "high", report.ADJUDICATE_SYSTEM, user,
                                     report.ADJUDICATE_SCHEMA], sort_keys=True).encode()).hexdigest()
    cache = tmp_path / "run" / "cache" / f"adjudicate-{key[:24]}.json"
    cache.parent.mkdir(parents=True)

    def answered(verdict, quote):
        cache.write_text(json.dumps({"parsed": {"verdict": verdict, "quote": quote}}), encoding="utf-8")
        return scoring_time_verdict("run", criterion, ad)

    assert answered("yes", "we fly  hydrogen planes")["accepted"]  # case and spacing are normalized
    assert not answered("yes", "We fly hydrogen jets")["accepted"]  # a quote that is not in the text
    assert not answered("yes", "We fly")["accepted"]  # shorter than 12 characters
    assert not answered("no", "We fly hydrogen planes")["accepted"]
    assert answered("no", "")["cache"] == f"run/cache/adjudicate-{key[:24]}.json"  # the file it came from
    assert scoring_time_verdict("run", "The ad mentions podcasts", ad) is None  # that run never asked


@pytest.mark.parametrize("rule, expected", [
    (r"\bsolar\b", [{"forms": ["solar"], "whole_word": True}]),
    (r"solar", [{"forms": ["solar"], "whole_word": False}]),
    (r"\bhydrogen\b|\bH2\b", [{"forms": ["hydrogen"], "whole_word": True}, {"forms": ["H2"], "whole_word": True}]),
    (r"\bLNG\b|liquefied natural gas", [  # a shared \b prefix is not moved in front of every alternative
        {"forms": ["LNG"], "whole_word": True}, {"forms": ["liquefied natural gas"], "whole_word": False}]),
    (r"\b(?:solar|wind) (?:farm|park)\b|[|]", [
        {"forms": ["solar farm", "solar park", "wind farm", "wind park"], "whole_word": True},
        {"forms": ["|"], "whole_word": False}]),
    (r"\b(?:carbon[- ]capture|CCS)\b", [{"forms": ["carbon capture", "carbon-capture", "CCS"], "whole_word": True}]),
    (r"\bwind ?farms?\b", [{"forms": ["wind farm", "wind farms", "windfarm", "windfarms"], "whole_word": True}]),
    (r"\bCOP ?\d{1,2}\b", [{"forms": ["COP #", "COP ##", "COP#", "COP##"], "whole_word": True}]),
])
def test_keyword_forms_spell_out_a_rule(rule, expected):
    assert keyword_forms(rule) == expected


@pytest.mark.parametrize("rule", [
    r"\bwind\w+", r"[a-z]{5}", r"\bgas(?:es)*\b",
    r"\bgo+al\b",  # a repeat is open-ended, whatever it repeats
    r"liquefied[\s-]+natural gas", r"wind\sfarm",  # \s also takes tabs and newlines, and + takes any run of them
    r"\bsolar", r"solar\bpanel", r"^solar$",  # a boundary on one end only, inside, or an anchor
])
def test_keyword_forms_give_up_unless_the_forms_are_exact(rule):
    assert keyword_forms(rule) is None


def test_a_space_in_a_form_is_one_space():
    assert keyword_forms(r"crude oil") == [{"forms": ["crude oil"], "whole_word": False}]
    assert re.search(r"crude oil", "CRUDE OIL", re.I) and not re.search(r"crude oil", "crude\noil", re.I)
    # what no short list of forms could show, so that rule is not spelled out
    assert re.search(r"liquefied[\s-]+natural gas", "liquefied \n- natural gas", re.I)


def _canon(text):
    return re.sub(r"\d", "#", text.lower())


@pytest.mark.parametrize("rule", [
    r"crude oil", r"\bbio-?fuels?\b", r"electric vehicles?|\bEVs?\b|electric cars?",
    r"Paris (?:climate )?(?:Agreement|accord)", r"\bCOP ?\d{1,2}\b", r"net[- ]zero", r"\bgas(?:es){0,2}\b",
])
def test_spelled_out_forms_are_exactly_what_the_rule_matches(rule):
    """Each alternative's forms all match it, and any one-character change of a form that it still matches is itself
    one of the forms: the forms are everything the alternative matches, not a sample."""
    entries, alternatives = keyword_forms(rule), report._alternatives(rule)
    assert entries is not None and len(entries) == len(alternatives)
    alphabet = sorted({c for e in entries for f in e["forms"] for c in f.lower()} | set("ab -73\n\t"))
    for alternative, entry in zip(alternatives, entries):
        pattern = re.compile(alternative, re.I)
        forms = {_canon(f) for f in entry["forms"]}
        spelled = [f.replace("#", "7") for f in forms]
        assert all(pattern.fullmatch(f) for f in spelled), alternative
        # every insertion or substitution (j = i or i + 1) and every deletion of one character
        near = {f[:i] + c + f[j:] for f in spelled for i in range(len(f) + 1) for j in (i, i + 1) for c in alphabet}
        near |= {f[:i] + f[i + 1:] for f in spelled for i in range(len(f))}
        assert {_canon(s) for s in near if s and pattern.fullmatch(s)} <= forms, alternative


def test_matched_forms_lists_what_the_text_contains_most_often_first():
    text = "Hydrogen buses, H2 storage and more hydrogen."
    assert matched_forms(r"\bhydrogen\b|\bH2\b", text) == [["hydrogen", 2], ["h2", 1]]
    assert matched_forms(r"\bsolar\b", None) == []


def test_scope_in_words():
    scope = {"sponsor": ["Northwind Energy", "Contoso Oil"], "years": [2019, 2021]}
    assert scope_words(scope) == "赞助方 = Northwind Energy、Contoso Oil；发布年份 2019–2021（无日期的不算）"
    assert scope_words({}) == "全部可检索的原生广告"


def test_in_scope_follows_the_generator_rule():
    ad = {"sponsor": "Northwind Energy", "publisher": "Daily Planet", "date": "2020-05-01"}
    assert in_scope(ad, {"years": [2019, 2021], "sponsor": "Northwind Energy", "publisher": "Daily Planet"})
    assert in_scope(ad, {"from": 2020}) and not in_scope(ad, {"before": 2020})
    assert not in_scope(ad, {"not_sponsor": ["Northwind Energy"]})
    assert not in_scope({**ad, "date": None}, {"years": [2019, 2021]})


def test_field_match():
    assert field_match("date", "2018-03-07", "2018-03-07T00:00:00")
    assert field_match("disclosure_head", "PAID POST", "Paid Post by Contoso Oil")
    assert field_match("publisher", "The Daily Planet", "the daily  planet")
    assert not field_match("sponsor", "Contoso Oil", None)
    assert not field_match("sponsor", "Contoso Oil", "Northwind Energy")


def answer(decisions, cited, queries=("hydrogen ads",), ranks=None):
    ranks = ranks or {}
    evidence = [{"evidence_id": f"E{i}", "record_id": rid, **({"retrieval_rank": ranks[rid]} if rid in ranks else {})}
                for i, rid in enumerate(dict.fromkeys([d[0] for d in decisions] + list(cited)))]
    by_record = {e["record_id"]: e["evidence_id"] for e in evidence}
    return {"status": "answered", "evidence": evidence,
            "citations": [{"evidence_id": by_record[rid]} for rid in cited] + [{"evidence_id": "gone"}],
            "research_trace": {"tools": [{"arguments": {"query": q}} for q in queries] + [{"arguments": {"title": "x"}}],
                               "list_screening": {"decisions": [{"record_id": rid, "decision": d, "quote": f"quote {rid}"}
                                                                for rid, d in decisions]}}}


def test_reading_a_saved_answer():
    result = answer([("a2", "matches"), ("a1", "does_not_match"), ("a2", "matches")], ["a2"],
                    queries=("solar farms", "solar farms"), ranks={"a2": 1})
    assert cited_ids(result) == {"a2"}
    assert searches(result) == ["solar farms"]
    order, verdicts = read_order(result)
    assert order == ["a2", "a1"] and verdicts["a1"]["decision"] == "does_not_match"
    assert order_check(result, order) == (1, 1)


def ad(rid, text, date="2020-01-01", title=None):
    return {"record_id": rid, "title": title or f"Story {rid}", "sponsor": "Northwind Energy", "publisher": "Daily Planet",
            "date": date, "text": text, "chunks": [text], "countable": "true"}


ADS = {"a1": ad("a1", "We build hydrogen hubs.", title="Hydrogen hubs"), "a2": ad("a2", "Fuel cells for trucks."),
       "a3": ad("a3", "H2 storage", date="2018-01-01"), "a4": ad("a4", "A hydrogen pilot.")}
KEYWORD = {"query_id": "T-1", "group": "T1", "query_class": "mention_years", "question": "Which ads from 2019-2021 mention hydrogen?",
           "rule": r"\bhydrogen\b|\bH2\b", "scope": {"years": [2019, 2021]}, "list_truth": {"positive": ["a1", "a4"]}}


def test_a_keyword_question_row():
    result = answer([("a2", "matches"), ("a1", "matches"), ("a4", "does_not_match")], ["a1", "a2"])
    reference = {"a2": {"status": "disputed", "adjudicator": "yes", "adjudicator_quote": "fuel cells"}}
    then = {"a2": {"verdict": "yes", "quote": "Fuel cells for trucks", "accepted": True}}
    got = b1k_list_row("run", KEYWORD, result, ADS, set(ADS), {}, reference, {}, with_ads=True, scoring_time=then.get)
    assert got["criterion"]["truth_matches_rule"] and got["criterion"]["ads_in_scope"] == 3
    assert got["criterion"]["alternatives"][1] == {"forms": ["H2"], "whole_word": True}
    assert (got["final"]["tp"], got["final"]["fp"], got["final"]["fn"]) == (1, 1, 1)
    assert got["final"]["fp_by_reference"] == {"disputed": 1}
    assert got["final_reference"]["precision"] == 1.0  # the AI-accepted wording counts neither way there
    old = got["final_old_scorer"]  # the scorer of the time added what its adjudicator accepted then
    assert (old["tp"], old["n_pos"], old["n_judged_cited"], old["fn"]) == (2, 3, 2, 1)
    assert got["adjudication_changed"] == []  # then and in the reference, the adjudicator accepted a2
    assert got["order"]["rr"] == 0.5 and got["order_kind"] == "read" and got["screened"]
    # a1 and a4 were read (places 2 and 3); only a1 is listed
    assert got["funnel"] == {"relevant": 2, "first_10": 2, "first_40": 2, "read": 2, "listed": 1, "read_not_listed": 1,
                             "listed_not_read": 0}
    assert got["first_read"] is None  # this fictional trace records no first_read
    assert (got["in_scope_not_read"], got["read_outside_scope"]) == (0, 0)  # a1, a2 and a4 are the scope and the record
    rows = {r["record_id"]: r for r in got["ads"]}
    assert list(rows) == ["a2", "a1", "a4"]  # a3 is out of scope, unread and unlisted
    assert rows["a1"]["why"]["forms"] == [["hydrogen", 1]] and rows["a1"]["why"]["in_title"]
    assert rows["a2"]["why"]["adjudicator_quote"] == "fuel cells" and rows["a2"]["label"] == "not_relevant"
    assert (rows["a4"]["label"], rows["a4"]["listed"], rows["a4"]["position"]) == ("relevant", False, 3)
    assert {rid: r["disagreement"] for rid, r in rows.items()} == {"a2": "wrong", "a1": None, "a4": "missed"}


def test_the_first_batch_of_a_small_scope_holds_only_when_every_ad_in_it_is_in_the_read_record():
    # a1, a2 and a4 are in scope; this record holds a1, a2 and the out-of-scope a3: three ads, but a4 is not among them
    short = answer([("a1", "matches"), ("a2", "does_not_match"), ("a3", "matches")], ["a1"])
    short["research_trace"]["list_screening"].update({"first_read": 40, "scope_total": 4})
    short = b1k_list_row("run", KEYWORD, short, ADS, set(ADS), {}, {}, {}, with_ads=False)
    assert (short["n_read"], short["criterion"]["ads_in_scope"]) == (3, 3)
    assert (short["in_scope_not_read"], short["read_outside_scope"]) == (1, 1)
    whole = answer([("a1", "matches"), ("a2", "does_not_match"), ("a4", "matches")], ["a1", "a4"])
    whole["research_trace"]["list_screening"].update({"first_read": 40, "scope_total": 3})
    whole = b1k_list_row("run", KEYWORD, whole, ADS, set(ADS), {}, {}, {}, with_ads=False)
    wide = {**whole, "criterion": {**whole["criterion"], "ads_in_scope": 50}, "n_read": 45}  # checked by its count only
    got = first_batch([short, whole, wide, {**whole, "screened": False}])
    assert got == {"screened": 3, "scope_at_least_target": 1, "read_target_count": 1, "scope_below_target": 2,
                   "read_whole_scope": 1, "read_on": 1, "outside_scope_in_record": 1, "below_run_scope_total": 1}
    tables = _dashboard_tables()
    assert tables.read_note(short) == ("读取记录 3 篇；首批目标 40 篇，范围内可检索的只有 3 篇，其中 1 篇不在记录里；"
                                       "记录里有 1 篇在本报告算的范围外")
    assert tables.read_note(whole) == "读取记录 3 篇；首批目标 40 篇，范围内可检索的只有 3 篇，都在记录里"


def test_a_changed_adjudication_is_listed_with_both_answers():
    result = answer([("a2", "matches"), ("a1", "matches")], ["a1", "a2"])
    reference = {"a2": {"status": "disputed", "adjudicator": "yes", "adjudicator_quote": "fuel cells"}}
    then = {"a2": {"verdict": "yes", "quote": "Fuel cells everywhere", "accepted": False}}  # its quote was not in the ad
    got = b1k_list_row("run", KEYWORD, result, ADS, set(ADS), {}, reference, {}, with_ads=False, scoring_time=then.get)
    assert (got["final_old_scorer"]["tp"], got["final_old_scorer"]["n_pos"]) == (1, 2)
    assert [(c["record_id"], c["then"]["accepted"], c["reference_adjudicator"]) for c in got["adjudication_changed"]] == [
        ("a2", False, "yes")]


def test_a_list_question_answered_without_screening_scores_zero():
    result = {"status": "answered", "evidence": [{"evidence_id": "E1", "record_id": "a1"}],
              "citations": [{"evidence_id": "E1"}], "research_trace": {"route": "evidence"}}
    got = b1k_list_row("run", KEYWORD, result, ADS, set(ADS), {}, {}, {}, with_ads=False)
    assert (got["screened"], got["n_read"], got["order"]["rr"], got["order"]["ndcg@10"]) == (False, 0, 0.0, 0.0)
    assert got["final"]["tp"] == 1  # what it cited still counts for the final list
    assert (got["funnel"]["read"], got["funnel"]["listed"], got["funnel"]["listed_not_read"]) == (0, 1, 1)


def test_a_frame_question_row_leaves_disputed_and_neutral_ads_unlabelled():
    frames = {"f1": "present gas as a partner of renewables"}
    spec = {"query_id": "F-1", "group": "T2", "query_class": "frame", "question": "Which ads present gas as a partner of renewables?",
            "frame_id": "f1", "scope": {}, "list_truth": {"positive": ["a1"]}}
    labels = {"a1": {"f1": {"verdict": "yes"}}, "a2": {"f1": {"verdict": "no"}}, "a3": {"f1": {"verdict": "unclear"}}}
    reference = {"a1": {"status": "positive"}, "a4": {"status": "disputed", "adjudicator": "yes"}}
    result = answer([("a1", "matches"), ("a4", "matches"), ("a2", "does_not_match"), ("a3", "matches")], ["a1", "a4", "a3"])
    got = b1k_list_row("run", spec, result, ADS, set(ADS), labels, reference, frames, with_ads=True)
    assert got["criterion"]["en"] == "present gas as a partner of renewables"
    assert got["criterion"]["annotation_counts"] == {"yes": 1, "no": 1, "unclear": 1, "missing": 1}
    assert (got["final"]["tp"], got["final"]["fp"], got["final"]["unlabelled_listed"]) == (1, 0, 2)
    assert {r["record_id"]: r["label"] for r in got["ads"]} == {"a1": "relevant", "a4": "disputed", "a2": "not_relevant",
                                                                "a3": "neutral"}
    assert all(r["disagreement"] is None for r in got["ads"])  # the listed disputed and neutral ads are not errors


def test_a_content_question_without_evidence_scores_zero_and_only_a_missed_source_disagrees():
    spec = {"query_id": "C-1", "group": "O", "query_class": "content_single", "question": "What does the hubs story say?",
            "source_record_ids": ["a1"]}
    nothing = b1k_content_row("run", spec, {"status": "insufficient_evidence", "evidence": [], "citations": []}, ADS, True)
    assert (nothing["n_read"], nothing["order"]["rr"], nothing["order"]["hit@1"]) == (0, 0.0, 0.0)
    assert [(r["record_id"], r["disagreement"]) for r in nothing["ads"]] == [("a1", "missed")]
    cited_other = answer([], ["a2", "a1"])  # cites a non-source too: not a wrong citation
    got = b1k_content_row("run", spec, cited_other, ADS, True)
    assert got["order"]["rr"] == 0.5 and all(r["disagreement"] is None for r in got["ads"])


def test_a_title_question_row():
    spec = {"query_id": "N-1", "group": "O", "query_class": "title_lookup", "source_record_ids": ["a1"],
            "question": 'Who published the ad titled "Hydrogen hubs"?',
            "field_truth": {"publisher": "Daily Planet", "sponsor": "Northwind Energy", "date": "2020-01-01"}}
    result = {"status": "answered", "answer": "Publisher: Daily Planet", "research_trace": {"tools": [
        {"tool": "find_records", "arguments": {"title": "Hydrogen  hubs"}, "data_refs": [{"record_id": "a1"}],
         "selected_record": {"record_id": "a1"}}, {"tool": "get_record_metadata"}]},
        "structured_result": {"display_fields": {"publisher": "Daily Planet", "sponsor": "Northwind Energy",
                                                 "publication_date": "2020-01-01T00:00:00"}}}
    got = b1k_title_row("run", spec, result, ADS)
    assert (got["record_found"], got["title_exact"], got["fields_correct"]) == (True, True, True)
    assert got["fields"]["publisher"]["in_answer_text"] and not got["fields"]["sponsor"]["in_answer_text"]
    assert got["order"]["rr"] == 1.0 and got["title_searched"] == ["Hydrogen  hubs"]
    result["structured_result"]["display_fields"]["sponsor"] = "Contoso Oil"
    assert b1k_title_row("run", spec, result, ADS)["fields_correct"] is False
    assert b1k_title_row("run", spec, {"status": "answered", "research_trace": {"tools": []}}, ADS)["order"]["rr"] == 0.0


def test_a_whole_word_has_no_letter_digit_or_underscore_next_to_it():
    """What the page says a whole word (\\b at both ends) means: a letter is any Unicode letter."""
    rule = re.compile(r"\bsolar\b", re.I)
    assert rule.search("Solar, wind") and rule.search("(solar)") and rule.search("solar-powered")
    for text in ("solar_panel", "solaré", "ésolar", "solar2", "solars"):
        assert not rule.search(text), text


def test_the_human_runs_score_an_empty_answer_zero_and_list_a_question_with_only_a_card(tmp_path, monkeypatch):
    val, s3e = tmp_path / "val", tmp_path / "s3e"
    val.mkdir()
    s3e.mkdir()
    docs = {"1": {"record_id": "r1", "title": "Tidal Futures", "sponsor": "Northwind Energy", "retrievable": True},
            "2": {"record_id": "r2", "title": "Quiet Coast", "sponsor": "Contoso Oil", "retrievable": True}}
    (val / "doc_map.json").write_text(json.dumps(docs), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    labels.write_text("doc_id,sentence,lab.a,lab.b,lab.c\n1,We build tidal turbines.,1,0,1\n2,We plant reeds.,0,1.0,0\n",
                      encoding="utf-8")

    def screened(*decisions, query=None):
        return {"status": "answered", "research_trace": {
            "tools": [{"arguments": {"query": query}}] if query else [],
            "list_screening": {"decisions": [{"record_id": rid, "decision": d, "route": route, "triage": {"meets": p}}
                                             for rid, d, route, p in decisions]}}}

    # saved against the judge's probability: the scores use the probability order
    hit = screened(("r2", "does_not_match", "exclude", 0.1), ("r1", "matches", "pass", 0.9))
    for path, value in ((val / "results.json", {}), (val / "triage_answers.json", {}),
                        (s3e / "triage_confirmed_answers.json",
                         {"lab.a": hit, "lab.a.card": screened(query="tidal power ads"), "lab.c.card": screened()}),
                        (s3e / "triage_confirmed_rest_answers.json", {"lab.b": screened()}),  # saved, but empty
                        (tmp_path / "shipped.json", {}),
                        (tmp_path / "depth.json", {"run_date": "2026-01-02", "data_version": "v-test", "questions": [
                            {"label": "lab.a", "question": "Which ads mention tidal power?", "scope_total": 2, "ranked": 2,
                             "ads": [{"record_id": "r2", "rank": 1, "human": False},
                                     {"record_id": "r1", "rank": 2, "human": True}]}]})):
        path.write_text(json.dumps(value), encoding="utf-8")
    for name, value in (("VAL", val), ("S3E", s3e), ("LABELS", labels), ("DEPTH", tmp_path / "depth.json"),
                        ("SHIPPED", tmp_path / "shipped.json")):
        monkeypatch.setattr(report, name, value)
    questions = {"lab.a": "Which ads mention tidal power?", "lab.b": "Which ads mention reeds?",
                 "lab.c": "Which ads mention turbines?"}
    rows, depth, summaries, _, _ = report.human(questions)
    s = summaries["h1028"]
    assert s["order_mean"]["rr"] == {"mean": 0.5, "n": 2} and s["order_mean"]["ndcg@10"] == {"mean": 0.5, "n": 2}
    assert (s["questions"], s["missing"], s["empty_order"]) == (2, ["h1028:lab.c"], 1)
    assert s["coverage"] == pytest.approx(2 / 3)
    by_label = {r["label"]: r for r in rows if r["run"] == "h1028"}
    assert set(by_label) == {"lab.a", "lab.b"}  # a card alone is not an answer
    assert by_label["lab.a"]["searches"] == ["tidal power ads"]  # it searched while drafting the card
    assert by_label["lab.b"]["final"]["recall"] == 0.0
    # the judge's re-sort gives no read-order stages: the run read every coded ad it was given
    assert by_label["lab.a"]["funnel"] == {"relevant": 1, "read": 1, "listed": 1, "read_not_listed": 0, "listed_not_read": 0}
    assert s["funnel"]["relevant"] == 2 and s["funnel"]["rates"]["listed"] == s["final_micro"]["recall"]
    assert by_label["lab.a"]["judge_order"] == {"inversions": 1, "across_labels": 1, "without_probability": 0,
                                                "labels_moved": True}
    # each ad keeps both places: the one it is scored at and the one it was saved at
    assert [(a["record_id"], a["position"], a["saved_position"]) for a in by_label["lab.a"]["ads"]] == [
        ("r1", 1, 2), ("r2", 2, 1)]
    assert (summaries["depth"]["coded"], summaries["depth"]["flag_mismatch"], depth[0]["condensed"]["rr"]) == (2, 0, 0.5)
    (s3e / "triage_confirmed_rest_answers.json").write_text(json.dumps({"lab.a": hit}), encoding="utf-8")
    with pytest.raises(AssertionError):  # the two blocks never answer the same question
        report.human_answers()


def _dashboard_tables():
    path = Path(report.ROOT) / "reports/rag_metrics_20261029/dashboard_tables.py"
    if not path.exists():
        # The published report folder is kept out of git until the user decides its sharing scope
        # (2026-11-10); these checks run only where the local copy exists.
        pytest.skip("reports/rag_metrics_20261029 is a local, unpublished report")
    spec = importlib.util.spec_from_file_location("dashboard_tables_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("route, status, words", [
    ("clarify", "insufficient_evidence", "否：反问了用户，"),
    ("evidence", "answered", "否：直接给了证据回答，"),
    (None, "service_unavailable", "否：回答失败（服务不可用），"),
    (None, "answered", "否：路线没有记录（已回答），"),  # only a recorded evidence route is called an evidence answer
])
def test_the_dashboard_says_why_a_list_question_has_no_read_order(route, status, words):
    row = {"group": "T1", "run": "run", "query_id": "T-1", "question": "Which ads mention hydrogen?",
           "criterion": {"scope_words": "全部可检索的原生广告", "ads_in_scope": 4}, "searches": [], "n_relevant": 2,
           "n_listed": 0, "n_read": 0, "screened": False, "route": route, "status": status,
           "final": set_metrics(set(), {"a1", "a4"}), "order": order_metrics([], {"a1", "a4"}, (10, 120)),
           "funnel": read_funnel([], {"a1", "a4"}, set())}
    got = _dashboard_tables().list_common(row)
    assert got["screened"].startswith(words) and got["screened"].endswith("筛查读取记录为空，相关的都记作不在记录里，排序记 0")
    assert (got["read_note"], got["fread_n"]) == ("没走名单筛查，筛查读取记录为空", 0)


def test_the_dashboard_funnel_names_each_measured_stage_and_where_ads_dropped_out():
    tables = _dashboard_tables()
    counts = {"relevant": 10, "first_10": 3, "first_40": 7, "read": 9, "listed": 8, "read_not_listed": 2,
              "listed_not_read": 1}
    got = tables.funnel_fields(counts, tables.B1K_STAGES, "basis", "not measured")
    assert (got["f10"], got["f40"], got["fread"], got["flisted"], got["f120"]) == (0.3, 0.7, 0.9, 0.8, None)
    assert (got["f120_n"], got["f120_name"], got["f40_name"]) == (None, None, "读取记录前 40 篇")
    # one relevant ad is not in the read record, two are in it but not listed, one was listed by another route
    assert (got["not_read"], got["read_not_listed"], got["listed_not_read"]) == (1, 2, 1)
    assert got["f_text"].startswith("相关 10 → 读取记录前 10 篇 3 → 读取记录前 40 篇 7")
    depth = tables.funnel_fields({"relevant": 4, "first_10": 1, "first_40": 2, "first_120": 4}, tables.DEPTH_STAGES, "b", "m")
    assert (depth["f120"], depth["fread"], depth["not_read"], depth["listed_not_read"]) == (1.0, None, None, None)
    assert tables.funnel_text({**counts, "relevant": 0}) == "没有相关广告"
    assert tables.funnel_text(counts).endswith("在记录里但没列入 2 篇，列入但不在读取记录里 1 篇")
    row = {"screened": True, "n_read": 52, "first_read": 40, "criterion": {"ads_in_scope": 113}, "in_scope_not_read": 61}
    assert tables.read_note(row) == "读取记录 52 篇；首批目标 40 篇，比首批目标多 12 篇"
    assert tables.read_note({**row, "n_read": 30}).endswith("记录不够首批目标的篇数")


def _fictional_metrics():
    """The smallest metrics.json the dashboard's headline and runs tables read, from fictional rows: one B1K run (also
    standing for the headline pair), the three human runs and the 10-29 ranking."""
    keyword = answer([("a2", "matches"), ("a1", "matches"), ("a4", "does_not_match")], ["a1", "a2"])
    frame_spec = {"query_id": "F-1", "group": "T2", "query_class": "frame", "question": "Which ads present gas as a partner?",
                  "frame_id": "f1", "scope": {}, "list_truth": {"positive": ["a1"]}}
    frame = answer([("a1", "matches"), ("a2", "does_not_match")], ["a1"])
    for result in (keyword, frame):
        result["research_trace"]["list_screening"].update({"first_read": 40, "scope_total": 4})
    content_spec = {"query_id": "C-1", "group": "O", "query_class": "content_single", "question": "What does the hubs story say?",
                    "source_record_ids": ["a1"]}
    title_spec = {"query_id": "N-1", "group": "O", "query_class": "title_lookup", "source_record_ids": ["a1"],
                  "question": 'Who published the ad titled "Hydrogen hubs"?', "field_truth": {"publisher": "Daily Planet"}}
    rows = {"keyword": ([b1k_list_row("wB1", KEYWORD, keyword, ADS, set(ADS), {}, {}, {}, with_ads=False)], report.LIST_KS),
            "frame": ([b1k_list_row("wB1", frame_spec, frame, ADS, set(ADS), {"a1": {"f1": {"verdict": "yes"}}}, {},
                                    {"f1": "present gas as a partner"}, with_ads=False)], report.LIST_KS),
            "content": ([b1k_content_row("wB1", content_spec, answer([], ["a1"]), ADS, False)], report.CONTENT_KS),
            "title": ([b1k_title_row("wB1", title_spec, {"status": "answered", "research_trace": {"tools": []}}, ADS)],
                      report.CONTENT_KS)}
    b1k = {kind: {name: {**summarize(items, ks), **report.kind_extras(kind, items)} for name in ("wB1", "headline")}
           for kind, (items, ks) in rows.items()}
    questions, human = [], {}
    for run in ("h1023", "h1024", "h1028"):
        order, relevant, listed = ["a1", "a2", "a3"], {"a1", "a3"}, {"a1"}
        questions.append(row(set_metrics(listed, relevant), 2, 1, order_metrics(order, relevant, report.HUMAN_KS), run=run,
                             n_read=3, ads=[{}] * 3, funnel=read_funnel(order, relevant, listed, ks=())))
        s = summarize(questions[-1:], report.HUMAN_KS)
        s.update({"screening_policy": {"list-screening-v19": 1}, "data_version": {"e7303ff3c0ffee00": 1}})
        if run != "h1023":
            s["judge_order"] = {"inversions": 0, "across_labels": 0, "without_probability": 0, "labels_moved": 0}
        human[run] = s
    human["depth"] = {"found": {"10": 1, "40": 2, "120": 3}, "relevant": 4, "questions": 2, "coded": 30, "not_ranked": 0,
                      "flag_mismatch": 0, "pooled_full_recall": {"r@10": 0.25, "r@40": 0.5, "r@120": 0.75},
                      "full_rank_mean": {k: {"mean": v} for k, v in (("rr", 0.4), ("ndcg@10", 0.2), ("ndcg@120", 0.3))},
                      "condensed_mean": {k: {"mean": v} for k, v in (("rr", 0.8), ("ndcg@10", 0.6), ("ndcg@15", 0.7))}}
    run = {"run": "wB1", "question_set": "new6", "from_utc": "2026-10-19T07:53:00+00:00", "to_utc": "2026-10-19T08:29:00+00:00",
           "screening_policy": {"list-screening-v17": 4}, "data_version": {"216d0085c0ffee00": 4}, "answers": 4,
           "not_answered": {}, "order_check": {"matched_with_rank": 1, "rank_equals_position": 1}}
    return {"human": {"summary": human, "questions": questions, "depth": [{"ranked": 50}]},
            "b1k": {"summary": b1k, "runs": [run]},
            "provenance": {"human": {"articles": 15, "depth": {"data_version": "e7303ff3c0ffee00"}}}}


def test_the_headline_keeps_list_mrr_out_and_the_runs_table_keeps_it_for_the_supplementary_table():
    tables, m = _dashboard_tables(), _fictional_metrics()
    head = {r["key"]: r for r in tables.headline(m)}
    lists = ("human_1024", "human_1028", "human_1023", "human_depth", "keyword", "frame")
    assert all(head[k]["kind"] == "list" and head[k]["mrr"] is None for k in lists)
    assert head["content"]["mrr"] == 1.0 and head["title"]["mrr"] == 0.0  # content and title keep their MRR
    # the 10-29 stages are the full-rank search depths; it has no read record or list, so those stay empty, never 0
    depth = head["human_depth"]
    assert (depth["f10_n"], depth["f40_n"], depth["f120_n"], depth["f40"]) == (1, 2, 3, 0.5)
    assert (depth["fread"], depth["flisted"], depth["not_read"], depth["listed_not_read"]) == (None, None, None, None)
    assert (depth["f_short"], depth["ndcg10"], depth["order_basis"]) == ("全库检索名次", 0.6, tables.CONDENSED)
    assert (head["keyword"]["f_short"], head["human_1023"]["f_short"]) == ("筛查读取记录", "判定记录（每题 15 篇）")
    assert head["human_1023"]["f10"] is None and head["human_1023"]["fread_n"] == 2
    assert head["keyword"]["f_basis"].startswith("已保存的筛查读取记录")
    runs = {r["key"]: r for r in tables.runs_table(m)}
    extra = [r for r in runs.values() if r["kind"] in ("keyword", "frame", "human", "depth")]
    assert len(extra) == 9 and all(r["mrr"] is not None and r["k_note"] for r in extra)
    assert runs["keyword|wB1"]["ndcg120"] is not None and runs["human|h1023"]["ndcg15"] is not None
    assert (runs["depth|full"]["ndcg120"], runs["depth|condensed"]["ndcg15"]) == (0.3, 0.7)
    assert runs["keyword|wB1"]["first_read"] == "40 篇；1/1 范围内全在记录里"
    assert runs["frame|wB1"]["first_read"] == "40 篇；0/1 范围内全在记录里"  # a3 and a4 are in scope, not in the record
