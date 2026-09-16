# CISS Advertising Observatory

A Python Dash application for browsing fossil fuel native advertisements and asking questions with locatable source evidence. PostgreSQL and pgvector run locally. OpenAI provides embeddings and grounded answer generation.

**Research preview: the real native corpus is connected and the application runs locally.** Version 0.2.4 contains 275 records, with 263 countable records, 226 eligible retrieval bodies and 558 source-located chunks. Data version: `5114ebc1cf9afe59cdaa715e3ea45166`. One article now includes reviewed partial continuation from PDF-265; its old text, evidence and label basis remain preserved. The dashboard, filtered CSV export, free keyword search and paid evidence answers are implemented. See the [0.2.4 quote context and reproduction report](reports/quote_context_v0_2_4.md), [recovery report](reports/pdf265_body_recovery.md), [publication checks](outputs/pdf265_publication_validation_20260916.json), [handoff](docs/handoff.md) and [acceptance status](docs/acceptance_status.md).

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

The CLI requires `config/native_admissions.json`, `config/native_body_ranges.json` and `config/native_body_recoveries.json`. Supply the recovery manifest's hash-matched PDF and extracted text separately. The [recovery report](reports/pdf265_body_recovery.md) includes the optional, pinned PDF extraction command. Missing recovery files stop import rather than reverting to the old text. PDF extraction is a maintenance dependency, not a requirement for running the app against its existing database.

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

Version **0.2.4 passed 245 engineering tests (19.03 seconds)**. It preserves PDF sentence context using a length-preserving segmentation view while copying quotes from the untouched source. All 4,672 candidate passages across 558 chunks passed substring, coverage and paragraph/page boundary checks. This does not repair incomplete source/chunk endings.

The fixed original development run returned 8 answers, 2 counts and 3 abstentions: 19/19 citation locators, 2/2 counts and 3/3 no-evidence abstentions. Seven social/cross-dataset questions remain pending. Two separate PDF diagnostic questions now have fuller quotes, but the second still misattributes the actor. Both runs remain pending human semantic review; see the [0.2.4 report](reports/quote_context_v0_2_4.md) and [human review sheet](reports/citation_review_v0_2_4.csv). The following results are retained historical checks.


The 0.2.3 engineering suite passed **209 tests in 19.63 seconds**. The [publication checks](outputs/pdf265_publication_validation_20260916.json) confirm one new record version, 274 unchanged records, and all 275 unchanged on repeat import; 558 current chunk locators, 86 historical evidence locators and 15 original development gold spans remain valid. These are source and engineering checks, not semantic acceptance. The original 94 truncation warnings remain a quality boundary: one article received partial continuation, not a verified complete transcript.

Two targeted PDF-265 smoke questions use the separate `eval/pdf265_recovery_smoke.jsonl` file. [Run `6c250056841b47feab178ffcc95bf2bd`](outputs/pdf265_recovery_paid_smoke_20260916.json) returned two answers, with support passages 2/2, evidence locators 6/6, citation locators 2/2 and two local language matches. The second answer still misstates the subject as “the advertisement has shown”; its estuary-testing caveat is preserved, but semantic acceptance remains pending. The file's `suite=development` field does not make it the original 20-question development suite or the 20-question acceptance draft. See the [evaluation index](reports/evaluation.md).

Historical evidence remains versioned: the [data revision report](reports/data_revision_v0_2.md) describes the earlier data snapshot, and the 0.2.1 engineering suite passed **164 tests**. A local Lingua check withholds clearly wrong-language generated claims while retaining evidence, raw structured output and settled costs.

Version 0.2.2 added explicit per-claim attribution and quantity requirements to the existing output schema. Its 52 relevant regression tests passed. Its paid development run `d26eb540a6114cfe9672a755c43f39a7`, on the earlier `d85…` data version, returned 8 answers, 2 exact counts and 3 abstentions, with 16/16 citation locators valid and 8 local language matches. These checks do not establish semantic acceptance: answer focus and completeness still need review. See the [0.2.2 report](reports/claim_contract_v0_2_2.md), [AI review](reports/assisted_semantic_review_v0_2_2.md) and [evaluation protocol](docs/evaluation_protocol.md). Earlier failures remain preserved; human validation, frozen acceptance and real social/cross-dataset validation remain pending.

## Data and documentation

- [Data dictionary and import mapping](docs/data_dictionary.md)
- [Architecture and evidence flow](docs/architecture.md)
- [Operations and budget accounting](docs/operations.md)
- [User guide](docs/user_guide.md)
- [Project requirements and remaining acceptance](docs/acceptance_status.md)
- [Current handoff and exact maintenance commands](docs/handoff.md)
- [0.2.2 research preview presentation](deliverables/research_preview_v0_2_2.pptx) and [Chinese demo script](deliverables/demo_script_v0_2_2.zh-CN.md): retained historical snapshot with 554 chunks; the current 0.2.4 database has 558.
- [Complete resource appendix](FA26_RESOURCE_APPENDIX.zh-CN.md)

Source data, private configurations, database files and backups are excluded from Git. The designated remote has not been provided or published. A clean checkout requires the separately supplied source files described in the data dictionary. Historical scraper notebooks do not run automatically. The handoff explains the reused packages and source delivery manifest.

The 0.2.3 wheel was built and installed in an isolated package-check environment: package and Lingua versions were confirmed, and `/healthz`, `/_dash-layout` and `/assets/observatory.css` returned 200. The local app was restarted on the current 558-chunk snapshot. This is not a complete setup or public-access acceptance test on another machine.

Version 0.2.4 was also reproduced from an isolated source installation and an installed wheel, each importing into empty `obs_test`: 275 new versions, then 275 unchanged on repeat; 558 chunk locators and 15 development gold spans matched. The 7 required private inputs were supplied separately. See [handoff](docs/handoff.md) for the exact procedure. Main data was unchanged; old answer history is outside this fresh snapshot import. This was on the same Windows machine, not a clean-machine or public-access acceptance test.
