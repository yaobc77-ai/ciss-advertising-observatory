# Client content review preparation

This prepares private full-context material for the client's 24 questions. It
does not create labels, reference answers, approvals, scores or published CLAIMS.
The questions have already been used in design and remain development material.

## Inputs and reuse

- [Question definitions](../../eval/customer_metrics/content_questions.v1.json)
  retain the client wording and latest PD3 paragraph IDs. Definitions and literal
  search hints are drafts requiring confirmation.
- A full source snapshot supplies exact bodies, record/version identities,
  admission flags, extraction issues and original/archived URLs.
- The preparer reuses `evaluate.load_snapshot`, canonical hashes, validated
  retrieval spans and the enforced read-only database adapter. It does not
  retrieve Top K, use embeddings or call a model.
- Existing `prepare_client_review.py` remains the separate independent-acceptance
  freezer. Its unused-question/holdout requirements must not be falsely declared
  satisfied by these development questions.

## Commands

Use a new **private** destination, such as ignored `.runtime/`. Existing output
directories are rejected; generating a packet does not update the application.

```powershell
# Read the existing database without changes or model calls.
.\.venv\Scripts\python.exe scripts/prepare_content_review.py `
  --database --output .runtime/content-review-new

# Reproduce from a full source JSON file, without a database connection.
.\.venv\Scripts\python.exe scripts/prepare_content_review.py `
  --input .runtime/private-source-snapshot.json `
  --output .runtime/content-review-replay-new
```

Database capture compares source/index and ledger observations before and after
separate read-only snapshots. It also checks stored body hashes, canonical
payload versions and record/dataset ownership. These checks
bind the observed data; they do not provide a global lock or semantic approval.
Supplied offline files retain their fingerprint but are marked unauthenticated.

## Outputs and review

| File | Purpose |
| --- | --- |
| `index.html` | Openable question index and source counts. |
| `questions/Q*.html` | Draft rules, candidate contexts, and all records without a literal hint. |
| `articles/*.html` | Complete retained body and its source/extraction metadata; links have not been checked online. |
| `review_units.csv` | Every selected record × question, initially unreviewed/unknown; fields for support, limitations, speaker, treatment, exclusion reason, reviewer and time. |
| `hint_spans.jsonl` | Literal matches with exact original Unicode `[start,end)` offsets and adjacent context. |
| `source_snapshot.json` | Private original bodies and identities, including nonselected records for scope audit. |
| `article_groups.draft.csv` | Exact normalized-body duplicate hints; near-duplicate grouping is still pending. |
| `preparation_summary.json` / `manifest.json` | Preparation scope, pending counts and file fingerprints; no quality scores. |

The current default selects active, countable **native source records**. It does
not silently deduplicate, infer paid sponsorship, merge aliases or include the
unadmitted social archive. Record count is not an advertising-market total.

Read an article once and consider multiple questions. A hint prioritizes reading;
it does not prove membership or make unmatched records negative. Missing or
partial original content remains unknown. `retrievable=True` does not prove full
extraction. Disclosure may require the original page or image. Preserve source
attribution, criticism, restrictions, and planned versus achieved outcomes. Q15
occurrence and consensus/skepticism are separate judgments.

Preserve the generated packet. Save individual reviews and adjudication as new
files, with exact source and definition versions; changing a draft rule requires
a new version and reconsideration of affected judgments. The blank CSV is a
worksheet, not an automatically validated review importer. It uses UTF-8 BOM and
escapes spreadsheet-formula prefixes; original text remains in the snapshot.

Only a fully reviewed declared scope can produce complete matching-ad gold.
Unresolved members prevent full recall claims. Actual returned IDs, answer units
and named reviews must then be bound separately through the
[metric report contract](../evaluation/customer_metric_report.md). This packet alone cannot
produce M06/M07 or semantic quality scores.
