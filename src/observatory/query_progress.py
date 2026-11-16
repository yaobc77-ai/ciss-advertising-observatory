"""Short-lived, session-bound progress for the synchronous Query request.

The registry stores public stage labels only. It is intentionally process-local:
the current Waitress deployment serves requests in one process. Multiple worker
processes would need a shared registry before enabling this live stage display.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable

STAGES = {
    "interpreting": "Interpreting your question",
    "database": "Searching the advertising database",
    "media": "Searching saved image and video evidence",
    "web": "Searching web sources",
    "organizing": "Organizing a source-grounded answer",
    "citations": "Checking citations against sources",
    # Two-phase list questions (pipeline step 3, S3-c).
    "drafting": "Drafting the judging rules",
    "judging": "Judging each ad by the confirmed rules",
}
PREPARING = "Preparing your search"  # a running request before its first stage report
_TOKEN = re.compile(r"[A-Za-z0-9_-]{24,80}\Z")


class ProgressRegistry:
    """Bounded progress state; a page token alone cannot read another session."""

    def __init__(self, *, ttl_seconds=900, max_entries=512, clock=time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        for key in list(self._entries):
            if now - self._entries[key]["updated"] >= self.ttl_seconds:
                del self._entries[key]

    @staticmethod
    def _valid(owner, token):
        return bool(isinstance(owner, str) and owner and isinstance(token, str)
                    and _TOKEN.fullmatch(token))

    def begin(self, owner, token):
        """Register a new request for this page token, replacing any earlier one (the latest wins)."""
        if not self._valid(owner, token):
            return None
        with self._lock:
            return self._start(owner, token)

    def try_begin(self, owner, token):
        """(admitted, request_id): begin() unless a request for this page token is still running.

        Admission and registration happen under one lock, so two contenders cannot both pass; the
        caller holds the slot until finish(). A request that outlives the TTL, or is evicted when
        the registry is full, loses its slot while its work continues (is_current then tells its
        late response apart). Without a valid token nothing is registered and the request is
        admitted with request_id None, as for begin().
        """
        if not self._valid(owner, token):
            return True, None
        with self._lock:
            self._prune(self.clock())
            entry = self._entries.get((owner, token))
            if entry and entry["status"] == "running":
                return False, None
            return True, self._start(owner, token)

    def _start(self, owner, token):
        now = self.clock()
        self._prune(now)
        key = (owner, token)
        if key not in self._entries and len(self._entries) >= self.max_entries:
            oldest = min(self._entries, key=lambda item: self._entries[item]["updated"])
            del self._entries[oldest]
        request_id = secrets.token_urlsafe(18)
        self._entries[key] = {
            "request_id": request_id, "stage": "", "status": "running", "updated": now,
        }
        return request_id

    def reporter(self, owner, token, request_id) -> Callable[[str], None]:
        def report(stage):
            if not isinstance(stage, str):
                return
            stage_key = stage if stage in STAGES else next(
                (key for key, label in STAGES.items() if label == stage), None,
            )
            if stage_key is None:
                return
            with self._lock:
                entry = self._entries.get((owner, token))
                if (entry and entry["request_id"] == request_id
                        and entry["status"] == "running"):
                    entry.update(stage=stage_key, updated=self.clock())
        return report

    def finish(self, owner, token, request_id, *, status="complete"):
        with self._lock:
            entry = self._entries.get((owner, token))
            if entry and entry["request_id"] == request_id and entry["status"] == "running":
                entry.update(status="failed" if status == "failed" else "complete",
                             stage="", updated=self.clock())

    def is_current(self, owner, token, request_id):
        """True while this request is the latest one begun for the page token: an older response is not published.

        A request begun without a valid token (request_id None) is never compared.
        """
        if request_id is None:
            return True
        with self._lock:
            entry = self._entries.get((owner, token))
            return bool(entry) and entry["request_id"] == request_id

    def snapshot(self, owner, token):
        if not self._valid(owner, token):
            return {"status": "idle", "label": ""}
        with self._lock:
            self._prune(self.clock())
            entry = self._entries.get((owner, token))
            if not entry:
                return {"status": "idle", "label": ""}
            return {
                "status": entry["status"],
                "label": STAGES.get(entry["stage"], PREPARING)
                if entry["status"] == "running" else "",
            }
