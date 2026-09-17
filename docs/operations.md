# 本机运行、预算与交接

## 当前状态 — 0.3.1

2026-09-17 已发布到本机：查询 `/query`、数据 `/data`；项目线框图 `/wireframe` 保留在页脚，根路径 `/` 也进入查询。0.3.1 新增完整交叉表、年度与标签分布、记录详情及检索词覆盖诊断，见 [研究界面修订报告](../reports/research_ui_v0_3_1_20260917.zh-CN.md)。共享筛选在浏览器 session 中保留，换页保留现有问答；问题或有效筛选改变时显示旧结果提示。导航本身不会产生付费调用。

当前 `active_profile=sentence600-v1`，556 个片段；旧 `legacy600-v1` 的 558 个片段保留，可按下述流程回退。源数据版本 `source_data_version=5114ebc1cf9afe59cdaa715e3ea45166` 未变：275 收录、263 默认可统计、226 可检索。`health.data_version` 现在同时包含源版本和索引版本，不能再直接与旧版的源快照 MD5 比较。发布记录见 [0.3.0 报告](../reports/release_v0_3_0_20260917.zh-CN.md)。

## 日常流程

从工作目录运行 `scripts/Start-Observatory.ps1`，会先启动项目数据库，再隐藏启动应用。`scripts/Test-Observatory.ps1` 检查应用和数据库，`scripts/Stop-Observatory.ps1` 只停止匹配的项目应用进程；数据库有独立停止脚本。也可在前台运行 `uv run observatory serve`。正文有更新时先保存源版本，运行 `uv run observatory import-native`、审查 `outputs/native_import.json`，再运行 `uv run observatory index`；后者可能产生 embedding 费用。先用免费 Search 核对新资料，付费回归另存其实际运行与数据版本。

原生 `import-native` 将输入视为该数据集的完整快照：本次未出现或被隔离的旧记录会停用，列入报告 `deactivated`，其历史正文与引文仍保留。空快照拒绝导入。社交导入默认增量，避免分批平台导出互相覆盖；将来需要完整替换时必须明确指定快照语义。

导入按当前 active profile 建立新正文的片段；`observatory index` 只补当前 profile、当前源版本缺失的向量，不扫描所有历史片段。只有重新导入源数据不能切换切分算法；算法切换使用下述 profile 发布流程。

不要把 `.runtime`、`.env`、源数据或备份提交公开仓库。页面服务绑定 `127.0.0.1:8050`，PostgreSQL 绑定 `127.0.0.1:55432`。源链接仅接收 HTTP(S)，不把内部本地路径作为公众链接。

## 已核验 PDF 与预览缓存

`config/native_body_recoveries.json` 中经过核验的附件才提供 PDF 链接；按标题匹配的候选不会自动公开。当前仅 PDF-265 对应记录具备这一映射。详情页核对正文版本、原 PDF 哈希及允许的文件路径，预览另核对 PNG 缓存及其生成凭据。

首次准备或核验附件更新后，可在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/render_record_previews.py
```

脚本使用已安装的 Poppler 将核验 PDF 的第一页转成 PNG，并写入 `sources/recovered_native/previews`。日常网页请求只读取缓存，不启动转换进程。缓存缺失时仍可打开或下载完整 PDF。迁移或部署时需单独携带相应 PDF、注册表、PNG 和凭据；源码不包含这些私有源文件。本次 0.3.1 没有重新导入正文、重算向量或调用付费模型。

## 检索索引准备、发布与回退

以下是维护命令，不是打开网页的前置步骤。操作前先备份，并保存当前 `health` 和 profile 状态。`init-db` 负责幂等建表及首次 legacy membership 迁移；已经完成迁移的本机无需为日常浏览再次执行。

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

## 当前发布验收基线

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

历史 0.2.4 的 `5114…` 源快照已完成[独立新库恢复](../reports/backup_restore_v0_2_4.md)：275/263/226/558、当时全部9张业务表内容、序列及结构均相同；110个存储回答中的177条引用定位通过，其中94条指向旧正文。验证未切换应用连接，也没有付费调用。此证据不包含 0.3.0 新增的 profile、成员、准备和发布状态表，也不代表异机灾备完成；当前发布的备份范围以 [0.3.0 报告](../reports/release_v0_3_0_20260917.zh-CN.md)为准。

若 Windows PowerShell 5 的默认执行策略阻止 `.ps1`，可直接使用包装脚本相同的 Python 入口，无需修改系统策略：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py backup
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py restore --backup-file '.runtime/backups/实际备份文件.dump' --database observatory_restore_review
```

恢复命令中的文件路径需替换为实际备份，数据库名必须尚不存在。

## 待接公网

正式方案是 Cloudflare Named Tunnel＋固定域名，指向 `http://127.0.0.1:8050`；数据库不进入 Tunnel。账户、域名和 Tunnel 配置暂由用户后续提供。配置模板见 `config/cloudflared.example.yml`。真实 token 只放受保护的本机配置，不写入模板或 Git。

正式开放前核对：社交真实导出、API 凭据/模型访问、稳定 cookie secret、错误页、并发预算和故障降级；从另一网络检查 HTTPS、筛选、来源和问答。仅本机页面可打开不算公开部署完成。

## 待接 GitHub

用户尚未提供本期指定仓库。现有历史链接不能自动用作交付 remote。收到目标后先核对其分支/内容，将源码、锁文件、配置样例、测试与文档提交可定位的版本；源数据另行交付。不要自动推送 `.env`、`.runtime` 或历史原始语料。
