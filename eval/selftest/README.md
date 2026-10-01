# Self-made regression set

24 statistics questions and 7 retrieval topics (each asked in English, Chinese and as an English paraphrase), written outside the Observatory code in `cases.json`.

Gold answers are never stored as numbers. `scripts/run_selftest.py` recomputes them on every run with independent SQL over the same active, countable records, so the set stays valid when the data version changes. Retrieval gold is every retrievable article whose current text contains the case's `gold_phrase`; a variant passes when one of them is in the top five distinct records.

## Runs

| Part | Command | Cost |
| --- | --- | --- |
| Case format and rule-planner scopes (CI) | `pytest tests/test_selftest_cases.py` | none, no database |
| Rule planner + database statistics, keyword search | `python scripts/run_selftest.py` | none, needs the database |
| Research agent answers, hybrid search | `python scripts/run_selftest.py --agent --hybrid --paid` | about $0.006; paced to the per-visitor rate limit (about 6 minutes) |

Results are written to `outputs/selftest-<timestamp>.json` and never overwrite an earlier run.

`rules: "gap"` marks a question the rule planner is known not to handle. The CI test treats these as strict expected failures, so fixing one fails CI until the case is changed to `"pass"`.

## Results on 2026-10-01 (data `f19d4d69…`)

| Path | Before fixes (2026-09-30) | After fixes |
| --- | ---: | ---: |
| Rule planner (fallback path) | 13/24 | 13/24 (unchanged; not part of the fixes) |
| Research agent (live path) | 21/24 | 23/24 |
| Keyword search, en / zh / paraphrase | 6/7, 2/7, 1/7 | same |
| Hybrid search, en / zh / paraphrase | 7/7, 5/7, 2/7 | same |

Fixed: a quoted English title made the language guard reject an English answer; rate limits were reported as an outage; the research tools did not recognise publisher aliases such as "nytimes.com"; a clarification exposed an internal tool name.

Remaining: the research agent sometimes cannot resolve a full legal name ("Exxon Mobil Corporation"), so the same question can pass on one run and fail on the next. Neither path computes percentages. Paraphrased questions without the source's wording are rarely retrieved.

These are engineering checks, not semantic answer review or client acceptance.
