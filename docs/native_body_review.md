# Review candidate native-ad text

This offline command compares original saved text with the current body at the
same supplied URL. It prepares a private review packet. It does not update the
corpus, enable retrieval, call a model or approve CLAIMS results.

## Prepare

First prepare an [original input source packet](claims_input_review.md), including
the frozen current-source snapshot. Then use a new output directory:

```bash
python scripts/prepare_native_body_review.py \
  --source-packet .runtime/claims-input-review/checked-run \
  --output .runtime/native-body-review/new-run
```

The command checks every declared input artifact against the packet manifest.
It also checks the underlying ZIP, workbook, TXT, historical cleaning recipe,
CSV paragraphs, source positions and snapshot versions. Matching hashes prove
file consistency; they do not establish a reviewed source identity.

By default it compares the 50 historical CLAIMS input groups. To review other
saved text from the same validated 268-source inventory, select original IDs:

```powershell
python scripts/prepare_native_body_review.py --source-packet .runtime/claims_input_review_20261006/validated --output .runtime/video_body_review_20261006/validated --article-ids 116 121 122 123 124 125
```

An explicit selection is frozen in the manifest and summary. Unknown or
duplicate source IDs and duplicate current targets are rejected. A selected
source need not have historical CLAIMS paragraphs. Without those paragraphs,
retained-input coverage is **not applicable**, with null coverage values;
an empty sequence never becomes evidence of complete coverage. Original-page
completeness remains unknown in either case.

The output must be outside the source packet, and must not already exist. Keep
the packet outside Git and public hosting. The command requires no database,
API credentials or new dependencies.

## What the comparison means

| Result | Definition | What it does not establish |
| --- | --- | --- |
| Unique current URL | Exactly one active native record has the literal URL supplied by the original workbook. | Correct publisher identity or identical article versions. |
| Located retained paragraph | The complete selected input paragraph has a valid location in that current body, using the existing whitespace locator or pinned ASCII projection. All occurrences are retained. | Semantic support, completeness of the page or a publishable classification. |
| Strict location | A location permits only whitespace differences; it does not use ASCII projection. | A resolved source identity. |
| Unlocated paragraph | No complete retained-paragraph location was found in the unique current body. | All of the paragraph's content is absent. Joined words, inserted navigation, punctuation or chart structure may prevent matching. |
| Location inside declared range | At least one occurrence fits wholly inside one declared retrieval interval. | The record is eligible for retrieval. Eligibility is checked separately. |
| Ordered retained coverage | There is an ordered, non-overlapping occurrence sequence covering every supplied paragraph in the group. | The entire original webpage, image or video was preserved. The historical pipeline filtered text before selecting inputs. |
| Quality signal | Existing quality checks or stored issues flag a placeholder, short body, suspected truncation or other review concern. | A confirmed cause or a complete new body when no signal is present. |

Coordinates use Python Unicode characters and half-open intervals `[start, end)`.
Original and current text have separate coordinate systems. Neither is a PDF,
UTF-8 byte or browser UTF-16 coordinate.

No other publisher's body is substituted when the same-URL body fails to match.
Shared footers and republication may produce text matches across records; they
must not merge source identity. No unique current URL produces a comparison
notice, rather than a body-update proposal.

## Read the packet

| File | Use |
| --- | --- |
| `index.md` | Prioritized article directory. Video placeholders come first, followed by existing truncation flags and other unlocated paragraphs. This is a review order, not a quality score. |
| `articles/{id}.md` | Current and supplied metadata, original notes, both bodies, quality signals, retained input and exact locations. |
| `original/{id}.txt`, `current/{id}.txt` | Unchanged original bytes and the frozen current body's UTF-8 text. |
| `body_comparisons.json` | Reproducible comparison details, all occurrences, range checks and retrieval eligibility. |
| `pending_body_review.csv` | Pending decisions with blank reviewer, timestamp and notes. Not an approval file. |
| `pending_body_proposals.json` | Candidate text bound to the expected current record, version and body hash, and original source hashes. Not an importable JSONL batch. |
| `inputs/` | Essential frozen inputs and the previous packet manifest. The previous manifest describes the original source packet, not the smaller copied input directory. |
| `preparation_summary.json`, `packet_manifest.json` | Scope, count definitions, no-call/no-write results and output fingerprints. |

Each proposal preserves the complete previous payload. Display and counting
metadata stay separate from the workbook's pending assertions. New text does
not inherit old annotations or retrieval coordinates, remains ineligible for
retrieval, and has unknown original-page completeness. A longer TXT and a clean
quality check do not authorize replacement.

## Subsequent work

The review role is currently undecided. Source identity, text adoption, retained
ranges, page completeness and publication remain separate pending decisions.
Original workbook notes, video and image limitations must be considered.

After an approved decision, an update must recheck the expected current version,
preserve old evidence with its old body, record new provenance, select fresh
retrieval ranges and run the normal import and index checks. The existing PDF
recovery manifest must not be used for TXT files: it requires a real PDF and
page-bound extraction. The generic JSONL importer's format check is also not a
source approval or a check against concurrent body changes.

After a corpus change, rerun the normal CLAIMS source audit and follow the
[publication rules](claims_result_import.md). Body preparation does not release
the earlier classification candidates or supply gold labels for the
[customer evaluation](evaluation_methodology.md).
