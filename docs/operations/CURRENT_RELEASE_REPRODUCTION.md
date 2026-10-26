# Current wheel reproduction

## Current local candidate: 6 October 2026

Use the [current source handoff candidate](../data/current_source_candidate_20261006.md)
for the latest package state, hashes and installation evidence. The new candidate
includes the company-post and media MCP modules and coordinated page-loading
changes. Same-machine source extraction, wheel building and installation have
been checked: 253 selected installed engineering cases passed, with three
Windows link-creation skips. The linked guide records the current candidate's
final hashes and status. This does not establish client acceptance.
The package version remains 0.4.10, so file hashes must identify the actual code.
Neither the published 0.4.10 receipt nor an earlier candidate's test count
verifies subsequently added modules.

### Earlier saved-TXT and statistics-preflight candidate

The later saved-TXT and statistics-preflight candidate has 598 source payloads
and all 84 runtime files. Its extracted-source wheel passed the installed
verification, 72 module imports and ten maintenance help entries in a new
external environment; 469 selected installed checks passed, with three Windows
link-creation skips. Evidence is separate in
`.runtime/current_source_handoff_text_20261006/`. No database or real model was
used. The final source keeps tested nondocument bytes unchanged; its manifest
and wheel hash identify the actual candidate. Earlier candidates below retain
their own versions and results. This remains same-machine, cache-only evidence.

### Earlier P18–P20 candidate

The refreshed candidate after P18–P20 has 84 runtime files and 72 importable
modules. It was built from the extracted source review archive and installed
in a fresh external Python 3.12.14 environment using the existing cache. All
runtime files, module imports, canonical dry-run, three sentence chunks and
source offsets passed, as did ten extracted maintenance help entries. Evidence
is `.runtime/current_source_handoff_p20_20261006/`.
The selected installed-wheel regression passed 957 cases with three Windows
link-creation skips; 12 integration/live cases were excluded. The final source
archive and receipts have their own hashes. This is same-machine engineering
evidence and does not demonstrate cold-machine setup, real-data admission or
semantic performance.

The earlier candidate's 81 files, 69 modules and 1,006 selected passing cases
belong to `.runtime/current_source_handoff_20261006/`; its three symlink skips
and original Windows socketpair-harness failures remain preserved. They do not
verify later code. Neither candidate proves independent client acceptance.

To prepare a review archive from the Git checkout, explicitly include current
nonignored untracked files that pass the builder's existing public checks:

```powershell
python scripts/build_handoff.py --include-untracked --output '<new candidate.zip>'
```

Without `--include-untracked`, the builder still uses tracked files only. The
manifest records the untracked paths, working-tree state, source hashes and
archived hashes. Private data, runtime results, credentials and backups remain
separate. A source ZIP is not a Git checkout; the builder needs a repository with
HEAD and must not be used to invent commit identity for extracted files.

The wheel alone does not contain maintenance `scripts/` or the `eval/` definitions
they read. Keep the complete source tree for those commands. The source archive
and installed package are checked separately; neither restores database content,
assets, real review decisions or client acceptance.

## Installed-wheel procedure

`scripts/verify_current_release.py` verifies the current installed package using
synthetic engineering fixtures. It is independent of the historical
`verify_clean_import.py` contract for 0.2.3 / `legacy600-v1`.

Build a wheel from the current checkout, create a fresh virtual environment, and
install that wheel with its `mcp` extra and normal dependencies. Use the lock file
to obtain the release dependency versions. Keep build output and environments in
an ignored directory such as `.runtime`. Run the verification from a clean
directory outside the checkout using the new environment's Python:

The locally verified setup used `uv build --wheel --offline`,
`uv export --offline --locked --no-dev --extra mcp --no-emit-project`, a new
`uv venv`, and `uv pip sync --offline` against the exported requirements. The wheel
was then installed with `uv pip install --offline --no-deps`. This used the existing
dependency cache; it does not demonstrate installation on a machine with no cache.

```powershell
& '<fresh-venv>/Scripts/python.exe' -I '<project>/scripts/verify_current_release.py' `
  --source-root '<project>' --wheel '<current-wheel.whl>' `
  --output '<new-evidence.json>'
```

The source root is used only for package file comparison. The script refuses to
import `observatory` from that checkout. It compares every Python module,
asset (including SVG) and SQL schema/migration against the wheel and installed
files, imports all packaged modules (including optional MCP), and runs canonical
JSONL CLI dry-run. It verifies the installed `sentence600-v1` definition,
deterministic chunk construction, original-text offsets and excluded header/footer
ranges. Package and dependency versions, file hashes and the exact wheel hash are
retained; the output file cannot overwrite earlier evidence.

The check disables dotenv, clears application configuration and model API
authority, and blocks Python socket connections. The sentence tokenizer must
already have its `cl100k_base` cache available. A missing tokenizer cache causes a
failure instead of downloading it. Building/installing dependencies is a separate
environment setup step; an offline dependency cache is sufficient when present.

For actual migration and import execution, explicitly add `--database` and provide
`OBS_TEST_DATABASE_URL` in the process environment. The script accepts only an
explicit loopback host and database name `obs_test` or `obs_test_<suffix>`. It does
not read `.env`, fall back to the application URL or connect to Railway. It checks
the actual database identity before writing and on each application connection.
The dedicated test database must already contain the PostgreSQL `vector`
extension. Before creating a random schema, the verifier derives the application
table names from the installed migrations, adds `schema_migrations`, and refuses
any same-name relation in `public`, including views and sequences. A random
schema with `public` on its search path does not by itself isolate existing
application tables. Use a dedicated test database without those public names;
unrelated public relations do not block the check. The script does not create a
new database or clear a populated one.

Immediately after the first migration, every unqualified application table name
must resolve to an ordinary table in the new schema. Missing tables, a public or
temporary-schema fallback, and views or other relation kinds are refused before
the repeated migration or fixture import. Later application connections repeat
the public-name and resolved-table checks. Unsupported migration table declaration
syntax is refused rather than silently omitted from the inventory.

All fixture writes use the validated fresh schema; cleanup drops only that
schema. Existing schemas are not truncated. These catalog checks do not protect
against unrelated concurrent DDL; use a test database with no concurrent
administrative changes.

This optional path exercises the actual CLI `migrate`, `index-prepare`,
`index-activate`, and canonical default upsert. It first activates the **empty**
test schema's sentence profile, which legitimately requires no embeddings. It then
imports two synthetic years, checks that earlier records remain, reimports the
second year unchanged, prepares sentence chunks, and confirms that activating
nonempty data without embeddings is blocked. It checks stored chunk locators and
that embeddings, generated answers and usage tables remain empty. It creates no
mock embeddings and makes no model calls.

A successful check establishes packaged code/assets/migrations and the tested
offline engineering path in that environment. It does not reproduce or certify
the live 275 records, 556 chunks, original source-data/index signatures, social
data, production vectors, historical answers/usage or semantic quality. A complete
production reproduction additionally needs hash-bound source/config/attachment
materials and a current database backup, including embeddings and history, with a
separate restore comparison. Regenerating real embeddings is a paid model action;
it is not performed by this script. Large-data performance and client acceptance
also require separate evidence.

The [2026-09-29 offline receipt](../../reports/releases/current_release_offline_reproduction_20260929.json)
records an actual fresh Windows environment with Python 3.12.14, current package
0.4.0, 81 locked runtime/MCP dependencies, all 50 package files compared, and 41
modules imported. Canonical CLI dry-run and three deterministic sentence chunks
passed. The receipt explicitly says the database path was not requested. Ten
verification guard tests and Ruff also passed. The earlier stage receipt is
retained separately and is not the final verification contract.

The [2026-09-30 isolated database receipt](../../reports/releases/current_release_database_reproduction_20260930.json)
records the same installed 0.4.0 wheel exercising the actual CLI against local
`obs_test`, inside a fresh random schema. Both ordered migrations ran to version 2;
the repeated migration check had no pending work. Default upsert preserved both
2025 and 2026 synthetic records, and reimporting the second year reported one
unchanged record. The active profile was `sentence600-v1`; all six stored sentence
chunks matched their source text. There were three distinct text hashes missing
embeddings because the two records intentionally shared the same fixture body.
Activation with those missing embeddings was blocked. `embeddings`, `answer_runs`,
`usage_ledger` and `generation_outputs` were all zero, with no model calls. The
script cleaned up only its random schema. The earlier offline receipt retains its
original `database: not_requested` scope. Neither receipt establishes production
corpus, vector or historical-answer restoration.

The [0.4.1 fixture-database receipt](../../reports/releases/current_release_database_reproduction_v0_4_1_20260930.json) separately verifies the patched wheel after the empty-canvas fix. It retains the same installed-package, isolated migration/upsert, locator and missing-embedding guards. The earlier 0.4.0 receipts and 37,000-row performance baseline remain evidence of their stated version.
