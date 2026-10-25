"""Independent, fictional research-agent fixtures for development checks.

Written against the product interfaces (ResearchAgent, ToolCatalog), not
copied from the protected legacy test modules, so tests that need a scripted
planner do not import evaluation-only material.
"""
import copy
import json
from types import SimpleNamespace

from observatory.config import Settings
from observatory.models import Filters
from observatory.research_agent import ResearchAgent
from observatory.research_tools import ToolCatalog

TOOLS = ("resolve_entity", "record_statistics", "search_records", "get_graph_schema", "get_graph_neighborhood",
         "get_record_sources", "get_record", "get_claims_matches", "get_content_matches")


def response(name, args, *, call_id="call_1", usage=True, status="completed"):
    """One provider reply that calls `name` with `args`."""
    return {"id": f"resp-{call_id}", "model": "gpt-5.6-luna", "status": status,
            "usage": {"input_tokens": 120, "output_tokens": 40, "input_tokens_details": {"cached_tokens": 20}}
            if usage else None,
            "output": [{"type": "function_call", "name": name, "call_id": call_id,
                        "arguments": args if isinstance(args, str) else json.dumps(args)}]}


class FakeBudget:
    def __init__(self):
        self.reserved, self.settled, self.uncertain_calls = [], [], []

    def reserve(self, amount, visitor, kind, model):
        self.reserved.append((amount, visitor, kind, model))
        return f"reservation-{len(self.reserved)}"

    def settle(self, reservation, actual, usage):
        self.settled.append((reservation, actual, usage))

    def uncertain(self, reservation, reason):
        self.uncertain_calls.append((reservation, reason))

    def reservation_cost(self, reservation):
        return 0.0


class FakeCatalog:
    """Strict read-only tool definitions; `results` maps a tool to a result or a function of its arguments."""

    def __init__(self, results=None):
        self.results = results or {}
        self.called = []

    def definitions(self):
        return [{"type": "function", "name": name, "description": "Read only", "strict": True,
                 "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}
                for name in TOOLS]

    def entity_context(self):
        return {"publishers": ["Harbor Daily", "Bay Weekly"], "sponsors": ["tidal co", "marigold gas"]}

    def call(self, name, args):
        self.called.append((name, args))
        result = self.results.get(name)
        if callable(result):
            return result(args)
        return copy.deepcopy(result) if result is not None else {
            "status": "ok", "tool": name, "filters": Filters().model_dump(mode="json"),
            "data_version": "v-fictional", "data_refs": ["record:fictional-1"]}


def harness(responses, *, catalog=None, budget=None, settings=None, **options):
    """A ResearchAgent whose provider returns `responses` in order; returns (agent, rag, catalog, sent)."""
    sent, pending = [], iter(responses)

    def create(**kwargs):
        sent.append(copy.deepcopy(kwargs))
        item = next(pending)
        if isinstance(item, Exception):
            raise item
        return item

    rag = SimpleNamespace(settings=settings or Settings(), budget=budget or FakeBudget(),
                          client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    catalog = catalog or FakeCatalog()
    return ResearchAgent(rag, catalog, **options), rag, catalog, sent


class FakeService:
    """The few service reads ToolCatalog needs to resolve names; fictional values only."""

    def __init__(self, facets=None):
        self._facets = facets or {"sponsors": ["tidal co"], "publishers": ["Harbor Daily"], "accounts": ["Tidal Co Ferries"]}
        self.settings = Settings()

    def facets(self, dataset):
        # Native ads have no accounts and social posts no publishers, as in the collection.
        absent = {"native": {"accounts"}, "social": {"publishers"}}.get(dataset, set())
        return {key: ([] if key in absent else list(values)) for key, values in self._facets.items()}

    def health(self):
        return {"status": "ok", "data_version": "v-fictional",
                "countable_record_counts": {"native": 3, "social": 2}}


def catalog_for(filters=None, facets=None):
    """A real ToolCatalog over a fictional service, both collections by default; returns (catalog, service)."""
    service = FakeService(facets)
    return ToolCatalog(service, filters or Filters(dataset="all")), service
