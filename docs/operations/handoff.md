# CISS Observatory 当前交接说明

当前交接入口已改为 [current_handoff.md](current_handoff.md)：包含 0.4.5 的 CLAIMS2 审核导入、format-2 评价输入与源码包。以下 0.4.1 及更早说明保留历史版本，不作为新版本的发布或验收依据。

0.4.1 修复初次图谱加载可能为空的回调竞态；当前状态见[发布记录](../reports/RELEASE_V0_4_0_20260930.zh-CN.md)，独立制品回执见[0.4.1复现](../reports/current_release_database_reproduction_v0_4_1_20260930.json)。以下0.4.0测试与规模基准保持其版本范围。

更新日期：**2026-09-30**。当前发布版本为 **0.4.1 / Research preview / Native corpus connected**。本机已实现集合知识图谱、实体占比与来源记录下钻、历史标签明细和语言模型选择共享只读工具；真实社交数据、正式 CLAIMS 判断与客户语义验收仍未完成。历史赞助方候选不等于已认证公司或商业合作，历史自动标签不等于已证实漂绿。

启用 `OBS_RESEARCH_AGENT_ENABLED=true` 后，Generate answer 先付费理解问题，再选择工具；关闭开关保留旧固定句式的无模型统计作为对照。同一执行器提供可选官方 SDK stdio MCP 服务。请先读 [MCP 接口与扩展](MCP_RESEARCH_TOOLS.zh-CN.md)、[图谱详情验证](../reports/GRAPH_DETAILS_V2_20260929.zh-CN.md)和下节运行契约。Railway 本轮设置已应用，0.4.1 的 CI、部署、迁移日志、健康版本与线上图谱流程见[本轮发布回执](../reports/release_v0_4_1_publication_20260930.json)。

**历史基线**：2026-09-17 的 0.3.1 界面修订记录 436 项非 live 测试通过，见[修订报告](../reports/research_ui_v0_3_1_20260917.zh-CN.md)。现有语料仍使用 556 个句界片段，旧 558 块索引保留，切换依据见[0.3.0 句界索引记录](../reports/release_v0_3_0_20260917.zh-CN.md)。此前的 [0.2.5 Dashboard 检查](../reports/dashboard_consistency_v0_2_5.md)、[0.2.4 付费生成与隔离导入](../reports/quote_context_v0_2_4.md)、[快照恢复验证](../reports/backup_restore_v0_2_4.md)均保留历史版本，不能代替 0.4.0 检查或当前全库恢复。下文旧源码包、演示、测试和费用按对应版本阅读，不视作本轮最终交付或客户验收。

## 0.4.1 发布运行契约

| 项目 | 接手时核对 |
|---|---|
| 制品与依赖 | [Dockerfile](../Dockerfile)固定 uv 0.12.7、Python 3.12，按 `uv.lock` frozen 安装，项目采用非 editable 制品；浏览器资源与 SQL 迁移均随包安装 |
| CI | [工作流](../.github/workflows/ci.yml)构建并安装 wheel，再以 `OBS_RELEASE_WHEEL` 核对资源和 CLI，并运行非 integration／live 工程测试；核对目标提交的实际成功记录，不能只检查 YAML |
| 已执行的独立复现 | [0.4.1 数据库回执](../reports/current_release_database_reproduction_v0_4_1_20260930.json)：实际 0.4.1 wheel，Python 3.12.14，本机 `obs_test` 的新随机 schema；迁移至 2、跨年 upsert、重复幂等、6 个句界片段定位与缺向量激活阻断通过，模型调用 0；0.4.0 旧回执保留 |
| 部署前迁移 | `/app/.venv/bin/observatory migrate`；先备份目标库，核对实际部署前日志和 `migration-status`，不重新导入资料、不自动计算 embedding |
| Railway UI 已应用设置 | Wait for CI 开启、健康路径 `/healthz`、超时 60 秒、上述部署前命令、`OBS_RESEARCH_AGENT_ENABLED=true`；后续更新仍需核对实际应用状态 |
| 线上识别 | `/healthz` 的 `application.version=0.4.1`、有效的 `application.commit` 与目标提交一致、`application.features` 符合目标；同时核对来源、索引、计数和片段数 |

`/healthz` 仅公开状态、收录数、片段数、活动 profile、来源／索引／组合版本，以及 application 的版本、有效 Git SHA 和三个 feature。无有效平台 SHA 时 commit 为 `null`，须从部署记录确认；接口不回传凭据、完整设置或内部路径。feature 表示功能／开关，不能证明真实数据完整或模型判断正确。

本轮 Railway UI 提示 config-as-code deprecated；[railway.json](../railway.json)是仓库中的目标契约，不能假定平台已采用。按[运行指南](operations.md#railway-040-发布配置与生效核对)检查已应用 UI 设置、构建、迁移、启动与健康日志。源码／环境开关／数据库分别核对；CI、部署连通和客户验收分别记录。

独立复现使用合成数据，未恢复生产 275 条语料、556 个片段的等价快照、生产向量、历史答案或用量账本；没有真实社交测试、客户语义验收或大规模性能结论。当前制品复现方法见 [CURRENT_RELEASE_REPRODUCTION.md](CURRENT_RELEASE_REPRODUCTION.md)。生产移交还需完整数据库备份、固定哈希的源资料／配置及核验 PDF、预览缓存；`.env`、密钥和备份通过私有渠道交接，预算预留和历史账本不能因升级清空。

## 1. 接手入口

| 入口 | 用处 |
|---|---|
| [README](../README.md) / [实施与验收状态](acceptance_status.md) | 启动入口、M1–M8 的已完成证据与剩余验收 |
| [数据字典](data_dictionary.md) / [架构](architecture.md) | 来源、字段、版本、资格规则和处理流程 |
| [运行指南](operations.md) / [用户指南](user_guide.md) | 本机维护、预算、筛选、导出和证据检查 |
| [评价协议](evaluation_protocol.md) | 题库、分母、草案边界及人工复核工作 |
| [0.2.2 AI 辅助语义审阅](../reports/assisted_semantic_review_v0_2_2.md) | 旧 `d85…` 数据运行的语义观察，不能替代当前人审 |
| [0.2.2 研究预览 PPTX](../deliverables/research_preview_v0_2_2.pptx) / [中文讲稿](../deliverables/demo_script_v0_2_2.zh-CN.md) | 保留 554 块的历史演示；现有活动索引为 556 块，不能当作 0.4.0 最终演示稿 |
| [94 项截断预检](../reports/truncation_recovery_preflight.md) / [PDF-265 恢复报告](../reports/pdf265_body_recovery.md) | 从候选到单篇有限续文的审核、来源哈希与可复现提取命令；仍非完整全文 |

统一评估汇总入口为 [reports/evaluation.md](../reports/evaluation.md)，以其中明确记载的 run_id、数据版本、分母与人工状态为准。旧版研究预览中的三个早期 smoke 案例仍可展示，但不是最新开发集指标。

## 2. 当前可以使用的部分

真实原生语料已接入。导入快照为 275 条收录、263 条可计数、226 条合格检索正文。英文 Dash 页面提供可打开详情的明细、赞助方/媒体数量和占比、完整 20×8 交叉表及导出、历史自动标签分布、年度柱图与单列 Unknown 的 22 条日期。当前筛选对应的明细是图表和交叉表共同的统计来源。CERAWeek 显示为会议/活动，纳入公司分母的规则待客户裁决；历史标签仍非人工金标准。

当前 556 个句界片段包含 PDF-265 的有限续文。该记录的旧 CLAIMS 标签保存在旧版本及内部 `previous_body_annotations`，不挂到新正文做标签过滤。原有 94 项截断限制没有整体解除，该篇仍缺部分遮挡文字和图像内容。记录详情展示实际存储正文和质量提示；只有这一篇具备核验本地 PDF 与首页图片，另有 254 条标题关联候选待核，公开 archive URL 仍为 0。部署时须携带核验源文件及预览缓存，维护命令见[运行指南](operations.md#已核验-pdf-与预览缓存)。

免费 **Search keywords** 使用词项检索。**Generate answer** 在启用研究开关后先用服务器 OpenAI 接口理解问题，选择共享只读工具；内容回答继续使用筛选后的证据、引文检查与预算控制。数据库保存原文版本和偏移，历史引文对应其生成时的版本。历史 CLAIMS 保存标签已导入，本期没有重建其分类后端或训练分类模型。

社交适配器和独立界面已实现，真实语料尚未连接，页面明确显示 **not connected**。社交零条不能解释为真实世界没有广告，也不构成该模块验收。

## 3. 隔离环境与已有安装

**2026-10-01 本机运行时更新**：当前机器使用 `.venv` 和 `.runtime/postgres18/`，数据库为 **PostgreSQL 18.6 + pgvector 0.8.6**，当前数据目录为 `.runtime/pgdata18/`。端口仍是 `127.0.0.1:55432`，主库仍是 `observatory`。重建脚本、编译前提和历史安装证据见 [local_postgres.md](local_postgres.md)。本节数据库运行时更新不改变下文应用历史发布记录的版本范围。

此次通过 `pg_upgrade --check` 与 copy 模式升级，保留原 13 个数据库、角色及权限。12 个可连接数据库的表行指纹、规范化结构、owner、序列和扩展一致；主库 21 张表、275 条 records，词项与存储向量检索、历史引用定位已对比。`.env` 与本机凭据文件字节哈希未变。详见 [PG18 升级报告](../reports/LOCAL_POSTGRES18_UPGRADE_20261001.zh-CN.md)及 [JSON 回执](../reports/local_postgres18_upgrade_20261001.json)。此证据覆盖本机升级，不表示已在全新机器从零重装。

0.4.1 wheel 在 `.runtime/current-release-venv` 的独立 Python 3.12.14 环境中安装并运行；不是从 editable 源码加载。实际迁移和默认 upsert 的新 schema 验证见上节 9 月 30 日回执。该环境与备份均不提交公开仓库；合成复现回执不能替代另一台新机器的完整源数据导入或生产灾备恢复。

此前 0.2.3 wheel 已构建并在 `.runtime/package-check` 独立安装，以隔离 Python 检查包版本 0.2.3、Lingua 2.2.0，以及 `/healthz`、`/_dash-layout`、`/assets/observatory.css` 均返回 200。本机应用重启后健康检查为 `5114…`／558 块。尚未在另一台全新 Windows 机器上完成从零重装。

| 部分 | 本项目位置 / 默认监听 |
|---|---|
| Python 依赖 | `.venv/`，由 `pyproject.toml` 与 `uv.lock` 描述 |
| 数据库运行时 | `.runtime/postgres18/`，锁定清单 `scripts/postgres-win64.lock.txt`（18 个包） |
| 数据库数据 | `.runtime/pgdata18/`，主库 `observatory` |
| 数据库端口 | `127.0.0.1:55432` |
| 页面入口 | `http://127.0.0.1:8050` |
| 应用日志 | `.runtime/app.stdout.log`、`.runtime/app.stderr.log` |
| 数据库日志 | `.runtime/postgres18.log` |
| 升级前副本 | `.runtime/postgres/`、`.runtime/pgdata/`，PG16 已停止并保留 |

没有安装 Windows 服务，也没有修改系统 PATH。机器重启后需执行启动脚本。`.env`、运行时、凭据和数据库文件属于本机私有资料。

新机器需先准备项目 Python 依赖及 **Visual Studio 2022 x64 C++ 编译工具／Windows SDK**。`Setup-Postgres.ps1` 安装锁定的 PostgreSQL 18 包，再由 `Install-Pgvector.ps1` 校验并构建上游 pgvector `v0.8.6`；源归档 SHA-256 与安装 DLL/SQL 哈希记录在 `.runtime/postgres18/pgvector-build.json`。不能复用原 PG16 的 pgvector DLL。已有旧集群时 Setup 会拒绝自动迁移；启动和停止脚本先核对当前二进制、数据大版本及解析 junction 后的集群目录。

## 4. 精确维护命令

下面命令从项目根目录的 PowerShell 执行。日常启动无需重新导入数据。

### 启动与健康检查

```powershell
.\scripts\Start-Observatory.ps1
.\scripts\Test-Observatory.ps1
.\scripts\Test-Postgres.ps1
```

第一条先启动项目数据库，再隐藏启动应用。第二条查询应用 `/healthz`，第三条检查数据库运行条件。打开 [本机页面](http://127.0.0.1:8050)。

需要前台日志时使用：

```powershell
.\scripts\Start-Postgres.ps1
.\.venv\Scripts\python.exe -m observatory.cli serve
```

前台运行用 Ctrl+C 停止。不要在同一端口并行启动两个实例。

### 停止

先结束导入、索引或评估等写入任务，再执行：

```powershell
.\scripts\Stop-Observatory.ps1
.\scripts\Stop-Postgres.ps1
```

第一条只停止启动脚本记录且身份匹配的应用进程，不关闭数据库，也不停止手动前台进程。第二条核对项目数据库目录后正常关闭集群，可能取消该项目仍活动的事务。

### 工程测试与免费开发诊断

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not integration and not live"
.\scripts\Start-Postgres.ps1
.\scripts\Setup-TestDatabase.ps1
.\.venv\Scripts\python.exe -m pytest -q -m "integration and not live"
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m observatory.evaluate --cases eval/development.jsonl
```

`Setup-TestDatabase` 准备固定的 `obs_test` 库和连接配置，已有库的重复执行已验证。集成测试读取 `OBS_TEST_DATABASE_URL`，数据库名必须以 `obs_test` 开头。它会清理该测试库业务表，不能填入主库连接。未配置而跳过不算通过。以上评价命令没有 `--paid`，不执行生成 API。正式验收草案应先由人审题和冻结。

### 备份与恢复

```powershell
.\scripts\Backup-Postgres.ps1
```

脚本生成新的时间戳备份及 SHA-256 记录。恢复时替换为它实际打印的文件路径，并选择尚不存在的新数据库名：

```powershell
.\scripts\Restore-Postgres.ps1 -BackupFile '.runtime\backups\实际备份文件.dump' -Database 'observatory_handoff_review'
```

`实际备份文件.dump` 是必须替换的占位。脚本拒绝主库和已有目标库，不自动切换应用连接。本机恢复验证记录见 [数据库运行文档](local_postgres.md)。旧备份只代表创建时刻，单数据库逻辑备份不包含运行环境或角色密码。

PG18 迁移前的完整私有备份位于 `.runtime/backups/pg16-before-pg18-20261001-complete/`，包含 12 个数据库 dump、全局角色导出以及配置、marker、项目 `.env` 副本，以私有 ACL 保护。原 PG16 数据目录也保留，但只是升级时刻快照，PG18 后续写入不会同步。回退应先保存并处理新增数据，按核对后的方案恢复旧配置、集群 marker 与脚本运行时路由；不能只替换二进制或直接重用数据目录。未执行旧集群删除脚本。

### 数据更新与付费边界

```powershell
.\.venv\Scripts\python.exe -m observatory.cli import-native --root .
.\.venv\Scripts\python.exe -m observatory.cli health
.\.venv\Scripts\python.exe -m observatory.cli search "biogas" --dataset native
```

9 月 25 日起，原生与社交导入默认 **upsert**，保留本批未出现的历史记录。仅对整个数据集的完整替换使用 `--mode snapshot`，此时缺失记录停用、历史保留。新来源先用 canonical JSONL 的 `import-records --dry-run` 检查，参见[导入与迁移说明](PROTOTYPE_DATA_PIPELINE.md)。先审查导入报告，再决定是否索引；社交 CSV 映射入口仍为 `config/social_mapping.example.json`。

CLI 同时要求 `native_admissions.json`、`native_body_ranges.json`、`native_body_recoveries.json` 三份配置。PDF 恢复清单绑定的原 PDF 与 UTF-8 抽取文本需要单独提供；缺失或哈希不符时导入停止，不会自动回退旧正文。[恢复报告](../reports/pdf265_body_recovery.md)给出锁定 `pypdf` 的可选提取命令，保留原字符和每页 `U+000C` 分隔。已有数据库的日常运行不需要重新提取 PDF。

下列命令调用付费 API，只在明确需要时执行，不属于普通启动或测试：

```powershell
.\.venv\Scripts\python.exe -m observatory.cli index
.\.venv\Scripts\python.exe -m observatory.cli answer "What does this archive say about carbon capture?"
.\.venv\Scripts\python.exe -m observatory.evaluate --cases eval/development.jsonl --paid
```

账本只读查询为 `.\.venv\Scripts\python.exe -m observatory.cli budget`。费用、缓存和未决预留的口径以 [operations.md](operations.md) 为准，早期 JSON 的单次费用字段不替代账本。

## 5. 复用包与维护选择

| 包 | 实际工作 | 复用理由与边界 |
|---|---|---|
| Dash / Plotly | Python 页面、回调和图表 | 界面与数据服务共用 Python，不另建前端工程 |
| Dash AG Grid | 六字段表、排序、分页和来源单元格 | 复用表格交互，项目维护公开字段及筛选导出规则 |
| pandas / Pandera | 表格读取、所需列与类型/URL 校验 | 显式保存数据契约；不认证赞助身份或正文完整性 |
| PostgreSQL / pgvector / psycopg | 事务、版本、词项和向量检索、预算账本 | 在一个数据库中先过滤再检索，当前精确向量无需额外服务 |
| OpenAI SDK / Pydantic | Responses 调用、结构化结果 | 使用官方客户端，项目保留提示、预算、引用和失败逻辑 |
| pySBD | quote catalog 的句界与字符跨度 | 0.2.4 使用等长分句视图，按返回位置切原文；空段/分页分开处理，过长句按有界窗口拆分 |
| Lingua 2.2.0 | 问题语言提示与生成说明的错语检查 | 固定版本、本地执行、无需额外模型调用；约 162.2 MiB 下载，不确定结果保留；详情见语言修复报告 |

pySBD 已接入 `src/observatory/rag.py`。最新句子组合最多 60 词，长句使用 60 词窗口和 15 词重叠。这些处理改善可定位引用的生成输入，是否充分支持回答仍需语义复核。依赖声明与解析版本分别见 [pyproject.toml](../pyproject.toml) 和 `uv.lock`。

## 6. 历史数据与生成诊断

本节保留 0.2.x 的测试、生成费用与快照检查。当前界面与生产验证见[0.4.1 发布报告](../reports/RELEASE_V0_4_0_20260930.zh-CN.md)，独立制品／合成数据库验证见上节；不要把本节旧 558 块结果标为当前 556 块检索或新版模型答案评价。

0.2.5完整工程回归253项通过（22.07秒），包含8个新增界面一致性案例；应用已重启，独立安装的0.2.5 wheel三个路由均200。浏览器未知日期筛选实测263/226/22→241/204/0。详见[当前Dashboard报告](../reports/dashboard_consistency_v0_2_5.md)。未重跑付费生成，下面结果保留0.2.4及更早版本。

0.2.4 全套 **245 项 / 19.03 秒**通过。原开发集重新执行 13 个原生题：8 个回答、2 个计数、3 个拒答，7 个社交/跨库题 pending；19/19 引用可定位，语义未验收。另两题 PDF smoke 的完整引文得到改善，但第二答仍错误地把行动主体写成广告。两次合计 $0.01798645，见 [报告](../reports/quote_context_v0_2_4.md)、[AI 审阅](../reports/assisted_semantic_review_v0_2_4.md)和 [21 条人工表](../reports/citation_review_v0_2_4.csv)。下文保留 0.2.3/0.2.2 历史记录。


0.2.3 当时的源数据版本为 `5114ebc1cf9afe59cdaa715e3ea45166`，275 条收录、263 条可统计、226 条可检索，558 个块。该次发布只生成 PDF-265 对应记录的新版本，其余 274 条不变；重复导入 275 unchanged。558 个当时的当前块、86 个历史证据定位和 15 段原开发 gold 前置校验有效。实际记录见 [发布验证](../outputs/pdf265_publication_validation_20260916.json)。

0.2.3 [两题定向 smoke](../outputs/pdf265_recovery_paid_smoke_20260916.json) 的 run 为 `6c250056841b47feab178ffcc95bf2bd`，绑定当前 `5114…`；两题 answered，所需片段 2/2、证据定位 6/6、引用定位 2/2，语言 match 2。smoke $0.00118708，加本轮 6 块 embedding $0.00002284，合计 $0.00120992。该检查使用独立文件 `eval/pdf265_recovery_smoke.jsonl`；模板 `suite=development` 不表示原 20 题开发集已重新运行，也不替代 20 题验收草案或人工评价。

第二答仍把展示技术的主体写成 `the advertisement has shown`，虽保留“河口仍需测试”的限定，仍须记录措辞问题。人审待完成，`overall_pass=null`。不能把两题定位通过或 AI 阅读作为语义验收。

历史 0.2.2 付费开发 run `d26eb540a6114cfe9672a755c43f39a7` 绑定旧 `d85…` 数据版本，8 个回答、2 个计数、3 个拒答，16 条引用可定位。语言检查 8 match；该轮 $0.01632325，未决预留 $0。原先的语言与数量表达失败结果仍保留。人工语义支持率未测量。

[0.2.2 AI 审阅](../reports/assisted_semantic_review_v0_2_2.md)与 [16 行复核 CSV](../reports/citation_review_v0_2_2.csv)保存该轮归因、单位对象、必要指代上下文及完整性意见；人工列为空。dev-01/07 在该轮补上了原缺口，dev-05 的额外背景及其他完整性项仍待审。7 个社交/跨库题保持 pending。语言检查与 schema 描述不能验证广告事实或替代语义审阅。

0.2.3 全套工程测试 **209 passed / 19.63 秒**。历史 0.2.2 的 52 项针对性回归和 wheel 安装冒烟、0.2.1 的完整 164 项测试保持原口径。旧报告的 268 条、93/138 项测试及较早生成成绩各自绑定历史快照，不替代当前结论。

## 7. 外部输入与剩余验收

| 待办 | 下一步需要 | 完成证据 |
|---|---|---|
| 社交数据 | 真实导出、字段说明、来源链接及所需原型资料 | 导入对账、真实图表、社交与跨库评价 |
| 本轮源码发布 | 已指定的 GitHub 仓库与目标提交的 CI、版本和发布回执 | 可定位提交、依赖锁、已安装制品测试和同步文档 |
| 现有 Railway 入口 | 0.4.1 已上线，实际设置、迁移日志、健康 metadata 和本轮浏览器流程已核对；Cloudflare 为可选方案 | 另一网络、并发、故障、完整恢复及客户使用验收 |
| 人工语义验收 | 审题、冻结题库、独立判读答案与引用 | 带人工判定的验收记录和未解决失败 |
| 最终展示 | 双数据集与公众环境完成 | 最终演示和客户反馈，与当前 research preview 分开标记 |

CLAIMS 后端、动物农业扩展及模型训练不是本次预览的已实施内容。

## 8. 可携带源码包与 manifest

0.2.5 源码交接使用文件名 `deliverables/observatory-0.2.5-20260916.zip`。0.2.4包保留原样。交付时核对包内 `CONTENTS.sha256` 中每个条目的哈希，以及包外同名 `.zip.sha256` 的整包哈希；本说明不替代实际清单核验。维护者可使用下面的命令生成新版本；脚本拒绝覆盖已有包，重建时另取新文件名：

```powershell
.\.venv\Scripts\python.exe scripts/build_handoff.py --output deliverables/observatory-0.2.5-20260916.zip
```

`dist/ciss_observatory-0.2.4-py3-none-any.whl` 已构建并完成独立安装检查，包版本、语言库、健康路由、布局和 CSS 均已验证，SQL 与静态资源包含在包内。该验证不是新机器完整导入或公网部署验收。0.2.2 wheel 的原验证记录保留为历史证据。

采用显式允许清单：源码、测试、脚本、锁文件、配置样例、文档、20+20 问题草案、经审查的评估/复核文件及研究预览。可以单独纳入选定开发运行 JSON 作为证据，但它包含用户提供广告的原文片段，属于随包的研究材料，不能说是无语料的纯源码包。包内是否包含某个运行或历史记录，以 `CONTENTS.sha256` 为准。

排除 `.env`、真实凭据、`.runtime/`、`.venv/`、原始语料目录 `sources/`、批量 `outputs/`、`analysis/`、备份、日志和临时构建目录。选定运行 JSON 是允许清单中的明确例外，不递归打包整个 outputs。`.gitignore` 仍忽略 outputs，源码归档的选择不自动改变未来 Git 提交范围。

打包时只将指向实际已随包文件的本机绝对链接改为相对链接；原始报告不被改写。其余本地绝对路径只适用于原工作区。包外原始语料、备份和历史运行链接可能不可用；新机器应根据数据字典单独取得授权来源，再由 setup 脚本重建环境。manifest 可以记录文件相对路径、用途、哈希与版本，不应写入秘密值。这里不创建远程仓库、不上传数据，也不替用户确认公网发布完成。


## 9. 历史 0.2.x 从空测试库复现快照

以下是旧 `verify_clean_import.py` 的固定原始数据复现方法，仍保留其清表警告与 558 块预期。当前独立安装／迁移验证使用 [verify_current_release.py](../scripts/verify_current_release.py) 和 [CURRENT_RELEASE_REPRODUCTION.md](CURRENT_RELEASE_REPRODUCTION.md)，在新随机 schema 中处理合成记录，不以本节旧成绩替代新版验证。

0.2.4 的 [源码安装结果](../outputs/clean_import_source_v0_2_4_20260916.json)与 [wheel 安装结果](../outputs/clean_import_wheel_v0_2_4_20260916.json)均通过。源码安装使用独立解包目录、CPython 3.13.3、包内 uv.lock；wheel 在独立 CPython 3.12.14 的 site-packages 中加载。两种方式以 `-I` 启动，并记录实际包路径和模块哈希。本机应用亦已重启，健康、布局和 CSS 路由通过。

在解包目录补入以下 **7 个私有输入**，保持相对路径。3 个 `config/native_*.json` 已随包；全部 10 个输入的 SHA-256 以 [发布清单](../outputs/pdf265_publication_validation_20260916.json)中的 `source_hashes` 为准。

| 相对路径 | 用处 |
|---|---|
| `sources/FA25_SP26/final_dataset_cleaned.csv` | 268 条基准数据 |
| `sources/Native Advertising Data/native_ad_dataset.xlsx` | 原始披露和质量备注 |
| `sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv` | 新增候选及采纳依据 |
| `sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv` | 历史标签及其版本依据 |
| `analysis/pdf_archive/source_index.json` | 归档对应和来源问题记录 |
| `sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/2018-12-28T10_21_52-0500_Usingmolluskstomonitorindustrialsites.pdf` | PDF-265 来源哈希核对 |
| `sources/recovered_native/PDF-265.pypdf-6.10.0.txt` | 固定抽取正文与原文坐标 |

不需要其余 PDF 或提取器即可导入当前快照；需要重新抽取时再安装可选 PDF 依赖。原始输入不会随源码 ZIP 自动提供。

安装源码环境后，运行 [verify_clean_import.py](../scripts/verify_clean_import.py)。它只允许数据库名严格为 `obs_test`，并逐连接核对实际库名。**此命令会清空该测试库的业务表**；不得与集成测试并行。它不会回退应用主库，不调用 API，也不生成 embedding。设置进程 `OBS_TEST_DATABASE_URL` 后执行：

```powershell
.\.venv\Scripts\python.exe -I -X utf8 scripts/verify_clean_import.py --root . --output outputs/clean-import-source.json
```

若已执行 `Setup-TestDatabase.ps1`，连接位于忽略的本机 `.env`，可用以下显式包装调用，仅向该进程载入测试连接，不在终端打印凭据：

```powershell
.\.venv\Scripts\python.exe -I -X utf8 -c "import os,runpy; from dotenv import dotenv_values; os.environ['OBS_TEST_DATABASE_URL']=dotenv_values('.env')['OBS_TEST_DATABASE_URL']; runpy.run_path('scripts/verify_clean_import.py',run_name='__main__')" --root . --output outputs/clean-import-source.json
```

上述两种命令二选一。输出文件使用独占创建，已有同名结果会阻止运行。检查 wheel 时换成独立 wheel 环境的 Python、指定解包目录和新的输出路径，再顺序执行一次。

预期首导 **275 new_versions / 0 unchanged**，重复导入 **0 / 275**；版本 `5114…`，计数 **275/263/226/558**；558 个块、15 段开发 gold 有效。它导入当前快照，不重建旧回答和旧正文版本；0.2.3 的 86 个历史引用核验属于原发布库证据。测试成功也不代表另一机器的 PostgreSQL 安装或公网验收完成。
