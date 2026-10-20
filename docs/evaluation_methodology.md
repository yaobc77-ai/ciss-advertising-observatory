# Customer evaluation method

Definition version: `customer-metrics-v1`, 5 October 2026. **Definitions implemented; independent results and customer acceptance targets pending.** Open **Tools → Evaluation** at `/evaluation`.

The full [Chinese methodology](evaluation_methodology.zh-CN.md) includes all formulas, task rubrics, failure rules, source requirements and evaluation steps. [The metric registry](../src/observatory/evaluation_scorecard.py) supplies the user page.

## What the metrics measure

| Customer requirement | Main checks |
| --- | --- |
| Compare volume by company and outlet | Exact statistics and scope; source-defined relationship precision/recall; graph drilldown agreement. |
| Find sponsors and publishers | Complete relationship sets, corresponding counts and exact supporting records. |
| Compare dates and selections | All requested groups, tied highest years, period endpoints, share denominators and unknown-date rules. |
| Explore supported themes | Matching-ad precision/recall; source support, attribution and required answer points. |
| Explore social media | Admitted counting scope, useful filters and views, source access and observed user-task completion. |
| Ask grounded questions across collections | Correct real question/tool path, supported statements, source limits, appropriate missing-information handling and unnecessary refusals. |

## Definitions

| ID | Metric | Definition |
| --- | --- | --- |
| M01 | Research task correctness | Fully correct tasks / executed reference-bound tasks. Errors and timeouts fail. |
| M02 | Statistics and scope agreement | Tasks with every requested number, group, tie, period, denominator and filter correct / executed statistics tasks. |
| M03–04 | Relationship precision / recall | Correct returned typed relationships / returned relationships; correct returned relationships / complete reference relationships. |
| M05 | Graph drilldown agreement | Correct node/edge selections with exact counts and record sets / evaluated selections. |
| M06–07 | Matching-ad precision / recall | Correct returned distinct ad IDs / returned ad IDs; correct returned IDs / all relevant IDs in the completely reviewed evaluation scope. |
| M08 | Statement evidence support | Distinct factual statements sufficiently supported by citations and source context / all distinct factual statements, including uncited or summary-only statements. |
| M09 | Attribution and qualification fidelity | Distinct factual statements retaining speaker, treatment, units, conditions, dates and planned/achieved state / all distinct factual statements. |
| M10 | Citation traceability | Citations passing source-type identity and recovery checks / emitted citations, reported separately for internal quotes, structured results and external pages. This does not prove semantic support or truth. |
| M11 | Missing-information handling | Correct behavior on designated no-evidence, ambiguity, unavailable-data, unreviewed-classification and tool-failure tasks / all executed designated tasks. |
| M12 | Unnecessary refusal rate | Answerable tasks incorrectly refused or called insufficient / executed answerable tasks. Operational errors fail M01 and are reported separately. |
| M13 | Unassisted user task completion | Successful target-user attempts without developer help within the agreed task time / attempted assignments. |
| M14 | Required answer-point coverage | Correctly supported predefined answer points / required points. Extra background cannot increase the score. |
| M15 | End-to-end waiting time | Median and nearest-rank P95 action-to-result/terminal-failure time, split by interaction type and success/failure. |
| M16 | API cost per submitted task | All settled model, query-embedding and web-search charges / submitted tasks, including failures and retries. Missing/unresolved ledger amounts prevent a final complete cost. |

Zero denominators remain undefined. Missing gold or reviews remain **Not evaluated**, never 0% or 100%. Deduplicate exact identities per question; across questions, the unit is a question-item pair. Show per-question results plus micro averages and explicitly scoped macro averages. Unsupported empty returns also fail the task or required-point checks, preventing refusal from inflating apparent quality.

Split compound statements into atomic propositions. Count repeated facts once within an answer; new summary assertions count separately. Mention, framing and external truth are different judgments. Published historical CLAIMS annotations are not new semantic gold. For disclosure, missing wording in retained body does not establish absence on the page/banner.

Internal quotations require record/text version, exact quote and offset. Structured statistics require frozen data, selection filters, supporting record sets and calculation receipts. External citations require URL, source identity, retrieval time and preserved supporting material; quotations must match that material. A URL alone is insufficient, and web sources must not enter collection counts. Existing internal locator checks are available; structured-result evaluation and complete external-citation checks still need implementation. Publish the three source types separately.

## Execution and publication

1. Agree counting, duplicate, entity, date, missing-data, codebook, completeness and acceptance policies with a named reviewer.
2. Independently enumerate statistics and relationships. Use full-context human review for content membership, support and attribution; preserve disagreements and adjudication.
3. Freeze versions, inputs, references and rubrics. Statistics/graph acceptance may use independent enumeration and review of the current frozen corpus. Content generalization needs genuinely unused article groups, including duplicates and republications; rewritten questions alone are insufficient. If no unused groups remain, label independent same-corpus review as such and leave cross-article generalization pending. The supplied 24 questions are already used for development.
4. Exercise actual question, graph and user paths under a fixed budget/retry policy. Retain failures. Data or index drift invalidates the run.
5. Publish numerators, denominators, pending reviews, dates, versions, task and native/social/cross scope. Independent binary cases may use Wilson 95% intervals; correlated statements, articles or users need grouped analysis rather than an independence assumption.
6. Publish acceptance only after the recorded reviewer approves the exact result and targets. No overall weighted accuracy or automatic conversion of old diagnostics to current quality.

The current page shows definitions and pending status because no real reviewed report is configured. [Arithmetic helpers](../src/observatory/metric_statistics.py) calculate rates, set comparisons and timing summaries; they do not certify human approval. The [report contract](customer_metric_report.md) validates exact run, answer, reference, source and review bindings. An optional server-selected adapter checks a file fingerprint and separately frozen plan fingerprint, and publishes aggregates only. A loaded report is explicitly for its frozen run; applicability to the current application and client acceptance remain unverified. Partial arithmetic is a labeled evaluated subset, never a final score.

[Independent statistics preparation](statistics_reference.md) enumerates complete matrix cells, relationships, dates, ties and configured periods with supporting record IDs. These are development references until the source mappings and counting policies are reviewed; they are not measured question-path quality.

One read-only application/tool reconciliation passes 1,844 engineering assertions for exact memberships across 160 cells, 35 relationships, 53 graph pages and 29 date scopes. Source, index and ledger observations remain unchanged. No model interpretation or browser interaction was evaluated; M01, M02 and M05 scores remain pending.

Existing `evaluate.py` can be reused for execution and frozen source binding. Its `hit_at_5` means **all required sources occur within the first five distinct ads**; it is not full-list recall. Its server-call latency excludes browser rendering. Database reconciliation and quote location are diagnostic checks, not semantic acceptance.

## References

Set precision/recall and task-relative relevance follow the [Stanford IR evaluation definitions](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-unranked-retrieval-sets-1.html). Separating answer correctness and citation quality is informed by [ALCE](https://aclanthology.org/2023.emnlp-main.398/); this project uses its own human source rubric rather than treating an automated evaluator as authoritative. Independent binary-rate intervals use the [NIST Wilson method](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
