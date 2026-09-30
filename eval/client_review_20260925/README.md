# Client review intake — 25 September 2026

**Status: pending client questions, reviewed evidence, reviewer and split approval.**
This directory contains blank intake forms, not a new benchmark or approved gold set.
The seven synthetic guard tests are software tests, not advertising research questions.

## Client input

Fill `client_intake.csv`, or give the same information in ordinary text:

- A question you actually need to answer; your role (journalist, researcher, advocate or lawyer).
- Collection, companies, media and dates of interest.
- Any known article/post links; leave blank if unknown.
- What the answer must explain and the most important mistakes to avoid.
- Where the question came from and who can review the evidence and answer.

Do not ask clients to create record IDs, quote offsets or database hashes. The team prepares
those from the current original records, then returns a readable evidence packet for review.
Do not copy existing development questions into this empty packet and call them independent.

## Team preparation

1. Map approved intake to `questions.jsonl` using the existing `EvaluationCase` format in
   `src/observatory/evaluate.py`. Keep `suite: acceptance_draft`, `dataset: native` and `status: ready`.
   Retrieval cases need exact original quotes and their record IDs; counts need the complete
   filtered record set; no-evidence cases need an agreed reason the fixed corpus is insufficient.
2. Review related articles/reprints/near duplicates and fill `article_groups.csv`. Each row has a
   stable record ID, a reviewed group ID, and `development` or `holdout`. Include all records used by
   both existing development and acceptance-draft questions, plus every proposed support record.
   A group must not occur on both sides. Exact-body checks supplement this human grouping.
3. Fill `review_plan.json` only after actual review. `approval_record` identifies the review note or
   decision; `acceptance_criteria` records the agreed rubric and decision procedure. Do not change
   Boolean confirmations merely to make the checker pass. `expected_data_version` is the exact
   `/healthz` data version of the reviewed corpus, not the source-file count or Git commit.
4. Run the readiness check and, once ready, the source check/freeze described in the
   [evaluation handoff](../../docs/PROTOTYPE_EVALUATION.md).
5. After execution, fill `answer_review.csv` with the run ID and case ID, reviewer, findings on
   source support, attribution, qualifications, completeness and usefulness, plus verdict and reason.
   Human review belongs to that exact run. An old review cannot approve a newly generated answer.

The checker cannot prove that a reviewer exists, that a task is representative or that grouping
is complete. Those declarations and near-duplicate decisions remain auditable human inputs.
There is no automatic semantic pass. Formal social and cross-dataset review remains pending
until formal data is available and the existing evaluator is extended for its released schema.
