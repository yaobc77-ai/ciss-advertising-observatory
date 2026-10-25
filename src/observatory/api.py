"""JSON-only backend for a separate frontend: `observatory api`.

The same Service the Dash app uses, without any page. Every route is read-only
except /api/v1/ask, which spends model budget under the per-visitor limits.
Filters use the dashboard's Filters model; list fields accept repeated or
comma-separated query parameters (?sponsors=Shell&sponsors=BP or ?sponsors=Shell,BP).
"""

import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from werkzeug.exceptions import HTTPException

from .models import Filters
from .quote_links import citation_locations, mark_segments, parse_highlights
from .topic_compare import compare_topics, company_choices, topic_table
from .year_drilldown import UNKNOWN, year_filters, year_records

log = logging.getLogger(__name__)

LIST_FIELDS = ("publishers", "sponsors", "platforms", "accounts", "keywords", "labels", "record_ids")
BOOL_FIELDS = ("include_unknown_dates", "include_inferred_dates")
SORTS = ("date", "title", "sponsor", "publisher", "platform", "account", "keyword", "dataset")


class _JSON(DefaultJSONProvider):
    sort_keys = False

    @staticmethod
    def default(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, (set, frozenset, tuple)):
            return list(value)
        return str(value)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    filters: Filters = Field(default_factory=lambda: Filters(dataset="all"))


class BadRequest(ValueError):
    pass


def filters_from_args(args, default_dataset="all"):
    values = {}
    for key in LIST_FIELDS:
        items = [part.strip() for raw in args.getlist(key) for part in raw.split(",") if part.strip()]
        if items:
            values[key] = items
    for key in BOOL_FIELDS:
        if key in args:
            raw = args[key].strip().lower()
            if raw not in ("true", "false", "1", "0"):
                raise BadRequest(f"{key} must be true or false")
            values[key] = raw in ("true", "1")
    for key in ("date_from", "date_to", "date_presence"):
        if args.get(key):
            values[key] = args[key]
    values["dataset"] = args.get("dataset", default_dataset)
    try:
        filters = Filters(**values)
    except ValidationError as exc:
        raise BadRequest(_first_error(exc)) from None
    year = args.get("year")
    if not year:
        return filters
    year = UNKNOWN if year.lower() == "unknown" else year
    if year != UNKNOWN and not (year.isdigit() and len(year) == 4):
        raise BadRequest("year must be a four-digit year or 'unknown'")
    narrowed = year_filters(filters, year)
    if narrowed is None:
        raise BadRequest("year lies outside the other date filters")
    return narrowed


def year_from_args(args):
    year = args.get("year", "")
    if year.lower() == "unknown":
        return UNKNOWN
    if not (year.isdigit() and len(year) == 4):
        raise BadRequest("year must be a four-digit year or 'unknown'")
    return year


def page_from_args(args, max_limit=100):
    try:
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 20))
    except ValueError:
        raise BadRequest("offset and limit must be whole numbers") from None
    if offset < 0 or not 1 <= limit <= max_limit:
        raise BadRequest(f"offset must be >= 0 and limit between 1 and {max_limit}")
    sort_by = args.get("sort_by", "date")
    if sort_by not in SORTS:
        raise BadRequest(f"sort_by must be one of {', '.join(SORTS)}")
    descending = args.get("descending", "true").lower() not in ("false", "0")
    return {"offset": offset, "limit": limit, "sort_by": sort_by, "descending": descending}


def _first_error(exc):
    err = exc.errors()[0]
    where = ".".join(str(part) for part in err.get("loc", ()))
    return f"{where}: {err.get('msg', 'invalid value')}" if where else err.get("msg", "invalid value")


def _visitor():
    """A stable per-client id for rate limits; never a credential."""
    supplied = (request.headers.get("X-Visitor-Id") or "").strip()
    if supplied and len(supplied) <= 128:
        return "api:" + supplied
    seed = f"{request.remote_addr}|{request.headers.get('User-Agent', '')}"
    return "api:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _referenced_ids(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_id" and isinstance(item, str):
                found.add(item)
            else:
                _referenced_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _referenced_ids(item, found)
    return found


def compact_answer(body):
    """Drop the internal trace and every passage the answer does not cite (often >1 MB)."""
    body = dict(body)
    body.pop("research_trace", None)
    cited = _referenced_ids([body.get(key) for key in ("citations", "cited_claims", "sections",
                                                         "structured_result", "summary")], set())
    body["evidence"] = [e for e in body.get("evidence") or [] if e.get("evidence_id") in cited]
    return body


def create_api(service, settings, record_details=None) -> Flask:
    api = Flask("observatory_api")
    api.json = _JSON(api)
    origins = set(getattr(settings, "api_cors_origins", ()) or ())

    if record_details is None:
        from .records import RecordDetails

        record_details = RecordDetails(service.db, settings)

    @api.after_request
    def cors(response):
        origin = request.headers.get("Origin")
        if origin and (origin in origins or "*" in origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Visitor-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @api.before_request
    def preflight():
        if request.method == "OPTIONS":
            return "", 204
        return None

    @api.errorhandler(BadRequest)
    def bad_request(exc):
        return jsonify({"error": str(exc)}), 400

    @api.errorhandler(404)
    def not_found(_exc):
        return jsonify({"error": "Not found"}), 404

    @api.errorhandler(Exception)
    def unavailable(exc):
        if isinstance(exc, HTTPException):
            return jsonify({"error": exc.name}), exc.code
        log.warning("API request failed: %s", type(exc).__name__)
        return jsonify({"error": "The service is temporarily unavailable."}), 503

    @api.get("/api/v1")
    def index():
        return jsonify({"endpoints": sorted(str(rule) for rule in api.url_map.iter_rules()
                                            if str(rule).startswith("/api/"))})

    @api.get("/api/v1/health")
    def health():
        state = service.health()
        public = {key: state[key] for key in (
            "status", "record_counts", "countable_record_counts", "chunks", "active_profile",
            "source_data_version", "index_version", "data_version") if key in state}
        return jsonify(public), (200 if state.get("status") == "ok" else 503)

    @api.get("/api/v1/facets")
    def facets():
        dataset = request.args.get("dataset", "all")
        if dataset not in ("native", "social", "all"):
            raise BadRequest("dataset must be native, social or all")
        return jsonify(service.facets(dataset))

    @api.get("/api/v1/dashboard")
    def dashboard():
        filters = filters_from_args(request.args)
        return jsonify(service.dashboard(filters, **page_from_args(request.args)))

    @api.get("/api/v1/records")
    def records():
        filters = filters_from_args(request.args)
        return jsonify(service.page(filters, **page_from_args(request.args)))

    @api.get("/api/v1/timeline/year")
    def timeline_year():
        """One year's totals and newest records per collection (a clicked timeline bar)."""
        year = year_from_args(request.args)
        args = request.args.copy()
        args.pop("year")
        filters = filters_from_args(args)
        limit = page_from_args(request.args)["limit"]
        return jsonify(year_records(service, filters, year, limit=limit))

    @api.get("/api/v1/compare/topics")
    def compare_options():
        """The keyword topic table and the companies the comparison can use (client item C15)."""
        table = topic_table()
        return jsonify({"version": table["version"], "status": table["status"], "method": table["method"],
                        "topics": [{k: t[k] for k in ("id", "label", "label_zh", "terms")} for t in table["topics"]],
                        "companies": company_choices()})

    @api.get("/api/v1/compare")
    def compare():
        """One company's native ads and social posts on chosen topics, by period (client item C15)."""
        args = request.args
        company = (args.get("company") or "").strip()
        topics = [t.strip() for value in args.getlist("topics") for t in value.split(",") if t.strip()]
        if not company or not topics:
            raise BadRequest("company and topics are required, e.g. ?company=ExxonMobil&topics=carbon_capture,hydrogen")
        try:
            bounds = [date.fromisoformat(args[key]) if args.get(key) else None for key in ("date_from", "date_to")]
        except ValueError:
            raise BadRequest("date_from and date_to must be YYYY-MM-DD") from None
        try:
            result = compare_topics(service.db, company, topics, granularity=args.get("granularity", "year"),
                                    date_from=bounds[0], date_to=bounds[1])
        except ValueError as exc:
            raise BadRequest(str(exc)) from None
        return jsonify(result), (404 if result["status"] == "not_found" else 200)

    @api.get("/api/v1/records/<record_id>")
    def record(record_id):
        value = record_details.get(record_id)
        if value is None:
            return jsonify({"error": "Not found"}), 404
        ranges = parse_highlights(request.args.getlist("hl"))
        if ranges:
            value = dict(value, highlights=_highlights(value, ranges, request.args))
        return jsonify(value)

    @api.post("/api/v1/ask")
    def ask():
        try:
            payload = AskRequest.model_validate(request.get_json(silent=True))
        except (ValidationError, TypeError) as exc:
            message = _first_error(exc) if isinstance(exc, ValidationError) else "Send JSON"
            raise BadRequest(f"{message}. Body: {{\"question\": \"...\", \"filters\": {{\"dataset\": \"all\"}}}}") from None
        result = service.answer(payload.question, payload.filters, _visitor())
        status = 429 if result.status == "limited" else 200
        body = result.model_dump(mode="json")
        body["citations"] = citation_locations(body.get("citations") or [], body.get("evidence") or [])
        if request.args.get("detail", "compact") != "full":
            body = compact_answer(body)
        return api.response_class(json.dumps(body, ensure_ascii=False),
                                  status=status, mimetype="application/json")

    @api.get("/api/v1/knowledge-maps")
    def knowledge_maps():
        """Prebuilt co-occurrence maps (Jaccard weights, top-k edges, Louvain communities)."""
        from .cooccurrence_ui import latest_maps

        maps = latest_maps()
        if maps is None:
            return jsonify({"error": "No knowledge maps found; set NATIVEADS_KNOWLEDGE_MAPS_DIR "
                                     "to the folder holding */knowledge_maps.json."}), 404
        view = request.args.get("view")
        if view:
            views = maps.get("views") or {}
            if view not in views:
                raise BadRequest(f"view must be one of {', '.join(views)}")
            return jsonify({key: maps[key] for key in maps if key != "views"} | {"views": {view: views[view]}})
        return jsonify(maps)

    # Existing JSON routes (company timeline, knowledge graph, record attachments).
    from .knowledge_routes import register_knowledge_routes
    from .records import register_record_routes

    register_knowledge_routes(api, service, record_details)
    register_record_routes(api, record_details)
    return api


def _highlights(record, ranges, args):
    """Validated quote spans for a record link built by an answer (version must match)."""
    if args.get("v") != record.get("version_id"):
        return {"status": "version_changed", "spans": []}
    text = record.get("body")
    observation = args.get("obs")
    if observation:
        variants = (record.get("social_admission") or {}).get("variants") or []
        text = next((v.get("body") for v in variants if v.get("source_record_id") == observation), None)
    if mark_segments(text, ranges) is None:
        return {"status": "position_mismatch", "spans": []}
    return {"status": "ok", "source_observation_id": observation or None,
            "spans": [{"start": start, "end": end, "text": text[start:end]} for start, end in ranges]}
