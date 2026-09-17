# CISS Advertising Observatory

面向 DS 549 FA26 项目的广告研究工具：浏览化石燃料原生广告，使用筛选与图表探索数据，并通过 RAG 问答返回可定位的原文证据。

**当前版本：0.3.1，原生广告研究预览。** 句界索引与生成前引用去重已启用，数据页已增加全量赞助方×媒体交叉表、历史标签分布、年度统计和记录详情；线框图入口移至页脚。真实社交数据、正式公网部署及人工语义验收仍待完成。本期以 Dashboard、证据问答和工程交接为主，CLAIMS 后端重建及动物农业数据扩展属于后续工作。

本机直接使用：[查询](http://127.0.0.1:8050/query) · [数据](http://127.0.0.1:8050/data) · [项目线框图](http://127.0.0.1:8050/wireframe)。查询和数据共享筛选；切页保留结果，筛选变化后旧结果会提示重新检索。

最新改动与保留缺口见 [0.3.1 研究任务修订](reports/research_ui_v0_3_1_20260917.zh-CN.md)。本地归档已接入 1 份核验 PDF，其余标题关联候选需继续核验。

## 从这里开始

| 你要做什么 | 阅读入口 |
| --- | --- |
| 找到全部说明、报告和历史资料 | [文档总索引](docs/DOCUMENT_INDEX.zh-CN.md) · [可排序文档清单](docs/document_catalog.csv) |
| 核对原文要求与完成情况 | [FA26 要求核对](reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md) · [实施与验收状态](docs/acceptance_status.md) |
| 使用网页、筛选或提问 | [用户指南](docs/user_guide.md) |
| 接手运行、数据更新和维护 | [交接说明](docs/handoff.md) · [运行维护](docs/operations.md) |
| 理解字段、来源和系统结构 | [数据字典](docs/data_dictionary.md) · [架构说明](docs/architecture.md) |
| 判断附件中哪些资料有用 | [三个附件的用途清单](reports/ARCHIVE_REUSE_REVIEW_20260916.zh-CN.md) · [完整资源附录](FA26_RESOURCE_APPENDIX.zh-CN.md) |
| 找具体广告 PDF 和来源网址 | [PDF 阅读指南](PDF_ARCHIVE_GUIDE.zh-CN.md) · [逐篇 PDF 目录](PDF_SOURCE_INDEX.zh-CN.md) |
| 审查模型回答是否合格 | [评价协议](docs/evaluation_protocol.md) · [人工审查表](reports/citation_review_v0_2_4.csv) |
| 核对句界索引、三页网页和回退 | [0.3.0 发布记录](reports/release_v0_3_0_20260917.zh-CN.md)；[此前的只读比较](reports/rag_chunking_review_20260916.zh-CN.md)保留历史指标 |

推荐阅读顺序：**本 README → 文档总索引 → FA26 要求核对 → 对应的使用或交接文档**。

## 目前能做什么

| 功能 | 状态与边界 |
| --- | --- |
| 原生广告 Dashboard | 已实现日期、媒体、Sponsor / advertiser、关键词和历史标签筛选，包含标数字的全量交叉表、历史标签图、年度图、记录详情与筛选结果导出。公司和赞助方当前共用字段，研究口径仍需确认。 |
| 免费关键词搜索 | 返回当前检索范围内的原文片段，不调用付费模型。返回数量是本次选出的片段数，不是全库命中总数或事实确认数量。 |
| 付费证据问答 | 使用检索证据生成回答，保存正文版本、引用位置和费用记录。引用可定位不等于回答语义已通过验收。 |
| 历史 CLAIMS 标签 | 使用前届保存的标签，并核对 URL 与正文版本；不是当前系统重新运行分类模型。 |
| 社交广告 | 页面和适配接口已有，真实语料未接入，界面显示 `not connected`。 |
| 对外部署与交付 | 本机研究预览已有运行证据；指定 GitHub、最终云端环境和客户验收尚未完成。 |

### 数据快照

以下为 2026-09-17 发布后的快照，不是每次打开 README 时的实时查询。

| 指标 | 数量 |
| --- | ---: |
| 收录记录 | 275 |
| 可统计记录 | 263 |
| 可检索正文 | 226 |
| 当前原文片段 | 556（sentence600-v1） |

正文版本 `source_data_version`：`5114ebc1cf9afe59cdaa715e3ea45166`，本轮未变。旧 558 块索引保留；健康检查的 `data_version` 现包含索引版本，完整标识见 [0.3.0 发布记录](reports/release_v0_3_0_20260917.zh-CN.md)。统计、检索资格不同，不能把文件数、记录数和有效广告数混用。来源与准入见 [数据字典](docs/data_dictionary.md)；项目交付差距见 [要求核对](reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md)。

## 在现有环境中启动

以下命令从**项目根目录**的 PowerShell 执行。日常启动使用现有数据库，不需要重新导入数据。这个前台入口也适用于不允许执行 `.ps1` 文件的终端。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py start
.\.venv\Scripts\python.exe -m observatory.cli serve
```

第二条命令保持终端运行。打开 [本机网页](http://127.0.0.1:8050/)；健康检查入口为 [/healthz](http://127.0.0.1:8050/healthz)。以上网址使用默认端口，端口改动时以 `.env` 的 `OBS_PORT` 为准。

停止前台网页用 `Ctrl+C`；停止数据服务：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py stop
```

允许执行本地脚本的 PowerShell 也可使用后台托管入口：

```powershell
.\scripts\Start-Observatory.ps1
.\scripts\Test-Observatory.ps1
```

托管入口用 `scripts/Stop-Observatory.ps1` 停止网页，用 `scripts/Stop-Postgres.ps1` 停止数据服务。新机器重建、运行配置及备份恢复请按 [交接说明](docs/handoff.md) 操作；运行方式详见 [运行维护](docs/operations.md)。

## 系统和数据入口

| 部分 | 当前实现 | 入口 |
| --- | --- | --- |
| 网页与图表 | Python、Dash、Plotly、Dash AG Grid、Waitress | [app.py](src/observatory/app.py) |
| 数据校验与导入 | pandas、Pandera、Pydantic，来源与版本记录 | [ingest.py](src/observatory/ingest.py) · [数据字典](docs/data_dictionary.md) |
| 存储和检索 | PostgreSQL、pgvector、关键词与向量检索 | [schema.sql](src/observatory/schema.sql) · [db.py](src/observatory/db.py) |
| 回答与证据检查 | OpenAI SDK、原文区间引用、语言与预算控制 | [rag.py](src/observatory/rag.py) · [架构](docs/architecture.md) |
| 环境和依赖 | Python 3.12/3.13；依赖锁定在 `uv.lock` | [pyproject.toml](pyproject.toml) · [配置示例](.env.example) |

日常使用流程：**选择数据集 → 设置筛选 → 查看图表与明细 → 搜索证据或生成回答 → 回到原文核对**。

原生输入主要包括基线 CSV、披露与质量元数据 XLSX、增补候选 CSV、历史标签及指定的 PDF 正文恢复材料。完整文件路径、关联方式和优先级见 [数据字典](docs/data_dictionary.md)。

数据更新需要注意：

- `import-native` 使用完整快照语义，不能把小批样本当作完整数据集替换。
- `config/native_admissions.json`、`config/native_body_ranges.json`、`config/native_body_recoveries.json` 共同约束准入、正文范围和恢复材料；所需源文件需与记录的哈希一致。
- `index` 和 `answer` 命令可能调用付费 API；数据更新和预算核对的步骤见 [运行维护](docs/operations.md)。
- `sources/`、`analysis/`、`outputs/`、运行时、凭据和备份属于另行管理的本地材料；仅取得代码仓库不等于取得这些输入。文档索引会标明这一点。

## 验证与评价

离线工程检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not integration and not live"
.\.venv\Scripts\python.exe -m ruff check src tests scripts
```

数据库集成检查使用独立测试库，操作步骤见 [交接说明](docs/handoff.md)。真实 API 评价与人工复核按 [评价协议](docs/evaluation_protocol.md) 进行。

当前证据入口：

- [0.3.1 研究任务修订](reports/research_ui_v0_3_1_20260917.zh-CN.md)：精确交叉表、详情与归档状态、免费缺词诊断、英文导航和验证边界。

- [0.3.0 句界索引与三页发布](reports/release_v0_3_0_20260917.zh-CN.md)：366 项非 live 测试、真实索引切换、两次开发题 API 检查及已发现的引用语义问题；不是独立性能或人工验收。
- [0.2.5 Dashboard 一致性检查](reports/dashboard_consistency_v0_2_5.md)：界面与工程结果。
- [0.2.4 引文上下文与复现报告](reports/quote_context_v0_2_4.md)：前一版本的付费生成与隔离导入证据，保留原版本。
- [评价运行汇总](reports/evaluation.md)：区分开发题、验收草案和独立诊断题；其“当前”表述按该报告的编制版本理解。
- [人工审查表](reports/citation_review_v0_2_4.csv)：人工列尚未完成，不把自动检查或 AI 辅助审阅当作人工验收。

历史测试数字、模型运行和数据版本保留在对应报告中。报告存在不代表本轮重新执行；工程检查通过也不等于研究结论或回答质量已经通过客户验收。

## 部署与下一步

FA26 原文在 Preferred Tech Stack 中列出 Railway；仓库已有 [Cloudflare Tunnel 模板](config/cloudflared.example.yml)。最终环境尚待落实，模板本身不代表已完成公网发布。

当前优先事项：

1. 完成应用构建配置、云端数据迁移准备与外部访问验证。
2. 取得真实社交导出，验证字段映射、统计及跨数据集问答。
3. 核对影响使用的正文与归档问题，完成回答语义和客户审阅。
4. 提交指定 GitHub，更新最终演示及交接记录。

详见 [FA26 要求核对](reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md)。CLAIMS 后端重建不作为这些交付工作的前置条件。

## 项目目录与文档维护

```text
README.md             项目总入口
 docs/                当前使用、技术、运行与交接文档
 reports/             按版本保留的审计、测试和评价证据
 config/              数据准入、正文范围及映射配置
 src/observatory/     应用源码
 scripts/             启动、维护、提取及交接工具
 tests/、eval/         工程检查和问答评价材料
 sources/             原始资料与恢复文本，另行提供
 analysis/            历史阅读与分析材料，本地保存
 outputs/             原始运行结果，本地保存
 deliverables/        打包交付与历史演示
```

新增文档时，在 [总索引](docs/DOCUMENT_INDEX.zh-CN.md) 中登记用途、版本和适用范围，并更新 [文档清单](docs/document_catalog.csv)。改变数据或评价结果时保留原报告，新建带版本的记录；README 只保留当前入口和必要概况。

旧版计划、阅读摘录和演示稿按其原日期理解。文档中的研究背景、旧指令或模板内容不自动成为本期新增要求。需求是否完成，以原始要求、对应实现和验收证据共同判断。
