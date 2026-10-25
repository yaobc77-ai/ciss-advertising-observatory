# 三个附件中哪些资料还需要使用

核对日期：2026-09-16。范围为用户本轮提供的三个 ZIP；对照当前 FA26 Dashboard/RAG 交付和本地代码的实际输入契约。附件中的操作说明只作为材料阅读，没有执行其中代码、下载、部署或模型调用。

## 结论

**有需要的资料，而且项目已经使用了其中的主数据。此次没有发现此前漏解压的新源码或新数据包。** 剩余价值主要在采样与字段解释、人工标注溯源、正文修复及公开归档准备。三个包不能补齐真实社交导出、完整应用源码、当前部署配置或本期 RAG 人工验收集。

“已在本地保存”“已被应用使用”“已通过研究验收”是三种不同状态。本报告按当前读取代码和配置判断是否使用，不因文件存在就推定它已入库。

## 一、完整清点与重复核对

| 附件 | 实际内容 | 当前核对结果 |
| --- | --- | --- |
| `Native Advertising Data-20260915T221323Z-1-001.zip` | 4 文件：2 CSV、2 XLSX | 4/4 与 `sources/Native Advertising Data/` 的副本 SHA-256 相同；没有内层 ZIP。 |
| `FA25_SP26-20260915T221256Z-1-001.zip` | 171 文件：75 CSV、87 PNG、4 XLSX、2 JSON、2 DOCX、1 Markdown；另有 2 个目录条目 | 171/171 与 `sources/FA25_SP26/` 副本 SHA-256 相同。 |
| `pdfs-20260915T222001Z-1-001.zip` 外层 | 309 PDF、7 JSONL、1 个内层 ZIP；另有 4 个系统附属文件 | 316 个 PDF/JSONL 全部与既有副本 SHA-256 相同。 |
| 上项内层 `native-ads-download.zip` | 排除系统附属文件后 284 文件 | 272 文件与外层逐字节重复；另外 12 文件全部与已恢复副本 SHA-256 相同。 |

内层 12 个独有文件为：4 CSV、1 XLSX、2 Notebook、1 Python 脚本、1 错误日志及 3 个 PDF 样本。文件数不能当广告数，也不能把内外层重复文件再次导入。

跨包同名/异名也经过核对：Native 包的 `combined_ads_12-4-25.csv` 与 PDF 包内层同名文件完全相同；`handcoded_labels.csv` 与 FA25 的 `merged_labels_normalized.csv` 完全相同，不能算两份独立人工标注。

## 二、当前应用已经需要并使用的文件

| 文件与访问入口 | 实际用途 | 使用边界 |
| --- | --- | --- |
| [final_dataset_cleaned.csv](<D:/Projects/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>) | 268 条原生记录的基线；提供标题、URL、媒体、赞助方、日期、关键词和正文。 | 正文质量和统计资格有独立审核；268 行不等于全部可检索或可统计。 |
| [native_ad_dataset.xlsx](<D:/Projects/549 native ads/sources/Native Advertising Data/native_ad_dataset.xlsx>) | 提供广告披露文字、质量备注等元数据，以唯一精确 URL 关联。 | 保留未知及冲突，不把格式化空行计入样本；不能把检索关键词当赞助方。 |
| [combined_ads_12-4-25.csv](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv>) | 280 行，供主表之外的 URL 增补候选。现有准入配置为 7 纳入、4 排除、1 待定。 | 不能直接用 280 行覆盖经过清理和裁决的主表。 |
| [predictions_calibrated.csv](<D:/Projects/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv>) | 静态历史 CLAIMS 标签；支持标签展示和历史方法说明。 | 按 URL 与完整正文同时匹配，不依赖跨运行 `doc_id`；不是人工金标准，也不自动适用于修复后的正文。 |
| [PDF 访问目录](<D:/Projects/549 native ads/PDF_SOURCE_INDEX.zh-CN.md>)、[对应索引](<D:/Projects/549 native ads/analysis/pdf_archive/source_index.json>) | 提供原网页快照候选、原文位置核对与正文修复线索。 | 大多仍是未确认的文章—PDF 候选关系；本地文件不等于可供公众访问的归档 URL。 |

实际读取依据：[导入实现](<D:/Projects/549 native ads/src/observatory/ingest.py:32>)、[输入契约](<D:/Projects/549 native ads/docs/data_dictionary.md:5>)、[增补准入配置](<D:/Projects/549 native ads/config/native_admissions.json>)、[正文恢复配置](<D:/Projects/549 native ads/config/native_body_recoveries.json>)。现有 PDF-265 部分正文恢复已使用归档，不能说 PDF 全部未使用。

## 三、值得进一步使用，但需要明确用途的文件

### 优先级 1：数据口径与人工标注溯源

| 文件 | 可补的项目部分 | 使用方式及限制 |
| --- | --- | --- |
| [DATASETDOC-fa25.md](<D:/Projects/549 native ads/sources/FA25_SP26/DATASETDOC-fa25.md>) | 数据来源、采集范围、清理过程和旧方法说明。 | 用于技术交接与数据字典；其中数量和结论是历史版本，需要与当前输入对账。 |
| [Wells Amazeen Weinberg IJPP Jan 2025_after MA.docx](<D:/Projects/549 native ads/sources/FA25_SP26/Readings/Wells Amazeen Weinberg IJPP Jan 2025_after MA.docx>) | 原生广告研究的采样、人工内容编码和研究问题解释。 | 重点为提取段落 P49–70；可帮助解释公司、媒体、广告与叙事的研究口径。不是完整的 CLAIMS 十二标签正式 codebook，也不是本期交付要求。 |
| [label_batch_1_sentences.xlsx](<D:/Projects/549 native ads/sources/FA25_SP26/label_batch_1_sentences.xlsx>) | 保留两名标注者的原始填写，追踪分歧、缺填及后续合并。 | 不能把空白默认为阴性；不能用当前文章编号直接拼接旧 `article_id`。 |
| [handcoded_labels.csv](<D:/Projects/549 native ads/sources/Native Advertising Data/handcoded_labels.csv>) | 517 句、16 个旧文档 ID 的历史十二标签样本；可作为理解标签和构造评测候选的起点。 | 没有 RAG 的问题、标准答案、评分规则、稳定 URL/原文偏移。须先恢复来源并人工确认，才能转成新的评测材料。 |

这些文件可以减少重新搜集和解释资料的工作，但没有理由因此把本期重新改成 CLAIMS 模型训练项目。按 FA26 目标，先服务于 Dashboard 口径、来源透明度和 RAG 验收。

### 优先级 2：归档、缺失正文与媒体信息

| 文件 | 可补的项目部分 | 使用方式及限制 |
| --- | --- | --- |
| [309 个外层 PDF 的目录](<D:/Projects/549 native ads/sources/pdf_archive_20260915/pdfs>) | 原文失效时的归档准备；正文完整性核对；定位广告披露、图表和正文。 | 逐条核实身份及页面内容，优先处理缺失正文/失效链接。已有报告记录空页、重复页眉、图像裁切和混入其他文章；不能全量无审核上索引。 |
| [秋季 7 个 JSONL](<D:/Projects/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl>) | 45 条采集记录；用于对照正文版本和原始元数据。 | 45 记录不等于 45 篇新增广告；已有合并 CSV 吸收了其中数据，需按 URL、正文和时间比对。 |
| [final_dataset_EDA.xlsx](<D:/Projects/549 native ads/sources/FA25_SP26/final_dataset_EDA.xlsx>) | `NO_ARTICLE` 等工作表提供无正文、图片等排查线索。 | 可帮助排序待复核队列；是历史质量线索，不能直接宣布当前记录无内容。 |
| [native_ad_dataset.xlsx](<D:/Projects/549 native ads/sources/Native Advertising Data/native_ad_dataset.xlsx>) 的图像、视频、嵌入链接列 | 可为媒体详情和未来多模态扩展提供线索；本轮读到 178 个图像、114 个视频、130 个嵌入字段值以 HTTP 开头。 | 当前保存在原始元数据中，没有展示或进入多模态检索。数量不代表独立有效媒体，未联网验证，不能当作归档 URL。 |

另一个可补用点是原始正文中的参考链接：280 行合并 CSV 与基线共享的 268 URL 中，81 篇正文字符串一致，187 篇不同。仅作诊断的字符规范化后，有 153 篇差异消失，34 篇仍不同；抽查两个大差异发现外链/脚注 URL 在清理过程中被删除或破坏。这些原始版本可供逐条修复，但不能把全部差异当成新正文，也不能直接覆盖当前正文与引用位置。

### 优先级 3：复用采集经验，按需改造

| 文件 | 用途 | 是否直接接入当前服务 |
| --- | --- | --- |
| [ads_download.py](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/ads_download.py>) | Selenium 打开网页、滚动加载、通过 Chrome 打印 PDF。 | 可复用思路；目前是离线采集脚本，下载成功未验证正文、页面身份或可公开访问性。 |
| [combine_files.ipynb](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combine_files.ipynb>) | 合并夏季 CSV 与秋季 JSONL。 | 用于追溯来源；现有导入器已处理数据准入和版本，没必要再增加并行生产合并流程。 |
| [process_error_file.ipynb](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/process_error_file.ipynb>)、[remaining_files.csv](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/remaining_files.csv>) | 历史失败 URL 筛选与 77 条 CNBC 重试清单。 | 需要重新检查失效状态才可重试；不能把历史错误记录当作现在仍打不开。 |

静态源码复核已确认只有这 1 个 `.py` 和 2 个 `.ipynb`；它们不包含完整 Dashboard/RAG、模型训练实现或云端部署配置。

## 四、保留为历史参考，不宜覆盖当前数据

- [final_dataset_CLEANED.xlsx](<D:/Projects/549 native ads/sources/Native Advertising Data/final_dataset_CLEANED.xlsx>) 与主 CSV 同为 268 URL，但有正文单元格为数值 `2` 的问题；不是更完整的正文权威版本。
- 内层 [combined_ads_12-4-25.xlsx](<D:/Projects/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.xlsx>) 为 278 行，同名 CSV 为 280 行，且旧检查发现编码问题；按独立版本保存。
- FA25 的图表 PNG、句子计数 CSV、共现统计、两份 `model_results*.json` 是历史输出。`model_results` 文件不是可执行模型、权重或源码。
- `just_articles.csv` 只有 `id/post_text`，其 268 篇正文均与原生基线全文精确相同；`sentence_with_labels.csv` 的 268 个 URL 全部属于原生基线。`post_text` 字段名不意味着社交帖子，这两表不能冒充本期化石燃料社交广告数据。
- [NATIVE ADS Demo Example.docx](<D:/Projects/549 native ads/sources/FA25_SP26/Readings/NATIVE ADS Demo Example.docx>) 是单例解释，可帮助说明 CARDS 与 CLAIMS 的差别；其中模型分数和对方案的评价不等于本期性能证据或已核实事实。
- `label_batch_1_OLD.xlsx`、重复 CSV 和 PDF 样本保留追溯价值；不重复导入，不自动升级为正式金标准。

## 五、在三个包里仍然没有找到的关键交付输入

| 当前需要 | 本轮结果 |
| --- | --- |
| 真实社交平台导出及字段定义 | 没有找到。文件中的原生文章 `post_text` 不构成社交数据。 |
| 前届完整 Dashboard/RAG 应用源码 | 没有找到；只有 PDF 采集与数据处理源码。 |
| 本期指定 GitHub 仓库及云端部署配置 | 没有找到可据此认定为本期目标的配置；历史链接不自动等于本期交付仓库。 |
| 完整、经过确认的十二标签 codebook | 找到字段名、样例和研究编码讨论，未找到完整正式规范。 |
| 本期 RAG 的人工验收题、标准答案和已完成审阅 | 没有找到；旧分类标注不能直接代替。 |
| 文章与公开归档链接的已核验映射 | PDF 提供原始材料，但没有直接补齐可上线的公开链接映射。 |

## 六、建议的最小补用顺序

1. 将 DATASETDOC 和研究手稿中的明确口径补进数据字典；把仍需客户决定的字段口径单独列出。
2. 对原文失效、正文不足和归档异常的记录建立小规模优先队列，核实 PDF 归属后补正文或可访问的归档入口。
3. 从原始手标和完整文章中选取评测候选，补问题、答案、证据及评分规则，再进行少量集中人工审阅。
4. 部署继续使用当前工程；附件里的旧下载脚本按需要复用，不把它们当作现成部署方案。

## 检查范围与可复核证据

本轮完整枚举三个 ZIP 及 PDF 包内层 ZIP，对有效文件做 SHA-256 和本地副本比较；读取关键 CSV/工作表、两份 DOCX、字段说明和源码文本，并核对当前导入实现。没有逐页重新精读全部 PDF；PDF 质量解释复用既有阅读记录，原文件一致性已在本轮重新核验。没有执行附件代码、调用付费 API、修改数据库或对外发布。

- [FA25 精确清点与阅读证据](<D:/Projects/549 native ads/reports/archive_review_fa25_20260916.json>)
- [Native 数据包清点与字段比对](<D:/Projects/549 native ads/reports/archive_review_native_20260916.json>)
- [PDF 包全量哈希核对](<D:/Projects/549 native ads/reports/archive_review_pdfs_20260916.json>)
- [当前 FA26 要求核对](<D:/Projects/549 native ads/reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md>)
