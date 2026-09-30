# 本机与部署运行、预算及交接

**2026-09-30 当前入口：** 线上 0.4.2 的发布证据见[选取关系回执](../reports/graph_selection_publication_v0_4_2_20260930.json)。新增[英文交接说明](current_handoff.md)、[私有附件配置](record_assets.md)和[固定快照完整恢复](../reports/DATABASE_RESTORE_20260930.en.md)。本机 15 表、向量、历史答案及用量账本已恢复对账；该结果不覆盖 Railway 的独立快照或异机恢复。本轮 0.4.3 维护代码尚须按新提交核对发布。下文 0.4.1 及旧阶段命令／数字按其历史范围阅读。

0.4.1 修复初次图谱加载可能为空的回调竞态；当前状态见[发布记录](../reports/RELEASE_V0_4_0_20260930.zh-CN.md)，独立制品回执见[0.4.1复现](../reports/current_release_database_reproduction_v0_4_1_20260930.json)。以下0.4.0测试与规模基准保持其版本范围。

更新日期：2026-09-30。当前发布运行契约为 **0.4.1**；Railway 的实际发布状态以本轮部署回执和线上 `/healthz` 为准。下面标注旧日期的测试、费用和恢复记录保留其历史范围。

## 当前状态 — 0.4.1

查询入口为 `/query`、数据入口为 `/data`，根路径 `/` 进入查询。Data 提供当前范围的公司／来源所列赞助方与媒体统计、集合知识图谱、点击实体后的占比与来源记录，以及历史标签下钻。图谱边表达记录支持的关系，不认证商业合作；历史标签不是经过核验的 CLAIMS 判断。界面与限制见 [用户指南](user_guide.md)及[图谱详情验证](../reports/GRAPH_DETAILS_V2_20260929.zh-CN.md)。

共享筛选在浏览器 session 中保留，换页保留现有问答；问题或有效筛选改变时显示旧结果提示。导航和数据浏览不产生付费调用。启用 `OBS_RESEARCH_AGENT_ENABLED=true` 后，Generate answer 先付费理解问题，再选择共享只读工具；预算与模型访问仍在服务器控制。社交真实语料尚未接入，客户语义与易用性验收尚未完成。

当前 `active_profile=sentence600-v1`，556 个片段；旧 `legacy600-v1` 的 558 个片段保留，可按下述流程回退。源数据版本 `source_data_version=5114ebc1cf9afe59cdaa715e3ea45166` 未变：275 收录、263 默认可统计、226 可检索。`health.data_version` 现在同时包含源版本和索引版本，不能再直接与旧版的源快照 MD5 比较。发布记录见 [0.3.0 报告](../reports/release_v0_3_0_20260917.zh-CN.md)。

## 当前构建、迁移与健康检查

[Dockerfile](../Dockerfile)使用 Python 3.12，固定 `uv:0.12.7`，先以 `uv sync --frozen --no-dev --no-install-project` 安装锁定依赖，再以 `uv sync --frozen --no-dev --no-editable` 安装项目。运行入口为 `/app/.venv/bin/observatory serve`；包内包含浏览器资源与有序 SQL 迁移，不能依靠工作目录中的 editable 源码补齐缺失文件。容器构建不携带 `.env`、原始语料、运行目录或数据库备份；应用配置由部署平台环境变量提供。

[CI](../.github/workflows/ci.yml)固定 uv 0.12.7 和 Python 3.12，安装 `uv.lock` 中的 test／MCP 依赖，执行 Ruff 与浏览器 JavaScript 语法检查，再构建并安装 wheel。测试设置 `OBS_RELEASE_WHEEL` 后针对已安装制品运行 `not integration and not live` 用例，并核对静态资源、迁移与 CLI。工作流文件存在不等于本次提交的 CI 已通过；发布时保存对应提交的实际运行结果。CI 不连接生产数据库，也不调用付费模型。

[2026-09-30 独立安装与测试库回执](../reports/current_release_database_reproduction_20260930.json)记录实际安装的 0.4.0 wheel 在 Python 3.12.14 中通过验证：本机 `obs_test` 内新随机 schema 的迁移升至版本 2，两年合成记录通过默认 upsert 保留，重复导入返回 1 条 unchanged；6 个句界片段均可定位，缺失 embedding 时激活被阻断。embedding、答案、用量和生成输出表均为空，模型调用为 0；仅清理该随机 schema。这验证了安装与合成工程路径，**没有复现生产语料、生产向量、历史答案或预算账本，也不代表客户验收或大规模性能已通过**。命令与完整边界见 [当前制品复现说明](CURRENT_RELEASE_REPRODUCTION.md)；原始快照复现仍需要授权源文件和完整备份。

新建或升级运行环境时，先备份目标库，再运行 `observatory migration-status` 检查迁移，执行 `observatory migrate`，随后复查状态。迁移不等于导入资料或重算向量；不要把付费 `index` 放进普通启动流程。Railway 的部署前命令使用 `/app/.venv/bin/observatory migrate`，由同一部署环境的数据库变量选择目标库，不能填入本机测试连接。

公开 `/healthz` 只返回以下白名单：

| 字段 | 核对目的 |
|---|---|
| `status`、`record_counts`、`chunks`、`active_profile` | 服务状态、收录规模与当前检索索引；收录数不等于可统计或可检索数 |
| `source_data_version`、`index_version`、`data_version` | 发布前后来源与索引是否变化 |
| `application.version` | 实际安装包版本，应与本轮发布记录匹配（0.4.1） |
| `application.commit` | 平台 `RAILWAY_GIT_COMMIT_SHA` 中有效的 40 位 Git SHA；无效或缺失时返回 `null` |
| `application.features` | `collection_graph`、`graph_breakdowns`、`research_agent` 能力／开关状态；不代表数据完整或回答准确 |

健康接口不会回传数据库连接、API key、cookie secret、完整配置或内部路径。`status=ok` 返回 200，其他状态返回 503。版本、提交与功能开关是线上制品核对依据，不能仅根据页面外观或 200 状态认定发布完成。

## 日常流程

从工作目录运行 `scripts/Start-Observatory.ps1`，会先启动项目数据库，再隐藏启动应用。`scripts/Test-Observatory.ps1` 检查应用和数据库，`scripts/Stop-Observatory.ps1` 只停止匹配的项目应用进程；数据库有独立停止脚本。也可在前台运行 `uv run observatory serve`。正文有更新时先保存源版本，运行 `uv run observatory import-native`、审查 `outputs/native_import.json`，再运行 `uv run observatory index`；后者可能产生 embedding 费用。先用免费 Search 核对新资料，付费回归另存其实际运行与数据版本。

原生 `import-native` 和社交 `import-social` 默认增量 upsert：本批未出现的旧记录保持原状态。完整数据集替换必须明确传入 `--mode snapshot`；此时本次未出现的旧记录会停用并列入 `deactivated`，历史正文与引文仍保留，空快照拒绝导入。若一批更新需要撤回旧记录，不能依靠 upsert 中的缺行表达撤回；须审查全量替换范围或另行制定撤回流程。

导入按当前 active profile 建立新正文的片段；`observatory index` 只补当前 profile、当前源版本缺失的向量，不扫描所有历史片段。只有重新导入源数据不能切换切分算法；算法切换使用下述 profile 发布流程。

不要把 `.runtime`、`.env`、源数据或备份提交公开仓库。页面服务绑定 `127.0.0.1:8050`，PostgreSQL 绑定 `127.0.0.1:55432`。源链接仅接收 HTTP(S)，不把内部本地路径作为公众链接。

## 已核验 PDF 与预览缓存

`config/native_body_recoveries.json` 中经过核验的附件才提供 PDF 链接；按标题匹配的候选不会自动公开。当前仅 PDF-265 对应记录具备这一映射。详情页核对正文版本、原 PDF 哈希及允许的文件路径，预览另核对 PNG 缓存及其生成凭据。

首次准备或核验附件更新后，可在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/render_record_previews.py
```

脚本使用已安装的 Poppler 将核验 PDF 的第一页转成 PNG，并写入 `sources/recovered_native/previews`。日常网页请求只读取缓存，不启动转换进程。缓存缺失时仍可打开或下载完整 PDF。迁移或部署时需单独携带相应 PDF、注册表、PNG 和凭据；源码不包含这些私有源文件。0.3.1 的历史界面发布没有重新导入正文、重算向量或调用付费模型。

## 检索索引准备、发布与回退

以下是维护命令，不是打开网页的前置步骤。操作前先备份，并保存当前 `health` 和 profile 状态。`migrate` 负责有序、幂等迁移及首次 legacy membership 初始化，`migration-status` 只读检查；已经完成迁移的本机无需为日常浏览再次执行。

```powershell
.\.venv\Scripts\python.exe -m observatory.cli health
.\.venv\Scripts\python.exe -m observatory.cli index-status
.\.venv\Scripts\python.exe -m observatory.cli index-status legacy600-v1
```

切换到某个 profile 分三步：

1. **Prepare**：按当前源版本与允许检索区间生成该 profile 的成员清单；写入新片段和准备记录，保留历史片段，不切换网页检索，不调用模型。
2. **补向量**：仅为目标 profile 的缺失文本计算 embedding；可能产生费用，不调用回答生成模型，也不激活候选索引。
3. **Activate**：核对源版本、完整成员、原文位置和向量齐全后，在事务中切换 active profile；不完整或过期的准备会拒绝发布。

例如准备句界索引：

```powershell
.\.venv\Scripts\python.exe -m observatory.cli index-prepare sentence600-v1
.\.venv\Scripts\python.exe -m observatory.cli index-status sentence600-v1
```

`index` CLI 补的是当前 active profile。为尚未激活的候选补向量时，在项目 Python 环境使用显式 profile 参数；先根据 `index-status` 的 `missing_embeddings` 核对所需工作与预算：

```python
from observatory.config import Settings
from observatory.db import Database
from observatory.rag import Rag

settings = Settings.from_env()
rag = Rag(Database(settings.database_url), settings)
print(rag.index(profile_id="sentence600-v1", visitor="index-maintenance"))
```

发布前再次检查状态，将下面占位值替换为本次准备记录的 `source_data_version`；不要使用包含索引的 `data_version`：

```powershell
.\.venv\Scripts\python.exe -m observatory.cli index-status sentence600-v1
.\.venv\Scripts\python.exe -m observatory.cli index-activate sentence600-v1 --expected-source-version '<本次准备的 source_data_version>'
.\.venv\Scripts\python.exe -m observatory.cli health
```

回退采用同一流程，把目标改为 `legacy600-v1`。即使历史片段仍在，也先检查其准备是否对应当前源版本；有新导入时重新 prepare，缺向量时补齐，再 activate。回退不删除新索引、历史正文或已保存的引用。旧 Evidence 继续按原始 chunk ID、源版本和字符位置校验。

发布过程会改变 `health.data_version`。问答在检索后及生成返回后检查该版本；中途变更时不公开旧答案或证据，已发请求的费用和生成记录仍保留。免费或付费评价也需要记录当前 profile、源版本和索引版本，不能把旧版 558 块的结果标作新索引评测。

## 原生数据交接与复现

正式导入必须带齐 [native_admissions.json](../config/native_admissions.json)、[native_body_ranges.json](../config/native_body_ranges.json)、[native_body_recoveries.json](../config/native_body_recoveries.json) 三份 manifest 及其固定哈希的私有源文件。第三份还要求源 PDF 和 [PDF-265 抽取文本](../sources/recovered_native/PDF-265.pypdf-6.10.0.txt)；缺文件或哈希、行号、身份、页界、区间不符会停止发布。不要以删除 manifest 或改用可选的库导入参数来绕过检查，这会改变快照语义。

抽取文本可由资料交付方提供。若需从固定 PDF 复现，使用可选依赖和[提取脚本](../scripts/extract_pdf_text.py)：

```powershell
uv run --extra pdf python scripts/extract_pdf_text.py `
  'sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/2018-12-28T10_21_52-0500_Usingmolluskstomonitorindustrialsites.pdf' `
  --expected-sha256 20b2ec33f808d96dc749ce0c62cd8b35dec43da48d7df0db44905544cb93479c `
  --out 'sources/recovered_native/PDF-265.pypdf-6.10.0.txt'
```

仅在输出文件不存在时运行；脚本拒绝覆盖。它用锁定的 `pypdf==6.10.0` 原样提取每页并追加 `U+000C`，不 OCR、不重写源 PDF。预期文本为7,098字符、SHA-256 `28110347b8b96cd32ac4b7bcac41d1f3b80c67798e220f9043382eb40a622b67`。常规应用和导入只读该文件，不需要安装 pypdf。

恢复保留6个区间、4,767字符，仍为 `partial`；原来的94项 CSV 截断限制不能因此记作全文恢复。原正文和版本继续保存，该篇旧标签在新版本的 `raw.previous_body_annotations` 中供内部追溯，不参与当前标签过滤。具体遗漏及身份边界见[恢复报告](../reports/pdf265_body_recovery.md)。

## 当前验证与历史发布基线

0.4.1 的安装制品 956 项测试、生产首屏与互动验证见[发布记录](../reports/RELEASE_V0_4_0_20260930.zh-CN.md)及[本轮发布回执](../reports/release_v0_4_1_publication_20260930.json)；安装与合成测试库执行见[0.4.1 回执](../reports/current_release_database_reproduction_v0_4_1_20260930.json)。0.4.0 三道客户问题与 37,000 条合成记录基准保持其原版本范围。下面 0.3.x／0.2.x 的成绩不作为当前运行成绩，工程检查不构成客户语义验收。

[0.3.0 发布报告](../reports/release_v0_3_0_20260917.zh-CN.md)记录 366 项工程测试通过、三页面与 sentence600-v1 的本机发布。两次付费 smoke 只支持已记录的工程定位检查；中文回答仍有选定短引文之外的地点实体、重复使用引文等待审项，不能记作人工语义验收或整体质量提升。

历史 [0.2.3 发布验证](../outputs/pdf265_publication_validation_20260916.json)的源数据版本是 `5114ebc1cf9afe59cdaa715e3ea45166`：275收录、263可计数、226可检索、558个当时的当前片段。该轮只有1条新记录版本、274条不变；重复导入275条不变。已验证558个当时片段定位、86个历史引文定位及15个开发 gold 原句，完整测试209项通过（19.63秒）。这些数字保留历史口径。

交接后核对实际源哈希、版本和定位，再使用应用。此前0.2.2的 `d85a98002e4493f0376c260ad82253ee`／554片段是历史基线；其付费开发输出、费用和成绩保持原样，不视作0.2.3新数据的评测。人工语义验收仍待完成。

## 预算

应用预算默认 $100/UTC 月，生成与 embedding 共用。每访客默认 5 次/分钟、30 次/UTC 日、全站最多 2 个正在生成的回答。

`uv run observatory budget` 显示已计费和未确定预留额。`uncertain_calls` 表示请求可能已经抵达供应商，不能直接清零；需拿供应商用量核对。进程中断后的过期预留保留金额，但释放生成并发名额。预算账本只覆盖本应用经过该接口的调用；其他程序使用同一 API 项目的支出不在此表中。

密钥从服务器环境变量读取，不返回客户端。匿名访问使用签名 session；公开运行前配置稳定随机的 `OBS_COOKIE_SECRET`。匿名访客配额不能单独防止更换 cookie 绕过；在 Cloudflare 入口增加 IP/网络限流，应用月预算是最终成本限制。

金额来自 API usage 与已核验标准单价，分别计入普通输入、缓存读取、缓存写入与输出；缓存写入为普通输入价的1.25倍。保守预留大于预计输入输出量。不确定结果保留预留成本。早期3次集成调用的缓存写入差额已依据实际usage补记，记录见私有 outputs/pricing_reconciliation.json。修改模型、API 服务地区或价格后，必须更新价格配置及测试，再开放调用。

## 数据库备份和恢复

使用 `scripts/Backup-Postgres.ps1`。恢复使用 `scripts/Restore-Postgres.ps1` 并明确提供一个新的测试数据库名称；不要覆盖现有数据库。详细参数和已执行证据见 `docs/local_postgres.md`。验证恢复后的行数、数据版本和历史引文后再考虑切换运行配置。

历史 0.2.4 的 `5114…` 源快照已完成[独立新库恢复](../reports/backup_restore_v0_2_4.md)：275/263/226/558、当时全部9张业务表内容、序列及结构均相同；110个存储回答中的177条引用定位通过，其中94条指向旧正文。验证未切换应用连接，也没有付费调用。此证据不包含 0.3.0 新增的 profile、成员、准备和发布状态表，也不代表异机灾备完成；历史变更见 [0.3.0 报告](../reports/release_v0_3_0_20260917.zh-CN.md)。0.4.0 的完整备份须包含当前业务表、源版本、索引成员与发布状态、embedding、历史答案和预算账本，并在独立恢复库对账；新的合成测试库回执不替代这项恢复。PDF、预览缓存、源 manifest、授权源文件和私有环境配置需分别备份，不包含在纯源码制品中。

若 Windows PowerShell 5 的默认执行策略阻止 `.ps1`，可直接使用包装脚本相同的 Python 入口，无需修改系统策略：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py backup
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py restore --backup-file '.runtime/backups/实际备份文件.dump' --database observatory_restore_review
```

恢复命令中的文件路径需替换为实际备份，数据库名必须尚不存在。

## Railway 0.4.0 发布配置与生效核对

已存在 [Railway 预览](https://ciss-advertising-observatory-production.up.railway.app/data)。2026-09-30 已应用下列 Railway UI 设置，0.4.1 生产部署与健康接口已核对。发布前日志显示迁移 current_version=2、pending=[]、两个迁移 applied。后续维护仍需检查实际设置，不能用 staged 值或仓库配置替代生效证据。

| 设置 | 本轮目标值 | 生效核对 |
|---|---|---|
| Wait for CI | 开启 | 已应用设置显示开启，目标提交的 CI 成功后部署继续 |
| Healthcheck path／timeout | `/healthz`／60 秒 | 已应用设置与部署健康检查阶段一致 |
| Pre-deploy command | `/app/.venv/bin/observatory migrate` | 部署前日志显示命令执行成功，应用启动使用迁移后的数据库 |
| `OBS_RESEARCH_AGENT_ENABLED` | `true` | 已应用环境变量，线上 `application.features.research_agent=true` |

[railway.json](../railway.json)记录 Dockerfile、健康检查和迁移目标配置。本轮平台界面出现 config-as-code deprecated 提示，因此不能仅凭文件存在、Git 推送成功或 staged UI 值认定它已生效。维护者应先核对提交、待应用变更和实际已应用设置，再查看构建、部署前迁移、启动与健康检查日志。若平台没有采用仓库配置，应通过项目设置应用同一契约，并保存实际生效记录；不要同时保留两个互相冲突的启动／迁移来源。

发布前保存线上健康白名单和备份；发布后核对 `/healthz` 的 `application.version=0.4.1`、`application.commit` 与部署提交一致，三个 feature 状态符合目标，且原生源版本、索引版本、活动 profile、收录数和片段数符合本次是否更新数据的预期。本轮代码发布不要求重导入语料、重算 embedding 或清空历史账本。`commit=null` 时需通过部署日志独立确认源码提交；缺少新版 `application` 字段表示尚不能由健康接口确认新版制品。

确认版本后再检查 `/query`、`/data`、节点点击／饼图／来源记录和详情。付费理解与生成需另行授权、记录用量并遵守预算，不属于免费上线连通检查；图谱和关键词浏览可独立检查。部署通过不等于客户验收，社交空库仍须显示未接入。

源码中的 research-agent 开关默认关闭以保留旧基线，`.env.example` 给出启用样例。失败时保留实际费用和未决预留，升级与重启不得清账；应用／API 月预算与 Railway 平台费用上限分别核对。服务器密钥、数据库连接与稳定 cookie secret 通过平台环境配置，不提交仓库或写入公开回执。

MCP 官方 SDK 是可选依赖，`uv sync --extra test --extra pdf --extra mcp` 安装后可用 `python -m observatory.mcp_server` 启动 stdio；MCP 客户端按需启动该进程。可选 HTTP 只在本机 8051 端口开放，未挂载到公开 Dash 应用。完整契约和配置见 [MCP 说明](MCP_RESEARCH_TOOLS.zh-CN.md)。

数据导入与迁移规则见 [数据管道说明](PROTOTYPE_DATA_PIPELINE.md)。Cloudflare 模板作为可选方案保留，不是现有 Railway 预览的运行前提。源码更新不会自动部署原始 PDF／预览等私有素材；在目标环境逐条检查核验附件能否访问，缺失时保持明确缺失提示。

正式开放前核对：社交真实导出、API 凭据/模型访问、稳定 cookie secret、错误页、并发预算和故障降级；从另一网络检查 HTTPS、筛选、来源和问答。仅本机页面可打开不算公开部署完成。

## GitHub 与更新数据

指定仓库为 [yaobc77-ai/ciss-advertising-observatory](https://github.com/yaobc77-ai/ciss-advertising-observatory)。源码、锁文件、配置样例、测试与文档需形成可定位的提交；源数据另行交付，`.env`、`.runtime` 和原始语料不进入公开提交。

从本轮起，`import-native` 和 `import-social` 默认 `--mode upsert`，不会停用本批未出现的历史记录。仅在材料确实是整个数据集的完整替换时明确传入 `--mode snapshot`。新年份／新来源可以先转换为 canonical JSONL，运行 `import-records --dry-run` 检查后再增量导入；字段含义与源 ID 仍需要数据方确认。详见 [数据管道说明](PROTOTYPE_DATA_PIPELINE.md)。
