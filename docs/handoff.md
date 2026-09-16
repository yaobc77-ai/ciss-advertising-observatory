# CISS Observatory 当前交接说明

更新日期：2026-09-16。当前版本为 **0.2.1 / Research preview / Native corpus connected**。最新状态以 [语言修复报告](../reports/language_guard_v0_2_1.md) 和 [数据修订报告](../reports/data_revision_v0_2.md) 为准。

## 1. 接手入口

| 入口 | 用处 |
|---|---|
| [README](../README.md) / [实施与验收状态](acceptance_status.md) | 启动入口、M1–M8 的已完成证据与剩余验收 |
| [数据字典](data_dictionary.md) / [架构](architecture.md) | 来源、字段、版本、资格规则和处理流程 |
| [运行指南](operations.md) / [用户指南](user_guide.md) | 本机维护、预算、筛选、导出和证据检查 |
| [评价协议](evaluation_protocol.md) | 题库、分母、草案边界及人工复核工作 |
| [当前 AI 辅助语义审阅](../reports/assisted_semantic_review_v0_2_1.md) | 最新运行的语义观察，不能替代人工结论 |
| [研究预览 PPTX](../deliverables/research_preview.pptx) / [中文讲稿](../deliverables/demo_script.zh-CN.md) | 当前原生应用的展示步骤与保存样例 |

统一评估汇总入口为 [reports/evaluation.md](../reports/evaluation.md)，以其中明确记载的 run_id、数据版本、分母与人工状态为准。研究预览中的三个早期 smoke 案例仍可展示，但不是最新开发集指标。

## 2. 当前可以使用的部分

真实原生语料已接入。导入快照为 275 条收录、263 条可计数、226 条合格检索正文。英文 Dash 页面提供六字段明细、公司/媒体数量和占比、时间分布、赞助关系、筛选导出、历史自动标签与来源开关。浏览器曾核对 `exxonmobil` 的 15 条筛选记录与 CSV 的 15 个不同 record_id 一致。

免费 **Search keywords** 使用词项检索。**Generate paid answer** 使用服务器 OpenAI 接口、结构化筛选后的证据、引文检查与预算控制。数据库保存原文版本和偏移，历史引文对应其生成时的版本。历史 CLAIMS 保存标签已导入，本期没有重建其分类后端或训练分类模型。

社交适配器和独立界面已实现，真实语料尚未连接，页面明确显示 **not connected**。社交零条不能解释为真实世界没有广告，也不构成该模块验收。

## 3. 隔离环境与已有安装

当前机器已有 `.venv` 和 `.runtime/postgres`。**用户无需再次下载 PostgreSQL。** 重建时由 `Setup-Postgres.ps1` 自动取得锁定包，无需安装单独的系统数据库服务。版本与安装证据见 [local_postgres.md](local_postgres.md)。

已构建 wheel，并在隔离的安装路径验证 `/healthz`、`/_dash-layout`、`/assets/observatory.css` 返回 200。这是包安装冒烟检查，尚未在另一台全新 Windows 机器上完成从零重装。

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

当前数据版本为 `d85a98002e4493f0376c260ad82253ee`，275 条收录、263 条可统计、226 条可检索，554 个块。最终重复导入 275 unchanged / 0 new_versions / 0 deactivated；275 条正文、554 个区间块及 79 个历史定位通过检查。实际记录见 [数据修订报告](../reports/data_revision_v0_2.md)。

最新付费开发 run `612863daa16a48dcb3a2b1179eb3479d` 绑定当前 `d85…` 数据版本，8 个回答、2 个计数、3 个拒答，16 条引用可定位。语言检查 7 match、1 inconclusive；本轮 $0.01567250，未决预留 $0。旧 `532453… / c5ad…` 的三条错语结果仍保留。人工语义支持率未测量。

[AI 审阅](../reports/assisted_semantic_review_v0_2_1.md)与 [16 行复核 CSV](../reports/citation_review_v0_2_1.csv)保存本次归因、单位对象、必要指代上下文及完整性意见；人工列为空。7 个社交/跨库题保持 pending。语言检查已实现；它不验证引用语义或广告事实。

0.2.1 工程全套 164 项通过，独立 wheel 安装冒烟通过。旧报告的 268 条、93/138 项测试及较早生成成绩各自绑定历史快照，不替代当前结论。

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

本次交接包为 `deliverables/observatory-0.2.1-20260916.zip`，包内 `CONTENTS.sha256` 记录每个条目的哈希，包外同名 `.zip.sha256` 用于检查整个压缩包。生成后逐项重新读取压缩条目并核对字节。维护者可使用下面的命令生成新版本；脚本拒绝覆盖已有包，重建时另取新文件名：

```powershell
.\.venv\Scripts\python.exe scripts/build_handoff.py --output deliverables/observatory-0.2.1-20260916.zip
```

另已构建 `dist/ciss_observatory-0.2.1-py3-none-any.whl`，在独立检查环境安装后，语言库可用，健康、页面布局和CSS均返回HTTP 200，SQL与静态资源包含在wheel中。该验证不是新机器完整导入和公网部署验收。

采用显式允许清单：源码、测试、脚本、锁文件、配置样例、文档、20+20 问题草案、经审查的评估/复核文件及研究预览。可以单独纳入选定开发运行 JSON 作为证据，但它包含用户提供广告的原文片段，属于随包的研究材料，不能说是无语料的纯源码包。包内是否包含某个运行或历史记录，以 `CONTENTS.sha256` 为准。

排除 `.env`、真实凭据、`.runtime/`、`.venv/`、原始语料目录 `sources/`、批量 `outputs/`、`analysis/`、备份、日志和临时构建目录。选定运行 JSON 是允许清单中的明确例外，不递归打包整个 outputs。`.gitignore` 仍忽略 outputs，源码归档的选择不自动改变未来 Git 提交范围。

打包时只将指向实际已随包文件的本机绝对链接改为相对链接；原始报告不被改写。其余本地绝对路径只适用于原工作区。包外原始语料、备份和历史运行链接可能不可用；新机器应根据数据字典单独取得授权来源，再由 setup 脚本重建环境。manifest 可以记录文件相对路径、用途、哈希与版本，不应写入秘密值。这里不创建远程仓库、不上传数据，也不替用户确认公网发布完成。
