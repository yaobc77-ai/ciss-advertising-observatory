# Advertising Observatory user guide

This guide describes **0.3.1**, prepared September 17, 2026. See the [research interface report](../reports/research_ui_v0_3_1_20260917.zh-CN.md) for local activation and validation status. The native collection contains 275 imported records, of which 263 appear in the default eligible selection and 226 have searchable text. The active sentence-based index remains `sentence600-v1`, with 556 passages; this interface update does not replace article text or republish the index. The [0.3.0 report](../reports/release_v0_3_0_20260917.zh-CN.md) records the earlier index publication.

## Navigate the application

| Page | Local address | Purpose |
|---|---|---|
| **Query** | [Open Query](http://127.0.0.1:8050/query) | Keyword search, paid answers and original-source evidence. The root address `/` also opens this page. |
| **Data** | [Open Data](http://127.0.0.1:8050/data) | Filtered counts, charts, sponsor-by-outlet cross-tab, record details and CSV downloads. |
| **Project wireframe** | [Open Wireframe](http://127.0.0.1:8050/wireframe) | Design-review reference for project collaborators, reached through the footer rather than the main navigation. |

The English main navigation contains **Query** and **Data**. These pages share the collection selection and filters. Filters persist in the browser session. Moving between the pages preserves the question and the last result; this does not promise that a full browser reload will restore an answer. Navigation does not submit a question or make a paid model call.

## Choose a collection

Use **Native advertising** or **Social advertising** at the top of the page. Each collection keeps its own filters when you change tabs. Until a real social dataset is imported, Social advertising shows the **not connected** explanation and hides its empty filters, statistics, charts and table. This is a pending dataset, not a measured total of zero advertisements.

Counts describe eligible records in the current filtered selection. Imported source assets may be retained by the data system without being counted as advertising records. **Searchable records** have text accepted for retrieval; other eligible records can still appear in the table and statistics.

## Filter and compare

Open **Data** for charts and the record table. The same collection filters also determine the default scope on **Query**.

Choose outlets, sponsors or advertisers, **Collection search term**, or **Historical automated label**. The social collection also supports platform filters when data is available. Filters combine; selecting several values within a field includes those values. Clear a field to include all values.

Set an optional publication date range. **Include unknown dates** is selected initially and can be turned off. Unknown text values remain visible as **(Unknown)**. **Collection search term** records a term used during collection; it does not identify the sponsor or establish the article's theme. A different collection term and sponsor in the same row are not automatically a data error.

Sponsor names use display forms such as **TotalEnergies**, **ExxonMobil** and **API**, while filtering retains the existing normalized keys. **CERAWeek** is marked as an event/series, not an energy company. Its inclusion in a company-only research denominator still requires a project scope decision; the interface does not silently reassign these records to a company.

Use **Count / Percent** to change the outlet/platform and sponsor charts. Percentages use the current filtered records as their denominator. The ranking charts show the top ten categories. The sponsor-by-news-outlet heatmap and cross-tab include **all** categories in the selection, including zero-count intersections. Each heatmap cell shows its count, and the color bar explains the count scale. The default native selection has 20 stored sponsor categories and eight outlets; these are collection categories, not 20 independently verified company identities. **Download cross-tab** exports the complete filtered matrix as CSV, with totals.

The publication timeline uses **yearly bars**, with a separate **Unknown** bar. The default native selection has 22 records with unknown dates. Changing date or other filters changes these counts; excluding unknown dates removes them from the selection.

**Historical theme labels** shows the 12 label categories from earlier automated classification. Different labels can overlap, so their counts can add up to more than the record total. The default selection has 43 records with no historical label; these records are not evidence of an absence of themes. The chart is an exploratory view of existing annotations, not a new topic model or a validated classification of every article.

## Inspect and download records

The native table displays the project fields with **Collection search term** as the collection-keyword heading, plus record-detail and archive access. Sort columns or use pagination to inspect records. Open a record's detail link to view its metadata, **Stored source text**, extraction-quality notes, original URL, archive availability and any reviewed local PDF. The text is shown unchanged; a partial capture is not presented as a complete article. Technical identifiers and source hashes remain available for auditing.

**Download selected records** exports all records selected by the collection filters, including records on other pages. It includes record/version identifiers and historical labels for traceability. Sorting the grid changes display order, not collection membership. This record export differs from **Download cross-tab**, which exports grouped sponsor/outlet counts.

Original links, public online archive links and local PDF snapshots are distinct. The current native selection has **no public archive URL**, **one reviewed local PDF snapshot**, **254 other records with unverified candidate files**, and **eight without a reviewed or candidate mapping**. Candidate files associated only by title are not linked as verified copies. A row without a verified archive shows that limitation explicitly; the app does not invent a Wayback URL.

The reviewed PDF is available on the [Using mollusks to monitor industrial sites detail page](http://127.0.0.1:8050/records/d340f887-efa7-5746-aaf8-14aabba6b63f), with preview and download. It contains page-layout and image limitations described on that page. Local capture identity does not establish the truth of advertiser claims or guarantee that the original webpage still works. PDF bytes are checked against the reviewed hash before serving; a changed or missing file is unavailable.

Source links are controlled by project configuration: when disabled, original/archive URLs and local PDF access are hidden. Internal filesystem paths, raw import payloads and private provenance are not part of the public response.

## Find evidence or request an answer

Open **Query** and enter a question or keywords, up to 2,000 characters.

- **Current collection and its filters** searches the active collection within its current filters.
- **Both collections · all eligible records** searches across the two collections independently of the collection filter panels.
- **Search keywords** retrieves passages without a paid model call.
- **Generate paid answer** uses the project's model API budget to generate an answer grounded in retrieved records. Availability depends on the configured service and usage limits.

Results show the last submitted question and filter scope. Changing the question or effective filters marks the existing result as out of date; it does not rerun the search or create another paid request. Use a search button again to refresh the results. Switching to Data or Wireframe and back also leaves the last result intact.

Evidence cards include a short passage, title, publication date (or an unknown-date label), collection, sponsor/outlet, result rank and available source links. **Read retrieved passage** expands the source passage. **Technical details** contains the evidence ID, record ID and text-version identifiers. Rank describes retrieval order, not a confidence percentage or proof that every search word is present.

Free keyword search uses English word stems and **OR** matching: a passage may match only part of a multi-term query. **Search term coverage** distinguishes terms missing from the returned passages from terms absent from the eligible filtered index. For example, in the default collection, `carbon capture and storage biogas` can return five passages without `biogas` even though three searchable records elsewhere in the current index match that term. Narrow the query to `biogas` to inspect those records. This diagnostic concerns keyword matches; it does not certify semantic support for a whole question.

Compare generated answers with their supporting passages; an advertising claim records what an advertiser said.

The current index ends chunks at sentence boundaries where possible, and answer preparation merges overlapping source intervals before selecting quotations. These steps preserve source locations; they do not establish that every generated claim is fully supported. The two **0.3.0** release smoke questions passed engineering citation-location checks, but human semantic review remains open, including an extra place name outside a selected quotation and repeated quotation use in the Chinese answer. The 0.3.1 interface changes do not establish that these generation issues have been resolved; this update made no new paid model calls.

Generated explanations follow the question's language; source quotations retain their original language. If a generated explanation clearly uses a different language, the app withholds it and keeps the evidence available. A short acronym or mixed-language question may be too ambiguous to check reliably. Use a full question in the language you want. Interface, count and service-status messages are currently in English.

If no supporting records are found, widen the filters, try a different term or search both collections. A model outage or usage limit leaves browsing and keyword search available when the data service is running. Data-service outages show a temporary-unavailability message and preserve the selected controls.

If the source or retrieval index changes while an answer is being prepared, the app withholds that answer. Submit again against the new version. A model request already dispatched before the change remains chargeable and is retained in the audit log.

## Current scope

The application covers the two fossil fuel advertising collections. Rebuilding the CLAIMS backend and adding animal agriculture datasets are future work. Availability of a social tab does not indicate that social data has already been connected.
