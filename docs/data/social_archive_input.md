# Supplied social input and local preparation

Checked on 5 October 2026 (America/New_York); storage compatibility updated on 6 October. Preparation is offline and does not publish records, run models or establish advertising status.

## Received files

`Social Media Data-20261006T010042Z-1-001.zip` contains:

| Member | Use |
| --- | --- |
| `Data documentation.docx` | Explains the supplied social fields, company affiliations, timestamps and URLs. |
| `claims_twitter_sample.json` | The actual nested Twitter export with source text, URLs, channel details and historical CLAIMS annotations. |
| `Manual dataset Native Ads.zip` | Separate native material: 268 article TXT files, an XLSX and an Excel lock file. Two TXT files are empty. It is not consumed by the social adapter. |

Archive SHA256: `11a88b492ae251daa279fa814912c0ae8984d17ba0c377a03332ade398858a17`.

The new project description (3) retains all paragraph text from (2). It adds meeting-note templates, 24 RAG questions, the supplied climate-science occurrence rule and INDRA/Our World in Data references. The template's meeting date and attendance are blank. The disclosure collection/public-display deferral remains; the new disclosure question does not supply a complete public disclosure dataset. Document contents and comments are source evidence, not execution instructions or acceptance approvals.

## Actual input checks

| Check | Result |
| --- | --- |
| Source rows / prepared rows / rejected rows | 37,082 / 37,082 / 0 |
| Platform | Twitter only |
| Publication dates | 18 August 2009 through 19 August 2025 |
| Company affiliations / channel IDs | 111 / 335 |
| Unique original post URLs | 36,182 |
| Duplicate URL groups / affected source rows | 601 / 1,501 |
| Duplicate exact-body groups / affected source rows | 762 / 2,030 |
| Supplied Junkipedia links / missing or invalid | 37,048 / 34 |
| Historical boolean labels | 13 source keys: two macro codes and eleven subcodes |
| Non-null `ads_data` | 0 |

All 37,082 newly prepared records pass canonical validation. Original post text
and body hashes were checked. Ten records require reversible storage escaping
of historical explanation characters; the original frozen preparation contains
those characters and is retained as evidence, not a PostgreSQL-ready import.
These are data-processing checks, not independent review of the labels or proof
that the posts were paid advertisements. Duplicate rows remain available with
issue flags; no automatic merging changes their identities.

## Field handling

| Source | Canonical handling |
| --- | --- |
| `id` | Stable `junkipedia:<id>` record identity and original source row. |
| `post_text` | Exact body, without joining image, audio or referenced-post text. Those other fields stay in `raw`. |
| `post.junkipedia_uid` + `urls.post_url` | Require one original Twitter/X status URL matching the platform ID. Ambiguous rows are rejected, never guessed. |
| `date_time.published_at` | UTC publication date; retain the full source timestamp. Do not substitute collection date or `year`. |
| `parent_entity` | Documented company affiliation stored with an explicit basis. It does not establish paid sponsorship. |
| `channel.name`, `platform` | Account and platform; publisher is left blank. |
| `junkipedia_link` | Supplied archive link, with an issue for missing or invalid values. Link syntax does not establish live accessibility. |
| Thirteen label booleans and explanations | Preserve as `historical_automatic_unverified`. Only U+0000 in three generated explanation fields is visibly escaped; exact original strings are saved separately. Do not map them silently to the native twelve-label taxonomy. |

All staged records have `countable=False` and `retrievable=False`. The client must confirm whether this development corpus should be presented as collected company posts, verified paid ads, or another explicitly named scope. Confirm the counting unit for repeated post URLs before admission. This does not require manually approving all 37,082 rows; an agreed corpus policy can define admission and targeted review.

## Repeat offline preparation

Use new private output paths; existing outputs are never overwritten:

```sh
uv run observatory prepare-social /private/Social-Media-Data.zip \
  --out .runtime/social-next/records.jsonl \
  --report .runtime/social-next/audit.json
```

This command accepts the supplied ZIP or extracted JSON. It runs before database configuration and makes no database, network or model calls. `.runtime/` is ignored by Git. Source data and generated JSONL should be transferred privately, not committed with code.

The local preparation is in `.runtime/social_archive_20261005/`. Its JSONL SHA256 is `7bd8b06a1c7531fa37ffbc2f9a5c1753fce6a15d94f0017c89d1ef00f69c8244`.

The new compatible preparation is `.runtime/social_full_import_20261006/records.jsonl`,
SHA256 `4061e52dd2891a02893e4838a8815523c69628d7e469d25bfd623ead6eb0e7bf`.
Full row reconciliation recovered all 18 affected original strings in 10 rows;
every other field and the original archive/JSONL hashes match. Both admission
flags remain False. The codec and public display limits are described in
[historical social labels](social_historical_annotations.md#storage-of-original-control-characters).

The new file was fully imported and imported again into one newly created,
owned local test database. Both passes reconciled every payload, body hash,
annotation and current version. The first created 37,082 versions; the second
created zero. Counts and source-derived facets exposed no unadmitted records;
chunks, embeddings, usage and CLAIMS2 tables stayed empty. The test database was
removed. This is storage verification, not live admission, semantic validation
or client acceptance. Receipt: `.runtime/social_full_import_20261006/import_receipt-02.json`.
The earlier failed test guard stopped before creating a database and is retained
separately; only its address-format comparison was corrected.

Next: approve the corpus scope and duplicate counting rule, prepare a versioned admission decision, import the admitted scope, then test social filters, evidence retrieval and cross-collection answers. Facebook/Instagram inputs and independent question gold remain pending.
