# Prototype evaluation handoff

Updated: 25 September 2026. This is a runnable preparation path, not a claim of client acceptance.

## What can run now

- Existing regression tests check software behavior.
- `observatory.evaluate` runs free lexical retrieval/count diagnostics or, only with `--paid`,
  the existing generated-answer path including query embeddings and the generation model.
- The new `scripts/prepare_client_review.py` checks readiness and can freeze reviewed native
  questions, source evidence and article groups. It makes no model calls or database writes.

The existing `eval/development.jsonl` and `eval/acceptance.draft.jsonl` remain development/draft
material. Both are treated as previously seen when preparing an independent packet. Their
historical scores are not new-prototype acceptance evidence. Formal social data, independent
client questions and completed semantic reviews are still missing.

## Prepare an independent native review

Start with the blank [client intake packet](../eval/client_review_20260925/README.md).
The team collects real tasks, maps original records and quotes, prepares grouped holdouts and
obtains an actual reviewer decision before recording approval in `review_plan.json`.

From the repository root, in the existing Python environment:

```powershell
.venv/Scripts/python.exe scripts/prepare_client_review.py
```

The supplied empty packet returns exit code **2** and lists blockers. It does not connect to the
database when these prerequisites are missing. This is the expected initial result.

After completing the packet:

```powershell
# Read-only source/version check. No search, embedding or generation calls.
.venv/Scripts/python.exe scripts/prepare_client_review.py --check-sources

# Freeze only after review and source checks pass; this destination must not exist.
.venv/Scripts/python.exe scripts/prepare_client_review.py --freeze --output outputs/client-review-native-v1
```

Source validation reuses the current evaluator: required records must exist within the selected
filters, support quotations must occur within accepted original retrieval ranges, and count gold
must enumerate the complete filtered record set. The reviewed data version must remain stable.
Previously seen questions, shared article groups and exact normalized-body overlap are rejected.

`manifest.json` binds the question file, review plan, group file, previously used question files,
data version and located original evidence. It records `overall_pass: null` and
`semantic_acceptance: pending_human_review`. Freezing inputs is not passing acceptance.
The freeze directory is never overwritten. Keep future tuning work out of this held-out packet;
if it informs changes, record that use and prepare new held-out questions for independent claims.

## Run the existing evaluator

Before each run, verify the frozen input hashes and retain the manifest with the result:

```powershell
$reviewDir = 'outputs/client-review-native-v1'
$reviewManifest = Get-Content -LiteralPath "$reviewDir/manifest.json" -Raw | ConvertFrom-Json
foreach ($reviewInput in $reviewManifest.input_sha256.PSObject.Properties) {
    $reviewHash = (Get-FileHash -LiteralPath "$reviewDir/$($reviewInput.Name)" -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($reviewHash -ne $reviewInput.Value) { throw "Frozen input changed: $($reviewInput.Name)" }
}

# Free: keyword retrieval and deterministic counts. This does not measure vector/hybrid retrieval.
.venv/Scripts/python.exe -m observatory.evaluate --cases "$reviewDir/questions.jsonl" --expected-data-version $reviewManifest.data_version --output outputs/client-review-native-v1-lexical.json

# Paid: run only within an agreed API evaluation budget and repetition plan.
.venv/Scripts/python.exe -m observatory.evaluate --cases "$reviewDir/questions.jsonl" --expected-data-version $reviewManifest.data_version --paid --output outputs/client-review-native-v1-paid.json
```

The evaluator retains its existing `gold_status: draft_not_frozen` field; it does not read the new
manifest. Attach the separately verified manifest to interpret an approved, frozen-input run.
Do not rewrite the evaluator result to imply an automatic semantic verdict. A passing citation
locator proves location/version consistency, not that the quotation supports the answer.
Free and paid modes measure different paths; they are not an isolated embedding ablation.

## What remains human or pending

| Item | Team can verify | Client/domain input still needed |
|---|---|---|
| Source-grounded answer | Original quote, scope, version and failure handling | Whether the answer is supported, attributed, qualified, sufficient and useful |
| Independent evaluation | File/version hashes, known-question overlap, exact duplicates | Representative tasks, reviewed near-duplicate groups and no tuning use |
| Counts | Complete fixed filtered record set | Counting unit, sponsor/entity and date policy |
| Relationship graph | Count/record agreement and source drilldown | Whether the relations answer the intended research questions |
| Social/cross collection | Adapter tests using explicit fixtures | Formal released data and schema, scoped gold and evaluator support |
| Speed and scale | Measured workload, latency, failures and cost | Expected data size, concurrency and acceptable waiting time |

Use [answer_review.csv](../eval/client_review_20260925/answer_review.csv) to tie semantic review to
the exact run and case. Report reviewed, failed, missing and not-run cases separately. No default
accuracy threshold is invented here. Graph/interface and scale acceptance remain separate from
RAG quality; a successful page load or a fast synthetic fixture does not settle those questions.

## Offline guard tests

```powershell
.venv/Scripts/python.exe -m pytest -q eval/client_review_20260925/test_prepare_client_review.py tests/test_evaluate.py
```

These tests exercise missing approvals, source validation, leakage and freeze immutability using
synthetic fixtures. They do not contact clients, query a real database or call paid APIs.
