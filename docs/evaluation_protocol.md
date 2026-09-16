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
2. 每段 gold quote 是当前原始正文的**逐字子串**，且完整落在一个接受区间内。显式 `retrieval_ranges` 优先于旧 `retrieval_end`；没有显式区间才使用前缀或全文。导航间隙两边的文字不得拼成一条 gold，即使拼接后看似通顺也无效。隔离的导航及未采纳正文不能作为可回答题 gold。引用错误、归属错误或越界会使整个运行失败，且失败发生在任何付费调用之前。
3. 检索题的必需记录当前可检索；计数题枚举集合与整个筛选集合完全一致。过期题目需要人工重审，不自动适配答案。
4. 当前 draft 使用稳定 record ID＋原句，没有把今天的版本写死成已经冻结的验收版。运行时绑定 `data_version`，解析当时 `version_id` 和原文字符偏移；逐题及结束再次核对。如中途更新数据，整个运行无效。`--expected-data-version` 可额外要求某个已记录的版本。

同一篇 biogas 广告可支持不同问题，两个草案存在来源重叠；因此验收草案当前不是按文章隔离的泛化测试。正式冻结前应由第二位审核者检查问题清晰度、必需来源是否穷尽／有合理替代来源、无证据判断与 rubric，并决定是否重新划分来源。只要调整了问题、gold、筛选、正文或可检索资格，就应重新验证和记录版本。

## 当前数据与调用结果

当前原生数据版本为 `5114ebc1cf9afe59cdaa715e3ea45166`，275收录、263可计数、226可检索、558当前块。CLI 要求 `native_admissions.json`、`native_body_ranges.json`、`native_body_recoveries.json` 三份配置及其绑定的源文件。0.2.3增加了PDF-265的有限续文；该文仍为partial，原有94项截断限制没有整体解除。

最近的付费开发记录来自0.2.4：原20题中13题运行、7题等待真实社交数据；19条生成引用可定位。另有独立两题PDF诊断；两者均待人工语义验收，不能以定位结果推出95%语义支持率。详见[0.2.4报告](../reports/quote_context_v0_2_4.md)。0.2.5仅修正Dashboard同次刷新的一致性和未知日期时间线，不改检索、生成、题库或数据，也未为此重复付费诊断。下文的数据变更及运行记录均保留其历史版本。

## 0.2.0 历史数据变更的评估约束

0.2.0当时的主库版本为 `d85a98002e4493f0376c260ad82253ee`，有275条收录、263条可计数、226条可检索及554个当前片段，媒体分组为8个。当时采用两份绑定源路径／文件哈希／逻辑行号／正文哈希的 AI 工程配置：新增候选7纳入、4排除、1待核；20处导航边界按有序原文区间采纳。当时CLI全快照要求两份配置均存在并通过校验；当前要求的三份配置见上一节。配置变动参与记录版本，旧运行不能自动当成本版本的成绩。

新增记录中2条仅元数据，可进入相应的完整筛选计数，但不能成为正文检索必需来源；正文区间修复也不得覆盖 `metadata_only` 限制。add-04 按既有 CERAWeek 范围纳入并保留未知赞助方，add-07/11 保留未知日期。最终只对新增 sponsor 使用 casefold，并作精确 `WSJ`→`The Wall Street Journal` 媒体简称映射，raw 保留原始拼写，不自动合并公司别名；keyword 保留源数据字面值与大小写。这些规则影响对应筛选集合，因此评估前仍须重新核对所有完整计数集合，不静默修改 gold。

区间修复后每段分别分块，字符偏移和段落 ID 指回原始正文；评估器的单区间 gold 校验与该合同一致。20处导航审核是 AI 工程采纳，不是人工语义验收；94处疑似截断、源文缺失列表和被截断的结尾仍未恢复。对现存片段的命中不能支持“完整文章没有提到某事”或“全文已核实”的结论。

[开发运行 `532453a7c43740ecbe5f4954d3522f41`](../outputs/development_reviewed_paid_final_20260916.json)绑定的是媒体简称对齐前的 `c5ad20ac2938e619e11fe1f8bfc26b97`，不是当前版本；其中3道英语题产生西班牙语／法语回答，按诊断保留。运行汇总以[评估报告](../reports/evaluation.md)为入口，不能把机械定位通过、检索命中或 AI 辅助审阅当成人工语义验收。初次结构迁移275个新版本、后续大小写修订7个新版本及各次275条 unchanged 是导入重复性证据，不是模型或标注质量指标。详见[数据合同](data_dictionary.md)。

## 免费运行是默认值

```powershell
.\.venv\Scripts\python.exe -m observatory.evaluate --cases eval/development.jsonl
```

这只调用 `Service.search` 的词项检索和 `Service.statistics` 的完整筛选计数，**不创建 embeddings、不调用生成 API**。原生无证据题可以记录检索行为，但“检索为空”不等于模型正确拒答：拒答率和生成引用指标标为 `not_run_lexical`，其分母为 0、rate 为 null。

结果默认保存到 `outputs/evaluation-<suite>-<run_id>.json`；可传 `--output` 指定新文件，已有文件不会覆盖。结果包括题库 SHA-256、数据版本、运行模式、逐题证据及当时 gold 定位信息，便于复核。

从 0.1.1 的审计修订起，新运行在 `implementation` 中记录提示哈希（仅付费模式）及 Python 模块文本哈希。模块哈希基于读取后的文本，换行按 Python 文本读取规则统一，不是文件原始字节哈希。成功生成的用量账本另在 `usage.observatory_request` 保存提示、动态输出 schema 的哈希，以及供应商返回的模型名。结果文件应与对应账本一起保留；旧输出不回填这些字段。2026-09-16 的 citation-first 开发运行早于此审计修订，其原始 JSON 保持不变。

## 付费运行必须显式开启

```powershell
# 手动开启付费诊断；普通测试和免费检索不会执行这类调用。
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
| language_check_statuses | 付费 ready 检索题逐题列出 match／mismatch／inconclusive／not_checked 数量；只检查生成的 claims，原文引文不参与。采用本地启发式，不能作为语义或人工通过率。短文本不确定项仍在分母中，不能并入 match。 |

**可定位引用不等于语义支持，更不等于广告主张真实。** Runner 不自动给出整体通过结论：`overall_pass` 为 null。也不自动为 social/cross 建立通过状态。

0.2.1 增加 Lingua 2.2.0 本地语言检查：少于 20 个 Unicode 字母，或前两候选分数差低于 0.20 时不确定。这两个阈值是工程策略，未作概率校准。明确的提问语言写入每次生成的 system 提示；逐条与合并 claims 均检查，出现明确不一致返回 `service_unavailable / answer_language_mismatch`，不作资料不足，不自动重试。原始结构化模型输出与已结算费用保留，公开回答只保留证据和状态。不确定输出仍可能展示并记录 inconclusive；混合语言及不在库内的语言不能保证识别。

从 0.2.1 起，运行级 `implementation.base_prompt_sha256` 表示公共提示模板；每次调用的账本 `observatory_request.prompt_sha256` 则对应包含目标语言的实际 system 提示，另记 base_prompt_sha256、target_language、language_policy。两者不混称相同提示。原有结果文件不回填。

`support_passage_coverage` 是严格的原句召回诊断：拆在两个片段中的原句、改写或部分匹配均不计覆盖；逐题的 `support_passage_matches` 保存覆盖它的 evidence ID。覆盖率高只说明这些已选原句可供回答使用，不证明模型实际使用了它们或正确保留了限定条件；覆盖率低也不能排除其他片段提供了有效的替代证据。最终仍需对照全文与 rubric 做人工语义评审。

## 定向恢复检查与正式题库

0.2.3 的 `eval/pdf265_recovery_smoke.jsonl` 是两道限定到一篇文章的维护冒烟题，复用同一 runner。它的 `suite=development` 仅表示开发诊断模式，不属于原 `eval/development.jsonl` 的 20 题，也不替代 20 题验收草案。其支持原句在调用前固定，结果单独保存为 [PDF-265 smoke](../outputs/pdf265_recovery_paid_smoke_20260916.json)，绑定 `5114ebc1cf9afe59cdaa715e3ea45166`。定位有效仍不能掩盖回答中的主体措辞问题，见 [恢复报告](../reports/pdf265_body_recovery.md)。本轮没有重新调用原开发题或验收草案的生成接口。

`tests/test_body_recoveries.py` 另外检查源 PDF／抽取文件漂移、页终止符与映射错位、旧标签依据、部分正文质量门槛，以及一个失效决定不能导致同批其他恢复半生效。测试用合成材料，真实数据的定位和旧引用保留另见发布记录。

## 测试与接下来的复核

`tests/test_evaluate.py` 用隔离的内存单元测试验证费用开关、引用归属、全部必需 ID 的命中规则、数据中途变更、pending 处理、计数集合过期，以及“原句可定位但回答语义错误”不能自动通过。这些人工小夹具**不是验收语料**。

多片段回归测试另检查：第 15 个片段的引用仍有效、同记录片段不挤占五个记录名额、第六个不同记录不计 hit@5、支持原句的归属／完整包含／版本要求、失败题保留覆盖率分母，以及共享短引文上限。

`tests/test_retrieval_ranges.py` 另覆盖显式区间优先、原文坐标、独立区间分块及 gold 不跨间隙；`tests/test_admissions.py` 与 `tests/test_body_reviews.py` 覆盖源文件／正文／行号变化、重复或失效规则、必需配置缺失，以及区间修复不能开启明确仅元数据的记录。测试夹具仅验证程序行为，不是人工金标准。

本阶段完成真实题库及程序前置校验；实际开发集运行和人工语义评审应分别记录。验收草案未冻结，任何试运行都只是诊断记录。

历史前置核验（0.2.0之前，2026-09-16）：数据库版本 `652ed975bbd44ea06e20af19b6a6642d`；development 的15段、acceptance draft 的17段原句归属、逐字匹配和当时 `retrieval_end` 范围全部有效，四道计数题的完整筛选集合一致。该次只读取原文和元数据，没有对 acceptance 执行检索或生成；当时评估程序的15个单元测试通过。这些数字保留为原快照证据，不代表当前版本已经冻结或正式验收。

后续区间修订的[只读核验记录](../outputs/source_revision_validation_20260916.json)绑定中间版本 `b5b03ce0e60a1fccd003e1056236ad85`：development 15段、acceptance draft 17段原句定位通过，并检查79个历史证据定位及554个当前片段。该记录早于最终casefold修订，也保持原版本，不回填成最终版本核验。

媒体对齐中间版本 `612e20bbef3d0910ba94c0e4be84d10e` 的[只读核验](../outputs/source_revision_validation_final_20260916.json)另外确认：275条原始正文保持一致、554个片段与79个历史证据可定位、development 的15段和acceptance draft 的17段原句仍有效。该记录早于最终 keyword 源拼写恢复，不改写成当前版本验证；它不执行验收题的生成、不冻结草案，也不给出人工语义通过结论。
