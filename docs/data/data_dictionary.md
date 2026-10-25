# Data dictionary and source-to-component mapping

Checked against the local implementation on 6 October 2026. This is a source and
interface contract, not a new deployment or client approval. The current native
selection has 275 active records, 263 countable, 232 retrievable and 622 active
passages. The active profile is `sentence600-social-observations-v1`; earlier
versions and profiles are retained. The local social collection contains 36,182
unique company posts, all retrievable with zero paused; all 37,082 supplied source
observations are preserved and independently indexed in 37,086 passages.
The two collections contain 37,708 active passages in total.
The user-selected unit is platform plus canonical original-post URL. Paid-ad
identity and client approval remain unverified. See [current handoff](../current_handoff.md)
and [full company-post retrieval](all_social_posts_retrieval.zh-CN.md). These local changes are not deployed.

Requirements covered: PD3-P026/P068/P112/P120/P178 and MT-P041, indexed in
[the current requirements baseline](../../客户需求/06_目标基准/PD3_要求与版本差异.md).
Native rules below retain the fixed 0.2.3 source contract. Dated snapshots and
recovery receipts describe their own versions, not all later changes.

This document describes the implemented import layer. It does not certify the source articles or historical model labels.

The local [social historical-label view](social_historical_annotations.md)
projects the current version's original 13 booleans as source True, source False
or Unknown. Public record details and `get_record_sources` share this projection;
raw annotation fields remain private. The local social distribution and filter
use 39 namespaced source-state IDs over 13 original keys. Public lists and CSV
expose `social_historical_states`, `social_historical_scheme` and
`social_historical_status`; no source explanations are added to list rows.
Multiple state IDs use OR. These labels are not native CLAIMS2 or
verified greenwashing results. The supplied company posts are locally imported;
independent semantic review, client counting approval and deployment remain pending.

## Shared storage and public views

The [RecordInput contract](../../src/observatory/models.py) is shared by the native
and social adapters. Database reads follow the current record pointer and the
trusted selection. `countable` and `retrievable` are separate decisions; a
countable record may have no searchable body. A syntactically valid source URL
does not establish accessibility, sponsorship or an article's factual truth.

| Stored or derived value | Where it lives | Public use and limits |
| --- | --- | --- |
| Stable record identity, collection and current pointer | `records.record_id`, `dataset`, `active`, `current_version` | Collection selection and exact record navigation; inactive records are excluded from current reads |
| Full import payload and immutable text | `record_versions.payload`, `body`, `body_hash`, `version_id` | Public metadata is explicitly projected; raw import fields, private paths and disclosure fields are not Dashboard columns |
| Historical annotations | `annotations.version_id`, `ordinal`, `payload` | Native historical-label display/filter uses the explicitly selected scheme; supplied social labels retain their own scheme and are not silently mapped |
| Source dates and optional supplements | Payload `published_at`; separate `date_inferences` | Public source date remains unchanged; effective date, date basis and inferred tier are labeled separately |
| Exact retrieval interval and profile membership | `chunks`, `chunk_profile_membership`, `retrieval_state` | Search and citations retain source version and half-open character positions; a page of passages is not full-corpus coverage |
| Saved social observation identity | Nullable `chunks.source_observation_id` | Original observation ID such as `junkipedia:<id>`; supplied with both source hashes for observation passages; null for native passages |
| Saved social observation version | Nullable `chunks.source_version_id` | SHA-256 of the complete canonical JSON source record; changes to saved source fields create a different observation version; null for native passages |
| Saved social observation body hash | Nullable `chunks.source_body_hash` | SHA-256 of the literal UTF-8 observation body; passage offsets refer to that body, which may differ from the post's display body; null for native passages |
| Cached vectors | `embeddings` keyed by text hash and model | Retrieval uses stored vectors; the current input is chunk text, without a metadata prefix |
| Published classifications | Separate `claims2_*` tables | Read-only matches retain taxonomy, evidence, review and withdrawal state; no match is not a negative classification |
| Imports, usage and answers | `imports`, `usage_ledger`, `generation_outputs`, `answer_runs` | Maintenance and answer audit; private logs and complete payloads are not exported as ordinary source fields |
| Company-post policy and source observations | Internal `raw.social_admission` and preserved `source_variants` | Public lists expose `collection_scope`, `count_unit` and `paid_ad_status=not_verified`; individual source variants stay in bounded record detail, not ordinary CSV/list rows |
| Social reply mark | Internal `raw.source_row.post.is_reply` (source value `true` or `Unknown`) | Public `reply_status` is `reply` when the source marks `true`, otherwise `not_marked`; `not_marked` includes unknown marks and is not a verified list of original posts. The `replies` filter (social only) selects either state; selecting both is no restriction. Replies and customer-service posts remain inside the company-post count |
| Current social source-retrieval policy | Internal `raw.social_source_retrieval` on the 32 updated versions | Explicit `social-source-observations-v1` policy enables preserved observation text and retains the earlier admission status, quality issues and source conflicts |
| Text, image and video evidence | A fixed, hash-bound operator bundle and local assets; current record/version binding | Standard MCP `get_media_evidence` returns typed sources and locations. OCR, descriptions and transcripts are derived evidence, not original-body quotations; production bundle is not enabled |

The actual SQL projections are in [db.py](../../src/observatory/db.py).
`versioned_record()` reads one current native or social source within all
active filters. MCP source reads and passage checks are described in
[the tool contract](../architecture/mcp_research_tools.md). The current company-post import is a
separately reviewed user implementation decision, not proof of paid sponsorship
or independent dual-collection acceptance. The three observation fields are
supplied together or all absent in storage and public evidence models. Native
evidence keeps them as `None`; social observation evidence also carries source
quality codes, conflicts and observation count. No raw source object or private
file path is exposed through these fields. See [migration 5](../../src/observatory/migrations/0005_social_observation_chunks.sql)
and [the evidence model](../../src/observatory/models.py).

## Source → record → public component

Social rows below distinguish the original observation adapter from the later
unique-post admission. Real company posts are now displayed locally. Shared
metadata is projected from `record_versions.payload`; source
positions and full original fields remain private provenance.

| Source and exact field | Canonical field / rule | Database or derived view | Component and boundary |
| --- | --- | --- | --- |
| Native baseline `url`; mapped social CSV URL | `url`; deterministic dataset-and-URL identity | Current record and public URL | Record title/detail/source link; original spelling and query string retained |
| Native `publisher`, `sponsor` | Source values; display aliases do not merge identities | Public publisher/sponsor projection and grouped SQL | Filters, matrix, company/outlet graph, distributions and CSV; source co-listing is not an independently verified contract |
| Native `title` | `title` | Public title | Record table, evidence card and source detail |
| Native `date` | `published_at`; source-format and conflict rules below | Source date plus optional labeled effective date | Date filters, annual counts and Unknown group; no collection date substitution |
| Native `keyword` | Literal collection search term | Public keyword | Collection-term filter and records/export column; not a sponsor or discovered topic |
| Native `article`; adopted fixed recovery text | Exact `body`, allowed intervals, operational retrieval flag | Immutable body and chunks | Stored-text view, search and citation cards; extraction completeness remains a separate review |
| URL-matched native XLSX disclosure text | Internal `disclosure` | Private payload | Not a Dashboard column; the disclosure question relies on available source evidence, not an invented metadata value |
| Native historical prediction CSV | Exact-URL and exact-body annotation match | `annotations` | Historical-label distribution and native source view; not a verified greenwashing finding |
| Supplied Twitter `id` | Original observation `record_id = junkipedia:<id>` | Preserved private source observation | Retained in the unique post's source variants; observation identity is not the selected unique-post count unit |
| Reviewed platform plus canonical original URL | Deterministic `social-post:<sha256>` identity under `collected-company-posts-unique-url-v1` | Current unique-post record and version | Count, filter, detail, search and CSV use the same post ID. Duplicate observations remain preserved; conflicting fields stay unknown and each saved body variant is indexed independently |
| Twitter `post.junkipedia_uid` and `urls.post_url` | One matching original status URL | Public URL | Original post reference; ambiguous matching is rejected |
| Twitter `post_text` | Exact `body`; do not append other media/reference text | Immutable body and permitted search chunks | Post detail, search and citations; images, audio and referenced posts remain outside this text scope. Conflicting text, failed body quality or sentence-source validation is not retrieved |
| Twitter `date_time.published_at` | Timezone-qualified timestamp converted to UTC calendar date | Payload source date; original timestamp in raw | Date filters and labeled counts; invalid values remain missing |
| Twitter `parent_entity` | `sponsor` as company affiliation; explicit `sponsor_basis` | Payload company plus bounded known affiliation basis | Company filter/detail; never presented as proof of paid sponsorship |
| Twitter `channel.name`, `platform` | `account`, `platform`; publisher stays blank | Public account/platform; complete filtered SQL account groups | Local social account/platform filters, account bar→Records, Query and CSV. Groups are source names, not unique channel identities; no inferred news outlet |
| Twitter `junkipedia_link` | Valid supplied `archive_url`, otherwise empty with issue | Public archive reference | Recorded archive link; page content and availability are unverified |
| Twitter thirteen booleans and explanations | `claims-social-export-v1`, `historical_automatic_unverified` | Version-bound annotations; exact source fields retained | Separate historical scheme; not the native label filter, not CLAIMS2, and not published as reviewed findings |
| Explicitly reviewed CLAIMS2 result batch | Record/body/taxonomy-bound assignments | `claims2_*` tables | CLAIMS views, matching results and graph evidence after publication; candidate results remain on hold |

See [social_archive.py](../../src/observatory/social_archive.py) for the supplied JSON
adapter, [social_admission.py](../../src/observatory/social_admission.py) for reviewed
unique-post grouping, [ingest.py](../../src/observatory/ingest.py) for the native and mapped CSV
adapters, and [app.py](../../src/observatory/app.py) for filters, charts and records.
Record detail and source materials use [records.py](../../src/observatory/records.py)
and [record_view.py](../../src/observatory/record_view.py). Source-link visibility is
controlled by `OBS_SHOW_SOURCE_LINKS`; raw import paths are not public links.

## Native inputs and priority

- `sources/FA25_SP26/final_dataset_cleaned.csv` is the native baseline. Its six public fields are `url`, `publisher`, `title`, `date`, `sponsor`, `keyword`. Its decoded `article` cell is retained exactly in raw data; no whitespace or Unicode normalization is applied to body text. A validated recovery manifest can select a separately preserved text source for a new record version.
- `sources/Native Advertising Data/native_ad_dataset.xlsx` supplies disclosure text and quality notes, joined only on one unique, exact URL after outer whitespace trimming. XLSX formatted empty rows are not data records. Cleaned binary disclosure is retained in raw data but never treated as presence/absence ground truth.
- `sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv` supplies candidates for URLs absent from the baseline. Only an explicit, validated `include` decision in [native_admissions.json](../../config/native_admissions.json) adds a candidate to `ImportBatch.records`; the candidate audit entry is also retained. Current decisions admit 7, exclude 4, and leave 1 pending. If the primary CSV is unavailable, the loader can discover the explicitly named copy in `sources/Native Advertising Data/`, but the current manifest pins the primary path and hash: a fallback cannot silently satisfy it. No same-name equivalence is assumed.
- `sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv` is optional static annotation input. Both original and calibrated labels require a unique matching URL **and exact full body**. Numeric `doc_id` is retained solely as legacy metadata. There is no model execution.
- The older `final_dataset_CLEANED.xlsx` and combined XLSX are not body authorities: earlier review found numeric/body and encoding conflicts.
- `analysis/pdf_archive/source_index.json` is an optional **candidate association index**. Its `source_urls` are matched exactly to imported record URLs, including admitted additions; original title matching remains unverified. Entries are retained only in internal provenance with `match_state=candidate_unverified`. The index's PDF path and recorded hash are preserved; this import hashes the index, not every PDF again. It never replaces CSV text or fills a public `archive_url` from a local path.
- [PDF-265 extraction](../../sources/recovered_native/PDF-265.pypdf-6.10.0.txt) is the sole adopted recovery source in 0.2.3. Its source PDF, extraction bytes, page map and retained ranges are bound by [native_body_recoveries.json](../../config/native_body_recoveries.json). It does not upgrade the old candidate index or certify the current online article.

## Record fields

| Field | Meaning / missingness |
|---|---|
| `record_id` | Native and mapped social CSV use deterministic UUIDv5 of dataset plus exact trimmed URL. Original Twitter observations use `junkipedia:<source id>`; user-reviewed unique posts use `social-post:<sha256>` of platform and canonical original URL. Canonical JSONL preserves its validated identity. Body changes retain identity; no fuzzy company or article merging is performed. |
| `dataset` | `native` or `social`; never inferred from text topic. |
| `url` | HTTP(S) URL from the input; preserved path, query, and case. Syntax validation does not establish live accessibility. |
| `publisher`, `title`, `sponsor`, `keyword` | Source text, with missing placeholders exposed as empty values. Newly admitted native records apply `casefold()` only to normalized sponsor values and map the exact publisher abbreviation `WSJ` to `The Wall Street Journal`. Original spelling stays in `raw.supplement`; title and keyword case are preserved. Keywords remain literal collection terms, not inferred sponsor identities or globally merged aliases. These rules do not merge parent/subsidiary names or corporate aliases. |
| `published_at` | Parsed calendar date, or null for missing, unparseable, partial, or explicitly conflicting dates. Native baseline uses `%d/%m/%Y`; admitted combined-source dates use ISO parsing. Native/mapped CSV date-time parsing keeps the source-local date; supplied Twitter deliberately converts timezone-qualified publication timestamps to UTC dates. Collection dates and `year` do not replace publication dates. `date_policy=unknown` retains raw values but sets the normalized date to null. |
| `platform`, `account` | Social-export fields from explicit mapping; unavailable in native input. |
| `body` | Exact decoded text selected for this version, including excluded material so offsets remain reproducible. Normally the article/post cell; for an adopted recovery, the full immutable extraction. Original CSV text stays in raw data and the old version. |
| `disclosure` | URL-matched raw disclosure text; blank/`None` does not prove no disclosure on a webpage. Internal field, not a native Dashboard column. |
| `archive_url` | Explicit source field only; never fabricated by title/PDF matching. |
| `countable` | Included in the collection-specific Dashboard denominator: native source records or unique company posts. All 36,182 prepared v2 posts are locally countable; this is not paid-ad verification. Native explicit image extensions or final URL segments ending in image dimensions remain stored but excluded. |
| `retrievable` | Record is countable and its current text policy permits body retrieval or validated social source-observation retrieval. Earlier admission issues remain preserved when an explicit source policy enables a new version. `metadata_only` remains ineligible even after a body-range repair. This is an operational flag, not proof of semantic completeness. |
| `retrieval_ranges` | Optional explicit list of nonempty, ordered, non-overlapping `[start, end)` intervals in this version's body. Integer offsets must be in bounds. These intervals take priority over `retrieval_end`; an empty list is invalid. |
| `retrieval_end` | Legacy optional exclusive boundary of the allowed prefix, used only when `retrieval_ranges` is absent. Without either field, the full body is the selected range. Applied range reviews set this field to null and retain the previous boundary in the review audit. |
| `raw` | Original CSV values, matched metadata, body hash, date precision/source, duplicate group, and admission/body-review decisions when present. A recovery preserves `previous_body`, `previous_body_review` and `previous_body_annotations` internally; old labels are not labels for the new text. |
| `provenance` | Source path, SHA-256 / source asset ID, logical row including header, optional worksheet and role. CSV logical row is not its physical text line. Source hashes do not prove article identity. |
| `issues` | Concrete `code`, `severity`, `detail`, source and row. Field failures restrict only dependent functions. |
| `annotations` | Native `claims-original` / `claims-calibrated` and separate social `claims-social-export-v1` retain source labels, values and body/source basis. Historical automatic labels remain unverified. Changed-body recoveries do not transfer old labels to new text; prior versions retain their basis. Published CLAIMS2 results are separate tables, not replacements for these annotations. |

The service/database owns persisted record versions and derived-index replacement. The importer supplies deterministic content and provenance. On a body change, consumers must rebuild chunks and not retain annotations attached to an older body hash.

## Versioned admission, range and recovery manifests

All three configuration files record **AI engineering decisions**, not human approval or semantic acceptance. Each pins a relative source path and the SHA-256 of that file's actual bytes. Each decision binds an exact URL, logical CSV row including the header, and original article UTF-8 hash (`body_sha256`, or `previous_body_sha256` for recoveries). Range and recovery reviews also bind the stable record ID. The loaders validate all decisions before applying that manifest; stale/missing sources, changed rows/bodies/identities, duplicates, or invalid ranges stop the load. All three manifest hashes become import provenance.

| Manifest | Pinned source | Current decisions |
|---|---|---|
| [native_admissions.json](../../config/native_admissions.json), `native-additions-20260916-v1` | Combined CSV, SHA-256 `a677a6de6a8c10a4f872456263af72f0f99be4c3c561bf8b7449bce9b892dd57` | 7 include: 5 `text`, 2 `metadata_only`; 4 exclude; 1 pending. |
| [native_body_ranges.json](../../config/native_body_ranges.json), `native-body-ranges-20260916-v1` | Baseline CSV, SHA-256 `689f330321e42ea608070b2590fa24ee6c2bfb06dbc671941b1f0a927f4ceffa` | 20 reviewed navigation boundaries, with explicit retained intervals. |
| [native_body_recoveries.json](../../config/native_body_recoveries.json), `pdf265-text-continuation-20260916-v1` | Same baseline CSV, plus independently pinned PDF and extracted-text hashes | 1 partial recovery; 6 retained intervals within a 6-page, 7,098-character extraction. |

`import-native` requires **all three** configuration files before publishing a full native snapshot. Missing files cannot silently deactivate the 7 admitted records or revert recovered text to the old body. The library's optional flags remain available for baseline-only read/fixture workflows; use the CLI's required-manifest path for snapshot publication.

Recovery is applied after the CSV range review. The manifest validates the source PDF hash, immutable extraction hash, page map and `retained_ranges`; offsets refer to that extraction, not the old CSV. Page numbers start at 1; page intervals continuously cover the extraction, including each page's terminating `U+000C`. PDF-265 has 4,767 retained characters across six independent ranges. Its identity is locally corroborated by the acquisition manifest and distinctive content; online canonical identity remains unconfirmed. `body_partial_recovery` preserves layout and completeness limitations. Cross-page half-sentences and untranscribed infographic numbers are excluded. See the [recovery report](../../reports/data_audits/pdf265_body_recovery.md) and [identity evidence](../../reports/data_audits/pdf265_identity_review.md).

The extraction must be supplied with private source materials or reproduced from the pinned PDF using [extract_pdf_text.py](../../scripts/extract_pdf_text.py) and optional `pypdf==6.10.0`. The script preserves page text and appends `U+000C` per page; it does not OCR or normalize. Normal import/runtime reads the text file and does not require pypdf. Reproduction and publication steps are in [operations](../operations/operations.md).

Admission scope continues to include the existing CERAWeek industry paid-content category. `add-04` is included on that basis with sponsor unknown; neither the article title incorrectly stored in the sponsor field nor IHS Markit authorship establishes a payer. `add-07` and `add-11` retain conflicting date values internally and expose an unknown date. Other policies use the source; that does not certify every source field. Missing raw disclosure stays unknown even when local review references support paid-content identity. The 2 metadata-only additions are countable but never sent to retrieval; excluded/pending candidates are not admitted records. Reasons and evidence limits remain in the [12-URL review](../../reports/data_audits/additional_url_review.md).

## Checks and human review

Pandera validates actual input frames, required columns, text types, URL syntax, and social platform presence. Invalid individual rows are isolated into `ImportBatch.rejected` with source row references; structural column failures isolate that input. The native and mapped-CSV adapters isolate duplicate URLs. The supplied Twitter adapter retains duplicate observations, and the separate reviewed admission workflow groups them without dropping their source variants or choosing conflicting values arbitrarily.

Native bodies containing only blanks, missing placeholders, `video`, or numbers are not indexed. Known mojibake characters, fewer than 40 words, short question-only bodies, and short/footer-dominated extracts need review before indexing. The 40-word gate is an explicit conservative heuristic, **not a learned quality score**. Full articles containing an ordinary disclosure/footer remain eligible. Complete social posts can naturally be short or questions, so these two article heuristics are informational for social imports; other body checks still apply.

The subsequent explicit social source-retrieval policy covers the 32 audited
posts through their validated saved observations, retaining the earlier issues.
It permits the observed social `body_footer_only` cases without treating that
article heuristic as proof that the complete saved post has no useful text.
It does not automatically enable missing, placeholder, numeric-only or garbled
bodies, or change native body gates.

Without a validated range review, the explicit markers `For more on the subject:` and `Read More Stories` set `retrieval_end` to the first marker; only that prefix is checked and indexed. The 20 known boundaries have now received AI source-text review and engineering adoption through the body manifest: the importer excludes the specifically reviewed navigation intervals and retains later article text. It does not rewrite the source or infer missing material. Selected text is joined only for body-quality checks; indexing and quotations keep intervals separate. The original suspected-truncation issue is preserved, and an explicit metadata-only admission cannot be overridden by this repair. See the [boundary review](../../reports/data_audits/prefix_boundary_review.md).

Bodies of 2800–3000 characters ending in `...` receive informational `body_truncated_suspected`: observed available passages remain eligible, but they cannot support full-article negative or completeness claims. The ellipsis pattern is a suspicion, not proof of the cause of truncation.

The 94 suspected-truncation flags describe the original CSV limitations and remain preserved. In 0.2.3, one of those records gains a limited PDF continuation; this does not make any of the 94 a confirmed complete article. Missing lists, obscured page-edge text and untranscribed figures cannot be inferred from the available passages.

Exact duplicate substantive bodies are flagged without merging distinct URLs or changing their record counts. Placeholder `video` values do not create misleading duplicate-document groups. This implementation does not detect all near-duplicates, mixed articles, truncation, or navigation-heavy pages; targeted human review and downstream evaluation remain necessary.

Archive review is independent of CSV body eligibility. Index `low_text`/extraction failures and the exact known asset hashes of PDF-006 (clipped infographic), PDF-020 (repeated headers), and PDF-085 (another article from page 4) produce `archive_review`. These existing observations are documented in `docs/history/fa26_0916/PDF_SOURCE_INDEX.zh-CN.md` and `docs/history/fa26_0916/PDF_ARCHIVE_GUIDE.zh-CN.md`. A good CSV body is not excluded because its candidate PDF is incomplete, and an archive candidate is never promoted by title similarity.

Notes explicitly reporting a URL/date mismatch or an alternative publication date from an archived capture cause the public date to remain null; original dates and notes remain available internally. Other vaguely worded notes do not automatically invalidate dates. Pre-2000 dates are review outliers for this digital-ad corpus, not automatically corrected dates. Year/month-only values remain partial; no day is invented.

No import checks link reachability or contacts external data providers. It does not collect social data, execute CLAIMS, infer sponsors from account names, or publish records externally.

## Supplied social archive and mapped CSV inputs

The supplied nested ZIP/JSON uses `prepare-social`, described in
[social_archive_input.md](social_archive_input.md), and then the existing
canonical `import-records --dataset social` path after a separate admission
decision. The initial observation preparation keeps `countable=False` and
`retrievable=False`; that output remains preserved. The later user-reviewed
[admission](social_posts_admission.md) produces unique company posts with an
explicit counting unit and preserved conflicts. Its earlier local frozen-v2
import had 36,182 countable, 36,150 retrievable and 32 paused; that package and
its decisions remain unchanged. The subsequent source-retrieval preparation
creates 32 new versions and enables all 36,182 posts under the observation
profile without altering original source text or adjudicating its differences.
No paid-ad status or client approval is inferred by these steps.

For a separately reviewed CSV export, `config/social_mapping.example.json` is
an example mapping, not the supplied nested JSON adapter. `columns` maps
supported target fields to exact input column names; `constants` supplies
explicit strings such as a single platform. A field cannot be both mapped and
constant. `url` and `body` must be mapped; `platform` must be mapped or constant.
Missing configured columns stop that input rather than guessing alternatives.

Optional targets: `account`, `publisher`, `title`, `published_at`, `sponsor`, `keyword`, `archive_url`, `disclosure`. `date_format` is an explicit Python `strptime` format; omission accepts ISO dates/date-times only. Invalid dates or archive links retain raw input and restrict the affected field; invalid post URLs or missing platforms isolate the row. A missing sponsor is unknown, not an inferred lack of commercial relationship.

The real Twitter export has been received privately and prepared. It is not
bundled with public code or automatically loaded. Importing an example mapping
alone creates no social records. Facebook/Instagram sources remain pending.

## Chunk contract

`chunk_retrieval_body()` resolves explicit `retrieval_ranges`, falling back to
the legacy prefix or full body, and processes each retained interval separately.
Versioned profile definitions in [indexing.py](../../src/observatory/indexing.py)
currently use 600-token budgets and 100-token overlap with `cl100k_base`.
`sentence600-v1` uses sentence boundaries where feasible; an over-budget sentence
needs a safe character split. `legacy600-v1` retains its earlier behavior. The
active `sentence600-social-observations-v1` profile keeps the native sentence
contract and processes each social observation separately, using verified
character coverage when strict sentence segmentation omits source characters.
Each output has `text`, `start`, `end`, `paragraph_ids`, and `token_count`.
Offsets are half-open Python Unicode character indices in that body's version:
`body[start:end] == text` must hold. Paragraph IDs come from the whole body,
not a concatenation of retained intervals. No chunk or quotation bridges an
excluded gap. Social observation offsets refer to the body bound by the three
source-observation fields, rather than a different variant selected for display.
Stored text is unchanged. Full saved-text coverage does not prove complete
original-post extraction, vector coverage, media recovery or semantic accuracy.

Overlap is bounded by the requested token count and shortened for small paragraphs to guarantee forward progress. Different calls cannot share article state. Literal tokenizer special-token spellings are treated as text. Invalid token/overlap settings fail explicitly.

## Historical local snapshot — 0.2.3, 2026-09-16

The [publication validation](../../outputs/pdf265_publication_validation_20260916.json) records data version `5114ebc1cf9afe59cdaa715e3ea45166`: **275 stored records, 263 countable, 226 retrievable, and 558 current chunks**. This remains the 268-record baseline plus 7 admitted additions. Only record `d340f887-efa7-5746-aaf8-14aabba6b63f` receives a new version; the other 274 records are unchanged, and the repeat import reports 275 unchanged. Metadata and count eligibility are unchanged. PDF-265 grows from 2 to 6 chunks using the partial recovery above.

All **558 current chunk locators**, **86 historical evidence locators** and **15 development gold source spans** validate. Old bodies, citations and label bases remain accessible; the recovered record's old labels are internal only for the new version. The full 0.2.3 test suite passed **209 tests in 19.63 seconds**. These are engineering and source-location checks, not human semantic acceptance or a new paid-answer score.

## Historical snapshots — 0.2.0 through 0.2.2

The 0.2.2 snapshot was `d85a98002e4493f0376c260ad82253ee`, with 275 stored / 263 countable / 226 retrievable records and **554** chunks. The [source-spelling correction](../../outputs/native_import_v0_2_published_20260916.json) and [repeat](../../outputs/native_import_v0_2_published_repeat_20260916.json) remain historical evidence. Earlier schema, sponsor-case and publisher-alignment imports are not rerun or rewritten as 0.2.3 results. The [intermediate source validation](../../outputs/source_revision_validation_final_20260916.json) binds `612e20bbef3d0910ba94c0e4be84d10e`; its 79 historical locators and keyword groups describe that intermediate snapshot.

Paid outputs retain their original run and data versions. For example, [run `532453a7c43740ecbe5f4954d3522f41`](../../outputs/development_reviewed_paid_final_20260916.json) used `c5ad20ac2938e619e11fe1f8bfc26b97` and exposed three wrong-language answers. Later 0.2.2 paid diagnostics also predate the PDF recovery. None of those results establish paid or human semantic performance for data version `5114ebc1cf9afe59cdaa715e3ea45166`.

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
