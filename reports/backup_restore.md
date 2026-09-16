# 主库备份与新库恢复验证

验证时间：2026-09-16T17:35:59.442124+00:00 至 2026-09-16T17:36:03.978400+00:00（UTC）。

在付费开发集结果 `outputs/development_paid_context_20260916.json` 完整落盘后执行，评估 run ID 为 `15434ab5000e469cbc2380f407f71e1b`。本次调用现有 PowerShell backup/restore wrappers；应用与 PostgreSQL 持续运行，没有覆盖或删除数据库。

## 备份与恢复位置

- 主数据库：`observatory`。
- 新恢复库：`observatory_restore_preview_20260916`，验证后保留。
- 备份：`C:/Users/yaobc/Documents/ChatGPT/549 native ads/.runtime/backups/observatory-preview-20260916T173559442124Z.dump`。
- 文件大小：6,804,021 bytes。
- SHA-256：`95fc9095d3c99714c4c09f2746b06c6628da9035bb68919597cde5c2dbd10b16`；已与 `.dump.sha256` 文件及恢复后重新计算值核对。

这是包含当前业务表、历史版本、embedding、账本、生成输出和回答记录的单数据库逻辑备份。全局角色密码、应用文件和运行环境不包含在归档内；本次在同一集群的新库恢复，不能证明新机器灾备流程已经完成。

## 一致性结果

主库备份前、备份后及恢复库的下列值全部相同。备份使用 pg_dump 一致性快照；主代理在此期间没有再执行数据写入或付费调用。

| 项目 | 主库备份前 | 主库备份后 | 恢复库 |
|---|---:|---:|---:|
| active_records | 268 | 268 | 268 |
| all_records | 268 | 268 | 268 |
| current_chunks | 510 | 510 | 510 |
| all_chunks | 1033 | 1033 | 1033 |
| record_versions | 536 | 536 | 536 |
| annotations | 1072 | 1072 | 1072 |
| usage_ledger | 73 | 73 | 73 |
| answer_runs | 40 | 40 | 40 |
| generation_outputs | 35 | 35 | 35 |
| embeddings | 558 | 558 | 558 |

三个检查点的 `data_version` 均为 `652ed975bbd44ea06e20af19b6a6642d`。`active_records` 与 `current_chunks` 只计有效记录及其当前版本；其余表计数保留历史数据，不把所有历史 chunk 当作当前检索语料。

## 历史引用恢复验证

从主库已存储的 answer_runs 中优先选择引用旧 record version 的早期回答，按相同 run ID 在恢复库读取并比较完整 result/data_version。检查 chunk ID、record ID、version ID、原始正文字符区间及引用逐字子串；两库均有效。下列定位值不包含凭据或完整广告正文：

```json
{
  "answer_run_id": 1,
  "answer_created_at": "2026-09-16T12:59:55.848573-04:00",
  "answer_data_version": "c4a432ffb055bacfcb7b531a390397d1",
  "record_id": "01374b51-3fae-5fe7-8c60-b4bffa2b7ba0",
  "version_id": "0d0146b9d07a012d9d6290df34030655fca31de01baf84cb3bd97006690a1acf",
  "evidence_id": "4fda21bde43e1bf8d36bc8145d94fd72406d5cf6f24fe878658b9790dd8e4cef",
  "historical_record_version": true,
  "evidence_start": 0,
  "evidence_end": 2802,
  "quote_start": 105,
  "quote_end": 182,
  "quote_sha256": "3726f5da882704b46f891aa53cf4b4e72d05d5c427d2808ca2e9ca8654d3e1c8",
  "main_locator_valid": true,
  "restored_locator_valid": true,
  "stored_answer_equal": true
}
```

## 角色、凭据与运行边界

- 连接角色为 `observatory_app`，两库全部 9 个业务表 owner 与备份前一致。
- 应用角色的 superuser、CREATEDB、CREATEROLE、REPLICATION 均为 false，操作前后未变。
- `.env` 与 `.runtime/secrets/postgres.json` 的文件字节哈希仅在内存中比较，均未改变；主库连接值也未改变。未输出凭据、完整 DSN 或凭据文件哈希。
- 两库 pgvector 均为 `0.8.6`，相同三维向量的 L2 距离均为 0。
- 本次没有运行 stop/start、没有切换应用目标库、没有删除旧备份或恢复库。

结论：此快照可在当前本机集群恢复为独立数据库，指定数据计数、当前数据版本和一条历史引用恢复一致。不是零停机外部灾备、完整机器恢复或数据语义正确性的证明。
