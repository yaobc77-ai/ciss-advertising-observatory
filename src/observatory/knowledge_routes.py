"""Read-only, bounded graph exports using the same filters as the dashboard."""

from flask import jsonify, request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .models import Filters


class GraphRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: Filters = Field(default_factory=Filters)
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=5, ge=1, le=20)


def register_knowledge_routes(server, service, record_details=None):
    @server.get("/api/knowledge-graph/schema")
    def knowledge_schema():
        from .knowledge_graph import build_graph

        graph = build_graph([], links_enabled=False)
        return jsonify({key: value for key, value in graph.items()
                        if key not in {"nodes", "edges", "warnings"}})

    @server.get("/api/knowledge-graph/organizations")
    def organization_export():
        from .knowledge_graph import organization_overview

        try:
            overview = organization_overview(service.db.source_value_counts())
        except Exception:
            return jsonify({"error": "The organization overview is temporarily unavailable."}), 503
        response = jsonify(overview)
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.get("/api/company-timeline")
    def company_timeline_export():
        from datetime import date

        from .company_timeline import company_timeline

        try:
            company = (request.args.get("company") or "").strip()
            if not company or len(company) > 120:
                raise ValueError("company")
            bounds = [date.fromisoformat(request.args[key]) if request.args.get(key) else None
                      for key in ("date_from", "date_to")]
            result = company_timeline(service.db, company, granularity=request.args.get("granularity", "month"),
                                      date_from=bounds[0], date_to=bounds[1])
        except ValueError:
            return jsonify({"error": "Use company=<name>, granularity=month|quarter|year and ISO dates."}), 400
        except Exception:
            return jsonify({"error": "The company timeline is temporarily unavailable."}), 503
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.post("/api/knowledge-graph")
    def knowledge_export():
        try:
            payload = GraphRequest.model_validate(request.get_json(silent=True))
            if payload.filters.dataset not in {"native", "social", "all"}:
                raise ValueError("Unsupported collection")
        except (ValueError, TypeError, ValidationError):
            return jsonify({"error": "Use native, social or all collection filters, offset >= 0 and limit 1–20."}), 400
        try:
            graph = service.knowledge_graph(payload.filters, offset=payload.offset,
                                            limit=payload.limit, record_details=record_details)
        except Exception:
            return jsonify({"error": "The knowledge graph is temporarily unavailable."}), 503
        response = jsonify(graph)
        response.headers["Cache-Control"] = "no-store"
        return response
