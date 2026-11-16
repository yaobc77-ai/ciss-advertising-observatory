# Current project demonstration

Prepared: 6 October 2026. **Progress review, not final client acceptance.**

This walkthrough follows the six research questions in the [latest project description](../../客户需求/06_目标基准/PD3_原文索引.json) and [Michelle's feedback](../../客户需求/02_逐条整理/EM_客户邮件逐条.md). The team suggests **8–10 minutes** for an introductory walkthrough; this is not a client deadline or an agreed usability target.

## Before the session

- Use the configured local application: [Data](http://127.0.0.1:8050/data), [Query](http://127.0.0.1:8050/query) and [Evaluation](http://127.0.0.1:8050/evaluation). Record the actual application and data versions. These local changes have not been published. The [hosted application](https://ciss-advertising-observatory-production.up.railway.app/data) has separate release evidence in the [handoff](../../docs/current_handoff.md).
- Select **Native advertising**, choose **Clear filters**, and retain **Include unknown dates** for the recorded examples below. The local reference has 275 active source records, 263 countable records and 226 searchable records. Counting and searchable-text coverage are different.
- Let the reviewer attempt each task before explaining the controls. Record assistance, failures and unperformed steps. Do not mark an unperformed task passed.
- This walkthrough uses Data, record details, Evaluation and free keyword search. **Do not select Generate answer.** Model-assisted interpretation can incur a charge even for a count question. Source reads and Data interactions do not call a model.

The [user guide](../../docs/operations/user_guide.md) explains navigation and controls; its hosted examples are dated 1 October. The [current handoff](../../docs/current_handoff.md) records the later local work. Private receipts are available to the project team and are not public customer data.

## 1. Compare volume by company and news outlet

**Question:** How can users compare the volume of fossil fuel native advertisements by company and news outlet?

1. Open **Data → Overview**. Read the current collection and filter scope.
2. Inspect the company/sponsor-by-outlet matrix. Numbers identify record counts; its color scale explains the same quantity.
3. Select the **ExxonMobil × The Washington Post** cell. Read the named selection and open its matching article titles.
4. Expand **View the complete count table**. Use **Download counts** for grouped counts or **Records → Download selected records** for individual records.

**Look for:** the selected pair's records, not only a collection total; consistent filters across the matrix, record list and exports. The default reference includes all 160 matrix cells, including zero intersections. Repeat and record any export performed during this session; the earlier export checks are not new session results.

**Limit:** these are source-record counts in the collected corpus. Duplicate-article treatment, company-only scope and sponsor identity still require review. A collection search term is not a sponsor or an article theme.

## 2. Follow specific publisher and sponsor relationships

**Questions:** Which publishers is ExxonMobil working with? Which organizations appear as sponsors at The Washington Post? How many native ads are from The New York Times?

1. Open **Data → Knowledge graph** and select **ExxonMobil → publishers**.
2. Read **Connected outlets**, the counterpart table and donut. Select **The Washington Post** in the table or donut, or use **Show supporting records for**.
3. Check the heading **ExxonMobil → The Washington Post** and its five articles. Open one title to inspect its stored text and source materials.
4. Select **Washington Post → sponsors**, then select **API**. Check **API → The Washington Post** and its six articles.
5. Select **New York Times → count**. Read the total and use **Next records** to inspect both pages of the 19-record list.

**Recorded local development checks, 6 October:**

| Selection | Selected records | Parent distribution retained beside the articles |
| --- | ---: | --- |
| ExxonMobil → The Washington Post | 5 | ExxonMobil: 15 records; Business Insider 5 (33.3%), Washington Post 5 (33.3%), New York Times 3 (20.0%), Wall Street Journal 2 (13.3%). |
| The Washington Post | 18 | API 6 (33.3%), ExxonMobil 5 (27.8%), Shell 2 (11.1%), Southern Company 2 (11.1%), AFPM 1 (5.6%), Chevron 1 (5.6%), Eni 1 (5.6%). |
| API → The Washington Post | 6 | The Washington Post's full 18-record distribution stays visible; selecting API narrows the article list. |
| The New York Times | 19 | BP 8 (42.1%), Shell 4 (21.1%), Chevron 3 (15.8%), ExxonMobil 3 (15.8%), PTT 1 (5.3%). |

The private browser receipt at `.runtime/relationship_ui_20261006/receipt.json` verifies the complete five-, six- and 19-record lists and these four distributions. The unfiltered Washington Post article list was inspected on its first page only. Percentages are rounded. These are developer checks, not independent user testing; repeat the task if the version or filters differ.

**Relationship meaning:** an entity line means **Co-listed in source records**. In **Articles**, arrows name **Source lists sponsor** and **Published in**. Associations such as API and AFPM are not companies; an event such as CERAWeek is not silently recoded as a company. The graph does not establish payment or all commercial partnerships.

## 3. Explore dates and combined selections

**Question:** How do counts change across selected dates, outlets, companies and sponsors?

1. In **Data**, choose **ExxonMobil**, **The Washington Post**, and a publication-date range such as **1 January–31 December 2022**.
2. Read the current scope, annual bars and selected matrix relationship. Open **Records** and compare the exact article list with that selection.
3. Clear the date range and inspect the **Unknown** bar. Toggle **Include unknown dates** and observe the corresponding scope change.

**Look for:** publication dates rather than collection dates; explicit range boundaries; the same records behind each view. The default reference includes 22 unknown-date records. Unknown dates must not be silently assigned to a year.

**Limit:** the direct views demonstrate filtering and annual counts. Natural-language year grouping, all tied highest years and two-period comparisons are implemented tool paths, but model interpretation and customer task performance still need evaluation. This session does not test those paths without a separately authorized model call.

## 4. Explore themes and inspect classification limits

**Question:** What themes or topics are represented where existing data supports the analysis?

1. In **Overview**, inspect **Which historical labels appear?** Read the annotation status before interpreting a count.
2. Select a historical-label bar or use **Read the labeled articles**. Open an article title and inspect its retained source text, extraction notes and available original/PDF materials.
3. Review the [24 client questions](../../docs/evaluation/rag_validation_requirements.md) and [full-article workflow](../../docs/data/content_assessment.md). Examples distinguish mentioning blue hydrogen from presenting it as a low-carbon fuel, and mentioning CCS from framing it as a climate solution.

**Current preparation:** all 263 countable native records are represented in 6,312 question–record review slots. There are 248 prepared full-text requests; 15 records lack usable text or contain placeholders. All judgments remain unknown. The private packet at `.runtime/content_review_20261006/current/index.html` preserves the retained text and pending review entries; it contains no approved results.

The [bounded provider workflow](../../docs/data/content_provider.md) has a three-article plan with up to 6,000 output tokens per article, a $0.095944500 reservation and a **$0.10 run limit**. **The exact plan is awaiting authorization and has not run.** It is an integration pilot, not a semantic benchmark or classification of the complete corpus. Outputs would remain unreviewed and held for publication.

**Limit:** historical labels are automated annotations, not verified greenwashing findings. The 37 legacy classification candidates remain on hold for source and semantic review. A missing classification is not negative. Retained full text may still be an incomplete original page; disclosure on a banner or image may be missing. Claim occurrence, article treatment and external factual truth are separate questions.

## 5. Explain the received social data and admission decision

**Question:** Which filters and visualizations are useful for exploring the fossil fuel social media dataset?

1. Select **Social advertising** and show its current **not connected** explanation. Do not describe this state as zero advertisements.
2. Open the [supplied social input summary](../../docs/data/social_archive_input.md). Explain the fields available for later exploration: company affiliation, account, platform, publication date, original post and supplied archive link.
3. Ask which of these fields and user tasks the client wants prioritized after admission.

**Received and prepared:** 37,082 Twitter source rows, 36,182 unique original post URLs and 601 repeated-URL groups affecting 1,501 rows. The export and field documentation have already been supplied; do not request them again. The 13 historical social labels are preserved separately from the native taxonomy.

**Pending:** the records have not been admitted or imported. All staged records remain outside live counts and retrieval. Supplied advertising-delivery fields are empty, so company affiliation does not establish paid sponsorship. Agree whether the intended corpus is collected company posts, verified paid ads or another named scope, and how repeated URLs should be counted. A corpus policy and targeted review can define admission; individual approval of every source row is not presumed.

## 6. Explore sources with grounded search

**Question:** How can RAG help users explore both collections while staying grounded in advertising records?

1. Open **Query**. Inspect the current collection and filters in **Tools**.
2. Enter a content term such as `blue hydrogen` and select **Tools → Search keywords**. Read titles, publication dates, collection labels and source links.
3. Expand **Read retrieved passage** and open the corresponding article. Explain that keyword results are candidates; English stemming and OR matching can match only part of a multi-term query.
4. Read the [research-tool design](../../docs/architecture/mcp_research_tools.md): the model interprets a question, constrained tools calculate statistics or retrieve version-bound sources, and content answers separate a summary from supporting evidence. A source outage, ambiguous entity and insufficient evidence are different outcomes.

**Look for:** the selected scope and exact source behind a result. Retrieval order is not a confidence score. A quotation's exact location proves traceability, not semantic support or the truth of an advertiser's claim.

**Optional branch, only after explicit model-budget authorization:** submit an agreed real question, for example “How do ExxonMobil and Shell describe their efforts to reduce emissions? Cite the relevant advertisements.” Inspect the summary, attributed evidence, limitations, selected tools, costs and record links. Record every failure. External search, when enabled and justified, must label outside sources separately and must not add them to collection counts. This script authorizes no call or search-provider expenditure.

**Limit:** real social and cross-collection retrieval remain pending admission, import and evaluation. The dual-collection source reader has engineering interfaces; this is not evidence that real social answers work. RAG candidates cannot supply a complete “Which ads…” list without a completely reviewed scope. The three-article offline assessment pilot is separate from online RAG.

## Show how quality will be evaluated

Open **Tools → Evaluation**. The page defines **16 measures** and currently displays pending evaluation, not quality scores. Expand an item to show its unit, numerator, denominator and review method.

| Measures | What to explain |
| --- | --- |
| M01–02 | Research-task correctness; every requested statistic, group, tie, period, denominator and filter. |
| M03–05 | Typed-relationship precision/recall; exact counts and supporting records after graph selection. |
| M06–07 | Matching-ad precision/recall within a completely reviewed evaluation scope. |
| M08–10 | Semantic evidence support, attribution/qualification and citation traceability are separate checks. Summary assertions and uncited facts also require review. |
| M11–12 | Correct missing-information behavior and unnecessary refusals on answerable questions. |
| M13–14 | Unassisted target-user task completion and coverage of predefined required answer points. |
| M15–16 | End-to-end waiting time and API cost, retaining failures and unresolved costs. |

Missing references, reviews and zero denominators do not become 0% or 100%. No reviewed report or public score is configured. Developer record reconciliation and selected browser checks do not certify these measures. The [evaluation method](../../docs/evaluation/evaluation_methodology.md) and [report contract](../../docs/evaluation/customer_metric_report.md) explain the frozen runs and review requirements. The 24 supplied content questions have already informed development; they are not an unseen acceptance set.

## Decisions and final demonstration still needed

**Ask the client to confirm:**

- The native and social counting units, duplicate/republication treatment, and whether associations/events belong in a company-only comparison.
- The social corpus name and admission policy; company affiliation and source-listed sponsorship must remain distinct.
- The named client/domain reviewers and who approves source completeness, content definitions, statistics and final results. Reviewer identities and deadlines are still TBD.
- Real validation questions with expected counts/lists or required answer points, supporting records and acceptable no-answer behavior. Agree the evaluation scope and acceptance targets before reporting scores.

**Final two-collection demonstration remains incomplete until:**

- The agreed social corpus is admitted and imported, with useful filters, source access and reproducible counts checked.
- Real native, social and cross-collection question paths are run under an agreed budget and frozen evaluation plan; full-context review and usability attempts are recorded.
- Any presented CLAIMS/content result has separate source, taxonomy/definition, semantic and publication decisions. Pending results remain pending rather than appearing as zero matches.
- The selected deployment, private data handoff and another implementer's reproduction are checked. Current local work and historical release receipts remain distinguishable.
- The client reviews the exact versions, outcomes and unresolved limits. Final presentation and handoff are then updated to those accepted results.

For each session task record **version, scope, reviewer, observed result, exact supporting records, assistance, failure/limitation and decision**. Preserve the failed first attempt; mark tasks not performed as **Not run**. Use [goal.md](../../goal.md), [plan.md](../../plan.md), [current handoff](../../docs/current_handoff.md) and the [requirements version comparison](../../客户需求/06_目标基准/PD3_要求与版本差异.md) for current status. The [1 October native demonstration](native_demo_v0_4_9.en.md) remains historical evidence and has not been overwritten.
