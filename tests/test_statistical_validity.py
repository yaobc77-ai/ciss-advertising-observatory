"""Source and selection boundary checks; synthetic fixtures are not accuracy evidence."""

import sys
from copy import deepcopy
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import prepare_statistical_validity as packet  # noqa: E402


def excel_row():
    values = {"url": "https://example.org/ad", "sponsor": "Shell", "publisher": "Publisher",
              "date": "2020-01-02", "keyword": "energy", "disclosure language": "Paid post",
              "disclosure description": "Above title"}
    return {"file": "source.xlsx", "sha256": "fixture", "sheet": "Sheet1", "row": 2,
            "url": values["url"], "cells": {k: {"coordinate": f"{chr(65+i)}2", "value": v}
                                             for i, (k, v) in enumerate(values.items())}}


def native_record():
    return {"record_id": "native-1", "url": "https://example.org/ad", "title": "Saved ad"}


@pytest.mark.parametrize("missing", [None, "", "  ", "unknown", "NULL", "n/a", "—"])
def test_missing_disclosure_never_counts_as_substantive_excel_answer(missing):
    row = excel_row()
    row["cells"]["disclosure language"]["value"] = missing
    case = next(c for c in packet.native_pool([row], [native_record()])
                if c["task_family"] == "disclosure_language")
    assert case["answer_status"] == "no_substantive_excel_answer"
    assert case["expected_fields"] is None
    assert not case["substantive_excel_answer"]


def test_url_join_alone_does_not_supply_other_answers():
    row = excel_row()
    row["cells"] = {"url": row["cells"]["url"]}
    cases = packet.native_pool([row], [native_record()])
    assert [c["task_family"] for c in cases if c["substantive_excel_answer"]] == ["original_source"]
    # Original URL is a valid source-access answer; it cannot answer disclosure/sponsor/date.
    assert all(c["expected_fields"] is None for c in cases if c["task_family"] != "original_source")


def test_one_missing_field_rejects_two_field_sponsor_publisher_answer():
    row = excel_row()
    del row["cells"]["publisher"]
    case = next(c for c in packet.native_pool([row], [native_record()])
                if c["task_family"] == "sponsor_publisher")
    assert not case["substantive_excel_answer"]
    assert case["expected_fields"] is None


def test_literal_url_match_does_not_guess_tracking_or_slash_equivalence():
    record = native_record()
    record["url"] += "?tracking=1"
    assert not any(c["substantive_excel_answer"] for c in packet.native_pool([excel_row()], [record]))


def test_duplicate_excel_url_is_ambiguous_even_if_cell_values_agree():
    row = excel_row()
    with pytest.raises(ValueError, match="ambiguous_excel_url"):
        packet.native_pool([row, deepcopy(row)], [native_record()])


def selection_pool():
    return [{"case_id": f"{i}-{j}", "task_family": family, "answer_status": "available",
             "source_group": f"article-{j}"} for i, family in enumerate(packet.NATIVE_TASKS)
            for j in range(6)]


def test_six_native_families_use_independent_articles():
    selected = packet.select_excel(selection_pool(), each=1)
    assert len(selected) == 6
    assert len({c["source_group"] for c in selected}) == 6
    assert {c["task_family"] for c in selected} == set(packet.NATIVE_TASKS)


def test_quota_cannot_reuse_same_article_between_families():
    pool = selection_pool()[::6]
    for case in pool:
        case["source_group"] = "only-one-article"
    with pytest.raises(ValueError, match="insufficient_distinct_source_excel_answers"):
        packet.select_excel(pool, each=1)


def test_duplicate_family_source_candidate_rejected_before_selection():
    pool = selection_pool()
    duplicate = deepcopy(pool[0])
    duplicate["case_id"] = "another-id-same-source-and-family"
    with pytest.raises(ValueError, match="duplicate_native_candidate_identity"):
        packet.select_excel(pool + [duplicate], each=1)


def test_membership_duplicate_cannot_inflate_counts():
    records = [{"record_id": "one"}, {"record_id": "one"}]
    with pytest.raises(ValueError, match="duplicate_member_identity"):
        packet.members_digest(records)
    with pytest.raises(ValueError, match="duplicate_member_identity"):
        packet.source_case("count", "social", "How many?", {"count": 2}, records, "fixture")


def social_records():
    return [{"record_id": "s1", "company": "Shell", "account": "account-a", "published_at": "2020-02-01"},
            {"record_id": "s2", "company": "shell", "account": "account-a", "published_at": "2024-02-01"},
            {"record_id": "s3", "company": "Shell", "account": None, "published_at": None},
            {"record_id": "s4", "company": "Shell", "account": "account-b", "published_at": "2024-03-01"}]


def test_social_company_counts_period_difference_and_unknown_account_group():
    cases = {c["task_family"]: c for c in packet.social_cases(social_records(), each=1)}
    assert cases["social_company_count"]["expected_fields"] == {"unique_company_posts": 4}
    accounts = cases["social_accounts"]["expected_fields"]
    assert accounts["total_unique_posts"] == 4
    assert {g["account"]: g["count"] for g in accounts["accounts"]} == {
        "Unknown": 1, "account-a": 2, "account-b": 1}
    periods = cases["social_period_comparison"]["expected_fields"]
    assert periods["period_counts"] == [{"year": "2020", "count": 1}, {"year": "2024", "count": 2}]
    assert periods["difference_second_minus_first"] == 1
    year_case = cases["social_year_count"]
    assert year_case["expected_fields"]["unique_company_posts"] == {
        "2020": 1, "2024": 2}[year_case["expected_fields"]["year"]]
    assert packet.groups(social_records(), "year") == [
        {"year": "2020", "count": 1}, {"year": "2024", "count": 2}, {"year": "Unknown date", "count": 1}]


def test_combined_counts_keep_native_ads_and_unique_posts_separate():
    companies = ["shell", "exxonmobil", "bp", "chevron", "total", "company-f", "company-g"]
    native = [{"record_id": f"n{i}", "company": c, "publisher": "Publisher", "published_at": None}
              for i, c in enumerate(companies)]
    social = [{"record_id": f"s{i}", "company": c, "account": "Account", "published_at": "2024-01-01"}
              for i, c in enumerate(companies)]
    social.append({"record_id": "extra-shell", "company": "shell", "account": "Account", "published_at": "2024-01-02"})
    cases = packet.combined_cases(native, social)
    totals = next(c for c in cases if c["task_family"] == "combined_collection_counts")
    assert totals["expected_fields"] == {"native_ads": 7, "unique_company_posts": 8}
    shell = next(c for c in cases if c["task_family"] == "combined_years"
                 and c["arguments"]["company_casefold"] == "shell")
    assert shell["expected_fields"]["native_unknown_dates"] == 1
    assert shell["expected_fields"]["native_years"] == [{"year": "Unknown date", "count": 1}]
    assert shell["expected_fields"]["social_years"] == [{"year": "2024", "count": 2}]


def test_original_workbook_hash_change_rejected_before_using_export(tmp_path):
    book = openpyxl.Workbook()
    book.active.append(["url"])
    book.active.append(["https://example.org/ad"])
    path = tmp_path / "source.xlsx"
    book.save(path)
    row = {"file": "source.xlsx", "sha256": packet.digest(path.read_bytes()), "sheet": "Sheet",
           "row": 2, "cells": {"url": {"coordinate": "A2", "value": "https://example.org/ad"}}}
    packet.verify_excel_export([row], tmp_path)
    book.active["A2"] = "https://example.org/different"
    book.save(path)
    with pytest.raises(ValueError, match="original_excel_changed"):
        packet.verify_excel_export([row], tmp_path)


def test_exported_cell_mismatch_rejected_even_when_workbook_hash_correct(tmp_path):
    book = openpyxl.Workbook()
    book.active.append(["sponsor"])
    book.active.append(["Shell"])
    path = tmp_path / "source.xlsx"
    book.save(path)
    row = {"file": "source.xlsx", "sha256": packet.digest(path.read_bytes()), "sheet": "Sheet",
           "row": 2, "cells": {"sponsor": {"coordinate": "A2", "value": "BP"}}}
    with pytest.raises(ValueError, match="excel_cell_export_mismatch"):
        packet.verify_excel_export([row], tmp_path)


def test_existing_output_is_preserved_without_reading_inputs(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    marker = out / "history.txt"
    marker.write_text("preserve original", encoding="utf-8")
    with pytest.raises(ValueError, match="output_already_exists"):
        packet.prepare(out, base=tmp_path / "absent-inputs", root=tmp_path)
    assert marker.read_text(encoding="utf-8") == "preserve original"
