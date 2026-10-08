# MCP and research tools

Checked against local source on 8 October 2026. This is the current tool contract; see [system design](architecture.md) for the complete pipeline and [work.md](../work.md) for dated execution evidence.

The web application uses **Responses API function calling**. The optional **Model Context Protocol (MCP) server** exposes the same `ToolCatalog` through a separate process. Starting MCP does not start the web planner, migrate a database or import data. The public dashboard does not host a remote MCP endpoint.

## Shared read tools

These tools do not call a language model. Inputs below show the main fields; the generated schemas in [research_tools.py](../src/observatory/research_tools.py) are authoritative and reject unknown fields.

| Tool | Input | Output and boundary |
| --- | --- | --- |
| `resolve_entity` | `query`, `entity_type` (`sponsor`, `publisher`, `account`), optional `limit` up to 10, filters | Source-name candidates and ambiguity. Accounts require social scope; a candidate does not merge identities. |
| `record_statistics` | Filters, `group_by`, `ranking`, `periods`, `measure`, optional `denominator_filters` or `paid_ad_status` | Exact selected-record counts, distributions or shares with date basis and separate collection units. Uses the full selection, including countable records without searchable body text. |
| `search_records` | `query` up to 2,000 characters, optional `limit` up to 10 and `comparison_scopes`, filters | Bounded keyword passages, source references and search diagnostics. The web service subsequently performs hybrid retrieval and cited generation for content answers. Passages do not establish corpus totals or an exhaustive matching list. |
| `find_records` | Literal `title` up to 500 characters, optional `limit` up to 10, filters | Exact case-insensitive stored-title matches, or literal substring candidates if no exact match exists. Candidates bind record/version/body hash; multiple matches require selection. SQL wildcard characters remain literal. |
| `get_record` | `record_id`, optional `body_start`, `body_limit` up to 12,000 characters and `source_observation_id`, filters | A permitted unchanged text interval with character positions and version. A differing social text observation needs its exact source ID; denied text is not returned. |
| `get_record_metadata` | `record_id`, requested `fields`, filters | Original field values, each field's status and source-cell provenance; normalized display values remain separate. Missing or conflicting fields do not invalidate other known requested fields. |
| `get_record_sources` | `record_id`, filters | Public original/archive references, source basis and historical annotation limits. Does not fetch arbitrary URLs or return private source paths. |
| `get_graph_schema` | No parameters | Node types, predicates, provenance policy and adapter limits. |
| `get_graph_neighborhood` | Optional `record_id`, `offset`, `limit` up to 5, filters | Typed relationships and supporting sources for a bounded page of native articles. It is neither the full graph nor a counting tool. |
| `get_claims_matches` | Optional `nc_ids`, `sc_ids`, taxonomy fingerprint, `review_state`, `offset`, `limit` up to 20, filters | Published, current-source CLAIMS2 assignments with definitions, review states and exact evidence. Missing assignments are not negatives; this does not classify, approve or write. |

`get_record_metadata.fields` accepts `title`, `publisher`, `sponsor`, `original_url`, `publication_date`, `collection_search_term`, `disclosure_language` and `disclosure_location`. Request only the fields needed, together in one read; omit `fields` only for an explicit all-fields request. Original spreadsheet metadata takes precedence over cleaned copies. Missing provenance or conflicting original cells remain unknown or require review; an external page cannot silently fill an original field.

Historical social labels retain their recorded True/False/Unknown states and generated explanations. They are unverified source annotations, separate from native labels and published CLAIMS2 assignments. Source-listed companies and accounts do not prove paid sponsorship or unique organizational identity.

## Scope and statistics rules

The catalog is constructed with trusted base filters. Tool arguments may narrow that selection; they cannot silently clear it or switch outside it. The caller's explicit date basis remains binding. Source and supplemented dates are labeled separately, and Unknown is not zero or a negative finding.

Supported filter fields are `dataset` (`native`, `social`, `all`), `publishers`, `sponsors`, `platforms`, `accounts`, `keywords`, `labels`, `record_ids`, `date_from`, `date_to`, `include_unknown_dates`, `date_presence` and `include_inferred_dates`. Name and record-ID lists are bounded by the schema. Account and historical social-label filters require an explicit social scope. Label choices use OR, not an inferred intersection.

| Operation | Contract |
| --- | --- |
| Distributions | `group_by` supports `none`, `publishers`, `sponsors`, `platforms`, `accounts`, `years` and `social_historical_labels`. Native articles and company posts retain separate units. |
| Highest years | `group_by="years"` and `ranking="highest"` return every tied highest year. Unknown dates remain separate. |
| Period comparison | `periods` contains 2–3 distinctly named date ranges, each with at least one explicit endpoint. Endpoints are inclusive. Shared filters apply within one statistics snapshot; missing dates fall outside the periods. Periods cannot be combined with grouping, shares or a comparison denominator. |
| Share | `measure="share"` uses a stated denominator within the active scope; numerator filters narrow that group. A named denominator uses `denominator_filters`. Grouping is not supported for shares, and a zero denominator is undefined. |
| Historical source states | Requires social scope, count, all rankings, no periods or denominator. Returns each original label's True/False/Unknown counts and annotation coverage; overlapping labels must not be added into one total. |
| Verified paid social ads | `paid_ad_status="verified_paid"` asks for this explicit identity. Missing identity evidence requires clarification; company-post counts cannot substitute. |

Entity resolution uses actual source values and controlled aliases. Multiple plausible entities remain ambiguous. Title lookup likewise returns candidates rather than selecting the first hit. A missing stored title does not establish absence on the web.

Source/version checks apply before and after reads where needed. Continued pages and matching-record browsing retain the submitted selection and version. These checks are optimistic consistency guards; separate tool calls are not one database transaction.

## Web planner and answer path

```text
Question + trusted filters
  → bounded model interpretation
  → shared read tools
  → deterministic result, or retrieved evidence + generated answer
  → scope / source / citation checks
  → Summary + Evidence + Scope and limitations
```

The planner has a bounded step and tool-call budget. `set_research_plan` and `request_clarification` are planner controls, not shared data tools. A supported compound plan contains 2–3 explicit tasks; execution retains each task's result, missing fields and failure state. It does not run an unrestricted agent loop or accept arbitrary SQL.

For content comparisons, `comparison_scopes` selects 2–3 distinct sponsor or outlet scopes. Each target is retrieved separately within the shared filters. The web service then combines keyword/vector candidates and optional fixed media evidence. The model selects program-built reference IDs; the program restores original quotes and checks their source versions, hashes and locations. A matching quote proves that the text exists, not that the interpretation is correct or the claim is true. Retrieved evidence is not a complete positive/negative classification of the collection.

Every answer uses Summary, Evidence, and Scope and limitations. Tool trace and API cost are available separately. Counts are calculated by data tools; interpretation and content generation still use the configured API budget. Loading indicators report real stages instead of simulated internal model reasoning.

The retained legacy answer route is a configuration alternative. MCP clients choose their own model and presentation; they do not automatically receive the web planner, hybrid answer generation or web layout.

## Media read and evaluation boundary

### Media read

`get_media_evidence` is exposed through MCP. It accepts `query`, optional `media_types` (`text`, `image`, `video`), `limit` up to 5, and narrowing filters. Each route considers bounded candidates, then merges by current record/version. Image and video are the default routes.

The operator mounts a fixed bundle using `OBS_MEDIA_BUNDLE_PATH`, `OBS_MEDIA_BUNDLE_SHA256` and `OBS_MEDIA_ASSET_ROOT`. Callers cannot supply local paths, arbitrary URLs or version maps. Each read verifies bundle bytes, saved assets and current record permissions. It does not run OCR, transcription, classification, downloads or a paid model.

`not_configured`, `missing_material`, `no_match` and `unavailable` distinguish missing configuration, absent media, no text match and validation/read failure. None proves that a claim is absent. OCR, descriptions and captions retain their own origins and available character, image or time locations.

The web planner does not select this tool directly: its service reads the fixed bundle internally after content search. The web renderer already distinguishes these evidence types and locations. Actual material recovery, review and activation remain separate work; use [media answers](media_answers.md) for its dated evidence and limits.

### Evaluation-only historical tools

`get_content_matches` is not exposed in normal MCP or web operation and is always excluded from the general web planner. Its historical question-specific publication mechanism is retained only for explicit evaluation. The client-question catalog, references, variants and per-question outputs must not enter ordinary tool prompts or development examples. Source-independent CLAIMS taxonomies remain usable. See [masking rules](client24_masking.zh-CN.md).

## Optional external lookup

External findings remain outside the stored advertising collection. They do not supply missing collection counts, replace original metadata cells, merge source identities or enter indexes/classifications automatically. Their provider citations are not the original-text character-location guarantee. Calls can incur model charges and retain usage accounting even when a result fails.

### Web application

When `OBS_WEB_SEARCH_ENABLED=true`, an unresolved collection answer or incomplete original-field answer may receive one external supplement if scope and budget permit. The original collection result, known fields and reason for incompleteness remain visible.

Exact zero counts and successful collection answers do not trigger fallback. Invalid requests, source-integrity errors, source drift, unavailable collection/statistics services, operational limits and budget failures are preserved; external results cannot bypass those checks. A previous external attempt is not repeated. The supplement is labeled **Outside the advertising collection**, with separate web references.

### MCP ticket workflow

When enabled, `search_external_sources` is an additional MCP tool:

1. Call `search_records` in the same server instance.
2. A healthy empty keyword search in supported scope may issue `web_fallback_ticket`.
3. Call `search_external_sources` with that ticket only.

The ticket expires after five minutes and is consumed before dispatch, including failed attempts. The collection version is checked again. The request cannot substitute another question, arbitrary URL or SQL. Empty keyword retrieval is not proof of semantic absence; this route does not run the web application's complete hybrid-generation path first.

### CLAIMS source maintenance

`find_claims_source_candidates` is a separate maintenance tool for legacy excerpts with unresolved source articles. It searches locally first, may make one paid external lookup, and returns candidates with pending review. It is hidden unless `OBS_CLAIMS_SOURCE_SEARCH_ENABLED=true`; it does not publish classifications or update source records. See [source discovery](claims_source_discovery.md).

## Start the separate MCP server

From the repository root:

```sh
uv sync --frozen --extra test --extra mcp
uv run python -m observatory.mcp_server --dataset native
```

Configure the private database and required application settings according to the [README](../README.md#run-locally). Keep credentials private. A client normally launches the stdio process; it may narrow the trusted scope with `--publisher` or `--sponsor` startup arguments.

For a separate local HTTP endpoint:

```sh
uv run python -m observatory.mcp_server --transport streamable-http --host 127.0.0.1 --port 8051
```

HTTP is restricted to loopback. Public remote MCP would require a separate deployment and access-control design. Starting the process is not permission to spend, import or publish.

| Setting | Purpose |
| --- | --- |
| `OBS_RESEARCH_AGENT_ENABLED=true` | Enable model selection of shared tools in the web application. |
| `OBS_WEB_SEARCH_ENABLED=true` | Enable bounded external lookup in applicable web/MCP paths. |
| `OBS_CLAIMS_SOURCE_SEARCH_ENABLED=false` | Keep legacy source maintenance hidden. |

These are configuration examples, not evidence that a running process loaded them. Check the actual runtime before reporting availability.

## Verification and source ownership

Use the [free test gate](test_gate.zh-CN.md) for current permitted engineering checks. Paid model evaluation, independent semantic review and client acceptance require separate evidence; passing schemas or quote-position checks does not establish answer accuracy.

- Tool schemas, selection and dispatch: [research_tools.py](../src/observatory/research_tools.py).
- Model planning and prompt policy: [research_agent.py](../src/observatory/research_agent.py), [prompts.py](../src/observatory/prompts.py).
- MCP transport: [mcp_server.py](../src/observatory/mcp_server.py).
- Answer and fallback orchestration: [service.py](../src/observatory/service.py).
- Retrieval, statistics and graph relationships: [db.py](../src/observatory/db.py), [knowledge_graph.py](../src/observatory/knowledge_graph.py).
- Source restoration and presentation: [rag.py](../src/observatory/rag.py), [app.py](../src/observatory/app.py).

Current collection sizes, published-result coverage and test totals belong in dated execution records. This contract does not repeat them or imply that local source changes have been deployed.
