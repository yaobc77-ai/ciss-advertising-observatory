# v0.2.4：AI 辅助内容与引文复核

**PDF-265 两题的所选引文已包含完整核心句，但 smoke-02 的技术验证主体仍写错。** 开发集的数量对象及计划状态整体可由所引文字支持，仍有引文残句、指代上下文、额外背景与来源措辞问题。不能据此宣布语义验收通过。

这是独立的 **AI 辅助审阅，不是人工验收或模型自审成绩**。[逐条 CSV](citation_review_v0_2_4.csv) 沿用 v0.2.2 的 28 列，共 21 行；`human_verdict`、`human_notes` 全部空白，不计算语义通过率、≥95% 或整体通过结论。

## 1. 运行、范围与证据边界

两个运行的数据版本均为 `5114ebc1cf9afe59cdaa715e3ea45166`。两题定向 smoke 与原开发集分开记录，不能合并成新的 22 题验收集。

| 范围 | 保存运行 | 本次阅读范围 |
|---|---|---|
| PDF-265 定向 smoke | [结果](../outputs/pdf265_quote_context_paid_20260916.json)，run `05077c5c92034712a711a4d74340683d`，`2026-09-16T19:55:41.544685+00:00`；题库 [pdf265_recovery_smoke.jsonl](../eval/pdf265_recovery_smoke.jsonl) | 2 个问题及回答、2 条引用、对应 2 个 evidence 全文，共 2,493 字符。 |
| 原开发集 | [结果](../outputs/development_quote_context_20260916.json)，run `604a225bb0d647c58b90c1982476732a`，`2026-09-16T19:56:36.534487+00:00`；题库 [development.jsonl](../eval/development.jsonl) | 20 个题目与状态，其中 13 ready：8 个生成答案、2 个 SQL 计数、3 个拒答。逐条读 19 条引用及其 10 个不同的实际被引 evidence 全文，共 29,272 字符。 |

没有声称读完全部 85 次开发集检索结果、原文章全文或 PDF 图像，也没有对拒答题所有检索 evidence 另作穷尽式语义审阅。开发集仍是 `draft_not_frozen`，已用于多轮开发迭代；7 道 social/cross 题继续 pending，不算通过。定向 smoke 虽在运行模板中标记 `suite=development`，其独立 case file 与用途不变。

```text
outputs/pdf265_quote_context_paid_20260916.json SHA-256
5889a447aec0f62e60e972184f05507361b661567b291fcca75c13025329a05b

outputs/development_quote_context_20260916.json SHA-256
1a0a2ab2682bbe8bad7811e1dea02498bf5671c1d533b24e4d81c8f4a5b15a44

eval/pdf265_recovery_smoke.jsonl SHA-256
ffeb40fc421196b233f7e3a1178831dfff48574f7ffc99c0be3d8f2464d7ee18

eval/development.jsonl SHA-256
270acbf50d29cdccdcde563d29c8a3217ce90814782769fabcdcec9df14aaac4
```

## 2. 两题 PDF-265 smoke

### pdf265-smoke-01：数量句完整，广告归因保留

答案明确使用 `According to the mollusks advertisement`，保留 16 只、每日超过 250 万、连续采集、至少两三年。原文写 `data`，答案写 `data points`，属于该语境的单位释义，没有扩大数量或改成经独立验证的性能。

本轮 quote 从 `Just sixteen mollusks...` 开始，并完整包含持续时间与 `continuously.`，随后还有一整句关于烃类敏感性的背景。所选引文足以支持该回答，不再需要从缺失的前后半句补齐数量条件。该结论仅针对此次保存的引用；PDF 正文仍为有限恢复，不因此变成完整来源。

### pdf265-smoke-02：主体错误仍是实质问题

答案仍写 **`Laurent Cazes says the advertisement has shown...`**。原文是 Laurent Cazes 的 `We’ve shown...`，广告是承载这段话的来源，不是完成水体试验、展示技术有效性的行动者。不能把这个问题仅称作行文风格。

本轮 quote 已完整包含 `We’ve shown...` 和 `We now need to see if it is effective in estuaries...`，所以残句已不能解释该 actor 错误。核心边界保留正确：此前涉及温水、冷水、淡水和咸水，河口淡咸水混合环境仍需测试，答案没有说河口有效性已成立。

建议表述为：广告引用 Laurent Cazes，称 valvometry 已在所述水体显示有效，而在河口是否有效仍需测试。这里是建议，CSV 保留实际错误答案，未替换为修订稿。

## 3. 原开发集逐题意见

| 题目 | 独立 AI 观察 |
|---|---|
| dev-01 | 两条分别明确广告归因。每日畜粪浆与印度 Adilabad 项目地点有完整原句支持；没有将产气或健康效果转成独立测量事实。 |
| dev-02 | 天然气结合 CCS 制蓝氢、宣布建设计划、完工后最多每日 10 亿立方英尺蓝氢均有据；现有炼化综合体与拟建蓝氢设施没有混淆。第三条是重复说明规划状态的数量例证，可精简。 |
| dev-03 | Michel Di Capua 和 Bloomberg New Energy Finance 在 quote 明示；技术上看似可行但成功部署很少的限定保留。前文另有经济挑战，答案未提；原 rubric 未要求穷尽原因，因此记为完整性人工边界，不事后改题判错。 |
| dev-04 | 强度下降限制再生料掺入量、难脱色造成棕灰色均有据，明确归于 AFPM 广告。第一条 quote 以 But 开始，其机械回收对象可由紧邻前句确认。 |
| dev-05 | 首条回答菌藻生物质、CO2 与微藻燃料研究的联系。第二、三条 BIOMEM 工艺/韧性背景有据，但不能作为已生产燃料或完成 CO2 抵消的证据。第三条将相邻广告叙述与专家引语总括为专家所说，存在来源层次压缩，见下。 |
| dev-06 | 甲烷 20%、2025 截止和目标状态保留，明确归于 Total 广告。原文所选段未列基准年，答案没有补造。引用附带未完整结束的背景，但核心目标句完整。 |
| dev-07 | 同时回答 Baytown 和 Kasawari。每日最多 10 亿立方英尺蓝氢、每年最多 1,000 万 metric tons CO2 捕集、每年 330 万 tons CO2e 减排分别表述；could、once completed、aims、when onstream、最早 2026 均保留。第四条所选 quote 仍在 chunk 末尾断句，第五条另引完整重叠句。 |
| dev-08 | 中文答案保留规划状态，95% 限于生产过程 CO2，没有扩大为全生命周期或已运行结果。场址名依赖同 evidence 前文。`由Enbridge发布` 可能混淆署名/赞助方与媒体 Politico；太阳能背景可精简，两条完全相同的 quote 不构成独立证据。 |

### 尚未解决的短引文充分性与归因问题

1. **dev-07[4]：chunk 边界仍可产生残句。** quote 终止于 `while aiming to cut CO2 emissions by`。已包含的 `poised` 分句支持本条实际的预期角色判断，但引用本身不是完整句。dev-07[5] 使用另一个重叠 chunk，才包含完整的 Kasawari 数量及时间条件。可去掉重复的第四条，或直接使用第五条完整 evidence；不能宣称这轮分句修复消除了所有截断。
2. **dev-05[1]、dev-06[1]：完整核心句附带不完整背景。** BIOMEM 引用开头带上一引号尾，末尾止于 `We often work in partnership`；甲烷引用末尾止于 `citizens`。核心支持句仍完整，不能由此判定数量或研发联系是捏造，但证据卡的边界质量尚有问题。
3. **dev-05：背景、研究方向和说话人层次要分清。** 后两条只说明水处理机制与水质变化韧性，第一条已回答题目核心。去除溶解有毒有机物来自广告叙述，韧性来自 Patrick Baldoni-Andrey 直接引语；第三答将两者一并写为该专家所说，宜改为分别归因。答案未明确宣称 BIOMEM 已实现燃料生产或 CO2 抵消，不能将有据背景直接判成虚构成果。
4. **dev-08[1]：短 quote 不独立给出全部信息。** quote 只写 `at the site`；Ingleside、Corpus Christi、Texas 在同 evidence 前文，CSV 的 `context_excerpt` 保留场址指代上下文。整个 evidence 另有 `By ENBRIDGE INC.`，支持作者署名；记录的媒体 publisher 是 Politico。宜写“Politico 刊载、署名 Enbridge 的原生广告”，避免 `由Enbridge发布` 混淆角色，不能直接判作无歧义的发布身份表述。

## 4. 计数、拒答与运行记录

保存结果中，dev-09 返回 20、dev-10 返回 14，均为按全部筛选条件的 countable record 计数，不是生成式回答。dev-18、19、20 均返回“所选记录不足以回答”的通用拒答，没有编造 2025 独立运营审计、随机试验或赞助发票金额。本次检查了题目、rubric、回答及运行状态；未另行重算数据库或对这些拒答题全部检索片段进行完整语义裁定。

运行机械结果分开保留：

- 原开发集：8/8 hit@5、13/13 预设支持片段覆盖、85/85 evidence locator、19/19 citation locator、2/2 计数、3/3 拒答；8 个生成答案本地语言检查均为 match。保存成本 `$0.0167516`。
- 两题 smoke：所需支持片段 2/2、evidence locator 6/6、citation locator 2/2，两个生成答案本地语言检查均为 match。保存成本 `$0.00123485`。

以上是原运行的机械记录，没有在本次审阅中重跑；定位正确、语言 match 和取得预设片段都不能消除主体错误，也不能证明广告主张真实。`semantic_support` 继续待人审，`overall_pass` 为空。

## 5. CSV 交付检查与后续人工边界

CSV 的 21 行按原引用编号对应回答单元（smoke 2 行、dev 19 行），含复合事实与重复 quote，不是 21 份独立证据。原答案、原 quote、record/version/evidence ID、来源 URL 均保留。`quote_start`/`quote_end` 是该原文版本的半开字符区间；`context_excerpt` 为同 evidence 的原字符切片，没有跨 gap 拼接或改写原文。URL 是保存的来源字段，本轮没有在线确认其可访问性。

已回读检查全部 21 行：旧版 28 列顺序一致，claim/quote/ID 与 JSON 一致，所有 quote 与原 evidence 字符切片相等，context 均来自同 evidence，人工两列全空。通过 Artifact Tool 值表生成 CSV，无公式；CSV 不承载 Excel 布局或样式。只新增本报告和 CSV，没有改源码、题库、原运行或数据库，也没有付费调用。

人工复核应优先裁定 smoke-02 主体错误、dev-08 来源角色措辞、dev-05 邻接归因与额外背景，以及 dev-03 完整性边界。开发集已经影响过多轮实现决策；修复的个例与机械检查不能代替独立盲测或 FA26 人工最终验收。
