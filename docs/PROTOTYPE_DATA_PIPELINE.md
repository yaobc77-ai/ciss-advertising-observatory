# Data pipeline prototype — September 25, 2026

This prototype supports ordered database upgrades and explicit incremental imports for new years. It does not infer the University of Miami source schema, manufacture social data, or automatically approve article text for RAG.

## Database upgrades

Run from the project root, with the existing server-only `OBS_DATABASE_URL` configuration:

```powershell
.venv/Scripts/python.exe -m observatory.cli migration-status
.venv/Scripts/python.exe -m observatory.cli migrate
```

`init-db` remains supported and performs the same initialization. Both commands apply missing migrations before the existing retrieval bootstrap. Import commands do not silently upgrade the database: run `migrate` when deploying this code version.

The authoritative migration files are `src/observatory/migrations/0001_baseline.sql`, `0002_dashboard_indexes.sql`, and future consecutively numbered SQL files. The old `schema.sql` is retained as a historical schema reference; new changes belong in a new migration. `0001` adopts the known previous schema using idempotent DDL and also creates a fresh database schema. `0002` adds two ordinary indexes for active-dataset and record-version lookup. It does not build a new vector index.

The `schema_migrations` table records version, filename, SHA-256 checksum and application time. New migrations and their ledger entries commit together. The existing import advisory lock serializes upgrades with imports. Applied files must not be edited; changed checksums, gaps or a database newer than the installed code cause a failure before pending SQL is applied. Checksums normalize Windows/Unix line endings.

Take a normal database backup before a production upgrade. This is a forward migration prototype; it has no automated downgrade command. No corpus rows, versions, embedding cache or usage history are removed by these migrations. A matching migration ledger verifies which scripts ran; it does not detect arbitrary manual schema changes made afterwards.

## Existing import commands: upsert is the default

```powershell
.venv/Scripts/python.exe -m observatory.cli import-native --root .
.venv/Scripts/python.exe -m observatory.cli import-social exports/social.csv --mapping config/social_mapping.example.json
```

These commands now default to `--mode upsert`: records in the batch are created or versioned, and records absent from the batch stay active. Re-importing identical input preserves the existing version. The historical native loader still requires its existing admission, body-review and recovery inputs; it is not a generic new-year CSV reader.

Only use an explicit snapshot when the input is the **complete authoritative replacement for that whole dataset**, across all years:

```powershell
.venv/Scripts/python.exe -m observatory.cli import-native --root . --mode snapshot
```

Snapshot mode marks missing records inactive; immutable source versions and old citations remain stored. An incomplete one-year snapshot would retire earlier years. Empty or mixed-dataset snapshots fail. Social CSV imports also support explicit `--mode snapshot`.

## Canonical JSONL for new batches

`import-records` accepts one complete `RecordInput` object per nonblank line. Use a source-specific adapter to produce this contract after the customer's field definitions are available. It does not guess mappings from column names.

The minimal native record is:

```json
{"record_id":"source-system:stable-ad-id","dataset":"native","url":"https://example.org/original-ad","published_at":"2026-01-20","title":"Source title","body":"Exact original text","retrievable":false,"raw":{"source_record_id":"stable-ad-id"},"provenance":[{"source":"customer-export.csv","row":2}]}
```

This is a format example, not a source record for the research corpus. Social records additionally require `"platform":"Facebook"` or another explicitly supplied platform. `account` and `sponsor` are separate fields and must follow the source's definitions. Dates are ISO `YYYY-MM-DD` or `null`; do not fabricate missing dates. Native/social URLs must be HTTP(S) source links; unavailable original URLs may still be stored, but the importer does not check online availability.

```powershell
# First validate every row, without opening the database or calling a model.
.venv/Scripts/python.exe -m observatory.cli import-records exports/native-2026.jsonl --dataset native --dry-run

# Then add/update this year's batch; older years stay active.
.venv/Scripts/python.exe -m observatory.cli import-records exports/native-2026.jsonl --dataset native

# Deliberate complete-dataset replacement; --dataset is mandatory for snapshots.
.venv/Scripts/python.exe -m observatory.cli import-records exports/all-native-years.jsonl --dataset native --mode snapshot
```

Important contract details:

- `record_id` is explicit, stable and preserved. It must match `^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`: 1–200 ASCII characters, beginning with a letter or digit, followed only by letters, digits, periods, underscores, colons or hyphens. This keeps the existing record-detail and attachment routes valid. UUIDs and IDs such as `source:2026` are accepted; slashes, query/fragment delimiters, percent escapes, whitespace and `.`/`..` are rejected. If a source uses a different ID format, its adapter must map it consistently to this contract and retain the exact original ID in `raw` (for example `raw.source_record_id`); the importer does not silently rewrite IDs. Reuse the same ID for later versions of the same source record. Different yearly exports must not assign new IDs to the same ad or reuse an old ID for a different ad. IDs cannot change dataset. The importer does not merge near duplicates or infer identity from a title.
- Upsert replaces the submitted record's whole current payload; it is not a partial-field patch. Supply all fields to retain. Missing fields use the existing `RecordInput` defaults; omitted `countable` is `true`, omitted `retrievable` is `false`.
- Original body, raw fields, supplied provenance and annotations are preserved. A JSONL file checksum and exact line number are appended to provenance and its hash is stored in the import report. Same filename and content produce the same payload; renaming or repackaging the source file changes its provenance and may create a new version.
- Unknown top-level fields, duplicate IDs/JSON keys, invalid booleans, invalid URLs, invalid retrieval offsets and dataset mismatches fail the entire input validation before the database transaction. Put source-specific unmapped fields in `raw`. Keep external source IDs there until an authoritative mapping is agreed.
- `retrievable` remains `false` unless explicitly supplied. `true` requires nonempty original text and valid nonempty source spans; this structural check is not a quality approval. Source completeness, attribution and rights still need the project's review process. The loader neither generates labels nor certifies their correctness.
- `retrieval_ranges` uses ordered, non-overlapping half-open `[start,end]` Python Unicode-character offsets into the exact `body`. Existing citation/version rules are unchanged.
- Embedding generation remains the separate `index` command and can incur paid API usage. Imports themselves do not call an LLM or embedding API. New chunks can be available to keyword retrieval before their embeddings are generated.
- The prototype validates the complete JSONL in memory. This creates an atomic, reviewable batch but is not a streaming importer for arbitrarily large exports; split large deliveries into stable upsert batches and measure representative scale.

## Verification and limits

```powershell
.venv/Scripts/python.exe -m pytest tests/test_canonical_import.py tests/test_pipeline_integration.py -q
```

Integration tests require `OBS_TEST_DATABASE_URL` with a database name starting `obs_test`. They use isolated per-test schemas and never import fixtures into the live corpus. Tests cover existing-schema adoption, repeat migrations, modified migration rejection, rollback after failed SQL, cross-year preservation, unchanged re-import, explicit snapshot retirement and cross-dataset ID rejection.

This prototype does not establish production load limits, provide customer source mappings, or close semantic RAG acceptance. Those require formal data, scale targets and domain review.
