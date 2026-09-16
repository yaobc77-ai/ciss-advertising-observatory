# Advertising Observatory user guide

## Choose a collection

Use **Native advertising** or **Social advertising** at the top of the page. Each collection keeps its own filters when you change tabs. Social advertising displays **not connected** until the real project dataset is imported.

Counts describe eligible records in the current filtered selection. Imported source assets may be retained by the data system without being counted as advertising records. **Searchable records** have text accepted for retrieval; other eligible records can still appear in the table and statistics.

## Filter and compare

Choose outlets, sponsors or advertisers, collection keywords, or historical automated labels. The social collection also supports platform filters. Filters combine; selecting several values within a field includes those values. Clear a field to include all values.

Set an optional publication date range. **Include unknown dates** is selected initially and can be turned off. Unknown text values remain visible as **(Unknown)**. Collection keywords and sponsors describe different information.

Use **Count / Percent** to change the outlet/platform and sponsor charts. Percentages use the current filtered records as their denominator. The charts show the top ten categories, the relationship chart shows the top eight sponsors and outlets, and the table includes the complete selection. The timeline excludes records with unknown dates; their count remains visible above it.

Historical labels are outputs from earlier automated classification. They can support exploration; their definitions and source versions are documented separately. Different labels can overlap.

## Inspect and download records

The native table displays the six project fields: source URL, news outlet, title, date, sponsor, and keyword. Sort columns or use pagination to inspect records. **Download selected records** exports all records selected by the collection filters, including records on other pages. It includes record/version identifiers and historical labels for traceability. Sorting the grid changes display order, not collection membership.

Public original and archive links appear when available. Their presence does not mean they were checked online during your visit. Source links are controlled by the project configuration: when disabled, URLs are hidden in the table, evidence cards, and downloads. Internal paths and disclosure text are not part of the public response.

## Find evidence or request an answer

Enter a question or keywords, up to 2,000 characters.

- **Current collection and its filters** searches the active collection within its current filters.
- **Both collections · all eligible records** searches across the two collections independently of the collection filter panels.
- **Search keywords** retrieves passages without a paid model call.
- **Generate paid answer** uses the project's model API budget to generate an answer grounded in retrieved records. Availability depends on the configured service and usage limits.

Results show the last submitted question and filter scope. Changing the controls does not rerun the search or create another paid request; use a search button again to refresh the results.

Evidence cards include a short passage, title, collection, sponsor/outlet, evidence ID, record ID, text version and available source links. **Read retrieved passage** expands the source passage. Compare the answer with its supporting passages; an advertising claim records what an advertiser said.

If no supporting records are found, widen the filters, try a different term or search both collections. A model outage or usage limit leaves browsing and keyword search available when the data service is running. Data-service outages show a temporary-unavailability message and preserve the selected controls.

## Current scope

The application covers the two fossil fuel advertising collections. Rebuilding the CLAIMS backend and adding animal agriculture datasets are future work. Availability of a social tab does not indicate that social data has already been connected.
