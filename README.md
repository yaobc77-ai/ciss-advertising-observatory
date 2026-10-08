# CISS Advertising Observatory

A dashboard for exploring fossil fuel advertising, built for Boston University's Fall 2026 DS 549 project. It helps journalists, lawyers, and researchers compare records and examine claims with source evidence.

[Live dashboard](https://ciss-advertising-observatory-production.up.railway.app/data) · [Ask a question](https://ciss-advertising-observatory-production.up.railway.app/query) · [Static project page](https://yaobc77-ai.github.io/ciss-advertising-observatory-549/)

## Project requirements and application

| Requirement | Application path | Limit |
| --- | --- | --- |
| Compare native ads by company and outlet | Count matrix and CSV export | Counts describe the selected collection. |
| Find each company's publishers and each outlet's sponsors | Interactive graph, named relationships, distributions and supporting records | Connections reflect stored source fields. |
| Compare dates, outlets, companies and sponsors | Shared filters, annual counts, tied maxima and period comparisons | Missing and inferred dates remain distinct. |
| Explore themes supported by the data | Historical labels and published CLAIMS2 reads | Unverified labels are not confirmed greenwashing findings. |
| Explore social advertising | Company-post filters, charts, observations and record export | Company posts do not establish paid-ad identity. |
| Ask grounded questions across both collections | Model-selected data tools and cited RAG | Retrieved examples do not establish an exhaustive matching-ad list. |

**Data** contains Overview, Relationships and Records. **Query** presents a summary, evidence and limitations. **Evaluation**, available from Tools, defines the measures and displays a reviewed report when configured.

Local code and data may differ from the live deployment. Dated coverage, model runs, review and release evidence belong in [work](work.md), [goals](goal.md) and the [handoff record](docs/current_handoff.md). This README does not repeat mutable row counts or historical test scores. A feature or software test does not constitute client acceptance. Animal agriculture remains future scope.

## How it works

1. **Import:** validate source files and create versioned PostgreSQL records, retaining original text and metadata.
2. **Explore:** SQL computes filtered counts and relationships; records lead back to text and available source material.
3. **Answer:** the model selects bounded tools. SQL answers statistics; content questions retrieve passages and generate cited answers. Optional web findings remain outside collection counts.
4. **Classify offline:** CLAIMS results bind to source versions, taxonomy and review state. Query reads published results without rerunning classification per question.
5. **Evaluate separately:** freeze sources, configuration and scoring rules. Client questions, references and derived variants are evaluation-only, excluded from daily prompts and development examples.

See [the current pipeline](docs/architecture.md) and [the tool contract](docs/mcp_research_tools.md). Original text, media-derived text, historical annotations and reviewed classifications keep distinct provenance.

## Current technology

| Part | Technology |
| --- | --- |
| Application | Python 3.12/3.13, Dash, Waitress |
| Charts and tables | Plotly, Dash Cytoscape, Dash AG Grid |
| Data and validation | pandas, Pandera, Pydantic |
| Database and retrieval | PostgreSQL, pgvector, keyword and vector retrieval |
| Models | OpenAI Python SDK, Responses API; server-configured models and budgets |
| Text processing | pySBD, tiktoken |
| Tool interface | MCP Python SDK and web function calling, sharing one catalog |
| Delivery and checks | uv, Docker, Railway, GitHub Pages; pytest, Ruff, GitHub Actions |

Exact dependencies are in [pyproject.toml](pyproject.toml) and [uv.lock](uv.lock). Browsing and keyword search do not call a model. Generated answers can incur API charges, including interpretation of statistical questions.

## Run locally

Use Python 3.12 or 3.13, uv, and PostgreSQL with pgvector.

```sh
uv sync --frozen --extra test --extra mcp
```

Copy `.env.example` to `.env`. Set `OBS_DATABASE_URL` and a random `OBS_COOKIE_SECRET`; set `OPENAI_API_KEY` for generated answers. Keep credentials on the server.

```sh
uv run observatory migrate
uv run observatory serve
```

Open [localhost:8050](http://127.0.0.1:8050). Datasets are supplied separately; installing code does not load the live collection. See [the user guide](docs/guide.md), [import contract](docs/PROTOTYPE_DATA_PIPELINE.md) and [operations](docs/operations.md).

## Checks and evaluation

Run the free development gate with a fresh report directory:

```sh
uv run --no-sync python scripts/run_project_checks.py --report-dir .runtime/project_checks_new
```

The gate isolates protected evaluation material and records its actual scope. [Test instructions](docs/test_gate.zh-CN.md) cover private database and installed-package checks. Paid evaluation is separate and requires a bounded, authorized run.

Evaluation defines 16 measures and their denominators. Answer coverage differs from correctness among answered questions. Quote-location checks do not prove semantic support; AI-reference agreement does not replace human review. See [evaluation isolation](docs/client24_masking.zh-CN.md) and [current engineering verification](docs/handoff_cleanup.zh-CN.md). Detailed methodology and dated accuracy reports are retained locally, separately from this source release.

## Requirements updates

These are requirement revisions, not releases. Detailed dates and current status remain in [client goals](client_goal.md) and [user goals](user_goal.md). The complete acceptance ledger is retained locally in `client_finish.md`. Earlier IDs are retained without copying their historical completion claims.

| Revision | Source | Requirement |
| --- | --- | --- |
| R1 | FA26 project description | Dual-dataset dashboard, grounded RAG, deployment, documentation and demonstration. |
| R2 | 25 September client meeting; year not stated | Interactive knowledge graph, different years and reproducible imports. |
| R3 | Michelle's feedback email; send date not supplied | Accessible counts, company–publisher relationships and source records. |
| R4 | User | Separate Query/Data, readable charts, nearby details and secondary tools. |
| R5 | Client priority relayed by user | Bring supplied CLAIMS code and results into scope. |
| R6 | User | Consistent answers, bounded tools, comparisons and labeled web supplementation. |
| R7 | Client | Validation questions, RAG design, hallucination controls and evaluation criteria. |
| R8 | Project description (3) and user | Preserve revised requirements; repair engineering issues and maintain plan/work files. |
| R9 | User | Clear evaluation definitions and version-bound reports. |
| R10 | User | Objectives, sources, completion criteria and unresolved requirements. |
| R11 | Client, explicitly confirmed by user on 6 October | Full-article input, offline classification and review. |
| R12 | User | Lower-effort video recovery; accuracy concession applies only to video transcription. |
| R13 | User | Separate requirement ownership and record concrete failures and completed parts. |
| R14 | User | Unique posts, distinct media evidence, readable review and explicit unknown states. |
| R15 | User | Unified exploration with collection identity and separate counts. |
| R16 | User | Separate development and evaluation; later strict masking also covers client-question derivatives. |
| R17 | User | Search all saved company-post observations with exact source locations. |
| R18 | User | Prepare AI references for evaluation only. |
| Later updates | Source recorded per item | Follow the client/user ledgers and dated plan/work entries; engineering choices do not create client requirements. |

For each meeting note or email, retain its source, date authority, task, owner, dependency, completion check and status. Unknown dates and reviewers remain **TBD**. Original customer files and itemized baselines are retained separately in the local client-requirements folder.

## Documentation

- [Architecture](docs/architecture.md): current modules and flows.
- [Tool contract](docs/mcp_research_tools.md): inputs, outputs, scope and failures.
- [Plan](plan.md) / [work](work.md): next actions and dated evidence.
- [CLAIMS integration](docs/claims_integration_plan.md): source matching, imports and review limits.
- [Document index](docs/DOCUMENT_INDEX.zh-CN.md): specialist guides and historical records.
- [Simplification review](docs/project_simplification.zh-CN.md): removed duplication and remaining structural work.
