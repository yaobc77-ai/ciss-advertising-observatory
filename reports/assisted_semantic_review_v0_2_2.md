# v0.2.2：AI 辅助内容复核

**本次回答已补齐 dev-01 的广告归因和 dev-07 的蓝氢产量对象。** dev-03 的人物归因正确，经济挑战遗漏仍属完整性待审；dev-05 新增两条水处理背景有据，但不能由此推断 BIOMEM 已实现燃料生产或 CO2 抵消。

这是 AI 辅助检查，**不是人工验收**。CSV 的 16 行 `human_verdict` 和 `human_notes` 均为空，人工语义支持率未知，不作 ≥95% 或整体通过结论。

## 输入与边界

- [原始运行](../outputs/development_claim_contract_20260916.json)：run `d26eb540a6114cfe9672a755c43f39a7`，数据版本 `d85a98002e4493f0376c260ad82253ee`，创建于 `2026-09-16T19:10:07.387051+00:00`。
- [未修改的 question/rubric](../eval/development.jsonl)：仍是开发草案，`draft_not_frozen`。
- [逐条 CSV](citation_review_v0_2_2.csv)：沿用 28 列，保留原答案、引用、ID、offset、必要上下文及独立 AI 意见。

```text
outputs/development_claim_contract_20260916.json SHA-256
4b5895092c9ef6449b1052a27faee151cfced8351e9d8354544dbc0e725765a7

eval/development.jsonl SHA-256
270acbf50d29cdccdcde563d29c8a3217ce90814782769fabcdcec9df14aaac4
```

逐条核对 8 个答案、16 条引用及对应的 **9 个实际被引 evidence，25,954 字符**。其中 8 个片段在上一轮已完整阅读，本轮确认文本逐字不变；新增 BIOMEM 片段完整阅读。没有声称读完全部 85 次检索结果或原文章全文。

按“quote＋同一 evidence 的必要指代上下文”检查含义、主体、单位、时间、归因与问题完整性。16 行是原引用编号对应的回答单元，包含复合事实及重复 quote，不能视为 16 份独立证据。

## 主要结论

| 题目 | 独立 AI 判断 |
|---|---|
| dev-01 | 两句分别明确 `The advertisement says/locates`，畜粪浆每日供料和 Total/GoodPlanet 项目位于印度 Adilabad 均有原句依据。旧归因缺口在**本次输出**已解决。 |
| dev-02 | 蓝氢由天然气结合 CCS 生产，以及新设施为宣布建设计划均有据。low-carbon 明确归于广告，未说全生命周期零排放。 |
| dev-03 | Michel Di Capua 与 Bloomberg New Energy Finance 均在所选 quote 明示；`in some respects`、技术上看似可行、成功部署很少的限定保留，归因正确。仍未提同片段的经济挑战：原 rubric 未要求穷尽原因，保留完整性人工边界。 |
| dev-04 | 强度下降限制掺入量，以及棕灰色／难脱色均有据，并明确归于 AFPM 广告。 |
| dev-05 | 首条已回答菌藻生物质与 CO2、微藻与沼气／生物燃料的研发联系。后两条 BIOMEM 背景有据，见下。 |
| dev-06 | 本轮明确 `The Total advertisement reported`；甲烷降低 20%、期限 2025 和目标状态正确，未增基准年、强度分母或达标结论。 |
| dev-07 | 正文已写“每天最多 10 亿立方英尺**蓝氢**”，并分开最多每年 1,000 万 metric tons CO2 捕集和每年 330 万 tons CO2e 减排目标。两广告的 could、once completed、aims、when onstream／最早 2026 均保留。旧单位对象缺口在**本次输出**已解决。 |
| dev-08 | 广告归因与计划主体 Enbridge 明确；Ingleside 场址可由同片段前文解析，孤立 quote 只写 at the site。最多 95% 限于生产过程 CO2，且属于规划，没有扩大为全生命周期减排或已运行成果。 |

### dev-05 的新增背景：有据，但不增加燃料成果证据

第二条“微生物在曝气生物反应器的浮动载体上形成生物膜”，来自 BIOMEM／MBBR 的直接描述。第三条“先去除烃类，再用包含 BIOMEM 的生物处理进一步降低有机污染物”，也有明确流程原句。它们与 water treatment 主题相关，不能直接判成离题或捏造。

不过，**题目要求的 CO2、biogas、biofuels 联系已由第一条回答**，这两条只是水处理机制与阶段背景，不直接证明这些产出。现有答案没有明确宣称 BIOMEM 已生产沼气／生物燃料或实现 CO2 抵消，所以不判为虚构成果；为聚焦问题，可省略背景，或明确标为独立背景，避免读者将其与第一条研发方向等同。流程先后也不等于所有污染物均被完全清除的测量结论。

## 验证与人工待审

AI 阅读中，8 个答案均使用对应题目语言；运行的 **8 match 仅为本地语言启发式结果**。运行另报告 16/16 citation locator、85/85 evidence locator、8/8 hit@5、13/13 support passage coverage、2/2 计数及 3/3 拒答。这些是保存的机械成绩，本轮未重跑，亦未另作拒答题全部证据的语义审阅。

CSV 已回读检查 16 条 claim/quote/ID 与原输出一致，字符切片和必要 context 有对应 evidence 支持，人工列全空，原输入哈希未变。表格通过 Artifact Tool 值表生成，无公式。只新增本报告和 CSV，未改运行、题库或代码，未调用付费 API 或连接数据库。

本轮没有发现与所选文字及必要上下文明显矛盾的数值或规划主张；这不能替代人工裁定完整性，也不能证明广告主张真实。7 道 social/cross 题仍 pending，不算通过。开发题已经用于多轮迭代，本次特定缺口的修正不等于独立泛化或稳健性证明。
