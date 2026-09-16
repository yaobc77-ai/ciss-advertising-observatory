# 本机运行、预算与交接

## 日常流程

从工作目录运行 `scripts/Start-Observatory.ps1`，会先启动项目数据库，再隐藏启动应用。`scripts/Test-Observatory.ps1` 检查应用和数据库，`scripts/Stop-Observatory.ps1` 只停止匹配的项目应用进程；数据库有独立停止脚本。也可在前台运行 `uv run observatory serve`。正文有更新时先保存源版本，执行导入、审查 `outputs/native_import.json`，再运行 `uv run observatory index`。先用免费 Search 核对新资料，随后做小规模付费回归。

原生 `import-native` 将输入视为该数据集的完整快照：本次未出现或被隔离的旧记录会停用，列入报告 `deactivated`，其历史正文与引文仍保留。空快照拒绝导入。社交导入默认增量，避免分批平台导出互相覆盖；将来需要完整替换时必须明确指定快照语义。

不要把 `.runtime`、`.env`、源数据或备份提交公开仓库。页面服务绑定 `127.0.0.1:8050`，PostgreSQL 绑定 `127.0.0.1:55432`。源链接仅接收 HTTP(S)，不把内部本地路径作为公众链接。

## 预算

应用预算默认 $100/UTC 月，生成与 embedding 共用。每访客默认 5 次/分钟、30 次/UTC 日、全站最多 2 个正在生成的回答。

`uv run observatory budget` 显示已计费和未确定预留额。`uncertain_calls` 表示请求可能已经抵达供应商，不能直接清零；需拿供应商用量核对。进程中断后的过期预留保留金额，但释放生成并发名额。预算账本只覆盖本应用经过该接口的调用；其他程序使用同一 API 项目的支出不在此表中。

密钥从服务器环境变量读取，不返回客户端。匿名访问使用签名 session；公开运行前配置稳定随机的 `OBS_COOKIE_SECRET`。匿名访客配额不能单独防止更换 cookie 绕过；在 Cloudflare 入口增加 IP/网络限流，应用月预算是最终成本限制。

金额来自 API usage 与已核验标准单价，分别计入普通输入、缓存读取、缓存写入与输出；缓存写入为普通输入价的1.25倍。保守预留大于预计输入输出量。不确定结果保留预留成本。早期3次集成调用的缓存写入差额已依据实际usage补记，记录见私有 outputs/pricing_reconciliation.json。修改模型、API 服务地区或价格后，必须更新价格配置及测试，再开放调用。

## 数据库备份和恢复

使用 `scripts/Backup-Postgres.ps1`。恢复使用 `scripts/Restore-Postgres.ps1` 并明确提供一个新的测试数据库名称；不要覆盖现有数据库。详细参数和已执行证据见 `docs/local_postgres.md`。验证恢复后的行数、数据版本和历史引文后再考虑切换运行配置。

## 待接公网

正式方案是 Cloudflare Named Tunnel＋固定域名，指向 `http://127.0.0.1:8050`；数据库不进入 Tunnel。账户、域名和 Tunnel 配置暂由用户后续提供。配置模板见 `config/cloudflared.example.yml`。真实 token 只放受保护的本机配置，不写入模板或 Git。

正式开放前核对：社交真实导出、API 凭据/模型访问、稳定 cookie secret、错误页、并发预算和故障降级；从另一网络检查 HTTPS、筛选、来源和问答。仅本机页面可打开不算公开部署完成。

## 待接 GitHub

用户尚未提供本期指定仓库。现有历史链接不能自动用作交付 remote。收到目标后先核对其分支/内容，将源码、锁文件、配置样例、测试与文档提交可定位的版本；源数据另行交付。不要自动推送 `.env`、`.runtime` 或历史原始语料。
