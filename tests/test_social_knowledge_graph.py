"""Social posts in the knowledge graph: a post, its posting account and its company affiliation."""

import hashlib

from observatory.knowledge_graph import build_graph, relationship_counts, validate_graph


def post(record_id="social-post:p1", account="Harbor Mill Ferries", sponsor="Harbor Mill", **updates):
    body = "Our new ferry carries 300 passengers."
    result = {
        "record_id": record_id, "version_id": "v-" + record_id[-2:], "dataset": "social",
        "title": "Twitter post · 1", "date": "2023-05-04", "sponsor": sponsor, "publisher": "",
        "account": account, "platform": "Twitter", "body": body,
        "body_hash": hashlib.sha256(body.encode()).hexdigest(),
        "url": "https://twitter.com/harbormill/status/1", "archive_url": "", "annotations": [],
    }
    result.update(updates)
    return result


def by_type(graph, kind):
    return [node for node in graph["nodes"] if node["type"] == kind]


def predicates(graph):
    return sorted(edge["predicate"] for edge in graph["edges"])


def test_a_post_is_a_social_post_posted_by_an_account_affiliated_with_a_company():
    graph = build_graph([post()])
    validate_graph(graph)
    assert not by_type(graph, "Article") and not by_type(graph, "Outlet")
    [social] = by_type(graph, "SocialPost")
    assert social["properties"]["paid_ad_status"] == "not_verified"
    [account] = by_type(graph, "Account")
    assert account["properties"] == {"source_value": "Harbor Mill Ferries", "platform": "Twitter", "dataset": "social",
                                     "source_field": "account",
                                     "identity_status": "source_account_name_not_verified_identity"}
    [company] = by_type(graph, "SponsorCandidate")
    assert company["properties"]["role"] == "listed_company_affiliation"
    assert {"posted_by", "source_lists_affiliation", "has_text_version"} <= set(predicates(graph))
    assert "source_lists_sponsor" not in predicates(graph) and "published_in" not in predicates(graph)


def test_two_posts_by_one_account_share_the_account_node():
    graph = build_graph([post("social-post:p1"), post("social-post:p2")])
    [account] = by_type(graph, "Account")
    assert account["record_ids"] == ["social-post:p1", "social-post:p2"]


def test_the_same_account_name_on_another_platform_is_another_node():
    graph = build_graph([post("social-post:p1"), post("social-post:p2", platform="Facebook")])
    assert len(by_type(graph, "Account")) == 2


def test_missing_account_and_affiliation_create_no_entities():
    graph = build_graph([post(account="", sponsor="")])
    assert not by_type(graph, "Account") and not by_type(graph, "SponsorCandidate")
    codes = {warning["code"] for warning in graph["warnings"]}
    assert {"missing_account", "missing_sponsor"} <= codes


def test_social_labels_are_not_projected_as_native_annotations():
    graph = build_graph([post(annotations=[{"ordinal": 0, "payload": {"scheme": "social13"}}])])
    assert not by_type(graph, "Annotation")
    assert "social_labels_not_projected" in {warning["code"] for warning in graph["warnings"]}


def test_a_post_and_an_article_share_one_registry_organization():
    article = {**post(), "record_id": "n1", "version_id": "vn1", "dataset": "native", "title": "An advertisement",
               "sponsor": "exxonmobil", "publisher": "The Times", "account": "", "platform": ""}
    graph = build_graph([article, post(sponsor="ExxonMobil", account="ExxonMobil")])
    validate_graph(graph)
    organizations = by_type(graph, "Organization")
    assert len(organizations) == 1 and organizations[0]["properties"]["registry_id"]
    assert predicates(graph).count("identifies_organization") == 2


def test_native_sponsor_by_outlet_counts_ignore_social_posts():
    article = {**post(), "record_id": "n1", "version_id": "vn1", "dataset": "native", "title": "An advertisement",
               "sponsor": "exxonmobil", "publisher": "The Times", "account": "", "platform": ""}
    counts = relationship_counts(build_graph([article, post()]))
    assert counts == [{"sponsor": "exxonmobil", "publisher": "The Times", "count": 1}]
