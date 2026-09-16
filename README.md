# CISS Advertising Observatory

A Python Dash application for browsing fossil fuel native advertisements and asking questions with locatable source evidence. PostgreSQL and pgvector run locally. OpenAI provides embeddings and grounded answer generation.

**Research preview: the real native corpus is connected and the application runs locally.** The import snapshot contains 268 records, with 256 countable records and 221 eligible retrieval bodies or prefixes. The dashboard, filtered CSV export, free keyword search and paid evidence answers are implemented. See the [handoff](docs/handoff.md) and [acceptance status](docs/acceptance_status.md) for evidence and remaining work.

Social data, the designated GitHub remote, a fixed public domain and Cloudflare configuration remain reserved integration points, as requested by the user. The social view explicitly shows **not connected**. Human semantic validation and full project acceptance remain pending.

## Run locally (Windows)

### Existing project on this machine

The project already has a Python `.venv` and its own PostgreSQL + pgvector runtime in `.runtime`. **You do not need to download PostgreSQL separately.** It does not install a Windows database service or change the system PATH. Run these commands from the project directory:

```powershell
.\scripts\Start-Observatory.ps1
.\scripts\Test-Observatory.ps1
```

Open [http://127.0.0.1:8050](http://127.0.0.1:8050). The start script starts the project database and launches the app in the background. Browsing, CSV export and **Search keywords** do not call a model.

```powershell
# Stop the managed app first. The database has its own stop command.
.\scripts\Stop-Observatory.ps1
.\scripts\Stop-Postgres.ps1
```

For foreground debugging, start PostgreSQL and run `.\.venv\Scripts\python.exe -m observatory.cli serve`; stop that foreground app with Ctrl+C. The managed stop script only targets a matching process it recorded.

### Recreate on another Windows machine

Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run `uv sync --frozen --extra test`. The [PostgreSQL setup](docs/local_postgres.md) script downloads the locked project runtime, so no separate system database installation is required. Supply the private source files listed in the [data dictionary](docs/data_dictionary.md). Keep credentials in `.env`, using `.env.example` only as a reference.

```powershell
.\scripts\Setup-Postgres.ps1
.\.venv\Scripts\python.exe -m observatory.cli init-db
.\.venv\Scripts\python.exe -m observatory.cli import-native --root .
.\scripts\Start-Observatory.ps1
.\scripts\Test-Observatory.ps1
```

Native imports use **complete snapshot semantics**: an old record absent from the new snapshot becomes inactive, with its history retained. Do not use a partial CSV as a full replacement. See [operations](docs/operations.md) before updating data.

```powershell
# These first two commands make paid API calls, subject to the application ledger.
.\.venv\Scripts\python.exe -m observatory.cli index
.\.venv\Scripts\python.exe -m observatory.cli answer "What does this archive say about carbon capture?"
.\.venv\Scripts\python.exe -m observatory.cli budget
```

## Tests

```powershell
# Offline engineering tests, without database integration or live API calls.
.\.venv\Scripts\python.exe -m pytest -q -m "not integration and not live"

# Dedicated project test database. These tests clear its test tables.
.\scripts\Start-Postgres.ps1
.\scripts\Setup-TestDatabase.ps1
.\.venv\Scripts\python.exe -m pytest -q -m "integration and not live"

# Runtime verification and a new timestamped backup.
.\scripts\Test-Postgres.ps1
.\scripts\Backup-Postgres.ps1
```

The setup command prepares the dedicated `obs_test` database and its configuration. Repeated setup on this existing machine was verified; a complete installation on another clean Windows machine has not been performed. Database tests refuse a database name that does not start with `obs_test`. A skipped test is not a passed feature. Exact backup and restore commands are in the [handoff](docs/handoff.md).

## Evaluation boundary

The latest saved development run `0369cb87f07648359dccd28687598a6b` exercised 13 native cases. It covered 13/13 required support passages, validated 17/17 citation locations, and passed the respective record, count and refusal checks. Its gold remains `draft_not_frozen`, `semantic_support` remains `pending_human_review`, and `overall_pass` is null. The latest engineering check completed 93 tests and Ruff without failures.

The [current evaluation report](reports/evaluation.md) identifies the applicable run, data version and earlier diagnostic history. The [current AI-assisted review](reports/assisted_semantic_review_citation_first.md) separates quotation support, reference context and remaining human review; it is not a semantic acceptance score. See the [evaluation protocol](docs/evaluation_protocol.md) before interpreting any metric.

## Data and documentation

- [Data dictionary and import mapping](docs/data_dictionary.md)
- [Architecture and evidence flow](docs/architecture.md)
- [Operations and budget accounting](docs/operations.md)
- [User guide](docs/user_guide.md)
- [Project requirements and remaining acceptance](docs/acceptance_status.md)
- [Current handoff and exact maintenance commands](docs/handoff.md)
- [Research preview presentation](deliverables/research_preview.pptx) and [Chinese demo script](deliverables/demo_script.zh-CN.md)
- [Complete resource appendix](FA26_RESOURCE_APPENDIX.zh-CN.md)

Source data, private configurations, database files and backups are excluded from Git. The designated remote has not been provided or published. A clean checkout requires the separately supplied source files described in the data dictionary. Historical scraper notebooks do not run automatically. The handoff explains the reused packages and source delivery manifest.
