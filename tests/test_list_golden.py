"""Golden samples of the list route, frozen before pipeline step 3 (S3-a) merged the one- and
two-collection list paths, and the merged function's own tests.

Fictional ads and posts only (Tidal Co, Harbor Daily, Kite Guild). Every model call is mocked:
screening replies from the passage text, the Decisions judge from a table by record, the
criterion drafter with a fixed criterion, the answer writer with one claim per passage; the
budget is a recording stub. Each scenario records the answer (text, citations, claims,
structured result, trace, cost), the model calls by role (screening and judge calls per
collection, sorted by candidate position or record so thread interleaving is not locked; shared
calls in order), the database calls and every budget reservation with its final state.

`tests/fixtures/list_golden/<scenario>.json` were written at commit 60775b3 (before the merge)
with `OBS_LIST_GOLDEN_RECORD=1 pytest tests/test_list_golden.py -k frozen`. Recording refuses
to overwrite a sample and runs only at that commit with a clean src/ (the baseline is checked
with git). The comparison drops only the differences listed in ALLOWED and in each scenario
(design: docs/architecture/pipeline_step3_list_once_two_phase.zh-CN.md, section 2.2). A sample
is never re-recorded to remove a difference: the code changes, or the difference is listed.
"""
import json
import os
import subprocess
import threading
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from observatory.budget import LimitReached
from observatory.config import Settings
from observatory.criterion_confirmation import UNCONFIRMED_NOTE, chinese
from observatory.list_screening import (
    Batch,
    Decision,
    Verdict,
    Verdicts,
    _phrase_pattern,
    summary_limited_line,
)
from observatory.models import Answer, Citation, CitedStatement, Evidence, Filters
from observatory.question_plan import PLAN_VERSION
from observatory.rag import Rag
from observatory.relevance_triage import Criterion
from observatory.retrieval_explain import group_explain
from observatory.service import Service

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "list_golden"
FROZEN = {"commit": "60775b3", "date": "2026-10-26", "module": "tests/test_list_golden.py"}

JOBS = "Which ads present tidal kites as a source of jobs?"
PHRASE_READ = 'Which ads mention "tidal kite" and what do they say about jobs?'
PHRASE_JOBS = 'Which ads mention "tidal kite" as a source of jobs?'
LITERAL = 'Which ads mention "tidal kite"?'
PLANNER_ZH = "讲潮汐风筝的广告都是哪几篇？"
HASHTAG = "Which posts use #KitePower?"


def ad(record, n, text, start=0):
    return Evidence(evidence_id=f"{record}-e{n}", record_id=record, version_id=f"{record}-v", dataset="native",
                    title=f"Kite notice {record}", publisher="Harbor Daily", sponsor="Tidal Co",
                    published_at=date(2021, 5, 4), text=text, start=start, end=start + len(text))


def post(record, text, account):
    return Evidence(evidence_id=f"{record}-e1", record_id=record, version_id=f"{record}-v", dataset="social",
                    title="", publisher="", sponsor="", account=account, published_at=date(2023, 7, 1),
                    text=text, start=0, end=len(text))


# n1 is a nine-passage article: retrieval returns its opening, record_passages its first eight,
# and the match sits in the ninth, so screening rules it out first and the re-reading finds it.
N1 = [ad("n1", 1, "Tidal Co sponsors the spring festival on the pier.")]
N1 += [ad("n1", n, f"Festival notes, part {n}.", start=100 * (n - 1)) for n in range(2, 9)]
N1.append(ad("n1", 9, "By night, tidal kites power the harbor lights and bring jobs.", start=800))
N2 = ad("n2", 1, "Tidal kites will bring 400 jobs to the harbor.")
N3 = ad("n3", 1, "The gallery shows paper kites from the bay.")
N4 = ad("n4", 1, "Ferries leave at nine from the harbor.")
N5 = ad("n5", 1, "Quiet tidal kite farms hire local crews.")
N6 = ad("n6", 1, "Harbor power prices fell last year.")
S1 = post("s1", "Every tidal kite farm hires local crews: jobs for the harbor.", "Kite Guild")
S2 = post("s2", "Our kite festival starts on Friday.", "Harbor Fest")
S3 = post("s3", "Tidal kites: jobs, jobs, jobs. #KitePower", "Kite Guild")
S4 = post("s4", "Harbor power is cheap tonight.", "Tidal Co Harbor")
PASSAGES = [*N1, N2, N3, N4, N5, N6, S1, S2, S3, S4]
# 45 more ads containing the quoted phrase (every third also a match), for lists with more than
# MAX_CANDIDATES phrase hits: every hit is read first, so the first reading grows past 40.
MANY = [ad(f"L{k:02d}", 1, f"Tidal kite yard {k} brings jobs to the pier." if k % 3 == 0 else
           f"Tidal kite yard {k} opens on Monday.") for k in range(1, 46)]
RANKED = {"native": [N1[0], N2, N3], "social": [S1, S2]}
TEXT_RECORD = {p.text: p.record_id for p in [*PASSAGES, *MANY]}
assert len(TEXT_RECORD) == len(PASSAGES) + len(MANY)  # every passage text identifies its record


def dataset_of(record_id):
    return "social" if record_id.startswith("s") else "native"


def judge(meets, borderline, not_meet, rule=0.0):
    choice = "meets" if meets >= max(borderline, not_meet) else "does_not_meet" if not_meet > borderline else "borderline"
    return {"answers": [
        {"type": "choice", "name": "verdict", "choice": choice, "confidence": 0.9,
         "probabilities": [{"value": "meets", "probability": meets}, {"value": "borderline", "probability": borderline},
                           {"value": "does_not_meet", "probability": not_meet}]},
        {"type": "score", "name": "strength", "score": 2.0, "probabilities": [{"value": 2, "label": "Clear", "probability": 0.8}]},
        {"type": "predicate", "name": "rule_1", "probability": rule},
        {"type": "predicate", "name": "exclusion_1", "probability": 0.05}],
        "usage": {"input_tokens": 500}}


# The Decisions judge's numbers by record: n3/n4/s2 are sure non-matches (excluded),
# n5/n6/s4 are unsure (review), the rest meet the rules.
JUDGE = {"n1": judge(0.9, 0.05, 0.05, 0.9), "n2": judge(0.9, 0.05, 0.05, 0.9), "n3": judge(0.02, 0.03, 0.95),
         "n4": judge(0.01, 0.02, 0.97), "n5": judge(0.6, 0.3, 0.1, 0.6), "n6": judge(0.4, 0.4, 0.2, 0.4),
         "s1": judge(0.9, 0.05, 0.05, 0.9), "s2": judge(0.02, 0.03, 0.95), "s3": judge(0.85, 0.1, 0.05, 0.85),
         "s4": judge(0.4, 0.4, 0.2, 0.4)}
CRITERION = Criterion(counts=["The ad presents tidal kites as a source of jobs."], does_not_count=["Jobs unrelated to kites."])
LISTING = {"selections": [{"relations": {"hashtags": ["#KitePower"]}, "matched_posts": 3}], "list_all": True}
# A relation list may be asked with comparison groups (research agent); the list covers the whole scope.
GROUPS = ({"query": HASHTAG, "filters": {"dataset": "social", "record_ids": ["s1", "s3"]}, "label": "Kite Guild"},
          {"query": HASHTAG, "filters": {"dataset": "social", "record_ids": ["s1", "s4"]}, "label": "Tidal Co Harbor"})

# Record fields the merge changes on purpose (design 2.2): the two-collection path wrote a fixed
# first_read (now the largest collection's, with one value per collection beside it); the plan's
# list_kind for a literal question over both collections; the plan version. S3-b added record
# keys only: the plan's criterion_mode / criterion_available / relation_hint signal, and the
# trace's criterion_source / screening_basis. S3-c adds the structured result's criterion_source
# and, for a list judged by an unconfirmed model draft, one sentence in the answer's first
# paragraph (decision 1, 2026-10-27), accepted by an exact rule in the test, not by a whitelist.
BOTH = (("result", "research_trace", "list_screening", "first_read"),
        ("result", "research_trace", "list_screening", "first_read_by_dataset"))
PLAN = ("result", "research_trace", "question_plan")
ALLOWED = (("db_calls", "public_rows"), ("db_calls", "count_public"),
           (*PLAN, "version"), (*PLAN, "criterion_mode"), (*PLAN, "criterion_available"),
           (*PLAN, "reasons", "criterion_mode"), (*PLAN, "signals", "relation_hint"),
           ("result", "research_trace", "list_screening", "criterion_source"),
           ("result", "research_trace", "list_screening", "screening_basis"),
           ("result", "research_trace", "list_screening", "criterion_draft"),
           ("result", "structured_result", "criterion_source"),
           ("result", "research_trace", "cost_basis"), ("result", "structured_result", "cost_basis"))


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    filters: dict
    match: str = "jobs"          # a passage containing this text is a screening match
    triage: bool = False         # the client can reach the Decisions API
    declared_shape: str | None = None
    relation_listing: dict | None = None
    retrieval_groups: tuple | None = None
    large_scope: bool = False    # 450 native records: the triage reads the candidates only
    many_literal: bool = False   # the 45 extra ads containing the quoted phrase are in the collection
    writer: str = "summary"      # summary | read | fail | limit (the writer hits the visitor's limit)
    fail_social_screening: bool = False
    fail_social_count: bool = False  # the posts' scope count fails before anything is read there
    limit_at: int | None = None  # the n-th budget reservation hits the visitor's limit
    allowed: tuple = ()
    note: str = ""


SCENARIOS = {s.name: s for s in [
    Scenario("native_screen", JOBS, {"dataset": "native"},
             note="screening with re-reading, then a written summary"),
    Scenario("native_screen_zh_planner", PLANNER_ZH, {"dataset": "native"}, match="tidal kite",
             declared_shape="every_matching_source", writer="fail", note="planner-declared list, Chinese wording"),
    Scenario("native_zero_match", JOBS, {"dataset": "native"}, match="unicorn", note="no match: a finding, no web"),
    Scenario("native_triage", JOBS, {"dataset": "native"}, triage=True, writer="fail",
             note="criterion, whole-scope judge, routes pass/review/exclude"),
    Scenario("native_triage_large", JOBS, {"dataset": "native"}, triage=True, large_scope=True, writer="fail",
             note="scope above TRIAGE_ALL_MAX: candidates only"),
    Scenario("native_phrase_read", PHRASE_READ, {"dataset": "native"}, triage=True, writer="read",
             note="quoted phrase read first, no criterion, matched ads read by the writer"),
    Scenario("native_many_phrase", PHRASE_JOBS, {"dataset": "native"}, many_literal=True,
             note="48 phrase hits: all read first, first_read above MAX_CANDIDATES"),
    Scenario("native_literal", LITERAL, {"dataset": "native"}, triage=True, note="exact wording, no model call"),
    Scenario("social_literal", LITERAL, {"dataset": "social"}, triage=True,
             note="exact wording over posts: lines as before the merge (no account filled in)"),
    Scenario("native_limit_reached", JOBS, {"dataset": "native"}, limit_at=3,
             note="the re-reading reservation hits the limit: a limited answer with the passages read"),
    Scenario("both_screen", JOBS, {"dataset": "all"}, allowed=BOTH, note="ads and posts screened apart, one summary"),
    Scenario("both_triage", JOBS, {"dataset": "all"}, triage=True, writer="fail", allowed=BOTH,
             note="one criterion, a judge per collection"),
    Scenario("both_literal", LITERAL, {"dataset": "all"}, triage=True,
             allowed=(*BOTH, ("result", "research_trace", "question_plan", "list_kind")),
             note="exact wording in each collection; the plan now says literal"),
    Scenario("both_phrase_read", PHRASE_READ, {"dataset": "all"}, triage=True, writer="read", allowed=BOTH,
             note="quoted phrase in each collection, matched items read by the writer"),
    Scenario("both_many_phrase", PHRASE_JOBS, {"dataset": "all"}, many_literal=True, allowed=BOTH,
             note="48 phrase hits in the ads, 2 in the posts: each collection's own first reading"),
    Scenario("both_social_fails", JOBS, {"dataset": "all"}, fail_social_screening=True, allowed=BOTH,
             note="one collection fails: the whole question fails, the retrieval candidates are shown"),
    Scenario("both_social_prepare_fails", JOBS, {"dataset": "all"}, triage=True, fail_social_count=True, allowed=BOTH,
             note="one collection's scope count fails: the criterion and the other collection's calls happen as before"),
    Scenario("native_writer_limit", JOBS, {"dataset": "native"}, writer="limit",
             note="the writer hits the limit after a successful re-reading: the screened list stands (2026-10-30)"),
    Scenario("both_writer_limit", JOBS, {"dataset": "all"}, writer="limit", allowed=BOTH,
             note="the writer hits the limit over two collections: the screened list stands (2026-10-30)"),
    Scenario("social_relation_list", HASHTAG, {"dataset": "social", "record_ids": ["s1", "s3", "s4"]},
             relation_listing=LISTING, note="every selected post listed without a model call"),
    Scenario("social_relation_list_groups", HASHTAG, {"dataset": "social", "record_ids": ["s1", "s3", "s4"]},
             relation_listing=LISTING, retrieval_groups=GROUPS,
             note="relation list asked with comparison groups: the whole selection is listed"),
    Scenario("social_relation_hint", HASHTAG, {"dataset": "social", "record_ids": ["s1", "s3", "s4"]}, triage=True,
             relation_listing={**LISTING, "list_all": False},
             note="relation hint in the screening question, no criterion"),
]}


class GoldenDb:
    """A fictional store: six ads (450 in the large variant, 51 with the phrase-hit ads) and four posts."""

    def __init__(self, large=False, many=False, fail_social_count=False):
        self.large, self.fail_social_count = large, fail_social_count
        self.passages = [*PASSAGES, *(MANY if many else [])]
        self.calls = {"search": [], "native": [], "social": [], "public_rows": Counter(), "count_public": Counter()}
        self.save_answer = Mock()
        self.validate_evidence = lambda _: True

    def health(self):
        return {"status": "ok", "data_version": "golden-v1"}

    def connect(self):
        return MagicMock()

    def _rows(self, scope):
        datasets = ["native", "social"] if scope.dataset == "all" else [scope.dataset]
        ids = [rid for rid in dict.fromkeys(p.record_id for p in self.passages) if dataset_of(rid) in datasets]
        if self.large and "native" in datasets:
            ids += [f"n{n}" for n in range(7, 451)]
        if scope.record_ids:
            ids = [rid for rid in ids if rid in scope.record_ids]
        return [{"record_id": rid, "title": f"Kite notice {rid}" if dataset_of(rid) == "native" else "",
                 "dataset": dataset_of(rid), "date_basis": ""} for rid in ids]

    def public_rows(self, scope):
        self.calls["public_rows"][scope.dataset] += 1
        return self._rows(scope)

    def count_public(self, scope):
        self.calls["count_public"][scope.dataset] += 1
        if self.fail_social_count and scope.dataset == "social":
            raise RuntimeError("count unavailable")
        return len(self._rows(scope))

    def search(self, query, scope, **options):
        self.calls["search"].append({"query": query, "dataset": scope.dataset, "record_ids": list(scope.record_ids),
                                     "limit": options.get("limit"), "chunks_per_record": options.get("chunks_per_record"),
                                     "hybrid": "vector" in options})
        found = RANKED.get(scope.dataset, [])
        return [p for p in found if not scope.record_ids or p.record_id in scope.record_ids]

    def phrase_search(self, phrases, scope, limit_records=80):
        patterns = [_phrase_pattern(phrase) for phrase in phrases]
        hits, records = [], []
        for p in self.passages:
            if (dataset_of(p.record_id) == scope.dataset and (not scope.record_ids or p.record_id in scope.record_ids)
                    and all(pattern.search(p.text) for pattern in patterns)):
                if p.record_id not in records:
                    if len(records) >= limit_records:
                        break
                    records.append(p.record_id)
                hits.append(p)
        self.calls[scope.dataset].append({"method": "phrase_search", "phrases": list(phrases),
                                          "limit_records": limit_records, "found": [p.evidence_id for p in hits]})
        return hits

    def record_passages(self, record_ids, scope, per_record=8):
        self.calls[scope.dataset].append({"method": "record_passages", "records": list(record_ids), "per_record": per_record})
        rows = []
        for rid in record_ids:
            own = [p for p in self.passages if p.record_id == rid and dataset_of(rid) == scope.dataset]
            rows.extend(own if per_record is None else own[:per_record])
        return rows


class Ledger:
    """A budget that records each reservation with its final state; the n-th reservation is denied (limit)."""

    def __init__(self, limit_at=None):
        self.open, self.closed, self.count, self.limit_at, self.lock = {}, [], 0, limit_at, threading.Lock()

    def reserve(self, amount, visitor, kind, model):
        with self.lock:
            self.count += 1
            number = self.count
            if number == self.limit_at:
                # Refused, so never granted: not a reservation left unsettled.
                self.closed.append([kind, model, round(float(amount), 9), "denied"])
            else:
                self.open[f"reservation-{number}"] = [kind, model, round(float(amount), 9)]
        if number == self.limit_at:
            raise LimitReached("Daily question limit reached")
        return f"reservation-{number}"

    def _close(self, reservation, *state):
        with self.lock:
            self.closed.append([*self.open.pop(reservation), *state])

    def settle(self, reservation, actual, usage):
        meta = usage.get("observatory_request", {})
        self._close(reservation, "settled", meta.get("stage"), round(float(actual), 9), meta.get("record_id") or meta.get("refs"))

    def uncertain(self, reservation, reason):
        self._close(reservation, "uncertain", reason)

    def cancel_unsent(self, reservation):
        self._close(reservation, "cancelled")

    def reservation_cost(self, reservation):
        return 0.001

    def snapshot(self):
        """Every reservation's lifecycle, as a multiset (reservation numbers depend on thread timing)."""
        return sorted([*self.closed, *([*item, "never settled"] for item in self.open.values())], key=json.dumps)


class Calls:
    """Model calls by role: per collection (sorted, so thread interleaving is not locked) and shared (in order)."""

    def __init__(self):
        self.shared, self.lock = [], threading.Lock()
        self.by_dataset = {"native": {"screen": [], "judge": []}, "social": {"screen": [], "judge": []}}

    def add(self, dataset, role, entry):
        with self.lock:
            if dataset is None:
                self.shared.append({"role": role, **entry})
            else:
                self.by_dataset[dataset][role].append(entry)

    def snapshot(self):
        return {"shared": self.shared,
                **{dataset: {"screen": sorted(roles["screen"], key=lambda e: int(e["first_ref"][1:])),
                             "judge": sorted(roles["judge"], key=lambda e: e["record"])}
                   for dataset, roles in self.by_dataset.items()}}


def reply(parsed, input_tokens, output_tokens):
    return SimpleNamespace(status="completed", model="offline-fictional", output_parsed=parsed,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                                 input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
                                                 model_dump=lambda: {"input_tokens": input_tokens, "output_tokens": output_tokens}))


def written(*cited):
    return Answer(status="answered", answer="", cost_usd=0.002,
                  citations=[Citation(evidence_id=e.evidence_id, quote=q) for e, q in cited],
                  cited_claims=[CitedStatement(text=f"The ad says: {q}", citation_indices=[n]) for n, (_, q) in enumerate(cited, 1)])


def golden_rag(db, scenario, ledger, calls):
    def screening(request):
        payload = json.loads(request["input"][1]["content"])
        ads = payload["ads"]
        records = [TEXT_RECORD[item["passages"][0]["text"]] for item in ads]
        datasets = {dataset_of(record) for record in records}
        if scenario.fail_social_screening and "social" in datasets:
            raise RuntimeError("social screening unavailable")
        calls.add(datasets.pop() if len(datasets) == 1 else None, "screen", {
            "first_ref": ads[0]["ref"], "question": payload["question"],
            "ads": [[record, [p["passage_id"] for p in item["passages"]]] for record, item in zip(records, ads)]})
        decisions = []
        for item in ads:
            hit = next((p for p in item["passages"] if scenario.match in p["text"].casefold()), None)
            decisions.append(Decision(ref=item["ref"], decision="matches" if hit else "does_not_match",
                                      passage_id=hit["passage_id"] if hit else "", quote=hit["text"] if hit else ""))
        return reply(Batch(decisions=decisions), 10, 5)

    def verify(request):
        ads = json.loads(request["input"][1]["content"])["ads"]
        return reply(Verdicts(verdicts=[Verdict(ref=item["ref"], verdict="keep", reason="") for item in ads]), 10, 5)

    def criterion(request):
        calls.add(None, "criterion", {"model": request["model"], "messages": len(request["input"]),
                                      "question": request["input"][-1]["content"]})
        return reply(CRITERION, 20, 10)

    def parse(**request):
        handler = {Batch: screening, Verdicts: verify, Criterion: criterion}.get(request["text_format"])
        assert handler is not None, f"unexpected structured call: {request['text_format']}"
        return handler(request)

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    if scenario.triage:
        def post(path, body, cast_to):
            record = TEXT_RECORD[body["input"].split("\n\n", 1)[1].split("\n")[0]]
            calls.add(dataset_of(record), "judge", {"path": path, "model": body["model"], "record": record,
                                                    "questions": [q["name"] for q in body["questions"]]})
            return JUDGE[record]
        client.post = post

    def embed(texts, visitor="maintenance", cost_sink=None):
        calls.add(None, "embed", {"texts": list(texts)})
        if cost_sink is not None:
            cost_sink.append(0.000001 * len(texts))
        return [[0.0] for _ in texts]

    def generate(question, evidence, visitor, reservation=None, *, progress=None, media_evidence=(),
                 validate_media=None, one_claim_per_source=False):
        records = list(dict.fromkeys(e.record_id for e in evidence))
        calls.add(None, "writer", {"question": question, "records": records, "one_claim_per_source": one_claim_per_source})
        if scenario.writer == "fail":
            raise ValueError("no writer in this scenario")
        if scenario.writer == "limit":
            raise LimitReached("Daily question limit reached")
        first = {e.record_id: e for e in reversed(evidence)}
        if one_claim_per_source:
            # Skips n2 whenever other ads are in the shard, so the follow-up call is exercised.
            cited = [(first[rid], first[rid].text) for rid in records if not (len(records) > 1 and rid == "n2")]
            return written(*cited) if cited else Answer(status="insufficient_evidence", answer="")
        lead = evidence[0]
        return Answer(status="answered", answer="", cost_usd=0.002,
                      citations=[Citation(evidence_id=lead.evidence_id, quote=lead.text)],
                      cited_claims=[CitedStatement(text=f"The ads call the kites a source of jobs: {lead.text}", citation_indices=[1])],
                      summary=[CitedStatement(text="Tidal Co's ads present the kites as a source of jobs.", citation_indices=[1])])

    rag = Rag(db, Settings(), client=client)
    rag.budget = ledger
    rag.embed = embed
    rag.generate = generate
    return rag


def canon(value):
    """JSON-comparable copy: floats rounded (summation order), dates as text, tuples as lists."""
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(canon(v) for v in value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def snapshot(result):
    return {
        "status": result.status, "failure_reason": result.failure_reason, "answer_mode": result.answer_mode,
        "answer": result.answer,
        "citations": [[c.evidence_id, c.quote] for c in result.citations],
        "cited_claims": [[c.text, c.citation_indices] for c in result.cited_claims],
        "summary": [[c.text, c.citation_indices] for c in result.summary],
        "sections": [[s.title, s.citation_indices] for s in result.sections],
        "evidence_ids": [e.evidence_id for e in result.evidence],
        "structured_result": result.structured_result,
        "research_trace": result.research_trace,
        "external_research": result.external_research,
        "cost_usd": result.cost_usd,
    }


def run(scenario):
    """Answer the scenario's question through the evidence route; return the recorded run."""
    db = GoldenDb(large=scenario.large_scope, many=scenario.many_literal, fail_social_count=scenario.fail_social_count)
    ledger, calls = Ledger(scenario.limit_at), Calls()
    service = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls))
    service._search_external = Mock(side_effect=AssertionError("A list answer must not search the web"))
    result = service._answer_evidence(scenario.question, Filters(**scenario.filters), "offline", audit=False,
                                      declared_shape=scenario.declared_shape, relation_listing=scenario.relation_listing,
                                      retrieval_groups=[dict(g) for g in scenario.retrieval_groups] if scenario.retrieval_groups else None)
    return canon({"scenario": asdict(scenario), "result": snapshot(result), "model_calls": calls.snapshot(),
                  "db_calls": db.calls, "ledger": ledger.snapshot()})


def drop(data, path):
    for key in path[:-1]:
        if not isinstance(data, dict) or key not in data:
            return
        data = data[key]
    if isinstance(data, dict):
        data.pop(path[-1], None)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()


def record(path, recorded):
    """Write one sample: only at the frozen commit, with a clean src/, and never over an existing file."""
    assert not path.exists(), f"{path.name} exists; a sample is not re-recorded (delete it on purpose first)"
    head, dirty = git("rev-parse", "--short", "HEAD"), git("status", "--porcelain", "--", "src")
    assert head.startswith(FROZEN["commit"]) and not dirty, (
        f"samples are recorded at {FROZEN['commit']} with a clean src/ (HEAD {head}; changed: {dirty or 'nothing'})")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"frozen": FROZEN, **recorded}, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


@pytest.fixture
def plain_environment(monkeypatch):
    # No private screening norms and no triage switch: the structured screening call, as in CI.
    monkeypatch.setenv("OBS_ANSWER_NORMS", "off")
    monkeypatch.delenv("OBS_RELEVANCE_TRIAGE", raising=False)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_list_route_reproduces_the_frozen_samples(name, plain_environment):
    scenario = SCENARIOS[name]
    actual = run(scenario)
    path = FIXTURES / f"{name}.json"
    if os.environ.get("OBS_LIST_GOLDEN_RECORD"):
        record(path, actual)
        pytest.skip(f"golden sample recorded: {path.name}")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert expected.pop("frozen") == FROZEN
    # The plan version may differ from the frozen one only by being the current one.
    plan = actual["result"]["research_trace"].get("question_plan")
    assert plan is None or plan["version"] == PLAN_VERSION
    # The recorded scenario must be this scenario (a field added to Scenario later keeps its default
    # for an older sample); only the free-text note may differ.
    frozen_scenario, live_scenario = {**actual["scenario"], **expected.pop("scenario")}, actual.pop("scenario")
    assert {k: v for k, v in frozen_scenario.items() if k != "note"} == {k: v for k, v in live_scenario.items() if k != "note"}
    drafted = (actual["result"]["research_trace"].get("list_screening") or {}).get("criterion_source") == "draft_unconfirmed"
    for allowed in (*ALLOWED, *scenario.allowed):
        drop(expected, allowed)
        drop(actual, allowed)
    # Two scores (2026-10-29): each retrieval group now keeps the reader's retrieval detail, accepted
    # by an exact rule: these fake searches keep no route detail, so the explanation has exactly the
    # group's retrieved records, each without routes, and no search words; a group that found nothing
    # has an empty explanation. No other group field may change.
    for group in (actual["result"].get("structured_result") or {}).get("groups") or []:
        explain = group.pop("retrieval_explain")
        if not group["passages"]:
            assert explain == group_explain([]), name
            continue
        records = explain.pop("records")
        assert {**explain, "records": {}} == {**group_explain([]), "partial": True}, name
        assert sorted(records) == sorted(group["retrieved_record_ids"]), name
        assert all(item["run"] is None and item["parts"] == [] for item in records.values()), name
    # A list judged by an unconfirmed model draft now says so (S3-c): the live answer must be the
    # frozen one plus that sentence, exactly once, at the end of the first paragraph; any other
    # list must read exactly as frozen.
    if drafted:
        note = UNCONFIRMED_NOTE["zh" if chinese(scenario.question) else "en"]
        live, frozen = actual["result"].pop("answer"), expected["result"].pop("answer")
        head, separator, rest = live.partition("\n\n")
        assert live.count(note) == 1 and head.endswith(note), name
        assert head[:-len(note)].rstrip() + separator + rest == frozen, name
        # The summary's first statement repeats the head, note included.
        actual["result"]["summary"] = [[text.replace(note, "").rstrip(), refs] if n == 0 else [text, refs]
                                       for n, (text, refs) in enumerate(actual["result"]["summary"])]
    # S3-c: a list that failed after its hold was released carries its embedding cost plus every
    # model call settled before the failure (the frozen samples recorded 0); accepted only as
    # exactly that run's embeddings and the ledger's settled amounts (a Decisions reply without
    # usage is charged its estimate), and only for a limited or unavailable answer.
    if actual["result"]["status"] in ("limited", "service_unavailable"):
        embedded = sum(0.000001 * len(call["texts"]) for call in actual["model_calls"]["shared"] if call["role"] == "embed")
        charged = sum(item[5] for item in actual["ledger"] if item[3] == "settled") + sum(
            item[2] for item in actual["ledger"] if item[3] == "uncertain" and item[4] == "usage_missing")
        live_cost, frozen_cost = actual["result"].pop("cost_usd"), expected["result"].pop("cost_usd")
        assert live_cost == pytest.approx(frozen_cost + embedded + charged), name
    # Spending caps (2026-10-30): a writer refused by a limit leaves the screened list as the answer;
    # before, the whole answer was limited. Accepted exactly: the live answer is the one the same
    # scenario gives when the writer fails, its list summary marked limited instead of failed and
    # one line saying why there is no written summary. The model calls, database reads and ledger
    # stay as frozen.
    if scenario.writer == "limit":
        failed = run(replace(scenario, writer="fail"))
        for allowed in (*ALLOWED, *scenario.allowed):
            drop(failed, allowed)
        for group in (failed["result"].get("structured_result") or {}).get("groups") or []:
            group.pop("retrieval_explain")
        summary = failed["result"]["research_trace"]["list_summary"]
        failed["result"]["research_trace"]["list_summary"] = {**summary, "status": "limited", "reason": "LimitReached"}
        failed["result"]["answer"] += "\n\n" + summary_limited_line(scenario.question)
        assert actual.pop("result") == failed["result"], name
        expected.pop("result")
    assert actual == expected, name


# --- The merged function (S3-a): one implementation, checked beyond the frozen samples ----------


def test_one_and_both_collections_go_through_the_same_function(plain_environment):
    seen = {}
    for name in ("native_triage", "both_triage"):
        scenario = SCENARIOS[name]
        db, ledger, calls = GoldenDb(), Ledger(), Calls()
        service = Service(Settings(), db=db, rag=golden_rag(db, scenario, ledger, calls))
        spy = Mock(wraps=service._list_answer)
        service._list_answer = spy
        result = service._answer_evidence(scenario.question, Filters(**scenario.filters), "offline", audit=False)
        assert spy.call_count == 1
        seen[name] = (len(spy.call_args.args[3]), result.research_trace["list_screening"]["triage"])
    (one_scopes, one), (both_scopes, both) = seen["native_triage"], seen["both_triage"]
    assert (one_scopes, both_scopes) == (1, 2)
    # One collection keeps the flat triage summary; two get one per collection and the totals (design 2.2).
    assert "by_dataset" not in one and one["whole_scope"] is True and one["criterion_cost_usd"] > 0
    assert set(both["by_dataset"]) == {"native", "social"} and "whole_scope" not in both
    assert both["triaged"] == sum(item["triaged"] for item in both["by_dataset"].values()) == 10
    assert both["criterion_cost_usd"] == one["criterion_cost_usd"]  # one criterion, drafted once


def test_a_literal_question_over_both_collections_searches_each_once_and_calls_no_model(plain_environment):
    recorded = run(SCENARIOS["both_literal"])
    for dataset, total, matches in (("native", 6, 3), ("social", 4, 2)):
        assert [call["method"] for call in recorded["db_calls"][dataset]] == ["phrase_search"]
        assert recorded["db_calls"][dataset][0]["phrases"] == ["tidal kite"]
        assert recorded["result"]["structured_result"]["by_dataset"][dataset] == {
            "scope_total": total, "examined": total, "matches": matches}
        assert recorded["model_calls"][dataset] == {"screen": [], "judge": []}
    assert [call["role"] for call in recorded["model_calls"]["shared"]] == ["embed"]
    # The question's own reservation is the only budget event, and it was cancelled unsent.
    assert recorded["ledger"] == [["generation", "gpt-5.6-luna", 0.04, "cancelled"]]
    trace = recorded["result"]["research_trace"]
    assert trace["question_plan"]["list_kind"] == "literal" and trace["list_screening"]["method"] == "exact_text"


def test_each_collection_numbers_and_rereads_its_own_candidates(plain_environment):
    recorded = run(SCENARIOS["both_screen"])
    native, social = recorded["model_calls"]["native"]["screen"], recorded["model_calls"]["social"]["screen"]
    # The ads: one batch of three candidates, then the re-reading of n1 (ruled out from eight of nine passages).
    assert [call["first_ref"] for call in native] == ["A1", "A4"]
    assert [record for record, _ in native[0]["ads"]] == ["n1", "n2", "n3"] and [r for r, _ in native[1]["ads"]] == ["n1"]
    # The posts are numbered from A1 again: each collection is screened on its own.
    assert [call["first_ref"] for call in social] == ["A1"] and [record for record, _ in social[0]["ads"]] == ["s1", "s2"]
    trace = recorded["result"]["research_trace"]["list_screening"]
    assert trace["first_read"] == 40 and trace["first_read_by_dataset"] == {"native": 40, "social": 40}
    # Every screening reservation was settled, each with its batch's refs.
    screening = [item for item in recorded["ledger"] if item[0] == "generation" and item[3] == "settled"]
    assert sorted(item[4] for item in screening) == ["list_screening"] * 2 + ["list_screening_reread"]


def test_more_than_forty_phrase_hits_are_all_read_first_in_each_collection(plain_environment):
    recorded = run(SCENARIOS["both_many_phrase"])
    trace = recorded["result"]["research_trace"]["list_screening"]
    # 45 extra ads plus n1, n2 and n5 contain the phrase: the ads' first reading covers all 48; the posts keep 40.
    assert trace["first_read_by_dataset"] == {"native": 48, "social": 40} and trace["first_read"] == 48
    hits = {hit.split("-")[0] for call in recorded["db_calls"]["native"] if call["method"] == "phrase_search"
            for hit in call["found"]}
    screened = {record for call in recorded["model_calls"]["native"]["screen"] for record, _ in call["ads"]}
    assert len(hits) == 48 and hits <= screened
    assert [call["first_ref"] for call in recorded["model_calls"]["native"]["screen"]][:3] == ["A1", "A5", "A9"]
    single = run(SCENARIOS["native_many_phrase"])["result"]["research_trace"]["list_screening"]
    assert single["first_read"] == 48 and "first_read_by_dataset" not in single


def test_a_writer_refused_by_a_limit_leaves_the_screened_list_with_each_passage_once(plain_environment):
    recorded = run(SCENARIOS["native_writer_limit"])
    result = recorded["result"]
    # The screened list stands; the summary was not written and the trace says a limit stopped it.
    assert result["status"] == "answered" and "Daily question limit reached" not in result["answer"]
    assert result["research_trace"]["list_summary"] == {"status": "limited", "reason": "LimitReached"}
    assert len(result["evidence_ids"]) == len(set(result["evidence_ids"]))
    assert [call["role"] for call in recorded["model_calls"]["shared"]].count("writer") == 1
    both = run(SCENARIOS["both_writer_limit"])["result"]
    assert both["status"] == "answered" and both["research_trace"]["list_summary"]["status"] == "limited"


def test_the_list_wiring_exists_once():
    import inspect

    from observatory import service as module

    assert not hasattr(Service, "_screen_both")
    source = inspect.getsource(module)
    for call in ("screen_list(", "make_criterion(", "self._triaged_screen(", "self._relation_list(",
                 "self._summarize_list(", "self._read_matched_sources(", "self._list_answer(", "ContextPool("):
        assert source.count(call) == 1, call
