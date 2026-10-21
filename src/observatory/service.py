"""Shared filtered-record service for the UI, export and evidence queries."""

import hashlib
import logging
import re
import time
from collections import Counter
from contextvars import ContextVar
from copy import deepcopy
from itertools import zip_longest
from urllib.parse import urlsplit

from .budget import LimitReached, price
from .db import Database
from .list_screening import (
    DISPLAY_LIMIT,
    MAX_CANDIDATES,
    MAX_WIDENED,
    hidden_line,
    list_answer,
    literal_results,
    pure_literal_question,
    quoted_phrases,
)
from .list_screening import screen as screen_list
from .models import Answer, AnswerSection, CitedStatement, Filters
from .rag import AnswerValidationError, Rag
from .structured_queries import QuestionPlan, plan_question, validate_share_scope

log = logging.getLogger(__name__)
_FINAL_AUDIT_CONTEXT = ContextVar("observatory_final_answer_audit", default=False)


# Run endings caused by planning or title lookup, not by the collection itself.
_COLLECTION_SEARCH_REASONS = {"research_plan_invalid", "research_plan_clarification", "research_filter_not_in_question",
                              "original_source_record_unresolved", ""}
# The user restricted the answer to the collection or current selection.
_COLLECTION_ONLY = re.compile(
    r"\bonly (?:use|using|from|in)\b|\bin (?:this|the selected|the current) (?:collection|selection) only\b"
    r"|仅使用|只使用|只用|仅限|仅根据|只根据", re.I)


def _collection_search_applies(run) -> bool:
    """A content question whose plan failed can still be searched in the saved text.

    Counts, original spreadsheet fields and statistics reads are never replaced
    by a passage search: those need their own tools.
    """
    if (run.failure_reason or "") not in _COLLECTION_SEARCH_REASONS:
        return False
    if (getattr(run, "question_contract", None) or {}).get("original_metadata_only"):
        return False
    for step in run.tool_trace:
        if step.get("tool") in {"record_statistics", "get_record_metadata"}:
            return False
        if step.get("tool") == "set_research_plan":
            routes = {task.get("route") for task in (step.get("arguments") or {}).get("tasks", [])
                      if isinstance(task, dict)}
            if routes & {"statistics", "metadata"} and not routes & {"record", "sources", "claims"}:
                return False
    return True


# Passage text sent to the writer; the prompt also carries a quotation catalogue
# of the same text, and the provider request is capped at 100,000 bytes.
EVIDENCE_CHAR_BUDGET = 30_000
# A selection this small is read whole: ranking 27 posts and reading the top 5
# missed the asked-about post (B1K-Q009). The prompt budget still applies.
SMALL_SCOPE_RECORDS = 30


def _fit_evidence_budget(evidence, budget=EVIDENCE_CHAR_BUDGET):
    """Keep the highest-ranked passages that fit the writer's prompt budget.

    Long passages from several records can exceed the request cap; dropping
    the lowest-ranked ones is better than answering nothing. Returns the kept
    passages and how many were dropped.
    """
    kept, used = [], 0
    for item in evidence:
        size = len(item.text)
        if kept and used + size > budget:
            continue
        kept.append(item)
        used += size
    return kept, len(evidence) - len(kept)


# A "what do these ads say" list reads its matched ads in up to three writer
# calls of four ads: the writer has MAX_CLAIMS claims per call, and two claims
# for one ad crowded others out of six-ad shards (B1K-S: 10/12, 8/12, 6/9).
ZONE_RECORDS = 4
CONTENT_ZONES = 3
# A list answer opens with an answer the writer drafts from the most relevant
# listed ads (retrieval order); the full list follows (user, 2026-10-19).
SUMMARY_RECORDS = 6


def _renumbered(claims, offset):
    """Listed lines end with their own "[n]"; drop it and shift the citation numbers."""
    return [CitedStatement(text=re.sub(r"\s*\[\d+\]$", "", c.text),
                           citation_indices=[n + offset for n in c.citation_indices]) for c in claims]
# Passages retrieval returns per screened ad (`Database.record_passages`).
RECORD_PASSAGES = 8


def _zone_evidence(evidence, record_ids, match_ids):
    """Passages of the given ads, interleaved so the prompt budget trims each
    ad's tail instead of dropping whole ads; each ad's matched passage leads.

    Returns the passages sent and, per ad, how many of its retrieved passages
    were available and sent. Retrieval caps an ad at RECORD_PASSAGES passages,
    so "all retrieved passages sent" is not "the whole article read".
    """
    groups = [sorted((e for e in evidence if e.record_id == rid),
                     key=lambda e: (e.evidence_id != match_ids[rid], e.start, e.evidence_id))
              for rid in record_ids]
    order = [item for row in zip_longest(*groups) for item in row if item is not None]
    sent = _fit_evidence_budget(order)[0]
    sent_ids = {e.evidence_id for e in sent}
    reading = {rid: {"available_passages": len(group),
                     "sent_passages": sum(e.evidence_id in sent_ids for e in group),
                     # The article may continue past the passages retrieval returned.
                     "retrieval_cap_reached": len(group) >= RECORD_PASSAGES}
               for rid, group in zip(record_ids, groups)}
    return sent, reading


def _list_over_selection(question, narrowed, selection, data):
    """A list question keeps both collections when the user selected both.

    The planner reads "which ads" as native ads only, so posts making the same
    point were never read (customer C08, 2026-10-20: no ad matched, three posts
    did). Narrowing that names an outlet, records or labels belongs to the ads
    and is kept.
    """
    from .question_policy import question_contract

    listing = data.get("answer_shape") == "every_matching_source" or question_contract(question)["requires_complete_list"]
    if (selection.dataset != "all" or narrowed.dataset != "native" or not listing or data.get("retrieval_groups")
            or narrowed.publishers or narrowed.record_ids or narrowed.labels):
        return narrowed
    return narrowed.model_copy(update={"dataset": "all"})


def _with_accounts(results, evidence):
    """Show a social post's account where a native ad shows its outlet."""
    account = {e.record_id: getattr(e, "account", "") for e in evidence if getattr(e, "dataset", "") == "social"}
    return [{**item, "publisher": account[item["record_id"]]}
            if not item.get("publisher") and account.get(item["record_id"]) else item for item in results]


def _opening_words(text, limit=30):
    """A verbatim opening of a passage: its first sentence, at most `limit` words."""
    sentence = re.split(r"(?<=[.!?。！？])\s", text.strip(), maxsplit=1)[0]
    words = sentence.split()
    return sentence if len(words) <= limit else text.strip()[:len(" ".join(words[:limit]))]


def _progress(callback, stage):
    # A disconnected browser must never interrupt accounting or source checks.
    if callback:
        try:
            callback(stage)
        except Exception:
            log.debug("Progress listener unavailable")


def safe_url(value):
    try:
        p = urlsplit(value or "")
        return (
            value
            if p.scheme in ("http", "https")
            and p.hostname
            and not p.username
            and not p.password
            else ""
        )
    except ValueError:
        return ""


def summarize(rows):
    total = len(rows)

    def group(field, selected=None):
        selected = rows if selected is None else selected
        counts = Counter(r.get(field) or "(Unknown)" for r in selected)
        return [
            {"name": k, "count": v, "percent": 100 * v / len(selected) if selected else 0}
            for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]

    timeline = Counter((r["date"][:7] if r.get("date") else "Unknown") for r in rows)
    inferred = Counter(r.get("inferred_tier") for r in rows
                       if str(r.get("date_basis") or "").startswith("inferred:"))
    relationships = Counter(
        (r.get("sponsor") or "(Unknown)", r.get("publisher") or "(Unknown)")
        for r in rows
    )
    return {
        "total": total,
        "retrievable": sum(r["retrievable"] for r in rows),
        "unknown_dates": sum(not r.get("date") for r in rows),
        **{
            f: group(f[:-1] if f != "keywords" else "keyword")
            for f in ["publishers", "sponsors", "platforms", "keywords"]
        },
        "accounts": group("account", [r for r in rows if r.get("dataset") == "social"]),
        "timeline": [{"month": k, "count": v} for k, v in sorted(timeline.items())],
        "relationships": [
            {"sponsor": s, "publisher": p, "count": n}
            for (s, p), n in sorted(relationships.items(), key=lambda x: (-x[1], x[0]))
        ],
        "inferred_dates": dict(sorted(inferred.items())),
    }


WEB_SUPPLEMENT_LEAD = ("The advertising collection does not contain enough to answer this question, so the "
                      "answer below is supplemented from web sources. It is not from the advertising "
                      "database: each paragraph cites the web page it relies on.")


def _date_inference_note(used: bool, tiers: dict) -> str:
    """Server-written label; the model can neither omit nor reword it."""
    total = sum(tiers.values())
    if not total:
        return ""
    # Plain words, no tier codes (user, 2026-10-19: the tier wording was unclear
    # and the estimated dates are unreliable).
    labels = {"A": "the article link", "B": "an archive capture", "C": "a web search"}
    detail = ", ".join(f"{n} from {labels.get(tier, tier)}" for tier, n in sorted(tiers.items()))
    if used:
        return (f" {total:,} of these ads have no publication date in the source; their dates were "
                f"estimated ({detail}) and may be wrong.")
    return (f" {total:,} of these ads have no publication date in the source, so they are not counted "
            "by date here.")


def _plain_scope(scope, base):
    """Describe how a comparison group narrows the trusted selection, in plain words."""
    from .analytics import sponsor_display

    parts = []
    if scope.sponsors and scope.sponsors != base.sponsors:
        relation = "posts with source-listed company affiliation " if scope.dataset == "social" else "ads sponsored by "
        parts.append(relation + ", ".join(sponsor_display(s) for s in scope.sponsors))
    if scope.publishers and scope.publishers != base.publishers:
        parts.append("ads in " + ", ".join(scope.publishers))
    if scope.accounts and scope.accounts != base.accounts:
        parts.append("posts from source-listed accounts " + ", ".join(scope.accounts))
    if scope.platforms and scope.platforms != base.platforms:
        parts.append("records on " + ", ".join(scope.platforms))
    if scope.dataset == "social" and scope.labels and scope.labels != base.labels:
        from .social_annotations import parse_social_state_id, social_label_metadata

        names = {item["key"]: item["label"] for item in social_label_metadata()}
        states = {"source_true": "True", "source_false": "False", "unknown": "unknown"}
        parts.append("posts matching any historical source state " + ", ".join(
            f"{names[key]}: {states[state]}" for key, state in map(parse_social_state_id, scope.labels)))
    if (scope.date_from, scope.date_to) != (base.date_from, base.date_to):
        unit = {"native": "ads", "social": "posts"}.get(scope.dataset, "records")
        parts.append(f"{unit} dated {scope.date_from or 'any time'} to {scope.date_to or 'today'}")
    if scope.date_presence != base.date_presence and scope.date_presence != "any":
        parts.append("ads " + ("with" if scope.date_presence == "known" else "without") + " a publication date")
    return " and ".join(parts) or "the current selection"


def empty_scope_note(question, filters):
    """Server-written scope of a search that found no stored records at all.

    "Insufficient evidence" alone reads as a system failure; stating what was
    searched shows the answer is a finding about the collection (P66-15).
    """
    scope = _plain_scope(filters, Filters(dataset=filters.dataset))
    collection = {"native": "native ads", "social": "social posts"}.get(filters.dataset, "both collections")
    if re.search(r"[一-鿿]", question):
        return f"检索范围内没有找到相符的记录（{collection}；{scope}）。"
    return f"No stored records matched the searched scope ({collection}; {scope})."


def _cited_record_count(result):
    evidence = {item.evidence_id: item for item in result.evidence}
    return len({getattr(evidence.get(c.evidence_id), "record_id", None) for c in result.citations} - {None})


def examples_note(question, result):
    """Server-written scope of a list or count answer built from retrieved passages.

    Retrieval reads the most relevant few ads, so a "which ads ..." answer is a
    set of supported examples. Readers take it as the complete list unless the
    answer says otherwise (C24: 4-6 ads cited where 6-65 contain the terms).
    """
    count = _cited_record_count(result)
    # Plain wording (user, 2026-10-19); the limit itself is unchanged.
    if re.search(r"[一-鿿]", question):
        return f"以上是最相关广告中的 {count} 个例子，不是完整名单，可能还有其他符合的广告。"
    return (f"These are {count} example{'s' if count != 1 else ''} from the most relevant ads, not a complete "
            "list; other ads may also match.")


def _titled_records(db, question, filters):
    """Records whose full title (20+ characters) the question names, with their collection."""

    def normal(text):
        return " ".join(re.findall(r"\w+", text.lower()))

    query = normal(question)
    return [(r["record_id"], r.get("dataset", filters.dataset)) for r in db.public_rows(filters)
            if len(normal(r["title"])) >= 20 and normal(r["title"]) in query]

class Service:
    def __init__(self, settings, db=None, rag=None, research_agent=None, claims_store=None, web_research=None):
        self.settings = settings
        self.db = db or Database(settings.database_url, read_cache=True)
        self.rag = rag or Rag(self.db, settings)
        self.research_agent = research_agent
        self.claims_store = claims_store
        self.web_research = web_research

    def media_evidence(self, filters: Filters, *, query, media_types=None, limit=5):
        """Read frozen operator-mounted material; never execute OCR or a model."""
        return self._media_reader().read(query=query, media_types=media_types or ["image", "video"],
                                         limit=limit, filters=filters)

    def _media_reader(self):
        """Capture fixed operator configuration for the entire answer request."""
        from .media_reader import MediaEvidenceReader

        return MediaEvidenceReader(
            bundle_path=getattr(self.settings, "media_bundle_path", ""),
            bundle_sha256=getattr(self.settings, "media_bundle_sha256", ""),
            asset_root=getattr(self.settings, "media_asset_root", ""),
            current_record=lambda filters, record_id: self.db.versioned_record(filters, record_id),
            show_source_links=self.settings.show_source_links,
        )

    def content_matches(self, filters: Filters, *, question_id, offset=0, limit=20):
        """Read operator-selected reviewed decisions, never rerun classification."""
        from .evaluation_mask import require_evaluation

        require_evaluation()
        from .content_assessment import QUESTION_IDS
        from .content_publication import load_publication, read_match_page

        if question_id not in QUESTION_IDS:
            raise ValueError("Use one of the fixed client question IDs Q01–Q24")
        if type(offset) is not int or not 0 <= offset <= 10000 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Content page bounds are invalid")
        if filters.dataset != "native":
            return {"status": "clarify", "available": False,
                    "message": "These 24 reviewed content questions cover native advertising. Select the native collection before reading this list.",
                    "records": [], "model_calls": 0}
        configured = [getattr(self.settings, field, "") for field in (
            "content_publication_path", "content_publication_sha256", "content_review_sha256")]
        empty = {"available": False, "publication_version": None, "review_version": None,
                 "question": {"question_id": question_id}, "records": [], "totals": None,
                 "coverage": {"classification_complete": False}, "offset": offset, "limit": limit,
                 "model_calls": 0, "filters": filters.model_dump(mode="json")}
        if not all(configured):
            return {**empty, "status": "unavailable", "reason": "publication_not_configured",
                    "message": "Reviewed content decisions are awaiting publication. Missing results are not negative findings."}
        try:
            publication = load_publication(*configured)
        except Exception:
            return {**empty, "status": "unavailable", "reason": "publication_validation_failed",
                    "message": "The reviewed content publication cannot be verified. No draft decisions are substituted."}
        try:
            sources = self.db.content_match_sources(filters)
            projected_sources = [{**row, "publicmetadata": {
                key: row.get(key) for key in (
                    "title", "publisher", "sponsor", "date", "source_date", "effective_date", "date_basis",
                    "inferred_date", "inferred_tier", "keyword", "platform", "account", "url", "archive_url",
                )}} for row in sources]
            result = read_match_page(publication, projected_sources, question_id, offset=offset, limit=limit,
                                     show_source_links=self.settings.show_source_links)
            from .evaluate import canonical_digest

            source_identity = [{
                **{key: row.get(key) for key in (
                    "record_id", "dataset", "version_id", "body_hash", "retrievable", "retrieval_ranges", "retrieval_end",
                    "title", "publisher", "sponsor", "date", "effective_date", "date_basis", "url", "archive_url",
                )},
                "actual_body_sha256": hashlib.sha256(row["body"].encode("utf-8")).hexdigest()
                    if isinstance(row.get("body"), str) else None,
            } for row in sorted(sources, key=lambda row: row["record_id"])]
            result["source_scope_sha256"] = canonical_digest(source_identity)
        except Exception:
            return {**empty, "status": "unavailable", "reason": "current_source_read_unavailable",
                    "message": "Current source coverage cannot be verified. Refresh the selection or try again later."}
        return {**result, "filters": filters.model_dump(mode="json"), "model_calls": 0}

    def claims_matches(self, filters: Filters, *, nc_ids=None, sc_ids=None, taxonomy=None,
                       review_state=None, offset=0, limit=20):
        """Read published NC/SC assignments, independently of historical labels.

        The store rechecks current source versions and exact quote positions in
        one read-only snapshot. This adapter applies the public link policy and
        preserves its positive-only coverage; no classification is run here.
        """
        from .claims_store import ClaimsStore

        store = self.claims_store if self.claims_store is not None else ClaimsStore(self.db)
        try:
            result = deepcopy(store.matches(filters, nc_ids=nc_ids, sc_ids=sc_ids,
                                            taxonomy=taxonomy, review_state=review_state,
                                            offset=offset, limit=limit))
        except ValueError:
            raise
        except Exception:
            # Driver diagnostics may include credentials or source paths.
            result = {"available": False, "claims_version": None, "total_records": 0,
                      "total_matches": 0, "records": [], "offset": offset, "limit": limit}
        result.setdefault("meaning", "Published taxonomy assignments; not independent fact checking.")
        result.setdefault("coverage", "Records with published matches only; unmatched records are not classified negatives.")
        result["filters"] = filters.model_dump(mode="json")
        result["status"] = "ok" if result.get("available") else "unavailable"
        result["model_calls"] = 0
        result["claims_status"] = "published_assignments_only"
        if not result.get("available"):
            result["message"] = "Published CLAIMS2 results are unavailable. Unmatched records are not classified negatives."
        refs = []
        for record in result.get("records", []):
            claims = record.get("claims", [])
            for claim in claims:
                for field in ("url", "archive_url"):
                    claim[field] = safe_url(claim.get(field)) if self.settings.show_source_links else ""
                refs.append({key: claim.get(key) for key in (
                    "candidate_key", "record_id", "version_id", "body_hash", "dataset", "start", "end",
                    "taxonomy_version", "review_version", "run_id",
                )})
            if claims:
                record.update({key: claims[0].get(key) for key in (
                    "title", "publisher", "sponsor", "dataset", "date", "url", "archive_url",
                )})
        result["source_refs"] = refs
        return result

    def browse(self, filters):
        return self._public_rows(self.db.public_rows(filters))

    def _public_rows(self, rows):
        for row in rows:
            for key in ["url", "archive_url"]:
                row[key] = (
                    safe_url(row.get(key)) if self.settings.show_source_links else ""
                )
        return rows

    def page(self, filters, offset=0, limit=20, sort_by="date", descending=True):
        result = self.db.public_page(filters, offset, limit, sort_by, descending)
        result["rows"] = self._public_rows(result["rows"])
        return result

    def dashboard(self, filters, offset=0, limit=20, sort_by="date", descending=True):
        result = self.db.dashboard(filters, offset, limit, sort_by, descending)
        result["page"]["rows"] = self._public_rows(result["page"]["rows"])
        return result

    def social_source_state_version(self, filters):
        """Read the current selection fingerprint without rebuilding its charts."""
        return self.db.social_source_state_version(filters)

    def network(self, filters, limit=60):
        return self.db.network(filters, limit)

    def knowledge_graph(self, filters, offset=0, limit=5, record_details=None):
        """A typed, provenance-bearing graph derived from current stored versions.

        No model inference or writes occur here. Entity IDs represent exact
        source identities; aliases need a separately reviewed resolution policy.
        """
        from .knowledge_graph import build_graph

        page = self.db.knowledge_page(filters, offset=offset, limit=limit)
        attachments = {}
        if record_details is not None and self.settings.show_source_links:
            for row in page["rows"]:
                detail = record_details.get(row["record_id"])
                # Attachments are optional and independently read. Do not join
                # a newly published version to the graph's earlier snapshot.
                if detail and detail.get("version_id") == row["version_id"]:
                    attachments[row["record_id"]] = detail.get("attachments", [])
        graph = build_graph(page["rows"], links_enabled=self.settings.show_source_links,
                            attachments_by_record=attachments, claims2=page.get("claims2"))
        graph["coverage"] = {
            "total_records": page["total"], "shown_records": len(page["rows"]),
            "offset": page["offset"], "limit": page["limit"],
        }
        graph["filters"] = filters.model_dump(mode="json")
        public_fields = ("record_id", "version_id", "dataset", "title", "date",
                         "sponsor", "publisher", "retrievable", "url", "archive_url")
        graph["records"] = self._public_rows([
            {key: row.get(key) for key in public_fields} for row in page["rows"]
        ])
        return graph

    def statistics(self, filters):
        return self.db.dashboard(filters)["stats"]

    def facets(self, dataset):
        return self.db.facets(dataset)

    def knowledge_map(self, filters):
        """Full selection overview with record-backed derived associations."""
        from .knowledge_map import build_collection_map

        if filters.dataset != "native":
            raise ValueError("The collection knowledge graph supports native records")
        rows = self.db.knowledge_map_rows(filters)
        graph = build_collection_map(rows, links_enabled=self.settings.show_source_links)
        graph["filters"] = filters.model_dump(mode="json")
        return graph

    def health(self):
        try:
            return self.db.health()
        except Exception:
            return {
                "status": "unavailable",
                "record_counts": {},
                "data_version": "unavailable",
            }

    def _public_evidence(self, evidence):
        return [
            e.model_copy(
                update={
                    "url": safe_url(e.url) if self.settings.show_source_links else "",
                    "archive_url": safe_url(e.archive_url)
                    if self.settings.show_source_links
                    else "",
                }
            )
            for e in evidence
        ]

    def search(self, question, filters, limit=5):
        if not 1 <= len(question.strip()) <= 2000:
            return []
        filters = self._title_scope(question, filters)
        return self._public_evidence(
            self.db.search(question, filters, limit=min(limit, 10))
        )

    def search_report(self, question, filters, limit=5):
        """Free search with keyword coverage of the same filtered index snapshot."""
        if not 1 <= len(question.strip()) <= 2000:
            return {
                "evidence": [],
                "diagnostics": {
                    "status": "unavailable", "operator": "OR", "terms": [],
                    "reason": "Enter a question of 1–2,000 characters.",
                },
            }
        filters = self._title_scope(question, filters)
        report = self.db.search_report(question, filters, limit=min(limit, 10))
        report["evidence"] = self._public_evidence(report["evidence"])
        return report

    def _title_records(self, question, filters):
        return _titled_records(self.db, question, filters)

    def _title_scope(self, question, filters):
        """A full explicitly named title narrows retrieval within existing filters."""
        # Uses only self.db: scripts/compare_retrieval_chunks.py passes a stand-in.
        matches = [record_id for record_id, _ in _titled_records(self.db, question, filters)]
        return (
            filters.model_copy(update={"record_ids": matches}) if matches else filters
        )

    def _statistics_answer(self, plan, *, available_datasets=None):
        """SQL totals and examples share a read-only snapshot per collection.

        Every eligible record contributes, including records without searchable
        text. Native articles and social posts retain separate counting units.
        Only public fields are returned; source categories are never merged.
        """
        from .analytics import sponsor_display

        if plan.kind == "share":
            return self._share_statistics_answer(plan)
        filters = plan.filters
        if (filters.accounts or plan.group_by == "accounts") and filters.dataset != "social":
            raise ValueError("Account filters and grouping require the social collection")
        datasets = ["native", "social"] if filters.dataset == "all" else [filters.dataset]
        missing = []
        if available_datasets is not None:
            missing = [dataset for dataset in datasets if dataset not in available_datasets]
            datasets = [dataset for dataset in datasets if dataset in available_datasets]
            if not datasets:
                raise ValueError("Statistics require an admitted collection")
        collections, groups, records, tiers = [], [], [], {}
        for dataset in datasets:
            snapshot = self.dashboard(filters.model_copy(update={"dataset": dataset}), limit=10)
            stats = snapshot["stats"]
            for tier, n in (stats.get("inferred_dates") or {}).items():
                tiers[tier] = tiers.get(tier, 0) + n
            collections.append({
                "dataset": dataset, "total": stats["total"],
                "retrievable": stats["retrievable"], "unknown_dates": stats["unknown_dates"],
            })
            if plan.group_by:
                for group in stats[plan.group_by]:
                    groups.append({
                        "dataset": dataset, "name": group["name"], "count": group["count"],
                        "display_name": sponsor_display(group["name"])
                        if plan.group_by == "sponsors" else group["name"],
                    })
            fields = ("record_id", "version_id", "dataset", "title", "date", "source_date", "effective_date", "date_basis",
                      "inferred_date", "inferred_tier", "publisher", "sponsor", "platform", "account", "url", "archive_url", "retrievable")
            if dataset == "social":
                fields += ("collection_scope", "count_unit", "paid_ad_status")
            records.extend({field: row.get(field) for field in fields} for row in snapshot["page"]["rows"])
        totals = "; ".join(
            f"{item['total']:,} eligible {'native ad records' if item['dataset'] == 'native' else 'company social posts'}"
            for item in collections
        )
        if plan.kind == "count":
            text = f"{totals} match this question and the active filters."
        else:
            dimension = {"publishers": "publishers", "sponsors": "source-listed company affiliations"
                         if filters.dataset == "social" else "source-listed sponsors / organizations",
                         "platforms": "platforms", "accounts": "source-listed account names"}[plan.group_by]
            names = {group["name"] for group in groups if group["name"] != "(Unknown)"}
            text = f"{len(names):,} {dimension} appear in {totals} within this selection. Every category and its count is listed below."
        if not any(item["total"] for item in collections):
            text += " No eligible records match; this does not establish that no such advertisements exist elsewhere."
        scope_notes = list(plan.scope_notes)
        if missing:
            names = ", ".join("native advertising" if dataset == "native" else "company social posts" for dataset in missing)
            missing_note = (f"The {names} collection has no admitted records and is omitted; "
                            "this is not a zero advertisement count.")
            text += " " + missing_note
            scope_notes.append(missing_note)
        note = _date_inference_note(filters.include_inferred_dates, tiers)
        if filters.date_presence == "missing" and filters.include_inferred_dates:
            # "Without a date" after supplementing differs from the source gap; say both.
            source_missing = sum(
                self.dashboard(filters.model_copy(update={"dataset": dataset, "include_inferred_dates": False}),
                               limit=1)["stats"]["total"] for dataset in datasets)
            remaining = sum(item["total"] for item in collections)
            if source_missing > remaining:
                note += (f" {source_missing:,} records have no publication date in the source data; "
                         f"{source_missing - remaining:,} of them have a supplemented date, so {remaining:,} "
                         "remain without any date.")
        return Answer(
            status="answered", answer=text + note, answer_mode="statistics",
            structured_result={
                "kind": plan.kind, "method": "database", "group_by": plan.group_by,
                "filters": filters.model_dump(mode="json"), "collections": collections,
                "groups": groups, "records": records, "scope_notes": scope_notes,
                **({"missing_datasets": missing} if missing else {}),
                "date_inference": {"used": filters.include_inferred_dates, "tiers": tiers, "note": note.strip()},
            },
        )

    def _cites_inferred_dates(self, result, filters):
        ids = sorted({item.record_id for item in [*(result.evidence or []), *(result.media_evidence or [])]})
        if not ids:
            return False
        try:
            rows = self.db.public_rows(filters.model_copy(update={"record_ids": ids}))
        except Exception:
            return None  # Unknown: keep the answer and add a conservative notice.
        return any(str(row.get("date_basis") or "").startswith("inferred:") for row in rows)

    def _share_statistics_answer(self, plan):
        """Compute numerator and trusted denominator in one snapshot per dataset.

        Reuse the database's complete eligibility/filter query rather than
        reproducing its annotation or unknown-date rules in Python. The caller's
        scope is bound before any target filters, and no model supplies a count.
        """
        numerator, denominator = plan.filters, plan.denominator_filters
        if not isinstance(numerator, Filters) or not isinstance(denominator, Filters) or plan.group_by:
            raise ValueError("A percentage needs a trusted denominator and no grouping")
        validate_share_scope(numerator, denominator)
        datasets = ("native", "social") if numerator.dataset == "all" else (numerator.dataset,)
        collections, records, share_tiers, denominator_inferred = [], [], {}, 0
        health = self.health()
        if health.get("status") != "ok":
            raise ValueError("Percentage statistics require a loaded collection")
        counts = health.get("countable_record_counts", health.get("record_counts", {}))
        missing = [dataset for dataset in datasets if not counts.get(dataset)]
        fields = ("record_id", "version_id", "dataset", "title", "date", "source_date", "effective_date", "date_basis",
                  "inferred_date", "inferred_tier", "publisher",
                  "sponsor", "platform", "account", "url", "archive_url", "retrievable")
        for dataset in datasets:
            if dataset in missing:
                continue
            base_query, base_params = self.db._public_query(denominator.model_copy(update={"dataset": dataset}))
            target_query, target_params = self.db._public_query(numerator.model_copy(update={"dataset": dataset}))
            # Identical record/version membership also enforces the subset at
            # the SQL boundary; both queries use the same MVCC snapshot.
            prefix = f"WITH denominator AS ({base_query}), target AS ({target_query}), numerator AS (SELECT t.* FROM target t JOIN denominator d USING(record_id,version_id)) "
            params = [*base_params, *target_params]
            with self.db.connect() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                counts = conn.execute(prefix + """SELECT count(*) AS numerator,
                    count(*) FILTER (WHERE date_basis LIKE 'inferred:%%' AND inferred_tier='A') AS inferred_a,
                    count(*) FILTER (WHERE date_basis LIKE 'inferred:%%' AND inferred_tier='B') AS inferred_b,
                    count(*) FILTER (WHERE date_basis LIKE 'inferred:%%' AND inferred_tier='C') AS inferred_c,
                    count(*) FILTER (WHERE retrievable) AS retrievable,
                    (SELECT count(*) FROM denominator WHERE date_basis LIKE 'inferred:%%') AS denominator_inferred,
                    count(*) FILTER (WHERE effective_date IS NULL OR effective_date='') AS unknown_dates,
                    (SELECT count(*) FROM denominator) AS denominator FROM numerator""", params).fetchone()
                rows = conn.execute(prefix + "SELECT * FROM numerator ORDER BY effective_date DESC NULLS LAST,record_id LIMIT 10", params).fetchall()
            n, d = counts["numerator"], counts["denominator"]
            denominator_inferred += counts.get("denominator_inferred") or 0
            for tier in "ABC":
                if counts.get(f"inferred_{tier.lower()}"):
                    share_tiers[tier] = share_tiers.get(tier, 0) + counts[f"inferred_{tier.lower()}"]
            collections.append({
                "dataset": dataset, "total": n, "retrievable": counts["retrievable"],
                "unknown_dates": counts["unknown_dates"], "numerator": n, "denominator": d,
                "percentage": 100 * n / d if d else None,
                "percentage_status": "defined" if d else "empty_selection",
            })
            records.extend({field: row.get(field) for field in fields} for row in self._public_rows(rows))
        basis = getattr(plan, "denominator_basis", None) or "current_selection_before_question_targets"
        note = ("Each percentage uses the comparison group named in the question, within the current selection."
                if basis == "question_comparison_group" else
                "Each percentage uses its collection's eligible records in the current selection before question targets.")
        data = {
            "kind": "share", "method": "database", "group_by": None,
            "filters": numerator.model_dump(mode="json"),
            "denominator_filters": denominator.model_dump(mode="json"),
            "denominator_basis": basis,
            "collections": collections, "groups": [], "records": records,
            "scope_notes": [*plan.scope_notes,
                note + " Unsearchable records still count; a zero denominator is undefined."],
        }
        if missing:
            data["scope_notes"].append("Unloaded collections are omitted, not reported as zero advertisements or zero percent.")
        used = numerator.include_inferred_dates or denominator.include_inferred_dates
        note = _date_inference_note(used, share_tiers).strip()
        if used and denominator_inferred:
            note = (note + " " if note else "") + (f"The comparison group includes {denominator_inferred:,} "
                                                   "records dated by an unreviewed estimate.")
        data["date_inference"] = {"used": used, "tiers": share_tiers,
                                  "denominator_inferred": denominator_inferred, "note": note}
        trusted = getattr(plan, "trusted_filters", None) or denominator
        return self._tool_statistics_answer(data, base_filters=trusted)

    def answer(self, question, filters, visitor, progress=None):
        start = time.monotonic()
        # A default must never override a caller's explicit source-only choice.
        if "include_inferred_dates" not in filters.model_fields_set:
            filters = filters.model_copy(update={"include_inferred_dates": True})
        token = _FINAL_AUDIT_CONTEXT.set(True)
        try:
            if (getattr(self.settings, "research_agent_enabled", False)
                    or getattr(self.settings, "question_intent_enabled", False)):
                result = self._answer_with_tools(question, filters, visitor, progress=progress)
            else:
                result = self._answer_legacy(question, filters, visitor, progress=progress)
            result = self._ensure_answer(question, filters, visitor, result, progress)
            self._record_web_trace(result, question, filters)
            result.latency_ms = int((time.monotonic() - start) * 1000)
        finally:
            _FINAL_AUDIT_CONTEXT.reset(token)
        if 1 <= len(question.strip()) <= 2000:
            self._save_supplement(question, filters, result)
        return result

    def _ensure_answer(self, question, filters, visitor, result, progress=None):
        """Always give an answer: when the collection cannot, supplement from the web.

        User decision (2026-10-05): every question gets an answer. A
        clarification, unresolved scope or missing source field stays visible
        as the stated reason, and the web supplement is labelled as not coming
        from the advertising database, with the provider's source links.
        Integrity failures below are never covered up; budget and rate limits
        still apply, and a failed web search never invents an answer.
        """
        from .research_agent import research_failure_status

        partial_metadata = (result.status == "answered"
                            and result.answer_mode == "tools"
                            and (result.structured_result or {}).get("kind") == "original_metadata"
                            and (result.structured_result or {}).get("complete") is False)
        if result.status != "insufficient_evidence" and not partial_metadata:
            return result
        if _COLLECTION_ONLY.search(question):
            # The user asked for the collection only: its gap is the answer.
            return result
        # A named sponsor/account absent from the collection is the answer to a
        # question restricted to it; web pages about other companies are not.
        protected = {"citation_mismatch", "quote_too_long", "invalid_claim_count", "named_source_not_in_collection",
                     "evidence_version_mismatch", "answer_structure_mismatch", "content_publication_unavailable",
                     "collection_unavailable", "statistics_unavailable", "historical_source_state_unverified",
                     "media_evidence_mismatch", "duplicate_evidence_identity"}
        if (not 1 <= len(question.strip()) <= 2000
                or result.failure_reason.startswith("data_changed") or result.failure_reason in protected
                or research_failure_status(result.failure_reason)):
            return result
        research = result.external_research or {}
        # Any prior outcome is a completed attempt, including failures and limits.
        # The evidence route may already have searched: do not charge it again.
        if not research:
            before = self.health()
            attempt = self._search_external(question, filters, visitor, progress=progress)
            if attempt.get("status") == "disabled" or attempt.get("reason") == "scope_not_supported":
                return result  # No lookup happened; the collection answer stands unchanged.
            research = attempt
            result.cost_usd += research.get("cost_usd", 0.0)
            result.external_research = research
            after = self.health()
            version = before.get("data_version")
            if before.get("status") == "ok" and version and version != "unavailable":
                result.research_trace["data_version"] = version
                if after.get("status") != "ok" or after.get("data_version") != version:
                    return self._withhold_changed_web_result(result)
        if research.get("status") != "ok":
            return result
        sources = [s for s in research.get("sources") or []
                   if isinstance(s, dict) and s.get("url") and s.get("supports_generated_paragraph", True)]
        if not sources or not str(research.get("summary") or "").strip():
            result.external_research = {**research, "status": "unresolved", "reason": "no_cited_answer"}
            return result
        reason = (result.answer or "").strip()
        research["collection_answer"] = {
            "status": result.status, "answer_mode": result.answer_mode,
            "answer": result.answer, "failure_reason": result.failure_reason, "complete": False,
        }
        # `answered` remains the legacy delivery status. It cannot certify a
        # collection task when the supplied content is an external supplement.
        result.research_trace["collection_completion"] = {
            "complete": False, "status": "incomplete", "answer_status": result.status,
            "answer_mode": result.answer_mode, "failure_reason": result.failure_reason,
        }
        result.research_trace["answer_provenance"] = {
            "source_kind": "external_web", "role": "supplement",
            "status_meaning": "response_available", "collection_task_completed": False,
        }
        result.status = "answered"
        result.answer_mode = "web_supplement"
        # API, MCP and exports receive the findings and links, not only UI metadata.
        result.answer = WEB_SUPPLEMENT_LEAD + "\n\n" + (research.get("summary") or "").strip()
        if sources:
            result.answer += "\n\nWeb sources:\n" + "\n".join(
                f"[{s.get('source_id')}] {s.get('title') or s['url']} - {s['url']}" for s in sources)
        result.answer += "\n\nThe collection task remains incomplete; the web findings are external context."
        if reason:
            result.answer += "\n\nWhy the collection could not answer: " + reason
        return result

    @staticmethod
    def _withhold_changed_web_result(result):
        external = result.external_research or {}
        trace = deepcopy(result.research_trace)
        trace["external_web"] = {key: external.get(key) for key in (
            "source_kind", "cost_usd", "model_calls", "searched_at", "audit",
        ) if key in external}
        trace["external_web"].update(status="withheld", reason="data_changed_during_web_research")
        return Answer(status="service_unavailable",
                      answer="The collection changed during research. Please submit the question again.",
                      failure_reason="data_changed_during_web_research", cost_usd=result.cost_usd,
                      research_trace=trace)

    @staticmethod
    def _withhold_changed_media_result(result):
        trace = deepcopy(result.research_trace)
        external = result.external_research or {}
        if external and external.get("status") != "disabled":
            trace["external_web"] = {key: external.get(key) for key in (
                "source_kind", "cost_usd", "model_calls", "searched_at", "audit",
            ) if key in external}
            trace["external_web"].update(status="withheld", reason="media_evidence_mismatch")
        return Answer(status="service_unavailable",
                      answer="Saved media changed during research. Please submit the question again.",
                      failure_reason="media_evidence_mismatch", cost_usd=result.cost_usd,
                      research_trace=trace)

    @staticmethod
    def _record_web_trace(result, question, filters):
        external = result.external_research or result.research_trace.get("external_web")
        if not external or external.get("status") == "disabled" or external.get("reason") == "scope_not_supported":
            return
        trace = deepcopy(result.research_trace)
        trace.setdefault("original_question", question)
        trace.setdefault("base_filters", filters.model_dump(mode="json"))
        trace.setdefault("model_calls", [])
        trace["cost_usd"] = result.cost_usd
        trace["external_web"] = {key: external.get(key) for key in (
            "status", "reason", "source_kind", "cost_usd", "model_calls", "searched_at", "audit",
        ) if key in external}
        # The lower evidence path may already have recorded the same lookup.
        trace["tools"] = [step for step in trace.get("tools", [])
                          if (step.get("tool") or step.get("name")) != "search_external_sources"]
        trace["tools"].append({
            "tool": "search_external_sources", "status": external.get("status"),
            "source_kind": "external_web", "cost_usd": external.get("cost_usd", 0),
            "data_refs": [{"source_id": s.get("source_id"), "url": s.get("url")}
                          for s in external.get("sources", [])],
        })
        result.research_trace = trace

    def _save_supplement(self, question, filters, result):
        try:
            version = result.research_trace.get("data_version") or self.health().get("data_version", "unavailable")
            self.db.save_answer(question, filters, result, version)
        except Exception:
            log.warning("Final answer audit log unavailable")

    def _answer_with_tools(self, question, filters, visitor, progress=None):
        """Understand the question before accessing constrained collection tools."""
        from .research_agent import ResearchAgent, _cjk_dominant_query
        from .research_tools import ToolCatalog

        start = time.monotonic()
        trusted_filters = filters.model_copy(deep=True)
        if not 1 <= len(question.strip()) <= 2000:
            return Answer(status="insufficient_evidence", answer_mode="clarification",
                          answer="Please enter a question of 1–2,000 characters.")
        run = None
        downstream_cost = 0.0
        version = "unavailable"
        try:
            _progress(progress, "database")
            before = self.health()
            candidate_version = before.get("data_version")
            if before.get("status") != "ok" or not isinstance(candidate_version, str) or not candidate_version or candidate_version == "unavailable":
                raise ValueError("A healthy source version is required for question tools")
            version = candidate_version
            catalog = ToolCatalog(self, filters)
            agent = self.research_agent or ResearchAgent(
                self.rag, catalog,
                intent_enabled=getattr(self.settings, "question_intent_enabled", False),
                max_output_tokens=1600 if getattr(self.settings, "question_intent_enabled", False) else 900,
                repairs=1,
            )
            _progress(progress, "interpreting")
            run = agent.run(question, filters, visitor,
                            **({"progress": lambda stage: _progress(progress, stage)} if progress else {}))
            data = run.result
            if run.route == "statistics":
                result = self._tool_statistics_answer(data, base_filters=filters)
            elif run.route == "evidence":
                narrowed = Filters.model_validate(data["filters"])
                validate_share_scope(narrowed, filters)
                narrowed = _list_over_selection(question, narrowed, filters, data)
                # Question language and wording remain intact for the cited answer.
                result = self._answer_evidence(question, narrowed, visitor,
                                               search_query=data.get("search_query") or data.get("query") or question, audit=False,
                                               declared_shape=data.get("answer_shape"),
                                               relation_listing=data.get("relation_listing"),
                                               **({"retrieval_groups": data["retrieval_groups"]} if data.get("retrieval_groups") else {}),
                                               **({"progress": progress} if progress else {}))
            elif run.route == "metadata":
                result = self._tool_metadata_answer(data)
            elif run.route == "composite":
                result = self._tool_composite_answer(
                    {**data, "failure_reason": run.failure_reason or data.get("failure_reason", "")},
                    filters, data_version=version, visitor=visitor, progress=progress,
                )
            elif run.route in {"graph", "sources", "record"}:
                source_choice = data.get("text_status") == "source_observation_selection"
                result = Answer(
                    status="insufficient_evidence" if data.get("text_status") == "paused" or source_choice else "answered", answer_mode="tools",
                    answer=(data.get("message") or "This company post's text is paused for review; source metadata is shown below. No content interpretation is supplied."
                            if data.get("text_status") == "paused" or source_choice else "Source records and relationships from the current collection are shown below."),
                    structured_result={"kind": run.route, **data},
                )
            elif run.route == "claims":
                result = self._tool_claims_answer(data)
            elif run.route == "content_matches":
                result = self._tool_content_answer(data)
            elif run.route == "clarify":
                result = Answer(status="insufficient_evidence", answer_mode="clarification",
                                answer=data.get("message") or "Please clarify the collection, entity or date range.",
                                failure_reason=run.failure_reason)
            elif run.route == "limited":
                # A rate or budget limit is expected behaviour, not an outage.
                result = Answer(
                    status="limited", answer_mode="tools", failure_reason=run.failure_reason,
                    answer="Your question limit or the API budget has been reached. Browsing and keyword search remain available; please try again later.",
                )
            else:
                result = Answer(
                    status="service_unavailable", answer_mode="tools",
                    failure_reason=run.failure_reason,
                    answer="Question understanding is temporarily unavailable. Browse the collection or use keyword search.",
                )
            collection_first = ""
            if result.status == "insufficient_evidence" and run.route in {"clarify", "composite"} \
                    and _collection_search_applies(run):
                # The plan or title lookup failed, not the collection: search the
                # saved text with the original question before any web lookup.
                # English search terms the model already wrote match the English
                # index better than a question in another language.
                fallback_query = next((
                    item["arguments"]["query"] for item in reversed(run.tool_trace)
                    if item.get("tool") == "search_records" and isinstance(item.get("arguments"), dict)
                    and isinstance(item["arguments"].get("query"), str) and item["arguments"]["query"].strip()
                    and not _cjk_dominant_query(item["arguments"])), question)
                try:
                    searched = self._answer_evidence(question, filters, visitor, search_query=fallback_query, audit=False,
                                                     **({"progress": progress} if progress else {}))
                except Exception:
                    # Best effort only: a failed fallback never replaces the explanation.
                    log.debug("Collection-first search unavailable", exc_info=True)
                    searched = None
                if searched is not None and searched.status == "answered":
                    collection_first, result = run.failure_reason or run.route, searched
            downstream_cost = result.cost_usd
            after = self.health()
            if after.get("status") != "ok" or after.get("data_version") != version:
                result = Answer(status="service_unavailable", answer_mode="tools",
                                failure_reason="data_changed_during_tool_research",
                                answer="The collection changed while processing this question. Please submit it again.",
                                cost_usd=result.cost_usd, research_trace=result.research_trace)
            elif not self._historical_tool_result_current(data, trusted_filters, answered=result.status == "answered"):
                result = Answer(status="service_unavailable", answer_mode="tools",
                                failure_reason="historical_source_state_unverified",
                                answer="The historical source-state selection cannot be verified. Refresh the selection and submit the question again.",
                                cost_usd=result.cost_usd, research_trace=result.research_trace)
            elif result.answer_mode == "statistics" and result.structured_result is not None:
                # Bind later record pagination to the same source snapshot that
                # passed the query's before/after guard, not a model-supplied ID.
                result.structured_result = {**result.structured_result, "data_version": version}
            result.cost_usd += run.cost_usd
            downstream_trace = result.research_trace
            result.research_trace = run.audit()
            result.research_trace["data_version"] = version
            if collection_first:
                result.research_trace["collection_first_fallback"] = collection_first
            for key in ("external_web", "media_retrieval", "generation_failure", "list_screening", "coverage_note",
                        "list_decision", "content_zones", "content_reading"):
                if key in downstream_trace:
                    result.research_trace[key] = downstream_trace[key]
            if result.external_research:
                external = result.external_research
                result.research_trace["external_web"] = {key: external.get(key) for key in (
                    "status", "source_kind", "cost_usd", "model_calls", "searched_at", "audit",
                ) if key in external}
                result.research_trace["tools"].append({
                    "tool": "search_external_sources", "status": external.get("status"),
                    "source_kind": "external_web", "cost_usd": external.get("cost_usd", 0),
                    "data_refs": [{"source_id": s.get("source_id"), "url": s.get("url")}
                                  for s in external.get("sources", [])],
                })
        except Exception as exc:
            log.warning("Question understanding failed: %s", type(exc).__name__)
            result = Answer(status="service_unavailable", answer_mode="tools",
                            answer="Question understanding is temporarily unavailable. Browse the collection or use keyword search.",
                            failure_reason="research_agent_unavailable",
                            cost_usd=downstream_cost + (run.cost_usd if run else 0))
            if run:
                result.research_trace = run.audit()
        result.latency_ms = int((time.monotonic() - start) * 1000)
        if not _FINAL_AUDIT_CONTEXT.get():
            try:
                self.db.save_answer(question, filters, result, version)
            except Exception:
                log.warning("Tool research audit log unavailable")
        return result

    def _tool_composite_answer(self, data, base_filters, *, data_version=None, visitor=None, progress=None):
        """Combine checked read results, preserving any unfinished question part.

        A content part arrives as a search result and is answered here with its
        own cited answer; the plan's other parts were read after it, not dropped.
        """
        from .research_agent import research_failure_status

        parts, messages, incomplete = [], [], []
        reason = data.get("failure_reason") or ""
        complete = bool(data.get("complete")) and not data.get("pending_parts") and not reason
        blocked_status = research_failure_status(reason)
        if data.get("failure_status") in {"limited", "service_unavailable"}:
            blocked_status = data["failure_status"]
        cited, cost = None, 0.0
        for part in data.get("parts", []):
            item, route = part["result"], part["route"]
            if route != "evidence" and not self._historical_tool_result_current(item, base_filters, answered=True):
                raise ValueError("A compound source-state read is not current")
            if route == "evidence":
                # The cited answer re-checks the data version itself.
                narrowed = Filters.model_validate(item["filters"])
                validate_share_scope(narrowed, base_filters)
                answer = self._answer_evidence(part["question_part"], narrowed, visitor,
                                               search_query=item.get("search_query") or part["question_part"],
                                               audit=False, declared_shape=item.get("answer_shape"),
                                               **({"progress": progress} if progress else {}))
                cost += answer.cost_usd
                cited = answer if cited is None else False
            elif route == "statistics":
                answer = self._tool_statistics_answer(item, base_filters=base_filters)
                if data_version and answer.structured_result is not None:
                    answer.structured_result = {**answer.structured_result, "data_version": data_version}
            elif route == "metadata":
                answer = self._tool_metadata_answer(item)
            elif route == "claims":
                answer = self._tool_claims_answer(item)
            elif route in {"graph", "sources", "record"}:
                paused = item.get("text_status") in {"paused", "source_observation_selection"}
                answer = Answer(status="insufficient_evidence" if paused else "answered", answer_mode="tools",
                                answer=item.get("message") or "The selected source records and relationships are available below.",
                                structured_result={"kind": route, **item})
            else:
                raise ValueError("Unsupported compound read route")
            part_complete = (answer.status == "answered"
                             and (answer.structured_result or {}).get("complete", True))
            complete = complete and part_complete
            if not part_complete:
                incomplete.append({"question_part": part["question_part"], "dataset": part["dataset"],
                                   "route": route, "failure_reason": answer.failure_reason})
                if answer.status in {"limited", "service_unavailable"} and not blocked_status:
                    blocked_status, reason = answer.status, answer.failure_reason
            parts.append({"question_part": part["question_part"], "dataset": part["dataset"],
                          "route": route, "answer": answer.model_dump(mode="json")})
            messages.append(part["question_part"] + "\n" + answer.answer)
        pending = data.get("pending_parts") or []
        if pending:
            messages.append("Still unresolved:\n" + "\n".join(part["question_part"] for part in pending))
        failure_message = data.get("failure_message") or ""
        if failure_message:
            messages.append("Why the remaining collection tasks could not be answered: " + failure_message)
        if not parts and not pending:
            raise ValueError("A compound response requires question parts")
        # One content part keeps its citations on the combined answer; several
        # would collide in numbering and stay inside their parts.
        sources = ({key: getattr(cited, key) for key in ("citations", "evidence", "media_evidence", "cited_claims")}
                   if cited else {})
        return Answer(status=blocked_status or ("answered" if complete else "insufficient_evidence"), answer_mode="tools",
                      cost_usd=cost, **sources,
                      answer="\n\n".join(messages), failure_reason="" if complete and not blocked_status else reason or "research_plan_incomplete",
                      structured_result={"kind": "composite", "complete": complete, "parts": parts,
                                         "pending_parts": pending, "incomplete_parts": incomplete,
                                         "failure_reason": reason,
                                         "failure_message": failure_message,
                                         "completion_basis": data.get("completion_basis")})

    def _historical_tool_result_current(self, data, trusted_filters, *, answered):
        """Recheck an optimistic source-state guard after downstream answer work.

        Tool reads have their own before/after checks. Their result can still
        become stale while evidence is retrieved or an answer is generated.
        This is another current-state check, not a permanent membership freeze.
        """
        supplied = data.get("historical_source_state_guard")
        if supplied is None:
            selected = data.get("filters") or {}
            required = (trusted_filters.dataset == "social" and trusted_filters.labels
                        or selected.get("dataset") == "social" and selected.get("labels")
                        or data.get("kind") == "social_historical_labels")
            return not (answered and required)
        try:
            if not isinstance(supplied, dict) or set(supplied) != {"filters", "source_state_version"}:
                return False
            scope = Filters.model_validate(supplied["filters"])
            version = supplied["source_state_version"]
            if (scope.dataset != "social" or not isinstance(version, str)
                    or re.fullmatch(r"[0-9a-f]{64}", version) is None):
                return False
            validate_share_scope(scope, trusted_filters)
            return self.db.social_source_state_version(scope) == version
        except Exception:  # public boundary; database errors can contain credentials.
            return False

    @staticmethod
    def _tool_metadata_answer(data):
        """Render original field values and their unknowns without another model."""
        fields = data.get("original_fields") or {}
        labels = {"title": "Title", "publisher": "Publisher", "sponsor": "Sponsor",
                  "original_url": "Original source URL", "publication_date": "Original publication date",
                  "collection_search_term": "Collection search term", "disclosure_language": "Stored disclosure wording",
                  "disclosure_location": "Stored disclosure location"}
        lines, known, missing, review = [], [], [], []
        for key, value in fields.items():
            status = value.get("status")
            stored = value.get("value")
            needs_review = (status == "needs_review"
                            or (value.get("provenance") or {}).get("status") == "needs_review")
            if needs_review:
                review.append(key)
                shown = "Awaiting source review"
            elif status == "recorded" and stored is not None:
                known.append(key)
                shown = str(stored)
            else:
                missing.append(key)
                shown = "Not recorded or unavailable in the stored source"
            lines.append(f"{labels.get(key, key)}: {shown}")
        complete = bool(fields) and not missing and not review
        if known and not complete:
            lines.append("The requested source fields are only partially available; missing and review fields remain unresolved.")
        return Answer(status="answered" if known else "insufficient_evidence", answer_mode="tools",
                      answer="\n\n".join(lines) or "Original metadata is unavailable for this selected record.",
                      failure_reason="" if complete else "original_source_metadata_missing",
                      structured_result={"kind": "original_metadata", **data, "complete": complete,
                                         "requested_fields": list(fields), "known_fields": known,
                                         "missing_fields": missing, "review_fields": review})

    @staticmethod
    def _tool_content_answer(data):
        """Separate reviewed membership, uncertain coverage and a bounded page."""
        if data.get("status") != "ok" or not data.get("available"):
            return Answer(status="insufficient_evidence", answer_mode="tools",
                          answer=data.get("message") or "Reviewed content decisions are unavailable; missing decisions do not establish absence.",
                          failure_reason="content_publication_unavailable")
        totals, coverage = data["totals"], data["coverage"]
        message = (f"{totals['relevant']:,} reviewed matching advertisements in this selection. "
                   f"{totals['not_relevant']:,} reviewed nonmatches and {totals['unknown']:,} unknown "
                   f"out of {totals['scope_records']:,} current records. ")
        message += ("Classification covers the whole current selection. " if coverage["classification_complete"]
                    else "This is a partial reviewed list; unknown records may contain additional matches. ")
        message += ("All reviewed matching records are shown." if data.get("page_complete")
                    else "This page shows part of the matching list; browse the reviewed content list in Data for the remaining records.")
        return Answer(status="answered", answer_mode="tools", answer=message,
                      structured_result={"kind": "content_matches", **data})

    @staticmethod
    def _tool_claims_answer(data):
        """Present stored assignments and exact quotes without prose generation."""
        if data.get("status") != "ok" or not data.get("available"):
            return Answer(status="service_unavailable", answer_mode="tools",
                          answer="Published CLAIMS2 results are unavailable; this does not establish that advertisements contain no claims.",
                          failure_reason="claims_results_unavailable")
        total = data["total_records"]
        matches = data["total_matches"]
        message = (f"{total:,} stored records have {matches:,} published CLAIMS2 assignments within this selection. "
                   "Definitions, review states and original evidence are shown below. "
                   "These assignments are not independent fact checking or verified greenwashing findings. "
                   "Unmatched records are not classified negatives.")
        return Answer(status="answered", answer_mode="tools", answer=message,
                      structured_result={"kind": "claims", **data})

    @staticmethod
    def _tool_statistics_answer(data, *, base_filters=None):
        """Publish program-computed counts; model-written totals are never used."""
        if data.get("kind") == "social_historical_labels":
            return Service._social_label_statistics_answer(data, base_filters=base_filters)
        if data.get("kind") in {"list_years", "top_years", "compare_periods"}:
            return Service._time_statistics_answer(data, base_filters=base_filters)
        account_scope = (data.get("filters") or {}).get("accounts") or (
            isinstance(base_filters, Filters) and base_filters.accounts)
        social_label_scope = (data.get("filters") or {}).get("dataset") == "social" and (
            (data.get("filters") or {}).get("labels") or
            isinstance(base_filters, Filters) and base_filters.labels)
        if account_scope or social_label_scope or data.get("group_by") == "accounts":
            scope = Filters.model_validate(data["filters"])
            if data.get("method") != "database":
                raise ValueError("Scoped statistics require the database scope")
            if isinstance(base_filters, Filters):
                validate_share_scope(scope, base_filters)
        if data.get("kind") == "share":
            numerator = Filters.model_validate(data["filters"])
            denominator = Filters.model_validate(data["denominator_filters"])
            basis = data.get("denominator_basis")
            if (not isinstance(base_filters, Filters)
                    or basis not in {"current_selection_before_question_targets", "question_comparison_group"}
                    or data.get("method") != "database" or data.get("group_by") is not None
                    or data.get("groups") != []):
                raise ValueError("The percentage denominator must match the trusted current selection")
            if basis == "current_selection_before_question_targets":
                if denominator != base_filters:
                    raise ValueError("The percentage denominator must match the trusted current selection")
            else:
                # A question's comparison group may only narrow the trusted selection.
                validate_share_scope(denominator, base_filters)
            validate_share_scope(numerator, denominator)
            seen, messages = set(), []
            for item in data["collections"]:
                dataset, n, d = item["dataset"], item["numerator"], item["denominator"]
                if (dataset not in {"native", "social"} or dataset in seen
                        or numerator.dataset not in {"all", dataset}
                        or type(n) is not int or type(d) is not int or not 0 <= n <= d
                        or type(item.get("total")) is not int or item["total"] != n):
                    raise ValueError("Invalid separate-collection percentage counts")
                seen.add(dataset)
                expected = 100 * n / d if d else None
                if (item.get("percentage") != expected or isinstance(item.get("percentage"), bool)
                        or item.get("percentage_status") != ("defined" if d else "empty_selection")):
                    raise ValueError("The percentage must be computed from its numerator and denominator")
                unit = "native ad records" if dataset == "native" else "company social posts"
                messages.append(f"{expected:.2f}% ({n:,} of {d:,} eligible {unit})" if d
                                else f"Percentage undefined (0 eligible {unit} in the denominator)")
            if not messages:
                raise ValueError("A percentage result needs a loaded collection")
            if basis == "question_comparison_group":
                group = _plain_scope(denominator, base_filters)
                suffix = f". The comparison group is {group} in this collection."
            else:
                suffix = ". Denominators use the current selection before question targets."
            note = (data.get("date_inference") or {}).get("note") or ""
            if social_label_scope:
                from .social_annotations import NOTE

                note = (note + " " + NOTE).strip()
            return Answer(status="answered", answer_mode="statistics",
                          answer="; ".join(messages) + suffix + (" " + note if note else ""), structured_result=data)
        totals = "; ".join(
            f"{item['total']:,} eligible {'native ad records' if item['dataset'] == 'native' else 'company social posts'}"
            for item in data["collections"]
        )
        group_by = data.get("group_by")
        if group_by == "accounts":
            scope = Filters.model_validate(data["filters"])
            if scope.dataset != "social" or any(item["dataset"] != "social"
                    for item in [*data["collections"], *data["groups"]]):
                raise ValueError("Account grouping requires the social collection")
        if group_by and group_by != "none":
            names = {item["name"] for item in data["groups"] if item["name"] != "(Unknown)"}
            dimension = {"publishers": "publishers", "sponsors": "source-listed sponsors / organizations",
                         "platforms": "platforms", "accounts": "source-listed account names"}[group_by]
            if group_by == "sponsors" and data.get("filters", {}).get("dataset") == "social":
                dimension = "source-listed company affiliations"
            message = f"{len(names):,} {dimension} appear in {totals} within this selection. Every category and its count is listed below."
        else:
            message = f"{totals} match this question and the active filters."
        note = (data.get("date_inference") or {}).get("note") or ""
        if social_label_scope:
            from .social_annotations import NOTE

            note = (note + " " + NOTE).strip()
        return Answer(status="answered", answer_mode="statistics",
                      answer=message + (" " + note if note else ""), structured_result=data)

    @staticmethod
    def _social_label_statistics_answer(data, *, base_filters):
        """Render complete source-state arithmetic without inventing findings."""
        from .social_annotations import (
            NOTE,
            SCHEME,
            SOCIAL_STATES,
            STATUS,
            social_label_metadata,
        )

        scope = Filters.model_validate(data.get("filters"))
        if (scope.dataset != "social" or not isinstance(base_filters, Filters)
                or data.get("status") != "ok" or data.get("method") != "database"
                or data.get("group_by") != "social_historical_labels"):
            raise ValueError("Historical social distributions require the trusted database scope")
        validate_share_scope(scope, base_filters)
        distribution = data.get("distribution")
        if not isinstance(distribution, dict):
            raise ValueError("A complete historical source distribution is required")
        counts = [distribution.get(key) for key in (
            "total", "valid_annotation_records", "unknown_annotation_records")]
        if (any(type(count) is not int or count < 0 for count in counts)
                or counts[1] + counts[2] != counts[0]
                or distribution.get("scheme") != SCHEME or distribution.get("status") != STATUS
                or not isinstance(distribution.get("source_state_version"), str)
                or re.fullmatch(r"[0-9a-f]{64}", distribution["source_state_version"]) is None):
            raise ValueError("Historical source totals or their version cannot be verified")
        total, valid, unknown = counts
        metadata = social_label_metadata()
        items = distribution.get("items")
        if (not isinstance(items, list) or len(items) != len(metadata)
                or {item.get("key") for item in items if isinstance(item, dict)}
                    != {item["key"] for item in metadata}
                or data.get("collections") != [{"dataset": "social", "total": total}]):
            raise ValueError("All thirteen source codes must be present exactly once")
        by_key = {item["key"]: item for item in items}
        lines = []
        for definition in metadata:
            item = by_key[definition["key"]]
            if (any(item.get(key) != definition[key] for key in ("label", "level"))
                    or any(type(item.get(state)) is not int or item[state] < 0 for state in SOCIAL_STATES)
                    or sum(item[state] for state in SOCIAL_STATES) != total
                    or item["unknown"] != unknown
                    or item["source_true"] + item["source_false"] != valid):
                raise ValueError("Each source code must reconcile True, False and unknown")
            lines.append(f"{definition['label']}: True {item['source_true']:,}; "
                         f"False {item['source_false']:,}; unknown {item['unknown']:,}.")
        message = (f"Historical source labels for {total:,} selected social posts: "
                   f"{valid:,} have a valid current-text annotation binding; {unknown:,} are unknown. "
                   "Each code below uses all selected posts as its denominator.\n\n"
                   + "\n".join(lines) + "\n\n" + NOTE)
        return Answer(status="answered", answer_mode="statistics", answer=message, structured_result=data)

    @staticmethod
    def _time_statistics_answer(data, *, base_filters):
        """Describe bounded time aggregates from the tool, preserving every part."""
        filters = Filters.model_validate(data["filters"])
        if not isinstance(base_filters, Filters) or data.get("method") != "database":
            raise ValueError("Time statistics require the trusted database scope")
        validate_share_scope(filters, base_filters)
        units = {"native": "native ad records", "social": "company social posts"}
        collections = data.get("collections") or []
        for item in collections:
            if (item.get("dataset") not in units or type(item.get("total")) is not int
                    or item["total"] < 0 or type(item.get("unknown_dates")) is not int
                    or not 0 <= item["unknown_dates"] <= item["total"]):
                raise ValueError("Invalid time-statistics totals")
        parts = []
        if data["kind"] == "compare_periods":
            periods = data.get("periods") or []
            if not 2 <= len(periods) <= 3:
                raise ValueError("A time comparison requires two or three periods")
            for period in periods:
                validate_share_scope(Filters.model_validate(period["filters"]), filters)
            for item in collections:
                counts = []
                for period in periods:
                    matches = [row for row in period["collections"] if row["dataset"] == item["dataset"]]
                    if len(matches) != 1 or type(matches[0].get("total")) is not int or matches[0]["total"] < 0:
                        raise ValueError("Every period must include each selected collection")
                    counts.append(matches[0]["total"])
                parts.append(units[item["dataset"]].capitalize() + ": " + "; ".join(
                    f"{count:,} in {period['label']}" for period, count in zip(periods, counts)))
                if len(counts) == 2:
                    if counts[0] == counts[1]:
                        parts.append("The two periods have equal counts")
                    else:
                        larger = 0 if counts[0] > counts[1] else 1
                        parts.append(f"{periods[larger]['label']} has {abs(counts[0] - counts[1]):,} more records")
        else:
            groups = data.get("groups") or []
            for item in collections:
                years = [group for group in groups if group["dataset"] == item["dataset"]]
                if any(type(group.get("count")) is not int or group["count"] < 0 for group in years):
                    raise ValueError("Invalid yearly counts")
                if data["kind"] == "top_years":
                    if years:
                        highest = max(group["count"] for group in years)
                        if any(group["count"] != highest for group in years):
                            raise ValueError("A highest-year result must preserve ties")
                        verb = "tie for the highest count" if len(years) > 1 else "has the highest count"
                        parts.append(f"{units[item['dataset']].capitalize()}: "
                                     + ", ".join(group["name"] for group in years)
                                     + f" {verb}, with {highest:,} records per year")
                    else:
                        parts.append(f"No dated {units[item['dataset']]} are available for year ranking")
                else:
                    if sum(group["count"] for group in years) + item["unknown_dates"] != item["total"]:
                        raise ValueError("Year counts and unknown dates must reconcile with the collection total")
                    parts.append(f"{item['total']:,} {units[item['dataset']]} are grouped by year below")
                    # A date-range question needs the end dates, not only years (B1K T0: 5 of 10).
                    if item.get("earliest_date") and item.get("latest_date"):
                        parts.append(f"The earliest is dated {item['earliest_date']} and the latest "
                                     f"{item['latest_date']}")
        parts.extend(f"{item['unknown_dates']:,} {units[item['dataset']]} have no date under this date basis; "
                     "they are listed separately" for item in collections)
        note = (data.get("date_inference") or {}).get("note")
        if note:
            parts.append(note)
        return Answer(status="answered", answer_mode="statistics", answer=". ".join(part.rstrip(". ") for part in parts) + ".",
                      structured_result=data)

    def _answer_legacy(self, question, filters, visitor, progress=None):
        from .question_policy import original_metadata_question, question_contract

        if original_metadata_question(question):
            return Answer(status="insufficient_evidence", answer_mode="clarification",
                          answer="Read this stored field through original metadata tools after identifying the record. Outside pages cannot replace it.",
                          failure_reason="original_source_metadata_required")
        if question_contract(question).get("compound_read_request"):
            return Answer(status="insufficient_evidence", answer_mode="clarification",
                          answer="This question has several read tasks. Use the model-assisted task planner or submit each part separately.",
                          failure_reason="research_plan_required")
        start = time.monotonic()
        if not 1 <= len(question.strip()) <= 2000:
            return Answer(
                status="insufficient_evidence",
                answer="Please enter a question of 1–2,000 characters.",
            )
        normalized = question.strip().lower().rstrip("?.!")
        current_count = normalized in {
            "how many records",
            "how many records are there",
            "how many records match the current filters",
            "count records",
            "当前筛选有多少条记录",
            "当前有多少条记录",
        }
        # Preflight has no database or model dependency. Resolve only structured
        # questions against actual source facets; semantic questions keep RAG.
        plan = (QuestionPlan("ready", kind="count", filters=filters.model_copy(deep=True),
                             scope_notes=("Counts use current eligible records within the active filters.",))
                if current_count else plan_question(question, filters, {}))
        if plan is not None:
            try:
                _progress(progress, "database")
                if plan.status == "unsupported":
                    return Answer(status="insufficient_evidence", answer_mode="clarification", answer=plan.message)
                before = self.health()
                version = before.get("data_version")
                if before.get("status") != "ok" or not isinstance(version, str) or not version or version == "unavailable":
                    raise ValueError("A healthy source version is required for statistics")
                counts = before.get("countable_record_counts", before.get("record_counts", {}))
                if not isinstance(counts, dict):
                    raise ValueError("Collection admission counts are unavailable")
                message = ("The selected collection has no admitted records." if counts else
                           "The selected collection's admission status cannot be verified.")
                unavailable = Answer(
                    status="service_unavailable", answer_mode="statistics",
                    failure_reason="collection_unavailable",
                    answer=message + " Collection statistics are unavailable; no advertisement count has been established.",
                )
                selected = ["native", "social"] if filters.dataset == "all" else [filters.dataset]
                if not any(counts.get(dataset, 0) > 0 for dataset in selected):
                    return unavailable
                if not current_count:
                    plan = plan_question(question, filters, self.facets(filters.dataset))
                if plan.status != "ready":
                    return Answer(status="insufficient_evidence", answer_mode="clarification", answer=plan.message)
                requested = ["native", "social"] if plan.filters.dataset == "all" else [plan.filters.dataset]
                available = [dataset for dataset in requested if counts.get(dataset, 0) > 0]
                if not available:
                    return unavailable
                result = self._statistics_answer(plan, available_datasets=available)
                after = self.health()
                if after.get("status") != "ok" or after.get("data_version") != version:
                    result = Answer(
                        status="service_unavailable", answer_mode="statistics",
                        failure_reason="data_changed_during_statistics",
                        answer="The collection changed while processing this question. Please submit it again.",
                    )
                else:
                    result.structured_result = {**result.structured_result, "data_version": version}
            except Exception:
                log.warning("Statistics answer unavailable")
                result = Answer(
                    status="service_unavailable", answer_mode="statistics",
                    answer="Collection statistics are temporarily unavailable. Please retry; no model call was made.",
                    failure_reason="statistics_unavailable",
                )
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result
        if re.search(
            r"\b(how many|count|percentage|percent|total number)\b|多少|占比|百分比",
            normalized,
        ):
            return Answer(
                status="insufficient_evidence",
                answer_mode="clarification",
                answer="Counts support named outlets, sponsors and explicit dates. Percentages compare target records with the current selected collection; select the denominator scope first. Topic counts require validated annotations. Retrieved passages cannot establish corpus totals.",
            )
        return self._answer_evidence(question, filters, visitor, progress=progress)

    def _small_scope_size(self, scope):
        """Record count of a selection narrow enough to read whole, else 0."""
        if not (scope.sponsors or scope.publishers or scope.accounts or scope.record_ids
                or scope.date_from or scope.date_to) or not hasattr(self.db, "public_rows"):
            return 0
        count = len(self.db.public_rows(scope))
        return count if count <= SMALL_SCOPE_RECORDS else 0

    def _merge_article_passages(self, evidence, filters, limit):
        """Join each screened ad's retrieved passages with the rest of that article.

        The candidate set and its ranking are unchanged; only the text read for
        each of the first `limit` ads is completed, in document order.
        """
        order = list(dict.fromkeys(e.record_id for e in evidence))[:limit]
        if not order or not hasattr(self.db, "record_passages"):
            return evidence
        rank = {rid: i for i, rid in enumerate(order)}
        whole = self._public_evidence(self.db.record_passages(order, filters))
        merged = {e.evidence_id: e for e in [*evidence, *whole] if e.record_id in rank}
        return sorted(merged.values(), key=lambda e: (rank[e.record_id], e.start, e.evidence_id))

    def _relation_list(self, question, filters, relation_listing):
        """Every post a relation filter selected, listed without content screening.

        A mention, hashtag or reference is a field of the post's source row, not
        text a model must find (a third of @-mentions are absent from the post
        text), so each selected post answers the question; its opening words are
        quoted. Posts without indexed text cannot be quoted and are counted.
        """
        passages = self._public_evidence(self.db.record_passages(filters.record_ids, filters, per_record=1))
        first = {}
        for item in passages:
            first.setdefault(item.record_id, item)
        results = _with_accounts([{
            "record_id": item.record_id, "title": item.title, "publisher": item.publisher, "sponsor": item.sponsor,
            "published_at": item.published_at, "decision": "matches", "evidence_id": item.evidence_id,
            "quote": _opening_words(item.text), "method": "relation"} for item in first.values()], passages)
        result = list_answer(question, results, passages, scope_total=len(filters.record_ids))
        selections = relation_listing["selections"]
        relations = "; ".join(f"{name}: {', '.join(map(str, values))}" for item in selections
                              for name, values in item.get("relations", {}).items())
        matched = max((item.get("matched_posts", 0) for item in selections), default=len(results))
        unquoted = len(filters.record_ids) - len(results)
        chinese = bool(re.search(r"[一-鿿]", question))
        if chinese:
            head = (f"按帖子来源字段中的关系（{relations}）选出 {matched} 篇帖子，下面全部列出。这是来源记录的字段，"
                    "不是对帖子内容的判断；被提及或使用某话题不代表认可或隶属。"
                    + (f"只列出最新的 {len(filters.record_ids)} 篇。" if matched > len(filters.record_ids) else "")
                    + (f"另有 {unquoted} 篇没有可引用的正文，未列出。" if unquoted else ""))
        else:
            head = (f"{matched} posts have this relation in their source records ({relations}); all are listed. "
                    "This is a source-record field, not a judgment of the post's content; a mention or hashtag "
                    "does not mean endorsement or affiliation."
                    + (f" Only the newest {len(filters.record_ids)} are listed." if matched > len(filters.record_ids) else "")
                    + (f" {unquoted} selected posts have no quotable text and are not listed." if unquoted else ""))
        parts = result.answer.split("\n\n")
        trace = {**result.research_trace["list_screening"], "method": "relation_selection", "relations": selections}
        return result.model_copy(update={
            "answer": "\n\n".join([head, *parts[1:-1]]),
            "structured_result": {**result.structured_result, "kind": "relation_list", "method": "relation_selection",
                                  "matched_posts": matched, "unquoted_posts": unquoted,
                                  "meaning": "Posts selected by a source-row relation field; content is not judged."},
            "research_trace": {**result.research_trace, "list_screening": trace},
        })

    def _screen_both(self, question, scoped, evidence, phrases, visitor, progress=None):
        """Screen a list question in the native ads and in the company posts, then answer once.

        Each collection gets its own ranked candidates, first reading and
        widening, so posts never crowd ads out of the reading (or the reverse).
        Returns the combined list answer and its cost.
        """
        from .question_policy import sources_content_request

        results, pool, cost, scopes, literal_only = [], [], 0.0, {}, pure_literal_question(question)
        for _, scope in scoped:
            dataset = scope.dataset
            total = len(self.db.public_rows(scope))
            scopes[dataset] = total
            literal = (self._public_evidence(self.db.phrase_search(phrases, scope, limit_records=total + 1))
                       if phrases else [])
            if literal_only:
                found = literal_results(literal, phrases[0])
                pool.extend(literal)
            else:
                own = [e for e in evidence if getattr(e, "dataset", dataset) == dataset]
                own = list({e.evidence_id: e for e in [*literal, *own]}.values())
                records = len({e.record_id for e in literal})
                own = self._merge_article_passages(own, scope, max(MAX_WIDENED, records))
                reread_passages = []

                def reread(record_ids, scope=scope, sink=reread_passages):
                    rows = self._public_evidence(self.db.record_passages(record_ids, scope, per_record=None))
                    sink.extend(rows)
                    return rows

                found, spent = screen_list(self.rag, question, own, visitor,
                                           limit=max(MAX_CANDIDATES, records), widen_to=max(MAX_WIDENED, records),
                                           reread=reread if hasattr(self.db, "record_passages") else None)
                cost += spent
                pool.extend([*own, *reread_passages])
            results.extend({**item, "dataset": dataset} for item in found)
        pool = list({e.evidence_id: e for e in pool}.values())
        results = _with_accounts(results, pool)
        result = list_answer(question, results, pool, scope_total=sum(scopes.values()), scopes=scopes,
                             literal=phrases[0] if literal_only else None)
        if literal_only:
            return result, cost
        result.research_trace["list_screening"]["first_read"] = MAX_CANDIDATES
        if sources_content_request(question) and result.citations:
            result, writer_cost = self._read_matched_sources(question, result, results, pool, visitor, progress)
            cost += writer_cost
        elif result.citations:
            result, writer_cost = self._summarize_list(question, result, results, pool, visitor, progress)
            cost += writer_cost
        return result, cost

    def _summarize_list(self, question, listed, results, evidence, visitor, progress=None):
        """Answer a list question in words before listing every matching ad.

        The writer reads the SUMMARY_RECORDS most relevant listed ads and
        answers the question with cited claims; the screened list follows as
        its own section. If the writer fails, the list answer stands alone.
        Returns the answer and the writer cost.
        """
        matched = [item for item in results if item["decision"] == "matches"]
        match_ids = {item["record_id"]: item["evidence_id"] for item in matched}
        # The listed order (a fair share of ads and posts first) picks the summary's sources.
        order = {c.evidence_id: n for n, c in enumerate(listed.citations)}
        ids = sorted(match_ids, key=lambda rid: order.get(match_ids[rid], len(order)))[:SUMMARY_RECORDS]
        passages, _ = _zone_evidence(evidence, ids, match_ids)
        try:
            part = self.rag.generate(question, passages, visitor, **({"progress": progress} if progress else {}))
        except LimitReached:
            raise
        except Exception as exc:
            trace = {**listed.research_trace, "list_summary": {"status": "failed", "reason": type(exc).__name__}}
            return listed.model_copy(update={"research_trace": trace}), 0.0
        trace = {**listed.research_trace, "list_summary": {"status": part.status, "records": ids}}
        if part.status != "answered" or not part.cited_claims:
            return listed.model_copy(update={"research_trace": trace}), part.cost_usd
        chinese = bool(re.search(r"[一-鿿]", question))
        head = listed.answer.split("\n\n", 1)[0]
        written = len(part.citations)
        listed_claims = _renumbered(listed.cited_claims, written)
        summary = [CitedStatement(text=head), *(part.summary or part.cited_claims[:2])]
        # The page lists the first DISPLAY_LIMIT matches; every match stays cited.
        shown = min(len(listed_claims), DISPLAY_LIMIT)
        hidden = len(listed_claims) - shown
        both = "by_dataset" in listed.structured_result
        what = ("符合的广告和帖子" if both else "符合的广告") if chinese else ("Matching ads and posts" if both else "Matching ads")
        unit = "项" if both else "篇"
        title = ((f"{what}（共 {len(matched)} {unit}，列出前 {shown} {unit}）" if hidden else f"{what}（{len(matched)} {unit}）")
                 if chinese else
                 (f"{what} ({len(matched)}; first {shown} listed)" if hidden else f"{what} ({len(matched)})"))
        sections = [
            AnswerSection(title="要点" if chinese else "Key points", citation_indices=list(range(1, written + 1))),
            AnswerSection(title=title, citation_indices=list(range(written + 1, written + shown + 1))),
        ]
        lines = [f"{n}. {c.text} " + " ".join(f"[{i}]" for i in c.citation_indices)
                 for n, c in enumerate(listed_claims[:shown], 1)]
        if hidden:
            lines.append(hidden_line(hidden, chinese, both=both))
        points = [f"{c.text} " + " ".join(f"[{i}]" for i in c.citation_indices) for c in part.cited_claims]
        basis = f"Summary drawn from the {len(ids)} most relevant matching {'items' if both else 'ads'}."
        return listed.model_copy(update={
            "answer": "\n\n".join([head, *points, title, *lines]),
            "citations": [*part.citations, *listed.citations],
            "cited_claims": [*part.cited_claims, *listed_claims],
            "summary": summary, "sections": sections,
            "evidence": list({e.evidence_id: e for e in [*part.evidence, *listed.evidence]}.values()),
            "research_trace": trace,
            "structured_result": {**listed.structured_result, "summary_basis": basis, "summary_records": len(ids),
                                  "display_citations": [*range(1, written + shown + 1)]},
        }), part.cost_usd

    def _read_matched_sources(self, question, listed, results, evidence, visitor, progress=None):
        """Second query zone of a "what do these ads say" list: read the matches.

        Screening, the first zone, decides which ads match and quotes one
        sentence each, which drops the points the user asked for (B1K-Q052).
        The matched ads' retrieved passages go to the writer in shards, one
        claim per ad; ads the writer skips get one follow-up call, and the parts
        are merged with renumbered citations. A matched ad still left out, or
        one past the shards, keeps its screening quote. Each ad's reading is
        recorded, and the answer says when the content reading is partial.
        Returns the merged answer and the writer cost.
        """
        matched = [item for item in results if item["decision"] == "matches"]
        match_ids = {item["record_id"]: item["evidence_id"] for item in matched}
        ids = list(match_ids)[:ZONE_RECORDS * CONTENT_ZONES]
        claims, citations, read, zones, cost, covered = [], [], [], [], 0.0, set()
        reading = {}

        def write(shard, kind):
            nonlocal cost
            passages, shard_reading = _zone_evidence(evidence, shard, match_ids)
            if kind == "shard":
                reading.update(shard_reading)
            try:
                part = self.rag.generate(question, passages, visitor, one_claim_per_source=True,
                                         **({"progress": progress} if progress else {}))
            except LimitReached:
                raise
            except Exception as exc:
                # The screened quotes below still answer for this shard.
                zones.append({"records": shard, "kind": kind, "status": "failed", "reason": type(exc).__name__})
                return
            cost += part.cost_usd
            zones.append({"records": shard, "kind": kind, "status": part.status})
            if part.status != "answered":
                return
            record_of = {e.evidence_id: e.record_id for e in passages}
            offset = len(citations)
            citations.extend(part.citations)
            claims.extend(CitedStatement(text=c.text, citation_indices=[n + offset for n in c.citation_indices])
                          for c in part.cited_claims)
            read.extend(passages)
            covered.update(record_of[c.evidence_id] for c in part.citations if c.evidence_id in record_of)

        for start in range(0, len(ids), ZONE_RECORDS):
            write(ids[start:start + ZONE_RECORDS], "shard")
        # The writer still skipped about one ad in five even with room to spare
        # (B1K-S); the ads it skipped get one more call of their own.
        skipped = [rid for zone in list(zones) if zone["status"] == "answered"
                   for rid in zone["records"] if rid not in covered]
        for start in range(0, len(skipped), ZONE_RECORDS):
            write(skipped[start:start + ZONE_RECORDS], "follow_up")
        written = {rid for zone in zones if zone["status"] == "answered" for rid in zone["records"]}
        ads = []
        for item in matched:
            rid = item["record_id"]
            state = reading.get(rid, {"available_passages": 0, "sent_passages": 0, "retrieval_cap_reached": False})
            gaps = [gap for gap, present in (
                ("past_shard_limit", rid not in reading),
                ("writer_failed", rid in reading and rid not in written),
                ("not_cited_by_writer", rid in written and rid not in covered),
                ("passages_trimmed", state["sent_passages"] < state["available_passages"]),
                ("retrieval_cap_reached", state["retrieval_cap_reached"])) if present]
            ads.append({"record_id": rid, **state, "cited_by_writer": rid in covered, "gaps": gaps})
        summary = {
            "matched_records": len(matched),
            "sent_records": sum(ad["sent_passages"] > 0 for ad in ads),
            "cited_records": len(covered),
            "partial_records": sum(bool(ad["gaps"]) for ad in ads),
            # "complete": every matched ad's retrieved passages were sent and the
            # writer cited it. It does not certify that each whole article was read.
            "status": "partial" if any(ad["gaps"] for ad in ads) else "complete",
        }
        trace = {**listed.research_trace, "content_zones": zones, "content_reading": {**summary, "records": ads}}
        chinese = bool(re.search(r"[一-鿿]", question))
        note = ""
        if summary["status"] == "partial":
            # Plain wording (user, 2026-10-19); counts stay in content_reading.
            note = (f"符合的 {len(matched)} 篇中有 {summary['partial_records']} 篇只读了部分内容或没有展开，"
                    "描述可能不完整。"
                    if chinese else
                    f"{summary['partial_records']} of the {len(matched)} matching ads were only partly read or "
                    "not described, so this may be incomplete.")
        parts = listed.answer.split("\n\n")
        # The listed answer is a head line and one line per matched ad; the
        # read content replaces those lines (no count line follows them).
        head = parts[0]
        if not claims:
            return listed.model_copy(update={
                "answer": "\n\n".join(part for part in [*parts, note] if part),
                "research_trace": trace,
                "structured_result": {**listed.structured_result, "content_reading": summary},
            }), cost
        sentences = [f"{c.text} " + " ".join(f"[{n}]" for n in c.citation_indices) for c in claims]
        read_refs = len(citations)
        rest = []
        for number, item in enumerate(matched):
            if item["record_id"] in covered:
                continue
            # The screened line ends with its old number; it is renumbered here.
            line = re.sub(r"\s*\[\d+\]$", "", listed.cited_claims[number].text)
            citations.append(listed.citations[number])
            claims.append(CitedStatement(text=line, citation_indices=[len(citations)]))
            rest.append(f"{line} [{len(citations)}]")
        if rest:
            rest.insert(0, "其他符合的广告（只有筛查引文）：" if chinese else
                        "Other matching ads (screening quote only):")
        # Shown as a summary line and grouped sections (what the ads say, then
        # matches described only by their screening quote).
        sections = [AnswerSection(title="各篇广告的内容" if chinese else "What the matching ads say",
                                  citation_indices=list(range(1, read_refs + 1)))]
        shown_rest = list(range(read_refs + 1, min(len(citations), read_refs + DISPLAY_LIMIT) + 1))
        if rest:
            sections.append(AnswerSection(title=rest[0].rstrip("：:"), citation_indices=shown_rest))
            hidden = len(rest) - 1 - len(shown_rest)
            rest = rest[:len(shown_rest) + 1] + ([f"另有 {hidden} 篇符合，未在此列出。" if chinese else
                                                  f"{hidden} more matching ads not shown here."] if hidden > 0 else [])
        return listed.model_copy(update={
            "answer": "\n\n".join(part for part in [head, *sentences, *rest, note] if part),
            "citations": citations, "cited_claims": claims,
            "summary": [CitedStatement(text=" ".join(part for part in [head, note] if part))], "sections": sections,
            "evidence": list({e.evidence_id: e for e in [*read, *listed.evidence]}.values()),
            "research_trace": trace,
            "structured_result": {**listed.structured_result, "content_reading": summary,
                                  "display_citations": [*range(1, read_refs + 1), *shown_rest]},
        }), cost

    def _answer_evidence(self, question, filters, visitor, search_query=None, audit=True,
                         retrieval_groups=None, progress=None, declared_shape=None, relation_listing=None):
        from .models import MediaAnswerEvidence
        from .question_policy import original_metadata_question

        if original_metadata_question(question):
            return Answer(status="insufficient_evidence", answer_mode="clarification",
                          answer="This is a stored original-field question. Identify the record and use original metadata tools; content retrieval and web pages cannot substitute for that field.",
                          failure_reason="original_source_metadata_required")

        start = time.monotonic()
        evidence = []
        media_evidence = []
        trimmed = 0
        media_groups = []
        media_reader = self._media_reader()
        reservation = None
        dispatched = False
        version = "unavailable"
        embedding_cost = []
        coverage = []
        scoped = []
        search_query = search_query or question
        from .question_policy import question_contract, sources_content_request

        # A "which ads ..." question over native ads screens every retrieved
        # candidate instead of citing the few most relevant ones.
        # A list is screened when the surface rule or the planner says so: a
        # missed list silently loses ads, a needless screening only costs time.
        rule_list = question_contract(question)["requires_complete_list"]
        wants_list = rule_list or declared_shape == "every_matching_source"
        # Social post lists are screened like ad lists (B1K-REL: listing five
        # examples of 34 selected posts capped recall at 15-35%).
        list_mode = wants_list and not retrieval_groups and filters.dataset in ("native", "social")
        # A list over both collections is screened in each one separately, and
        # the answer counts both (user, 2026-10-19: a "which ads" question over
        # ads and posts listed nothing while three posts matched).
        both_list = wants_list and not retrieval_groups and filters.dataset == "all" and not filters.labels
        list_mode = list_mode or both_list
        # The planner says the relation filters are the question's whole condition;
        # honoured only when this read actually selected posts by a relation.
        relation_list = bool(relation_listing and relation_listing.get("list_all")
                             and relation_listing.get("selections") and filters.dataset == "social"
                             and filters.record_ids and filters.record_ids != ["no-relation-match"])
        list_mode = list_mode or relation_list
        try:
            _progress(progress, "database")
            version = self.db.health()["data_version"]
            trusted_filters = filters.model_copy(deep=True)
            # A named title narrows only the collection it belongs to: an ad title
            # must not restrict the social scope of a both-collections question.
            titled = self._title_records(question, filters)
            if not retrieval_groups and filters.dataset != "all":
                filters = self._title_scope(question, filters)
            searches = retrieval_groups or [{"query": search_query, "filters": filters.model_dump(mode="json"), "label": "Current selection"}]
            if both_list:
                searches = [{"query": search_query, "label": label,
                             "filters": filters.model_copy(update={"dataset": dataset}).model_dump(mode="json")}
                            for dataset, label in (("native", "Native ads"), ("social", "Company posts"))]
            if not 1 <= len(searches) <= 3:
                raise ValueError("Invalid comparison scope count")
            # Narrowing is revalidated here even for a custom research adapter.
            for item in searches:
                scope = Filters.model_validate(item["filters"])
                validate_share_scope(scope, trusted_filters)
                own_titles = [rid for rid, dataset in titled if scope.dataset == dataset]
                if retrieval_groups and own_titles:
                    selected_ids = [rid for rid in own_titles if not scope.record_ids or rid in scope.record_ids]
                    if not selected_ids:
                        raise ValueError("Comparison titles do not intersect the requested records")
                    scope.record_ids = selected_ids
                validate_share_scope(scope, filters)
                scoped.append((item, scope))
            # Keyword search always runs first so failures can return usable evidence.
            for item, scope in scoped:
                evidence.extend(self.search(item["query"], scope, limit=3 if retrieval_groups else 5))
            # Recall stays separate by modality and by comparison target. This
            # reads supplied derived text only; it does not run OCR or watch video.
            if any(getattr(self.settings, name, "") for name in ("media_bundle_path", "media_bundle_sha256", "media_asset_root")):
                _progress(progress, "media")
            for item, scope in scoped:
                report = media_reader.read(item["query"], filters=scope,
                                           media_types=["image", "video"],
                                           limit=3 if retrieval_groups else 5)
                if report["status"] == "unavailable":
                    evidence = []
                    raise ValueError("Media evidence failed source validation")
                units = [MediaAnswerEvidence.from_source_ref(ref) for ref in report.get("source_refs", [])]
                media_groups.append((scope, report, units))
                media_evidence.extend(units)
            media_evidence = list({item.evidence_id: item for item in media_evidence}.values())

            def validate_media(items):
                # Never let a custom downstream adapter introduce additional
                # source IDs or change the selected derived excerpts.
                if list(items) != media_evidence:
                    return False
                return all(media_reader.validate_selection(units, filters=scope)
                           for scope, _, units in media_groups if units)

            if media_evidence and not validate_media(media_evidence):
                evidence, media_evidence = [], []
                raise ValueError("Media evidence failed source validation")
            price(self.settings.generation_model, 1, 1)
            # Admission covers the whole paid question, before query embedding.
            # This exceeds the maximum generation cost under the 100k-byte prompt cap.
            reservation = self.rag.budget.reserve(
                "0.04", visitor, "generation", self.settings.generation_model
            )
            vectors = self.rag.embed([item["query"] for item, _ in scoped], visitor=visitor, cost_sink=embedding_cost)
            if len(vectors) != len(scoped):
                raise ValueError("Embedding count mismatch")
            evidence = []
            for ((item, scope), vector, (_, report, units)) in zip(scoped, vectors, media_groups):
                whole = self._small_scope_size(scope) if not (retrieval_groups or list_mode) else 0
                found = self._public_evidence(self.db.search(
                    item["query"], scope, vector=vector, model=self.settings.embedding_model,
                    chunks_per_record=2 if list_mode else 3,
                    **({"limit": 3} if retrieval_groups else {"limit": MAX_WIDENED} if list_mode
                       else {"limit": whole} if whole > 5 else {}),
                ))
                coverage.append({"label": item.get("label") or "Selected target", "passages": len(found),
                                 "image_units": sum(unit.media_type == "image" for unit in units),
                                 "video_units": sum(unit.media_type == "video" for unit in units),
                                 "evidence_units": len(found) + len(units),
                                 "media_status": report["status"],
                                 "retrieved_record_ids": sorted({unit.record_id for unit in [*found, *units]}),
                                 "retrieved_evidence_ids": [unit.evidence_id for unit in [*found, *units]],
                                 "filters": scope.model_dump(mode="json"), "query": item["query"]})
                evidence.extend(found)
            evidence = list({e.evidence_id: e for e in evidence}.values())
            if not list_mode:
                # Screening sends bounded batches instead of one prompt.
                evidence, trimmed = _fit_evidence_budget(evidence)
            if self.db.health()["data_version"] != version:
                evidence, media_evidence = [], []
                version = self.db.health()["data_version"]
                raise ValueError(
                    "Data changed during retrieval; retry on a consistent version"
                )
            dispatched = True
            _progress(progress, "organizing")
            if list_mode:
                # Each screening batch reserves and settles its own call.
                self.rag.budget.cancel_unsent(reservation)
                reservation = None
                # Every ad containing a quoted phrase is read first, with the
                # passage that contains it; ranked candidates follow.
                phrases = quoted_phrases(question)
                if not both_list:
                    scope_total = len(self.db.public_rows(filters))
                    literal = (self._public_evidence(self.db.phrase_search(phrases, filters, limit_records=scope_total + 1))
                               if phrases else [])
                if both_list:
                    result, screening_cost = self._screen_both(question, scoped, evidence, phrases, visitor, progress)
                elif relation_list:
                    result, screening_cost = self._relation_list(question, filters, relation_listing), 0.0
                elif pure_literal_question(question):
                    # Wording, not meaning: the exact search is the complete
                    # answer and needs no model judgment.
                    results, screening_cost = literal_results(literal, phrases[0]), 0.0
                    result = list_answer(question, results, literal, scope_total=scope_total, literal=phrases[0])
                else:
                    evidence = list({e.evidence_id: e for e in [*literal, *evidence]}.values())
                    records = len({e.record_id for e in literal})
                    evidence = self._merge_article_passages(evidence, filters, max(MAX_WIDENED, records))
                    # An ad is not ruled out from part of its text: its whole
                    # article is read again first, and a match there is cited.
                    reread_passages = []

                    def reread(record_ids):
                        rows = self._public_evidence(self.db.record_passages(record_ids, filters, per_record=None))
                        reread_passages.extend(rows)
                        return rows

                    # Past the first 40, reading continues only while matches still turn up.
                    # Posts selected by a relation satisfy it by their source records, which
                    # the screener cannot see in the text (B1K-REL4: 0 of 17 replies kept).
                    screened = question
                    if relation_listing and relation_listing.get("selections") and filters.dataset == "social":
                        relations = "; ".join(f"{name}: {', '.join(map(str, values))}"
                                              for item in relation_listing["selections"]
                                              for name, values in item.get("relations", {}).items())
                        screened = (f"{question}\n\n(Every candidate post already satisfies, by its source "
                                    f"record, the relation {relations}; this is not visible in the text. Judge "
                                    "only the question's other conditions; if it has none, every post matches.)")
                    results, screening_cost = screen_list(self.rag, screened, evidence, visitor,
                                                          limit=max(MAX_CANDIDATES, records),
                                                          widen_to=max(MAX_WIDENED, records),
                                                          reread=reread if hasattr(self.db, "record_passages") else None)
                    evidence = list({e.evidence_id: e for e in [*evidence, *reread_passages]}.values())
                    results = _with_accounts(results, evidence)
                    result = list_answer(question, results, evidence, scope_total=scope_total)
                    result.research_trace["list_screening"]["first_read"] = max(MAX_CANDIDATES, records)
                    if sources_content_request(question) and result.citations:
                        result, writer_cost = self._read_matched_sources(
                            question, result, results, evidence, visitor, progress)
                        screening_cost += writer_cost
                    elif result.citations:
                        result, writer_cost = self._summarize_list(
                            question, result, results, evidence, visitor, progress)
                        screening_cost += writer_cost
                result.cost_usd = screening_cost + sum(embedding_cost)
            else:
                result = self.rag.generate(
                    question, evidence, visitor, reservation=reservation,
                    **({"progress": progress} if progress else {}),
                    **({"media_evidence": media_evidence, "validate_media": validate_media} if media_evidence else {}),
                )
            if media_evidence and not validate_media(media_evidence):
                evidence, media_evidence = [], []
                raise ValueError("Media evidence failed source validation")
            _progress(progress, "citations")
            final_version = self.db.health()["data_version"]
            if final_version != version:
                # A dispatched call remains charged and audited, but an answer
                # from an index superseded during generation is not published.
                evidence, media_evidence = [], []
                version = final_version
                raise ValueError(
                    "Data changed during generation; retry on a consistent version"
                )
        except LimitReached as exc:
            result = Answer(status="limited", answer=str(exc), evidence=evidence, media_evidence=media_evidence)
        except Exception as exc:
            log.warning("Answer failed: %s", type(exc).__name__)
            known = {
                "Unverifiable citation": "citation_mismatch",
                "Citation exceeds short-quote limit": "quote_too_long",
                "Missing or excessive claims": "invalid_claim_count",
                "Evidence failed original-version validation": "evidence_version_mismatch",
                "Unverifiable answer-structure citation": "answer_structure_mismatch",
                "Media evidence failed source validation": "media_evidence_mismatch",
                "Duplicate answer evidence identity": "duplicate_evidence_identity",
                "Data changed during retrieval; retry on a consistent version": "data_changed_during_retrieval",
                "Data changed during generation; retry on a consistent version": "data_changed_during_generation",
            }
            reason = exc.reason if isinstance(exc, AnswerValidationError) else known.get(str(exc), type(exc).__name__)
            if reason in {"media_evidence_mismatch", "duplicate_evidence_identity", "evidence_version_mismatch"}:
                evidence, media_evidence = [], []
            result = Answer(
                status="service_unavailable",
                answer="The answer service is unavailable. Browse the evidence below or use keyword search.",
                evidence=evidence,
                media_evidence=media_evidence,
                failure_reason=reason,
                research_trace=({"generation_failure": exc.details}
                                if isinstance(exc, AnswerValidationError) else {}),
            )
        finally:
            if reservation and not dispatched:
                self.rag.budget.cancel_unsent(reservation)
        if reservation:
            result.cost_usd = self.rag.budget.reservation_cost(reservation) + sum(
                embedding_cost
            )
        if coverage and "list_screening" in result.research_trace:
            # Keep the screening counts; the retrieval groups go beside them.
            result.structured_result = {**result.structured_result, "groups": coverage}
        elif coverage:
            result.structured_result = {"kind": "evidence_coverage", "groups": coverage,
                                        "meaning": "Retrieved text and derived media are a sample, not complete coverage or verified semantic support."}
        if result.status == "insufficient_evidence" and not evidence and not media_evidence and not retrieval_groups:
            result.answer += "\n\n" + empty_scope_note(question, filters)
        cited_ids = {citation.evidence_id for citation in result.citations}
        cited_sources = {item.evidence_id: item.record_id for item in [*result.evidence, *result.media_evidence]
                         if item.evidence_id in cited_ids}
        if retrieval_groups:
            for item in coverage:
                item["cited_records"] = len({cited_sources[eid] for eid in item["retrieved_evidence_ids"]
                                             if eid in cited_sources})
                item["citation_coverage_status"] = "present" if item["cited_records"] else "missing"
        gaps = [item["label"] for item in coverage if not item["evidence_units"]
                or retrieval_groups and result.status == "answered" and not item.get("cited_records")]
        if retrieval_groups and gaps and result.status == "answered":
            # A supported statement about one target is a partial answer,
            # never a completed comparison with a target that has no evidence.
            result.status = "insufficient_evidence"
            result.answer += "\n\nThe collection comparison is incomplete: no source was cited for " + ", ".join(gaps) + "."
        if trimmed:
            result.research_trace["evidence_trimmed_for_prompt_budget"] = trimmed
        result.research_trace["media_retrieval"] = {
            "method": "separate_lexical_media_rrf", "recognition_calls": 0,
            "source_binding": media_reader.source_binding,
            "groups": [{"label": item.get("label") or "Current selection", "status": report["status"],
                        "image_units": sum(unit.media_type == "image" for unit in units),
                        "video_units": sum(unit.media_type == "video" for unit in units)}
                       for (item, _), (_, report, units) in zip(scoped, media_groups)],
        }
        # The evidence path supplements shortfalls. The outer wrapper also
        # only accepts evidence shortfalls, never operational/integrity failures.
        # A screened list that found no match is a collection finding; web
        # pages are not advertisements and cannot fill it.
        if (result.status == "insufficient_evidence" and not _COLLECTION_ONLY.search(question)
                and "list_screening" not in result.research_trace):
            topics = gaps if retrieval_groups else []
            result.external_research = self._search_external(question, filters, visitor, missing_topics=topics, progress=progress)
            result.cost_usd += result.external_research.get("cost_usd", 0.0)
        if result.status == "answered":
            # Written by the server: a cited record's date is an estimate, or
            # could not be checked. An unknown is never reported as "none".
            from .date_inference import BASIS_NOTE, UNCHECKED_NOTE

            cited = self._cites_inferred_dates(result, filters)
            # Kept out of the answer text: readers found the tier wording
            # unhelpful and the supplemented dates unreliable (user, 2026-10-19).
            if cited is None:
                result.research_trace = {**result.research_trace, "date_note": UNCHECKED_NOTE}
            elif cited:
                result.research_trace = {**result.research_trace, "date_note": BASIS_NOTE}
            contract = question_contract(question)
            # Decided by the answer itself (no per-ad screening, several sources
            # cited), not only by list recognition: the note backs up that
            # recognition, so it cannot depend on it (F04: N1 15, N2 11 unlabelled).
            if ((contract["selects_sources"] or contract["requires_content_count"] or wants_list
                 or _cited_record_count(result) >= 2)
                    and "list_screening" not in result.research_trace):
                result.answer = result.answer + "\n\n" + examples_note(question, result)
                result.research_trace["coverage_note"] = "retrieved_examples_only"
        # Disagreements between the rule and the planner are kept for review.
        result.research_trace["list_decision"] = {"rule": bool(rule_list), "planner": declared_shape}
        if media_evidence and result.status == "service_unavailable" and not result.external_research:
            # Recheck the fixed reader before returning an operational failure.
            if not validate_media(media_evidence):
                result = self._withhold_changed_media_result(result)
        if result.external_research:
            after_web = self.health()
            if after_web.get("status") != "ok" or after_web.get("data_version") != version:
                result = self._withhold_changed_web_result(result)
            elif media_evidence and not validate_media(media_evidence):
                result = self._withhold_changed_media_result(result)
        result.latency_ms = int((time.monotonic() - start) * 1000)
        if audit and not _FINAL_AUDIT_CONTEXT.get():
            try:
                self.db.save_answer(question, filters, result, version)
            except Exception:
                log.warning("Answer audit log unavailable")
        return result

    def _web_scope_supported(self, filters):
        # Every scope may be supplemented; the filters travel as context only.
        # Links must be showable, because external content is only usable with its sources.
        return bool(self.settings.show_source_links)

    def _search_external(self, question, filters, visitor, missing_topics=None, progress=None):
        if not getattr(self.settings, "web_search_enabled", False):
            return {"status": "disabled", "reason": "web_search_not_enabled", "cost_usd": 0.0}
        if not self._web_scope_supported(filters):
            return {"status": "unavailable", "reason": "scope_not_supported", "cost_usd": 0.0,
                    "message": "Web research is unavailable because source links are disabled. Enable source links to show external references."}
        from .web_research import WebResearch

        adapter = self.web_research or WebResearch(self.rag, enabled=True, base_filters=filters)
        _progress(progress, "web")
        try:
            result = adapter.call({"question": question, "missing_topics": missing_topics or []}, visitor=visitor)
        except Exception:
            # The production adapter contains accounting failures; a custom
            # adapter must likewise not expose provider diagnostics.
            result = {"status": "unavailable", "reason": "web_research_unavailable", "cost_usd": 0.0}
        _progress(progress, "citations")
        return result
