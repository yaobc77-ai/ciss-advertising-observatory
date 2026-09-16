# 0.1.1 源码交接包 v2 清单与链接验证

日期：2026-09-16。**v2 的文件清单与包内链接检查通过，v1 发现的演示 JSON 遗漏和包内目标绝对路径问题均已修复。** 本次只读取打包脚本和新 ZIP，没有再次安装依赖、运行测试、连接数据库或调用模型。

## 检查对象

| 项目 | 结果 |
|---|---|
| 文件 | `deliverables/observatory-research-preview-20260916-v2.zip` |
| 项目版本 | `0.1.1`，读取包内 `pyproject.toml` |
| 文件大小 | 795,586 bytes |
| SHA-256 | `b4e0e64eb80755dbf39280b1407be2751ed30b65ef71584e3736e9f6a3bdec5d` |
| ZIP 条目 | 91，含 `CONTENTS.sha256` |
| manifest 载荷 | 90 / 90 条目全覆盖，所有 SHA-256 一致 |
| 包外 `.zip.sha256` | 与实际压缩包哈希一致 |
| CRC、重复条目、路径检查 | 通过，无损坏、重复条目或路径逃逸 |

此报告生成于 ZIP 之后，未包含在该包内，避免报告和包哈希相互引用。报告不要求重建该 ZIP。此前完整源码隔离安装的事实仍见 [v1 验证记录](handoff_validation.md)，其 74 项离线测试结论绑定 v1，不冒称本轮重新执行了 0.1.1 测试。

## 新增材料与必要依赖

| 材料 | 包内检查 |
|---|---|
| 最新开发运行 | `outputs/development_paid_citation_first_20260916.json` 存在，run_id `0369cb87f07648359dccd28687598a6b` |
| 最新 AI 审阅 | `reports/assisted_semantic_review_citation_first.md` 存在 |
| 最新引用复核表 | `reports/citation_review_citation_first.csv` 为 17 行，与新运行的 17 条 citation 数一致，全部 `human_verdict` 为空 |
| 12 个额外 URL 审核 | `reports/additional_url_review.md` 与 `.csv` 均存在，CSV 12 行 |
| 缺失拒答样例 | `outputs/live_no_evidence.json` 已纳入，状态 `insufficient_evidence` |
| 开发/验收草案 | 两个 `eval/*.jsonl` 各 20 题，路径存在 |
| 代码与资源 | `schema.sql`、UI CSS/JS、启动/停止脚本、`Setup-TestDatabase.ps1`、`uv.lock` 均存在 |

当前运行仍标记 `draft_not_frozen`，`semantic_support` 为 `pending_human_review`。本次只确认交接材料、结构和对应数量，不评定答案语义、不决定新增 URL 入库，也不把复核 CSV 的存在算作人工验收。

## Portable links 与 manifest 逻辑

只读审查 `scripts/build_handoff.py` 的处理顺序：

1. 先生成允许清单和各条目原始字节。
2. 只把**精确目标已纳入该包**的工作区绝对 Markdown 链接改成相对路径，不改写原工作区文件或包外来源。
3. 对转换后的实际入包字节计算 `CONTENTS.sha256`。
4. 以独占创建模式写新 ZIP，再读取条目校验，并生成压缩包整体哈希。

该顺序没有发现阻塞本包正确性的明显问题。当前转换器处理 `](<绝对路径>)` 形式，对本次已有引用适用；它不是适用于任意 Markdown 语法、大小写或路径别名的通用转换器。

实际包内结果：

- **127 处相对 Markdown 链接，0 处缺失目标。** v1 的三处拒答样例断链已消失。
- **19 处转换**与原工作区中的对应链接逐项核对，均正确指向包内相对目标。
- **0 处绝对链接仍指向已随包目标。** 当前和历史 AI 审阅中的 CSV、运行 JSON、development 草案，以及额外 URL 审核报告引用均可在包内解析。
- 仍有 **489 处包外绝对链接**，指向原始资料、历史审计或工作区附件。它们保留原来的来源记录，不属于自包含资料。交接文档已说明新机器需另行取得授权源数据，不能将评估 JSON 充当完整原生基线数据。

## 结论边界

v2 清单、哈希、重点材料和包内本地链接已核对。没有重跑锁定安装、工程测试、PostgreSQL 初始化/恢复、付费问答或公众网络验收。代码测试与模型诊断应引用各自实际运行记录；本报告仅补充该压缩包的可携带材料检查。
