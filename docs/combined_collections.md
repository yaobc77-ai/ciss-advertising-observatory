# Unified native and social collections

Updated: 2026-10-06. Local implementation; publication and client acceptance are separate.

## What changes

Query and Data now start with **All records**. Company, collection search term and publication-date filters apply to both collections. Native advertising and Company social posts remain available for outlet, platform, account, historical-label and graph exploration.

Data provides:

- Separate native-ad and company-post counts, including searchable records and unknown dates.
- Sponsor/company comparisons and annual charts with separate series for the two record types.
- Click a bar to browse its corresponding records while keeping date and collection-term filters.
- One paged source table with record type, sponsor or company affiliation, outlet or platform, account, date, original and archive links.
- A complete CSV export of the current selection, with dataset, source identity, version, count unit and paid-ad status.

Open a record title to read the existing text and source materials. The unified interface reuses current record identities. A separate local update on 2026-10-06 enabled saved-text retrieval for the remaining 32 company posts, preserving their original text and source observations.

## Identity and counting

Native advertisements and social posts are different units. The interface never presents their sum as the number of paid advertisements. The social source contains collected company posts; paid status remains **not verified**.

For the unified selector, `Shell` and `shell` share a displayed name and expand to both exact source values. Different aliases, such as `Williams` and `Williams Companies`, remain separate. Sponsor display names do not establish entity identity or a financial relationship. The export preserves original names alongside readable labels.

Shared filters are company, collection term and publication date. Collection-specific filters remain in their respective views; they are not silently translated across datasets. Unknown dates are included by default and are displayed separately. Changing the selected view does not clear its saved filters.

## Implementation

- `combined_ui.py` owns the unified workspace, company selection, charts, paging, click-through and export.
- `app.py` adds the collection choice and passes a third, separate filter scope to the existing Query paths.
- `Database.dashboard()` calculates type counts, companies and years from the same read-only database snapshot as page membership.
- Paging reuses signed summaries, checks the data and social-source versions, and reads only the requested page. Changed sources refresh the first page; persistent changes withhold the result.
- Export checks current filters, version and complete per-type membership before producing a download. Public projections and link settings remain binding.

## Local verification

Current full selection: **263 native advertisement records** and **36,182 unique company posts**. Of these, 232 and **36,182** have searchable saved text. There are 22 native records without publication dates.

The later all-post retrieval update indexes every one of the 37,082 preserved
social source observations separately. Differing text remains unadjudicated;
quotes identify their exact observation, while each unique post counts once.
The active profile is `sentence600-social-observations-v1`, with 37,086 social
chunks and the unchanged 622 native chunks. Existing vectors were preserved;
this update generated no new vectors or paid calls. Full per-observation
character coverage and independent database checks are recorded in
[the retrieval report](all_social_posts_retrieval.zh-CN.md). Earlier receipts
under `.runtime/combined_collections_20261006/` describe the previous profile
and retain their original evidence scope.

The unified Shell selection returns **10 native ads and 3,137 company posts**, retaining the exact source spellings. Database validation independently enumerates full members, company counts and years, and compares ordered page identities. Receipts are saved locally in `.runtime/combined_collections_20261006/`.

Actual browser checks confirmed that the company bar opens Records, both pages'
18 rendered links match the corresponding ordered reference prefixes, and a
record title opens its captured post text and source links. The export page
reports 10 native ads and 3,137 company posts; the automation download-event wait
expired before a file path was captured, so no downloaded-file content check is
claimed.

The query tool definitions reuse local schema definitions and share repeated
filter guidance once. The initial entity directory has a 6KB soft budget;
omitted names remain resolvable against complete source facets, and selected
identities are retained. A pathological long selection can still trigger the
unchanged 60KB total-input limit. All 39 historical social-state IDs remain.
Twelve real-source capacity probes (four scopes, ordinary and 2,000-character
English/Chinese questions, each with one entity resolution) fit that limit;
the largest input is 57,676 bytes. This is not a guarantee for arbitrary later
tool outputs. Local schema definitions and
references are supported by [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs#definitions-are-supported).
Offline and payload checks do not establish live provider compatibility or
semantic answer quality; no paid call is part of this verification.

These are source and engineering checks. They do not establish the accuracy of model answers, advertising coverage, paid status or client acceptance.
