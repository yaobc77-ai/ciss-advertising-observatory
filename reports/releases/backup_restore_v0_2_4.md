# 当前原生快照的备份与恢复 — 0.2.4

2026-09-16 使用现有 `scripts/local_postgres.py backup/restore`，把主库 `observatory` 的当前快照恢复到新库 `observatory_restore_v024_20260916`。没有覆盖旧库或备份，也没有切换应用连接。完整结果见 [验证记录](../outputs/backup_restore_v0_2_4_20260916.json)。

## 备份及一致性

- 备份：`.runtime/backups/observatory-v024-20260916T203146793999Z.dump`，9,638,747 字节。
- SHA-256：`50c4cf3758176586f343ae78ebbaaa3559e853f509c2494cd984b52512aef4a7`；已核对同名 `.dump.sha256`，恢复后文件哈希未变。
- 数据版本：`5114ebc1cf9afe59cdaa715e3ea45166`。主库备份前、操作后和恢复库均为 **275 收录 / 263 可计数 / 226 可检索 / 558 当前块**。
- 三个检查点的全部业务表逐行内容指纹、表 owner、列定义、索引、约束及序列状态相同。

| 表 | 三个检查点共同的行数 |
|---|---:|
| records | 275 |
| record_versions | 828 |
| chunks | 1,634 |
| annotations | 1,608 |
| embeddings | 611 |
| imports | 13 |
| usage_ledger | 148 |
| answer_runs | 110 |
| generation_outputs | 105 |

表总数包含历史版本，不等于当前可检索语料规模。账本有 146 条 settled、2 条 cancelled；本应用当月已结算 **$0.15530368**，无 pending/uncertain 条目。本次恢复验证没有调用付费 API。

## 全量定位检查

恢复后检查全部 828 个正文哈希、1,634 个块的身份/版本/哈希/字符区间，以及 110 个已保存回答中的 704 个 evidence 和 177 个引用，均有效。这里的分母来自当前数据库全部已保存记录，不是单轮开发集成绩。

其中 **267 个 evidence、94 个引用**指向该文章已非当前的正文版本；仍能回到其生成时的原文。检查保留原始引文，未将旧回答重新绑定到新正文，也未修改先前错误答案。

## 方法与运行边界

1. 在只读、可重复读事务中读取主库；固定会话时区为 UTC。对每行的 PostgreSQL `to_jsonb(row)::text` 计算 SHA-256，将排序后的行哈希再哈希，形成表内容指纹。另比较列、索引、约束、序列和角色信息。
2. 用项目现有备份入口调用 `pg_dump --format=custom`，核对归档及旁路哈希文件。
3. 用现有恢复入口向不存在的新库执行 `pg_restore --exit-on-error --single-transaction`。读取恢复库，再读取主库，逐项比较快照结果。
4. 对全部已存 evidence 核对 chunk ID、记录/版本、正文区间；引用还须为其对应 evidence 的非空逐字子串。
5. `.env` 和私有数据库凭据文件只在内存比较字节哈希，结果未变；不保存秘密值或凭据哈希。运行中应用 `/healthz` 仍为 `ok`、同一数据版本和 558 块。

最初通过 Windows PowerShell 5 的 `powershell.exe -NoProfile -File` 启动 wrapper，被其默认 `Restricted` 策略阻止，没有创建备份。随后使用 wrapper 本来调用的 Python CLI；没有修改执行策略。当前工具所在 PowerShell Core 为 `RemoteSigned`。因此本轮证明的是 **Python 备份/恢复入口**，不把失败的 Windows PowerShell 5 调用记为通过。

此验证只覆盖同一 Windows 机器、同一 PostgreSQL 集群中的独立恢复库。单数据库逻辑备份不包含全局角色密码、应用环境或整机恢复；尚未完成异机灾备或公众网络验收。定位有效也不代表回答语义正确。

## 接手命令

从项目根目录执行；下列命令不会改变系统执行策略。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py backup

# 用上一步实际生成的路径替换占位，并选择一个尚不存在的新库名。
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py restore `
  --backup-file '.runtime/backups/实际备份文件.dump' `
  --database observatory_restore_review
```

备份与恢复库保留在本机，均不进入源码包或 Git。较早的 [268 条快照恢复报告](backup_restore.md)保留为历史记录。
