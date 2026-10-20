# Setup and user guide

## Explore the dashboard

[Open Data](https://ciss-advertising-observatory-production.up.railway.app/data) · [Open Query](https://ciss-advertising-observatory-production.up.railway.app/query)

These links open the hosted release. Later local changes below are available at [local Data](http://127.0.0.1:8050/data); they have not been deployed.

- Open **Data** and select a collection. Filter by sponsor, news outlet, and publication date.
- In **Native advertising**, use **Knowledge graph** to select a company, publisher, connection, or article. The side panel shows the named relationship, record counts, shares, and supporting articles. Selecting a distribution row or chart segment narrows the supporting articles.
- Use **Overview** for the company–outlet matrix, annual counts, and historical label distributions. Unknown dates are reported separately.
- Use **Records** to open article details, stored text, and available original or archived sources. Export the selected records or grouped counts as CSV.
- Open **Query** for keyword search or generated answers. Generated answers can use database tools for statistics and retrieved passages for content questions. Check the cited sources when interpreting an advertising claim.
- For counts, publisher/sponsor lists and percentages, open **Inspect matching records** and use **Previous**, **Next** or **First page**. Paging preserves the submitted selection and makes no model calls. Editing filters does not change a saved answer; submit a new question to apply them. A collection update requires a new query.

To compare a company with an outlet, choose the sponsor, outlet and optional dates in **Collection filters**. In **Overview**, a matrix cell opens its specific articles; **Download counts** exports the whole filtered matrix. In **Records**, **Download selected records** exports the same selection, including rows on other pages. Missing source dates are written as `(Unknown)`.

Generated answers show **Citation [n]** next to every cited quotation. **Retrieval rank** is a separate ordering of search results. One article card may support more than one answer citation.

The selected reviewed PDF's preview and server bytes are available. An Edge **Download PDF** check was blocked with `ERR_BLOCKED_BY_CLIENT`; browser download remains unresolved. Record CSV and cross-tab downloads have been checked separately against their selected records.

The local **Company social posts** collection contains 36,182 unique original posts, preserving all 37,082 source observations. Of these, 36,150 have searchable text and 32 are paused for conflicting text, quality problems or strict sentence-source validation. Counts use one post per platform and canonical original URL, following a user decision. These are not verified paid advertisements, and the client has not approved that social-advertising denominator. CLAIMS2 import and read-only views are implemented; real results still await reviewed publication.

The local [social account view](social_account_exploration.md) adds company-affiliation,
platform, source-account and date controls. Select an account
bar in Overview to open its Records under the same other filters. Current-selection
Query and CSV exports preserve those account choices. Company affiliation is
not verified paid sponsorship; native label charts do not represent the supplied
social label scheme. A checked AFPM account selection shows 745 posts and 743 searchable bodies; its selected-record CSV has exactly those 745 members. This local change has not been deployed or independently accepted by the client.

In local social record details, **Supplied social historical labels** shows the
13 original codes as source True, source False or Unknown. Historical generated
explanations are separate from the post text. False is an old classifier value,
not a reviewed finding that greenwashing is absent. The source tool returns the
same bounded view for permitted records. Paused post-text/source tools return metadata and review reasons rather than unreviewed text. The local Overview shows 13 separate source-state distributions and
their current-post denominator. Click a nonempty segment to open its matching
posts. Under an existing source-state selection, only an already selected state
can be narrowed by clicking; change or clear the dropdown to choose another one.
Multiple choices mean **any selected state**, not all labels together. CSV
includes these source states and their unverified scheme. Refresh after source
changes; this local feature is not deployed. See
[the source-state guide](social_historical_annotations.md).

Maintainers can run a [read-only CLAIMS source audit](claims_source_audit.md) against the supplied saved results before importing classifications. This command does not publish new labels.

## Install and configure

Follow the commands in the [README](../README.md). PostgreSQL must support pgvector. Keep `.env` and database backups private.

`OBS_DATABASE_URL` specifies the database connection. `OBS_COOKIE_SECRET` should be a random, stable value. `OPENAI_API_KEY` enables model requests. Model names, API budget, and request limits are configured in `.env.example`. `OBS_SHOW_SOURCE_LINKS=false` hides original advertisement links.

## Load data

Native CSV/XLSX inputs are validated against the source files referenced by `config/native_admissions.json`, `config/native_body_ranges.json`, and `config/native_body_recoveries.json`. Obtain those exact source files before using the native importer.

```sh
uv run observatory import-native --root /path/to/source-bundle
```

For the supplied nested Twitter ZIP, first use the offline preparation workflow:

```sh
uv run observatory prepare-social /private/Social-Media-Data.zip \
  --out .runtime/social-next/records.jsonl \
  --report .runtime/social-next/audit.json
```

The first preparation preserved 37,082 supplied observations with counts and retrieval disabled. Preparation itself makes no database or model calls. A separate user-reviewed [company-post admission workflow](social_posts_admission.md) grouped original URLs, preserved source variants and produced the locally imported 36,182-post collection. The frozen v2 pauses 32 bodies and permits 36,150 for retrieval. An exact reimport created zero new versions.

For a new source bundle, prepare and review the admission package before using the existing `import-records --dataset social` path. Do not import the unadmitted preparation as if it were the reviewed unique-post package, and do not use the mapped CSV importer for this nested source. See [source input handling](social_archive_input.md) and [the local execution record](decision_followup.zh-CN.md). This workflow does not approve paid-ad identity or public deployment.

For separately reviewed social CSV exports, map the client fields using `config/social_mapping.example.json`:

```sh
uv run observatory import-social /path/to/posts.csv --mapping config/social_mapping.example.json
```

The import commands update records by default. A complete replacement requires the explicit `--mode snapshot` option. The alternative `import-records` command accepts validated JSONL records; `src/observatory/models.py` defines their fields, and `--dry-run` validates without changing the database.

```sh
uv run observatory index
```

Indexing may make paid embedding requests. Without embeddings, keyword search remains available.

## How the application works

Imports validate metadata and retain article text and versions in PostgreSQL. Dashboard filters, counts, and exports share the same record selection. Search combines keyword and vector retrieval. Generated content answers select program-built reference IDs from stored body passages and any configured image/video evidence. The application restores the exact quotations, types and locations and rechecks the current sources. It does not ask the model to invent a quotation or a video time.

The graph contains articles, source-listed sponsor names, publishers, and their record-supported relationships. Missing source fields stay explicit. A source relationship is not independent evidence of payment, and a located quotation does not by itself establish the truth of a claim.

## Current local review work

**Tools → Evaluation** defines 16 measures for the six customer research tasks.
No independently reviewed quality report is configured. Read the
[methodology](evaluation_methodology.md) before interpreting a published score.
If a reviewed report is later selected, its measurements describe the displayed
frozen run. Check its scope, sample coverage, failures and limitations; a partial
review is not a final score or evidence that the current release passed.

In **Data → Overview**, select the **Native** collection and use **Reviewed
content questions** to choose one of Q01–Q24 under the current filters. The
coverage counts include every active, countable record in that selection:
reviewed matches, reviewed nonmatches and unknown records. A nonmatch requires
an explicit complete-source and full-text review; pending, changed or
insufficient text remains unknown. These judgments describe the advertisement
under the reviewed question definition, not the truth of its claims.

Each displayed match links to the current article and materials, shows supporting
and limiting quotations where supplied, and identifies their article version
and character positions under **Source location**. Original source links follow
the configured link setting. Read the speaker, treatment and planned/achieved
status alongside the quotations.

**Complete classification** means no record is unknown for that question and
selection. The number shown on the current page is separate: **Previous matches**
and **Next matches** browse reviewed matches without model calls. **Download this
page JSON** exports that page, its record/source/version bindings and coverage
for the whole selection. It contains a complete matching list only when both
`classification_complete` and `page_complete` are true. Record and matrix CSV
downloads retain their separate selection-wide behavior. If the question,
selection, publication or source version changes, read the first page again
before continuing or exporting.

No real reviewed content publication is configured: all 6,312 judgments remain
pending. An unavailable publication or empty displayed page does not mean no
advertisements match. The [reviewed content workflow](content_publication.md)
describes the review and operator selection needed before results appear.

The [24-question review packet](content_review_packet.md) and
[offline full-text workflow](content_assessment.md) prepare source-linked
classification work separately from online question answering. Preparing a
[provider run plan](content_provider.md) does not call a model; execution requires
separate authorization. No real assessment call has been made. These local
changes are not covered by the earlier release receipt.

The local [MCP source-reading tools](mcp_research_tools.md) support admitted
native and company-post records with the current filters intact. The standard MCP catalog has 10 read-only tools; the web model catalog has 9. Web content answers can combine body and typed media references through the service's internal reader. The 32 paused posts cannot expose their unreviewed body through text or media tools. Paid-advertising questions return the missing-identity limitation rather than substituting company-post counts.

The web planner uses `search_records` for content questions; the service then reads a fixed operator-mounted media bundle for each requested target. Direct `get_media_evidence` remains MCP-only. The reader keeps image/video origins and locations separate and does not download media, run OCR, transcribe audio or call a model. Answer generation still uses the configured model budget. The three production media settings remain unconfigured. Earlier real checks covered six saved-page texts and 23 retained units; saved page text is not a caption. Actual image recognition, captions and transcripts remain at zero.

A media evidence card states whether it contains OCR text, an image description, a publisher/automatic caption or a transcript. It shows a supplied page/region or video segment when available; an unknown location remains unknown. These excerpts are not labeled as quotations from the article body. Citation numbers are shared with body evidence, while hashes and derived-text offsets remain under **Technical details**. Comparison scope reports actually cited records for each target, without claiming semantic accuracy or a complete list of matching advertisements. See [media answers](media_answers.md).

No configuration gives `not_configured`; requested media absent from a valid bundle gives `missing_material`; available media with no match gives `no_match`. These states do not prove that the original advertisement lacks that content. Changed or mismatched evidence blocks the answer rather than being hidden by a web lookup.

The local [media-material form](http://127.0.0.1:8070/media) lists 26 concrete sources and accepts screenshots, descriptions and optional times as separate pending review records. Submitted material does not automatically enter search or become an original-body quotation. The [24-question reference draft](../.runtime/customer_holdout/references/24_answer.md) is AI-assisted development material; complete gold, independent testing and client review remain pending. This update made no paid calls or remote writes and does not establish dual-collection answer quality.

## Deploy and maintain

Build the provided Docker image or connect the repository to Railway. Configure the database URL, cookie secret, and optional API key through the platform's variables. Use `OBS_HOST=0.0.0.0`; Railway supplies `PORT`. For HTTPS hosting, set `OBS_SECURE_COOKIES=true` and configure the trusted proxy for the deployment.

Apply migrations with `observatory migrate` before serving the application. Use `/healthz` to check availability and the application version. Back up the database before upgrades and retain source inputs separately. Import and indexing commands can be repeated when data changes.

Reviewed PDFs and previews are deployed separately using a [private record asset bundle](record_assets.md). [Current handoff instructions](current_handoff.md) cover complete database recovery, source inputs, and remaining acceptance work.

The GitHub Pages workflow publishes only `site/`. It provides the static project description and links to the running application; it does not contain the database or execute RAG.
