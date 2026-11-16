# Independent statistics references

`scripts/prepare_statistics_reference.py` prepares G01–G03 from exact source
metadata. It is a **current-corpus development reference**, not a customer
approval, semantic gold, unseen test result or market-wide advertising total.

## Existing work and the additional scope

- `scripts/build_user_question_gold.py` already provides independent SQL answers
  for the fixed 38-question development bank. Its group output selects one top
  item; this new reference retains **all maximum-year ties** and exact record
  membership for every matrix cell and source relationship.
- The 1 October native export reconciliation records a historical download. It
  does not automatically become a current reference or customer acceptance.
- `scripts/prepare_client_review.py` freezes reviewed semantic packets. The new
  preparer does not create approvals or reuse its application filter results.

## Outputs

| Reference | Contents |
| --- | --- |
| G01 | Full company/source-sponsor × outlet matrix, including zero cells; exact record IDs; row and column totals. |
| G02 | Typed `source_listed_sponsor_at_outlet` relationships and their exact supporting record IDs. Missing entities are recorded separately. |
| G03 | Overall and per-entity yearly counts, all tied maximum years, unknown-date members, and two configured inclusive periods with counts, members and differences. |

Company names are exact source sponsor keys. There is no automatic alias merging,
company classification, inferred date, duplicate-post removal, sponsorship
verification or relation to payment/contracts. A blank entity is a missing-data
bucket, not a fabricated `Unknown` company node. The count unit is exactly
`source_record_id`; one record is not automatically one independently verified ad.

Rows are selected by dataset, observed active/countable flags and configured exact
source keys and dates. Unknown dates remain unknown. Periods intersect the base
selection; an unknown date is explicitly unassigned to both periods. Overlapping
periods require explicit permission and expose their shared record IDs. A zero
first-period denominator gives no percentage change.

## Configuration and execution

Create a private JSON configuration. This example defines development periods;
it does not set customer policy or a required historical comparison:

```json
{
  "dataset": "native",
  "counting_unit": "source_record_id",
  "scope_label": "Observed active countable native records; development reference",
  "filters": {"include_unknown_dates": true},
  "allow_period_overlap": false,
  "periods": [
    {"id": "first", "date_from": "2020-01-01", "date_to": "2020-12-31", "unknown_dates": "unassigned"},
    {"id": "second", "date_from": "2021-01-01", "date_to": "2021-12-31", "unknown_dates": "unassigned"}
  ]
}
```

Optional filters are `sponsors`, `publishers`, `date_from`, `date_to`, and
`date_presence` (`any`, `known`, `missing`). `include_unknown_dates` is mandatory.
Date boundaries are inclusive; source dates must be `YYYY-MM-DD` or missing.
No historical labels, free-text conditions or inferred-date policy are supported.

Run from the project root:

```powershell
# Offline: no database configuration, network or model requests.
.\.venv\Scripts\python.exe scripts/prepare_statistics_reference.py `
  --input .runtime/private-source-records.jsonl `
  --config .runtime/statistics-config.json `
  --output .runtime/statistics-reference-new

# Optional source acquisition: an existing configured database, read-only.
.\.venv\Scripts\python.exe scripts/prepare_statistics_reference.py `
  --database --config .runtime/statistics-config.json `
  --output .runtime/statistics-reference-current
```

Offline input can be canonical JSONL, a JSON array, or a JSON object with a
`records` array. Rows can be canonical records or database-style
`{record_id, dataset, version_id, payload}` objects. `countable` must be an actual
boolean. `active` defaults to true for supplied canonical-file rows; present
`retrievable` flags and version IDs are preserved. A hash-only frozen manifest
does not contain enough metadata and is rejected. Supplied identities are marked
unverified rather than promoted to authenticated database versions.

Database acquisition uses raw source reads in a **REPEATABLE READ, READ ONLY**
transaction with `default_transaction_read_only=on`. It captures the source
version identity before and after acquisition within the same snapshot. That
establishes one coherent observation, not that subsequent database changes are
impossible. It does not call application analytics, retrieval, public filter or
statistics functions, and does not import data, run migrations or call a model.
Database exception messages and credentials are not printed.

The destination must be new. Keep these files private, for example under ignored
`.runtime/`:

- `source_metadata.json`: the exact normalized metadata, source version IDs and
  countable/retrievable flags used in calculation; no source bodies are copied.
- `reference.json`: G01–G03, selection members, source identity and limitations.
- `config.json`: exact configured selection and period rules.
- `manifest.json`: hashes of those files and the preparer itself.

The metadata fingerprint is **not** the application's combined data/index
fingerprint. No index identity is needed or invented for these metadata-only
calculations. Approval flags remain false and no system accuracy is reported.
Use the reference to check the actual query, export and graph paths separately;
an independently calculated answer does not establish that those paths passed.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_prepare_statistics_reference.py
.\.venv\Scripts\python.exe -m ruff check scripts/prepare_statistics_reference.py tests/test_prepare_statistics_reference.py
```

Synthetic checks cover exact membership, zero cells, all ties, empty scopes,
unknown dates, inclusive period endpoints, overlapping periods, withheld
percentage changes, source identity conflicts, admission flags and private
read-only acquisition. These test the preparer, not independent customer review.

## Current private preparation

One current source observation was prepared on 6 October 2026 UTC (the 5 October
New York work session), in `.runtime/statistics_reference_20261005/current/`.
It has 275 active source records, 263 observed countable records and 226 observed
retrievable records. G01 contains 160 cells; G02 contains 35 source-defined
relationships. Twenty-two selected records have no source publication date.

The source version identity before and after acquisition was
`5114ebc1cf9afe59cdaa715e3ea45166`. The private manifest binds the actual source
metadata, configuration and reference bytes. CNBC's known-date maxima are tied
in 2018 and 2020 at 20 records each, with 19 undated records kept separate. The
configured before-2020/from-2020 comparison yields 58/36 TotalEnergies source
records, plus 19 undated records unassigned to either period. The raw source keys
remain separate; CERAWeek and other non-company categories are not silently
reclassified or deleted.

This prepared reference has not evaluated the application response, obtained
independent semantic review or established customer acceptance. The current
source count is not an advertising-market total. Later source changes require a
new observation and reference; the files above are not overwritten.

## Application/tool reconciliation

`scripts/check_statistics_reference.py` checks the frozen reference against
actual statistics, matrix, browse and graph tools using read-only connections.
Model access and vector connections are prohibited. Each selected record ID
and version is compared, including empty cells; statistics tools' ten-record
examples are not treated as complete membership. The complete members are
checked through the actual browse path. MCP graph pages retain typed edges and
source witnesses. Date checks include every highest-year tie and both period
endpoints.

```powershell
.\.venv\Scripts\python.exe scripts/check_statistics_reference.py `
  --reference .runtime/statistics_reference_20261005/current `
  --output .runtime/statistics-reference-check-new
```

On 6 October 2026 UTC, saved observations passed 1,844 engineering assertions:
all 160 cells, 35 source-defined relationships, 53 graph pages covering 263
countable records, and 29 date scopes matched the independent reference. Source,
index and ledger fingerprints matched before and after collection. The receipt
is private at
`.runtime/statistics_reference_20261005/application_check/validated/receipt.json`.
Separate read-only snapshots were used, not one global database transaction.

This is a backend/tool check with explicit source keys. It did not evaluate
natural-language interpretation, generated answers, browser node/edge clicks,
semantic gold or usability. M01/M02/M05 quality scores and customer acceptance
remain pending. The preparer observation above and its hashes remain preserved;
the later check does not retroactively approve source policies.
