# Original CLAIMS input source review

This offline command prepares private source-review material from the supplied
CLAIMS repository. It does not run the repository's notebook, call a model, fetch
URLs, access a database or publish results.

## Inputs and their roles

| Input | Role |
| --- | --- |
| `Manual dataset Native Ads.zip` | Original saved article text and its metadata table. |
| `New/articletexts/{id}.txt` inside that ZIP | Original text associated with the upstream article ID. Raw UTF-8 bytes are preserved. |
| `New/native_ad_dataset.xlsx` inside that ZIP | Supplied ID, URL, publisher, title, sponsor and other fields, including notes. These remain source assertions requiring review. |
| `sampled_50_articles_paragraphs.csv` | Selected paragraph IDs, upstream article groups and text used by the saved run. |
| `native_ads_paragraphs_cleaned.csv` | The historical retained paragraph sequences. |
| `clean_paragraph_data.ipynb` | Pinned description of the historical cleaning recipe. Only literal settings are read; no notebook code executes. |
| Optional frozen source snapshot | Exact URL candidates in the supplied current-record snapshot. This is a file comparison, not a live database check. |
| Optional complete `claims-audit` directory | Prior paragraph-to-source and classification candidates, checked through the existing audit loader and copied with their hashes. |

The ZIP also contains `New/~$native_ad_dataset.xlsx`, an Office lock file. It is
not a second dataset. No ZIP member is extracted to a caller-supplied filename.

## Prepare a packet

Run from the repository using a new private output directory:

```bash
python scripts/prepare_claims_input_review.py \
  --manual-zip "/path/to/Manual dataset Native Ads.zip" \
  --input-csv "/path/to/sampled_50_articles_paragraphs.csv" \
  --cleaned-csv "/path/to/native_ads_paragraphs_cleaned.csv" \
  --notebook "/path/to/clean_paragraph_data.ipynb" \
  --current-snapshot "/path/to/source_snapshot.json" \
  --source-audit "/path/to/upstream-ascii-v1" \
  --output .runtime/claims-input-review/new-run
```

The last two inputs are optional. Missing comparisons remain unavailable, rather
than becoming confirmed identities. Existing output directories are refused.
Keep the entire packet outside Git and public hosting.

## Method

1. Freeze input bytes and fingerprints. Require the notebook version already
   supported by the existing ASCII projection. Read the three cleaning settings
   as literals, preserving the original regex escaping.
2. Require an explicit metadata ID for each original TXT and preserve table row
   numbers. Do not infer IDs from spreadsheet row order, titles or current record
   UUIDs. Formulas are preserved as formulas and never become clickable URLs.
3. Reproduce the historical newline, encoding, paragraph and filtering steps in
   a separate view. Compare each retained sequence with the frozen cleaned CSV.
   The raw text, including material removed by that historical process, remains
   unchanged.
4. Locate every selected paragraph in its original TXT using the existing
   whitespace locator and fixed ASCII projection. Keep every valid occurrence,
   Unicode quote, character interval, method and lossy flag. Check existence of
   an ordered, non-overlapping sequence; do not choose a repeated occurrence as
   a human decision.
5. Compare supplied URLs literally with the frozen source snapshot. Show the
   earlier audit's text candidates separately, including their publisher, URL
   and version correspondence. Shared text does not replace the table's source
   assertions or merge different publishers.
6. Write pending review rows, unchanged input copies and a final hash manifest.
   Source identity, page completeness, semantic support and publication remain
   separate decisions.

Coordinates refer to decoded original TXT Python Unicode characters, using
`[start, end)`. They are not positions in the current database body, PDF, Markdown
page, UTF-8 bytes or JavaScript UTF-16 strings.

## Packet files

| File | Use |
| --- | --- |
| `index.md` | Readable directory for the selected article groups. |
| `articles/{id}.md` | Supplied metadata and notes, original text, current URL candidates, prior text candidates and all paragraph locations. |
| `original/{id}.txt` | Selected original TXT bytes, unchanged. |
| `source_archive.zip`, `source_workbook.xlsx` | Frozen source archive and valid metadata workbook. |
| `source_inventory.json` | All original TXT fingerprints, supplied metadata, filtering counts and sequence comparisons. |
| `article_lineage.json` | Selected inputs, exact original locations and explicitly pending source decisions. |
| `pending_source_review.csv` | Blank source decisions, reviewer and timestamp. CSV formula prefixes are escaped. This is not an importer approval file. |
| `prior_audit/` | Complete checked copies of the earlier audit, when supplied. |
| `preparation_summary.json`, `packet_manifest.json` | Scope, methods, counts, zero-call/write assertions and artifact fingerprints. |

## Local result, 6 October 2026

The supplied archive contains 268 TXT files and one valid metadata table. Its
4,650 nonempty source paragraphs reproduce the historical 3,905 retained
paragraphs across 239 nonempty groups; the other 29 groups reproduce empty
retained sequences. All 50 selected groups and 810 input paragraphs reproduce
the supplied retained sequences and can be located in ordered original text.

There are 811 original location candidates: one paragraph occurs twice. The
selected groups each have one literal URL candidate in the frozen 6 October
source snapshot. This advances input provenance recovery; it does not establish
original-page completeness, current-body coverage or verified publisher identity.

The unchanged earlier current-body audit still has 8 complete retained-group
candidates, 38 partial groups and 4 unlocated groups. Its 37 classification
candidates remain on hold. The new material does not override that audit,
approve labels or improve a measured classification score.

For example, original group 244 is supplied as a Washington Post page, with a
note that its content is the same as group 173, a WSJ page. Keep both sources and
their notes. Do not assign the publisher from whichever shared paragraph a
locator happens to find.

## Next decisions

The user has left the review role undecided. Continue to record it as pending.
After source review, use the existing corpus admission process to assess any
replacement text and its source/version. Then rerun the normal audit and follow
the [result publication rules](claims_result_import.md). The packet itself
cannot be supplied to `claims-import --apply`.

Use the [customer evaluation methodology](evaluation_methodology.md) for actual
answer and classification review. File lineage and exact quote locations are
engineering evidence; they are not semantic scores or customer acceptance.
