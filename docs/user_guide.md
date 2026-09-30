# Advertising Observatory user guide

This guide describes the local prototype updated on **September 29, 2026**, including the large interactive source knowledge graph, company/outlet explorer and model-assisted database answers. These latest changes have not been deployed to Railway. See the [graph implementation report](../reports/COLLECTION_KNOWLEDGE_GRAPH_20260929.zh-CN.md), [feedback audit](../reports/MICHELLE_FEEDBACK_AUDIT_20260929.zh-CN.md) and [database smoke results](../reports/collection_graph_smoke_20260929.json) for the current scope and verification. The native collection contains 275 imported records, of which 263 appear in the default eligible selection and 226 have searchable text. The active sentence-based index remains `sentence600-v1`, with 556 passages; this interface update does not replace article text or republish the index. The [0.3.0 report](../reports/release_v0_3_0_20260917.zh-CN.md) records the earlier index publication.

## Navigate the application

| Page | Local address | Purpose |
|---|---|---|
| **Query** | [Open Query](http://127.0.0.1:8050/query) | Model-assisted counts/lists and cited content answers; keyword search has no model charge. The root address `/` also opens this page. |
| **Data** | [Open Data](http://127.0.0.1:8050/data) | Opens **Knowledge graph** for network exploration. **Overview** provides count comparisons and charts; **Records** provides the paged article table. |
| **Project wireframe** | [Open Wireframe](http://127.0.0.1:8050/wireframe) | Design-review reference for project collaborators, reached through **Tools** in the top-right corner. |

The English main navigation contains **Query** and **Data**. These pages share the collection selection and filters. Filters persist in the browser session. Moving between the pages preserves the question and the last result; this does not promise that a full browser reload will restore an answer. Navigation does not submit a question or make a paid model call.

## Choose a collection

Use **Native advertising** or **Social advertising** at the top of the page. Each collection keeps its own filters when you change tabs. Until a real social dataset is imported, Social advertising shows the **not connected** explanation and hides its empty filters, statistics, charts and table. This is a pending dataset, not a measured total of zero advertisements.

Counts describe eligible records in the current filtered selection. Imported source assets may be retained by the data system without being counted as advertising records. **Searchable records** have text accepted for retrieval; other eligible records can still appear in the table and statistics.

## Filter and compare

Open **Data** for charts and the record table. Sponsor, outlet and date filters appear above all three views, followed by the current scope. **More filters** contains collection search terms and historical labels. Switching views preserves the selection; **Clear filters** resets it. The same collection filters also determine the default scope on **Query**.

Choose outlets, sponsors or advertisers, **Collection search term**, or **Historical automated label**. The social collection also supports platform filters when data is available. Filters combine; selecting several values within a field includes those values. Clear a field to include all values.

Set an optional publication date range. **Include unknown dates** is selected initially and can be turned off. Unknown text values remain visible as **(Unknown)**. **Collection search term** records a term used during collection; it does not identify the sponsor or establish the article's theme. A different collection term and sponsor in the same row are not automatically a data error.

Sponsor names use display forms such as **TotalEnergies**, **ExxonMobil** and **API**, while filtering retains the existing normalized keys. **CERAWeek** is marked as an event/series, not an energy company. Its inclusion in a company-only research denominator still requires a project scope decision; the interface does not silently reassign these records to a company.

In **Overview**, start with **Explore a company or a news outlet**, above the matrix:

1. Under **Start with**, choose **Company / sponsor** to see its publishers, or **News outlet** to see its source-listed sponsors. Choose the company/sponsor or outlet in the dropdown. The explorer narrows the current filters; it does not discard them.
2. Read the horizontal bars. Every matching publisher or sponsor is shown with its exact record count. **View every count as a table** provides the complete numbers as text. These results are not restricted to the top ten.
3. Select a bar, or use **Show records for**, to read its **Matching articles** beside the chart. **All matching articles** shows the whole selected company's or outlet's record set. The list displays ten records per page; use **Previous articles / Next articles** for the rest. Open an article title for stored text and source materials.

With the default collection filters, ExxonMobil appears in 15 records across four outlets: Business Insider 5, The Washington Post 5, The New York Times 3 and The Wall Street Journal 2. Choosing The Washington Post shows 18 records across seven source-listed sponsors/organizations, including API and AFPM as associations. These numbers describe this collection; they do not establish all commercial partnerships or verify every source sponsor assignment. Dates and other filters can change the results.

For comparison across multiple companies and outlets, the sponsor-by-news-outlet matrix includes **all** categories in the selection, including zero-count intersections. Each cell shows its count, and the color bar explains the count scale. Select a cell to list matching articles beside the matrix (below it on narrow screens); selecting a zero shows an explicit empty result. Article titles open their source details. **View the complete count table** expands the cross-tab, and **Download counts** exports the complete filtered matrix as CSV, with totals. The default native selection has 20 stored sponsor categories and eight outlets; these are collection categories, not 20 independently verified company identities.

Below the matrix, **Count / Percent** changes the outlet/platform and sponsor ranking charts. Percentages use the current filtered records as their denominator. These ranking charts show the top ten categories. All charts retain horizontal numbers and wrapped long labels; wide matrices scroll inside their own panel.

The publication timeline uses **yearly bars**, with a separate **Unknown** bar. The default native selection has 22 records with unknown dates. Changing date or other filters changes these counts; excluding unknown dates removes them from the selection.

**Which historical labels appear?** shows the 12 label categories from earlier automated classification. Different labels can overlap, so their counts can add up to more than the record total. The default selection has 43 records with no historical label; these records are not evidence of an absence of themes. The chart is an exploratory view of existing annotations, not a new topic model or a validated classification of every article.

Select a historical-label bar, or choose **Historical label** in **Read the labeled articles**, to read matching records beside the chart. The list intersects the chosen label with every current filter, including already-selected historical labels. Paging and **Clear** affect this article list without changing the collection filters. Exact label identifiers remain in **Technical label reference**. These saved automated labels do not establish verified greenwashing findings.

## Explore advertising relationships

Open **Data → Knowledge graph**. The initial **Entities** view contains every source-listed sponsor/organization and outlet in the current filters, with every counted association between them. The default view has **27 entity nodes and 35 associations**, derived from 263 eligible records. Node size represents supporting record count; line width represents records co-listing that sponsor and outlet. There is no Top-N cutoff. One record lacks a sponsor and cannot produce a sponsor/outlet line; it remains available in Articles and Records. **Scope & missing fields** explains this coverage.

Sponsor nodes are circles; outlets are rounded squares. Each interior dot summarizes one record. The two-color outer ring shows whether those records have text eligible for retrieval or metadata only. It does not indicate verified content or claim truth. Entity links mean names co-listed in source records, while Article arrows explicitly identify **Source lists sponsor** or **Published in**.

After selecting a company or outlet, the detail panel shows a **donut chart**, the complete counterpart list, counts and record shares. The denominator includes every supporting record in the current filters, including an explicit missing-source category when needed. Select a slice, a name in the count table, or **Show supporting records for** to read that category's articles and highlight its relation. Donut colors identify categories within this selected breakdown; they do not encode support/opposition or match graph-node types. **Download counts** exports every category, its exact source value, count, share and denominator. Selected relationship details also show publication-year shares and separate shares relative to both endpoints.

**Try a client question** provides direct Data shortcuts for ExxonMobil's publishers, Washington Post's sponsors and the New York Times record total, with no model call. They respect the current filters; an unavailable object produces an empty result rather than switching to all records. See the [second-iteration delivery report](../reports/GRAPH_DETAILS_V2_20260929.zh-CN.md) for the client requirement review.

1. Drag the canvas to pan, drag nodes to move them, and scroll or use **+ / −** to zoom. **Fit** fits the existing positions to the view. **Expand view** gives the graph more screen space; **Exit expanded view** or Escape returns. Opening or resizing the graph automatically fits its existing positions and preserves the selection; a Reset is not required. **Layout** starts with **By type**, placing sponsors and outlets in separate readable groups; Network, Circle and Grid are also available. Positions describe the layout, not a measured geographic or business distance. **Reset** clears the selected object and lays out the current graph again.
2. Click a node or line, or use **Find a node or relationship** with the keyboard. The selection panel shows exact counts, all connected sponsor/outlet names and their counts, and supporting articles. For example, The Washington Post has 18 supporting records across seven source-listed sponsors/organizations; ExxonMobil has 15 across four outlets. Other graph connections fade while the selected neighborhood is highlighted. Selection and record paging preserve manually moved positions and the viewport.
3. Use **Previous records / Next records** above the selection details to read all matching articles, ten per page. Each title opens the record's stored text, original reference and available source materials. Selecting the ExxonMobil → The Washington Post line shows its five supporting records.
4. Switch to **Articles** to expand the selected node or association, or the selected donut category, into article nodes and typed sponsor/outlet paths. Without a selected object, Articles includes the whole current selection: 290 nodes and 525 source-field relations in the default collection. If you expanded a selected object/category, **Scope & missing fields** makes that restriction explicit. Entity dots/counts then describe this expanded subset. Reset while in Articles returns to all selected records. Article labels appear when selected; use the searchable node list to find titles.
5. **PNG ↓** downloads the current visible drawing. **JSON ↓** exports the **complete current filtered map**, including every article, source relation, counted association, stable IDs, record/version witnesses, definitions and coverage. A focused drawing does not reduce this JSON export. It contains public metadata, not article bodies or private import payloads. Source-link configuration applies to the export as well.

The original, more detailed source inspector is below the large graph in **Inspect article versions, sources and historical annotations**. Open this section to load its five-article page. **Sources** follows versions and materials; **Historical labels** follows one saved annotation version and its available evidence. Arrow direction and the relation dictionary define these connections. Its **Download page graph** exports that inspector's five-article page, distinct from the large graph's complete JSON export. Graph browsing and downloads do not call a paid model.

Sponsor/outlet identities remain exact source candidates; display aliases do not merge companies. Missing fields do not create a shared real-world “Unknown” entity. Historical labels are model annotations, not verified themes, factual verdicts or proof that the article contains a particular claim. An annotation is linked to the current text only when its recorded body hash matches. Missing evidence spans and unavailable codebooks remain explicit; the graph does not invent quotations. Text recovered from a PDF does not inherit the old text's labels. Social relationships and reviewed corporate identity mappings remain pending.

## Inspect and download records

Open **Data → Records** for article titles, sponsors, outlets, publication dates and source/archive access. Article titles link directly to their detail pages. The collection search term remains clearly labeled in record details and in the export, separate from sponsor identity. Use **Sort records**, **Rows per page**, **Previous** and **Next**; the server returns only the requested page. Charts and totals still cover the entire filtered selection. Open a title to view its metadata, **Stored source text**, extraction-quality notes, original URL, archive availability and any reviewed local PDF. The text is shown unchanged; a partial capture is not presented as a complete article. Technical identifiers and source hashes remain available for auditing.

**Download selected records** exports all records selected by the collection filters, including records on other pages. It includes record/version identifiers and historical labels for traceability. Sorting the grid changes display order, not collection membership. This record export differs from **Download counts** in Overview, which exports grouped sponsor/outlet counts.

Original links, public online archive links and local PDF snapshots are distinct. The current native selection has **no public archive URL**, **one reviewed local PDF snapshot**, **254 other records with unverified candidate files**, and **eight without a reviewed or candidate mapping**. Candidate files associated only by title are not linked as verified copies. A row without a verified archive shows that limitation explicitly; the app does not invent a Wayback URL.

The reviewed PDF is available on the [Using mollusks to monitor industrial sites detail page](http://127.0.0.1:8050/records/d340f887-efa7-5746-aaf8-14aabba6b63f), with preview and download. It contains page-layout and image limitations described on that page. Local capture identity does not establish the truth of advertiser claims or guarantee that the original webpage still works. PDF bytes are checked against the reviewed hash before serving; a changed or missing file is unavailable.

Source links are controlled by project configuration: when disabled, original/archive URLs and local PDF access are hidden. Internal filesystem paths, raw import payloads and private provenance are not part of the public response.

## Find evidence or request an answer

Open **Query** and enter a question or keywords, up to 2,000 characters.

- **Current collection and its filters** searches the active collection within its current filters.
- **Both collections · all eligible records** searches across the two collections independently of the collection filter panels.
- **Search keywords**, inside **Tools**, retrieves passages without a paid model call. Search scope is also inside Tools. **Collection filters** can be expanded under the question, or opened through its shortcut in Tools.
- **Generate answer**, beside the question, first uses the model to interpret the question and select a constrained read-only tool when `OBS_RESEARCH_AGENT_ENABLED=true`. Interpretation uses the project's API budget even for counts. The database calculates counts and organization lists; source/graph reads do not call a model. Advertisement-content questions also use the existing paid retrieval and grounded-generation path. Data exploration and keyword search remain free.

The three example buttons fill the question box only. They do not change filters or submit a request. Choose an example and then select **Generate answer**:

- **Count ads at an outlet**: `How many native ads are from the New York Times?`
- **Explore a company's publishers**: `Which publishers is ExxonMobil working with?`
- **Explore an outlet's sponsors**: `Which fossil fuel companies has the Washington Post worked with?`

Database answers show **Collection statistics · model-assisted query** in model mode, the effective filter scope, exact totals, searchable-record coverage and unknown-date counts. **How this question was answered** shows selected tools, call count and API cost. List answers include every matching category and its count. **Inspect matching records** shows up to ten example records per collection; use Data with the shown filters to browse all matching articles. Totals include every eligible record, even without searchable text. For example, the default NYT result counts 19 records even though only 15 have searchable text. The older fixed-phrase baseline, available with the model switch disabled, retains its no-model-charge label.

The model interprets dates and bilingual entity names, then validates them against available source fields. Explicit dates narrow the active date range and exclude records whose dates are unknown; inspect the displayed scope. An unavailable or ambiguous company/outlet name prompts clarification. Unsupported percentages or counts of themes/greenwashing require a defined denominator or validated annotations; historical model labels do not establish verified greenwashing totals. Source-listed organization lists can include associations and events, even when a question uses the word “companies.” Multi-part questions and missing references may require clarification; this interface does not yet resolve conversational pronouns from previous queries.

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
