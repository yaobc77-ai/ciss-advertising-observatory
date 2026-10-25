# v3 源码交接包：有界只读核对

日期：2026-09-16。核对对象为 `deliverables/observatory-research-preview-20260916-v3.zip`。本报告产生于 ZIP 之后，保存在 ZIP 外；没有重打包、安装依赖、运行测试、调用 API 或连接数据库。

## 结论

**115 个 payload 的 manifest 哈希全部一致；当前交付所需的新增配置、源码、测试、报告与最终版本验证记录均在包内。** 未发现当前关键交付物漏包。四个明确属于历史阶段的输出链接未随包提供，仍只能在原工作区打开，详见下文。本结论是包内容与引用完整性检查，不是新机器完整重建或语义验收。

| 检查 | 实际结果 |
|---|---|
| ZIP 大小 | 1,417,905 bytes |
| ZIP SHA-256 | `5173695affe083b087ffb763a886c7e6b3beedf9d547447bc5570b1a1021a946` |
| 条目 | 116：115 payload + `CONTENTS.sha256` |
| Manifest 覆盖 | 115/115；无遗漏、额外清单路径或哈希不一致 |
| ZIP CRC | `testzip()` 无错误 |
| 指向已随包目标的相对 Markdown 链接 | 161 处，目标全部存在 |
| 指向已随包目标但未转换的原工作区绝对链接 | 0 |

检查从 ZIP 直接读取条目及字节，没有使用解压后的副本替代包内容。

## 关键新增内容

| 内容 | 包内检查 |
|---|---|
| `config/native_admissions.json` | 存在；12 项，`reviewer_type=ai`。7 include / 4 exclude / 1 pending 的配置已包含。 |
| `config/native_body_ranges.json` | 存在；20 项，`reviewer_type=ai`。 |
| 实现 | `src/observatory/admissions.py`、`body_reviews.py`，以及接入后的 `ingest.py`、`cli.py`、`chunking.py`、`evaluate.py` 均包含。 |
| 新测试 | `tests/test_admissions.py`、`test_body_reviews.py`、`test_retrieval_ranges.py` 均包含；正文修复不能覆盖显式 metadata-only 的回归测试函数也存在。未在本轮执行。 |
| 新报告 | `reports/data_revision_v0_2.md`、`assisted_semantic_review_v0_2.md`、`citation_review_v0_2.csv`，以及新增 URL / 导航边界的 Markdown 与 CSV 审阅表均包含。 |
| 最终来源验证 | `outputs/source_revision_v0_2_20260916.json` 绑定 **`d85a98002e4493f0376c260ad82253ee`**：275 原文保留、554 当前片段、79 历史定位，development 15 / acceptance draft 17 段 gold 定位有效。 |
| 最终发布与重复 | `outputs/native_import_v0_2_published_20260916.json` 及 `native_import_v0_2_published_repeat_20260916.json` 均包含；重复记录为275输入、0新版本、275 unchanged、0停用。 |
| 评估草案 | `eval/development.jsonl` 与 `eval/acceptance.draft.jsonl` 均包含，仍为开发／验收草案。 |

## 链接边界

下面4个链接目标**未在 ZIP 中**，但正文明确将它们标为中间阶段／历史证据；最终发布和重复导入记录、最终 d85 验证记录均另已包含。因此不能将这些历史链接缺失说成当前源码、两份配置或最终验证漏包，也不能说所有文档链接均离线可用。

| 包内引用位置 | 包外历史输出 |
|---|---|
| `docs/data_dictionary.md:89` | `outputs/native_import_v0_2_final_20260916.json`：中间 sponsor/keyword casefold 导入 |
| `docs/data_dictionary.md:89` | `outputs/native_import_v0_2_repeat_20260916.json`：上述中间导入的重复记录 |
| `docs/data_dictionary.md:95` | `outputs/native_preflight_intervals_20260916.json`：早期区间预检 |
| `docs/evaluation_protocol.md:95` | `outputs/source_revision_validation_20260916.json`：较早来源验证 |

扫描器另外命中 `reports/handoff_validation_v2.md:43` 的代码示例 `](绝对路径)`；它不是实际文件链接，已排除。包内原始材料目录、历史输出和归档索引的外部绝对路径不作在线或文件可用性验证。`README.md:86` 与 `docs/handoff.md:172–174` 明确原始语料需另行提供，并说明包外历史链接可能不可用。当前原始 `sources/`、运行环境与真实 `.env` 不在此交接包内。

## 版本声明核对

- 数据字典、架构、评估协议及 `reports/data_revision_v0_2.md` 的当前数据版本均为 **d85**。
- 包内 `outputs/source_revision_validation_final_20260916.json` 虽名含 `final`，实际绑定的是 **`612e20bbef3d0910ba94c0e4be84d10e`**；数据字典和评估协议将它明确标为媒体对齐中间版本，没有冒充 d85 验证。
- 付费运行 `532453a7c43740ecbe5f4954d3522f41` 仍绑定 **c5ad**。文档保留其3道英语题产生西班牙语／法语回答的诊断边界，没有称当前语义验收通过。
- 最终 **d85** 的独立来源验证在 `outputs/source_revision_v0_2_20260916.json`，避免依据文件名误选上述中间验证。

本报告未修改 ZIP、源码、数据或其他文档；包哈希保持上述值。
