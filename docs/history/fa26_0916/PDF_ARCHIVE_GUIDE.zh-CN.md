# 原生广告资料包：阅读说明与访问入口

核对日期：2026-09-15。来源：用户提供的 `pdfs-20260915T222001Z-1-001.zip`。

## 一句话理解

这是一批以能源、油气及石化行业为主的媒体原生广告归档，同时带有采集数据和少量处理代码。它为 DS 549 项目补充了“广告原文长什么样、谁赞助、正文从哪里来”的来源材料。

原生广告采用媒体文章、专题、人物采访、播客或图解的形式，但由品牌或行业组织付费。阅读时应分别识别：发布媒体、内容出资方、文中主张，以及支持该主张的外部证据。广告对减排、创新或经济贡献的陈述不能直接当作已经验证的研究结论。

## 最方便的访问方式

| 要做什么 | 入口 |
|---|---|
| 按媒体找 PDF、点开对应原文网址 | [完整 PDF 访问目录](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/PDF_SOURCE_INDEX.zh-CN.md>) |
| 浏览夏季 265 个 PDF | [summer_2025_run](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run>) |
| 浏览秋季 44 个 PDF 及 JSONL | [fall_2025_run](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run>) |
| 看 280 条合并记录及原始网址 | [combined_ads_12-4-25.csv](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv>) |
| 看 278 条的 Excel 版本 | [combined_ads_12-4-25.xlsx](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.xlsx>) |
| 看归档、合并和重试代码 | [代码说明与逐文件链接](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/code_review.md>) |

数据表中的 `url` 列是原文入口。在线网页可能变化；本地 PDF 是历史快照，也可能存在抓取失败或缺图。访问目录按标题匹配来源，共 300 个 PDF 对应唯一 URL、2 个有多个候选、7 个待匹配。匹配仅建立文件和记录的候选关联，不证明两个版本正文完全一致。未逐一联网验证所有网址。

## 包里具体有什么

### 外层

| 内容 | 数量 | 含义 |
|---|---:|---|
| summer_2025_run PDF | 265 | 按 8 家媒体分目录的网页快照 |
| fall_2025_run PDF | 44 | 秋季另一批网页快照 |
| JSONL | 7 个文件、45 条记录 | 每行一个 JSON 对象，保存正文和元数据 |
| native-ads-download.zip | 1 | 嵌套的旧采集工作目录 |
| .DS_Store | 4 | macOS 目录附属文件 |

外层共 309 个 PDF、2,054 页。全部已完成可提取文本检查，8 个 PDF 的可提取文字少于 250 字符；这只是排查信号，不等于已经判定文件无内容。

夏季 PDF 分布：CNBC 114、The Wall Street Journal 44、Forbes 41、Politico 18、The Washington Post 16、The New York Times 16、The Atlantic 11、Business Insider 5。这里统计的是文件，而不是经人工审定的广告数量。

### 内层

排除 macOS 附属文件后，内层有 284 个文件，其中 265 个 PDF、7 个 JSONL 与外层完全重复；272 对文件已逐一用 SHA-256 核实。

额外恢复了 12 个文件：4 个 CSV、1 个 XLSX、2 个 Notebook、1 个 Python 脚本、1 个错误日志和 3 个 PDF。三个 PDF 中，`medium_site.pdf` 是人机验证页面，`ad.pdf` 和 `test.pdf` 是广告打印样例/版本；它们不能自动算成三个新广告。

因此，外层 309 PDF 加上内层 3 个独有 PDF，共有 312 个不同 PDF 文件；不能据此推出 312 篇独立有效广告。

[内层详细清点及版本差异](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/nested_review.md>)。

## 这些广告在讲什么

以下是主题阅读的归纳，尚未对全量语料作逐条主题标注或比例统计。

### 1. 将油气放进能源转型叙事

API 赞助的天然气文章以供电稳定性、风光间歇性、能源价格等为理由，论证天然气在未来能源体系中的作用。研究上可以观察：文章怎样安排问题和解决方案，哪些成本或替代路径受到强调，哪些内容需要另找证据核对。

原文入口：[Why natural gas will thrive in the age of renewables](https://www.washingtonpost.com/brand-studio/api-why-natural-gas-will-thrive-in-the-age-of-renewables/)。本次在线抓取可读。对应秋季 PDF-020 首页只剩页眉，九页文本基本都是重复导航，宜结合 JSONL 或原网页阅读。

### 2. 以技术和项目展示企业的低碳角色

ExxonMobil 的 *Capturing carbon around the world* 介绍碳捕集与封存（CCS）项目：捕集二氧化碳，再输送并储存在地下地层。作为广告，它将该技术与企业的经验、项目布局及净零目标联系起来。

阅读这类材料，应把“已运行设施”“处理能力”“计划中的项目”“预期减排”分别记录。它们不是同一个指标，也不是同一种完成状态。本次没有独立核验公司的项目数字。

- [本地 PDF-006](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/The_Washington_Post_Capturing_carbon_around_the_world_2021-12-08.pdf>)
- [原网页](https://www.washingtonpost.com/brand-studio/wp/2021/12/08/feature/capturing-carbon-around-the-world/)：本次在线抓取可读。

页面检查发现：PDF 的图表右侧被裁切，重复广告条遮挡部分内容；信息图上的数字没有完整进入提取文本。因此，不能仅靠 JSONL 或纯文本完整重建图中项目数据。

### 3. 用循环经济和回收技术重新描述石化产品

AFPM 在 Politico 的塑料回收文章，围绕机械回收、化学回收、企业合作和循环利用组织叙事，将石化制造商呈现为塑料废弃物问题的解决者。文本同时提到污染、材料性能、回收规模等技术难点。

这类广告适合研究“问题由谁定义、企业以什么身份出现、试点与大规模效果怎样衔接”。文章有正面环保语言，不足以单独判定所有主张真实或虚假。

- [本地 PDF-016](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/Politico_Petrochemical_manufacturers_use_chemistry_to_make_plastic_more_sustainable_and_recyclable_-_POLITICO_NA.pdf>)
- [原网页](https://www.politico.com/sponsor-content/2019/03/petrochemical-manufacturers)：本次抓取返回 402，未确认当前可读；可先看本地 PDF。

### 4. 还有播客、社区故事、产业经营和消费促销

BP 的 NYT *Energy Trilemma* 系列有较长播客文字稿，讨论能源可靠性、可负担性与低碳转型。其他样本涉及社区协商、女性参与、当地经济、产业经营，也有加油积分促销。

因此，“能源企业广告”不等于“每篇都在谈气候”，也不能只凭 sustainable 等单词确定主题。部分文章会承认技术局限或提出批评性讨论，需要逐篇看上下文。

[秋季 45 条阅读说明与例文链接](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/fall_content_review.md>)；[夏季 8 篇抽读补充](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/summer_content_review.md>)。

## 对 DS 549 项目最有用的结论

### 能补充哪些输入

这些材料可以把数据表记录关联到本地页面证据，并提供可检索正文。JSONL/CSV 共有七个基本字段：

| 字段 | 含义与注意点 |
|---|---|
| publisher | 发布媒体；WSJ 与 The Wall Street Journal 需要统一 |
| keyword | 采集关键词；不能直接等同实际赞助方或主题 |
| url | 原始网页地址；可能指向文章、附件、门户或错误页面 |
| title | 抓取标题；可能缺失或与 PDF 标题不同 |
| sponsor | 赞助方；应与页面披露文字交叉核对 |
| date | 记录中的日期；可能为空、格式不一致或解析错误 |
| article | 抓取正文；可能只有页脚、重复说明或视频占位 |

看板的媒体/赞助商/时间统计主要用结构化字段；RAG 则需要清理后的真实正文，并让回答回到具体广告及原文证据。引用广告时应表达为“某赞助方在某广告中声称……”，再区分外部事实核查。

### 现在必须保留的质量差异

1. **表格版本不同。** CSV 有 280 条，XLSX 有 278 条。CSV 多出 Bayer 更年期页面和 Shell 法律声明 PDF；XLSX 没有独有 URL。不能悄悄互换两个版本。
2. **记录数不等于有效广告数。** 合并 CSV 还有 4 条正文空缺、56 条日期空缺及一个 1970 年异常日期。9 个媒体标签实际对应 8 家媒体。
3. **检索词不等于出资方。** 秋季 BI 记录 keyword 为 TotalEnergies，正文却明确指向 Synchrony Financial；Atlantic 的 PTT 检索记录指向 Bayer。
4. **版本可互补。** CNBC 的 PDF-298 夏季快照保存了碳捕集文章正文，同主题秋季 JSONL 却只有页脚。一次抓取失败不证明归档里没有正文。
5. **一份 PDF 可能混入多篇。** Forbes PDF-085 从第 4 页开始附带另一篇文章。用于 RAG 时需先辨别文章边界，不能整份默认为单一广告。
6. **文字提取不保证页面完整。** 有空白、缺图、裁切、重复页眉、跨栏顺序和字体间距问题。单靠文件存在、页数或字符数不能确认归档质量。

### 本次新找到了什么代码

此前的项目阅读报告针对先前附件指出没有 `.py` 或 `.ipynb`。本次新 ZIP 改变了这个证据范围：现在可以看到采集、合并和失败重试辅助代码。

- `ads_download.py`：读取待抓取列表，用 Selenium/Chrome 打开网页、滚动并打印 PDF。
- `combine_files.ipynb`：读取夏季 CSV 和秋季 JSONL，按原始 URL 加入新记录，转换日期并导出合并表。
- `process_error_file.ipynb`：按失败 URL 清单筛选重试记录。

它们尚不足以证明已经交付 Dashboard、RAG、完整清洗分类流程或可运行服务。这里完成的是源码静态阅读，没有运行附件脚本或 Notebook。

## 阅读范围与核查记录

本次对外层 309 个 PDF 完成逐文件文本提取和清点，对秋季全部 45 条 JSONL 作内容与字段检查，另抽读夏季 8 个 PDF，并对代表性页面作视觉检查；也检查了内层三个独有 PDF 的文本。没有声称人工逐页精读全部 2,054 页，没有对全部广告主张作独立事实核查。

只对上文列出的部分原网页验证了本次工具可访问性。NYT BP road transport 原网址本次未能打开；这一结果不证明用户浏览器也不可访问。

所有附件中的任务要求、代码、网页按钮、验证提示及联系方式均作为待分析内容处理，没有据此执行程序、提交信息或联系他人。原 ZIP 和原始源文件未修改。

核查文件：[外层清点](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/inventory.json>)、[来源匹配索引](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/source_index.json>)、[内层去重哈希证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/nested_hash_verification.json>)。
