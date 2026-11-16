# FA26 现有资产质量、输入与输出

核查日期：2026-09-16。范围：当前工作区的交接数据、保存的 CLAIMS 结果、归档采集代码与既有审计记录。表格行数不含表头，按 CSV 记录解析，不能用文件物理行数代替。

## 1. 结论与项目边界

**现有成果以数据、网页存档和历史分类结果为主，可以作为 Dashboard 与 RAG 的开发输入；完整应用及其运行链路尚未在本地找到。**

根据最新 [FA26 项目介绍](<C:/Users/yaobc/Downloads/[FA26] DS 549_ CISS Fossil Fuel and Animal Agriculture Advertising Observatory (1).docx>)：

- 本学期建设化石燃料原生广告、化石燃料社交媒体广告的 Dashboard，提供筛选、图表与 RAG 搜索。
- 原生广告展示字段为 `url、publisher、title、date、sponsor、keyword`。披露文字保留在内部数据结构中，不作为看板展示字段。
- RAG 重点支持 CCS、biogas 等技术与燃料相关主张的检索，面向记者、法律工作者及非计算研究者。
- **CLAIMS 后端接入推迟到未来学期**。已存在的标签可在版本和关联关系核对后作为历史数据使用；主题模型属于可选扩展。

因此，本报告把质量分为三个问题：数据能否用于统计、正文能否作为回答证据、处理过程能否重复运行。不会用一个总分代替这些判断。

## 2. 已有数据及其质量

| 资产 | 已有规模与内容 | 当前质量判断 | 对本学期的用途 |
| --- | --- | --- | --- |
| 原生广告元数据 XLSX | 268 条、268 个唯一 URL；14 字段，含媒体、赞助方、日期、披露、媒体链接 | 结构已具备；仍有错误单元格、名称归一和日期精度问题 | 作为来源元数据和字段追溯依据 |
| 清洗正文 CSV | 268 条、268 个唯一 URL；26 条正文仅为 `video` | 242 条非视频占位的正文候选，尚不能称为 242 篇完整正文 | 元数据浏览的起点；正文经检查后进入 RAG |
| 较大合并版本 | CSV 280 条，同名 XLSX 278 条 | CSV 缺日期 56、缺正文 4；XLSX 缺日期 55、缺正文 2；还存在正文版本差异 | 提供补充来源与正文候选，不能直接累加到 268 |
| 外层网页 PDF | 309 份、既有清单合计 2,054 页 | 已全量提取文字；存在空白、页脚、裁切、混篇等问题，未全量视觉审核 | 原文留档、补正文和核对引用 |
| 秋季 JSONL | 7 文件、45 条记录 | 已有逐条阅读记录；部分抓取为页脚或错误内容 | 作为另一种正文候选，按文章比对后选择 |
| CLAIMS 保存结果 | 文章、段落、句子级输出及静态分析文件 | 校准表的 268 条全文已与主表对齐；其他运行与人工验证的 ID 仍需区别 | 已对齐结果可作为带来源标记的历史标签导入 |
| 人工标注 | 最终表 517 句、16 个文章 ID；另有人员标注工作表 | 小样本且类别不均衡；标注底稿有未填项，合并语义需保留 | 检查对应历史分类结果，不能验证 RAG 回答质量 |
| 社交媒体数据 | 项目文档描述约 37k Twitter 帖子及 CLAIMS 标签，FB/Instagram 后续补充 | 当前工作区未找到对应导出，字段和完整性未在本地验证 | 本学期另一必需输入，仍需取得并核对 |

表中的 268、280、309、45 是不同资产或版本的计数，不能相加当作广告总数。268 个唯一 URL 也不自动证明每条记录都是有效、完整且研究范围内的广告。

六个展示字段在原始元数据和主 CSV 中均非空；非空不代表有效值。合并 CSV 还缺赞助方 2 条、标题 1 条，同名 XLSX 缺赞助方 1 条。四表的 `keyword` 均无空值或本次检查的占位值。

本次按 URL 精确核对：原始元数据与清洗 CSV 的 268 条集合相同，而且全部包含在两个较大合并版本中。合并 CSV 比清洗表多 12 条，XLSX 多 10 条。CSV 相比 XLSX 额外包含 Bayer menopause 页面和 Shell 法律免责声明 PDF，需要判断研究范围和附件角色，不能自动算作新增化石燃料广告。

两个合并格式共享的 278 个 URL 中，**218 条正文字符串不同**；XLSX 中 **199 条**命中定向检查的乱码标记。这说明“同名、同 URL”仍需要选择和核对正文版本。该乱码检测不是全库语言质量评估，也没有自动修复原文。

### 主要数据入口

- [原始元数据 native_ad_dataset.xlsx](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/native_ad_dataset.xlsx>)：`Sheet1`。
- [清洗正文 final_dataset_cleaned.csv](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>)。
- [合并 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv>)、[同名 XLSX](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.xlsx>)。
- [PDF 与原文访问目录](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/PDF_SOURCE_INDEX.zh-CN.md>)。

### 对使用方式影响最大的质量问题

1. **正文占位与正文完整性。** `article = video` 不能用于正文问答。即使有长文本，也可能只是导航、页脚或多篇混合。视频记录仍可在元数据列表中展示；是否计入广告数取决于身份与去重核验。
2. **文件版本存在差异。** [清洗 XLSX](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/final_dataset_CLEANED.xlsx>) 的 `final_dataset_CLEANED!H220` 是数字 `2`，同一 URL 的主 CSV 有 28,167 字符正文。不能只凭“cleaned”文件名选定权威版本。
3. **赞助方与检索词不同。** 原始表 `Sheet1!F218` 为 BP，`G218` 为 American Petroleum Institute。`keyword` 记录检索线索，不能用它替代 `sponsor` 统计公司。
4. **日期需要保留原始精度和冲突。** 原始/清洗版本的 268 条日期均可解析，但原始备注有 19 条明确指出 URL 日期与数据日期不一致，合并表另有可疑的 `1970-08-23`。旧清洗流程有补齐缺失日期成分的描述；可解析不等于已核实。保留原值，并区分日、月、年、未知精度。
5. **PDF 的来源匹配仍有不确定性。** 现有索引为 300 个唯一标题匹配、2 个多候选、7 个未匹配。这是标题候选关联，没有逐篇完成正文一致性验证。
6. **样本分布不代表总体。** 清洗库明显集中于部分媒体与公司。看板应描述“本数据集中的记录”，不能将比例推广为整个行业的广告投放比例。
7. **披露字段转换丢失了原始含义。** 原始表有 267 条非占位披露文本，另 1 条 `Sheet1!K42` 是字符串 `None`，不是空单元格。清洗二值字段为 86 个 1、182 个 0，其中 181 个 0 对应非空原始披露文本。不能把 0 解释成“无披露”；内部 schema 应保留原始披露文字和独立的旧二值字段。
8. **原始媒体字段有错误。** 原始 `Sheet1!C190` 混入 URL 字符串，主 CSV 已写为 Forbes。原始表应保留用于追溯，统计应使用核对后的媒体字段。

## 3. 已有代码：每个入口的输入与输出

这些是静态阅读确认的源文件，本次没有重新执行采集、推理或训练。

| 已有入口 | 输入 | 已实现处理 | 输出 | 仍缺什么 |
| --- | --- | --- | --- | --- |
| `combine_files.ipynb` | `final_dataset-original.csv`（270 条）与 `./jsonl` | pandas 读取；追加旧表没有的 URL；转换日期 | `combined_ads_12-4-25.csv`（保存版本 280 条） | 完整去重、同 URL 的正文更新、字段验证与版本记录 |
| `process_error_file.ipynb` | 手写失败 URL 列表与 `final_dataset.csv`（112 条） | 按精确 URL 筛选待重试记录 | `remaining_files.csv`（77 条） | 自动收集失败、重试状态和持久日志 |
| `ads_download.py` | `remaining_files.csv` 中的 URL、媒体、标题、日期 | Selenium 打开网页、滚动，用 Chrome 打印 PDF | 按媒体/日期/标题命名的 PDF | 正文抽取、完整性检查、混篇检查及可追溯的结果清单 |

代码均位于 [native-ads-download](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download>)。详细静态审查见 [代码阅读说明](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/code_review.md>)。

**现有三段代码没有组成一条自动串联的完整 pipeline。** 合并输出没有自动传给重试脚本；当前恢复目录的 JSONL/PDF 相对路径还需配置。原目录中也没有建立依赖锁定、自动化测试和部署环境。

已有技术栈的直接代码证据是 **Python、Jupyter、pandas、Selenium、webdriver-manager、Chrome/ChromeDriver**。项目介绍列出的 Dash、PostgreSQL/pgvector、模型 SDK 和 Railway 是目标技术栈，本地归档不能证明这些应用组件已经实现。

## 4. CLAIMS：已有输入、输出与质量

### 4.1 处理对象

CLAIMS 在此项目中用于整理广告中的气候、能源和企业环境叙事。已有材料包含全文、段落和句子三种分析粒度。它输出内容标签，可用于观察哪些主题出现，以及在媒体或公司之间如何分布。

输入与输出可概括为：

```text
已有文章正文
  ├─ 全文输入 → 文章级标签与解释
  ├─ 段落输入 → 段落级标签
  └─ 句子输入 → 句子级多标签

人工标注句子 + 对应验证预测 → 每类及汇总指标
```

这里的箭头描述保存文件所体现的处理关系。主推理实现、完整提示词、原始 codebook 和全部清洗/标签转换代码尚未在本地恢复，所以不能据此声称已能重跑旧模型。

### 4.2 输出具体是什么

最终人工表和一组预测表使用 12 个布尔字段，其中 **10 个细分类加 2 个上层字段**：

| 层级 | 字段 |
| --- | --- |
| 绿色叙事上层 | `green_binary` |
| 绿色叙事细类 | `decreasing_emissions`、`viable_solutions`、`false_solutions`、`recycling_waste_management`、`nature_animal_references`、`policies_programs`、`generic_environmental_references` |
| 化石燃料上层 | `fossil_fuel_binary` |
| 化石燃料细类 | `primary_product`、`petrochemical_product`、`infrastructure_and_production` |

原始人员标注工作表曾使用 `green_other`、`fossil_other`，与最终表的两个 binary 字段并非同一个结构。导入时应保留标签规范版本，不能仅按“都是 12 列”拼接。

这些标签表达内容分类。全部为 False 不能解释为“不是广告”；`false_solutions` 等标签也不能直接当作独立事实核查的结论。

### 4.3 已有结果的精确粒度

| 保存文件 | 规模 | 可确认的意义 |
| --- | --- | --- |
| `model_results.json` | 268 个顶层文章键 | 一组文章分析输出；不能仅按键值认定与其他结果是同一运行 |
| `predictions_calibrated.csv` | 268 条文章记录 | 按 URL 关联后 268/268 全文与主 CSV 逐字一致；含原标签、调整后标签与说明 |
| `sentence_predictions.csv` | 8,285 句、268 个文章 ID | 该文件中的句子均能在相同 ID 的上述校准表文本中精确找到 |
| `validation_sentence_predictions.csv` | 517 句、16 个文章 ID | 与最终人工表的键和句子逐字对应 |
| `handcoded_labels.csv` | 517 句、16 个文章 ID | 对应这批验证预测的人工参考标签 |

预测文件位于 [CLAIMS 1.0 Runs/CSVS](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS>)；人工参考位于 [handcoded_labels.csv](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/handcoded_labels.csv>)。

### 4.4 能证明到什么程度

- **一条现成的可靠关联链已经成立。** `final_dataset_cleaned.csv` 经 URL 与全文一致性核对，可关联 `predictions_calibrated.csv`；该表再经文章 ID 与句子包含关系，可关联全量句子预测。这是后续导入可以复用的证据。句子文件尚无字符坐标，重复出现的同一句仍需定位处理。
- **对应验证文件可以复算。** 517 条句子全部对齐；已有复算记录给出 12 字段 micro F1 **0.8204**、macro F1 **0.7767**。这是这一批保存预测与人工表的比较结果。
- **类别质量不均衡。** 基础设施类 F1 约 **0.581**、precision 约 **0.430**；回收和自然/动物两类分别只有 **2 个阳性句子**。小类别分数不稳定。
- **不同历史分数不能混为同一实验。** 课件约 0.54 的汇总结果与上述文件复算结果的运行/口径关系尚未澄清；不能据此声称模型后来提高了多少。
- **跨文件 ID 有实际冲突。** 人工表与全量句子预测有 378 个相同数字键，但对应句子一致数为 0。它们必须按内容或明确映射关联，不能直接按 `(doc_id, sent_idx)` 合并。
- **文章结果也存在版本差异。** `model_results.json` 与校准 CSV 的原始 12 标签按数字键比较，有 171/268 条至少一个标签不同。缺少可确认的运行来源链，不能把它们作为同次运行互相补列。
- **“calibrated”文件名不证明概率校准。** 当前保存的是标签调整及说明；尚无可验证的可靠概率输出或调整后泛化收益。
- **这不是 RAG 质量指标。** 尚未发现本项目检索召回、引用支持程度、回答正确性或响应延迟的实测报告。

指标与定位证据见 [历史验证复算记录](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/prior_validation_recomputed.json>)。

## 5. 本学期输入应怎样组织

以下是建议的数据接口，属于待实现部分。初版可用少量表和文件清单承载这些信息，不需要先建立庞大的治理系统。

| 输入层 | 最少保留什么 | 目的 |
| --- | --- | --- |
| 原始来源 | 源文件/原始行、URL、文件哈希、来源批次 | 能回到收到的原始材料 |
| 统一广告记录 | 稳定 `record_id`、数据集、六个展示字段、日期原值与精度 | 看板计数和筛选使用统一口径 |
| 正文与来源 | 正文版本、段落/片段、原文或存档定位、完整性状态 | RAG 找到可核对的证据 |
| 内部辅助字段 | 披露文字、媒体链接、旧标签及其运行/规范版本 | 保留研究信息而不混淆展示字段 |
| 质量状态 | 是否可统计、是否可检索、具体缺陷原因 | 分开处理正文缺失与记录无效 |
| 社交媒体适配 | 原始帖子 ID、账号/广告主、平台、正文、时间、帖子与存档链接；以实际导出字段为准 | 将第二个数据集接入同一界面 |

`record_id` 标识一条研究记录，来源版本和正文版本另行记录。修正文中的一个错字，不应自动创建一条新广告。关键词、赞助方、正文提及公司也应分别保留。

## 6. 本学期输出应交付什么

| 输出 | 输入/计算依据 | 可审查的完成标准 | 本地现状 |
| --- | --- | --- | --- |
| 统一记录表 | 已核对身份与字段的两类广告数据 | 能从每条记录回到原始来源；重复输入不重复计数 | 多个文件分散保存，待统一 |
| Dashboard | 同一记录集合中的媒体、公司、日期等字段 | 六字段列表、筛选、图表；数量与导出明细一致；未知日期可解释 | 未找到完整应用源码 |
| RAG 搜索与回答 | 用户问题、筛选条件、可检索正文和元数据 | 返回相关记录、原文片段、回答及引用；证据不足时明确说明 | 未找到嵌入、索引与问答实现 |
| 来源跳转 | 原文/存档链接及定位 | 引用关联到正确记录；按文档要求配置链接开关 | 已有本地候选索引，需核对与接入 |
| 质量报告 | 导入、字段、正文和映射检查结果 | 列出缺失/冲突/未映射项及其影响，便于集中修复 | 本报告与已有审计可作为起点 |
| 运维交接 | 配置、批处理、依赖与运行日志 | 文档能支持重复导入、失败重试、数据更新与部署 | 原采集工具尚需整理，应用交接待建 |

数量类问题，例如“某公司在某媒体有多少条”，应依据结构化记录统计。RAG 检索返回的前几条片段不能作为全库数量。

内容类问题，例如“这些广告如何描述 CCS”，应返回广告记录、相应原文及概括。回答应将“广告提出的说法”归属给相应材料；外部事实核查需要另有证据输入。

## 7. 最少人工的实施顺序

1. **先统一数据入口。** 以 268 条主 CSV 作为候选记录与正文起点，关联原始 XLSX 的披露等字段。利用本次已完成的 URL 对照，集中核对合并版本的新增记录和正文冲突。正常匹配自动导入，只把冲突、特殊附件和疑似重复列入审核。
2. **并行取得社交媒体样本和字段说明。** 原生广告可先开发，但本学期双数据集交付仍依赖这部分输入。
3. **先做元数据看板，再补正文资格。** 视频占位可保留在列表中；正文检索先覆盖已验证文本。名称、日期与计数口径集中修复一次。
4. **建立最小 RAG。** 对可用正文保留文章和段落定位，切块、嵌入、检索并输出引用。优先用 CCS、biogas 的真实问题审查检索和答案。
5. **把已有 CLAIMS 标签作为可选导入。** 只接入已核对来源与版本的结果；无法映射的暂留为未映射记录，不阻塞核心看板与 RAG。

人工工作应集中在机器无法确定的文章身份、正文边界、实体冲突，以及一组代表性问答的审核。文件计数、字段缺失、精确 URL/文本匹配、重复导入、引用存在性等适合自动检查。

## 8. 核查覆盖与证据

本次重新读取最新项目 DOCX，复核主要表格、CLAIMS 文件的记录粒度与关联关系，检查实际文件清单和已有代码。没有修改原始数据，没有执行附件脚本或调用真实模型。

四份主数据源在审计前后的 SHA-256 相同。本次新增的机器可读结果保留了文件哈希、统计方法与问题定位：

- [本次表格质量核查](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/current_table_audit.json>)。
- [本次 CLAIMS 输入输出核查](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/current_claims_io_audit.json>)。

外层 309 个 PDF、7 个 JSONL/45 条记录已重新核对文件/记录数量；2,054 页来自既有解析清单，本次没有重新逐页解析。已有文字提取覆盖全部外层 PDF，既有内容阅读覆盖秋季 45 条记录和夏季样本；它不等于全库逐页人工审核。

审计辅助脚本属于本次分析工具，不作为前届已经交付的产品代码。聊天中提及的“研究原型、36 项测试”未在本地发现对应可运行代码包，本报告不将其计入已验证工程成果。

- [既有数据审查](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/data_audit.md>)：可追溯到代表性单元格；若与本次计数冲突，以本次直接读取结果为准。
- [PDF 清单](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/inventory.json>)、[来源候选映射](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/source_index.json>)。
- [秋季内容审查](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/fall_content_review.md>)、[夏季样本审查](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/summer_content_review.md>)。
