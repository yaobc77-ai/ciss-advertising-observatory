# 本机 PostgreSQL 18 升级记录（2026-10-01）

本机项目集群已从 **PostgreSQL 16.15** 升级为 **PostgreSQL 18.6 + pgvector 0.8.6**，本地网页已恢复运行。端口仍为 `127.0.0.1:55432`，主库仍为 `observatory`；`.env` 与凭据文件的字节哈希保持一致。完整证据见 [JSON 回执](local_postgres18_upgrade_20261001.json)。

## 升级方法与运行位置

当前运行时为 `.runtime/postgres18/`，数据目录为 `.runtime/pgdata18/`，日志为 `.runtime/postgres18.log`。控制脚本和安装锁已同步更新。原 `.runtime/postgres/` 与 `.runtime/pgdata/` 保留，旧集群停止；没有执行 `delete_old_cluster.bat`。

PostgreSQL 与 libpq 18.6 来自锁定的 18 个 conda-forge Windows 包。原 conda pgvector 包绑定 PG16，所以使用校验 SHA-256 的上游 v0.8.6 源码，通过 Visual Studio 2022 x64 C++ 工具和 `Makefile.win` 为 PG18 重新编译；构建回执绑定源码及安装文件哈希。当前机器具备这些编译工具；新机器重建须先准备同样的工具，不能直接沿用 PG16 的 DLL。

升级先运行 [pg_upgrade 兼容性检查](https://www.postgresql.org/docs/18/pgupgrade.html)，再暂停本地应用、保存备份并复核源集群未改变，最后执行 `pg_upgrade --copy`。独立端口上的目标集群通过核验后才切回原端口，随后刷新统计信息。复制模式保留原数据文件；[大版本升级说明](https://www.postgresql.org/docs/18/upgrading.html)解释了为何不能只更换二进制并直接重用旧目录。

## 数据保留核验

原有 **13 个数据库**的名称、owner、编码、locale、连接属性和权限一致；用户角色、口令验证值、角色权限与角色设置一致。12 个可连接数据库的全部用户表逐行内容指纹、规范化 schema、owner/ACL、序列和扩展一致。ACL 按集合语义比较，schema 使用同一 PG18 dump 工具并去除来源版本注释和随机 guard token。`template0` 不允许连接，核对其元数据并保留旧集群，未声称逐表指纹检查。

主库 **21 张表**均匹配，包括以下升级时刻的数据：

| 内容 | 数量 |
|---|---:|
| records | 275 |
| record_versions | 828 |
| chunks（含历史 profile） | 2,071 |
| embeddings | 1,073 |
| answer_runs | 220 |
| generation_outputs | 114 |
| usage_ledger | 287 |

全部 828 个正文版本与 2,071 个片段定位有效；779 条历史/当前答案证据、199 条引用均可定位。六组检索检查（CCS、biogas、publisher/dataset 过滤、空记录范围、复用真实向量的混合检索）与升级前结果一致。当前活动 profile 为 `sentence600-v1`，页面显示 556 个活动片段。

## 验证结果

- **87 项集成测试全部通过**，使用单独的 PG18 集群 `127.0.0.1:55434` 和其中的 `obs_test`；完成后停止该验证集群。原集群的 `obs_test` 与历史恢复库均保持原内容。
- **18 项运行时/恢复保护测试通过**，包括 PG 大版本拒绝、旧集群拒绝、真实 Windows junction 路径核验。
- 首轮独立库名测试通过 74 项，13 项因固定库名保护要求而被拒绝；随后换用单独集群重跑全部 87 项成功，没有放宽保护条件。
- PG18 版本、vector 0.8.6、向量距离运算、SCRAM、错误密码拒绝和数据 checksums 均正常。
- `/healthz`、`/_dash-layout`、`/assets/observatory.css` 均返回 **200**。应用保持原连接值，当前本机应用报告版本为 0.4.8；本次只升级数据库。
- 安装脚本重复执行通过，已安装 pgvector 的构建哈希匹配时无需重建。18 包锁的 dry-run、PowerShell 语法、Ruff 与 diff 检查通过。

## 备份与回退边界

私有备份目录为 `.runtime/backups/pg16-before-pg18-20261001-complete/`，含 **12 个数据库的 custom-format dump + SHA-256**、全局角色导出 `globals.sql`、配置、旧集群标记和 `.env` 副本。12 个数据库归档合计 83,713,508 字节；备份哈希已复核。全局导出含口令验证值，该目录使用私有 ACL，未作为公开附件。日常备份脚本仍是单数据库备份。

旧 PG16 集群是升级时刻的快照。此后写入 PG18 的数据不会出现在旧集群；回退前须保存并处理这些新增变化，再恢复已核对的配置、marker 和脚本运行时路由。不要只把二进制切回 PG16，也不要将 PG18 数据交给 PG16 打开。

本次没有更改远程数据库或发布到外部。数据、向量和引用匹配证明本机升级的工程兼容性；不代表人工语义评价、完整客户验收或全新机器重建完成。日常命令与安装前提见 [本机 PostgreSQL 文档](../docs/local_postgres.md)。
