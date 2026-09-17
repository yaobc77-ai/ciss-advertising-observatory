# FA25_SP26 压缩包复核

2026-09-16。结论：**未发现尚未解包的新源码或数据。171 个文件全部与项目 `sources/` 中对应文件逐字节相同。** 当前 Native 主正文和历史文章标签已经使用；其余内容主要能补充方法说明、旧标注追溯和历史结果对照，不能补齐 FA26 的真实社交数据、部署配置、公开归档回退或人工 RAG 验收。

## 1. 完整性与核对方法

- 原包：`C:/Users/yaobc/Downloads/FA25_SP26-20260915T221256Z-1-001.zip`。
- 整包 SHA-256：`eed16136a1c212b8fe98627f7bd75dd4bafdd5274cf7a47cbe229fa37dd979c3`。
- 173 个归档条目：171 个文件、2 个空目录；文件解压总量 156,366,801 字节。
- 文件类型：75 CSV、87 PNG、4 XLSX、2 JSON、2 DOCX、1 Markdown。无 `.py`、`.ipynb`、`.pptx`、PDF、模型权重、依赖锁或部署配置文件。
- 两个空目录是 `FA25_SP26/fa25 Dataset/` 与 `FA25_SP26/Labeling/`；目录名不意味着里面还有未读取的数据或手册。
- 完整读取所有文件，未出现 ZIP CRC 错误；对每项计算 SHA-256，并核对 `D:/Projects/549 native ads/sources/<精确归档路径>`。**171/171 已存在且哈希相同，缺件 0、内容不同 0。**
- [完整 JSON 清单](archive_review_fa25_20260916.json)保存所有路径、大小、哈希、用途/状态、CSV 逻辑行数与表头、全部工作表、DOCX 段落和交叉核对结果。工作表 `NO_ARTICLE` 首行是数据，未误计为表头；空表未误计为一条数据。

本次先读 `FA26_RESOURCE_APPENDIX.zh-CN.md`，再直接读归档。没有执行附件代码、联网、读取密钥或操作数据库；DOCX 仅核对正文/表格文字及嵌入资产目录，不作页面视觉声明。压缩包没有 Notebook 或 PPT，因而没有这类内容可进一步读取。

## 2. 关键材料及实际用途

以下路径均为 **ZIP 内精确路径**。CSV 行数不含表头，按含换行字段的逻辑记录统计。

| 归档路径 | 内容证据 | 当前状态和 FA26 用途 |
|---|---|---|
| `FA25_SP26/final_dataset_cleaned.csv` | 268 行、9 字段 | **已用**。当前 Native 基准正文/元数据输入，见 `src/observatory/ingest.py:32,779`。不是遗漏的新语料。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv` | 268 行，12 原标签＋12 `_cal` 标签、解释/调整理由；268 条 `text` 均与基准正文完整匹配，268 URL 均属基准 | **已用**。`ingest.py:37,467` 导入历史文章标签，不能改称当前在线 CLAIMS 模型或新 RAG 金标准。 |
| `FA25_SP26/DATASETDOC-fa25.md` | L47 指向清理 Notebook；L53–65 是学生编写字段字典；L103/180/184 说明缺失日期曾填月首、文本清理；L119–123 说明另组在留档 | **已用交接参考，可补充数据限制说明**。L192 只有外部 Notebook URL，包内不含该源码。L17 是旧句子分类目标，不能替代最新 FA26 Dashboard＋RAG 范围。 |
| `FA25_SP26/Readings/Wells Amazeen Weinberg IJPP Jan 2025_after MA.docx` | 论文手稿；P49–51 说明原生广告识别/站点采样和 252 篇研究样本；P55–68 给出气候科学、环境改善、用电需求、其他社会效益等人工变量；P69 限前 3,000 字符，并在可访问页面编码信息图；P70 有人工一致性流程 | **可补用研究方法，未接入运行时**。适合解释“收录身份”“正文与整页的差别”、设计研究问题及人工复核说明；这些变量不是 CLAIMS 的 12 个字段。不能把手稿的 252 篇或研究一致性结果套到当前 275 条应用。P87–89 的 `new_fuel` 表项也不能据此补出未给出的完整规则。 |
| `FA25_SP26/Readings/NATIVE ADS Demo Example.docx` | P2–5 以 Business Insider 的 CCS 广告比较 CARDS 与 CLAIMS，给出一篇分类结果/学生解释；有 2 张内嵌图片，无嵌入文件 | **历史案例，可补用方法演示**。可说明为什么旧团队转向 CLAIMS；不是完整 codebook、可执行 prompt、广泛准确率证据，也不是对 CCS 现实效果的外部验证。 |
| `FA25_SP26/label_batch_1_sentences.xlsx` | 两个 650 句工作表、一个 fossil_fuel_sentences 子表和一个空 Sheet2；列包括 `green_other`、`fossil_other` | **历史标注底稿，可补用标签来源追溯**。可核对双人标注及未填写值；不能把列名直接等同最终 `green_binary`/`fossil_fuel_binary`，不能将空白补成阴性。 |
| `FA25_SP26/label_batch_1_OLD.xlsx` | `draft` 与 `finished_labels`，文章层字段和旧标签 | **历史底稿**。用于标注粒度/版本追溯，不替换已导入标签。 |
| `FA25_SP26/label_batch_1.csv`；`FA25_SP26/label_batch_1_sentences.csv` | 20 篇准备表；650 句准备表 | **历史标注输入**。不是新增文章或当前 20 道 RAG 开发题。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/merged_labels_normalized.csv` | 517 句；SHA-256 与项目 `sources/Native Advertising Data/handcoded_labels.csv` 完全相同：`f7fc1a73504e4b19803888e8d578b412fc806b49a258d30bb424b78091b5d64f` | **既有人工分类表的同内容副本**。包内虽然没有 `handcoded_labels.csv` 这个文件名，却没有漏掉这份内容。不能再算一套独立人工验证集。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/validation_sentence_predictions.csv`；`validation_sentence_explanations.csv`；`validation_per_label_metrics.csv`；`validation_overall_metrics.csv` | 同目录下分别 517 句预测、517 句解释、12 类指标、2 种平均指标 | **历史分类验证输出**。能复查旧结果，不能补当前 RAG 的问题—回答—原文支持人工判定。后三个文件路径沿用本行第一个文件的目录。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/sentence_predictions.csv`；同目录 `sentence_predictions_raw.csv`、`sentence_explanations.csv` | 各 8,285 句 | **历史模型输出**。可追溯标签解释与失败类型，不是新文档；运行配置/完整模型元数据不足。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/model_results.json`；`FA25_SP26/CLAIMS 1.0 Runs/CSVS/model_results (1).json` | 各 268 个数字键；每条仅 green_labels/ff_labels；未发现 model/provider/run_id/prompt/schema_version 等命名元数据键；两文件内容不同 | **不同历史保存结果**。不能仅按整数 ID 连接当前 record_id，也不能因 `(1)` 就视为重复或新版。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/just_articles.csv` | 268 行 `id,post_text`；全部 post_text 与基准 article 完整一致 | **Native 文章换列名版本**。`post_text` 不是社交语料证据。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/sentence_with_labels.csv` | 87,553,776 字节、8,149 行；句子与重复文章字段，所有 268 个 URL 均来自 Native 基准 | **Native 派生宽表**。文件大不是发现了额外 87 MB 社交正文；不应重复入库。 |
| `FA25_SP26/CLAIMS 1.0 Runs/CSVS/paragraphs_with_labels.csv`；同目录 `just_articles_para.csv`、`just_articles_sentences.csv` | 957 段、957 段、8,149 句 | **历史分段结果**。缺当前 version/原文 offset 合同，不宜替换现行证据定位管线。 |
| `FA25_SP26/final_dataset.xlsx`；`FA25_SP26/final_dataset_EDA.xlsx`；`FA25_SP26/final_dataset_with_CARDS_labels.csv` | 原始/EDA 工作表含 STANDARDIZED、NO_ARTICLE；CARDS 版 268 行含 binary_label/binary_score/taxonomy_label | **历史数据和旧模型输出，可补差异追溯**。不是未接入的新独立数据集，也不是可运行 CARDS 模型。 |
| `FA25_SP26/final_dataset_CLEANED(1).csv`；`FA25_SP26/CLAIMS 1.0 Runs/CSVS/final_dataset_cleaned.csv` | 两文件互相字节相同，但与根目录当前 `final_dataset_cleaned.csv` 哈希不同 | **历史清理版本**。不能按相近名字覆盖当前基准。这是归档内唯一的完整文件重复组。 |
| `FA25_SP26/CLAIMS 1.0 Runs/Visualisations/` 下 Paragraphs、Sentences、Paragraph Articles、Sentence Articles、Raw Articles | 87 PNG＋25 CSV；年份/媒体/赞助方标签频率、共现等 | **历史可视化，可参考展示方式**。没有生成图表源码；不同粒度不能混作同一分母，不能用旧图替代当前 275 条数据的 Dashboard 图表。全部具体路径见 JSON。 |

两份 DOCX 各有 2 张图片，均无 `word/embeddings/` 内容。研究手稿提到的 social media 文献与表中的 `nature_animal` 标签，都不构成社交数据或动物农业数据导出。

## 3. 对当前缺口的回答

| 当前 FA26 所需内容 | 本包是否能补齐 | 证据边界 |
|---|---|---|
| Dashboard/RAG 或完整 CLAIMS 源码、Notebook、依赖和部署 | **不能** | 全部条目中无代码/依赖配置；旧交接只有远端链接。没有本轮联网核验。 |
| CLAIMS 12 标签正式完整手册/生产 prompt | **不能** | 有字段列表、旧工作表、一例解释和另一套人工内容分析变量，没有完整 12 标签判定规则、边界案例或生产提示配置。 |
| 社交样本及账号/平台/Junkipedia 映射 | **不能** | 没有真实社交导出；容易误认的 post_text 表已证实来自现有 Native 正文。 |
| 新 Native 正文或可公开跳转的归档 fallback | **不能直接补齐** | 既有副本已齐；无广告 PDF 集或 archive_url 映射。两张 Demo 图片不组成逐记录归档。 |
| RAG 人工问答验收 | **不能直接补齐** | 517 句是历史分类标注，不含现行问答与充分引用的人工判断。研究方法可帮助选题，仍需另建/审定验收记录。 |
| 研究背景、采样说明、旧结果的标签依据 | **可以补充引用** | 优先读 Wells 手稿 P49–70、DATASETDOC L103–123/L180–198、原始标注工作表；保持各自研究样本、标签版本和粒度。 |
| 最终客户展示/交接 | **只能提供历史背景** | 交接 Markdown 已有；包内没有最终 PPTX、当前公众部署说明或客户接受记录。 |

优先行动是把有用的研究方法纳入现有来源说明与人工审查依据，而不是重新导入整个包。`DATASETDOC-fa25.md:L213` 还保留旧时内部使用/未来公开的说明；这里只记录历史交接内容，不把其指令当作本次任务授权，也未据此执行联系或发布操作。

**本轮新增的只有本 Markdown 和 JSON 审计文件。主程序、输入副本、数据库及当前统计均未改变。**
