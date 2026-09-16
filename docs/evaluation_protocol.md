# M6：开发评估与验收草案

两个题库各 **20 题**：10 个原生广告支持题（8 个检索／解释题、2 个完整筛选计数题）、4 个社交媒体题、3 个跨数据集题、3 个原生广告无证据题。当前每组 **13 ready、7 pending_social**。没有社交媒体实料，因此这 7 题不执行、不评分，也不以零条、假数据或原生广告代替。

- `eval/development.jsonl` 用于开发诊断。
- `eval/acceptance.draft.jsonl` 是**验收草案**；尚未经独立人工审阅、冻结或预注册，不能称正式金标准、独立测试集或正式验收成绩。
- 题库包括 CCS、biogas、项目规划／已实现结果、成本与技术限制、政策、循环利用、中文提问、多文章比较、媒体＋赞助方＋日期／历史标签的组合筛选。模型本身不是研究对象，不进行模型排行榜或自动微调。

## Gold 的来源和边界

支持题先对整个 PostgreSQL 原生记录库进行 SQL 内容／元数据定位，再读取原始 `record_versions.body` 中的明确支持句；没有调用检索 top-k 产生或修正 gold，也没有使用 LLM 的现成回答反推 gold。计数题从整个库按相同筛选条件枚举全部记录，保存完整 ID 集合。

每行包含：`id`、`suite`、`dataset`、`status`、`case_type`、`question`、`filters`、`required_record_ids`、`support_quote`、`expected_count`、`rubric`、`selection_note`。`support_quote` 是 `{record_id, quote}` 列表，支持一题多来源。检索题每个 required ID 至少有一个确切支持句；无证据题的引用若存在，只是解释其前提和证据边界的锚点，不是问题已经可回答的正例。

运行前会验证：

1. record ID 存在且属于指定数据集和完整筛选集合。
2. 每段 gold quote 是当前原始正文的**逐字子串**，且完整位于当前 `retrieval_end` 接受范围内；隔离的导航／截断区不能作为可回答题的 gold。引用错误、归属错误或越界会使整个运行失败，且失败发生在任何付费调用之前。
3. 检索题的必需记录当前可检索；计数题枚举集合与整个筛选集合完全一致。过期题目需要人工重审，不自动适配答案。
4. 当前 draft 使用稳定 record ID＋原句，没有把今天的版本写死成已经冻结的验收版。运行时绑定 `data_version`，解析当时 `version_id` 和原文字符偏移；逐题及结束再次核对。如中途更新数据，整个运行无效。`--expected-data-version` 可额外要求某个已记录的版本。

同一篇 biogas 广告可支持不同问题，两个草案存在来源重叠；因此验收草案当前不是按文章隔离的泛化测试。正式冻结前应由第二位审核者检查问题清晰度、必需来源是否穷尽／有合理替代来源、无证据判断与 rubric，并决定是否重新划分来源。只要调整了问题、gold、筛选、正文或可检索资格，就应重新验证和记录版本。

## 免费运行是默认值

```powershell
.\.venv\Scripts\python.exe -m observatory.evaluate --cases eval/development.jsonl
```

这只调用 `Service.search` 的词项检索和 `Service.statistics` 的完整筛选计数，**不创建 embeddings、不调用生成 API**。原生无证据题可以记录检索行为，但“检索为空”不等于模型正确拒答：拒答率和生成引用指标标为 `not_run_lexical`，其分母为 0、rate 为 null。

结果默认保存到 `outputs/evaluation-<suite>-<run_id>.json`；可传 `--output` 指定新文件，已有文件不会覆盖。结果包括题库 SHA-256、数据版本、运行模式、逐题证据及当时 gold 定位信息，便于复核。

## 付费运行必须显式开启

```powershell
# 这条命令会使用项目的付费 API 与预算限制；不是本次准备工作已执行的命令。
.\.venv\Scripts\python.exe -m observatory.evaluate `
  --cases eval/development.jsonl --paid
```

`--paid` 对 ready 的检索／无证据题调用 `Service.answer`；计数题仍由完整筛选统计处理，不让模型编造全库数量。社交／跨库 pending 题始终跳过。预算、频率和并发限制沿用项目 Service，限流／服务失败会如实进入结果，不能从分母中悄悄剔除。

结果保留并汇总 `failure_reason`，例如引用校验失败与接口失败分别记录；二者都不当成正确拒答。

当前免费检索最多返回 5 个不同记录、每记录 1 个片段。付费回答可为排名前 5 个不同记录各返回最多 3 个片段，总计最多 15 个。评估器保留并校验 **全部返回片段**；`hit_at_5` 按返回顺序去重后的前五个 record ID 计算，不把同一文章的多个片段当作多个排名位置。结果分别保存全部片段的 `retrieved_record_ids` 与 `top_five_distinct_record_ids`，便于核查。

短引文词数上限与生成端共用 `rag.MAX_QUOTE_WORDS`，当前为 60，运行结果记录实际数值。生成端优先按完整句子选取引文；评估器仅检查返回引文是否符合共享长度上限和原文定位，不把保留句子或增加片段数量自动视为语义正确。

每次调用使用独立 evaluation visitor 标识，读取 `usage_ledger` 统计查询 embedding＋生成的已结算费用以及未决预留金额。`Answer.cost_usd` 另外保留，不能独自冒充全部费用。若账本读取失败，记录 cost unavailable 和未知题数，不宣称付费运行成本为零。

## 指标分别意味着什么

每个数据集范围 native、social、cross 单独列出题数和分母，不合并文章与帖子单位。

| 指标 | 分母与解释 |
|---|---|
| hit@5 | ready 检索题数；按返回顺序去重后的前五个记录必须覆盖 **全部 required_record_ids** 才命中。一篇命中不能替代双来源比较。记录命中不证明返回的具体片段已经回答问题。 |
| support_passage_coverage | ready 检索题的 `support_quote` 原句数；同一 record 的任一定位有效、版本有效的返回片段完整包含原句才计覆盖，每段 gold 原句最多计一次。逐题和按数据集均提供 numerator／denominator／rate；检索失败仍保留原句分母。检查全部返回片段，独立于 hit@5 的记录排名限制。计数题、无证据题的前提锚点以及 pending 不进入分母，无分母时 rate 为 null。 |
| count_exact | ready 计数题数；完整筛选记录数与预先枚举的 gold 数一致。这里数的是数据记录，不是已经核实的独立广告数量。 |
| evidence_locator_valid | **全部**实际返回的证据片段数；核验 chunk、record、version、字符位置及原文，不截断为前五个片段。 |
| citation_locator_valid | 付费回答实际产生的引用数；对照全部返回片段核验 evidence ID、原文子串、定位有效及共享短引文长度上限。无引用时为 null；answered_without_citations 单独暴露，不算机械引用通过。 |
| abstention_on_no_evidence | 付费模式下 ready 无证据题数；只有 `insufficient_evidence` 计正确拒答，limited／service_unavailable 不当成正确拒答。免费模式不评分。 |
| latency/cost | 逐题墙钟延迟、已结算账本费用、未决预留和费用未知题数。pending 不产生请求。 |
| semantic_support | 始终 `pending_human_review`。必须由人对照 rubric 检查论断是否被支持、是否遗漏限制、是否把宣传说成事实。 |

**可定位引用不等于语义支持，更不等于广告主张真实。** Runner 不自动给出整体通过结论：`overall_pass` 为 null。也不自动为 social/cross 建立通过状态。

`support_passage_coverage` 是严格的原句召回诊断：拆在两个片段中的原句、改写或部分匹配均不计覆盖；逐题的 `support_passage_matches` 保存覆盖它的 evidence ID。覆盖率高只说明这些已选原句可供回答使用，不证明模型实际使用了它们或正确保留了限定条件；覆盖率低也不能排除其他片段提供了有效的替代证据。最终仍需对照全文与 rubric 做人工语义评审。

## 测试与接下来的复核

`tests/test_evaluate.py` 用隔离的内存单元测试验证费用开关、引用归属、全部必需 ID 的命中规则、数据中途变更、pending 处理、计数集合过期，以及“原句可定位但回答语义错误”不能自动通过。这些人工小夹具**不是验收语料**。

多片段回归测试另检查：第 15 个片段的引用仍有效、同记录片段不挤占五个记录名额、第六个不同记录不计 hit@5、支持原句的归属／完整包含／版本要求、失败题保留覆盖率分母，以及共享短引文上限。

本阶段完成真实题库及程序前置校验；实际开发集运行和人工语义评审应分别记录。验收草案未冻结，任何试运行都只是诊断记录。

2026-09-16 前置核验记录：数据库版本 `652ed975bbd44ea06e20af19b6a6642d`；development 的 15 段、acceptance draft 的 17 段原句归属、逐字匹配和 `retrieval_end` 范围全部有效，四道计数题的完整筛选集合一致。这里只读取原文和元数据，没有对 acceptance 执行检索或生成。评估程序的 15 个单元测试通过；这不是模型效果成绩，也不把此数据版本指定为正式冻结版本。
