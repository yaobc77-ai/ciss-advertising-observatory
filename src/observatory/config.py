"""Server-only configuration; never serialize Settings to the browser."""

import os
from dataclasses import dataclass, field
from decimal import Decimal

from dotenv import load_dotenv

PUBLIC_ENV_PREFIX = "NATIVEADS_"
INTERNAL_ENV_PREFIX = "OBS_"


def apply_public_env_names(environ=None):
    """Accept NATIVEADS_* (the public name) for every OBS_* setting; NATIVEADS_* wins.

    OBS_* keeps working, so existing deployments need no change.
    """
    environ = os.environ if environ is None else environ
    for key, value in list(environ.items()):
        if key.startswith(PUBLIC_ENV_PREFIX):
            environ[INTERNAL_ENV_PREFIX + key[len(PUBLIC_ENV_PREFIX):]] = value


@dataclass
class Settings:
    database_url: str = field(default="", repr=False)
    show_source_links: bool = True
    host: str = "127.0.0.1"
    port: int = 8050
    monthly_budget_usd: Decimal = Decimal("100")
    generation_model: str = "gpt-5.6-luna"
    embedding_model: str = "text-embedding-3-small"
    max_output_tokens: int = 1600
    requests_per_minute: int = 5
    requests_per_day: int = 30
    concurrency: int = 2
    cookie_secret: str = field(default="", repr=False)
    # Hosted HTTPS deployments send session cookies only over TLS.
    secure_cookies: bool = False
    trusted_proxy: str = ""
    # Explicit opt-in preserves the deterministic baseline for reproducible checks.
    research_agent_enabled: bool = False
    # One typed interpretation compiled to existing reads; opt in after validation.
    question_intent_enabled: bool = False
    # /compare runs the same question with and without retrieval (paid); demo only.
    compare_demo_enabled: bool = False
    # `observatory api`: JSON-only backend for a separate frontend.
    api_port: int = 18060
    api_cors_origins: tuple = ("http://localhost:5173", "http://127.0.0.1:5173",
                               "http://localhost:3000", "http://127.0.0.1:3000")
    # Planner reads may select social posts by X relations (mentions, hashtags,
    # replies to collected posts) and companies by source profile; opt in after
    # the A/C comparison.
    relation_selection_enabled: bool = False
    # Paid source discovery is confined to the separate maintenance MCP server.
    claims_source_search_enabled: bool = False
    # Public semantic questions may search the web after a validated corpus miss.
    web_search_enabled: bool = False
    # Private curated attachments can be mounted independently of application code.
    record_asset_root: str = field(default="", repr=False)
    record_asset_manifest_sha256: str = field(default="", repr=False)
    # A curated frozen-run report is mounted separately; never accept UI uploads.
    evaluation_report_path: str = field(default="", repr=False)
    evaluation_report_sha256: str = field(default="", repr=False)
    evaluation_plan_sha256: str = field(default="", repr=False)
    # Reviewed native content decisions are mounted by the server operator.
    content_publication_path: str = field(default="", repr=False)
    content_publication_sha256: str = field(default="", repr=False)
    content_review_sha256: str = field(default="", repr=False)
    # Fixed local media evidence prepared and mounted by the server operator.
    media_bundle_path: str = field(default="", repr=False)
    media_bundle_sha256: str = field(default="", repr=False)
    media_asset_root: str = field(default="", repr=False)

    @classmethod
    def from_env(cls):
        load_dotenv(override=False)
        apply_public_env_names()
        return cls(
            database_url=os.getenv("OBS_DATABASE_URL", ""),
            show_source_links=os.getenv("OBS_SHOW_SOURCE_LINKS", "true").lower()
            == "true",
            host=os.getenv("OBS_HOST", "127.0.0.1"),
            # Platforms such as Railway assign the listening port through PORT.
            port=int(os.getenv("OBS_PORT") or os.getenv("PORT") or "8050"),
            monthly_budget_usd=Decimal(os.getenv("OBS_MONTHLY_BUDGET_USD", "100")),
            generation_model=os.getenv("OBS_GENERATION_MODEL", "gpt-5.6-luna"),
            embedding_model=os.getenv("OBS_EMBEDDING_MODEL", "text-embedding-3-small"),
            requests_per_minute=int(os.getenv("OBS_REQUESTS_PER_MINUTE", "5")),
            requests_per_day=int(os.getenv("OBS_REQUESTS_PER_DAY", "30")),
            concurrency=int(os.getenv("OBS_CONCURRENCY", "2")),
            cookie_secret=os.getenv("OBS_COOKIE_SECRET", ""),
            secure_cookies=os.getenv("OBS_SECURE_COOKIES", "false").lower() == "true",
            trusted_proxy=os.getenv("OBS_TRUSTED_PROXY", ""),
            research_agent_enabled=os.getenv("OBS_RESEARCH_AGENT_ENABLED", "false").lower() == "true",
            question_intent_enabled=os.getenv("OBS_QUESTION_INTENT_ENABLED", "false").lower() == "true",
            compare_demo_enabled=os.getenv("OBS_COMPARE_DEMO_ENABLED", "false").lower() == "true",
            api_port=int(os.getenv("OBS_API_PORT", "18060")),
            api_cors_origins=tuple(o.strip() for o in os.getenv(
                "OBS_API_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
            ).split(",") if o.strip()),
            relation_selection_enabled=os.getenv("OBS_RELATION_SELECTION_ENABLED", "false").lower() == "true",
            claims_source_search_enabled=os.getenv("OBS_CLAIMS_SOURCE_SEARCH_ENABLED", "false").lower() == "true",
            web_search_enabled=os.getenv("OBS_WEB_SEARCH_ENABLED", "true").lower() == "true",
            record_asset_root=os.getenv("OBS_RECORD_ASSET_ROOT", ""),
            record_asset_manifest_sha256=os.getenv("OBS_RECORD_ASSET_MANIFEST_SHA256", ""),
            evaluation_report_path=os.getenv("OBS_EVALUATION_REPORT_PATH", ""),
            evaluation_report_sha256=os.getenv("OBS_EVALUATION_REPORT_SHA256", ""),
            evaluation_plan_sha256=os.getenv("OBS_EVALUATION_PLAN_SHA256", ""),
            content_publication_path=os.getenv("OBS_CONTENT_PUBLICATION_PATH", ""),
            content_publication_sha256=os.getenv("OBS_CONTENT_PUBLICATION_SHA256", ""),
            content_review_sha256=os.getenv("OBS_CONTENT_REVIEW_SHA256", ""),
            media_bundle_path=os.getenv("OBS_MEDIA_BUNDLE_PATH", ""),
            media_bundle_sha256=os.getenv("OBS_MEDIA_BUNDLE_SHA256", ""),
            media_asset_root=os.getenv("OBS_MEDIA_ASSET_ROOT", ""),
        )
