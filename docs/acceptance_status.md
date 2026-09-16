# 实施与验收状态 — 0.2.2

更新日期：2026-09-16。当前原生数据版本 `d85a98002e4493f0376c260ad82253ee`，应用在本机运行；完整 M1–M8 目标仍未完成。用户暂缓提供的外部资料继续预留。

| 模块 | 当前证据 | 尚未完成 |
|---|---|---|
| M1 数据 | 275 条版本记录；12 项候选的 7/4/1 决定已应用；重复导入 275 unchanged / 0 new_versions / 0 deactivated，原值保留 | 社交真实映射、待核候选补证及持续维护 |
| M2 正文 | 263 可统计、226 可检索；20 项边界与 26 个导航块已审阅并应用；554 个块逐一验证，旧 79 个定位有效 | 原有 94 项截断疑点仍未补齐；PDF 对应与原网页完整性不自动认证 |
| M3 Dashboard | 六字段、筛选、统计、导出、历史标签；浏览器显示新统计，Southern Company 单组 5 条、媒体 8 个 | 真实用户反馈和持续回归 |
| M4 社交 | 独立适配器、字段映射样例、独立视图及 not connected 状态 | 真实社交导出、统计对账与问答验收 |
| M5 RAG | 关键词/向量检索、付费回答、原文区间引用、预算；Lingua；逐条来源与数量表达要求 | 语义充分性、回答聚焦、语言不确定性与跨库验证 |
| M6 评价 | 20 开发题＋20 验收草案；当前版本 15/17 段 gold 前置校验有效；0.2.1 全套 164、0.2.2 针对性 52 通过 | 草案审题、冻结与独立人工语义验收；7 个社交/跨库题尚未运行 |
| M7 部署 | 本机 PostgreSQL+pgvector、生产服务、预算、限额、备份恢复脚本；本机健康通过 | 固定域名/Tunnel 及另一网络的公众验收 |
| M8 交接 | 0.2.2 源码、依赖锁、配置、wheel、文档及更新的研究预览 | 指定 GitHub、完整双数据集最终展示、客户与交接验收 |

## 查看证据

- [当前数据修订与测试](../reports/data_revision_v0_2.md)、[重复导入](../outputs/native_import_v0_2_published_repeat_20260916.json)、[当前源数据验证](../outputs/source_revision_v0_2_20260916.json)。
- [12 URL 审阅](../reports/additional_url_review.md)、[20 正文边界审阅](../reports/prefix_boundary_review.md)。报告记录审阅当时的建议；本期应用结果见上述修订报告。
- [AI 语义复核](../reports/assisted_semantic_review_v0_2.md)、[14 行人工复核表](../reports/citation_review_v0_2.csv)：人工列空白。
- [0.2.1 语言修复及开发诊断](../reports/language_guard_v0_2_1.md)、[本次 AI 复核](../reports/assisted_semantic_review_v0_2_1.md)、[16 行人工复核表](../reports/citation_review_v0_2_1.csv)：人工列仍空白。
- [运行与交接](handoff.md)、[数据字典](data_dictionary.md)、[评价协议](evaluation_protocol.md)。
- [0.2.2 改动与结果](../reports/claim_contract_v0_2_2.md)、[本次 AI 复核](../reports/assisted_semantic_review_v0_2_2.md)、[16 行人工表](../reports/citation_review_v0_2_2.csv)、[94 项截断预检](../reports/truncation_recovery_preflight.md)。

最新付费诊断 `d26eb5…` 绑定当前 `d85…`：记录命中 8/8、支持片段 13/13、引用定位 16/16、拒答 3/3；语言 8 match，`overall_pass=null`。本轮 dev-01/07 补上了归因和蓝氢对象，但回答聚焦与完整性仍有审阅项。较早错语及表达失败均保留，不能称已完成语义验收。社交数据为空不计为通过。
