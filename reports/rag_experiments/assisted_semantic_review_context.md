# 新上下文检索运行：AI 辅助语义审阅

## 优先复核的 3 条

| 顺序 | 案例/主张 | 缺口及建议 |
|---:|---|---|
| 1 | dev-01 / 1 | claim 增加“两头牛的粪便足够平均一家”，但所选 quote 只到每天沼气及热水用途。同一 evidence 的下一句支持“两头牛”，并非虚构；需把对应句纳入引用，或删掉这个额外细节。 |
| 2 | dev-05 / 6 | claim 前半的光合作用、CO2、脂质和燃料/聚合物有引用支持；后半的炼厂、水泥厂、钢铁厂供 CO2 来自同一 evidence 的另一段，未被选中 quote 覆盖。可拆开引用或精简该补充。 |
| 3 | dev-07 / 3 | `3.3 million MTCO2e` 保留了来源中 MT 的缩写歧义。建议明确写“每年 330 万吨 CO2 当量”，同时保留 aiming、投产条件与最早2026年。现有材料不足以仅凭缩写断定数值放大百万倍。 |

上述前两条均得到完整已引 evidence 支持，但展示的 quote 未支撑完整 claim；第三条的公司/项目身份和未来限定正确，问题在最终单位表达。**本次未识别出确定的跨公司事实错归或与完整 evidence 直接矛盾的主张。**

[逐行复核 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/reports/citation_review_context.csv>) 已将这 3 条置顶。全部 `human_verdict` 留空。

## dev-05 / dev-07 的目标完成情况

### dev-05：上一轮的核心遗漏已补齐

新答案第 1–3 条均来自目标文章 `Total: Using biomimicry for cleaner water` 的末段 evidence `[5004, 7696)`，准确对应细菌/微藻制造生物质、帮助抵销 CO2、探索微藻生产 biogas 和 biofuels。回答保留 developing/examining 的研发语气，没有声称已独立测得抵销效果。第 4–5 条由同篇前段解释 BIOMEM 的水处理机制。

第 6 条确实来自另一篇 `Microalgae, a promising pathway to sustainable biofuels`，但已明确 Separately，且核心问题已经由目标文章完成；本次不能再把它解释为“拿其他文章替代未回答的目标联系”。它仍有上表列出的短引用覆盖缺口，也属于可删的扩展背景。

### dev-07：氢产量与 CCS 捕集量现已区分

第 1 条明确每天最多 10 亿立方英尺的**蓝氢产量**；第 2 条明确每年最多 1000 万公吨 CO2 的**潜在捕集量**。两条均保留 could/once completed 等条件。Kasawari 第 3 条保留 poised、aims、when it comes onstream、as early as 2026；没有把任一规划数字写成独立运行实绩。剩余复核重点是 CO2 当量单位的无歧义表达。

## 范围与判断口径

本报告是 **AI 辅助审阅，不是人工金标准、盲测或人工 ≥95% 验收结果**。开发集仍为 `draft_not_frozen`；同一开发集已经用于调试，不应把本次改进外推为未见问题上的准确率或泛化能力。所有人工判断保持待完成，不覆盖输出中的 `pending_human_review`。

仅检查该运行的 **8 个 answered 案例、23 条 claim/quote**。没有重评 count_only、无证据拒答或尚未取得的社交数据。逐条结合原问题、既有 rubric、所选 quote 与完整已返回 evidence 片段判断：

| assistant_assessment | 含义 | 条数 |
|---|---|---:|
| supported | quote 及必要指代上下文支持完整 claim，主体、文章、单位、时间/规划限定与题目范围相符。 | 20 |
| partial | 完整 evidence 有依据，但 quote 缺关键细节或最终单位/限定仍需复核；不等同于事实为假。 | 3 |
| unsupported | 提供的 evidence 不支持或与 claim 矛盾。 | 0 |

这只是待人工核对的分类数量，**不是人工语义通过率**。23 条 quote 均在指定 evidence 中精确出现，且不超过本轮配置的 60 个空白分隔词；定位有效与语义充分分开判断。原文件报告的 8/8 命中、13/13 gold passage、23/23 citation locator 不替代本次语义审阅，也不能替代人工验收。

## 逐案完整性

| 案例 | 题目完成情况与限制 |
|---|---|
| dev-01 | 原料和地点均回答；第1条额外“两头牛”缺对应 quote。建议前置“广告称”，保持来源语境。 |
| dev-02 | 自然气—CCS 联系、新氢设施尚属规划、潜在蓝氢产量与 CCS 捕集量均有完整句引用，单位与条件保留。 |
| dev-03 | 已回答技术上似乎可行但当时成功部署很少的部署让步。未展开经济挑战，但题目/rubric未要求列尽文章全部让步，不能仅因少复述另一 gold 句就判失败。to date 应限于2015年文章时点。 |
| dev-04 | 核心因果链和强度限制现有完整 quote；去色困难也有据。 |
| dev-05 | 目标文章的微藻/细菌联系已补齐，研发/预期语气保留；第6条额外跨文章背景有引用覆盖缺口。 |
| dev-06 | OGCI 20%/2025 目标有直接支持，没有混同 Total 的15%碳强度目标，也未写为已实现。 |
| dev-07 | 两篇广告均用于回答；蓝氢体积产量与 CO2 捕集量现已区分，未来条件保留；Kasawari 单位缩写仍需明确。 |
| dev-08 | 地点、氢/氨—CCS关系、最高95%的生产环节分母、规划状态均有完整支持；新增60兆瓦太阳能农场是同文的另一项规划，能回应“哪些说法属于规划”。部分重复但不构成不支持。 |

## 证据来源与可复查范围

- 新运行：[development_paid_context_20260916.json](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/outputs/development_paid_context_20260916.json>)。
- 问题/rubric：[development.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/eval/development.jsonl>)。
- 日期：2026-09-16；run_id：`15434ab5000e469cbc2380f407f71e1b`；data_version：`652ed975bbd44ea06e20af19b6a6642d`。
- 新运行 SHA-256：`2287df245fd070c3f89119d61d0e597c3da5104ff6e574e0918a5e727727090f`。
- 问题/rubric SHA-256：`270acbf50d29cdccdcde563d29c8a3217ce90814782769fabcdcec9df14aaac4`，与运行记录一致。
- 23 条引用共使用 10 个不同 evidence 片段。其中 9 个片段的 text、record_id、version_id、起止字符、标题、赞助方、URL 与上次已完整审阅片段逐字段一致；本次另完整阅读了目标水处理文章末段，并逐条重新对照新 claim/quote。
- 判断所需内容均已在上述 evidence 及既有 rubric 中提供，因此未额外查询数据库或网站。不将检索片段称为全部网页全文，也不把定位通过称为独立现实事实核验。
- 仅写本报告及 `citation_review_context.csv`，保留旧报告和旧 CSV；未改输出、gold、问题、代码，未调用付费 API。

| case_id | claim 数 | 原问题 |
|---|---:|---|
| dev-01 | 2 | What feedstock supplies the biogas digesters used in Total and GoodPlanet's employee air-travel offset project, and where is the project? |
| dev-02 | 3 | How does the ExxonMobil Baytown hydrogen advertisement link natural gas to CCS, and is the new hydrogen facility described as already completed? |
| dev-03 | 1 | What caveat does the Statoil-commissioned Forbes technology article acknowledge about carbon capture deployment? |
| dev-04 | 2 | Why does AFPM's Politico plastics advertisement describe limits to mechanical recycling? |
| dev-05 | 6 | How does Total connect bacteria and microalgae in water treatment with CO2 emissions, biogas and biofuels? |
| dev-06 | 1 | Describe the methane target announced at the OGCI CEO meeting in Total's 2018 carbon-intensity advertisement. |
| dev-07 | 3 | How do the ExxonMobil Baytown and PETRONAS Kasawari CCS advertisements mark capacity as prospective rather than achieved? |
| dev-08 | 5 | 在2022年Politico的Enbridge原生广告中，低碳氢和氨生产出口中心怎样与CCS相连？哪些说法属于规划？ |

### 被引用 evidence 的身份与范围

| evidence_id | 文章 | record_id | version_id | 原字符区间 |
|---|---|---|---|---|
| f3f7d517d5800644716ec19a1aaa57bd0345990cb94b06b14cee3de86e3a6c80 | Biogas to offset air travel emissions | `01374b51-3fae-5fe7-8c60-b4bffa2b7ba0` | `5fe6f34efdd3af3a24b64dea13847dbac5cbe8659df866643b4f69e33e8cefcb` | [0, 2802) |
| 63eb9019881347c2d291ea3455f6fd40039975e33c9cd489ba10b8807989409c | Hydrogen: Another Chapter in ExxonMobil's Lower-Emissions Ambitions | `0d2b4bc2-4397-5604-8235-fcda8c7088f7` | `b24cc22b09f6d6247109e3504b47d947c036c3aec87ac131fbc4b1d2c69ea101` | [0, 1955) |
| 67f870082c904a4e2d750c68854f7ac9bba8ac30b2fc8b0967093aad5a9dc0ad | The Technology Behind Energy Innovation | `11cb9509-d4c7-5bbe-bd19-ad24d914e43e` | `51bd49d35ce5943faa4bddbef24da53441e867e8dba80f9410667d755c9121ad` | [0, 3199) |
| 07bb2e0a00453b2f513e03e0cf0b6c25e19307a74a91cf609b71c81b0e1114fa | Petrochemical manufacturers use chemistry to make plastic more sustainable and recyclable - POLITICO | `efb2878e-efea-5821-a9c1-20851779c77a` | `e696aa7061c7b553d393ad536513f6cf0d958f79e33754c5fe92f001198509ed` | [0, 3211) |
| d8de3d390bc0a5c8f0352405abd63d9ca5baf482293e915729d9ab3b669ce235 | Total: Using biomimicry for cleaner water | `42114981-e507-5753-9b3a-62c09a7624a2` | `781aa2f69323e06e82304557b3143dc6fbe683ae28554d500d5bc218c2be0990` | [5004, 7696) |
| 9fa4761e73bf375249330de8175a461d4b68dc45477812ded479f5b6dc2ef8c0 | Total: Using biomimicry for cleaner water | `42114981-e507-5753-9b3a-62c09a7624a2` | `781aa2f69323e06e82304557b3143dc6fbe683ae28554d500d5bc218c2be0990` | [0, 3092) |
| 9cec9237fa4aaabd6162ab594d1ce935bef5475c938fb4f46c0a55eefc1642a6 | Microalgae, a promising pathway to sustainable biofuels | `83b24daa-988f-56f7-baf3-5177120e457b` | `8ee21f0ddc1b8d8f4fa915cc64b70e8c06247705d12e6f3be26fd8c3dbf4b7aa` | [0, 2954) |
| d9808d4eaf37f70d2053c61e4488f33b4e9fa7d6c5919799b2ab43d459f75187 | Total gives itself 15 years to make its products 15 percent less carbon intensive | `1cd348bd-2725-5147-a290-8d40341a15de` | `0e0527137564e9d75c5a19b53cbc8deac1fce64ae0d8bf32a7ab978d550b5cc9` | [0, 2811) |
| 3a1caa866f42772bc29e5e632648956104746b7bd511056d7a48220306a11941 | Building On An Innovation Legacy Toward A Sustainable Future | `049b49ed-d68f-506a-b7e4-b8369dc1b8fe` | `16b0b539d7755b3023a35ec6a1532e29cdfca70b2182a5cb1bf2de07016e0bbf` | [5209, 8244) |
| cd29b694bc8582a880b968e480921ac491777db5f22f1e9ff8d5a88898aad8ee | Bridging to a sustainable and secure energy future | `e1c336a6-d8ed-5fec-9147-5f4efc588cc1` | `d0c407d7c2abca14508153e5f4169efc105f331d0bf60facd4e2ad19dfdff292` | [0, 3157) |

CSV 保留原 claim 与 quote 文本，建议只写在 reason；以 `case_id + claim_index + evidence_id` 回到运行 JSON，即可看到 URL、完整证据片段与来源版本。人工宜分别检查“完整证据是否支持”“所选引用是否充分”“题目关键限制是否完成”，再填写自己的 verdict。请不要将 assistant_assessment 自动复制为 human_verdict。
