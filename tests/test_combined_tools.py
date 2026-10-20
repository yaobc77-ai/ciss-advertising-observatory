"""Combined company selection reaches both source spellings without alias merges."""

import json
from datetime import date
from types import SimpleNamespace
from typing import Annotated

import pytest
from pydantic import Field, TypeAdapter
from test_research_tools import SourceDB, source

from observatory.config import Settings
from observatory.models import Filters
from observatory.research_tools import (
    ENTITY_CONTEXT_BYTES,
    TOOLS,
    FiltersRequest,
    Name,
    Names,
    OptionalNames,
    ScopeConflict,
    ToolCatalog,
    strict_schema,
)
from observatory.service import Service


def catalog_for(base=None):
    db = SourceDB()
    db.rows = [
        source("native-shell", "Outlet A", "shell"),
        source("native-exxon", "Outlet B", "exxonmobil"),
        source("native-bp", "Outlet A", "bp"),
        source("native-unknown", "Outlet A", "(Unknown)"),
        {**source("social-shell", "", "Shell"), "dataset": "social", "platform": "Twitter"},
        {**source("social-exxon", "", "ExxonMobil"), "dataset": "social", "platform": "Twitter"},
        {**source("social-bp", "", "BP"), "dataset": "social", "platform": "Twitter"},
        {**source("social-unknown", "", "(Unknown)"), "dataset": "social", "platform": "Twitter"},
    ]
    service = Service(Settings(show_source_links=False), db=db, rag=object())
    return ToolCatalog(service, base or Filters(dataset="all")), db


@pytest.mark.parametrize("name", ["Shell", "shell", "SHELL", " Shell "])
def test_combined_company_request_expands_real_same_spelling_sources(name):
    catalog, _db = catalog_for()
    selected = catalog.narrow(FiltersRequest(sponsors=[name]))
    assert selected.sponsors == ["Shell", "shell"]
    assert selected.dataset == "all"
    result = catalog.call("record_statistics", {"filters": {"sponsors": [name]}})
    assert result["status"] == "ok"
    assert {item["dataset"]: item["total"] for item in result["collections"]} == {"native": 1, "social": 1}
    assert {row["record_id"] for row in result["records"]} == {"native-shell", "social-shell"}


@pytest.mark.parametrize("trusted", [["Shell", "shell"], ["shell"], ["Shell"]])
@pytest.mark.parametrize("requested", ["Shell", "shell", "SHELL"])
def test_company_expansion_is_intersected_with_trusted_source_variants(trusted, requested):
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=trusted))
    selected = catalog.narrow(FiltersRequest(sponsors=[requested]))
    assert set(selected.sponsors) == set(trusted)
    assert catalog.base_filters.sponsors == trusted


def test_multiple_company_groups_expand_without_duplicate_names_or_guessing_aliases():
    catalog, _db = catalog_for()
    selected = catalog.narrow(FiltersRequest(sponsors=["Shell", "shell", "BP"]))
    assert selected.sponsors == ["Shell", "shell", "BP", "bp"]


@pytest.mark.parametrize("names", [["Imaginary"], ["Shell", "Imaginary"], ["Exxon Mobil"]])
def test_unknown_or_approximate_company_names_do_not_become_zero_or_partial_counts(names):
    catalog, _db = catalog_for()
    result = catalog.call("record_statistics", {"filters": {"sponsors": names}})
    assert result["status"] == "clarify"
    assert "collections" not in result


def test_unknown_source_category_stays_explicit_and_is_not_identity_resolved():
    catalog, _db = catalog_for()
    selected = catalog.narrow(FiltersRequest(sponsors=["(Unknown)"]))
    assert selected.sponsors == ["(Unknown)"]
    result = catalog.call("record_statistics", {"filters": {"sponsors": ["(Unknown)"]}})
    assert {item["dataset"]: item["total"] for item in result["collections"]} == {"native": 1, "social": 1}
    # The unknown category is not a stored name: nothing resolves, nothing is merged.
    resolved = catalog.call("resolve_entity", {"entity_type": "sponsor", "query": "(Unknown)"})
    assert resolved["status"] == "not_found" and resolved["candidates"] == []


def test_different_source_names_and_identical_display_aliases_are_not_merged():
    catalog, db = catalog_for()
    db.rows += [source("native-w", "Outlet A", "williams"),
                {**source("social-w", "", "Williams Companies"), "dataset": "social"},
                source("native-c", "Outlet A", "cera"),
                {**source("social-c", "", "CERAWeek"), "dataset": "social"}]
    result = catalog.call("record_statistics", {"filters": {"sponsors": ["Williams"]}})
    assert result["status"] == "clarify"
    assert catalog.narrow(FiltersRequest(sponsors=["williams", "Williams Companies"])).sponsors == ["williams", "Williams Companies"]
    assert catalog.narrow(FiltersRequest(sponsors=["cera"])).sponsors == ["cera"]
    resolved = catalog.call("resolve_entity", {"query": "CERAWeek", "entity_type": "sponsor"})
    assert resolved["status"] == "clarify"
    assert resolved["source_variants"] == [["cera"], ["CERAWeek"]]


def test_punctuation_and_internal_whitespace_are_not_same_spelling_groups():
    catalog, db = catalog_for()
    db.rows += [source("punctuation", "Outlet A", "Shell."), source("space", "Outlet A", "Exxon Mobil")]
    assert catalog.narrow(FiltersRequest(sponsors=["Shell"])).sponsors == ["Shell", "shell"]
    assert catalog.narrow(FiltersRequest(sponsors=["ExxonMobil"])).sponsors == ["ExxonMobil", "exxonmobil"]
    assert catalog.narrow(FiltersRequest(sponsors=["Exxon Mobil"])).sponsors == ["Exxon Mobil"]


@pytest.mark.parametrize("dataset,expected", [("native", "shell"), ("social", "Shell")])
def test_explicit_collection_projects_trusted_union_to_exact_collection_sources(dataset, expected):
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=["Shell", "shell"]))
    selected = catalog.narrow(FiltersRequest(dataset=dataset))
    assert selected.dataset == dataset
    assert selected.sponsors == [expected]
    result = catalog.call("record_statistics", {"filters": {"dataset": dataset, "sponsors": ["Shell"]}})
    assert result["status"] == "ok"
    assert result["collections"] == [{"dataset": dataset, "total": 1, "retrievable": 1, "unknown_dates": 0}]


def test_explicit_collection_cannot_change_an_existing_exact_source_selection():
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=["Shell"]))
    with pytest.raises(ScopeConflict):
        catalog.narrow(FiltersRequest(dataset="native", sponsors=["Shell"]))
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=["shell"]))
    with pytest.raises(ScopeConflict):
        catalog.narrow(FiltersRequest(dataset="social", sponsors=["Shell"]))


@pytest.mark.parametrize("dataset", ["native", "social"])
def test_native_and_social_case_variants_keep_existing_exact_candidate_behavior(dataset):
    catalog, db = catalog_for(Filters(dataset=dataset))
    db.rows.append({**source("same-dataset-second", "Outlet A", "Shell" if dataset == "native" else "shell"), "dataset": dataset})
    selected = catalog.narrow(FiltersRequest(sponsors=["Shell"]))
    assert selected.sponsors == ["Shell"]
    resolved = catalog.call("resolve_entity", {"query": "Shell", "entity_type": "sponsor"})
    assert resolved["status"] == "clarify" and resolved["candidate_count"] == 2
    assert "source_variants" not in resolved


def test_combined_entity_context_explains_same_spelling_without_false_ambiguity():
    catalog, _db = catalog_for()
    context = catalog.entity_context()
    shell = next(item for item in context["sponsors"] if item["display"] == "Shell")
    assert shell == {"value": "Shell", "display": "Shell", "source_variants": ["Shell", "shell"]}
    assert not any(item["query"].strip().casefold() == "shell" for item in context["ambiguity_hints"])
    assert "(Unknown)" not in {item["value"] for item in context["sponsors"]}


def test_entity_context_variant_groups_preserve_trusted_filters_and_limit():
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=["shell"]))
    context = catalog.entity_context(limit=1)
    assert context["sponsors"] == [{"value": "shell", "display": "Shell", "source_variants": ["shell"]}]
    catalog, _db = catalog_for()
    context = catalog.entity_context(limit=1)
    assert len(context["sponsors"]) == 1 and context["truncated"] is True


def test_resolve_entity_combined_spellings_are_one_selection_group_but_keep_candidate_ids():
    catalog, _db = catalog_for()
    result = catalog.call("resolve_entity", {"query": "Shell", "entity_type": "sponsor"})
    assert result["status"] == "ok"
    assert result["candidate_count"] == 2
    assert result["source_variants"] == [["Shell", "shell"]]
    assert {(candidate["dataset"], candidate["source_value"]) for candidate in result["candidates"]} == {
        ("native", "shell"), ("social", "Shell")
    }
    assert len({candidate["entity_id"] for candidate in result["candidates"]}) == 2
    assert all(candidate["identity_status"] == "source_candidate_not_resolved" for candidate in result["candidates"])


def test_resolve_combined_names_still_requires_clarification_for_related_other_names():
    catalog, db = catalog_for()
    db.rows.append(source("shell-energy", "Outlet A", "Shell Energy"))
    resolved = catalog.call("resolve_entity", {"query": "Shell", "entity_type": "sponsor"})
    assert resolved["status"] == "clarify"
    assert resolved["source_variants"] == [["Shell", "shell"], ["Shell Energy"]]
    hints = catalog.entity_context()["ambiguity_hints"]
    assert any(item["query"].strip().casefold() == "shell" and item["candidate_count"] == 2 for item in hints)


def test_candidate_id_cannot_be_reinterpreted_as_company_name():
    catalog, _db = catalog_for()
    resolved = catalog.call("resolve_entity", {"query": "Shell", "entity_type": "sponsor"})
    key = resolved["candidates"][0]["entity_id"]
    result = catalog.call("record_statistics", {"filters": {"sponsors": [key]}})
    assert result["status"] == "clarify" and "collections" not in result


def test_narrowing_share_denominator_and_numerator_keeps_company_groups_within_trusted_scope():
    base = Filters(dataset="all", sponsors=["Shell", "shell", "BP", "bp"],
                   keywords=["energy"], date_from=date(2019, 1, 1), date_to=date(2021, 12, 31),
                   include_unknown_dates=False)
    catalog, _db = catalog_for(base)
    denominator = catalog.narrow(FiltersRequest(sponsors=["Shell"]))
    numerator = catalog.narrow(FiltersRequest(sponsors=["shell"], publishers=["Outlet A"],
                                             date_from=date(2020, 1, 1)), base=denominator)
    assert denominator.sponsors == numerator.sponsors == ["Shell", "shell"]
    assert numerator.publishers == ["Outlet A"]
    assert numerator.keywords == denominator.keywords == ["energy"]
    assert numerator.date_from == date(2020, 1, 1) and numerator.date_to == base.date_to
    assert not numerator.include_unknown_dates
    with pytest.raises(ScopeConflict):
        catalog.narrow(FiltersRequest(sponsors=["BP"]), base=denominator)
    assert catalog.base_filters == base


def test_explicit_collection_denominator_remains_narrow_and_cannot_reopen_other_dataset():
    catalog, _db = catalog_for(Filters(dataset="all", sponsors=["Shell", "shell"]))
    denominator = catalog.narrow(FiltersRequest(dataset="native", sponsors=["Shell"]))
    numerator = catalog.narrow(FiltersRequest(dataset="all", sponsors=["shell"]), base=denominator)
    assert numerator.dataset == "native" and numerator.sponsors == ["shell"]
    with pytest.raises(ScopeConflict):
        catalog.narrow(FiltersRequest(dataset="social", sponsors=["Shell"]), base=denominator)


@pytest.mark.parametrize("dataset", ["native", "social"])
def test_duplicate_case_hints_are_compact_but_exact_candidates_are_not_merged(dataset):
    catalog, db = catalog_for(Filters(dataset=dataset))
    db.rows.append({**source("same-collection-case", "Outlet A", "Shell" if dataset == "native" else "shell"),
                    "dataset": dataset})
    context = catalog.entity_context()
    hints = [hint for hint in context["ambiguity_hints"] if hint["query"].strip().casefold() == "shell"]
    assert len(hints) == 1
    assert set(hints[0]["source_candidates"]) == {"Shell", "shell"}
    assert "Resolve or clarify" in hints[0]["instruction"]
    assert {item["value"] for item in context["sponsors"] if item["value"].casefold() == "shell"} == {"Shell", "shell"}
    assert catalog.call("resolve_entity", {"query": "Shell", "entity_type": "sponsor"})["status"] == "clarify"
    assert catalog.narrow(FiltersRequest(sponsors=["Shell"])).sponsors == ["Shell"]


def test_hint_deduplication_retains_different_candidate_sets_and_dimensions():
    catalog, db = catalog_for(Filters(dataset="native"))
    names = ["Williams", "WILLIAMS", "Williams Companies", "Williams Companies Holdings", "Williams Plumbing"]
    db.rows = [source(f"w{index}", name, name) for index, name in enumerate(names)]
    context = catalog.entity_context()
    for dimension in ("publishers", "sponsors"):
        broad = [hint for hint in context["ambiguity_hints"]
                 if hint["field"] == dimension and hint["query"].casefold() == "williams"]
        specific = [hint for hint in context["ambiguity_hints"]
                    if hint["field"] == dimension and hint["query"].casefold() == "williams companies"]
        assert len(broad) == len(specific) == 1
        assert set(broad[0]["source_candidates"]) == set(names)
        assert set(specific[0]["source_candidates"]) == {"Williams Companies", "Williams Companies Holdings"}


def test_compact_schema_removes_only_generated_titles_and_keeps_validation_constraints():
    original = FiltersRequest.model_json_schema()
    compact = strict_schema(original)
    assert "title" not in json.dumps(compact)
    assert "title" in original  # The source validator and MCP schema are unchanged.
    for name in original["properties"]:
        old = {key: value for key, value in original["properties"][name].items()
               if key not in {"title", "default"}}
        assert compact["properties"][name] == old
    assert compact["additionalProperties"] is False
    assert compact["required"] == list(original["properties"])
    assert compact["properties"]["dataset"]["anyOf"][0]["enum"] == ["native", "social", "all"]
    expanded = _expand_local_schema(compact)
    assert expanded["properties"]["sponsors"]["anyOf"][0]["maxItems"] == 20
    assert expanded["properties"]["sponsors"]["anyOf"][0]["items"]["maxLength"] == 200
    assert "never AND" in compact["properties"]["labels"]["description"]
    assert "require dataset='social'" in compact["properties"]["labels"]["description"]
    assert "not False" in compact["properties"]["labels"]["description"]
    assert "never widens" in compact["properties"]["date_presence"]["description"]
    assert "Must match" in compact["properties"]["include_inferred_dates"]["description"]


def _expand_local_schema(schema):
    """Resolve every local reference; fail on dangling or cross-schema refs."""
    def expand(node):
        if isinstance(node, list):
            return [expand(value) for value in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            assert node["$ref"].startswith("#/$defs/")
            name = node["$ref"].split("/")[-1]
            assert name in schema["$defs"]
            return {**expand(schema["$defs"][name]),
                    **expand({key: value for key, value in node.items() if key != "$ref"})}
        return {key: expand(value) for key, value in node.items() if key not in {"$defs", "title", "default"}}

    return expand(schema)


def test_shared_name_schema_is_identical_to_original_unshared_bounds():
    original_name = Annotated[str, Field(min_length=1, max_length=200)]
    original_names = Annotated[list[original_name], Field(max_length=20)]
    assert _expand_local_schema(TypeAdapter(Name).json_schema()) == TypeAdapter(original_name).json_schema()
    assert _expand_local_schema(TypeAdapter(Names).json_schema()) == TypeAdapter(original_names).json_schema()
    assert _expand_local_schema(TypeAdapter(OptionalNames).json_schema()) == TypeAdapter(original_names | None).json_schema()
    for tool_name, (model, _description) in TOOLS.items():
        original = model.model_json_schema()
        compact = strict_schema(original)
        expanded = _expand_local_schema(compact)
        # Check every tool's entire resolved schema, not a fake provider response.
        assert expanded == _expand_local_schema(strict_schema(_expand_local_schema(original))), tool_name

        def strict_objects(node):
            if isinstance(node, list):
                for value in node:
                    strict_objects(value)
            elif isinstance(node, dict):
                if node.get("type") == "object":
                    assert node["additionalProperties"] is False
                    assert node["required"] == list(node["properties"])
                for value in node.values():
                    strict_objects(value)

        strict_objects(expanded)
    catalog, _db = catalog_for()
    for definition in catalog.definitions():
        model = TOOLS[definition["name"]][0]
        expected = _expand_local_schema(strict_schema(model.model_json_schema()))
        actual = _expand_local_schema(definition["parameters"])

        def without_prose(node):
            if isinstance(node, dict):
                return {key: without_prose(value) for key, value in node.items() if key != "description"}
            if isinstance(node, list):
                return [without_prose(value) for value in node]
            return node

        assert without_prose(actual) == without_prose(expected)
    assert set(catalog.entity_context()["filter_policy"]) == {
        "accounts", "labels", "date_presence", "include_inferred_dates"}


def _context_bytes(context):
    return len(json.dumps(json.dumps(context, ensure_ascii=False, sort_keys=True), ensure_ascii=False).encode())


def _large_namespace_catalog(base=None):
    catalog, _db = catalog_for(base)
    sponsors = [f"Company {index:03d} " + "x" * 175 for index in range(180)] + ["Chosen Company", "Williams", "Williams Companies"]
    accounts = [f"Account {index:03d} " + "x" * 175 for index in range(280)] + ["Chosen Account"]
    facets = {"publishers": ["Outlet A", "Outlet B"], "sponsors": sponsors, "accounts": accounts,
              "labels": [], "platforms": ["Twitter"], "keywords": []}
    catalog.service.facets = lambda _dataset: facets
    return catalog, facets


def test_extremely_large_directory_is_bounded_with_honest_omission_counts():
    catalog, facets = _large_namespace_catalog()
    context = catalog.entity_context()
    assert _context_bytes(context) <= ENTITY_CONTEXT_BYTES == 6000
    assert context["truncated"] is True
    assert "not record counts or absence evidence" in context["namespace_lookup"]
    assert "resolve_entity" in context["namespace_lookup"]
    for field in ("publishers", "sponsors", "accounts"):
        coverage = context["namespace_coverage"][field]
        assert coverage["available"] == len(facets[field])
        assert coverage["shown"] == len(context[field])
        assert coverage["shown"] + coverage["omitted"] == coverage["available"]
    assert context["namespace_coverage"]["accounts"]["omitted"] > 200
    omitted = facets["sponsors"][-1]
    assert omitted not in {item["value"] for item in context["sponsors"]}
    # Namespace omission is not absence: source checks still see the complete facet.
    assert catalog.narrow(FiltersRequest(sponsors=[omitted])).sponsors == [omitted]
    assert catalog._resolve_entity(
        TOOLS["resolve_entity"][0](query="Williams", entity_type="sponsor"), catalog.base_filters
    )["status"] == "clarify"
    with pytest.raises(ScopeConflict):
        catalog.narrow(FiltersRequest(sponsors=["Williams"]))


def test_namespace_cap_keeps_every_explicit_selected_entity_even_when_count_limit_is_one():
    selected = Filters(dataset="social", sponsors=["Chosen Company", "Williams Companies"],
                       accounts=["Chosen Account"])
    catalog, _facets = _large_namespace_catalog(selected)
    context = catalog.entity_context(limit=1)
    assert {item["value"] for item in context["sponsors"]} == set(selected.sponsors)
    assert {item["value"] for item in context["accounts"]} == set(selected.accounts)
    assert _context_bytes(context) <= ENTITY_CONTEXT_BYTES
    assert catalog.base_filters == selected


def test_long_optional_name_cannot_bypass_directory_budget_and_explicit_names_are_never_dropped():
    catalog, _db = catalog_for()
    facets = {"publishers": ["p" * 2000], "sponsors": ["s" * 2000], "accounts": ["a" * 2000]}
    catalog.service.facets = lambda _dataset: facets
    context = catalog.entity_context()
    assert _context_bytes(context) <= ENTITY_CONTEXT_BYTES
    assert all(context["namespace_coverage"][name]["omitted"] == 1 for name in facets)
    explicit = "Chosen " + "x" * 3000
    catalog, _db = catalog_for(Filters(dataset="native", sponsors=[explicit]))
    catalog.service.facets = lambda _dataset: {"publishers": [], "sponsors": [explicit], "accounts": []}
    context = catalog.entity_context()
    assert context["sponsors"][0]["value"] == explicit
    assert context["explicit_context_over_budget"] is True
    assert catalog.base_filters.sponsors == [explicit]


@pytest.mark.parametrize("dataset", ["all", "social"])
def test_compact_historical_context_retains_every_actual_state_and_unknown_semantics(dataset):
    from observatory.social_annotations import (
        NOTE,
        SCHEME,
        STATUS,
        parse_social_state_id,
        social_state_options,
    )

    catalog, _db = catalog_for(Filters(dataset=dataset))
    states = catalog.entity_context()["social_historical_labels"]
    expected = [item["value"] for item in social_state_options()]
    actual = [item["value"] for item in states["options"]]
    assert actual == expected and len(set(actual)) == 39
    assert len({parse_social_state_id(value)[0] for value in actual}) == 13
    assert {parse_social_state_id(value)[1] for value in actual} == {"source_true", "source_false", "unknown"}
    assert states["dataset"] == "social" and states["scheme"] == SCHEME and states["status"] == STATUS
    assert states["match"] == "any_selected_state_OR_not_AND" and states["note"] == NOTE
    assert "filters.dataset='social'" in states["required_scope"]
    assert "not False" in states["states"]["unknown"]
    assert len(json.dumps(states).encode()) < len(json.dumps(social_state_options()).encode())


@pytest.mark.parametrize("dataset", ["all", "native", "social"])
def test_compact_exact_model_payload_leaves_room_for_long_question_and_resolution(dataset):
    from observatory.content_assessment import QUESTION_IDS, QUESTION_TEXTS
    from observatory.research_agent import (
        MAX_INPUT_BYTES,
        SYSTEM,
        ResearchAgent,
        _json,
        question_contract,
    )

    catalog, _db = catalog_for(Filters(dataset=dataset))
    question = ("Which publishers is Shell working with? " + "查" * 2000)[:2000]
    assert len(question) == 2000
    payload = {
        "question": question, "active_scope": catalog.base_filters.model_dump(mode="json"),
        "question_contract": question_contract(question), "entity_context": catalog.entity_context(),
        "reference_date": None,
        "client_content_questions": [{"question_id": key, "question_exact": text}
                                     for key, text in zip(QUESTION_IDS, QUESTION_TEXTS, strict=True)],
    }
    inputs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _json(payload)}]
    args = {"query": "Shell", "entity_type": "sponsor"}
    result = catalog.call("resolve_entity", args)
    assert result["status"] == "ok"
    inputs += [{"type": "function_call", "id": "fc_test", "call_id": "call_test", "name": "resolve_entity",
                "arguments": _json(args), "status": "completed"},
               {"type": "function_call_output", "call_id": "call_test", "output": _json(result)}]
    definitions = ResearchAgent(SimpleNamespace(), catalog)._definitions()
    assert len(_json({"input": inputs, "tools": definitions}).encode()) + 4096 <= MAX_INPUT_BYTES
    assert MAX_INPUT_BYTES == 60_000
    # Model definitions remain the same exact bounded tools; no new write or fallback route.
    assert {item["name"] for item in definitions} == set(TOOLS) - {"get_media_evidence"} | {"request_clarification"}
