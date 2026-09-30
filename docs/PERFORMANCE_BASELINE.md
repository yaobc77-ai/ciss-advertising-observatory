# Dashboard engineering performance baseline

This baseline measures existing repository methods against **37,000 physical,
fabricated advertisement rows** in PostgreSQL. It is an engineering diagnostic,
not a customer SLA, a customer-data benchmark, or acceptance of the final product.

## Reproduce safely

Install the project with its locked dependencies. Supply `OBS_TEST_DATABASE_URL`
explicitly in the process environment, then run:

```powershell
.venv/Scripts/python.exe scripts/benchmark_dashboard.py `
  --rows 37000 --repeats 15 --warmups 1 `
  --out outputs/dashboard_benchmark.json
```

The script does not load `.env`, `OBS_DATABASE_URL`, platform credentials, or API
keys. The connection must name an `obs_test*` database and a numeric loopback
address. Every connection checks the actual server address and database name.
The script creates a fresh UUID-named schema, uses the existing migrations, and
checks ownership before dropping only that schema in `finally`. It does not clear
shared test tables or touch the application database. Each SQL statement has a
60-second timeout, and waiting for a database lock is capped at five seconds.

No models, embedding calls, HTTP requests, screenshots, or production writes are
part of this benchmark. Connections should be provided through the environment;
do not paste credentials into reports or commands that are retained in history.

## Workload and measurement

The data generator creates native records with unique IDs, 20 synthetic outlets,
200 synthetic companies, five collection terms, 2018–2026 dates, some missing
dates and sponsors, and synthetic topic annotations. Every payload and annotation
is marked synthetic. Native rows exercise the company/outlet and graph metadata
queries at the proposed scale; they are not a reconstruction of the unavailable
37,000-row Twitter export or a substitute for a social-data benchmark.

The generator builds `RecordInput` payloads and immutable hashes, then uses COPY
and SQL inserts into the real `records`, `record_versions`, and `annotations`
tables. It does not time the full import, document extraction, chunking, or vector
indexing pipeline. It runs ANALYZE before measurements, and does not add product
indexes or alter the application query implementation.

Measured methods:

| Operation | Existing method and scope |
|---|---|
| Full dashboard | `Database.dashboard`, totals, groups, full company/outlet matrix, labels, timeline and 50 records |
| Company dashboard | Same method with one sponsor filter |
| First and middle pages | `Database.public_page`, matching total and at most 50 rows |
| Field choices | `Database.facets`, distinct filter values |
| Bounded relationships | `Database.network`, at most 100 relationships plus full matching totals and truncation flag |
| Collection metadata | `Database.knowledge_map_rows`, **all** matching record identities and metadata |

Each operation receives one excluded warmup and 15 measured serial repetitions.
`read_ms` includes connection establishment, target verification, SQL execution,
row decoding, and repository-side Python transformations. `serialize_ms` measures
compact UTF-8 JSON encoding of the return value; `total_ms` includes both. Payload
bytes describe that JSON value, not a complete Dash/browser response. p50 and p95
use linear interpolation over the sorted measurements; raw samples are retained.

## Current result

The dated machine-readable receipt records actual inserted counts, repeats,
payload sizes, PostgreSQL/Python/application versions, and successful cleanup.
See [the September 30 receipt](../reports/dashboard_performance_baseline_20260930.json).

The September 30 run used Python 3.12.14, PostgreSQL 16.15 and application 0.4.0
on Windows 11. It inserted 37,000 records, 37,000 immutable versions and 37,000
synthetic annotations. There were 3,364 unknown dates, 31,714 records carrying the
synthetic retrievable flag, 20 outlets and 200 named companies. Seeding took 2.876
seconds; the full run took about 53 seconds. The receipt confirms cleanup of its
private schema and 114 verified repository connections.

| Operation | p50 total, ms | p95 total, ms | Maximum JSON bytes |
|---|---:|---:|---:|
| Full dashboard | 891.0 | 921.0 | 482,747 |
| Company dashboard | 279.3 | 305.2 | 31,203 |
| First 50 records | 313.2 | 319.0 | 22,719 |
| Middle 50 records | 246.7 | 283.8 | 22,702 |
| Field choices | 465.4 | 483.0 | 5,691 |
| Bounded company/outlet relationships | 203.8 | 213.1 | 8,185 |
| Complete collection metadata | 693.7 | 721.9 | 19,673,048 |

The full dashboard returned a matrix with 4,020 company/outlet pairs while its
record page contained 50 rows. The bounded relationship method returned 100
pairs and correctly reported truncation. The complete metadata method returned
all 37,000 identities: **about 18.76 MiB of JSON before graph assembly, HTTP or
browser rendering**. This identifies an architectural cost to measure and reduce
when building a large graph, even though the local metadata read itself took less
than a second in this fixture. These are observations, not acceptance thresholds.

## Practical limits

- This is a local Windows loopback, warmed-cache, serial workload. It does not
  measure Railway latency, concurrent users, browser layout, graph construction,
  Cytoscape rendering, network bandwidth, or independent customer tasks.
- Synthetic cardinalities, repeated body text, dates, label overlap, and metadata
  completeness are explicit fixtures. Real long text, high-cardinality fields,
  skewed companies, duplicate campaigns, and actual social fields can change the
  result. No inference about real corpus accuracy follows from these timings.
- The relationship method intentionally caps its returned list. The dashboard
  matrix and collection metadata methods have a different scope; their payload
  sizes must not be compared as if they return the same information.
- `knowledge_map_rows` returns the complete filtered collection. A fast database
  query does not establish that shipping and rendering all those records is a
  suitable large-graph design. Its payload size makes that remaining cost visible.
- Fifteen repetitions are a small engineering sample, with no controlled CPU,
  cache eviction, isolated background workload, or statistical confidence bound.
  The report makes no pass/fail latency threshold. Customer scale, acceptable
  delay, concurrency, and realistic interaction tasks still need agreement.

## Deployment configuration boundary

`railway.json` is a code configuration reference. Its presence does not establish
that the production service uses it. Effective production migration and health
configuration must be confirmed in Railway and the final deployment receipt.
Railway's current documentation gives existing Config as Code services until
2026-12-01 to migrate to Infrastructure as Code; this migration remains a tracked
deployment task. See [Railway Config as Code](https://docs.railway.com/config-as-code)
and [pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command).
