# Historical social labels: details and exploration

Local implementation, 6 October 2026. This view supports the existing social
exploration task (RQ5). It is a team implementation choice, not a new client
requirement to classify posts. Real social admission, deployment and user
evaluation remain pending.

## What users can read

An admitted social record shows its source account, platform, company affiliation
and date. Company affiliation does not establish paid sponsorship. The page shows
the stored post text and a separate historical-label section. It does not request
native CLAIMS2 results for a social post.

The existing `get_record_sources` tool returns the same
`social_historical_annotation` view within the caller's current selection. This
adds no tool, table, model call or external lookup. Native record details and
native annotations retain their existing behavior.

## The source scheme

The supplied export uses `claims-social-export-v1`. Its 13 original keys comprise
two broad messaging codes and 11 subcodes:

| Level | Source keys |
| --- | --- |
| Broad codes | `green_binary`, `fossil_fuel_binary` |
| Green subcodes | `decreasing_emissions`, `renewable_energy`, `other_viable_solutions`, `false_solutions`, `recycling_waste_management`, `nature_conservation_references`, `broad_environmental_concepts`, `green_policies_politics` |
| Fossil fuel subcodes | `fossil_fuel_explicit`, `petrochemicals_other_ff_derivatives_and_industry`, `fossil_fuel_implicit` |

The original documentation describes positive or neutral green/fossil-fuel
messaging. It does not supply a complete per-subcode manual or a verified
greenwashing judgment. Labels may overlap; their counts cannot be added to obtain
a post total. The interface preserves source keys and does not map them to native
labels or CLAIMS2.

| Displayed state | Meaning |
| --- | --- |
| Source export: True | The applicable historical export explicitly recorded the boolean `true`. |
| Source export: False | The applicable historical export explicitly recorded the boolean `false`. This is not a reviewed negative or proof that greenwashing is absent. |
| Unknown | No single usable historical annotation is bound to this stored post text. Missing fields are not converted to False. |

The scheme remains `historical_automatic_unverified`, including when all file and
text checks pass. Historical model explanations are shown separately from the
post, in a disclosure section. They are not source quotations or new findings.
Only three known explanation fields are exposed; long text is explicitly marked
as truncated after 2,000 characters.

### Storage of original control characters

Ten supplied records contain U+0000 in historical generated explanations.
[PostgreSQL rejects that character in text or JSONB](https://www.postgresql.org/docs/current/datatype-json.html).
The social adapter
escapes it as a visible literal `\u0000` in these three explanation fields only.
The record page and source-tool projection flag this display representation.
Post text, label booleans and admission flags are unchanged.

For affected rows, `raw.source_row` is an explicit storage projection. Exact
original explanation strings are retained in
`raw.source_string_storage.original_json_strings`, under scheme
`json-string-nul-v1`. Decode each saved value with `json.loads`; never reverse
the display text by replacement, because an original may also contain a literal
`\u0000`. The supplied archive stays unchanged. Other fields containing U+0000
are rejected before import instead of silently cleaned. Import also checks
mutated records and report fields before opening a database connection.

## Binding and public projection

1. Read an active, countable current record. MCP also retains all trusted filters.
2. Select exactly one annotation of the social scheme from that current version.
3. Match the stored body's SHA-256 and the annotation's body hash. Require the
   original status, identity basis, source hash, positive source-row number and
   unchanged taxonomy marker.
4. Require all 13 actual JSON booleans and agreement with the preserved positive
   list. Do not coerce strings or numbers, infer macro values, or transfer a prior
   text's annotation to new text.
5. Return only known code states, bounded explanations and safe provenance.
   Raw imports, filesystem paths and arbitrary annotation fields are omitted.

`validation_state` describes these engineering checks: `bound`, `missing`,
`invalid`, `ambiguous` or `body_mismatch`. Every non-bound result has 13 Unknown
values and no historical explanation. A matched hash establishes text binding,
not classification accuracy or the truth of a claim. The source hash identifies
the recorded input; it does not independently certify the source.

## Explore a source state

The local Data Overview has a separate social source-state chart. Each of the
13 rows shows source True, source False and Unknown. Its three counts add to the
current selected-post total; a percentage uses that same total. Coverage reports
how many selected posts have a usable annotation, including all-False posts.
This chart does not add overlapping code counts into a post total or a pie.

The existing label filter uses exact IDs such as
`claims-social-export-v1:renewable_energy:source_true`. Only the social collection
accepts these 39 source-state IDs. Native labels and CLAIMS2 remain separate.
Multiple selected IDs mean **any selected state (OR)**. They do not mean that all
selected codes apply together. A question requiring an AND intersection must be
clarified; the interface does not substitute an OR count.

With no state filter, click a nonempty chart segment to open its Records. With
an existing OR selection, a click may narrow to one already selected state.
To switch to another code or state, explicitly change or clear the dropdown.
Company, source account, platform and date filters are retained. A stale chart,
changed annotation or withdrawn selection requires refreshing before clicking
or exporting; Data reads current records rather than storing a permanent copy
of the members. CSV includes the safe state IDs, scheme and unverified status,
without raw fields or historical explanations.

For MCP, `record_statistics` supports `group_by: "social_historical_labels"`
under an explicit social scope, with count, all codes and no periods or comparison
denominator. The result includes the full selected total, valid/unknown coverage,
all 13 rows and a source-state version. A state-specific count or record read
uses the same IDs in `filters.labels`. Tool requests cannot clear or widen the
trusted selection. Source-state reads check for changes before and after the
operation; missing evidence or SQL failure is unavailable, not a replacement
web count. These are readings of an old export, not new model classifications.
The web answer checks this guard again after any downstream generation and
before displaying the result. A missing, malformed or changed guard withholds
the stale answer, preserves recorded costs and audit information, and does not
replace local counts with a web result.
Saved state-filtered Query pages sign the guard's filters and source-state
version, then recheck it before and after reading another page. Equal counts or
an unchanged general health version are insufficient. These are optimistic
change checks, not a permanent membership archive or an atomic transaction
across several tool calls. PostgreSQL checks the stored JSON representation;
it cannot reconstruct numeric exponent spelling from the original import.

## Current evidence and remaining work

Read-only projection of all 37,082 prepared records found 37,082 usable source
annotations and 21,410 records with all 13 source values False. This checked
prepared file consistency only: it did not inspect an active database version,
admit records, produce new predictions or evaluate semantics. The prepared
records remain outside counts and retrieval. Receipt:
`.runtime/social_annotation_details_20261006/prepared_projection_verification.json`.

P19 added record details, public JSON and the existing source tool. P20 adds
the local distribution, source-state filters and corresponding-record chain.
P20 verification is recorded separately from the original P19 receipts.
Real social admission, deployment, usability review and semantic evaluation
remain pending. This cannot replace the reviewed 24-question native lists.

### P20 verification

The final 867-case related offline run and five actual PostgreSQL cases use fabricated
records, Dash HTTP callbacks and MCP memory protocol. The SQL cases cover all
39 states, independent code totals, corresponding records and pagination,
annotation-only changes, repeatable-read consistency and trusted tool scope.
The owned temporary schema was removed. Its 443 successful SELECT/WITH reads
and 60 statement shapes include initialization and internal reads; they are
not 443 user tasks. Catalog equality checks metadata, not shared business data.
The original P18 and P19 evidence directories retain their bytes.

An initial related run passed 866 cases and failed one cross-test import because
the runtime runner omitted the repository root from Python's import path. Only
the runner was corrected; the failure is retained. The corrected 867-case run
passed with a separate receipt and unchanged before/after source hashes. Receipts:
`.runtime/social_label_exploration_20261006/final-offline-runner-02.json`,
`final-regression-02.junit.xml`, `sql_final_01/runner.json` and `verification.json`.
The earlier whole-suite run passed 3,725 cases, with six skips and ten expected
legacy-planner failures; 121 integration/live cases were excluded. It started
before the final UI/answer fixes, so it is not a frozen final-source result.
Overlapping batches are not added together or reported as semantic accuracy.

### P19 captured verification

415 related offline checks, Ruff and three actual PostgreSQL
checks using synthetic records in a disposable owned local schema passed.
The schema was removed. The three SQL checks cover annotation reads, version
and admission changes, and the source tool's trusted selection. Receipts:
`.runtime/social_annotation_details_20261006/final-regression.junit.xml` and
`.runtime/social_annotation_details_20261006/final_sql/runner.json`.
An earlier SQL run is retained separately; overlapping batches are not added.
These checks do not establish classification accuracy, real-model routing,
customer usability or deployment. P19's per-record labels and explanations were
available in record details and MCP output; the later P20 Query distribution
table does not turn those old explanations into source evidence.

Code: [projection](../src/observatory/social_annotations.py),
[shared SQL](../src/observatory/social_annotation_sql.py),
[chart and state checks](../src/observatory/social_label_ui.py),
[public records](../src/observatory/records.py),
[record page](../src/observatory/record_view.py),
[source tool](../src/observatory/research_tools.py).

Related: [supplied input](social_archive_input.md),
[account exploration](social_account_exploration.md),
[research tools](mcp_research_tools.md),
[current plan](../plan.md).
