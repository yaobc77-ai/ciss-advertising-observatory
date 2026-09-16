# v0.2.1：AI 辅助语义复核

**本次需补 dev-01 的显式广告归因，以及 dev-07 蓝氢产量的对象名称；dev-03 经济障碍遗漏仍需人工判断完整性。** AI 阅读未见西班牙语／法语偏离。此结论不是人工验收：16 行 `human_verdict`、`human_notes` 全为空，人工语义支持率保持未知，不能宣称 ≥95% 或整体通过。

## 输入与范围

- [运行输出](../outputs/development_language_guard_20260916.json)：run `612863daa16a48dcb3a2b1179eb3479d`，数据版本 `d85a98002e4493f0376c260ad82253ee`，创建于 `2026-09-16T18:58:33.111818+00:00`。
- [开发题库与 rubric](../eval/development.jsonl)：未修改，仍为 `draft_not_frozen`。
- [逐条审阅 CSV](citation_review_v0_2_1.csv)：16 个带引文回答单元，保留原文、引用、ID、字符位置、必要上下文、AI 意见和空白人工列。

```text
outputs/development_language_guard_20260916.json SHA-256
cfafce2ed95c36507490db6361904fa4fbafd90a5b9fe808a21cacc6a5444ee5

eval/development.jsonl SHA-256
270acbf50d29cdccdcde563d29c8a3217ce90814782769fabcdcec9df14aaac4
```

逐条读取了 8 道支持题的 question/rubric、16 条引用及其实际对应的 **8 个完整 evidence 片段，共 22,862 字符**。不声称读完全部 85 次检索结果或文章全文。每个回答单元按原引用编号划分，复合事实与重复 quote 不等于独立证据。

口径为“所选 quote＋同一 evidence 的必要指代上下文”，分别检查含义、归因、单位／未来限定、任务完整性与语言。没有用其他文章补造依据。定位有效不等于回答完整，也不证明广告主张真实。

## 关键发现

### dev-07：引用有蓝氢，答案正文没有

第一条写的是 `1 billion cubic feet a day`，保留 `could`、`up to` 和 `once completed`，数值与规划限定有据；但**整份答案正文没有写出该体积是 blue hydrogen 的生产量**。本题 rubric 明确要求区分 hydrogen production 与 proposed CO2 reductions，因此这不是单纯的文字偏好，而是单位对象及任务完整性缺口，建议补 `of blue hydrogen`。

后两条正确分开了最多每年 1,000 万 metric tons CO2 的潜在捕集能力，以及 Kasawari 每年 330 万 tons CO2e、投产时且最早可能 2026 年的目标，没有混算。quote 中有产物并不能替代答案正文明确完成比较要求。

dev-02 第三条也省了产物名，但前两条已经明确蓝氢设施，故其主要问题是孤立阅读清晰度，与 dev-07 的整答遗漏不同。

### dev-01：两点有据，来源归因未补

畜粪浆每日供料和印度 Adilabad 地点均获原句支持，原问题的两个事实点已回答；正文仍直接说 `The digesters are…`／`The project is…`，没有 rubric 要求的明确广告／受访者归因。建议在首句加入 `According to the advertisement`，让后句承接。

### dev-03：部署困难已答，经济挑战仍省略

答案忠实转述“技术看似可行，但截至文章所述时期成功部署很少”。同一 evidence 还明确写出即使有已证实技术仍面临 economic challenges，答案没有解释此原因。原题和 rubric 未要求穷尽原因，故不按 gold 短句未复述直接判错；若研究目的包括解释为何落地不足，则应补经济障碍。保留为人工完整性待审项。

## 其余单元与语言

| 题目／单元 | AI 检查结果与边界 |
|---|---|
| dev-02-1、2、3 | 天然气＋CCS 的蓝氢生产关系、宣布建设计划、未来产量均有据且归于广告。第三句的未来状态应按广告发表时理解。 |
| dev-04-1、2 | 强度下降限制回收料掺入量，以及棕灰色／脱色困难均有据，明确归于广告。 |
| dev-05-1、2 | 菌藻生物质与 CO2、微藻与沼气／生物燃料关系有据。R&D 团队可由同片段 Total/Baldoni-Andrey 前文恢复；保留研发而非量产或实测成果。两条用同一 quote。 |
| dev-06-1 | 甲烷目标降低 20%、期限 2025 均有据，未补基准年或强度分母。归于会议措施，可再补“据 Total 广告”明确材料来源。 |
| dev-08-1、2 | Ingleside 场址由同片段前文支持，孤立 quote 只写 at the site。枢纽、CCS、最多 95% 均保留规划，分母为生产过程 CO2，未扩为全生命周期温室气体。第二条明确广告归因。 |

本地语言检查保存为 **7 match、1 inconclusive**：dev-01 的地点短句检测不确定，组合文本为 English。AI 可读出两句均为英文；此意见没有覆盖工具原状态，也不是人工通过。本次 8 个答案均使用对应题目语言，不能由一次开发快照推断语言稳定性或改进的因果效果。

## 验证与未完成项

CSV 的 16 条 claim、quote、record/version/evidence ID 与运行原文逐项回读一致；quote 和必要 context 均存在于对应保存片段，offset 切片一致。人工列全空，输入哈希未变，内部相对链接有效。CSV 通过 Artifact Tool 值表生成，无公式。

运行文件另报告 16/16 citation locator、85/85 evidence locator、8/8 hit@5、13/13 support passage coverage、2/2 计数、3/3 拒答。**本轮没有重跑这些检查，也没有对拒答题全部证据另作语义审阅。** 7 道 social/cross 题仍 pending，不算通过，不进入人工支持率分母。

应由人工按原 question/rubric 填写 CSV，分开判断文本支持与任务完整性；必要时查完整原文。当前开发材料已用于迭代，不是独立盲审或正式验收。只新增本报告和 CSV，未调用模型 API、连接数据库或修改原输出、题库、代码。
