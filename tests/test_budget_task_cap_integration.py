"""Opt-in, real checks of the persistent embedding task cap in one owned disposable schema of the private
test database.

Set OBS_RUN_TASK_CAP_INTEGRATION=1 and an explicit OBS_TEST_DATABASE_URL (private cluster from
scripts/private_test_postgres.py). Ledger rows only (fictional task names); no model calls; the schema is
dropped afterwards.
"""

import os
import threading
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql

from observatory.budget import Budget, LimitReached
from observatory.db import Database

pytestmark = pytest.mark.integration
MODEL = "text-embedding-3-small"


class SchemaDatabase(Database):
    def __init__(self, url, schema):
        super().__init__(url)
        self.schema = schema

    def connect(self, vector=False):
        if vector:
            raise ValueError("Task-cap checks do not use vectors")
        return verified_test_connection(self.url, self.schema)


@pytest.fixture()
def budget():
    if os.environ.get("OBS_RUN_TASK_CAP_INTEGRATION") != "1":
        pytest.skip("Explicit task-cap integration opt-in is absent")
    url = configured_test_url()
    schema = f"obs_taskcap_{uuid4().hex}"
    with verified_test_connection(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        database = SchemaDatabase(url, schema)
        database.initialize()
        yield Budget(database, SimpleNamespace(monthly_budget_usd=Decimal("100")))
    finally:
        with verified_test_connection(url, autocommit=True) as conn:
            owned = conn.execute("SELECT nspowner=current_user::regrole AS owned FROM pg_namespace "
                                 "WHERE nspname=%s", (schema,)).fetchone()
            if owned and owned["owned"]:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_concurrent_holds_of_one_task_never_pass_its_cap(budget):
    task, results, start = f"task:kites-{uuid4().hex}", [], threading.Barrier(8)

    def hold():
        start.wait()
        try:
            results.append(budget.reserve(Decimal("0.30"), task, "embedding", MODEL, task_cap=1))
        except LimitReached:
            results.append(None)

    threads = [threading.Thread(target=hold) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(r is not None for r in results) == 3
    assert budget.task_spent(task) == Decimal("0.90")


def test_settled_uncertain_and_cancelled_holds_count_as_the_cap_says(budget):
    task = f"task:boats-{uuid4().hex}"
    settled = budget.reserve(Decimal("0.40"), task, "embedding", MODEL, task_cap=1)
    budget.settle(settled, Decimal("0.10"), {"input_tokens": 5000})
    uncertain = budget.reserve(Decimal("0.40"), task, "embedding", MODEL, task_cap=1)
    budget.uncertain(uncertain, "Timeout")
    cancelled = budget.reserve(Decimal("0.40"), task, "embedding", MODEL, task_cap=1)
    budget.cancel_unsent(cancelled)
    assert budget.task_spent(task) == Decimal("0.50")
    budget.reserve(Decimal("0.50"), task, "embedding", MODEL, task_cap=1)
    with pytest.raises(LimitReached, match="Task cap"):
        budget.reserve(Decimal("0.01"), task, "embedding", MODEL, task_cap=1)
    # Another task, and an uncapped maintenance call, are not limited by this task's total.
    budget.reserve(Decimal("0.50"), f"task:other-{uuid4().hex}", "embedding", MODEL, task_cap=1)
    budget.reserve(Decimal("0.50"), "maintenance", "embedding", MODEL)


def test_a_task_keeps_its_first_cap_and_records_it_on_every_hold(budget):
    task = f"task:nets-{uuid4().hex}"
    first = budget.reserve(Decimal("0.10"), task, "embedding", MODEL, task_cap="1.00")
    budget.settle(first, Decimal("0.05"), {"input_tokens": 2500})
    second = budget.reserve(Decimal("0.10"), task, "embedding", MODEL, task_cap=1)
    budget.uncertain(second, "Timeout")
    with pytest.raises(ValueError, match="another cap"):
        budget.reserve(Decimal("0.10"), task, "embedding", MODEL, task_cap=5)
    with pytest.raises(ValueError, match="needs its task cap"):
        budget.reserve(Decimal("0.10"), task, "embedding", MODEL)
    assert budget.task_caps(task) == ["1"]
    with budget.db.connect() as conn:
        rows = conn.execute("SELECT state,usage FROM usage_ledger WHERE visitor=%s ORDER BY state", (task,)).fetchall()
    assert [(r["state"], r["usage"]) for r in rows] == [
        ("settled", {"task_cap": "1", "input_tokens": 2500}),
        ("uncertain", {"task_cap": "1", "error_type": "Timeout"})]
