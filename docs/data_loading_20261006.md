# Data page loading checks

> Current data scope (2026-10-06): the local social collection contains 36,182 unique posts, all with searchable saved text. AFPM's 745 posts are an account-filtered subset used for interaction and performance checks, not the collection total. The 743 searchable / 2 paused AFPM figures below describe the earlier test snapshot; AFPM now has 745 searchable posts. See [full collection retrieval](all_social_posts_retrieval.zh-CN.md). These updates have not been deployed.

Date: 2026-10-06. Local development build; not deployed or client accepted.

## What changed

Only the active collection on the Data page reads dashboard statistics. Query,
Evaluation and hidden collections do not run that dashboard callback.

For company social posts, changing the page, sort order or page size reads the
requested records without rebuilding every chart. Reuse requires a signed
server selection that matches the current filters, chart metric, data version,
historical source-state fingerprint and total. Browser state alone is insufficient.

The requested page is checked before and after reading its rows and attachment
metadata. A change refreshes the first page and full statistics. Full reads also
check their source state; they retry once and withhold results if it keeps changing.
Missing annotations remain unknown. Service failures do not appear as invalid dates.

## Actual local measurements

Same local database, real Service and Dash HTTP callback, AFPM account, no date
restriction, unknown dates included, 20 rows per page. There were 745 unique
posts in the selection. One run per condition; startup is outside these timings.

| Callback | Before | After | SQL executions before / after |
| --- | ---: | ---: | ---: |
| First AFPM selection | 14.403 s | 17.966 s | 25 / 38 |
| Next AFPM page | 9.830 s | 6.724 s | 23 / 17 |
| Hidden social collection after selecting native | 8.442 s | 0.000647 s | 17 / 0 |

The first selection became slower because its concurrent-change checks read
additional state. It still builds all charts for the active collection. This
change improves paging and avoids hidden work; it does not resolve initial-load
latency or establish production performance.

The first 20 and next 20 record IDs, in order, match the before-change results.
The hidden callback now returns HTTP 204 without database access. Database
health and source/index versions did not change. All profiling connections were
read-only; no model or external search was called.

## Verification and limits

- Related UI checks passed in batches: 148 distinct cases. The final focused
  run passed 26 cases, overlapping the broader run. These are engineering tests.
- Tests cover exact filtered members, hidden pages, unchanged charts during
  paging, missing or forged browser state, changed annotations and versions,
  one-time and continuous updates, withdrawn data and private error handling.
- Independent review examined the final source guards. Concurrent-update
  scenarios use synthetic fixtures; no real corpus was changed to test them.
- Original-post counts do not establish paid-advertising status. Historical
  annotations do not establish greenwashing or answer accuracy.

Private receipts are retained locally under
`.runtime/delivery_followup_20261006/performance/`: `before.json`, `after.json`,
`verification.json` and the bounded profiling script. They are not included in
the public source package.

## Earlier plan before the P32 follow-up

Measure initial-load queries separately, then defer views that are not visible
or simplify expensive reads while retaining the same members and version checks.
Compare multiple runs and larger selections before making a performance claim.
Public release remains pending the user's release instruction.

## First-load diagnosis after typed-media integration

A separate read-only run on 6 October 2026 measured one first Dash HTTP callback
with a fresh local test client per scope. App construction and the initial
baseline health read are outside these timings; this is not browser rendering or
production performance. Each callback returned HTTP 200 with 20 unique page
records. The database health, source/index versions and eight source fingerprints
were unchanged. No model, external search or business write occurred.

| Company-post selection | Unique posts | Callback, seconds | SQL executions |
| --- | ---: | ---: | ---: |
| AFPM account | 745 | 17.950 | 38 |
| Shell company field | 3,137 | 20.499 | 38 |
| All company posts | 36,182 | 51.280 | 38 |

AFPM's first-page order matches the earlier receipt. This is a repeated diagnosis,
not a new optimization or a collection-wide member audit. Company fields do not
prove paid sponsorship or advertising status.

The full selection spends 12.529 seconds constructing historical-label counts
and 12.471 seconds checking its current source fingerprint. Both cover all
36,182 selected records. Other selected-range reads cost 3.761 seconds for groups,
3.036 for totals, 2.584 for relationships and 2.202 for months. The initial layout
reads two full-library facet queries in 3.853 seconds, and four full-library health
count reads take 3.572 seconds. Health also fetches the 36,776 current chunk members
four times to verify the index manifest. This does not mean every aggregation
reparses all annotation fields: unused projections can be pruned when no historical
label filter is present.

At that diagnostic stage, the proposed next implementation was to combine dashboard aggregations within the
existing read-only snapshot, sharing a narrow, fully filtered metadata projection.
Only the requested page should expand detailed public source fields. A full-width
materialized projection could do more work and is not the proposed change.
Preserve repeatable-read consistency, exact filters and members, signed reuse,
current versions, complete annotation fingerprints and final change checks.
Then measure whether source-state parsing can be computed once per version while
retaining every unknown state, candidate count and fingerprint byte. Facet loading
is a later opportunity; data-version-only caching would not protect mutable
annotations.

Private evidence is `.runtime/first_load_profile_20261006/profile.json`,
`analysis.json` and its README. Each scope was measured once, with a 30-second
per-SQL timeout. Multiple controlled before/after runs and member/statistic
equivalence are required before claiming a speed improvement.

## First-load optimization: verified local follow-up

P32 now shares one narrow, fully filtered projection for totals, groups,
relationships, dates and label counts within the existing read-only snapshot.
Detailed public source fields are expanded after selecting the requested page.
Historical social annotations are checked in batches, computing the body hash
once per selected version while preserving every original filtered member.
Missing, duplicate, invalid or stale annotations remain Unknown. The final
source-state check, full fingerprint, signed selection and change retry remain.

### Repeated measurements

The frozen P34 installation and current source used the same Python interpreter,
dependencies, local database and 20-row Dash HTTP callback. Each range has three
paired runs; the execution order alternated. Startup and verification reads are
outside the timing. The database cache was not reset, and prechecks warm it.
These figures measure server callbacks, not browser rendering, a cold database,
production performance or client usability.

| Company-post selection | Unique posts | Before median (range), seconds | After median (range), seconds | SQL before / after |
| --- | ---: | ---: | ---: | ---: |
| AFPM account | 745 | 18.016 (17.984–18.656) | 12.972 (12.812–13.118) | 38 / 30 |
| Shell company field | 3,137 | 20.426 (20.348–22.339) | 13.712 (13.647–14.156) | 38 / 30 |
| All company posts | 36,182 | 51.898 (50.877–52.670) | 26.367 (25.972–26.815) | 38 / 30 |

All nine paired comparisons preserve the complete normalized Service and Dash
outputs, exact ordered page records, complete scope members and source state.
Only dictionary-key order, a fresh visitor ID and cookie signing bytes are
normalized; raw responses, decoded selection guards and cookie attributes remain.

Eight additional ranges preserve complete Service outputs: native, both
collections, an empty selection, native label/date filters, social True/date/
account/platform filters, the corresponding Unknown selection, title sorting,
and Shell's clamped last page. Those are correctness checks, not extra performance
samples. All 11 distinct ranges retain current versions, members and source
fingerprints; no business data changed.

### Engineering checks and retained failures

- The parent regression passed 218 selected offline cases; 20 opt-in SQL cases
  skipped there and 12 write-integration cases were deselected. A separate
  PostgreSQL-enabled run passed 112 cases across the two new test files: 100
  read-only SQL cases and 12 offline contract cases; nine overlap the first run.
  These are engineering checks, not semantic scores.
- The annotation fixture compares the old and new PostgreSQL output text for
  counts and fingerprints, including invalid values, duplicate schemes, stale
  bodies, mixed collections and repeated members. The paging fixture confirms
  only 20 detail projections for its synthetic 47-row scope. This execution-plan
  check is fixture evidence, not an actual-corpus plan claim.
- The first harness used lowercase `shell` instead of the actual `Shell` facet,
  producing an empty scope. The failed capture is retained; definitions were
  corrected from the frozen baseline before candidate measurements. No expected
  corpus count or production filter was changed to make it pass.
- An initial synthetic fixture failed on an ambiguous SQL literal type. Adding
  `::text` repaired the fixture; production SQL was not the cause. An invalid
  division-by-zero probe failed on the old baseline too and is not a regression.
- Independent source review found no blocking issue. The parent's file checks
  reconfirmed all 87 runtime hashes, original eight reviews, fourteen historical
  reports, 24 questions and the immutable P34 archive.
- The first restart precheck used a host interpreter missing `dotenv` and stopped
  before reading health or stopping a process. The existing verified P34
  environment corrected this without installing dependencies. In the browser,
  checkbox/label mouse attempts did not select AFPM; search plus keyboard did.
  A subsequent stable-page check using native AX mouse clicks deselected and
  reselected AFPM (1→0→1) and restored the correct records. The earlier DOM
  locator failure remains an automation-entry limitation with an unconfirmed
  cause; it does not establish a broken mouse UI. No runtime change was needed.

The local 8050 application was restarted and checked with the actual AFPM
selection. It shows 745 unique posts, 743 searchable bodies and corresponding
record pages. The 8070 review program and its saved decisions remain intact.
Eight visible rows per page match retained ordered references. The grid
virtualizes rows; this browser check does not claim all 40 rows were rendered.
Health, data/index versions and unconfigured media settings remain unchanged.
No model, external search, data write, push or deployment occurred.

### Remaining work and source-package boundary

Full-library facets and health/index-manifest reads still contribute to initial
loading. Measure and revise them separately without weakening source guards.
Production and independent usability measurements remain pending.

P34's 634-file archive and 613 installed checks remain evidence for their frozen
typed-media source. This optimization changes `db.py` and
`social_annotation_sql.py`, adds two test files and adapts two existing test
stubs after that capture. A new
source freeze and install check are needed for the latest handoff; the old package
and receipts have not been overwritten.

Private receipts: `.runtime/dashboard_optimization_20261006/paired_02.json`,
`baseline_extra_02.json`, `candidate_extra_validation_02.json`,
`.runtime/dashboard_root_review_20261006/final_verification.json`,
`readonly-final.xml` and `local_activation.json`. Public release still follows D08.
The later `mouse_interaction.json` and `afpm_mouse.png` retain the native-mouse
follow-up without overwriting the earlier interaction observations.
