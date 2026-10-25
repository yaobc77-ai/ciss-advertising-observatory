from contextlib import contextmanager
from datetime import date

import pytest

from observatory import company_timeline as tl


def test_periods_fill_gaps_with_every_month_quarter_or_year():
    assert tl._periods(date(2020, 11, 1), date(2021, 2, 1), "month") == ["2020-11", "2020-12", "2021-01", "2021-02"]
    assert tl._periods(date(2020, 8, 1), date(2021, 1, 1), "quarter") == ["2020-Q3", "2020-Q4", "2021-Q1"]
    assert tl._periods(date(2019, 6, 1), date(2021, 1, 1), "year") == ["2019", "2020", "2021"]
    assert tl._label_start("2021-Q2") == date(2021, 4, 1)


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        rows = []
        if "GROUP BY" in sql:
            rows = {"native": [{"period": date(2018, 1, 1), "n": 2}],
                    "social": [{"period": date(2020, 1, 1), "n": 5}]}[params[1]]
        elif "count(*)" in sql:
            rows = [{"n": 1 if params[0] == "native" else 0}]
        return type("Cursor", (), {"fetchall": lambda self: rows, "fetchone": lambda self: rows[0] if rows else None})()


class FakeDB:
    def __init__(self):
        self.conn = FakeConn()

    @contextmanager
    def connect(self):
        yield self.conn


def test_two_series_share_one_axis_and_undated_records_stay_separate():
    db = FakeDB()
    result = tl.company_timeline(db, "Chevron", granularity="year")
    assert result["status"] == "ok"
    assert result["periods"] == ["2018", "2019", "2020"]
    assert result["series"]["native"]["counts"] == [2, 0, 0]
    assert result["series"]["social"]["counts"] == [0, 0, 5]
    assert result["series"]["native"]["undated_records"] == 1
    assert "not evidence of one campaign" in result["interpretation"]
    assert db.conn.calls[0][0].startswith("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")


def test_an_unknown_company_is_not_guessed_and_a_bad_granularity_is_rejected():
    assert tl.company_timeline(FakeDB(), "Imaginary Tidal Oil")["status"] == "not_found"
    with pytest.raises(ValueError):
        tl.company_timeline(FakeDB(), "Chevron", granularity="week")
