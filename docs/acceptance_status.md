# 实施与验收状态 — 0.2.5

更新日期：2026-09-16。当前原生数据版本 `5114ebc1cf9afe59cdaa715e3ea45166`，应用在本机运行；完整 M1–M8 目标仍未完成。用户暂缓提供的外部资料继续预留。

| 模块 | 当前证据 | 尚未完成 |
|---|---|---|
| M1 数据 | 275 条收录；12 项候选的 7/4/1 决定已应用；0.2.3 数据发布仅 1 个新正文版本、274 不变，重复导入 275 unchanged；原值和旧版本保留 | 社交真实映射、待核候选补证及持续维护 |
| M2 正文 | 263 可统计、226 可检索；既有导航审核保留，PDF-265 的 6 个有限区间已应用；558 个当前块与 86 个历史证据定位有效 | 原有 94 项截断限制中仅 1 篇补入有限续文，仍未完整恢复；图像与遮挡文字仍缺失 |
| M3 Dashboard | 六字段、筛选、统计、导出、历史标签；已实测全部263→ExxonMobil 15→叠加Washington Post 5；0.2.5让明细与图表使用同一次查询，并将未知日期留在汇总、排除于月份时间线 | 真实用户反馈和持续回归 |
| M4 社交 | 独立适配器、字段映射样例、独立视图及 not connected 状态 | 真实社交导出、统计对账与问答验收 |
| M5 RAG | 关键词/向量检索、付费回答、原文区间引用、预算；Lingua；0.2.4 等长分句视图保留 PDF 引文上下文 | 语义充分性、回答聚焦、语言不确定性与跨库验证 |
| M6 评价 | 20 开发题＋20 验收草案；当前版本 15 段开发 gold 前置校验有效；0.2.4 全套 245 项通过；另有独立两题 PDF-265 smoke | 草案审题、冻结与独立人工语义验收；7 个社交/跨库题尚未运行，两题 smoke 不替代原题库 |
| M7 部署 | 本机 PostgreSQL+pgvector、生产服务、预算、限额；当前275条快照已恢复到新库，9张表及序列/结构一致，177条存储引用定位有效，本机健康通过 | 固定域名/Tunnel 及另一网络的公众验收 |
| M8 交接 | 0.2.5 源码、依赖锁、回归测试与文档；0.2.4源码和wheel从空测试库复现275/263/226/558；0.2.5 wheel安装和三个路由通过，完整工程测试253项；0.2.2演示保留历史快照 | 源码包交付以最终manifest核对；指定GitHub、完整双数据集最终展示、客户与交接验收 |

## 当前生成与交接验证

0.2.5的[Dashboard修复报告](../reports/dashboard_consistency_v0_2_5.md)记录界面回归；[当前备份恢复报告](../reports/backup_restore_v0_2_4.md)记录旧版本引用和账本保留。本次没有改变检索、生成或题库，没有重新调用付费模型。

见 [0.2.4 报告](../reports/quote_context_v0_2_4.md)、[AI 审阅](../reports/assisted_semantic_review_v0_2_4.md)和 [21 条人工审查表](../reports/citation_review_v0_2_4.csv)。原开发集 13 题运行、7 题 pending；19/19 引文定位、2/2 计数、3/3 无证据拒答。独立 PDF 两题的完整引文已改善，行动主体归因错误仍未消除。人审列为空，整体尚未验收。下文 0.2.3/0.2.2 结果保留历史口径。

## 查看证据

- [当前 PDF-265 局部恢复](../reports/pdf265_body_recovery.md)、[本轮发布与定位检查](../outputs/pdf265_publication_validation_20260916.json)。原 PDF 和抽取文本需另行提供，哈希与提取命令见恢复报告。
- [历史数据修订与测试](../reports/data_revision_v0_2.md)、[历史重复导入](../outputs/native_import_v0_2_published_repeat_20260916.json)、[历史源数据验证](../outputs/source_revision_v0_2_20260916.json)。
- [12 URL 审阅](../reports/additional_url_review.md)、[20 正文边界审阅](../reports/prefix_boundary_review.md)。报告记录审阅当时的建议；本期应用结果见上述修订报告。
- [AI 语义复核](../reports/assisted_semantic_review_v0_2.md)、[14 行人工复核表](../reports/citation_review_v0_2.csv)：人工列空白。
- [0.2.1 语言修复及开发诊断](../reports/language_guard_v0_2_1.md)、[本次 AI 复核](../reports/assisted_semantic_review_v0_2_1.md)、[16 行人工复核表](../reports/citation_review_v0_2_1.csv)：人工列仍空白。
- [运行与交接](handoff.md)、[数据字典](data_dictionary.md)、[评价协议](evaluation_protocol.md)。
- [0.2.2 改动与结果](../reports/claim_contract_v0_2_2.md)、[本次 AI 复核](../reports/assisted_semantic_review_v0_2_2.md)、[16 行人工表](../reports/citation_review_v0_2_2.csv)、[94 项截断预检](../reports/truncation_recovery_preflight.md)。

0.2.3 [两题定向 smoke](../outputs/pdf265_recovery_paid_smoke_20260916.json) 的 run_id 为 `6c250056841b47feab178ffcc95bf2bd`，绑定当前 `5114…`。两题 answered，支持段 2/2、证据定位 6/6、引用定位 2/2、语言 match 2，`overall_pass=null`。第二答仍把展示技术的主体写成 `the advertisement has shown`，不能标为语义通过。该运行使用独立文件 `eval/pdf265_recovery_smoke.jsonl`；即使模板 `suite=development`，也不属于原 20 题开发集，不替代 20 题验收草案或人审。

历史 0.2.2 付费诊断 `d26eb540a6114cfe9672a755c43f39a7` 绑定旧数据 `d85…`：记录命中 8/8、支持片段 13/13、引用定位 16/16、拒答 3/3；语言 8 match，`overall_pass=null`。该轮 dev-01/07 补上了归因和蓝氢对象，但回答聚焦与完整性仍有审阅项。0.2.2 的 52 项针对性测试、0.2.1 的 164 项全套测试均保留历史口径。较早错语及表达失败不删除，不能称已完成语义验收。

0.2.2 PPTX／讲稿中的 554 块属于旧快照；当前为 558 块，未重做演示稿。真实社交、公开域名／Tunnel、指定 GitHub、人工与最终项目验收仍未完成；社交数据为空不计为通过。
