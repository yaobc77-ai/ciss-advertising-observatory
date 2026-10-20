"""Independent reference preparation checks using synthetic source metadata."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "statistics_reference", Path(__file__).parents[1] / "scripts/prepare_statistics_reference.py"
)
reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference)


def config(**filters):
    return {"dataset": "native", "counting_unit": "source_record_id", "scope_label": "Synthetic development scope",
            "filters": {"include_unknown_dates": True, **filters}, "allow_period_overlap": False,
            "periods": [{"id": "first", "date_from": "2020-01-01", "date_to": "2020-12-31", "unknown_dates": "unassigned"},
                        {"id": "second", "date_from": "2021-01-01", "date_to": "2021-12-31", "unknown_dates": "unassigned"}]}


def row(rid, *, sponsor="Alpha", publisher="Outlet", when="2020-01-01", **values):
    return {"record_id": rid, "dataset": "native", "countable": True, "retrievable": True,
            "sponsor": sponsor, "publisher": publisher, "published_at": when, **values}


def build(rows, settings=None):
    return reference.build_reference(reference.normalize_rows(rows), settings or config())


def test_matrix_has_full_zero_cells_and_exact_members_without_alias_merging():
    result = build([row("one"), row("two"), row("three", sponsor="alpha", publisher="Other")])
    cells = {(item["source_sponsor"], item["outlet"]): item for item in result["G01_company_outlet"]["cells"]}
    assert len(cells) == 4
    assert cells["Alpha", "Outlet"]["record_ids"] == ["one", "two"]
    assert cells["Alpha", "Other"]["count"] == 0
    assert result["selected_count"] == 3
    assert result["selected_record_ids"] == ["one", "three", "two"]


def test_admission_dataset_and_active_flags_filter_without_assumed_totals():
    result = build([row("yes"), row("held", countable=False), row("inactive", active=False), row("social", dataset="social")])
    assert result["source_record_count"] == 4
    assert result["selected_record_ids"] == ["yes"]


def test_unknown_entities_are_matrix_buckets_but_not_fabricated_relationships():
    result = build([row("known"), row("no-sponsor", sponsor=""), row("no-outlet", publisher=None)])
    relationships = result["G02_source_relationships"]
    assert relationships["missing_entity_record_ids"] == ["no-outlet", "no-sponsor"]
    assert len(relationships["relationships"]) == 1
    item = relationships["relationships"][0]
    assert item["predicate"] == "source_listed_sponsor_at_outlet"
    assert item["source"] == {"type": "source_sponsor", "key": "Alpha"}
    assert item["record_ids"] == ["known"]
    assert sum(cell["count"] for cell in result["G01_company_outlet"]["cells"]) == 3


def test_years_return_all_tied_maxima_and_separate_unknown_members():
    result = build([row("one", when="2020-12-31"), row("two", when="2021-01-01"), row("missing", when=None)])
    dates = result["G03_dates"]["overall"]
    assert dates["all_maximum_years"] == [2020, 2021]
    assert dates["maximum_known_year_count"] == 1
    assert dates["unknown_date_record_ids"] == ["missing"]
    assert dates["known_date_count"] == 2
    assert result["G03_dates"]["by_entity"]["publisher"][0]["all_maximum_years"] == [2020, 2021]


def test_two_periods_are_inclusive_intersect_selection_and_do_not_assign_unknown_dates():
    result = build([row("edge-one", when="2020-12-31"), row("edge-two", when="2021-01-01"),
                    row("outside", when="2019-12-31"), row("missing", when=None), row("other", sponsor="Other")],
                   config(sponsors=["Alpha"]))
    comparison = result["G03_dates"]["period_comparison"]
    assert [item["record_ids"] for item in comparison["periods"]] == [["edge-one"], ["edge-two"]]
    assert comparison["unassigned_unknown_record_ids"] == ["missing"]
    assert comparison["change_percentage"] == 0
    assert comparison["overlap_record_ids"] == []
    assert result["selected_count"] == 4


def test_zero_first_period_has_no_percentage_invented():
    comparison = build([row("second", when="2021-07-01")])["G03_dates"]["period_comparison"]
    assert comparison["second_minus_first"] == 1
    assert comparison["change_percentage"] is None
    entity = comparison["by_entity"]["sponsor"][0]
    assert [period["count"] for period in entity["periods"]] == [0, 1]
    assert entity["periods"][0]["record_ids"] == []


@pytest.mark.parametrize("filters,expected", [
    ({"date_from": "2021-01-01", "date_to": "2021-12-31"}, ["missing", "second"]),
    ({"date_from": "2021-01-01", "include_unknown_dates": False}, ["second"]),
    ({"date_presence": "missing"}, ["missing"]),
    ({"date_presence": "known"}, ["first", "second"]),
    ({"date_presence": "missing", "include_unknown_dates": False}, []),
    ({"publishers": ["Unseen"]}, []),
])
def test_source_date_and_exact_entity_selection(filters, expected):
    result = build([row("first"), row("second", when="2021-01-01"), row("missing", when="")], config(**filters))
    assert result["selected_record_ids"] == expected


def test_empty_scope_has_no_maximum_year_and_all_period_counts_zero():
    result = build([])
    assert result["G03_dates"]["overall"]["maximum_known_year_count"] is None
    assert result["G03_dates"]["overall"]["all_maximum_years"] == []
    assert [period["count"] for period in result["G03_dates"]["period_comparison"]["periods"]] == [0, 0]


@pytest.mark.parametrize("change", [
    {"countable": "true"}, {"active": 1}, {"retrievable": "false"}, {"sponsor": 4},
    {"record_id": " "}, {"dataset": "external"}, {"published_at": "2020-13-01"},
    {"published_at": "2020-W01-1"}, {"published_at": "2020-01-01T12:00:00Z"}, {"version_id": ""},
])
def test_invalid_source_fields_are_rejected(change):
    with pytest.raises(ValueError):
        reference.normalize_rows([row("one", **change)])


def test_duplicate_record_id_and_envelope_conflicts_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        reference.normalize_rows([row("one"), row("one")])
    with pytest.raises(ValueError, match="conflict"):
        reference.normalize_rows([{"record_id": "outer", "dataset": "native", "payload": row("inner")}])


def test_database_style_source_preserves_version_and_both_admission_flags():
    result = reference.normalize_rows([{"record_id": "one", "dataset": "native", "version_id": "v-exact", "payload": row("one", countable=False, retrievable=True)}])
    assert result[0]["version_id"] == "v-exact"
    assert result[0]["countable"] is False
    assert result[0]["retrievable"] is True


@pytest.mark.parametrize("field,value", [("include_unknown_dates", None), ("sponsors", ["Alpha", "Alpha"]),
                                         ("date_presence", "guess"), ("labels", ["green"]),
                                         ("date_from", "2022-01-01")])
def test_invalid_or_unsupported_filters_are_rejected(field, value):
    settings = config(date_to="2021-12-31")
    settings["filters"][field] = value
    with pytest.raises(ValueError):
        reference.validate_config(settings)


def test_period_overlap_requires_explicit_permission_and_reports_shared_members():
    settings = config()
    settings["periods"][0]["date_to"] = "2021-01-01"
    with pytest.raises(ValueError, match="overlapping"):
        reference.validate_config(settings)
    settings["allow_period_overlap"] = True
    result = build([row("shared", when="2021-01-01")], settings)
    assert result["G03_dates"]["period_comparison"]["overlap_record_ids"] == ["shared"]


@pytest.mark.parametrize("text", ['{"countable":true,"countable":false}', '{"n":NaN}', '{"n":Infinity}'])
def test_ambiguous_json_is_not_silently_accepted(text):
    with pytest.raises(ValueError):
        reference.strict_json(text)


def test_jsonl_and_full_snapshot_inputs_produce_same_independent_counts(tmp_path):
    rows = [row("first"), row("held", countable=False)]
    jsonl = tmp_path / "records.jsonl"
    jsonl.write_text("\n".join(json.dumps(item) for item in rows), encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"records": rows, "observed_identity": {"data_version": "unverified-supplied"}}), encoding="utf-8")
    first, _ = reference.read_source(jsonl)
    second, identity = reference.read_source(snapshot)
    assert first == second
    assert identity["supplied_identity_unverified"]["data_version"] == "unverified-supplied"
    assert reference.build_reference(first, config())["selected_record_ids"] == ["first"]


def test_hash_only_frozen_manifest_is_insufficient_metadata(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"source_records": {"one": {"payload_sha256": "abc"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="full_records"):
        reference.read_source(path)


def test_prepare_writes_new_bound_private_packet_without_database_dependency(tmp_path, monkeypatch):
    source, config_path, output = tmp_path / "records.jsonl", tmp_path / "config.json", tmp_path / "new"
    source.write_text(json.dumps(row("one")) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps(config()), encoding="utf-8")
    monkeypatch.setattr(reference, "acquire_database", lambda: pytest.fail("offline path touched database"))
    receipt = reference.prepare(source, config_path, output)
    result = json.loads((output / "reference.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert receipt["selected_count"] == 1
    assert result["customer_approved"] is False and result["semantic_gold"] is False
    assert result["unseen_evaluation"] is False
    for name, expected in manifest["input_sha256"].items():
        assert reference.digest((output / name).read_bytes()) == expected
    with pytest.raises(ValueError, match="already_exists"):
        reference.prepare(source, config_path, output)


def test_database_acquisition_is_repeatable_read_read_only_with_no_analytics(monkeypatch):
    import psycopg

    from observatory.config import Settings

    connection = MagicMock()
    connection.__enter__.return_value = connection

    def execute(sql):
        answer = MagicMock()
        if sql == "SHOW transaction_read_only":
            answer.fetchone.return_value = {"transaction_read_only": "on"}
        elif "AS version" in sql:
            answer.fetchone.return_value = {"version": "observed-md5"}
        elif sql.startswith("SELECT r.record_id"):
            answer.fetchall.return_value = [{"record_id": "one", "dataset": "native", "version_id": "v1", "payload": row("one")}]
        elif sql != "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY":
            pytest.fail("unexpected SQL statement")
        return answer

    connection.execute.side_effect = execute
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(Settings, "from_env", lambda: Settings(database_url="private-not-output"))
    rows, identity = reference.acquire_database()
    assert connect.call_args.kwargs["options"] == "-c default_transaction_read_only=on"
    assert identity["identity_before"] == identity["identity_after"] == "observed-md5"
    assert rows[0]["version_id"] == "v1"
    assert rows[0]["retrievable"] is True


def test_database_errors_never_print_credentials(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config()), encoding="utf-8")

    def failed():
        raise ValueError("postgresql://user:secret@private")

    monkeypatch.setattr(reference, "acquire_database", failed)
    assert reference.main(["--database", "--config", str(config_path), "--output", str(tmp_path / "out")]) == 2
    assert "secret" not in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("read_only,versions,expected", [
    ("off", ["first", "first"], "read_only_transaction_required"),
    ("on", ["first", "changed"], "source_identity_changed_within_snapshot"),
])
def test_database_snapshot_guards_fail_closed(monkeypatch, read_only, versions, expected):
    import psycopg

    from observatory.config import Settings

    connection = MagicMock()
    connection.__enter__.return_value = connection
    observed = iter(versions)

    def execute(sql):
        answer = MagicMock()
        if sql == "SHOW transaction_read_only":
            answer.fetchone.return_value = {"transaction_read_only": read_only}
        elif "AS version" in sql:
            answer.fetchone.return_value = {"version": next(observed)}
        elif sql.startswith("SELECT r.record_id"):
            answer.fetchall.return_value = []
        return answer

    connection.execute.side_effect = execute
    monkeypatch.setattr(psycopg, "connect", MagicMock(return_value=connection))
    monkeypatch.setattr(Settings, "from_env", lambda: Settings(database_url="private-not-output"))
    with pytest.raises(ValueError, match=expected):
        reference.acquire_database()
