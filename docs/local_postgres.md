# 本机 PostgreSQL + pgvector

本项目自 **2026-10-01** 使用独立的 **PostgreSQL 18.6 + pgvector 0.8.6**。当前运行时为 `.runtime/postgres18/`，数据目录为 `.runtime/pgdata18/`，监听 **127.0.0.1:55432**，主数据库为 **observatory**。没有安装 Windows 服务或修改系统 PATH；机器重新启动后需执行启动脚本。原 PostgreSQL 16 运行时与数据目录保留为升级前快照并停止使用。

## 为什么选择这条安装路径

- PostgreSQL 18.6 及依赖使用 conda-forge 的 win-64 包。`scripts/postgres-win64.lock.txt` 固定 **18 个包**的下载 URL 与 MD5；安装元数据保留在 `.runtime/postgres18/conda-meta/`。
- 先前使用的 conda-forge pgvector 0.8.6 Windows 包要求 libpq 16，不能将其 DLL 直接用于 PostgreSQL 18。当前锁文件不包含该包，而由 [Install-Pgvector.ps1](../scripts/Install-Pgvector.ps1) 按 [pgvector 上游 Windows 构建说明](https://github.com/pgvector/pgvector#windows)从源码编译。
- pgvector 源码固定为上游 `v0.8.6`，归档 SHA-256 为 `10bf9938906e5d643bbc4a7eea104b6f57ba4898e5b76b20e60484ea1d5a7f8f`。脚本核对归档、限制解包路径，再使用 **Visual Studio 2022 x64 C++ 工具**和上游 `Makefile.win`，以当前 PostgreSQL 18 的 `Library` 目录为 `PGROOT` 编译并安装。构建记录 `.runtime/postgres18/pgvector-build.json` 绑定源码、PostgreSQL 二进制、DLL、control 与安装 SQL 的哈希；一致时重复运行不重建。
- [micromamba 官方安装说明](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)提供独立运行方式。使用 2.9.0 的 conda-forge Windows 归档，下载后核对发布元数据中的 SHA-256，仅提取 `micromamba.exe`。
- Setup 负责新环境安装，不执行大版本迁移。已有旧集群标记或数据时会拒绝自动初始化；控制脚本在调用 `pg_ctl` 前核对 PostgreSQL 18 二进制与数据大版本，不能直接重用 PostgreSQL 16 数据目录。

## 文件位置与权限

| 路径 | 内容 |
|---|---|
| `.runtime/postgres18/` | 当前 PostgreSQL 18、源码构建的 pgvector 及依赖 |
| `.runtime/pgdata18/` | 当前项目数据库集群；初始化遇到非空目录会拒绝覆盖 |
| `.runtime/postgres-cluster.json` | 集群所属目录与端口标记 |
| `.runtime/postgres18.log` | 当前 PostgreSQL 18 服务日志 |
| `.runtime/postgres/`、`.runtime/pgdata/`、`.runtime/postgres.log` | 保留的 PostgreSQL 16 运行时、升级前数据与旧日志；不是当前运行目录 |
| `.runtime/secrets/postgres.json` | 随机生成的本机管理账号与应用账号凭据 |
| `.env` | `OBS_DATABASE_URL`，以及测试使用的 `OBS_TEST_DATABASE_URL` |
| `.runtime/backups/` | 本地备份及 SHA-256 文件 |

`.runtime/` 和 `.env` 已列入项目 `.gitignore`。凭据目录和 `.env` 去除继承权限，仅为当前 Windows 账号设置访问权限；脚本不输出口令或完整连接 URL。修改连接值时保留 `.env` 内其他键。备份可能包含数据正文，因此默认也放在忽略目录中。

认证使用 **SCRAM-SHA-256**，`pg_hba.conf` 仅允许 `127.0.0.1/32` 的密码连接，没有 `trust` 规则。应用账号 `observatory_app` 不是超级用户，没有 CREATEDB、CREATEROLE 或 REPLICATION；本机管理账号只供这些管理脚本使用。网站访问者通过应用后端访问，不直接连数据库端口。

## PowerShell 操作

在项目根目录执行；脚本也支持从其他目录按完整路径调用，并通过 Python 解析 Windows junction 后核对集群所属目录。新机器先准备项目 `.venv`、`psycopg` 依赖，以及 Visual Studio 2022 的 x64 C++ 编译工具与所需 Windows SDK。源码构建写入项目运行目录，不要求将数据库安装为系统服务。

```powershell
# 新环境下载安装并构建 PG18 对应的 pgvector；遇到旧集群时拒绝自动迁移。
.\scripts\Setup-Postgres.ps1

# 启动（首次会初始化集群和数据库）。已有服务正常时可重复执行。
.\scripts\Start-Postgres.ps1

# 验证版本、vector 运算、监听范围、SCRAM 和错误密码被拒绝。
.\scripts\Test-Postgres.ps1

# 只停止本项目集群。不要在导入、测试或网站服务工作期间执行。
.\scripts\Stop-Postgres.ps1

# 产生新的时间戳命名 custom-format 备份，不覆盖已有备份。
.\scripts\Backup-Postgres.ps1
```

启动通过 `pg_ctl` 完成，辅助进程使用 Windows `CREATE_NO_WINDOW`，没有可见终端窗口。启动发现 55432 被其他进程占用时会报错，不停止占用进程。停止前核对集群标记和服务器数据目录，只对这个集群调用 `pg_ctl stop -m fast`；它会取消该集群的活动事务后正常关闭，因此应先停应用或等待写入结束。

安装参考：[PostgreSQL 18 initdb](https://www.postgresql.org/docs/18/app-initdb.html)、[pg_ctl](https://www.postgresql.org/docs/18/app-pg-ctl.html)。Windows 上 Python 使用系统工具 `icacls` 设置本项目凭据文件的 ACL，不依赖 PowerShell 模块自动加载。

## 当前升级记录（2026-10-01）

本机 PostgreSQL 16.15 已通过 PostgreSQL 18 的 `pg_upgrade --check` 与 **copy 模式**升级为 PostgreSQL 18.6，pgvector 维持 0.8.6。新集群运行于 `.runtime/pgdata18/`，原端口与应用数据库名不变。原集群的 **13 个数据库**及角色、口令验证值、数据库权限已保留；12 个可连接数据库的表行指纹、规范化结构、owner、序列与扩展逐项一致。主库有 21 张表、275 条 records；词项检索、复用存储向量的检索结果和历史引用定位与升级前一致。`.env` 与凭据文件的字节哈希未变。

迁移前完整私有备份位于 `.runtime/backups/pg16-before-pg18-20261001-complete/`，包含 12 个可连接数据库的 custom-format dump、全局角色导出 `globals.sql`、配置、集群标记和项目 `.env` 副本。该目录以私有 ACL 保护；全局导出包含口令验证值，不应作为公开报告附件。日常 `Backup-Postgres.ps1` 仍只是单数据库备份，不等同于此次完整迁移备份。

原 `.runtime/postgres/` 与 `.runtime/pgdata/` 均保留并停止使用，未执行 `delete_old_cluster.bat`。它们只代表升级时刻的 PG16 快照，后续 PG18 写入不会同步过去。若需要回退，先保留并处理升级后的数据变化，再按经过核对的恢复方案还原旧配置、集群标记及脚本运行时路由；不能直接复用数据目录或只切回旧二进制。

证据见 [PG18 升级报告](../reports/LOCAL_POSTGRES18_UPGRADE_20261001.zh-CN.md)及 [JSON 回执](../reports/local_postgres18_upgrade_20261001.json)。这是当前本机集群升级与等价性核验，不表示已在全新机器完成从零安装，也不替代语义回答质量或公众部署验收。以下带日期和版本的 PG16 记录保留为历史证据。

## 恢复：必须显式提供一个新数据库名

先使用备份命令打印出的实际文件路径，再自行给出尚不存在的目标数据库名：

```powershell
.\scripts\Restore-Postgres.ps1 `
  -BackupFile '.runtime\backups\实际备份文件.dump' `
  -Database 'observatory_review_copy'
```

`-Database` 没有默认值。脚本拒绝 `observatory`、系统库和任何已经存在的目标库；不删除数据库、不使用 `--clean`，也不修改主库连接。恢复使用 `pg_restore --exit-on-error --single-transaction`，保留归档中的本项目角色归属。失败时保留新建目标库供检查，不自动删除或覆盖。不要把不可信来源的 SQL／备份交给恢复脚本；这里的恢复用于本项目自己产生的备份。

备份前后主库可继续工作，`pg_dump` 获取一致性快照。恢复后若希望应用改用恢复库，应另行明确修改 `.env`；脚本不会自动切换。当前备份操作为**单数据库逻辑备份**，不包含全局角色密码、运行环境和机器故障后的自动恢复；恢复至新机器还需运行 setup 并妥善保留私有凭据文件。

## 集成测试数据库

另有 **obs_test**，由本机管理账号创建，owner 是 `observatory_app`，并已启用 vector。`.env` 的 `OBS_TEST_DATABASE_URL` 使用该库；应用账号仍无建库权限。此库只用于测试，测试代码应先断言数据库名以 `obs_test` 开头再清理测试表，不能回退使用主库 URL。

新机器在项目虚拟环境与主库就绪后执行：

```powershell
# 先按项目依赖说明创建 .venv，然后初始化本机主库。
.\scripts\Setup-Postgres.ps1

# 创建或核验固定名称 obs_test，并保存测试连接配置。
.\scripts\Setup-TestDatabase.ps1

# 执行项目测试；测试程序可清理测试库中的测试表。
.\.venv\Scripts\python.exe -m pytest -q
```

等价 Python 命令为 `.\.venv\Scripts\python.exe scripts/local_postgres.py setup-test-db`。此命令不接受其他目标库名：先核对当前服务器属于本项目、应用角色无管理权限；`obs_test` 已存在时核对 owner，不符就拒绝。命令启用 vector、只更新 `OBS_TEST_DATABASE_URL` 并保留 `.env` 的其他键和凭据文件 ACL，不输出秘密。重复运行不 truncate、drop 或初始化业务表，也不重置测试数据；业务 schema 由测试 fixture 管理。

2026-09-16 已在现有 `obs_test` 上连续执行两次 wrapper：9 个业务表的计数、主库 URL、所有其他 `.env` 值、私有凭据文件、`.env` ACL 和应用角色权限均未变，vector 0.8.6 可用，PowerShell 语法解析通过。这证明现有测试库上的幂等行为；未为测试新建分支而删除现有 `obs_test`，本次没有声称从空机器完整重装已经实测。

## 历史 PostgreSQL 16 验证记录（2026-09-16）

已验证运行时安装、启动、重复启动、停止后重新启动，以及 `.env` 写入；`SELECT version()` 返回 PostgreSQL 16.15，`pg_extension` 中 vector 为 0.8.6。相同三维向量的 L2 距离为 0；监听地址为 127.0.0.1，认证规则为 SCRAM，故意错误的口令被拒绝。`obs_test` 应用账号连接正常。

2026-09-16 已生成并恢复 `.runtime/backups/observatory-20260916T165727764638Z.dump`，目标为独立的 `observatory_restore_smoke_20260916`；恢复后 vector 可用，8 个业务表的 owner 均为 `observatory_app`。备份文件和 SHA-256 留在本地，测试恢复库也予以保留。随后验证了三种拒绝行为：恢复到主库、恢复到已存在的测试恢复库、覆盖已存在的备份文件，均在变更前失败；原备份哈希和主库 DSN 保持不变。全部 PowerShell 包装脚本语法解析通过，固定包清单经 micromamba dry-run 解析通过。

数据库结构、真实数据导入和应用功能由项目主流程管理，不在这些运行时脚本中创建业务表。这份备份只代表创建时刻的快照，不等于后续导入后的最终数据备份。

## 真实数据与历史引用恢复验证（2026-09-16）

付费开发集结果落盘后，新备份 `.runtime/backups/observatory-preview-20260916T173559442124Z.dump` 已恢复到独立库 `observatory_restore_preview_20260916`，原库与应用持续运行。SHA-256 为 `95fc9095d3c99714c4c09f2746b06c6628da9035bb68919597cde5c2dbd10b16`。

主库备份前／后与恢复库一致：active records 268、current chunks 510、全部 record_versions 536、annotations 1072、usage_ledger 73、answer_runs 40、generation_outputs 35；data_version `652ed975bbd44ea06e20af19b6a6642d`。存储回答 run `1` 的引用在恢复后仍能按 chunk/version/字符位置定位。应用角色权限、`.env`、私有凭据文件及主库连接值均未改变；未打印凭据。

详见 [本次备份恢复报告](../reports/backup_restore.md)。这是同一本机集群的新库恢复验证，单数据库归档不包含全局角色密码与应用运行环境。备份与恢复库均保留。

## 历史快照恢复验证（0.2.4，2026-09-16）

以上268条记录属于早期快照。当前 `5114ebc1cf9afe59cdaa715e3ea45166` 已于2026-09-16再次备份并恢复到新库 `observatory_restore_v024_20260916`。主库前后与恢复库的275收录、263可计数、226可检索、558当前块，以及9张业务表逐行指纹、列/索引/约束/序列均一致；全部177条存储引用可定位，94条仍指向旧正文版本。主库连接与凭据文件未变，应用保持运行。

本次直接执行 `python -X utf8 scripts/local_postgres.py backup/restore`；Windows PowerShell 5的 `Restricted` 策略阻止了最初的 `.ps1` 调用，未改变策略。当前备份路径、哈希、表行数、方法和命令见[当前快照恢复报告](../reports/backup_restore_v0_2_4.md)。仅证明同机独立库恢复，不包含异机环境和公众网络验收。
