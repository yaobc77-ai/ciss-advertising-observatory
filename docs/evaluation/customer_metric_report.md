# Offline reviewed metric report contract

## Optional page integration

`evaluation_report.published_report(settings)` reads a server-selected file with
`OBS_EVALUATION_REPORT_PATH`, `OBS_EVALUATION_REPORT_SHA256`, and
`OBS_EVALUATION_PLAN_SHA256`. The file digest and separately retained plan digest
must match. Missing, oversized or invalid evidence displays an unavailable state
without file paths, raw values or substitute scores. No report is configured by
default; do not mount synthetic fixtures as production evidence.

`/evaluation` publishes aggregates, scope, limitations, dates, reviewer count and
method only. Raw packets, individual names, review records and private policy
identities are omitted. Each collection/task/source stratum retains coverage,
failed and invalid cases. Partial arithmetic is explicitly labeled as an
evaluated subset. Empty denominators stay not applicable.

The page always labels a loaded report as a frozen-run measurement. It does not
compute current code/data/index fingerprints or authenticate review authority,
and cannot establish current quality or client acceptance. Verify the original
run and reviews separately before selecting a report. Restart the application
to apply a changed selection; never overwrite history to validate a new release.

Contract: `src/observatory/metric_report.py`, format `1`, metric definitions
`customer-metrics-v1`. This engineering contract supports the methodology in
`evaluation_methodology.zh-CN.md`. It is a team methodology declaration; it is
not an approved customer acceptance baseline.

The module performs no execution, model calls, database access, file writes,
publication, or automatic conversion of development evaluation reports. It
validates declared evidence bindings and calculates results. Validation cannot
authenticate execution, reviewer authority or independence, complete semantic
inventories, source entailment, external truth, or customer acceptance. A person
must verify the original artifacts and the authority of the review records.

## API

```python
from observatory.metric_report import (
    load_metric_report,
    metric_plan_sha256,
    observation_sha256,
    source_bindings_sha256,
    summarize_metric_report,
    validate_metric_report,
)

# packet and expectations must come from separately verified real artifacts.
validated_packet = validate_metric_report(
    packet, expected_versions=current_fingerprints,
    expected_plan_sha256=frozen_plan_digest,
)
report = summarize_metric_report(
    validated_packet, expected_versions=current_fingerprints,
    expected_plan_sha256=frozen_plan_digest,
)
# Equivalent strict JSON input boundary:
report = load_metric_report(
    packet_json_bytes, expected_versions=current_fingerprints,
    expected_plan_sha256=frozen_plan_digest,
)
```

All validators raise `MetricReportInvalid`, a `ValueError` subclass, on an invalid
contract. Returned dictionaries are detached copies. JSON rejects duplicate keys
at every depth, nonfinite numbers, malformed UTF-8, invalid structures and more
than 4 MiB. Limits also cap cases (2,000), metric strata (128), planned samples
(10,000), reviews (10,000), identity lists and text lengths. No numeric or boolean
coercion is accepted. Unknown fields, including supplied scores or acceptance,
are rejected.

`metric_plan_sha256(packet)` hashes declared case identities, dataset/task strata,
producer identities, sampling description, versions, review policies and planned
units. Freeze case eligibility and task rubrics before execution. Generated
statement and citation inventories become available after generation; freeze
those inventories before review. The digest helper neither validates nor
approves the plan. Comparing an independently retained digest detects later
changes, including omission of failed cases; a digest supplied by the same
unverified packet cannot establish that the plan was frozen at the right time.

## Required packet fields

Every object uses exactly its documented fields. IDs are nonblank bounded exact
strings; they are not trimmed, aliased or case-normalized.

| Object | Fields |
| --- | --- |
| Root | `format_version`, `definition_version`, `report_id`, `created_at`, `versions`, `plan_sha256`, `sampling_description`, `limitations`, `run`, `cases`, `metrics`, `reviews` |
| Run | `run_id`, `operator_id`, `artifact_sha256`, `started_at`, `ended_at`, `versions_start`, `versions_end` |
| Case | `case_id`, `dataset`, `task_type`, `producer_id`, `execution_status`, `executed_at`, `answer_sha256`, `reference_sha256`, `source_bindings` |
| Source binding | `record_id`, `dataset`, `version_id`, `body_sha256`, `payload_sha256` |
| Metric stratum | `metric_id`, `dataset`, `task_type`, `citation_source_type`, `review_policy`, `unit_plan`, `samples` |
| Review policy | `required_reviewers`, `method`, `policy_record`, `independent_units` |
| Unit plan item | `case_id`, `unit_ids` |
| Sample | `sample_id`, `case_id`, `unit_id`, `answer_sha256`, `reference_sha256`, `source_bindings_sha256`, `value` |
| Review record | `review_id`, `reviewer_id`, `reviewer_name`, `role`, `independence_declared`, `method`, `reviewed_at`, `definition_version`, `versions`, `evidence_record`, `bindings` |
| Review binding | `sample_id`, `metric_key`, `run_id`, `case_id`, `unit_id`, `answer_sha256`, `reference_sha256`, `source_bindings_sha256`, `value_sha256`, `decision` |

`versions` has exactly `app_version`, `prompt_version`, `data_version`,
`source_data_version`, `index_version`, `question_version`, `rubric_version` and
`active_profile`. **The seven version fields are lowercase SHA-256 artifact
fingerprints, not release labels or display versions.** For example,
`app_version` fingerprints the frozen code manifest; `prompt_version`
fingerprints the frozen prompts and generation/model settings. `active_profile`
is the exact retrieval-profile identity. A separate display label must not be
substituted for a fingerprint. Start, end, report and review identities must
match exactly. Definition drift or run-time drift rejects the packet. Supplied
`expected_versions` must also match; without them the report is not checked
against the current app and corpus.

Datasets are `native`, `social`, or `cross`; source declarations additionally
allow `external`. Internal sources must belong to the case collection. A source
identity must retain the same original version and body/payload hashes across
the run. `version_id` identifies the actual original record version; it is not
the retrieval chunk ID. Hashes do not prove that external pages were captured
or that citations recover their claimed sources.

Case execution status is `pending`, `succeeded`, `failed`, or `invalid`.
Unexecuted cases have null answer hashes and execution dates. Executed cases
require the fingerprint of the actual answer/output or terminal failure receipt,
including enough evidence to recover the observed result. Reference fingerprints
identify the exact frozen reference artifact; null references stay unscorable.
`producer_id` declares the producer responsible for the tested output/reference;
review records must be independent of that producer and the run operator.
All timestamps include a timezone; execution is within the run, review follows
the run, and report creation follows its reviews.

The metric key is `[metric_id, dataset, task_type, citation_source_type]`.
Duplicate keys are invalid. M10 requires separate `article_quote`,
`structured_result`, and `external_page` strata; other metrics use null for that
field. Review binding of the key prevents reusing a support review as an
attribution review. Each unit plan includes every case in its dataset/task
stratum. Eligibility such as answerability or designated missing-information
tasks must be fixed in the task strata and rubric; the validator cannot infer
those meanings. An external frozen-plan comparison is needed to detect changes
to declared eligibility. Task, set, cost and latency metrics require one unit
per case. Statement, citation and rubric-point metrics can declare multiple
units, or an empty inventory. Empty denominators never become 100%; an
unexecuted case with an empty inventory still prevents a final result.

## Observations and review

| Metrics | `value` contract |
| --- | --- |
| M01, M02, M05, M08–M14 | Exact boolean, or null when not yet scorable |
| M03, M04, M06, M07 | `{expected_ids, returned_ids, gold_complete}` with unique exact IDs and explicit boolean completeness |
| M15 | `{latency_ms, cache_state, temperature_state, timing_boundary}` |
| M16 | `{settled_usd, ledger_complete}` with explicit ledger completeness |

All observations also permit null. Invalid runs cannot supply scored values.
M01 and M14 cannot pass operational failures; M12 cannot label a timeout as an
unnecessary refusal. Complete empty set denominators remain null. Membership
gold that is incomplete prevents a final set result even if its reviewers agree.

M15 accepts only `submission_to_usable_result_or_terminal_failure`; server-call
timing cannot be relabeled as user waiting time. Cache states are `cached`,
`uncached`, `unknown`; temperature states are `cold`, `warm`, `unknown`. Finite
nonnegative latency is capped at 10^12 milliseconds and cost at 10^9 USD per
task. Timing summaries separate successful/failed outcomes and cache/temperature
states and reuse median/nearest-rank P95 from `metric_statistics.py`. M16 uses
decimal summation of declared settled charges and includes failed submitted
tasks. Incomplete ledger samples remain visible in raw data and block a final
cost; subset costs are conditional on their explicitly shown coverage.

`required_reviewers` is a frozen team-policy integer from 1 through 5. A pilot
can require double independent source coding; measured statistics, locator
receipts, latency and costs can use one named reviewer and batch receipt audits.
There is no invented two-reviewer customer requirement for every observation.
`method` is `source_reading` or `receipt_audit`; receipt audit is restricted to
M02, M10, M15 and M16. Semantic metrics require source reading.

Each named review explicitly declares independence and supplies an audit-record
identity. One record may bind many observations, allowing a single reviewer to
audit a complete timing or usage ledger. Every binding identifies the exact
run, metric key, case, unit, answer, reference, source-version declarations and
candidate value. Compute source fingerprints with `source_bindings_sha256()`
and candidate fingerprints with `observation_sha256()`. Changes to a candidate
after review invalidate its binding, even if the answer hash stays the same.
Two aliases with the same normalized display name cannot fill a multiple-reviewer
policy; repeated decisions by one reviewer cannot do so either. These checks
do not detect undisclosed aliases or establish actual human independence.

Review roles are `independent_reviewer` and `adjudicator`, and decisions are
`agree` or `disagree` with the exact candidate. Disagreement remains recorded and
blocks scoring until the required independent reviews exist and a distinct,
later adjudicator agrees with the candidate. A disagreeing adjudication blocks
scoring. An absent value/reference or invalid execution cannot receive approval.

## Derived results and display

The display projection is the derived top-level metadata, `notice`, and
`metrics`. Metadata includes the run identity, evaluation start/end dates,
sampling description, limitations, plan digest, and declared named
`review_records` (identities, roles, method, date, audit record and bound sample
count). Review names and audit-record identities require publication authority
alongside the report. `raw_packet` is bounded audit material and must not be blindly
rendered in a public page. It can contain output/reference identities and review
records requiring their own publication decision. Integrating a report requires
explicitly selecting real reviewed material; the current pending scorecard and
old evaluator outputs are not automatically promoted.

`status` is `pending`, `partial`, or `complete`. Complete means every planned
unit is eligible for arithmetic and all included cases have executed validly;
it does not mean the result is accurate, representative, customer approved, or
accepted. `result` is null until complete. `reviewed_subset_result` may show
conditional arithmetic with mandatory coverage, never a substitute final score.
Binary rates reuse `binary_result`; Wilson intervals are suppressed unless task
independence is explicitly declared. Statement/citation/rubric and set units
cannot claim independent binomial intervals. Set rates reuse `set_result` and
micro-aggregate question–identity pairs, retaining the same ad in two different
questions as two distinct evaluation units.

Coverage fields are `planned_cases`, `executed_cases`, `pending_cases`,
`failed_cases`, `invalid_cases`, `planned_units`, `observed_units`,
`reviewed_units`, `evaluated_units`, `pending_units`, `pending_review_units`.
`reviewed_units` counts completed declared reviews; `evaluated_units` additionally
requires a usable complete reference/ledger. Thus reviewed incomplete gold is
visible as reviewed but remains pending for arithmetic. Pending execution and
pending review never become false outcomes or disappear from the plan.

`current_versions_checked` and `externally_frozen_plan_checked` report whether
the optional external comparisons were supplied. `review_policy_authority` is
always `team_methodology_declaration`, `client_acceptance` is always
`not_established`, and `semantic_truth` is always
`not_established_by_validation`. No overall accuracy or combined acceptance
score is produced. Missing metrics remain unmeasured; callers must retain the
pending definition rows for those metrics.

Tests use explicitly synthetic fixture identities and are engineering checks,
not production scores. No production result is included in this document.
