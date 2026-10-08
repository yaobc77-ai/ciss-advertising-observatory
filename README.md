# CISS Advertising Observatory

Explore fossil fuel advertising for Boston University's Fall 2026 DS 549 project. The dashboard helps journalists, lawyers, and researchers compare advertising records and examine claims with source evidence.

[Live dashboard](https://ciss-advertising-observatory-production.up.railway.app/data) · [Project page](https://yaobc77-ai.github.io/ciss-advertising-observatory-549/)

## What it does

- **Data:** compare company and news-outlet counts; explore relationships; filter dates and records; export tables.
- **Query:** ask statistical or content questions and read answers with supporting advertisements and limitations.
- **Sources:** open record text and available original links, PDFs, image previews, and historical annotations.
- **Collections:** explore native advertising and social-media company posts together while keeping their counts separate.
- **CLAIMS:** read published classifications with their source and review status.

Counts describe the stored collection, not all advertising activity. Company posts do not establish paid-ad identity. Historical labels are not confirmed greenwashing findings. Retrieved examples do not establish an exhaustive list.

Local changes and the live deployment may differ. The optional structured-question interpreter is implemented and defaults to off; its real-model performance has not been validated. Animal agriculture remains future scope.

## Current stack

| Part | Technology |
| --- | --- |
| Application | Python 3.12–3.13, Dash, Waitress |
| Visuals and tables | Plotly, Dash Cytoscape, Dash AG Grid |
| Database and retrieval | PostgreSQL, pgvector, keyword and vector search |
| Data validation | pandas, Pandera, Pydantic |
| Model and tools | OpenAI Python SDK, Responses API, optional MCP SDK |
| Text processing | pySBD, tiktoken |
| Delivery and checks | uv, Docker, Railway, GitHub Pages, pytest, Ruff, GitHub Actions |

Dependencies are fixed in [pyproject.toml](pyproject.toml) and [uv.lock](uv.lock). Browsing and keyword search are free of model calls; generated answers can incur API charges.

## Run locally

Use Python 3.12 or 3.13, uv, and PostgreSQL with pgvector.

```sh
uv sync --frozen --extra test --extra mcp
```

Copy `.env.example` to `.env`. Set `OBS_DATABASE_URL`, a random `OBS_COOKIE_SECRET`, and `OPENAI_API_KEY` for generated answers.

```sh
uv run observatory migrate
uv run observatory serve
```

Open [localhost:8050](http://127.0.0.1:8050). Source datasets and attachment bundles are supplied separately; installation does not load the live collection. Keep credentials on the server.

## Key files

| File | Purpose |
| --- | --- |
| [User guide](docs/guide.md) | Pages, filters, records, and answers |
| [Architecture](docs/architecture.md) | Application components and data flow |
| [Data dictionary](docs/data_dictionary.md) | Record fields and counting units |
| [Tool contract](docs/mcp_research_tools.md) | Available tools, scope, and failure states |
| [Operations](docs/operations.md) | Import, configuration, and deployment |
| [Document index](docs/DOCUMENT_INDEX.zh-CN.md) | Short directory of project documentation |

## Requirements updates

[Client goals](client_goal.md) preserve the project description, meeting notes, and client feedback. [User goals](user_goal.md) record later implementation requests separately. Each ledger retains sources, dates, completion checks, and unresolved items; implementation does not constitute client acceptance.

Historical reports remain in the source repository. This README avoids repeating dated data counts or test scores.
