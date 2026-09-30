# Current wheel reproduction

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
extension. All tables and fixture writes use a fresh random schema; cleanup drops
only that schema. Existing schemas are not truncated.

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

The [2026-09-29 offline receipt](../reports/current_release_offline_reproduction_20260929.json)
records an actual fresh Windows environment with Python 3.12.14, current package
0.4.0, 81 locked runtime/MCP dependencies, all 50 package files compared, and 41
modules imported. Canonical CLI dry-run and three deterministic sentence chunks
passed. The receipt explicitly says the database path was not requested. Ten
verification guard tests and Ruff also passed. The earlier stage receipt is
retained separately and is not the final verification contract.

The [2026-09-30 isolated database receipt](../reports/current_release_database_reproduction_20260930.json)
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
