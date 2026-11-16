# Search and question-answering evaluation — status at 10 October 2026

Prepared for the 9 October client follow-up (Wilson, Michelle, Ned). All figures come from saved run outputs; none are estimates.

## 1. What is being measured

Three questions are evaluated separately, because a score for one says nothing about the others:

| Layer | Question | Status |
| --- | --- | --- |
| Retrieval | Does the system find the articles or posts that hold the answer? | Measured (NDCG, precision, recall, MRR, hit rate at 5) |
| Answer faithfulness | Is every statement in the answer supported by a quoted source passage? | Measured by AI-assisted review; citations are checked by the server character by character |
| CLAIMS classification | Does the system label ads with the CLAIMS categories correctly? | **Not yet tested.** Waits for the codebook and the planned CLAIMS 1.0 labels for native ads |

Two further boundaries: finding text is not the same as interpreting it correctly (for example, a planned project read as completed), and counting what ads say does not verify that the advertisers' claims are true.

## 2. Test design

Each round draws **36 new questions** from the collection with a fixed random seed, excluding every source used in earlier rounds. Questions and expected answers are frozen before the system runs; each question is asked once. Every round has the same composition: 12 single-article content questions, 6 title lookups, 4 multi-article, 4 across both collections, 6 counting questions and 4 questions the collection cannot answer.

| Round | Questions | Distinct expected sources (native + social) |
| --- | ---: | ---: |
| P60 | 36 | 34 (26 + 8) |
| P61 | 36 | 36 (28 + 8) |
| P63 | 36 | 32 (24 + 8) |
| P64 | 36 | 33 (25 + 8) |

These are samples (about 25 of 263 native ads per round), not a full-collection evaluation.

## 3. Results

| Round | Fully correct answers | First tool choice correct | Retrieval NDCG@5 | Recall@5 | Model cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| P60 | 28/36 | 27/36 | 0.75 | 0.90 | $0.18 |
| P61 | 30/36 | 35/36 | 0.80 | 0.88 | $0.16 |
| P63 | 29/36 | — | — | — | $0.17 |
| P64 | 30/36 | 32/36 | 0.86* | 0.93* | $0.16 |

\*P64 counts only the frozen expected sources as relevant; P60–P61 also graded other retrieved articles (AI-assisted). P64 figures are therefore a lower bound and not directly comparable.

**Precision@5 is low by design** (0.26–0.31): most questions have one or two relevant articles, while the system always returns five. The extra results are mostly related articles that were not part of the expected answer, not errors in the answer itself; answer citations are checked separately (citation precision 0.95 in P61).

**Cost correction.** A figure of "about $2 for 16 questions" was mentioned in the meeting. $2 was the approved spending cap. Actual model cost is about **$0.005 per question** for ordinary questions (a 36-question round costs about $0.16–0.18), and about $0.01 for a complete-list question (section 5).

Errors found in each round were fixed by changing the general mechanism (never by tuning to a specific question), and every fix was checked on the next round's new questions.

## 4. The 24 client questions

The 24 questions from the project description are kept for evaluation only. The team has read them, so they are **not a blind test**. They were run once on 9 October with frozen code:

| Outcome (AI-assisted review, not yet human-reviewed) | Questions |
| --- | ---: |
| Supported, relevant partial list | 19 |
| Correct bounded answer (e.g. "no ad claims mitigation is impossible") | 2 |
| Correctly found nothing in the collection | 1 |
| Answer in the wrong language (fixed since) | 1 |
| Relevance doubtful | 1 |

The main finding: most client questions ask **"which ads …"**, and the system listed only the five or six most relevant examples, without saying so. For questions that can be checked word for word, the share of matching ads listed was 8%–67%.

## 5. Complete lists (new, 10 October)

- For a question that only asks which ads contain a quoted word or phrase, the system now searches the indexed text of **every** ad in scope and lists each match with the sentence containing it. Measured on 16 new phrases: **100% of matching ads found**; the few extras were plural forms.
- For other "which ads …" questions over native ads, every candidate ad (the 40 most relevant, plus every ad containing a quoted phrase) is checked one by one by the model, and an ad is listed only when the server finds the quoted sentence in that ad. On new held-out questions: **89% of matching ads found, 100% of listed ads correct**, against 16% / 55% for the previous behaviour.
- Every list states how it was produced (exact text search, or AI check of retrieved passages) and that it is not a reviewed annotation. Questions about how an ad frames something cannot be scored automatically and need human spot checks.

## 6. Data checks

- The "1970" advertisement ("Meet The Problem Solvers", Chevron) has the date 1970-08-23 in the supplied file `combined_ads_12-4-25.csv`; another scrape gives 2025-06-13. The database already treats its date as unknown. The dashboard showed 1970 because it read that CSV directly; it should read the database export (provided) instead. The correct date still needs checking against the live page.
- Across all 263 native ads, the source files agree on the date for 234 (231 identical and 3 a day apart from time zones); 28 conflict. Most conflicts are TotalEnergies/CNBC ads dated November 2020 in the spreadsheets but 2015–2019 in their URLs. A chart built from the spreadsheets would show a false spike in November 2020.

## 7. Not yet done

- Human review of a sample of answers (a reviewer needs to be named).
- CLAIMS classification evaluation (needs the codebook and labels).
- Cross-platform company timelines: a read-only endpoint now gives one company's native ads and social posts per month on one axis, with undated records listed separately. Topic-level comparison waits for the codebook.
