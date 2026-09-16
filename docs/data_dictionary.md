# Data import contract — 0.2.3

This document describes the implemented import layer. It does not certify the source articles or historical model labels.

## Inputs and priority

- `sources/FA25_SP26/final_dataset_cleaned.csv` is the native baseline. Its six public fields are `url`, `publisher`, `title`, `date`, `sponsor`, `keyword`. Its decoded `article` cell is retained exactly in raw data; no whitespace or Unicode normalization is applied to body text. A validated recovery manifest can select a separately preserved text source for a new record version.
- `sources/Native Advertising Data/native_ad_dataset.xlsx` supplies disclosure text and quality notes, joined only on one unique, exact URL after outer whitespace trimming. XLSX formatted empty rows are not data records. Cleaned binary disclosure is retained in raw data but never treated as presence/absence ground truth.
- `sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv` supplies candidates for URLs absent from the baseline. Only an explicit, validated `include` decision in [native_admissions.json](../config/native_admissions.json) adds a candidate to `ImportBatch.records`; the candidate audit entry is also retained. Current decisions admit 7, exclude 4, and leave 1 pending. If the primary CSV is unavailable, the loader can discover the explicitly named copy in `sources/Native Advertising Data/`, but the current manifest pins the primary path and hash: a fallback cannot silently satisfy it. No same-name equivalence is assumed.
- `sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv` is optional static annotation input. Both original and calibrated labels require a unique matching URL **and exact full body**. Numeric `doc_id` is retained solely as legacy metadata. There is no model execution.
- The older `final_dataset_CLEANED.xlsx` and combined XLSX are not body authorities: earlier review found numeric/body and encoding conflicts.
- `analysis/pdf_archive/source_index.json` is an optional **candidate association index**. Its `source_urls` are matched exactly to imported record URLs, including admitted additions; original title matching remains unverified. Entries are retained only in internal provenance with `match_state=candidate_unverified`. The index's PDF path and recorded hash are preserved; this import hashes the index, not every PDF again. It never replaces CSV text or fills a public `archive_url` from a local path.
- [PDF-265 extraction](../sources/recovered_native/PDF-265.pypdf-6.10.0.txt) is the sole adopted recovery source in 0.2.3. Its source PDF, extraction bytes, page map and retained ranges are bound by [native_body_recoveries.json](../config/native_body_recoveries.json). It does not upgrade the old candidate index or certify the current online article.

## Record fields

| Field | Meaning / missingness |
|---|---|
| `record_id` | Deterministic UUIDv5 of dataset plus exact trimmed URL; stable across reruns and body changes. A changed URL needs an explicit future identity decision, not fuzzy auto-merge. |
| `dataset` | `native` or `social`; never inferred from text topic. |
| `url` | HTTP(S) URL from the input; preserved path, query, and case. Syntax validation does not establish live accessibility. |
| `publisher`, `title`, `sponsor`, `keyword` | Source text, with missing placeholders exposed as empty values. Newly admitted native records apply `casefold()` only to normalized sponsor values and map the exact publisher abbreviation `WSJ` to `The Wall Street Journal`. Original spelling stays in `raw.supplement`; title and keyword case are preserved. Keywords remain literal collection terms, not inferred sponsor identities or globally merged aliases. These rules do not merge parent/subsidiary names or corporate aliases. |
| `published_at` | Parsed calendar date, or null for missing, unparseable, partial, or explicitly conflicting dates. Baseline dates use `%d/%m/%Y`; admitted combined-source dates use ISO parsing. Date-time inputs keep their source-local calendar date, not an invented UTC conversion. An explicit `date_policy=unknown` retains raw values but sets the normalized date to null. |
| `platform`, `account` | Social-export fields from explicit mapping; unavailable in native input. |
| `body` | Exact decoded text selected for this version, including excluded material so offsets remain reproducible. Normally the article/post cell; for an adopted recovery, the full immutable extraction. Original CSV text stays in raw data and the old version. |
| `disclosure` | URL-matched raw disclosure text; blank/`None` does not prove no disclosure on a webpage. Internal field, not a native Dashboard column. |
| `archive_url` | Explicit source field only; never fabricated by title/PDF matching. |
| `countable` | Included in the record-level Dashboard denominator. Explicit image extensions or final URL segments ending in image dimensions are retained but excluded. Topic guesses do not exclude baseline records. |
| `retrievable` | Record is countable, its selected text passes implemented body gates, and any explicit admission permits text retrieval. `metadata_only` remains ineligible even after a body-range repair. This is an operational flag, not proof of semantic completeness. |
| `retrieval_ranges` | Optional explicit list of nonempty, ordered, non-overlapping `[start, end)` intervals in this version's body. Integer offsets must be in bounds. These intervals take priority over `retrieval_end`; an empty list is invalid. |
| `retrieval_end` | Legacy optional exclusive boundary of the allowed prefix, used only when `retrieval_ranges` is absent. Without either field, the full body is the selected range. Applied range reviews set this field to null and retain the previous boundary in the review audit. |
| `raw` | Original CSV values, matched metadata, body hash, date precision/source, duplicate group, and admission/body-review decisions when present. A recovery preserves `previous_body`, `previous_body_review` and `previous_body_annotations` internally; old labels are not labels for the new text. |
| `provenance` | Source path, SHA-256 / source asset ID, logical row including header, optional worksheet and role. CSV logical row is not its physical text line. Source hashes do not prove article identity. |
| `issues` | Concrete `code`, `severity`, `detail`, source and row. Field failures restrict only dependent functions. |
| `annotations` | `claims-original` / `claims-calibrated`, positive `labels`, all boolean `values`, exact-body basis/hash and original source row/hash. Historical automatic labels remain unverified. Changed-body recoveries clear current annotations; old versions and internal `raw.previous_body_annotations` retain their prior basis. |

The service/database owns persisted record versions and derived-index replacement. The importer supplies deterministic content and provenance. On a body change, consumers must rebuild chunks and not retain annotations attached to an older body hash.

## Versioned admission, range and recovery manifests

All three configuration files record **AI engineering decisions**, not human approval or semantic acceptance. Each pins a relative source path and the SHA-256 of that file's actual bytes. Each decision binds an exact URL, logical CSV row including the header, and original article UTF-8 hash (`body_sha256`, or `previous_body_sha256` for recoveries). Range and recovery reviews also bind the stable record ID. The loaders validate all decisions before applying that manifest; stale/missing sources, changed rows/bodies/identities, duplicates, or invalid ranges stop the load. All three manifest hashes become import provenance.

| Manifest | Pinned source | Current decisions |
|---|---|---|
| [native_admissions.json](../config/native_admissions.json), `native-additions-20260916-v1` | Combined CSV, SHA-256 `a677a6de6a8c10a4f872456263af72f0f99be4c3c561bf8b7449bce9b892dd57` | 7 include: 5 `text`, 2 `metadata_only`; 4 exclude; 1 pending. |
| [native_body_ranges.json](../config/native_body_ranges.json), `native-body-ranges-20260916-v1` | Baseline CSV, SHA-256 `689f330321e42ea608070b2590fa24ee6c2bfb06dbc671941b1f0a927f4ceffa` | 20 reviewed navigation boundaries, with explicit retained intervals. |
| [native_body_recoveries.json](../config/native_body_recoveries.json), `pdf265-text-continuation-20260916-v1` | Same baseline CSV, plus independently pinned PDF and extracted-text hashes | 1 partial recovery; 6 retained intervals within a 6-page, 7,098-character extraction. |

`import-native` requires **all three** configuration files before publishing a full native snapshot. Missing files cannot silently deactivate the 7 admitted records or revert recovered text to the old body. The library's optional flags remain available for baseline-only read/fixture workflows; use the CLI's required-manifest path for snapshot publication.

Recovery is applied after the CSV range review. The manifest validates the source PDF hash, immutable extraction hash, page map and `retained_ranges`; offsets refer to that extraction, not the old CSV. Page numbers start at 1; page intervals continuously cover the extraction, including each page's terminating `U+000C`. PDF-265 has 4,767 retained characters across six independent ranges. Its identity is locally corroborated by the acquisition manifest and distinctive content; online canonical identity remains unconfirmed. `body_partial_recovery` preserves layout and completeness limitations. Cross-page half-sentences and untranscribed infographic numbers are excluded. See the [recovery report](../reports/pdf265_body_recovery.md) and [identity evidence](../reports/pdf265_identity_review.md).

The extraction must be supplied with private source materials or reproduced from the pinned PDF using [extract_pdf_text.py](../scripts/extract_pdf_text.py) and optional `pypdf==6.10.0`. The script preserves page text and appends `U+000C` per page; it does not OCR or normalize. Normal import/runtime reads the text file and does not require pypdf. Reproduction and publication steps are in [operations](operations.md).

Admission scope continues to include the existing CERAWeek industry paid-content category. `add-04` is included on that basis with sponsor unknown; neither the article title incorrectly stored in the sponsor field nor IHS Markit authorship establishes a payer. `add-07` and `add-11` retain conflicting date values internally and expose an unknown date. Other policies use the source; that does not certify every source field. Missing raw disclosure stays unknown even when local review references support paid-content identity. The 2 metadata-only additions are countable but never sent to retrieval; excluded/pending candidates are not admitted records. Reasons and evidence limits remain in the [12-URL review](../reports/additional_url_review.md).

## Checks and human review

Pandera validates actual input frames, required columns, text types, URL syntax, and social platform presence. Invalid individual rows are isolated into `ImportBatch.rejected` with source row references; structural column failures isolate that input. Duplicate baseline/post URLs are all isolated rather than selecting one arbitrarily.

Native bodies containing only blanks, missing placeholders, `video`, or numbers are not indexed. Known mojibake characters, fewer than 40 words, short question-only bodies, and short/footer-dominated extracts need review before indexing. The 40-word gate is an explicit conservative heuristic, **not a learned quality score**. Full articles containing an ordinary disclosure/footer remain eligible. Complete social posts can naturally be short or questions, so these two article heuristics are informational for social imports; other body checks still apply.

Without a validated range review, the explicit markers `For more on the subject:` and `Read More Stories` set `retrieval_end` to the first marker; only that prefix is checked and indexed. The 20 known boundaries have now received AI source-text review and engineering adoption through the body manifest: the importer excludes the specifically reviewed navigation intervals and retains later article text. It does not rewrite the source or infer missing material. Selected text is joined only for body-quality checks; indexing and quotations keep intervals separate. The original suspected-truncation issue is preserved, and an explicit metadata-only admission cannot be overridden by this repair. See the [boundary review](../reports/prefix_boundary_review.md).

Bodies of 2800–3000 characters ending in `...` receive informational `body_truncated_suspected`: observed available passages remain eligible, but they cannot support full-article negative or completeness claims. The ellipsis pattern is a suspicion, not proof of the cause of truncation.

The 94 suspected-truncation flags describe the original CSV limitations and remain preserved. In 0.2.3, one of those records gains a limited PDF continuation; this does not make any of the 94 a confirmed complete article. Missing lists, obscured page-edge text and untranscribed figures cannot be inferred from the available passages.

Exact duplicate substantive bodies are flagged without merging distinct URLs or changing their record counts. Placeholder `video` values do not create misleading duplicate-document groups. This implementation does not detect all near-duplicates, mixed articles, truncation, or navigation-heavy pages; targeted human review and downstream evaluation remain necessary.

Archive review is independent of CSV body eligibility. Index `low_text`/extraction failures and the exact known asset hashes of PDF-006 (clipped infographic), PDF-020 (repeated headers), and PDF-085 (another article from page 4) produce `archive_review`. These existing observations are documented in `PDF_SOURCE_INDEX.zh-CN.md` and `PDF_ARCHIVE_GUIDE.zh-CN.md`. A good CSV body is not excluded because its candidate PDF is incomplete, and an archive candidate is never promoted by title similarity.

Notes explicitly reporting a URL/date mismatch or an alternative publication date from an archived capture cause the public date to remain null; original dates and notes remain available internally. Other vaguely worded notes do not automatically invalidate dates. Pre-2000 dates are review outliers for this digital-ad corpus, not automatically corrected dates. Year/month-only values remain partial; no day is invented.

No import checks link reachability or contacts external data providers. It does not collect social data, execute CLAIMS, infer sponsors from account names, or publish records externally.

## Social mapping

`config/social_mapping.example.json` is a placeholder for a future real export. `columns` maps supported target fields to exact input column names; `constants` provides explicitly chosen strings such as a known single platform. A field cannot be both mapped and constant. `url` and `body` must be mapped; `platform` must be mapped or constant. Missing configured columns stop that input rather than guessing alternatives.

Optional targets: `account`, `publisher`, `title`, `published_at`, `sponsor`, `keyword`, `archive_url`, `disclosure`. `date_format` is an explicit Python `strptime` format; omission accepts ISO dates/date-times only. Invalid dates or archive links retain raw input and restrict the affected field; invalid post URLs or missing platforms isolate the row. A missing sponsor is unknown, not an inferred lack of commercial relationship.

No real social export is bundled or automatically loaded. Importing an example mapping alone creates no social records.

## Chunk contract

`chunk_retrieval_body(body, max_tokens=600, overlap_tokens=100, ...)` first resolves explicit `retrieval_ranges`, falling back to the legacy prefix or full body. It calls `chunk_body` independently on each retained interval using `cl100k_base` token counts. Each output has `text`, `start`, `end`, `paragraph_ids`, and `token_count`. Offsets are translated back to half-open Python Unicode character indices in that version's body: `body[start:end] == text` must always hold. Paragraph IDs come from the whole stored body/version (`p1`, `p2`, …), not a renumbered concatenation; this does not imply a complete article. No chunk or quotation can bridge an excluded gap. Blank-line boundaries are preferred; long paragraphs split at safe Unicode character boundaries. Stored text is never normalized.

Overlap is bounded by the requested token count and shortened for small paragraphs to guarantee forward progress. Different calls cannot share article state. Literal tokenizer special-token spellings are treated as text. Invalid token/overlap settings fail explicitly.

## Current local snapshot — 0.2.3, 2026-09-16

The [publication validation](../outputs/pdf265_publication_validation_20260916.json) records data version `5114ebc1cf9afe59cdaa715e3ea45166`: **275 stored records, 263 countable, 226 retrievable, and 558 current chunks**. This remains the 268-record baseline plus 7 admitted additions. Only record `d340f887-efa7-5746-aaf8-14aabba6b63f` receives a new version; the other 274 records are unchanged, and the repeat import reports 275 unchanged. Metadata and count eligibility are unchanged. PDF-265 grows from 2 to 6 chunks using the partial recovery above.

All **558 current chunk locators**, **86 historical evidence locators** and **15 development gold source spans** validate. Old bodies, citations and label bases remain accessible; the recovered record's old labels are internal only for the new version. The full 0.2.3 test suite passed **209 tests in 19.63 seconds**. These are engineering and source-location checks, not human semantic acceptance or a new paid-answer score.

## Historical snapshots — 0.2.0 through 0.2.2

The 0.2.2 snapshot was `d85a98002e4493f0376c260ad82253ee`, with 275 stored / 263 countable / 226 retrievable records and **554** chunks. The [source-spelling correction](../outputs/native_import_v0_2_published_20260916.json) and [repeat](../outputs/native_import_v0_2_published_repeat_20260916.json) remain historical evidence. Earlier schema, sponsor-case and publisher-alignment imports are not rerun or rewritten as 0.2.3 results. The [intermediate source validation](../outputs/source_revision_validation_final_20260916.json) binds `612e20bbef3d0910ba94c0e4be84d10e`; its 79 historical locators and keyword groups describe that intermediate snapshot.

Paid outputs retain their original run and data versions. For example, [run `532453a7c43740ecbe5f4954d3522f41`](../outputs/development_reviewed_paid_final_20260916.json) used `c5ad20ac2938e619e11fe1f8bfc26b97` and exposed three wrong-language answers. Later 0.2.2 paid diagnostics also predate the PDF recovery. None of those results establish paid or human semantic performance for data version `5114ebc1cf9afe59cdaa715e3ea45166`.

## Historical local import snapshot — before 0.2.0, 2026-09-16

The following snapshot and its test count describe the earlier baseline/prefix implementation. They are preserved as historical evidence, not current totals. It was produced by `load_native` and prefix chunking over the local files, with no collection or model execution.

| Quantity | Result |
|---|---:|
| Baseline records retained | 268 |
| Countable native records | 256 |
| Records with an eligible retrieval body/prefix | 221 |
| Chunks (maximum 600 tokens; exact character slices checked) | 510 |
| Explicit date conflicts retained as unknown | 20 |
| Combined-source candidates outside the baseline | 12 |
| Rejected input rows | 0 |
| URL + exact full-body matched historical records | 268 |
| Historical annotations, original + calibrated | 536 |
| Records with explicit navigation and a retained eligible prefix | 20 |
| Informational suspected truncation flags | 94 |
| Records linked to unverified archive candidates | 260 |
| Archive candidate links / distinct recorded PDF hashes | 293 / 291 |
| Archive review links / affected records | 8 / 7 |

The 47 unavailable retrieval bodies comprise 26 literal `video` values and 21 short extracts (question/footer flags overlap the latter). All 12 resource exclusions are among those video placeholders. Four records belong to exact duplicate substantive-body groups; they remain distinct URLs. Raw disclosure text exists despite cleaned binary `0` on 181 records; one raw disclosure is a missing-value placeholder. The five actual import inputs' hashes were unchanged after verification.

For example, baseline logical row 80, `Using mollusks to monitor industrial sites`, contains its only `biogas` occurrence in the related-story link starting at character 2050. The historical indexable prefix was `[0, 2050)`, with the original 2998-character text retained. In 0.2.0 its explicit ranges are `[0, 2050)` and `[2113, 2998)`: the link is excluded while the later mollusk-method discussion is restored. Row 131, `Total: Using biomimicry for cleaner water`, discusses biogas in its own body and keeps its full 7696-character text eligible. The earlier 20 prefix boundaries covered 19 records containing `For more on the subject:` and one containing `Read More Stories`; later review did not treat each entire suffix as navigation.

The following 12 baseline records remain stored but are excluded from the record-count denominator because their final URL segments end in explicit image dimensions. Logical row numbers include the header in `sources/FA25_SP26/final_dataset_cleaned.csv`; no subject-matter inference was used.

| CSV row | Record ID | Final URL segment |
|---:|---|---|
| 134 | `7801ae24-0e4c-55e1-9835-bc1e610d3728` | `blockchain-400x400` |
| 135 | `04ddb0aa-667e-512c-8bea-d3664b21a763` | `blockchain-800x800` |
| 138 | `c51a91fe-1c17-5432-88e8-2f53695326f5` | `barra-960x540` |
| 139 | `c47f2a4b-44ff-5cac-8043-d58578f9f376` | `greene-belani-960x540` |
| 141 | `df0d4e13-c277-5e48-8cc7-0369a7ef47fe` | `barkindo-wsj-400x400` |
| 142 | `7d2464ef-b35b-5913-8b63-94e50b769cbd` | `barkindo-wsj-960x540` |
| 147 | `39fc1061-26b2-5077-9b0a-5e4530d7eb39` | `pruitt-wsj-400x400` |
| 156 | `8cd52109-a0ef-5e67-856a-7087675b13dc` | `connectedhomeagora-wsj-400x400` |
| 157 | `3312861b-bf59-5ce7-a77f-fb248927ee35` | `trudeau-wsj-1300x400` |
| 158 | `f81d1148-b0f7-59b8-8e0b-79960dc117d9` | `trudeau-wsj-400x400` |
| 163 | `ede1d6a4-7586-5a65-b144-4d25ed5cb97b` | `blockchain-960x540` |
| 164 | `01c4a736-c556-58d0-ad4f-56277e48b560` | `diwan-1200x630` |

Historical verification: 23 import/quality/chunk tests passed; Ruff passed for those owned modules/tests. Static labels continue to describe their original full-body input, not the current retained retrieval intervals. Automatic flags and AI engineering reviews do not replace human semantic or source-identity acceptance.
