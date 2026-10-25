"""Test-only bypass of the record_versions immutability trigger.

Some integration tests deliberately rewrite a stored version to prove that the
application still detects drift if the database guard is ever bypassed.
"""

from contextlib import contextmanager

TRIGGER = "record_versions_no_update"


@contextmanager
def out_of_band_edit(conn):
    present = conn.execute(
        "SELECT 1 FROM pg_trigger WHERE tgname=%s AND tgrelid='record_versions'::regclass", (TRIGGER,)
    ).fetchone()
    if present:
        conn.execute(f"ALTER TABLE record_versions DISABLE TRIGGER {TRIGGER}")
    try:
        yield
    finally:
        if present:
            conn.execute(f"ALTER TABLE record_versions ENABLE TRIGGER {TRIGGER}")
