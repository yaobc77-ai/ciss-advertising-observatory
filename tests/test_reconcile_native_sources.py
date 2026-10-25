from datetime import date

from scripts import reconcile_native_sources as rec


def test_dates_are_parsed_in_each_source_format_without_guessing():
    assert rec.parse_date("26/10/2021", day_first=True) == (date(2021, 10, 26), "day")
    assert rec.parse_date("20250613") == (date(2025, 6, 13), "day")
    assert rec.parse_date("2018-03") == (date(2018, 3, 1), "month")
    assert rec.parse_date("2017-03-07 23:08:17+00:00") == (date(2017, 3, 7), "day")
    assert rec.parse_date("") == (None, "missing")
    assert rec.parse_date("31/02/2020", day_first=True) == (None, "invalid")
    assert rec.parse_date("Sept. 3") == (None, "unparsed")


def test_an_implausible_source_date_is_set_aside_not_chosen_or_corrected():
    status = rec.date_status({"combined": (date(1970, 8, 23), "day"), "scrape": (date(2025, 6, 13), "day"),
                              "baseline": (None, "no_row")})
    assert status == {"status": "single_source", "dated_sources": ["scrape"], "implausible_sources": ["combined"]}


def test_month_precision_and_time_zone_gaps_are_not_conflicts_but_years_are():
    assert rec.agree((date(2018, 3, 14), "day"), (date(2018, 3, 1), "month")) == "same"
    assert rec.agree((date(2017, 3, 7), "day"), (date(2017, 3, 8), "day")) == "one_day"
    status = rec.date_status({"baseline": (date(2020, 11, 24), "day"), "url": (date(2016, 11, 14), "day")})
    assert status["status"] == "conflict"


def test_database_value_is_compared_with_every_dated_source():
    values = {"baseline": (date(2020, 11, 24), "day"), "url": (date(2016, 11, 14), "day")}
    assert rec.db_agreement(date(2020, 11, 24), values) == "matches_some"
    assert rec.db_agreement(None, values) == "db_unknown"
    assert rec.db_agreement(date(2020, 11, 24), {"baseline": (date(2020, 11, 24), "day")}) == "matches_all"


def test_urls_and_names_are_normalized_only_for_matching():
    assert rec.normal_url("https://www.NYTimes.com/paidpost/x/y.html/?a=1") == "nytimes.com/paidpost/x/y.html"
    assert rec.normal_name("By American Fuel & Petrochemical Manufacturers") == "by american fuel petrochemical manufacturers"
