# Database migrations and incremental imports

This guide maintains the import contract introduced by the September 25 prototype. For the current end-to-end flow, use [architecture](architecture.md). Historical migration and test receipts retain their original dates. Imports do not infer an unknown source schema or automatically approve article text for RAG.

## Database upgrades

Run from the project root, with the existing server-only `OBS_DATABASE_URL` configuration:

```powershell
.venv/Scripts/python.exe -m observatory.cli migration-status
.venv/Scripts/python.exe -m observatory.cli migrate
```

`init-db` remains supported and performs the same initialization. Both commands apply missing migrations before the existing retrieval bootstrap. Import commands do not silently upgrade the database: run `migrate` when deploying this code version.

The authoritative migration inventory is the [ordered SQL directory](../src/observatory/migrations). Use `migration-status` against the intended database to distinguish available scripts from applied migrations. A migration present in source is not proof that production applied it. `schema.sql` is historical; future changes use new consecutive migrations. Migrations do not import corpus records or generate embeddings.

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

Use the [development gate](test_gate.zh-CN.md) for free offline checks and its private-database procedure for SQL integration checks. Do not run the full historical test tree directly: evaluation-dependent fixtures are isolated from development.

Import checks cover existing-schema adoption, repeat migrations, changed-checksum rejection, rollback, cross-year preservation, unchanged re-import, explicit snapshot retirement and cross-dataset ID rejection. A passing run applies only to its recorded code, database and selected checks.

This importer does not establish production load limits, provide unconfirmed source mappings or close semantic RAG acceptance. Those require source definitions, scale targets and review.
