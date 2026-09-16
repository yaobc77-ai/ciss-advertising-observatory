# CISS Observatory 当前交接说明

更新日期：2026-09-16。当前版本为 **0.2.3 / Research preview / Native corpus connected**。最新数据状态以 [PDF-265 有限正文恢复](../reports/pdf265_body_recovery.md)和 [发布验证](../outputs/pdf265_publication_validation_20260916.json)为准。[回答表达报告](../reports/claim_contract_v0_2_2.md)、[语言修复报告](../reports/language_guard_v0_2_1.md)与 [先前数据修订](../reports/data_revision_v0_2.md)保留各自历史版本。

## 1. 接手入口

| 入口 | 用处 |
|---|---|
| [README](../README.md) / [实施与验收状态](acceptance_status.md) | 启动入口、M1–M8 的已完成证据与剩余验收 |
| [数据字典](data_dictionary.md) / [架构](architecture.md) | 来源、字段、版本、资格规则和处理流程 |
| [运行指南](operations.md) / [用户指南](user_guide.md) | 本机维护、预算、筛选、导出和证据检查 |
| [评价协议](evaluation_protocol.md) | 题库、分母、草案边界及人工复核工作 |
| [0.2.2 AI 辅助语义审阅](../reports/assisted_semantic_review_v0_2_2.md) | 旧 `d85…` 数据运行的语义观察，不能替代当前人审 |
| [0.2.2 研究预览 PPTX](../deliverables/research_preview_v0_2_2.pptx) / [中文讲稿](../deliverables/demo_script_v0_2_2.zh-CN.md) | 保留 554 块的历史演示；当前 0.2.3 数据为 558 块，未重做演示稿 |
| [94 项截断预检](../reports/truncation_recovery_preflight.md) / [PDF-265 恢复报告](../reports/pdf265_body_recovery.md) | 从候选到单篇有限续文的审核、来源哈希与可复现提取命令；仍非完整全文 |

统一评估汇总入口为 [reports/evaluation.md](../reports/evaluation.md)，以其中明确记载的 run_id、数据版本、分母与人工状态为准。旧版研究预览中的三个早期 smoke 案例仍可展示，但不是最新开发集指标。

## 2. 当前可以使用的部分

真实原生语料已接入。导入快照为 275 条收录、263 条可计数、226 条合格检索正文。英文 Dash 页面提供六字段明细、公司/媒体数量和占比、时间分布、赞助关系、筛选导出、历史自动标签与来源链接配置。此前浏览器曾核对 `exxonmobil` 的 15 条筛选记录与 CSV 的 15 个不同 record_id 一致，本轮没有重新操作浏览器。

当前 558 个文本块包含 PDF-265 的有限续文。该记录的旧 CLAIMS 标签保存在旧版本及内部 `previous_body_annotations`，不挂到新正文做标签过滤。原有 94 项截断限制没有整体解除，该篇仍缺部分遮挡文字和图像内容。

免费 **Search keywords** 使用词项检索。**Generate paid answer** 使用服务器 OpenAI 接口、结构化筛选后的证据、引文检查与预算控制。数据库保存原文版本和偏移，历史引文对应其生成时的版本。历史 CLAIMS 保存标签已导入，本期没有重建其分类后端或训练分类模型。

社交适配器和独立界面已实现，真实语料尚未连接，页面明确显示 **not connected**。社交零条不能解释为真实世界没有广告，也不构成该模块验收。

## 3. 隔离环境与已有安装

当前机器已有 `.venv` 和 `.runtime/postgres`。**用户无需再次下载 PostgreSQL。** 重建时由 `Setup-Postgres.ps1` 自动取得锁定包，无需安装单独的系统数据库服务。版本与安装证据见 [local_postgres.md](local_postgres.md)。

0.2.3 wheel 已构建并在 `.runtime/package-check` 独立安装，以隔离 Python 检查包版本 0.2.3、Lingua 2.2.0，以及 `/healthz`、`/_dash-layout`、`/assets/observatory.css` 均返回 200。本机应用重启后健康检查为 `5114…`／558 块。尚未在另一台全新 Windows 机器上完成从零重装。

| 部分 | 本项目位置 / 默认监听 |
|---|---|
| Python 依赖 | `.venv/`，由 `pyproject.toml` 与 `uv.lock` 描述 |
| 数据库运行时 | `.runtime/postgres/`，锁定清单 `scripts/postgres-win64.lock.txt` |
| 数据库数据 | `.runtime/pgdata/`，主库 `observatory` |
| 数据库端口 | `127.0.0.1:55432` |
| 页面入口 | `http://127.0.0.1:8050` |
| 应用日志 | `.runtime/app.stdout.log`、`.runtime/app.stderr.log` |
| 数据库日志 | `.runtime/postgres.log` |

没有安装 Windows 服务，也没有修改系统 PATH。机器重启后需执行启动脚本。`.env`、运行时、凭据和数据库文件属于本机私有资料。

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

### 数据更新与付费边界

```powershell
.\.venv\Scripts\python.exe -m observatory.cli import-native --root .
.\.venv\Scripts\python.exe -m observatory.cli health
.\.venv\Scripts\python.exe -m observatory.cli search "biogas" --dataset native
```

原生导入按**完整快照**发布：本次缺失或隔离的旧记录会停用，历史保留。先检查完整输入和导入报告，再决定是否索引。社交导入默认增量，映射入口为 `config/social_mapping.example.json`。

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
| pySBD | quote catalog 的句界与字符跨度 | `clean=False` 保留原文，`char_span=True` 返回位置，程序逐条校验偏移；过长句才按有界窗口拆分 |
| Lingua 2.2.0 | 问题语言提示与生成说明的错语检查 | 固定版本、本地执行、无需额外模型调用；约 162.2 MiB 下载，不确定结果保留；详情见语言修复报告 |

pySBD 已接入 `src/observatory/rag.py`。最新句子组合最多 60 词，长句使用 60 词窗口和 15 词重叠。这些处理改善可定位引用的生成输入，是否充分支持回答仍需语义复核。依赖声明与解析版本分别见 [pyproject.toml](../pyproject.toml) 和 `uv.lock`。

## 6. 当前数据与生成诊断

当前数据版本为 `5114ebc1cf9afe59cdaa715e3ea45166`，275 条收录、263 条可统计、226 条可检索，558 个块。本轮只生成 PDF-265 对应记录的新版本，其余 274 条不变；重复导入 275 unchanged。558 个当前块、86 个历史证据定位和 15 段原开发 gold 前置校验有效。实际记录见 [发布验证](../outputs/pdf265_publication_validation_20260916.json)。

0.2.3 [两题定向 smoke](../outputs/pdf265_recovery_paid_smoke_20260916.json) 的 run 为 `6c250056841b47feab178ffcc95bf2bd`，绑定当前 `5114…`；两题 answered，所需片段 2/2、证据定位 6/6、引用定位 2/2，语言 match 2。smoke $0.00118708，加本轮 6 块 embedding $0.00002284，合计 $0.00120992。该检查使用独立文件 `eval/pdf265_recovery_smoke.jsonl`；模板 `suite=development` 不表示原 20 题开发集已重新运行，也不替代 20 题验收草案或人工评价。

第二答仍把展示技术的主体写成 `the advertisement has shown`，虽保留“河口仍需测试”的限定，仍须记录措辞问题。人审待完成，`overall_pass=null`。不能把两题定位通过或 AI 阅读作为语义验收。

历史 0.2.2 付费开发 run `d26eb540a6114cfe9672a755c43f39a7` 绑定旧 `d85…` 数据版本，8 个回答、2 个计数、3 个拒答，16 条引用可定位。语言检查 8 match；该轮 $0.01632325，未决预留 $0。原先的语言与数量表达失败结果仍保留。人工语义支持率未测量。

[0.2.2 AI 审阅](../reports/assisted_semantic_review_v0_2_2.md)与 [16 行复核 CSV](../reports/citation_review_v0_2_2.csv)保存该轮归因、单位对象、必要指代上下文及完整性意见；人工列为空。dev-01/07 在该轮补上了原缺口，dev-05 的额外背景及其他完整性项仍待审。7 个社交/跨库题保持 pending。语言检查与 schema 描述不能验证广告事实或替代语义审阅。

0.2.3 全套工程测试 **209 passed / 19.63 秒**。历史 0.2.2 的 52 项针对性回归和 wheel 安装冒烟、0.2.1 的完整 164 项测试保持原口径。旧报告的 268 条、93/138 项测试及较早生成成绩各自绑定历史快照，不替代当前结论。

## 7. 外部输入与剩余验收

| 待办 | 下一步需要 | 完成证据 |
|---|---|---|
| 社交数据 | 真实导出、字段说明、来源链接及所需原型资料 | 导入对账、真实图表、社交与跨库评价 |
| 指定 GitHub | 本期仓库和目标分支 | 可定位源码提交、依赖锁、测试和文档 |
| 固定公网入口 | Cloudflare Named Tunnel / 域名配置 | 另一网络上的 HTTPS、功能、预算与故障验证 |
| 人工语义验收 | 审题、冻结题库、独立判读答案与引用 | 带人工判定的验收记录和未解决失败 |
| 最终展示 | 双数据集与公众环境完成 | 最终演示和客户反馈，与当前 research preview 分开标记 |

CLAIMS 后端、动物农业扩展及模型训练不是本次预览的已实施内容。

## 8. 可携带源码包与 manifest

0.2.3 源码交接使用文件名 `deliverables/observatory-0.2.3-20260916.zip`。交付时核对包内 `CONTENTS.sha256` 中每个条目的哈希，以及包外同名 `.zip.sha256` 的整包哈希；本说明不替代实际清单核验。维护者可使用下面的命令生成新版本；脚本拒绝覆盖已有包，重建时另取新文件名：

```powershell
.\.venv\Scripts\python.exe scripts/build_handoff.py --output deliverables/observatory-0.2.3-20260916.zip
```

`dist/ciss_observatory-0.2.3-py3-none-any.whl` 已构建并完成独立安装检查，包版本、语言库、健康路由、布局和 CSS 均已验证，SQL 与静态资源包含在包内。该验证不是新机器完整导入或公网部署验收。0.2.2 wheel 的原验证记录保留为历史证据。

采用显式允许清单：源码、测试、脚本、锁文件、配置样例、文档、20+20 问题草案、经审查的评估/复核文件及研究预览。可以单独纳入选定开发运行 JSON 作为证据，但它包含用户提供广告的原文片段，属于随包的研究材料，不能说是无语料的纯源码包。包内是否包含某个运行或历史记录，以 `CONTENTS.sha256` 为准。

排除 `.env`、真实凭据、`.runtime/`、`.venv/`、原始语料目录 `sources/`、批量 `outputs/`、`analysis/`、备份、日志和临时构建目录。选定运行 JSON 是允许清单中的明确例外，不递归打包整个 outputs。`.gitignore` 仍忽略 outputs，源码归档的选择不自动改变未来 Git 提交范围。

打包时只将指向实际已随包文件的本机绝对链接改为相对链接；原始报告不被改写。其余本地绝对路径只适用于原工作区。包外原始语料、备份和历史运行链接可能不可用；新机器应根据数据字典单独取得授权来源，再由 setup 脚本重建环境。manifest 可以记录文件相对路径、用途、哈希与版本，不应写入秘密值。这里不创建远程仓库、不上传数据，也不替用户确认公网发布完成。
