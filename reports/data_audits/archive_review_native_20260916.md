# Native Advertising Data 压缩包复核

日期：2026-09-16。对象：`C:/Users/yaobc/Downloads/Native Advertising Data-20260915T221323Z-1-001.zip`。

## 结论

**包内只有 4 个表格文件，无额外内层 ZIP；4 个文件全部与项目已有副本 SHA-256 相同。** 没有发现尚未取得的社交数据、采集代码、Notebook、字段说明文档、部署配置、PDF 或截图文件。XLSX 自身是 OOXML ZIP 容器，不计作一个新的资料包；两份工作簿均只有一个可见工作表，没有嵌入附件或 VBA 部件。

这并不表示所有字段都已用于产品：原始媒体链接保存在内部 metadata；合并 CSV 保留了一些被旧清理过程删去或破坏的参考链接。它们可供后续来源链接修复，但不能直接当作公开归档、完整正文或已经核实的证据。

完整字段、源行和哈希见 [机器审计 JSON](<D:/Projects/549 native ads/.tmp/archive_review_native_20260916.json>)。本次读取了已有资源附录与质量报告，然后直接解析归档和现有源文件验证；没有只按文件名认定同版，没有执行附件代码、联网、调用模型或操作数据库。

## 清单、精确身份及用途

归档大小 **977,308 bytes**，SHA-256：`73535a6651862886a7caca297f05c8f081e3d8b768e08249052f0475651e2c2b`。

| 精确 ZIP 成员路径 | 实际内容 | 当前使用情况 |
|---|---|---|
| `Native Advertising Data/native_ad_dataset.xlsx` | `Sheet1`，268 条数据、268 唯一 URL、14 字段；最大格式化行号 1000 不等于 999 条数据 | importer 使用唯一 URL 补 disclosure/notes；完整源行保存在 `raw.metadata`。 |
| `Native Advertising Data/final_dataset_CLEANED.xlsx` | `final_dataset_CLEANED`，268 条、268 唯一 URL、9 字段 | 已知历史替代版本；正文优先用 `sources/FA25_SP26/final_dataset_cleaned.csv`，有据而非漏读。 |
| `Native Advertising Data/combined_ads_12-4-25.csv` | 280 条、280 唯一 URL、7 字段；与基准共享 268 URL，额外 12 URL | 与 importer 实際主读的 nested_unique 副本字节相同；增补按现有 7 纳入／4 排除／1 待核决定处理。共享 URL 的正文不由此自动覆盖基准。 |
| `Native Advertising Data/handcoded_labels.csv` | 517 句、16 个 legacy `doc_id`、517 唯一 `(doc_id,sent_idx)`；15 字段 | 旧分类器人工参考，已有方法审阅；没有生产导入，也不能作为现成 RAG 问答金标准。 |

四个本地对应文件均位于 `D:/Projects/549 native ads/sources/Native Advertising Data/`，逐项字节哈希一致：

| 文件 | Bytes | SHA-256 |
|---|---:|---|
| `native_ad_dataset.xlsx` | 102983 | `1dcabfcdb3369e52ecd4a9d2b428e589b51e888bb7afb348f0f287cf7e84510e` |
| `final_dataset_CLEANED.xlsx` | 422850 | `5cd04454ca2f64aaa0e24f309014a7dd2f22653cc7e238b1e5bb261b7719de64` |
| `combined_ads_12-4-25.csv` | 1245171 | `a677a6de6a8c10a4f872456263af72f0f99be4c3c561bf8b7449bce9b892dd57` |
| `handcoded_labels.csv` | 95674 | `f7fc1a73504e4b19803888e8d578b412fc806b49a258d30bb424b78091b5d64f` |

`sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv` 的哈希亦为上表 `a677…dd57`，与 ZIP 成员字节相同。该核对消除了“只因同名便认定版本相同”的不确定性。

## 字段与关键质量证据

- 原始 XLSX 14 字段：`id,url,publisher,title,date,sponsor,keyword,image url,video url,embedded url,disclosure language,disclosure description,disclosure code,notes`。只有列名和逐记录 notes，没有独立数据字典或隐藏说明表。
- 清理 XLSX 9 字段：`publisher,keyword,url,title,Disclosure language,sponsor,date,article,is_video`。
- 合并 CSV 7 字段：`publisher,keyword,url,title,sponsor,date,article`。空日期 56、空正文 4、空 sponsor 2、空 title 1；26 条 `article=video`。这些是字段/正文限制，不能据 280 行声称 280 篇可用全文。
- 原始 `Sheet1!K42` 是字符串 `None`，L42/M42 是 `N/A`，并非真实披露信息；`C190` 是损坏的 Forbes URL，不是媒体名称。`F218=BP` 而 `G218=American Petroleum Institute`，继续说明 keyword 不能代替 sponsor。
- 清理 XLSX 的 268 个 URL 与基准 CSV 相同；**267 条正文完全相同，唯一差异是 `final_dataset_CLEANED!H220` 数字 2，对应基准 CSV 第 220 行有 28,167 字符正文。** 这个 XLSX 不提供遗漏的新完整正文。

## 合并 CSV 的旧正文差异与可复用链接

268 个共享 URL 中，正文字符串 **81 条完全相同、187 条不同**。仅为诊断，将字符串 NFKC、casefold 并仅保留字母数字后，187 条中 153 条一致、34 条仍不同。该比较不改变原文、不参与引用定位，也不能证明语义等价。

抽看两个字符增加最多的例子：

| 原文位置 | 比基准多出的内容 | 判断 |
|---|---|---|
| 合并 CSV 第 240 行；基准第 238 行，`why-pipelines-and-production-are-pathways-to-progress` | 8,472 对 7,430 字符，主要增加 BLS/EIA/API 等外部参考 URL | 可用于核对旧清理删去的参考链接；不是新发现的文章续文。 |
| 合并 CSV 第 245 行；基准第 243 行，`how-energy-and-the-environment-can-collectively-thrive` | 9,355 对 8,029 字符，保留编号外链；基准残留 `1https://` 等碎片 | 可用于修复脚注链接，需独立核验目标与用途；不能只因更长便覆盖当前正文。 |

本轮未逐篇裁定这 34 条剩余差异的语义完整性。因此结论是“原始差异来源已在本地、没有发现新增文件”，不是“所有原文已完整使用”或“所有差异都只有格式”。JSON 保留了全部 187 条差异的 URL、两份源行和长度，便于之后有界复核，不自动形成新的采纳决定。

原始元数据中的媒体列也有潜在用途：`image url` 有 179 条非占位值、其中 178 条以 HTTP(S) 开头；`video url` 114 条、`embedded url` 130 条均以 HTTP(S) 开头。这些计数可重叠，不能相加当记录数。本轮未访问链接，HTTP 前缀不证明可达、版权许可、文章身份或归档有效性。当前 importer 已保存这些字段，但公众投影和文本 RAG 不使用它们。

## 手工标签为什么不是当前 RAG 验收集

`handcoded_labels.csv` 的字段是 `doc_id,sent_idx,sentence` 加 12 个布尔标签：8 个 `green_labels.*`、4 个 `ff_labels.*`。共 517 句，各字段没有空白值，数字 ID 是该历史产物内部标识。

它没有问题、参考回答、rubric、URL、稳定 record/version ID 或原文字符偏移。它可核对内容已经对应上的**旧句子分类输出**；不能据相同 doc_id 直接接当前文章，也不能验证 RAG 选到的来源是否充分、生成 claim 是否被支持、引用是否完整。当前生产静态标签来自另外的 `sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv`，按 URL＋全文一致性连接，不能把这个手工表与生产标签文件混称。

因此，“没有把手工表导入生产 RAG”有任务边界依据，并不代表漏用了一套现成 RAG 金标准。原始 FA26 文档也明确将 CLAIMS backend 延期。

## 实现与既有审阅定位

- `src/observatory/ingest.py:32–38`：当前各输入路径；`:467–543`：历史预测按 URL＋全文匹配；`:547`：合并 CSV 备用路径；`:879–909`：XLSX 来源及 `raw.metadata` 保留。
- `src/observatory/db.py:182–195`：公众字段投影不包含媒体辅助列或 disclosure。
- `FA26_RESOURCE_APPENDIX.zh-CN.md:54–64`：历史四文件目录记录；本次新增的是字节一致性确认。
- `FA26_EXISTING_QUALITY_AND_IO.zh-CN.md:41–55`：已知 XLSX/CSV、披露及字段问题；其中早期“未找到应用”等建设前状态不能代替当前实现状态。
- `analysis/prior_methods_review.md:15–36`：手标与历史句子预测的用途和跨文件数字 ID 限制。

尚缺的真实社交导出、其字段说明、Miami 原型访问及公众部署资料，不能由这四个原生广告表格补齐。本轮只写本报告和机器 JSON，没有创建/修改工作簿或运行附件代码。
