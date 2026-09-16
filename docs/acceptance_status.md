# 实施与验收状态

更新日期：2026-09-16。**原生广告研究预览已在本机运行**，完整目标仍保持为 M1–M8。用户要求先完成其余部分，社交资料、指定 GitHub 和公网配置暂缓提供，这些接口维持预留。当前入口见 [README](../README.md) 和 [交接说明](handoff.md)。

| 模块 | 已实现及已有本机证据 | 仍需完成的验收 |
|---|---|---|
| M1 | 原生/社交契约、版本表及独立适配器已实现；真实原生 268 条导入，保存的重复导入为 268 unchanged / 0 new_versions；12 条新增 URL 已逐项审核，建议和证据另存，未改变主库 | 社交真实映射与对账；采用候选审核决定并补齐列明的来源证据；持续维护异常 |
| M2 | 256 条可计数、221 条可检索；26 条 video 正文占位不入索引；版本、字符偏移和导航前缀有程序检查，质量清单已记录 | 20 个前缀边界及 94 个疑似截断需针对性审核；PDF 候选对应和全篇完整性不能自动认证 |
| M3 | 英文 Dash / AG Grid 六字段表、统计、筛选、导出及来源开关已实现；浏览器实测 ExxonMobil 15 条，CSV 为 15 个不同 record_id；两视图独立状态已验证 | 持续回归与真实用户反馈；新增数据版本后的对账 |
| M4 | 社交适配器、映射样例、独立视图与 not connected 状态已实现 | 提供真实导出、字段说明及所需原型资料，再做记录、统计及问答验收 |
| M5 | 免费关键词、精确向量与混合检索、OpenAI Responses、引用定位、预算及失败处理已接通；已有真实回答和拒答记录 | 短引文语义充分性、指定问题完成度及跨库质量；后续修正需单独运行和评价 |
| M6 | 20 个开发问题和 20 个验收草案，每组 13 ready / 7 pending_social；前置定位校验、runner 与真实开发运行已完成；AI 辅助复核暴露语义缺口 | 独立人工审题、冻结验收版、人工语义判断；社交/跨库题待真实资料，不以空数据评分 |
| M7 | 项目隔离 PostgreSQL + pgvector、启动/停止/健康检查、预算账本、备份恢复脚本已实现；数据库启停及新库恢复有本机记录 | Cloudflare Named Tunnel / 固定域名配置；另一网络的 HTTPS、可用性与成本防护验证 |
| M8 | Python 包、依赖锁、配置样例、测试、数据/运行/用户文档、7 页研究预览及中文讲稿已存在 | 指定 GitHub remote 的实际交付；完整双数据集最终演示、客户审阅及正式交接验收 |

## 开发运行与语义验收分开记录

当前主记录为 [development_paid_citation_first_20260916.json](../outputs/development_paid_citation_first_20260916.json)，run_id `0369cb87f07648359dccd28687598a6b`，时间 `2026-09-16T17:47:34Z`，数据版本 `652ed975bbd44ea06e20af19b6a6642d`。它是一次固定版本的开发诊断，不是后续代码自动继承的成绩。

| 机械检查 | 该次结果 | 证据边界 |
|---|---:|---|
| 必需记录 hit@5 | 8/8 | 记录命中不能证明返回段落覆盖题目细节 |
| 必需支持片段覆盖 | 13/13 | gold 原句确实出现在返回 evidence，仍不自动评价回答语义 |
| 完整筛选计数 | 2/2 | 对照指定题目的完整记录集合 |
| evidence 定位 | 79/79 | 原文、版本与字符位置有效 |
| citation 定位 | 17/17 | 引句存在于指定 evidence，仍需判断支持关系 |
| 无证据问题拒答 | 3/3 | 仅覆盖该次 3 个开发案例 |

该次 `gold_status=draft_not_frozen`、`semantic_support=pending_human_review`、`overall_pass=null`。4 个社交问题与 3 个跨库问题仍 pending，不进入已运行分母。

最新工程检查为 93 tests passed，Ruff 通过。它验证程序行为，与模型语义验收分开。

[当前 AI 辅助语义审阅](../reports/assisted_semantic_review_citation_first.md) 逐条检查 17 条引用，并区分必要指代上下文、广告归因和任务完整性。人工列仍为空，不能计算人工通过率。较早运行的缺口与修正过程统一保留在评估报告中。

统一结果入口为 [reports/evaluation.md](../reports/evaluation.md)，以其明确记载的 run_id、数据版本、分母和未解决问题为准。当前机械复跑通过不代表人工语义支持已经通过。评价规则见 [evaluation_protocol.md](evaluation_protocol.md)。

## 证据入口

- [数据字典及导入快照](data_dictionary.md)，[重复导入记录](../outputs/native_import_repeat.json)。
- [新增 12 个 URL 审核](../reports/additional_url_review.md)：7 项建议纳入、4 项建议排除、1 项待核；其中 1 项纳入取决于 CERAWeek 范围定义，建议尚未应用。
- [用户指南](user_guide.md)，[研究预览](../deliverables/research_preview.pptx)，[演示讲稿](../deliverables/demo_script.zh-CN.md)。
- [数据库验证与恢复记录](local_postgres.md)，[运行维护](operations.md)，[交接索引](handoff.md)。

历史计划与附录保存需求和来源记录，当前实施以本页及其运行证据为准。本机可用、程序检查通过、研究预览和完整公众交付是不同状态。缺少外部输入与人工语义验收的部分继续保留未完成。
