"""X relation reads (mentions, hashtags, replies to collected posts) and company profiles, with fictional entities."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_pipeline_integration import db as db  # noqa: F401  (integration fixture)
from test_research_tools import make_catalog

from observatory.models import Filters, ImportBatch, RecordInput
from observatory.research_tools import RELATION_FILTERS


def relation_catalog(enabled, base=None):
    catalog, fake = make_catalog(base or Filters(dataset="social"))
    catalog.service.settings = replace(catalog.service.settings, relation_selection_enabled=enabled)
    return catalog, fake


def filter_properties(definition):
    return set(definition["parameters"]["$defs"]["FiltersRequest"]["properties"])


def test_relation_reads_are_hidden_from_the_planner_until_enabled():
    hidden, _ = relation_catalog(False)
    names = {item["name"] for item in hidden.definitions()}
    assert "select_by_company_profile" not in names
    search = next(item for item in hidden.definitions() if item["name"] == "search_records")
    assert not filter_properties(search) & set(RELATION_FILTERS)
    assert hidden.call("select_by_company_profile", {"organization_type": "State-owned Entity"})["tool"] == "unknown"
    shown, _ = relation_catalog(True)
    assert "select_by_company_profile" in {item["name"] for item in shown.definitions()}
    search = next(item for item in shown.definitions() if item["name"] == "search_records")
    assert set(RELATION_FILTERS) <= filter_properties(search)


def test_a_relation_filter_becomes_the_matching_post_ids_inside_the_active_scope():
    catalog, fake = relation_catalog(True, Filters(dataset="all", date_from=None))
    fake.relation_record_ids = Mock(return_value=(["x1", "x2"], 2))
    from observatory.research_tools import FiltersRequest

    scoped = catalog.narrow(FiltersRequest(hashtags=["#KitePower"], mentions=["@HarborFund"]))
    assert scoped.dataset == "social" and scoped.record_ids == ["x1", "x2"]
    used = fake.relation_record_ids.call_args
    assert used.args[0].dataset == "social"
    assert used.kwargs == {"hashtags": ["#KitePower"], "mentions": ["@HarborFund"], "limit": 600}
    assert catalog.relation_selections[0]["matched_posts"] == 2
    fake.relation_record_ids = Mock(return_value=([], 0))
    assert catalog.narrow(FiltersRequest(references=["quoted"])).record_ids == ["no-relation-match"]


def test_relation_filters_are_refused_when_disabled_or_outside_social():
    from observatory.research_tools import FiltersRequest, ScopeConflict

    disabled, _ = relation_catalog(False)
    with pytest.raises(ScopeConflict, match="not available"):
        disabled.narrow(FiltersRequest(hashtags=["kitepower"]))
    native, _ = relation_catalog(True, Filters(dataset="native"))
    with pytest.raises(ScopeConflict):
        native.narrow(FiltersRequest(hashtags=["kitepower"]))


def test_company_profile_lookup_returns_social_names_and_registry_native_spellings(monkeypatch):
    catalog, fake = relation_catalog(True, Filters(dataset="all"))
    fake.company_profiles = Mock(return_value=[
        {"sponsor": "Tidal Co", "organization_type": "State-owned Entity", "region": "Atlantis", "commodity": "Wind", "posts": 4},
        {"sponsor": "Gale Union", "organization_type": "State-owned Entity", "region": "Atlantis", "commodity": "Wind", "posts": 1}])
    tidal = SimpleNamespace(id="org:tidal", review_status="ai_proposed", source_values={"native.sponsor": ["tidal co"]})
    monkeypatch.setattr("observatory.research_tools.entity_registry",
                        lambda: SimpleNamespace(for_source=lambda d, f, v: tidal if v == "Tidal Co" else None))
    result = catalog.call("select_by_company_profile", {"organization_type": "State-owned Entity"})
    assert result["status"] == "ok"
    assert result["sponsors"] == {"social": ["Tidal Co", "Gale Union"], "native": ["tidal co"]}
    assert fake.company_profiles.call_args.kwargs["organization_type"] == "State-owned Entity"
    assert "unverified" in result["basis"]
    assert catalog.call("select_by_company_profile", {})["status"] == "invalid_request"




@pytest.mark.integration
def test_database_relation_reads_cover_string_and_list_fields_and_collected_references(db):  # noqa: F811
    def post(record_id, status, **row):
        return RecordInput(record_id=record_id, dataset="social", platform="Twitter", account="Tidal Co",
                           sponsor=row.pop("sponsor", "Tidal Co"), body="Kites lift the harbor.",
                           url=f"https://twitter.com/Tidal_Co/status/{status}", raw={"source_row": row})
    db.import_batch(ImportBatch(records=[
        post("x1", "5001", engagement={"username_mentions": "HarborFund"}, **{"post.hashtags_identified": ["#KitePower"]}),
        post("x2", "5002", engagement={"username_mentions": ["kitelab", "harborfund"], "referenced_tweet_ids": "5001"},
             post={"reference_tweet_type": "quoted"}),
        post("x3", "5003", engagement={"referenced_tweet_ids": "9999"}, post={"reference_tweet_type": "replied_to"},
             parent_entity_info={"type": "State-owned Entity", "region": "Atlantis", "commodity": "Coal, Wind"},
             sponsor="Gale Union"),
    ]))
    social = Filters(dataset="social")
    assert sorted(db.relation_record_ids(social, mentions=["@HARBORFUND"])[0]) == ["x1", "x2"]
    assert db.relation_record_ids(social, hashtags=["kitepower"]) == (["x1"], 1)
    # Only the quote of a collected post counts; the reply to an uncollected post does not.
    assert db.relation_record_ids(social, references=["quoted", "replied_to"]) == (["x2"], 1)
    assert db.relation_record_ids(social, mentions=["nobody"]) == ([], 0)
    profiles = db.company_profiles(social, organization_type="state-owned entity", commodity="wind")
    assert [(row["sponsor"], row["posts"]) for row in profiles] == [("Gale Union", 1)]
    assert db.company_profiles(social, region="Elsewhere") == []


def social_passage(record, text, account="Tidal Co Harbor"):
    from datetime import date

    from observatory.models import Evidence
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="social",
                    title=f"Twitter post · {record}", publisher="", sponsor="Tidal Co", account=account,
                    published_at=date(2022, 3, 1), text=text, start=0, end=len(text))


def test_a_social_post_list_is_screened_like_an_ad_list():
    from test_list_screening import screening_service

    from observatory.list_screening import Decision
    service, parse, _ = screening_service([Decision(ref="A1", decision="matches", passage_id="A1.1",
                                                    quote="Tidal kites will supply cheap power to the harbor.")])
    result = service._answer_evidence("Which posts mention tidal kites?", Filters(dataset="social"), "offline", audit=False)
    assert parse.call_count >= 1 and result.structured_result["kind"] == "ai_screened_list"


def test_a_relation_only_list_names_every_selected_post_without_a_model_call():
    from test_list_screening import screening_service

    service, parse, db = screening_service([])
    posts = [social_passage("p1", "Kites lift the harbor. More soon."), social_passage("p2", "Quiet kites at dawn!")]
    db.record_passages = Mock(return_value=posts)
    listing = {"selections": [{"relations": {"hashtags": ["#KitePower"]}, "matched_posts": 3}], "list_all": True}
    result = service._answer_evidence("Which posts use #KitePower?", Filters(dataset="social", record_ids=["p1", "p2", "p3"]),
                                      "offline", audit=False, relation_listing=listing)
    assert parse.call_count == 0
    assert result.structured_result["kind"] == "relation_list" and result.structured_result["unquoted_posts"] == 1
    assert result.answer.startswith("3 posts have this relation in their source records (hashtags: #KitePower)")
    assert "Tidal Co Harbor" in result.answer and "“Kites lift the harbor.”" in result.answer
    assert "1 selected posts have no quotable text" in result.answer
    assert [c.evidence_id for c in result.citations] == ["p1-e1", "p2-e1"]


def test_listing_every_post_needs_an_actual_relation_selection():
    from test_list_screening import screening_service

    service, parse, db = screening_service([])
    db.record_passages = Mock(return_value=[])
    listing = {"selections": [], "list_all": True}
    result = service._answer_evidence("Which posts mention tidal kites?", Filters(dataset="social", record_ids=["p1"]),
                                      "offline", audit=False, relation_listing=listing)
    # Without a relation selection the request is an ordinary screened list.
    assert result.structured_result["kind"] == "ai_screened_list" and parse.call_count >= 1


def test_the_listing_switch_and_relation_guide_follow_the_setting():
    hidden, _ = relation_catalog(False)
    search = next(item for item in hidden.definitions() if item["name"] == "search_records")
    assert "list_selected_posts" not in search["parameters"]["properties"] and "Social relations" not in search["description"]
    shown, _ = relation_catalog(True)
    search = next(item for item in shown.definitions() if item["name"] == "search_records")
    assert "list_selected_posts" in search["parameters"]["properties"]
    assert "select_by_company_profile" in search["description"]


def test_relation_filters_appear_only_on_the_reads_that_select_records():
    catalog, _ = relation_catalog(True)
    by_name = {item["name"]: item for item in catalog.definitions()}
    for name in ("search_records", "record_statistics"):
        assert set(RELATION_FILTERS) <= filter_properties(by_name[name])
    assert not filter_properties(by_name["get_record"]) & set(RELATION_FILTERS)


@pytest.mark.parametrize("query, relation", [
    ("@HarborFund", True), ("#KitePower", True), ("UK trade associations", True), ("state-owned companies", True),
    ("Tidal Co", False), ("Harbor Daily", False)])
def test_handles_hashtags_and_kinds_of_company_are_not_stored_names(query, relation):
    from observatory.research_agent import _RELATION_NAME
    assert bool(_RELATION_NAME.search(query)) is relation


@pytest.mark.parametrize("query, question, relation", [
    ("HarborFund", "Which posts mention @HarborFund?", True),
    ("kitepower", "Which posts use #KitePower?", True),
    ("Harbor Fund", "What does Harbor Fund say about kites?", False)])
def test_a_name_the_question_writes_with_at_or_hash_is_a_relation(query, question, relation):
    from observatory.research_agent import _relation_name
    assert _relation_name(query, question) is relation


def test_the_company_profile_result_stays_compact(monkeypatch):
    catalog, fake = relation_catalog(True, Filters(dataset="all"))
    fake.company_profiles = Mock(return_value=[{"sponsor": f"Gale {n}", "organization_type": "State-owned Entity",
                                                "region": "Atlantis", "commodity": "Wind", "posts": n} for n in range(40)])
    monkeypatch.setattr("observatory.research_tools.entity_registry",
                        lambda: SimpleNamespace(for_source=lambda d, f, v: None))
    result = catalog.call("select_by_company_profile", {"organization_type": "State-owned Entity"})
    assert result["profile"] == {"organization_type": "State-owned Entity"}
    assert set(result["companies"][0]) == {"sponsor", "posts"}


def test_screening_is_told_that_selected_posts_already_satisfy_the_relation(monkeypatch):
    from test_list_screening import screening_service

    service, _, db = screening_service([])
    db.record_passages = Mock(return_value=[])
    seen = []

    def screen(rag, question, evidence, visitor, **_):
        seen.append(question)
        return [], 0.0
    monkeypatch.setattr("observatory.service.screen_list", screen)
    listing = {"selections": [{"relations": {"references": ["quoted"]}, "matched_posts": 1}], "list_all": False}
    service._answer_evidence("Which posts quote another collected post?", Filters(dataset="social", record_ids=["p1"]),
                             "offline", audit=False, declared_shape="every_matching_source", relation_listing=listing)
    assert seen and "already satisfies, by its source record, the relation references: quoted" in seen[0]


def test_the_company_profile_tool_takes_no_scope_filters():
    catalog, _ = relation_catalog(True)
    profile = next(item for item in catalog.definitions() if item["name"] == "select_by_company_profile")
    assert "filters" not in profile["parameters"]["properties"]
