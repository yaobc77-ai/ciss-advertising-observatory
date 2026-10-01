# Inferred publication dates

22 eligible native records have no source publication date. The application keeps that gap visible and adds separate, reviewable estimates; source dates are never edited.

## Evidence tiers

| Tier | Method | What it shows | Current rows |
| --- | --- | --- | --- |
| A | `url_path` | A full `/YYYY/MM/DD/` date in the article URL. Each row stores the publisher's URL-vs-source agreement on dated records (CNBC: 59 of 70 exact, 63 within 3 days). | 19 |
| B | `archive_first_capture` | Earliest archive capture; only an upper bound. | 0 |
| C | `web_search` | A dated statement found by one bounded hosted web search; the evidence URL must be one of the provider's own search sources. | 2 |

Tiers are evidence categories, not probabilities. Every row starts `unreviewed`; set `review_state` to `accepted` or `rejected` after checking the evidence.

Usable inferences: tier A unless rejected, and any tier once accepted. Unreviewed tier B and C rows are stored as leads only: they do not date records, enter filters or appear in counts, because a web result can describe a related page rather than the advertisement itself.

## How the application uses them

- Counts, charts and filters use source dates only, unless a request sets `include_inferred_dates`.
- Every record returned by the research tools and MCP carries `date_basis` (`source`, `inferred:<method>` or `missing`) plus `inferred_date` and `inferred_tier`.
- Statistics answers append a server-written sentence whenever records in the result, or in a percentage's comparison group, have an inferred date, stating the method and tier. Passage search results add `date_notice`, and generated answers append the same notice, when a cited record's date is inferred. The model cannot omit or reword these notices.

## Commands

```sh
uv run observatory migrate                                   # creates date_inferences (0004)
uv run observatory infer-dates                               # preview tier-A URL dates
uv run observatory infer-dates --apply                       # write them (idempotent)
uv run observatory infer-dates --web-search --paid --apply   # tier C for records without URL dates (paid)
```

The 1 October 2026 web search found: Southern Company "Responsibly Green" 2023-06-05 (the Washington Post page itself) and Chevron "Meet The Problem Solvers" 2025-06-23 (Chevron's own newsroom, not the New York Times page; review before use). No date was found for the AFPM article.
