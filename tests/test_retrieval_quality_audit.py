"""Fresh school, ferry and equipment examples; no corpus or saved eval inputs."""

import hashlib
import json
from contextlib import contextmanager

import pytest

from observatory.config import Settings
from scripts import audit_retrieval_quality as audit


def chunk(body, start, end, **updates):
    text = body[start:end]
    value = {"start_char": start, "end_char": end, "text": text,
             "text_hash": hashlib.sha256(text.encode()).hexdigest(),
             "source_body_hash": hashlib.sha256(body.encode()).hexdigest()}
    return {**value, **updates}


def enumerated_missing(body, spans, expected):
    # Independent set enumeration is the oracle; the audit uses a byte mask.
    covered = {i for start, end in spans for i in range(start, end)}
    intended = {i for start, end in expected for i in range(start, end) if not body[i].isspace()}
    return len(intended), len(intended - covered)


@pytest.mark.parametrize("body,spans", [
    ("Ferry capacity is 40. Trips stop during repairs.", [(0, 20), (15, 46)]),
    ("School owns 12 desks.\n\nDelivery starts in July.", [(0, 20), (22, 46)]),
    ("🛟 Ferry resumes after inspection.\u00a0Crew must approve.", [(0, 33), (34, 51)]),
])
def test_exact_unicode_coverage_counts_overlaps_and_whitespace_once(body, spans):
    spans = [(a, min(b, len(body))) for a, b in spans]
    expected, missing = enumerated_missing(body, spans, [(0, len(body))])
    result = audit.coverage(body, [chunk(body, a, b) for a, b in spans], observation=True)
    assert result["expected_nonwhitespace_characters"] == expected
    assert result["uncovered_nonwhitespace_characters"] == missing
    assert result["invalid_offset_chunks"] == result["text_or_text_hash_mismatch_chunks"] == 0


def test_missing_qualification_is_detected_and_complete_source_passes():
    body = "School hired 12 tutors. Funding ends in June."
    first = "School hired 12 tutors."
    result = audit.coverage(body, [chunk(body, 0, len(first))])
    assert result["uncovered_nonwhitespace_characters"] == len("FundingendsinJune.")
    assert audit.coverage(body, [chunk(body, 0, len(body))])["uncovered_nonwhitespace_characters"] == 0


def test_reviewed_native_ranges_do_not_turn_excluded_navigation_into_failure():
    first, navigation, last = "Equipment was inspected.", " Read related articles. ", "Next inspection is in June."
    body = first + navigation + last
    spans = [(0, len(first)), (len(first + navigation), len(body))]
    result = audit.coverage(body, [chunk(body, a, b) for a, b in spans], ranges=spans)
    assert result["uncovered_nonwhitespace_characters"] == 0
    assert result["expected_nonwhitespace_characters"] == len("Equipmentwasinspected.NextinspectionisinJune.")
    assert audit.coverage(body, [chunk(body, a, b) for a, b in spans])["uncovered_nonwhitespace_characters"] > 0


def test_explicit_partial_prefix_only_checks_the_authorized_saved_scope():
    body = "Ferry service restarts. Footer and unfinished extraction."
    end = len("Ferry service restarts.")
    result = audit.coverage(body, [chunk(body, 0, end)], retrieval_end=end)
    assert result["uncovered_nonwhitespace_characters"] == 0
    # This says nothing about completeness of the original ferry announcement.
    assert result["source_characters"] == len(body)


@pytest.mark.parametrize("updates,counter", [
    ({"text": "Different equipment report."}, "text_or_text_hash_mismatch_chunks"),
    ({"text_hash": "0" * 64}, "text_or_text_hash_mismatch_chunks"),
    ({"source_body_hash": "0" * 64}, "source_body_hash_mismatch_chunks"),
    ({"start_char": -1}, "invalid_offset_chunks"),
    ({"end_char": 1000}, "invalid_offset_chunks"),
    ({"start_char": True}, "invalid_offset_chunks"),
])
def test_wrong_bindings_cannot_manufacture_coverage(updates, counter):
    body = "Equipment includes 8 radios."
    result = audit.coverage(body, [chunk(body, 0, len(body), **updates)], observation=True)
    assert result[counter] == 1
    assert result["uncovered_nonwhitespace_characters"] == len("Equipmentincludes8radios.")


def item(identifier, reason):
    return {"record_id": identifier, "reason": reason, "title": "Synthetic ferry report"}


def test_bounded_queue_preserves_other_categories_and_never_deletes_candidates():
    categories = [[item("ferry:1", "partial"), item("ferry:2", "partial")],
                  [item("school:1", "duplicate"), item("school:1", "duplicate")]]
    assert audit.bounded_queue(categories, 0) == []
    assert [(i["record_id"], i["reason"]) for i in audit.bounded_queue(categories, 3)] == [
        ("ferry:1", "partial"), ("school:1", "duplicate"), ("ferry:2", "partial")]
    assert len(categories[1]) == 2


@pytest.mark.parametrize("limit", [-1, 51, True, "12"])
def test_invalid_limits_fail_before_a_database_connection(limit, monkeypatch):
    monkeypatch.setattr(audit.psycopg, "connect", lambda *a, **kw: pytest.fail("Must not connect"))
    with pytest.raises(ValueError):
        audit.collect(settings=Settings(database_url="not-a-dsn"), review_limit=limit)


def test_connection_and_snapshot_are_readonly_and_repeatable(monkeypatch):
    calls = []
    original_snapshot = audit.collect_snapshot

    @contextmanager
    def connect(dsn, **kwargs):
        assert dsn == "synthetic-secret-dsn"
        calls.append(kwargs)
        yield object()

    monkeypatch.setattr(audit.psycopg, "connect", connect)
    monkeypatch.setattr(audit, "collect_snapshot", lambda conn, **kw: kw)
    result = audit.collect(settings=Settings(database_url="synthetic-secret-dsn", embedding_model="fixture-model"))
    assert result == {"embedding_model": "fixture-model", "review_limit": 12}
    assert "default_transaction_read_only=on" in calls[0]["options"]
    assert "statement_timeout=60000" in calls[0]["options"]
    monkeypatch.setattr(audit, "collect_snapshot", original_snapshot)

    class NotReadonly:
        def execute(self, sql):
            calls.append(sql)
            return self

        def fetchone(self):
            return {"transaction_read_only": "off"}

    with pytest.raises(RuntimeError, match="read-only"):
        audit.collect_snapshot(NotReadonly(), embedding_model="fixture-model")
    assert calls[-2:] == ["SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", "SHOW transaction_read_only"]


def test_error_receipt_omits_credentials_and_raw_exception(monkeypatch, tmp_path):
    def fail(**kwargs):
        raise RuntimeError("postgres://user:SECRET@example.invalid/private source text")

    monkeypatch.setattr(audit, "collect", fail)
    out = tmp_path / "failed"
    assert audit.run_audit(out) == 1
    value = (out / "failure.json").read_text()
    assert "SECRET" not in value and "private source text" not in value
    assert json.loads(value) == {"status": "failed", "error_type": "RuntimeError", "sqlstate": None,
                                 "dsn_and_source_text_omitted": True}


def test_new_output_preserves_previous_receipts(monkeypatch, tmp_path):
    out = tmp_path / "previous"
    out.mkdir()
    (out / "audit.json").write_text("previous evidence", encoding="utf-8")
    monkeypatch.setattr(audit, "collect", lambda **kw: pytest.fail("Existing output must reject before connecting"))
    with pytest.raises(FileExistsError):
        audit.run_audit(out)
    assert (out / "audit.json").read_text() == "previous evidence"


def test_aggregate_and_review_queue_are_saved_separately(monkeypatch, tmp_path):
    queue = [item("ferry:3", "duplicate_body_candidate")]
    fixture = {"source_fingerprint": {"active_current_versions": "fixture"},
               "snapshot": {"read_only": "on"}, "collections": [{"dataset": "native", "countable_records": 1}],
               "review_queue": queue}
    monkeypatch.setattr(audit, "collect", lambda **kw: fixture.copy())
    out = tmp_path / "new"
    assert audit.run_audit(out) == 0
    assert "review_queue" not in json.loads((out / "audit.json").read_text())
    saved = json.loads((out / "review_queue.json").read_text())
    assert saved["items"] == queue and saved["status"] == "review_only_no_changes_applied"


def test_source_coverage_preserves_observation_units_and_detects_unexplained_chunks(monkeypatch):
    body = "Ferry has 4 life rafts."
    sources = [
        {"record_id": "ferry:1", "version_id": "v1", "dataset": "social", "title": "Ferry equipment",
         "body": body, "retrieval_ranges": None, "retrieval_end": None, "source_observation_id": "source:1"},
        {"record_id": "ferry:1", "version_id": "v1", "dataset": "social", "title": "Ferry equipment",
         "body": body, "retrieval_ranges": None, "retrieval_end": None, "source_observation_id": "source:2"},
    ]
    chunks = [{**chunk(body, 0, len(body)), "record_id": "ferry:1", "version_id": "v1",
               "dataset": "social", "title": "Ferry equipment", "source_observation_id": identifier}
              for identifier in ("source:1", "unexplained:3")]
    responses = iter((sources, chunks))
    monkeypatch.setattr(audit, "_rows", lambda *a, **kw: next(responses))
    counts, queue = audit._source_coverage(object(), "fixture-profile", 5)
    assert counts[0]["source_units"] == 2
    assert counts[0]["source_units_without_active_chunks"] == 1
    assert counts[0]["uncovered_nonwhitespace_characters"] == len("Ferryhas4liferafts.")
    assert counts[0]["chunks_without_expected_source_unit"] == 1
    assert {i["source_observation_id"] for i in queue} == {"source:2", "unexplained:3"}
    assert len(sources) == 2  # Equal text never collapses independent observations.


def test_excluded_article_text_is_flagged_but_navigation_and_repeated_quotes_are_not():
    article = ("Amongst the most eye-catching recent developments is the battery-based energy storage project "
               "in the port district, with a storage capacity of 61 megawatt hours and an output of 61 MW. ")
    quote = ("\u201cStorage is key to our strategy, and we will need to embrace reliable energy storage to "
             "integrate more and more solar and wind into our energy mix in the years ahead.\u201d")
    body = "Intro paragraph.\n" + quote + "\nHome\nMenu\nSubscribe\n" + quote + "\n" + article * 2 + "\nEnd."
    keep_quote = body.index(quote) + len(quote)
    navigation_end = body.index(quote, keep_quote)
    # Navigation and the repeated pull quote are excluded: no signal.
    ranges = [(0, keep_quote), (body.index(article), len(body))]
    assert audit.excluded_unique_prose(body, ranges) == []
    # Excluding the article itself is flagged with its interval.
    flagged = audit.excluded_unique_prose(body, [(0, navigation_end)])
    assert len(flagged) == 1
    assert flagged[0]["excluded_start"] == navigation_end
    assert flagged[0]["first_line"].startswith(article[:40])
