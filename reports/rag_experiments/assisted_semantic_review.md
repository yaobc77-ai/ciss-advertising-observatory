# 开发集回答的 AI 辅助语义审阅

## 优先人工复核

1. **dev-05：目标问题没有完整回答。** 问题与 rubric 要求解释指定水处理广告中细菌/微藻、生物质、CO2 抵销以及 biogas/biofuels 的联系。本次只检索到目标文章 `Total: Using biomimicry for cleaner water` 的 `[0, 3092)`，所需联系句没有出现在本案例返回的任何 evidence 中。回答第 1 条只介绍 BIOMEM；第 2–4 条转向另一篇微藻生物燃料广告，第 5–6 条转向 Adilabad 粪浆沼气广告。后两组各自有来源，且以 separate/another 区别，不应称为已证实的公司错归；但这些来源不能替代题目指定的联系。`required_record_id` 命中因此不足以判定答案完成。
2. **dev-07：单位及产能类型需要明确。** 第 2 条没有在 claim 中说明每日 10 亿立方英尺是**蓝氢产量**，紧接 CCS capacity 的表述容易混淆两类能力；rubric 明确要求区分氢产量与 CO2 减排。第 3 条的 `3.3 million MTCO2e` 存在缩写解释歧义，建议明确写“每年 330 万吨 CO2 当量”。这里不据缩写单独断言数值扩大百万倍。两篇广告均保留了 could/aiming/onstream 等预期语气，没有在回答中被直接说成已实现的运行结果。
3. **短引文的内容覆盖不足。** dev-04 第 1 条的核心原因“塑料逐渐变弱”在 quote 之外；dev-08 第 2 条的 quote 截在 `95% of the`，未包含“生产过程中产生的 CO2”这个分母与阶段限制。其他缺口见 CSV。完整 evidence 支持这些细节，不能据此叫作虚构事实；但“可定位到原文”与“所选短 quote 支持整条 claim”应分开验收。

[逐条复核 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/reports/citation_review.csv>) 已将 dev-05、dev-07 的主要问题放在前面，再列其他 partial，最后列 supported。`human_verdict` 的 25 个单元格全部留空，供用户独立填写。

## 范围、输入与证据边界

- 审阅日期：2026-09-16；只审阅指定运行的 **8 个 answered 案例、25 条 claim/quote**，不评价 count_only、拒答案例或尚未取得的社交数据。
- 输出快照：[development_paid_quotes_20260916.json](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/outputs/development_paid_quotes_20260916.json>)。
- 问题及 rubric：[development.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/eval/development.jsonl>)。
- run_id：`19675da7bac04367a45a6de6ed89e293`；data_version：`652ed975bbd44ea06e20af19b6a6642d`；gold_status：`draft_not_frozen`。
- 输出 SHA-256：`256f4a05e97ae6569a2133868966f27e08acd4eed69b07657ad0fd003b2f9cbf`。
- rubric 文件 SHA-256：`270acbf50d29cdccdcde563d29c8a3217ce90814782769fabcdcec9df14aaac4`。
- 本次依据 JSON 中完整的**已返回 evidence 片段**审阅，而非声称重新读取全部网站或每篇完整文章。逐行依据 `case_id + claim_index + evidence_id` 对应输出；没有使用裸旧 doc_id 跨文件关联。
- 使用现有短引用，未修改问题、rubric、模型、源文章、运行结果或旧指标，未调用付费 API。

## 判定口径与汇总

这是 **AI 辅助审阅，不是人工金标准、盲测或独立性能估计**。当前开发问题仍标记 draft_not_frozen。不得把下面数量换写为“人工 95% 语义支持已达标”，也不得覆盖原结果中的 pending_human_review。

| 判定 | 含义 | 本次条数 |
|---|---|---:|
| supported | 短 quote 与必要的指代上下文支持完整 claim，且符合题目的文章/限制范围；仍只是广告所述内容，不认证现实事实。 | 9 |
| partial | 完整 evidence 有依据，但短 quote 缺关键细节，或归因/单位/任务范围存在待复核缺口；不是“部分句子一定为假”的同义词。 | 16 |
| unsupported | 所提供 evidence 不支持或与 claim 矛盾。 | 0 |

本次没有识别出确定的跨公司事实错归或与完整已引 evidence 直接矛盾的 claim；这不等于证明没有语义错误。25 条 quote 均可在其指定 evidence 中精确找到，且都不超过 25 个空白分隔词，这仅是本地定位/长度复核。没有重新运行数据库版本验证或模型。

**为什么采用严格的 partial：** 例如一条 claim 同时声称每日产量、产品类型和完工条件，而 quote 只覆盖数值和部分条件，即使相邻完整 evidence 可以补齐，仍列入复核。这样能区分“背景文本有依据”和“展示给用户的短引文充分支撑”。案例级的遗漏（尤其 dev-05）不能通过其他无关但真实的 claim 数量补偿。

## 按案例检查问题覆盖

| 案例 | 结论及主要限制 |
|---|---|
| dev-01 | 原料与地点均覆盖；公司/项目身份一致。建议最终表述加“广告称”，保持对广告材料的归因。 |
| dev-02 | 自然气—CCS 联系及规划状态均覆盖；第 3 条短引文漏掉 day/blue hydrogen，需补足单位和产品。 |
| dev-03 | 经济挑战及部署不足两条让步关系均覆盖；“to date”应按历史文章时点，不能外推到当前。 |
| dev-04 | 完整 evidence 支持答案，但第 1、2 条的短引文遗漏关键因果/强度条件。 |
| dev-05 | 未完整回答指定文章中的联系；6 条全部需检查引用窗口或题目范围，其中 5 条取自其他文章。 |
| dev-06 | 正确保留 OGCI 的 20%/2025 目标，没有错当为已完成减排或 Total 的 15% 碳强度目标。 |
| dev-07 | 两篇目标广告均有引用，预期状态保留；蓝氢产量命名和 CO2 当量单位仍须修正/确认。 |
| dev-08 | 规划与协议状态区分正确、公司身份一致；4 条均有短引文覆盖不足，第 1/3 条重复。 |

## 审阅案例及来源索引

| case_id | claim 数 | 原问题 |
|---|---:|---|
| dev-01 | 2 | What feedstock supplies the biogas digesters used in Total and GoodPlanet's employee air-travel offset project, and where is the project? |
| dev-02 | 3 | How does the ExxonMobil Baytown hydrogen advertisement link natural gas to CCS, and is the new hydrogen facility described as already completed? |
| dev-03 | 2 | What caveat does the Statoil-commissioned Forbes technology article acknowledge about carbon capture deployment? |
| dev-04 | 3 | Why does AFPM's Politico plastics advertisement describe limits to mechanical recycling? |
| dev-05 | 6 | How does Total connect bacteria and microalgae in water treatment with CO2 emissions, biogas and biofuels? |
| dev-06 | 1 | Describe the methane target announced at the OGCI CEO meeting in Total's 2018 carbon-intensity advertisement. |
| dev-07 | 4 | How do the ExxonMobil Baytown and PETRONAS Kasawari CCS advertisements mark capacity as prospective rather than achieved? |
| dev-08 | 4 | 在2022年Politico的Enbridge原生广告中，低碳氢和氨生产出口中心怎样与CCS相连？哪些说法属于规划？ |

| case_id | 本次答案实际引用的文章 |
|---|---|
| dev-01 | Biogas to offset air travel emissions |
| dev-02 | Hydrogen: Another Chapter in ExxonMobil's Lower-Emissions Ambitions |
| dev-03 | The Technology Behind Energy Innovation |
| dev-04 | Petrochemical manufacturers use chemistry to make plastic more sustainable and recyclable - POLITICO |
| dev-05 | Biogas to offset air travel emissions, Microalgae, a promising pathway to sustainable biofuels, Total: Using biomimicry for cleaner water |
| dev-06 | Total gives itself 15 years to make its products 15 percent less carbon intensive |
| dev-07 | Building On An Innovation Legacy Toward A Sustainable Future, Hydrogen: Another Chapter in ExxonMobil's Lower-Emissions Ambitions |
| dev-08 | Bridging to a sustainable and secure energy future |

CSV 中的 claim 与 quote 保留原输出，不把建议改写混进原回答。其 evidence_id 可在指定 JSON 中取得 record_id、version_id、URL、起止字符和证据片段。对于 partial，人工应分别判断：主张是否受完整 evidence 支持、短 quote 是否充分、是否满足该题 rubric；必要时在 `human_verdict` 中注明需要改引文、改限定或重新回答，避免把三个问题压成单一“引用通过”。
