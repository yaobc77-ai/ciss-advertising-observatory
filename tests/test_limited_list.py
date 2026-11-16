"""C26 (user 2026-11-10): a list on the web reads in rank order until LIMITED_LIST matches, then offers
the full list with a button at the end of the answer.

Fictional questions, ads and posts only (the golden fixtures of test_list_golden and synthetic
passages); every model call is mocked. The screener tests drive list_screening.screen with a fake
judge; the service tests go through Service.answer with the golden list fixture; the web tests
render the answer and call the button's callback with a fake service.
"""
import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_list_criterion_mode import roles, service_for
from test_list_golden import JOBS

from observatory import list_screening
from observatory.config import Settings
from observatory.criterion_confirmation import pending_confirmation
from observatory.list_screening import (
    FULL_LIST_BUTTON,
    LIMITED_LIST,
    MatchQuota,
    limited_head,
    limited_order,
)
from observatory.models import Filters

NATIVE = Filters(dataset="native")


# --- The screener ---------------------------------------------------------------------------------------------

def _passages(count):
    return [SimpleNamespace(record_id=f"ad-{n:03d}", evidence_id=f"ev-{n:03d}", text=f"Ad {n} text") for n in range(count)]


def _judge(matching, read):
    lock = threading.Lock()

    def judge(rag, question, batch, first, phrases, visitor, stage):
        time.sleep(0.01)
        with lock:
            read.extend(group[0].record_id for group in batch)
        return ([{"record_id": group[0].record_id,
                  "decision": "matches" if group[0].record_id in matching else "does_not_match"} for group in batch],
                Decimal("0.001"))
    return judge


def _screen(monkeypatch, matching, count, quota=None, limit=40):
    read = []
    monkeypatch.setattr(list_screening, "_judge", _judge(matching, read))
    rag = SimpleNamespace(settings=Settings(screen_workers=16))
    results, _ = list_screening.screen(rag, "Which ads mention kites?", _passages(count), "visitor",
                                       limit=limit, widen_to=count, verify=False, quota=quota)
    return results, read


def test_reading_stops_after_the_wave_that_reaches_the_quota(monkeypatch):
    matching = {f"ad-{n:03d}" for n in range(0, 120, 2)}  # every other ad matches: 20 in the first 40
    results, read = _screen(monkeypatch, matching, 120, quota=MatchQuota(LIMITED_LIST))
    assert len(read) == 40 and sorted(read) == [f"ad-{n:03d}" for n in range(40)]  # the first wave only
    assert sum(item["decision"] == "matches" for item in results) == 20


def test_a_quota_reached_in_a_later_wave_keeps_that_wave_whole(monkeypatch):
    matching = {f"ad-{n:03d}" for n in (*range(0, 40, 4), *range(40, 120))}  # 10 in the first wave, then all
    results, read = _screen(monkeypatch, matching, 120, quota=MatchQuota(LIMITED_LIST))
    assert len(read) == 40 + 4 * list_screening.WIDEN_WAVE  # one widening wave of WIDEN_WAVE batches of four
    assert sum(item["decision"] == "matches" for item in results) == 10 + 32  # the wave's matches all kept


def test_without_enough_matches_reading_continues_past_the_widening_window(monkeypatch):
    # One match early and one at the very end: a full list stops widening after WIDEN_WINDOW ads
    # without a match; a limited list keeps reading every candidate until it has its matches.
    matching = {"ad-001", "ad-118"}
    full, full_read = _screen(monkeypatch, matching, 120)
    limited, limited_read = _screen(monkeypatch, matching, 120, quota=MatchQuota(LIMITED_LIST))
    assert len(full_read) < 120 and "ad-118" not in full_read
    assert len(limited_read) == 120 and [item["record_id"] for item in limited if item["decision"] == "matches"] == ["ad-001", "ad-118"]


def test_the_full_list_asked_from_a_quick_one_reads_past_the_widening_window(monkeypatch):
    matching = {"ad-001", "ad-118"}
    read = []
    monkeypatch.setattr(list_screening, "_judge", _judge(matching, read))
    rag = SimpleNamespace(settings=Settings(screen_workers=16))
    results, _ = list_screening.screen(rag, "Which ads mention kites?", _passages(120), "visitor",
                                       limit=40, widen_to=120, verify=False, narrow=False)
    assert len(read) == 120 and [r["record_id"] for r in results if r["decision"] == "matches"] == ["ad-001", "ad-118"]


def test_without_a_quota_screening_is_unchanged(monkeypatch):
    matching = {f"ad-{n:03d}" for n in range(0, 120, 2)}
    results, read = _screen(monkeypatch, matching, 120)
    assert len(read) == 120 and sum(item["decision"] == "matches" for item in results) == 60


def test_the_quota_is_shared_by_the_collections_of_one_list(monkeypatch):
    quota = MatchQuota(LIMITED_LIST)
    quota.add(18)  # the other collection already found 18
    matching = {f"ad-{n:03d}" for n in range(0, 120, 2)}
    _, read = _screen(monkeypatch, matching, 120, quota=quota)
    assert len(read) == 40 and quota.found == 18 + 20 and quota.reached()


def test_a_collection_that_starts_after_the_quota_is_full_reads_nothing(monkeypatch):
    quota = MatchQuota(LIMITED_LIST)
    quota.add(LIMITED_LIST)
    results, read = _screen(monkeypatch, {"ad-001"}, 120, quota=quota)
    assert read == [] and results == []


def test_the_quota_counts_from_several_threads():
    quota = MatchQuota(1000)
    threads = [threading.Thread(target=lambda: [quota.add(1) for _ in range(100)]) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert quota.found == 800 and not quota.reached()


# --- What is listed and the opening line ----------------------------------------------------------------------

def test_one_collection_keeps_the_first_matches_by_rank():
    matched = [{"record_id": f"ad-{n}"} for n in range(25)]
    assert [item["record_id"] for item in limited_order(matched, both=False)] == [f"ad-{n}" for n in range(20)]


def test_two_collections_keep_a_fair_share_of_each():
    matched = [*({"record_id": f"n{n}", "dataset": "native"} for n in range(15)),
               *({"record_id": f"s{n}", "dataset": "social"} for n in range(15))]
    kept = limited_order(matched, both=True)
    assert len(kept) == 20 and sum(item["dataset"] == "native" for item in kept) == 10


def test_the_opening_line_says_what_was_read_and_that_it_is_not_the_full_list():
    reached = limited_head(False, 20, {"native": {"scope_total": 275, "examined": 72}}, True)
    assert reached.startswith("This is a quick list: the 72 ads closest to the question were read")
    assert "first 20 matches" in reached and "not the full list" in reached and FULL_LIST_BUTTON in reached
    exhausted = limited_head(False, 3, {"native": {"scope_total": 275, "examined": 120}}, False)
    assert "all 120 ads the search picked" in exhausted and "3 matches were found" in exhausted
    both = limited_head(True, 20, {"native": {"scope_total": 275, "examined": 40},
                                   "social": {"scope_total": 36182, "examined": 72}}, True)
    assert "原生广告 40 篇、公司社交帖子 72 条" in both and "不是完整名单" in both and FULL_LIST_BUTTON in both
    nothing = limited_head(False, 0, {"native": {"scope_total": 275, "examined": 120}}, False)
    assert "0 matches were found" in nothing and "another way" in nothing


# --- The service --------------------------------------------------------------------------------------------

def test_a_limited_list_skips_the_triage_and_the_card_and_says_it_is_quick(monkeypatch):
    service, _, calls, _ = service_for("native_triage_large", monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", criterion_confirmation="ask", list_depth="limited")
    assert result.status == "answered" and not pending_confirmation(result)  # no card for a quick list
    assert calls.by_dataset["native"]["judge"] == []  # no Decisions triage
    assert "criterion" in roles(calls)  # still drafted, for the question-is-about-the-texts check (C24)
    trace = result.research_trace["list_screening"]
    assert trace["list_depth"] == "limited" and trace["full_list_available"] is True
    assert trace["criterion_source"] == "none" and trace["screening_basis"] == "question" and trace["criterion_draft"]
    assert trace["limited"]["wanted"] == LIMITED_LIST and trace["limited"]["reached"] is False
    assert "criterion" not in trace  # the draft judged nothing
    assert result.structured_result["full_list_available"] is True
    assert result.answer.startswith("This is a quick list: all ") and "Your selection has 6 ads" in result.answer
    assert "not confirmed by a researcher" not in result.answer  # the draft was not used to judge


def _screened(count, matches):
    return [{"record_id": f"ad-{n}", "decision": "matches" if n < matches else "does_not_match"} for n in range(count)]


def _listed(results, scope_total):
    from observatory.list_screening import list_answer
    answer = list_answer("Which ads mention kites?", [], [], scope_total=scope_total)
    return answer.model_copy(update={"structured_result": {**answer.structured_result,
                                                           "matches": sum(r["decision"] == "matches" for r in results)}})


def test_a_scope_read_whole_with_nothing_dropped_is_the_full_list_and_offers_no_button():
    from observatory.service import Service
    results = _screened(3, 2)
    result = _listed(results, 3)
    before = result.answer
    quota = MatchQuota(LIMITED_LIST)
    quota.add(2)
    Service._limit_list("Which ads mention kites?", result, results, {"native": 3}, quota, 0)
    assert result.structured_result["full_list_available"] is False and result.answer == before
    assert result.research_trace["list_screening"]["list_depth"] == "limited"


def test_a_scope_read_whole_but_cut_at_the_limit_still_offers_the_full_list():
    from observatory.service import Service
    results = _screened(30, 25)
    result = _listed(results, 30)
    quota = MatchQuota(LIMITED_LIST)
    quota.add(25)
    Service._limit_list("Which ads mention kites?", result, results, {"native": 30}, quota, 5)
    assert result.structured_result["full_list_available"] is True
    assert result.answer.startswith("This is a quick list: the 30 ads closest")


def test_a_list_cut_by_the_spending_cap_keeps_its_line_and_says_it_is_not_the_full_list():
    from observatory.service import Service
    results = [*_screened(4, 1), {"record_id": "ad-9", "decision": "unclear", "reason": "question_cap"}]
    result = _listed(results, 50)
    head = result.answer.partition("\n\n")[0]
    Service._limit_list("Which ads mention kites?", result, results, {"native": 50}, MatchQuota(LIMITED_LIST), 0)
    assert result.answer.partition("\n\n")[0] == head + " This is not the full list."
    assert result.structured_result["full_list_available"] is True


def test_matches_beyond_the_limit_are_found_but_not_listed(monkeypatch):
    monkeypatch.setattr(list_screening, "LIMITED_LIST", 1)
    import observatory.service as service_module
    monkeypatch.setattr(service_module, "LIMITED_LIST", 1)
    service, _, _, _ = service_for("native_triage_large", monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", list_depth="limited")
    trace = result.research_trace["list_screening"]
    assert trace["limited"]["beyond_limit"] >= 1 and trace["limited"]["listed"] == 1 == trace["matches"]
    assert [d["route"] for d in trace["decisions"] if d.get("route") == "beyond_limit"]
    assert len(result.citations) >= 1 and trace["full_list_available"] is True


def test_two_collections_share_one_limit_and_one_opening_line(monkeypatch):
    service, _, _, _ = service_for("both_screen", monkeypatch)
    result = service.answer(JOBS, Filters(dataset="all"), "offline", list_depth="limited")
    trace = result.research_trace["list_screening"]
    assert trace["list_depth"] == "limited" and trace["limited"]["wanted"] == LIMITED_LIST


def test_the_default_and_full_depth_are_the_list_as_before(monkeypatch):
    first, _, first_calls, _ = service_for("native_triage", monkeypatch)
    default = first.answer(JOBS, NATIVE, "offline")
    second, _, second_calls, _ = service_for("native_triage", monkeypatch)
    full = second.answer(JOBS, NATIVE, "offline", list_depth="full")
    assert "list_depth" not in default.research_trace["list_screening"]
    assert default.answer == full.answer and first_calls.by_dataset["native"]["judge"]  # the triage ran
    assert len(first_calls.by_dataset["native"]["judge"]) == len(second_calls.by_dataset["native"]["judge"])
    card = service_for("native_triage", monkeypatch)[0].answer(JOBS, NATIVE, "offline", criterion_confirmation="ask",
                                                              list_depth="full")
    assert pending_confirmation(card)  # the full list keeps the card


def test_the_expanded_depth_screens_every_candidate_without_the_stop_rule_or_a_quota(monkeypatch):
    import observatory.service as service_module
    seen = []
    original = service_module.screen_list

    def spy(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(service_module, "screen_list", spy)
    service, _, _, _ = service_for("native_screen", monkeypatch)
    result = service.answer(JOBS, NATIVE, "offline", list_depth="expanded")
    assert result.status == "answered" and seen
    assert seen[0]["narrow"] is False and "quota" not in seen[0] and seen[0]["widen_to"] >= 120
    assert "list_depth" not in result.research_trace["list_screening"]  # a full list, said as before
    seen.clear()
    service_for("native_screen", monkeypatch)[0].answer(JOBS, NATIVE, "offline", list_depth="full")
    assert "narrow" not in seen[0]  # an ordinary full list keeps its stop rule


def test_an_exact_wording_list_is_complete_and_not_limited(monkeypatch):
    service, scenario, _, _ = service_for("native_literal", monkeypatch)
    result = service.answer(scenario.question, NATIVE, "offline", list_depth="limited")
    assert "list_depth" not in result.research_trace["list_screening"]
    assert not result.structured_result.get("full_list_available")


def test_an_unknown_depth_is_refused():
    with pytest.raises(ValueError):
        service_for.__globals__["Service"](Settings()).answer("Which ads mention kites?", NATIVE, "v", list_depth="some")


def test_the_web_setting_defaults_to_limited_and_reads_the_environment(monkeypatch):
    assert Settings().list_depth == "limited"
    monkeypatch.setenv("OBS_LIST_DEPTH", "full")
    assert Settings.from_env().list_depth == "full"
    monkeypatch.setenv("OBS_LIST_DEPTH", "anything")
    assert Settings.from_env().list_depth == "limited"


# --- The web: the button under a quick list, and its click ----------------------------------------------------

def _quick(answer, full_list_available=True):
    from observatory.models import Answer
    return Answer(status="answered", answer_mode="rag", answer=answer.answer, evidence=answer.evidence,
                  citations=answer.citations,
                  structured_result={"kind": "ai_screened_list", "list_depth": "limited",
                                     "full_list_available": full_list_available, "matches": 1},
                  research_trace={"list_screening": {"list_depth": "limited", "question": "q"}})


def _web(full_list_available=True, list_depth=None):
    from test_criterion_ui import CardService

    class QuickService(CardService):
        def answer(self, question, filters, visitor, progress=None, **options):
            self.options.append(options)
            plain = super(CardService, self).answer(question, filters, visitor)
            return _quick(plain, full_list_available) if options.get("list_depth") == "limited" else plain

    from observatory.app import create_app
    service = QuickService()
    service.pending = None
    settings = SimpleNamespace(show_source_links=True, cookie_secret="test-cookie-secret", monthly_budget_usd=100,
                               criterion_confirmation="ask", **({"list_depth": list_depth} if list_depth else {}))
    app = create_app(service, settings)
    return app, app.server.test_client(), service


def _offers(children):
    from test_app import component_tree
    return [node for node in component_tree(children)
            if isinstance(node["props"].get("id"), dict) and node["props"]["id"].get("type") in ("full-list", "full-list-data")]


def test_a_quick_list_ends_with_the_full_list_button_carrying_its_question_and_scope():
    from test_app import callback, research_values
    app, client, service = _web()
    response = callback(app, client, "research-results.children", research_values() | {"answer-paid.n_clicks": 1},
                        "answer-paid.n_clicks")
    assert service.options[-1]["list_depth"] == "limited" and service.options[-1]["criterion_confirmation"] == "ask"
    offers = _offers(response["research-results"]["children"])
    button = next(node for node in offers if node["props"]["id"]["type"] == "full-list")
    store = next(node for node in offers if node["props"]["id"]["type"] == "full-list-data")
    assert button["props"]["children"] == FULL_LIST_BUTTON
    assert store["props"]["data"]["question"] == "carbon capture" and store["props"]["data"]["filters"]["dataset"] == "native"


def test_a_complete_quick_list_and_the_full_setting_show_no_button():
    from test_app import callback, research_values
    app, client, service = _web(full_list_available=False)
    response = callback(app, client, "research-results.children", research_values() | {"answer-paid.n_clicks": 1},
                        "answer-paid.n_clicks")
    assert _offers(response["research-results"]["children"]) == []
    app, client, service = _web(list_depth="full")
    response = callback(app, client, "research-results.children", research_values() | {"answer-paid.n_clicks": 1},
                        "answer-paid.n_clicks")
    assert service.options[-1]["list_depth"] == "full" and _offers(response["research-results"]["children"]) == []


def test_the_button_asks_again_at_full_depth_in_the_lists_own_scope():
    from test_criterion_ui import post_pattern_callback

    from observatory.criterion_ui import question_key
    app, client, service = _web()
    submission = {"question": "Which ads mention kites?", "filters": {"dataset": "social", "platforms": ["Facebook"]}}
    response = post_pattern_callback(app, client, "full-list", {"q": question_key(submission["question"]), "f": "full"},
                                     {"full-list.n_clicks": 1, "full-list-data.data": submission,
                                      "research-progress-token.data": "progress-token-progress-token-1234",
                                      "page-location.pathname": "/query"}, ({}, "n_clicks"))
    assert service.options[-1] == {"criterion_confirmation": "ask", "list_depth": "expanded", "address": "127.0.0.1"}
    question, filters, _ = service.answer_calls[-1]
    assert question == "Which ads mention kites?" and filters.dataset == "social" and filters.platforms == ["Facebook"]
    assert response["research-submission"]["data"]["question"] == "Which ads mention kites?"
    assert "proposes a carbon capture project" in str(response["research-results"]["children"])
    assert _offers(response["research-results"]["children"]) == []  # the full list offers no button


def test_the_full_list_button_owns_its_busy_controls():
    app, client, _ = _web()
    for spec in client.get("/_dash-dependencies").json:
        if "full-list" in str(spec.get("inputs", [])) and "full-list-data" in str(spec.get("state", [])):
            running = set(spec["running"]["running"])
            assert {"full-list-progress.style", "full-list-progress-poll.disabled"} <= running
            assert not {"answer-paid.disabled", "research-progress.style", "criterion-progress.style"} & running
            break
    else:
        raise AssertionError("no full-list callback")


def test_a_compound_answer_with_a_quick_part_gets_one_button_at_its_end():
    from observatory.app import _render_answer_result
    part = {"status": "answered", "answer_mode": "rag", "answer": "This is a quick list.", "evidence": [], "citations": [],
            "structured_result": {"kind": "ai_screened_list", "full_list_available": True}, "research_trace": {}}
    composite = {"status": "answered", "answer_mode": "tools", "answer": "",
                 "structured_result": {"kind": "composite", "complete": True,
                                       "parts": [{"question_part": "Which ads mention kites?", "answer": part}]},
                 "list_submission": {"question": "Which ads mention kites, and which posts?", "filters": {"dataset": "all"}},
                 "research_trace": {}}
    cards = _render_answer_result(composite, True, None)
    import json
    offers = _offers(json.loads(json.dumps([card for card in cards if card is not None],
                                           default=lambda item: item.to_plotly_json())))
    stores = [node for node in offers if node["props"]["id"]["type"] == "full-list-data"]
    assert len(stores) == 1 and stores[0]["props"]["data"]["question"] == "Which ads mention kites, and which posts?"
    assert cards.index(next(c for c in cards if c is not None and "full-list-offer" in str(getattr(c, "className", ""))))         >= len(cards) - 2  # at the end, before the research steps
