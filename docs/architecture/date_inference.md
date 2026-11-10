# Inferred publication dates

22 eligible native records have no source publication date. The application keeps that gap visible and adds separate, reviewable estimates; source dates are never edited.

## Evidence tiers

| Tier | Method | What it shows | Current rows |
| --- | --- | --- | --- |
| A | `url_path` | A full `/YYYY/MM/DD/` date in the article URL. Each row stores the publisher's URL-vs-source agreement on dated records (CNBC: 59 of 70 exact, 63 within 3 days). | 19 |
| B | `archive_first_capture` | Earliest archive capture; only an upper bound. | 0 |
| C | `web_search` | A dated statement found by one bounded hosted web search; the evidence URL must be one of the provider's own search sources. | 2 |

Tiers are evidence categories, not probabilities. By user decision (1 October 2026) there is no manual review step: every row is used unless someone sets `review_state` to `rejected`.

## How the application uses them

- Questions (Query page, research tools and MCP) use supplemented dates by default. The Data dashboard still charts source dates only.
- Every record returned by the research tools and MCP carries `date_basis` (`source`, `inferred:<method>` or `missing`) plus `inferred_date` and `inferred_tier`.
- Statistics answers append a server-written sentence whenever records in the result, or in a percentage's comparison group, have a supplemented date, naming the method and tier. Passage search results add `date_notice`, and generated answers append the same label, when a cited record's date is supplemented. The model cannot omit or reword these labels.

## Commands

```sh
uv run observatory migrate                                   # creates date_inferences (0004)
uv run observatory infer-dates                               # preview tier-A URL dates
uv run observatory infer-dates --apply                       # write them (idempotent)
uv run observatory infer-dates --web-search --paid --apply   # tier C for records without URL dates (paid)
```

The 1 October 2026 web search found: Southern Company "Responsibly Green" 2023-06-05 (the Washington Post page itself) and Chevron "Meet The Problem Solvers" 2025-06-23 (Chevron's own newsroom, not the New York Times page; reject the row if it proves wrong). No date was found for the AFPM article.
