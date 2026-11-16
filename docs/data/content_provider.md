# Bounded article-assessment runs

This workflow adds a real-provider path to the [offline assessment](content_assessment.md). Preparation and planning are local. Executing a plan sends selected retained articles and draft definitions to the configured model. Results remain unpublished drafts; this is separate from online RAG and historical CLAIMS results.

## What to check before a pilot

The current unexecuted three-article plan is stored privately in
`.runtime/content_provider_current_20261006/pilot_plan/`; its review note is
`../pilot_review.zh-CN.md` relative to that directory. The earlier plan in
`.runtime/content_provider_20261006/pilot_plan/` remains unchanged as historical
evidence. It is rejected by the current preflight because the shared usage-helper
source fingerprint changed. The new plan keeps the same articles, requests,
model, call settings and $0.10 cap, and requires approval of its own hash.
No real model call has been made by this workflow.

| Question | Current handling |
| --- | --- |
| Are the original pages complete? | Unknown unless separately reviewed. Full input means all retained text, not the complete original page. |
| Are the 24 definitions approved? | No. They retain the client's questions and draft rules; the domain reviewer remains TBD. |
| Can the model produce a usable result? | The pilot will check response structure, real usage, passage selection and failure handling. Offline tests cannot establish this. |
| Does a quotation support the judgment? | Exact location is checked by code. Semantic support requires separate review. |
| Is spending authorized? | A frozen plan records the articles, parameters and cap. Project approval is required before execution. |
| Does this recover video content? | No. Video placeholders follow the separate [video plan](video_recovery_plan.zh-CN.md). |

## Reused components

The provider uses the installed OpenAI SDK, existing price registry and monthly budget ledger. It reuses source/request rebuilding, strict schema checks, usage validation and original-passage materialization. No new service, database or orchestration framework is required.

The prepared packet stays unchanged. A separate run plan binds its original files and all article requests, the selected calls, code fingerprints, SDK version and fee policy. Planning does not load API credentials, construct a client or connect to the database.

## Request policy

- Model: the project's configured `gpt-5.6-luna`.
- Input: full retained body, public article metadata, draft definitions and a program-built passage catalog. Historical labels and private reviewer fields are excluded.
- Output: one strict JSON object containing all 24 judgments, using passage IDs rather than model-written quotations.
- Separate output limit: default 6,000 tokens for article assessment. The website's generation limit is unchanged.
- Fixed call settings: Responses API, reasoning `none`, `store=false`, default service tier, truncation disabled, 60-second timeout and no automatic retries. No external tools are supplied.
- Conservative input bound: UTF-8 request bytes plus fixed overhead. Calls above 272,000 estimated input tokens are rejected by this workflow.

The official [model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) were checked on 6 October 2026. Schema compliance does not prove correct judgments. Refusals and incomplete responses still need explicit handling.

## Spending and failures

The run plan records an explicit dollar cap, the selected number of calls and a conservative reservation for each call. The total planned reservation must fit the cap before execution. The existing monthly, concurrency and visitor limits also apply; a pilot does not bypass them. The plan permits at most 30 selected calls. A larger batch needs an explicit batch policy rather than rotating visitor IDs to evade the current daily limit.

On 6 October 2026 the official [pricing table](https://developers.openai.com/api/docs/pricing) listed the following standard rates for the configured model at this short-context tier: $0.20 per million input tokens, $0.02 for cached reads, $0.25 for cache writes and $1.20 for output tokens. The reservation adds a 25% margin. Actual settled cost comes from provider usage, not from the local tokenizer. This application guard is not a provider-side absolute billing limit, and it does not establish account access to the model.

| Outcome | Fee handling | Assessment handling |
| --- | --- | --- |
| Valid completed response with valid usage | Settle actual usage. | Validate IDs and source positions; retain an unreviewed draft. |
| Refusal, incomplete output or invalid JSON/schema with valid usage | Settle actual usage before parsing or validation. | Keep all 24 judgments unknown with a failure reason. |
| Timeout, missing usage or failed settlement | Retain uncertain reserved exposure. | Keep all 24 judgments unknown; stop further calls. |
| Unexpected model or pricing boundary | Retain usage and private response without guessing a lower fee. | Stop the run; require ledger inspection before another plan. |
| Input drift, absent authorization assertion or insufficient planned cap | Reject before constructing real dependencies or dispatch. | No model call. |

Each result is saved privately before the next call. A workspace execution registry records the plan hash once; copying the same plan to another directory or changing its output directory does not permit redispatch in that workspace. New plans have distinct IDs and require their own approval. This local guard does not claim to prevent an operator from deleting the registry or using another checkout.

A started or interrupted run cannot be resumed automatically. Inspect saved results and the budget ledger, then explicitly plan any remaining requests. Unknown total cost is `null`; the settled subtotal and retained exposure are reported separately. A plan hash asserts which plan an operator authorized; the CLI flag itself is not independent evidence of human approval.

## Commands

Create a new plan directory. Repeat `--record-id` for each selected article; use the real IDs from `requests.jsonl`.

```powershell
python scripts/run_content_assessment.py plan --packet .runtime/content_review_20261006/current --prepared .runtime/content_assessment_20261006/prepared --record-id RECORD_ID --max-output-tokens 6000 --max-usd DOLLAR_CAP --out NEW_PRIVATE_PLAN
```

After reviewing and approving the exact plan, execution is a separate command:

```powershell
python scripts/run_content_assessment.py execute --packet .runtime/content_review_20261006/current --prepared .runtime/content_assessment_20261006/prepared --plan NEW_PRIVATE_PLAN --approved-plan-sha256 APPROVED_PLAN_SHA256 --out NEW_PRIVATE_RUN
```

The example is not execution authorization. Configuration and credentials are loaded only by execution, and raw provider responses stay in the private run directory. Nothing is automatically imported into the source corpus, the published classification store, evaluation gold or the website.

## Coverage and next decisions

The frozen development scope remains 263 native records and 6,312 question-record slots. Unselected, missing-text, stopped and failed records remain in that scope with unknown judgments. A three-article pilot cannot be reported as classifying the complete collection or estimating semantic accuracy.

After a successful integration pilot, review source completeness, definition disagreements and selected evidence; agree a larger batch policy and independent evaluation scope. Publishing results requires separate source, classification and version decisions. The customer requirements and video-only efficiency preference remain unchanged.
