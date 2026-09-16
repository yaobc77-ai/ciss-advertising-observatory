# Data import contract

This document describes the implemented import layer. It does not certify the source articles or historical model labels.

## Inputs and priority

- `sources/FA25_SP26/final_dataset_cleaned.csv` is the native baseline. Its six public fields are `url`, `publisher`, `title`, `date`, `sponsor`, `keyword`. Its `article` is retained byte-for-byte after UTF-8 decoding; no whitespace or Unicode normalization is applied to body text.
- `sources/Native Advertising Data/native_ad_dataset.xlsx` supplies disclosure text and quality notes, joined only on one unique, exact URL after outer whitespace trimming. XLSX formatted empty rows are not data records. Cleaned binary disclosure is retained in raw data but never treated as presence/absence ground truth.
- `sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv` supplies **candidates only** for URLs absent from the baseline. If unavailable, the explicitly named copy in `sources/Native Advertising Data/` is the fallback; provenance identifies the file actually read. No same-name equivalence is assumed. Candidates require review; they are not returned in `ImportBatch.records`.
- `sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv` is optional static annotation input. Both original and calibrated labels require a unique matching URL **and exact full body**. Numeric `doc_id` is retained solely as legacy metadata. There is no model execution.
- The older `final_dataset_CLEANED.xlsx` and combined XLSX are not body authorities: earlier review found numeric/body and encoding conflicts.
- `analysis/pdf_archive/source_index.json` is an optional **candidate association index**. Its `source_urls` are matched exactly to baseline URLs; original title matching remains unverified. Entries are retained only in internal provenance with `match_state=candidate_unverified`. The index's PDF path and recorded hash are preserved; this import hashes the index, not every PDF again. It never replaces CSV text or fills a public `archive_url` from a local path.

## Record fields

| Field | Meaning / missingness |
|---|---|
| `record_id` | Deterministic UUIDv5 of dataset plus exact trimmed URL; stable across reruns and body changes. A changed URL needs an explicit future identity decision, not fuzzy auto-merge. |
| `dataset` | `native` or `social`; never inferred from text topic. |
| `url` | HTTP(S) URL from the input; preserved path, query, and case. Syntax validation does not establish live accessibility. |
| `publisher`, `title`, `sponsor`, `keyword` | Baseline text, with missing placeholders exposed as empty values. `keyword` is not automatically a sponsor identity. No mother/subsidiary or corporate-alias merge. |
| `published_at` | Parsed calendar date, or null for missing, unparseable, partial, or explicitly conflicting dates. Native dates use `%d/%m/%Y`. Date-time inputs keep their source-local calendar date, not an invented UTC conversion. |
| `platform`, `account` | Social-export fields from explicit mapping; unavailable in native input. |
| `body` | Exact decoded article/post text, including faulty source text so offsets remain reproducible. |
| `disclosure` | URL-matched raw disclosure text; blank/`None` does not prove no disclosure on a webpage. Internal field, not a native Dashboard column. |
| `archive_url` | Explicit source field only; never fabricated by title/PDF matching. |
| `countable` | Included in the record-level Dashboard denominator. Explicit image extensions or final URL segments ending in image dimensions are retained but excluded. Topic guesses do not exclude baseline records. |
| `retrievable` | Body passes implemented technical gates and is not an explicit image resource. This is an operational eligibility flag, not proof of semantic completeness. |
| `retrieval_end` | Optional exclusive character boundary of the allowed retrieval prefix. A consumer must chunk `body[:retrieval_end]` when present; offsets still refer to the preserved complete `body`. |
| `raw` | Original CSV values, matched metadata, body hash, date precision/source, and duplicate group when present. |
| `provenance` | Source path, SHA-256 / source asset ID, logical row including header, optional worksheet and role. CSV logical row is not its physical text line. Source hashes do not prove article identity. |
| `issues` | Concrete `code`, `severity`, `detail`, source and row. Field failures restrict only dependent functions. |
| `annotations` | `claims-original` / `claims-calibrated`, positive `labels`, all boolean `values`, exact-body basis/hash and original source row/hash. Historical automatic labels remain unverified. |

The service/database owns persisted record versions and derived-index replacement. The importer supplies deterministic content and provenance. On a body change, consumers must rebuild chunks and not retain annotations attached to an older body hash.

## Checks and human review

Pandera validates actual input frames, required columns, text types, URL syntax, and social platform presence. Invalid individual rows are isolated into `ImportBatch.rejected` with source row references; structural column failures isolate that input. Duplicate baseline/post URLs are all isolated rather than selecting one arbitrarily.

Native bodies containing only blanks, missing placeholders, `video`, or numbers are not indexed. Known mojibake characters, fewer than 40 words, short question-only bodies, and short/footer-dominated extracts need review before indexing. The 40-word gate is an explicit conservative heuristic, **not a learned quality score**. Full articles containing an ordinary disclosure/footer remain eligible. Complete social posts can naturally be short or questions, so these two article heuristics are informational for social imports; other body checks still apply.

The explicit markers `For more on the subject:` and `Read More Stories` set `retrieval_end` to the first marker. Only the preceding prefix is checked and indexed. Some markers occur **inside an article**, so the omitted suffix may contain valid later body text as well as navigation; it is retained unchanged for review. `body_related_navigation` records the excluded character interval. A marker at the start supplies no valid prefix and fails body eligibility. This deliberately avoids inventing where an interleaved link ends.

Bodies of 2800–3000 characters ending in `...` receive informational `body_truncated_suspected`: observed available passages remain eligible, but they cannot support full-article negative or completeness claims. The ellipsis pattern is a suspicion, not proof of the cause of truncation.

Exact duplicate substantive bodies are flagged without merging distinct URLs or changing their record counts. Placeholder `video` values do not create misleading duplicate-document groups. This implementation does not detect all near-duplicates, mixed articles, truncation, or navigation-heavy pages; targeted human review and downstream evaluation remain necessary.

Archive review is independent of CSV body eligibility. Index `low_text`/extraction failures and the exact known asset hashes of PDF-006 (clipped infographic), PDF-020 (repeated headers), and PDF-085 (another article from page 4) produce `archive_review`. These existing observations are documented in `PDF_SOURCE_INDEX.zh-CN.md` and `PDF_ARCHIVE_GUIDE.zh-CN.md`. A good CSV body is not excluded because its candidate PDF is incomplete, and an archive candidate is never promoted by title similarity.

Notes explicitly reporting a URL/date mismatch or an alternative publication date from an archived capture cause the public date to remain null; original dates and notes remain available internally. Other vaguely worded notes do not automatically invalidate dates. Pre-2000 dates are review outliers for this digital-ad corpus, not automatically corrected dates. Year/month-only values remain partial; no day is invented.

No import checks link reachability or contacts external data providers. It does not collect social data, execute CLAIMS, infer sponsors from account names, or publish records externally.

## Social mapping

`config/social_mapping.example.json` is a placeholder for a future real export. `columns` maps supported target fields to exact input column names; `constants` provides explicitly chosen strings such as a known single platform. A field cannot be both mapped and constant. `url` and `body` must be mapped; `platform` must be mapped or constant. Missing configured columns stop that input rather than guessing alternatives.

Optional targets: `account`, `publisher`, `title`, `published_at`, `sponsor`, `keyword`, `archive_url`, `disclosure`. `date_format` is an explicit Python `strptime` format; omission accepts ISO dates/date-times only. Invalid dates or archive links retain raw input and restrict the affected field; invalid post URLs or missing platforms isolate the row. A missing sponsor is unknown, not an inferred lack of commercial relationship.

No real social export is bundled or automatically loaded. Importing an example mapping alone creates no social records.

## Chunk contract

`chunk_body(body, max_tokens=600, overlap_tokens=100)` uses `cl100k_base` token counts. Each output has `text`, `start`, `end`, `paragraph_ids`, and `token_count`. Offsets are half-open Python Unicode character indices: `body[start:end] == text` must always hold. Paragraph IDs are local to one body/version (`p1`, `p2`, …). Blank-line boundaries are preferred; long paragraphs split at safe Unicode character boundaries. Stored text is never normalized.

Overlap is bounded by the requested token count and shortened for small paragraphs to guarantee forward progress. Different calls cannot share article state. Literal tokenizer special-token spellings are treated as text. Invalid token/overlap settings fail explicitly.

## Verified local import snapshot — 2026-09-16

This snapshot is an operational import result, not a measurement of source accuracy or model performance. It was produced by `load_native` and `chunk_body` over the existing local files, with no collection or model execution.

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

For example, baseline logical row 80, `Using mollusks to monitor industrial sites`, contains its only `biogas` occurrence in the related-story link starting at character 2050. Its indexable prefix is `[0, 2050)`, with original 2998-character text retained. Row 131, `Total: Using biomimicry for cleaner water`, discusses biogas in its own body and keeps its full 7696-character text eligible. Twenty prefix boundaries cover 19 records containing the `For more on the subject:` template and one containing `Read More Stories`; the remaining suffix is not assumed to be wholly navigation.

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

Verification: 23 import/quality/chunk tests passed; Ruff passed for the owned modules/tests. Static labels continue to describe their original full-body input, not the possibly shorter retrieval prefix. Automatic flags do not replace full article-boundary or source-identity review.
