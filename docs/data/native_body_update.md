# Reviewed saved-text updates

This maintenance tool prepares a saved-TXT update from an explicit review decision. It does not approve a source, authenticate a reviewer, produce CLAIMS labels or establish customer acceptance.

## Inputs and outputs

Inputs are the complete [original-input review packet](claims_input_review.md), its matching [current-body comparison packet](native_body_review.md), and a separate `review.json`. Both packets remain unchanged. The tool checks every declared file hash and recomputes the comparisons and proposals from their frozen inputs.

Body packets may use the default 50 historical groups or an explicit selection
from the validated original-source inventory. The updater verifies that
selection, its input counts and coverage counts before rebuilding proposals.
Sources with no historical input keep coverage not applicable; they do not
acquire fabricated CLAIMS history. Changing a proposal and recomputing its file
hash is insufficient: it must still match the frozen original sources and
current-record bindings.

Each proposal is `pending`, `adopt` or `reject`. Pending decisions have no reviewer or approval assertions. A completed decision records a review ID, human or AI reviewer type, reviewer name, timestamp with timezone, reason and evidence references. Adoption also requires explicit source-identity confirmation, a separate retrieval decision and a completeness value: unknown, partial or complete. These are recorded assertions, not independently verified identities or conclusions.

Enabled retrieval requires new, explicit character ranges in the new TXT. Ranges must be valid; the existing counting/admission restrictions and selected-text quality checks must pass. A source can be adopted with retrieval disabled. Old ranges are never copied to the new body.

Adopted text carries a public saved-TXT origin note, and enabled retrieval carries
the existing reviewed-interval note. These fixed descriptions do not expose
private review paths or notes. Stored text remains unchanged, including parts
excluded from retrieval; adopting page text does not recover or validate a video.

Preparation writes:

- `review.json`: the exact frozen review bytes.
- `update_plan.json`: new canonical records, expected current-source bindings and deterministic target versions.
- `preparation_summary.json`: decision counts and limits.
- `plan_manifest.json`: hashes of the three prepared files, written last.

The plan is **not generic import JSONL**. Applying a reviewed update must use the guarded path below. Exporting or reading a plan does not update the database.

## Commands

Run from the project root. Use new output paths; existing outputs cannot be overwritten.

```powershell
python scripts/prepare_native_body_update.py review-template --source-packet .runtime/claims_input_review_20261006/validated --body-packet .runtime/native_body_review_20261006/validated --out .runtime/native_body_update_20261006/review.pending.json
```

This creates a separate pending review template. Preserve it; save later recorded decisions to a new file. Do not fill decisions merely to make import succeed.

```powershell
python scripts/prepare_native_body_update.py plan --source-packet .runtime/claims_input_review_20261006/validated --body-packet .runtime/native_body_review_20261006/validated --review .runtime/native_body_update_20261006/review.pending.json --out .runtime/native_body_update_20261006/pending_plan
```

An all-pending plan has zero updates. Neither preparation command loads database settings, accesses a database, uses the network or calls a model.

For a reviewed batch and an authorized target environment only:

```powershell
python scripts/prepare_native_body_update.py apply --source-packet SOURCE_PACKET --body-packet BODY_PACKET --review RECORDED_REVIEW --out NEW_APPLICATION_DIRECTORY
```

`apply` rebuilds and validates the plan from the original packets and the review. It uses the configured database URL; inspect the target before invoking it. The command does not grant authorization to write a remote database. An all-pending or rejected-only review stops before database settings are loaded. An apply failure leaves the prepared plan for inspection but no success receipt; do not treat the directory's existence as adoption.

After a successful transaction, `apply_receipt.json` records the import report. This additional receipt is separate from the preparation manifest; the latter describes the prepared files and never claims they were applied.

## Source and version protection

The new body retains its exact decoded TXT characters. Current title, publisher, sponsor, URL, date, collection term, counting status and other metadata are preserved. The old workbook remains a separate source assertion, not a metadata override.

The previous body, body-specific issues, duplicate-text markers and body-review information are preserved as history. New-body quality is checked again. Old annotations remain with the old database version and in historical payload fields; current annotations are empty. Old PDF attachments are not automatically rebound to a new text hash. Unknown or partial completeness remains visible in record details and the source graph; a TXT is not described as a PDF recovery.

`Database.import_batch(expected_current=...)` freezes the batch and requires exact coverage of every target record. In the same transaction as the import, it takes the existing publication lock, locks the target records and versions, and checks active status, dataset, URL, current version, actual body hash and payload hash before any writes. Missing, withdrawn or changed targets reject the entire batch. This path cannot replace a dataset snapshot.

A retry is accepted when the active record is already the **exact full target version**, including metadata and provenance. Identical body text with different metadata is not enough. Such a retry uses the existing unchanged path. The report's `already_applied` counts only this retry exception, when the expected old version is no longer current.

The tool also rejects modified source files, changed review bytes or changed prepared batch/guard/summary values. Deterministic versions contain the recorded review timestamp; preparation does not add a fresh runtime timestamp to the payload on every retry.

## Limits and follow-up

Synthetic engineering tests cover preparation, version guards and rollback behavior. Seven additional tests passed on the existing local PostgreSQL 18.6 in one disposable schema of the loopback `obs_test` database. They cover adoption and exact retry, stale/withdrawn targets, whole-batch rejection, an actual late-write failure and three two-connection lock scenarios. The schema was removed; public business tables and the project database were not accessed. The private receipt and JUnit output are in `.runtime/guarded_import_validation_20261006/`.

These checks validate the listed transactions and lock scenarios, not all writer patterns, production performance, semantic source correctness, whole-page coverage or customer approval. A real source update still requires recorded source/text decisions, an authorized target environment and a post-update source audit.

Ordinary import rebuilds lexical chunks. It does not request embeddings. New vectors and CLAIMS processing are separate follow-up work; paid runs and publication follow project authorization rules. Published CLAIMS and evaluation reports bound to previous versions do not automatically validate the new body.

The original 50-group and six-video-placeholder review templates retain their
pending state as frozen preparation history. On 6 October 2026, a separate
recorded AI engineering review adopted six supplied page TXT files into the
loopback project database. It preserved their full text, metadata, counting and
old versions, and enabled 23 lexical chunks only within reviewed ranges. The
exact repeat added zero versions. Partial completeness and saved-TXT origin are
visible in record details. The private application receipt is
`.runtime/video_text_review_20261006/local_apply_receipt.json`.

The selected 169 offline tests passed; a separate files-only audit checked the
review and transaction receipts. These results establish the stated local text
update and source-position checks. They do not validate a complete publisher
page, OCR accuracy, a video transcript, classification semantics, the entire
database or customer acceptance. New vectors and remote publication were not
performed. A subsequent [two-advertisement update](native_saved_text_update_20261006.md)
adopted the complete supplied TXT for source IDs 12 and 16 after separate AI
source/text review. Both had truncated bodies; their disclosure and interview
attribution are retained. It added two local versions and five lexical chunks,
with zero new versions on exact repeat. Coverage remains partial and no labels,
vectors or hosted update were created. The current review materials were separately
rebound; original pending templates retain their historical scope.

Other saved-text candidates still need actual source/text review. Changed current
versions require fresh bindings rather than replaying old guards.

A subsequent [nineteen-text batch](native_truncated_text_update_20261006.md)
recorded actual AI full-text/source reviews of twenty further candidates. It
adopted nineteen and rejected replacing source 79 because the candidate omits
existing disclosure and a footnote. Full TXT and old versions remain; explicit
ranges exclude related titles, image credits and identified defects. The guarded
local import added nineteen versions and 74 lexical passages, with zero new
versions on exact repeat. Current detail reads and source positions were checked;
coverage remains partial. No vectors, classification, model run or hosted update
were created. Original review templates keep their historical state.
