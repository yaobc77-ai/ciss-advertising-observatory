"""Dashboard callbacks that hide an error from the public page still leave a log line (known defect, 2026-10-25)."""
import logging
import re
from pathlib import Path

from observatory import app as dashboard

SOURCE = Path(dashboard.__file__).read_text(encoding="utf-8").splitlines()


def test_boundary_failure_logs_the_place_and_type_but_no_details(caplog):
    with caplog.at_level(logging.WARNING, logger="observatory.app"):
        dashboard._boundary_failure("records view", ValueError("postgres://secret@host/db"))
    assert caplog.records[-1].getMessage() == "Dashboard records view failed: ValueError"
    assert "secret" not in caplog.text


def test_every_hidden_exception_in_the_dashboard_logs_or_re_raises():
    """A bare `except Exception` in app.py must log through _boundary_failure or re-raise within three lines."""
    silent = []
    for number, line in enumerate(SOURCE, 1):
        if not re.match(r"\s*except Exception\b", line):
            continue
        following = "\n".join(SOURCE[number:number + 3])
        if "_boundary_failure(" in following or re.search(r"^\s*raise\b", following, re.M):
            continue
        silent.append(number)
    assert silent == [], f"except blocks without a log line or re-raise at app.py lines {silent}"
