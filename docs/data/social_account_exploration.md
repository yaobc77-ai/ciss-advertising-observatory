# Social account exploration

Updated 6 October 2026. This local change supports RQ5; it does not admit the
supplied Twitter records or establish which controls users find most useful.
Engineering checks passed on the local source. Real-data and user-task
evaluation remain pending; the running services have not been restarted.

## Purpose and source

PD3-P037–039 and PD3-P060 require suitable social filters and visualizations
within the shared dashboard. The supplied export already has `channel.name`,
`platform`, `parent_entity` and publication timestamps. Account filtering is a
team implementation choice based on these fields, not a new client requirement.

## Dashboard

After admission and import, select **Social advertising** in Data:

1. Combine **Company affiliation**, **Platform**, **Account** and
   publication dates. Multiple selected values are alternatives within one
   field; different fields intersect.
2. Overview shows source-account, company-affiliation, platform and annual
   distributions. Counts and shares use the complete filtered selection,
   including records on other pages and posts without searchable text.
3. Select an account bar to retain the other filters and open its Records.
   Use the account control or **Clear filters** to change the selection.
4. Open a record for its stored text and available source references; export
   the full filtered record selection as CSV.

When there are no admitted social records, the page shows a notice and hides
empty charts. Active records whose `countable` value is false do not make the
collection available. `record_counts` retains its active-source meaning;
`countable_record_counts` reports the admitted counting scope separately.

## Query and MCP

Account choices also apply to current-selection keyword search, generated
answers, statistics, source reads and record pagination. Social member cards
show the source account name, platform and company affiliation. Changing a control
marks a saved query as stale; submit again to use the new scope. The explicit
**Both collections** option still chooses all collections rather than the
current collection's filters.

The shared `record_statistics` tool accepts `group_by: "accounts"` for a social
scope. Its complete groups are not limited to the dashboard's ten displayed
bars or the first page of supporting records. `filters.accounts` contains exact
source names. Under a trusted combined scope, a tool request must explicitly
narrow to `filters.dataset: "social"`. Native account requests are rejected.
`resolve_entity` accepts `entity_type: "account"` for source-name candidates.
Requests cannot clear or widen an active account selection.

The legacy answer path also checks collection admission before returning counts.
For a combined selection, unavailable collections are omitted and named, while
the requested scope remains combined. A zero result within an admitted
collection is still valid. Unavailable admission or a statistics read failure
does not trigger a web answer to replace the collection count.

## Engineering verification

- 594 frozen offline checks passed, covering the changed UI, tool, source,
  legacy answer and neighboring native paths. Four new account cases use the
  official MCP SDK's in-memory JSON-RPC transport; they do not test account
  requests over stdio or HTTP.
- Five checks passed against real loopback PostgreSQL using synthetic records
  in an owned schema. They cover account filters, complete groups, current
  versions, admission and trusted tool scope. The schema was removed.
- The earlier full offline run had 3,488 passes, four stale-expectation failures,
  six skips and ten known rule-planner expected failures. The four expectations
  were updated and are included in the frozen passing checks. The original
  result is retained; this is not a claim of a second complete passing run.

The [local verification receipt](../../.runtime/social_accounts_20261006/root_check/verification.json)
binds the checks to source fingerprints. Overlapping batches are not added
together. No real social data, model performance, rendered browser layout or
customer acceptance was evaluated; no commit, push or deployment occurred.

## Interpretation and remaining work

- `parent_entity`, stored in the shared `sponsor` field, is documented company
  affiliation. It is not proof of a paid advertising relationship.
- Account groups use the supplied name, not a verified unique channel identity.
  Platform filters distinguish same-named accounts on different platforms;
  same-named channels on one platform still share a name group.
- Missing accounts form `(Unknown)` within social records. Empty native account
  fields do not become social Unknown accounts.
- The thirteen supplied social label keys retain their separate historical
  scheme. The native historical-label filter and chart do not classify these
  social posts. A later [record-detail view](social_historical_annotations.md)
  exposes the original thirteen source values and explanations separately;
  P20 adds separate source-state distributions, filters and corresponding posts.
  The 594 checks and five SQL
  receipts above describe the captured account implementation, not that later
  detail or source-state exploration changes; see that guide for their evidence.
- Corpus scope, duplicate-post counting, admission, import, independent social
  question references and RQ5 user evaluation remain pending. See
  [the supplied input](social_archive_input.md) and [the project plan](../../plan.md).

The earlier [source archive](current_source_candidate_20261006.md) is a frozen
snapshot made before this change. It remains valid for its captured bytes;
it is not an installed or published version of this account feature.
