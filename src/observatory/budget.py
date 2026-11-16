"""Transactional reservations for every paid call, including embeddings.

Unknown outcomes retain their reservation as charged exposure until reconciliation.
Expired leases release concurrency, never money. All accounting months are UTC.
"""

import contextvars
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from psycopg.types.json import Jsonb


class LimitReached(Exception):
    pass


def price(model, input_tokens, output_tokens=0, cached_tokens=0, cache_write_tokens=0):
    """USD cost of a call from token counts; only the configured models have prices."""
    if model == "text-embedding-3-small":
        return Decimal(input_tokens) * Decimal("0.02") / 1_000_000
    if model == "gpt-6-luna":
        # Decisions API: input only, output is free (OpenAI, 2026-10-22); cached input billed at full rate.
        return Decimal(input_tokens) * Decimal("0.10") / 1_000_000
    if model != "gpt-5.6-luna":
        raise ValueError("No verified price configuration for this model")
    if (
        min(input_tokens, output_tokens, cached_tokens, cache_write_tokens) < 0
        or cached_tokens + cache_write_tokens > input_tokens
    ):
        raise ValueError("Invalid token accounting")
    return (
        Decimal(input_tokens - cached_tokens - cache_write_tokens) * Decimal("0.20")
        + Decimal(cached_tokens) * Decimal("0.02")
        + Decimal(cache_write_tokens) * Decimal("0.25")
        + Decimal(output_tokens) * Decimal("1.20")
    ) / 1_000_000


class QuestionCapReached(LimitReached):
    """This question has used its spending cap; what was read so far still answers."""


# The open question this thread works for (a server-made id) and whether the current calls read
# ads for a list. Pools copy the context into their workers (ContextPool).
_QUESTION = contextvars.ContextVar("observatory_question", default=None)
_READING = contextvars.ContextVar("observatory_reading", default=False)

# Reading calls stop this share of the question cap early, so the answer can still be written.
WRITER_SHARE = Decimal("0.2")


class ContextPool(ThreadPoolExecutor):
    """A thread pool whose tasks run in a copy of the submitter's context (question id, reading)."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


@contextmanager
def reading():
    """Calls made inside read ads for a list (judge, screening, reread, verification)."""
    token = _READING.set(True)
    try:
        yield
    finally:
        _READING.reset(token)


class QuestionGate:
    """Visitor and address rate limits count questions, not the model calls inside one answer.

    One list answer can make dozens of calls; counting each call refused the
    question part-way through. A question is counted at its first paid call, so
    free answers (statistics, metadata) never count. It is counted against its
    visitor and, when known, its network address: a client that changes its
    visitor id or cookie keeps its address. Each open question has a server-made
    id and its own spending: settled calls at their cost, calls in flight or of
    unknown outcome at their reservation. Once a reading call is refused, the
    question reads no more (a later settlement does not reopen reading), so a
    list stops at one point. Counts and spending live in this process and
    restart with it; the daily and monthly budgets stay in the database for
    every call.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(deque)
        self._questions = {}
        self._owner = {}

    @contextmanager
    def question(self, visitor, address=None):
        qid = uuid4().hex
        with self._lock:
            self._questions[qid] = {"visitor": visitor, "address": address, "admitted": False, "spent": {},
                                    "stopped_reading": False}
        token = _QUESTION.set(qid)
        try:
            yield qid
        finally:
            _QUESTION.reset(token)
            with self._lock:
                for rid in self._questions.pop(qid)["spent"]:
                    self._owner.pop(rid, None)

    def _current(self, visitor):
        """The open question this call belongs to: the thread's own, else the visitor's only one."""
        qid = _QUESTION.get()
        if qid in self._questions:
            return qid
        mine = [key for key, item in self._questions.items() if item["visitor"] == visitor]
        return mine[0] if len(mine) == 1 else None

    def _count(self, key, now, day_start, per_minute, per_day):
        history = self._history[key]
        while history and now - history[0] >= 86_400:
            history.popleft()
        minute = sum(1 for at in history if now - at < 60)
        day = sum(1 for at in history if at >= day_start)
        return minute >= per_minute or day >= per_day

    def admit(self, visitor, settings):
        """True when this paid call belongs to an open question (counting it once)."""
        with self._lock:
            qid = self._current(visitor)
            if qid is None:
                return False
            item = self._questions[qid]
            if item["admitted"]:
                return True
            now = time.time()
            day_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0).timestamp()
            keys = [(("visitor", visitor), settings.requests_per_minute, settings.requests_per_day)]
            if item["address"]:
                keys.append((("address", item["address"]), getattr(settings, "address_requests_per_minute", 10),
                             getattr(settings, "address_requests_per_day", 60)))
            if any(self._count(key, now, day_start, per_minute, per_day) for key, per_minute, per_day in keys):
                raise LimitReached(
                    "Your question limit has been reached. Please use keyword search or try later."
                )
            if sum(q["admitted"] for q in self._questions.values()) >= settings.concurrency:
                raise LimitReached("Other answers are in progress. Please try again shortly.")
            for key, *_ in keys:
                self._history[key].append(now)
            item["admitted"] = True
            return True

    def hold(self, rid, amount, visitor, settings):
        """Count a reservation against its open question; refuse it past the question's cap.

        Reading calls stop WRITER_SHARE of the cap early. Outside a question nothing is held.
        """
        cap = Decimal(str(getattr(settings, "question_budget_usd", "0.50")))
        with self._lock:
            qid = self._current(visitor)
            if qid is None:
                return
            item = self._questions[qid]
            spent, reads = item["spent"], _READING.get()
            limit = cap * (1 - WRITER_SHARE) if reads else cap
            if (reads and item["stopped_reading"]) or sum(spent.values()) + amount > limit:
                item["stopped_reading"] = item["stopped_reading"] or reads
                raise QuestionCapReached(
                    "This question reached its spending limit. Try a narrower question or selection."
                )
            spent[rid] = amount
            self._owner[rid] = qid

    def settle(self, rid, actual):
        """A settled call counts at its cost (late settlements go to the question that made them)."""
        with self._lock:
            qid = self._owner.get(rid)
            if qid in self._questions:
                self._questions[qid]["spent"][rid] = Decimal(str(actual))

    def release(self, rid):
        """A reservation that was never sent no longer counts."""
        with self._lock:
            qid = self._owner.pop(rid, None)
            if qid in self._questions:
                self._questions[qid]["spent"].pop(rid, None)

    def spent(self, qid=None):
        """A question's spending so far; by default the question this thread works for."""
        with self._lock:
            item = self._questions.get(qid or _QUESTION.get())
            return sum(item["spent"].values()) if item else Decimal("0")

    def carry(self, amount):
        """Count an earlier part of the same question (phase 1 of a confirmed list) in this thread's question."""
        amount = Decimal(str(amount or 0))
        with self._lock:
            item = self._questions.get(_QUESTION.get())
            if item is not None and amount > 0:
                item["spent"][f"carried-{uuid4().hex}"] = amount


QUESTIONS = QuestionGate()


def task_cap_text(value):
    """A positive, finite task cap in USD as its canonical text (1, 1.0 and 1.00 are one cap)."""
    try:
        cap = Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError("A task cap needs a positive amount and a 'task:<name>' visitor") from exc
    if not cap.is_finite() or cap <= 0:
        raise ValueError("A task cap needs a positive amount and a 'task:<name>' visitor")
    return format(cap.normalize(), "f")


class Budget:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    def reserve(self, amount, visitor, kind, model, *, task_cap=None):
        """Hold an estimated amount before a model call; refuse when a limit would be exceeded.

        Expired pending holds become 'uncertain' and still count. The monthly and daily (UTC) caps
        apply to every kind; per-visitor and per-address minute/day limits and concurrency apply to
        generation and are counted once per question by QUESTIONS (in memory), falling back to the
        ledger outside Service.answer. A call inside an open question also counts against that
        question's cap (QuestionCapReached).

        ``task_cap`` bounds everything this ``visitor`` (a persistent task name) has ever reserved:
        settled, pending and uncertain entries all count, in every month. It is checked under the
        same lock and transaction as the new hold, so concurrent runs, retries and restarts of one
        task cannot pass the cap together. The cap is recorded on every hold of the task: a later run
        with another cap, or without one, is refused, so a cap cannot be raised or dropped by rerunning.
        A 'task:' visitor always needs a cap.
        """
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Reservation must be positive")
        if task_cap is not None:
            task_cap = task_cap_text(task_cap)
            if not str(visitor).startswith("task:"):
                raise ValueError("A task cap needs a positive amount and a 'task:<name>' visitor")
        elif str(visitor).startswith("task:"):
            raise ValueError("A 'task:<name>' visitor needs its task cap")
        rid = uuid4().hex
        QUESTIONS.hold(rid, amount, visitor, self.settings)
        try:
            self._reserve(rid, amount, visitor, kind, model, task_cap)
        except BaseException:
            QUESTIONS.release(rid)
            raise
        return rid

    def _reserve(self, rid, amount, visitor, kind, model, task_cap=None):
        with self.db.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(54902)")
            month = conn.execute(
                "SELECT to_char(now() AT TIME ZONE 'UTC','YYYY-MM') AS month"
            ).fetchone()["month"]
            # Crashed or timed-out requests remain fully reserved in spend totals.
            conn.execute(
                "UPDATE usage_ledger SET state='uncertain' WHERE state='pending' AND expires_at<now()"
            )
            spent = conn.execute(
                "SELECT COALESCE(sum(COALESCE(actual_usd,reserved_usd)),0) AS n FROM usage_ledger WHERE month=%s AND state<>'cancelled'",
                (month,),
            ).fetchone()["n"]
            if spent + amount > self.settings.monthly_budget_usd:
                raise LimitReached(
                    "Monthly API budget reached. Browsing and keyword search remain available."
                )
            if task_cap is not None:
                caps = {row["cap"] for row in conn.execute(
                    "SELECT DISTINCT usage->>'task_cap' AS cap FROM usage_ledger WHERE visitor=%s", (visitor,)
                ).fetchall()}
                if caps - {task_cap}:
                    raise ValueError(
                        f"{visitor} was approved with another cap ({', '.join(sorted(str(c) for c in caps))} USD); "
                        "a task's cap cannot change. Use a new task name for a new approval."
                    )
                task_spent = conn.execute(
                    "SELECT COALESCE(sum(COALESCE(actual_usd,reserved_usd)),0) AS n FROM usage_ledger "
                    "WHERE visitor=%s AND state<>'cancelled'",
                    (visitor,),
                ).fetchone()["n"]
                if task_spent + amount > Decimal(task_cap):
                    raise LimitReached(
                        f"Task cap reached for {visitor}: {task_spent} of {task_cap} USD used, "
                        f"next call would hold {amount}."
                    )
            today = conn.execute(
                "SELECT COALESCE(sum(COALESCE(actual_usd,reserved_usd)),0) AS n FROM usage_ledger WHERE state<>'cancelled' AND created_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
            ).fetchone()["n"]
            if today + amount > getattr(self.settings, "daily_budget_usd", Decimal("10")):
                raise LimitReached(
                    "Today's API budget reached. Browsing and keyword search remain available."
                )
            # A call inside an open question counts as that question, once.
            if kind == "generation" and not QUESTIONS.admit(visitor, self.settings):
                count = conn.execute(
                    "SELECT count(*) FILTER(WHERE created_at>now()-interval '1 minute') AS minute,count(*) FILTER(WHERE created_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS day FROM usage_ledger WHERE visitor=%s AND kind='generation'",
                    (visitor,),
                ).fetchone()
                if (
                    count["minute"] >= self.settings.requests_per_minute
                    or count["day"] >= self.settings.requests_per_day
                ):
                    raise LimitReached(
                        "Your question limit has been reached. Please use keyword search or try later."
                    )
                active = conn.execute(
                    "SELECT count(*) AS n FROM usage_ledger WHERE kind='generation' AND state='pending'"
                ).fetchone()["n"]
                if active >= self.settings.concurrency:
                    raise LimitReached(
                        "Two answers are already in progress. Please try again shortly."
                    )
            conn.execute(
                "INSERT INTO usage_ledger(reservation_id,month,visitor,kind,model,reserved_usd,state,expires_at,usage) VALUES (%s,%s,%s,%s,%s,%s,'pending',now()+interval '180 seconds',%s)",
                (rid, month, visitor, kind, model, amount,
                 Jsonb({"task_cap": task_cap} if task_cap is not None else {})),
            )

    def settle(self, rid, actual, usage):
        with self.db.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(54902)")
            row = conn.execute(
                "SELECT state FROM usage_ledger WHERE reservation_id=%s FOR UPDATE",
                (rid,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown reservation")
            if row["state"] not in ("pending", "uncertain"):
                raise ValueError("Reservation already reconciled")
            conn.execute(
                "UPDATE usage_ledger SET actual_usd=%s,state='settled',usage=COALESCE(usage,'{}'::jsonb)||%s WHERE reservation_id=%s",
                (actual, Jsonb(usage), rid),
            )
        QUESTIONS.settle(rid, actual)

    def uncertain(self, rid, error_type):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE usage_ledger SET state='uncertain',usage=COALESCE(usage,'{}'::jsonb)||%s WHERE reservation_id=%s AND state='pending'",
                (Jsonb({"error_type": error_type}), rid),
            )

    def cancel_unsent(self, rid):
        """Only for calls known not to have been dispatched; never after a timeout."""
        with self.db.connect() as conn:
            cancelled = conn.execute(
                "UPDATE usage_ledger SET state='cancelled',actual_usd=0 WHERE reservation_id=%s AND state='pending'",
                (rid,),
            ).rowcount
        if cancelled:  # a settled or uncertain call keeps counting against its question
            QUESTIONS.release(rid)

    def task_caps(self, visitor):
        """The caps recorded on this task's holds (normally one; an uncapped hold shows as None)."""
        with self.db.connect() as conn:
            return sorted((row["cap"] for row in conn.execute(
                "SELECT DISTINCT usage->>'task_cap' AS cap FROM usage_ledger WHERE visitor=%s", (visitor,)
            ).fetchall()), key=str)

    def task_spent(self, visitor):
        """Everything a task has held or spent (settled, pending and uncertain), as the task cap counts it."""
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT COALESCE(sum(COALESCE(actual_usd,reserved_usd)),0) AS n FROM usage_ledger "
                "WHERE visitor=%s AND state<>'cancelled'",
                (visitor,),
            ).fetchone()["n"]

    def summary(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT month,count(*) AS calls,sum(COALESCE(actual_usd,reserved_usd)) AS exposure_usd,count(*) FILTER(WHERE state='uncertain') AS uncertain_calls FROM usage_ledger WHERE state<>'cancelled' GROUP BY month ORDER BY month"
            ).fetchall()

    def reservation_cost(self, rid):
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(actual_usd,reserved_usd) AS cost FROM usage_ledger WHERE reservation_id=%s",
                (rid,),
            ).fetchone()
            return float(row["cost"]) if row else 0.0
