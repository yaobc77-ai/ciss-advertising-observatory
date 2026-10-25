# FA26 项目交付计划与资料附录

> **当前实施入口（2026-09-16）**：原生研究预览已在本机运行。查看 [实施与验收状态](docs/acceptance_status.md)、[交接说明](docs/handoff.md) 和 [README](README.md)。本页保留模块要求及编制时附录，不将历史“待建”当作当前状态；实际已实现内容和剩余验收以上述入口为准。社交、指定 GitHub、固定公网入口及人工语义验收仍有待完成。

本计划按模块实施与验收，不安排周次。附录依据最新版项目介绍逐项核对，区分已有输入、参考资料与待创建交付物。

## 一、目标与已确定的方案

依据 [FA26 项目介绍](<C:/Users/yaobc/Downloads/[FA26] DS 549_ CISS Fossil Fuel and Animal Agriculture Advertising Observatory (1).docx>)，交付一个公众可访问的广告观测站，包含：

- **原生广告视图**：公司、媒体、赞助关系、日期的筛选与统计。
- **社交媒体广告视图**：使用真实社交数据，与原生广告共享导航和检索体验。
- **RAG 搜索**：围绕 CCS、biogas 等问题，返回有原文证据的回答。
- **完整工程交接**：源码、测试、部署、数据字典、用户指南及最终演示。

| 项目 | 采用方案 |
| --- | --- |
| 人员 | 单人主导，AI 辅助实现、测试和文档 |
| 组织方式 | 按模块和依赖推进，不安排周次 |
| 应用 | Python、Plotly Dash、Plotly、Dash AG Grid |
| 数据 | pandas＋Pandera；本地 PostgreSQL＋pgvector |
| 模型 | `gpt-5.6-luna`＋Responses API；`text-embedding-3-small` |
| 部署 | 本机运行应用和数据库，通过公网入口提供服务 |
| API 预算 | **100 美元/月**，包含生成与 embedding 调用 |
| CLAIMS | 导入已核对的历史标签；后端重建列入未来工作 |

模型与接口组合已在 [OpenAI 官方支持表](https://developers.openai.com/api/docs/guides/your-data#api-endpoint-tool-and-model-support)核实；账户实际访问能力在接入模块中验证。现有资产及质量依据 [质量与输入输出报告](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/FA26_EXISTING_QUALITY_AND_IO.zh-CN.md>)。

## 二、八个实施模块

### M1．统一数据与可重复导入

**输入：**现有元数据 XLSX、268 条清洗 CSV、280/278 条合并版本，以及后续取得的社交数据。

**实施：**

- 建立稳定记录 ID，保存原始字段、来源位置和正文版本。
- 以 268 条主 CSV 为候选起点，关联原始披露文字。
- 对合并版本新增的 12 个 URL 集中审核；已有记录按字段比较，不整表覆盖。
- 将字段缺失、日期冲突、正文问题和身份重复分别记录。
- 提供独立的原生广告、社交数据导入适配器。

**输出：**统一记录库、两类数据字段映射、数据字典、导入报告和问题清单。

**完成标准：**相同输入重复导入不会新增重复记录；每条记录能够追溯来源；异常记录有明确原因。`keyword` 不替代赞助方，清洗版披露二值不替代披露原文。

### M2．正文质量与来源证据

**输入：**候选正文、PDF、JSONL、原网址与现有来源索引。

**实施：**

- 自动识别空正文、`video`、数字正文、明显乱码和重复文本。
- 对疑似截断、页脚、混篇、PDF 对应错误生成集中审核清单。
- 为接受的正文保存段落、字符位置和原始来源定位。
- 分开标记“可用于统计”和“可用于正文检索”。
- 建立原网址、公开归档网址和内部本地存档的对应关系。

**输出：**可检索正文集合、可定位证据、来源状态及待复核清单。

**完成标准：**检索片段不会跨文章；引用能回到正确正文版本。26 条 `video` 占位不会进入正文索引，正文缺失不妨碍可用元数据的展示。

### M3．原生广告 Dashboard

**输入：**统一记录、已核对的公司/媒体信息，以及可关联的历史 CLAIMS 标签。

**实施：**

- 展示项目规定的六字段：URL、publisher、title、date、sponsor、keyword。
- 实现日期、媒体和赞助公司筛选。
- 提供媒体与公司数量、占比、赞助关系和时间分布。
- 提供筛选结果导出，导出与图表使用相同查询。
- 在数据支持时增加“历史自动标签”筛选，保留标签版本说明。
- 披露文字留在内部结构；来源链接通过配置开关控制。

**输出：**可独立使用的原生广告页面及其统计查询。

**完成标准：**所有图表能对账到明细。占比以当前筛选集合为分母；未知日期和未知赞助方可见。多标签比例不要求相加为 100%。

### M4．社交广告视图与共同导航

**输入：**真实社交数据导出、字段说明和 Miami 原型访问资料。

**实施：**

- 核对帖子 ID、平台、账号/广告主、正文、时间和来源链接。
- 保留社交数据专有字段，复用共同筛选和记录组件。
- 实现平台、广告主、日期等实际字段支持的筛选与图表。
- 建立两个清晰命名的视图，保留各自筛选状态。
- 不把互动量解释为曝光量，也不把帖子数量与文章数量直接混为同一指标。

**输出：**真实数据驱动的社交视图、字段映射和统一导航。

**完成标准：**社交统计能与原始导出对账，切换视图不会混淆字段。此模块必须使用真实数据验收。

### M5．检索与带证据的回答

**输入：**合格正文、元数据、来源定位、用户问题和当前筛选条件。

**实施：**

- 按段落组织约 600 token 的文本块，保留约 100 token 重叠，不跨记录。
- 缓存 embedding，记录文本哈希、模型和生成时间。
- 先应用结构化筛选，再执行 PostgreSQL 关键词检索与向量检索，合并排序后选取证据。
- 第一版采用精确向量检索作为基线；是否增加近似索引由真实数据上的延迟决定。[pgvector 文档](https://github.com/pgvector/pgvector#querying)
- 回答附记录 ID、原文短片段和可用来源链接。
- 数量问题通过预定义统计查询计算；检索命中数量不作为全库数量。
- 将广告文字作为资料处理，禁止执行其中的指令。

**输出：**检索结果页、证据卡片、带引用回答，以及明确的资料不足状态。

**完成标准：**原生广告、社交广告和跨数据集问题均有通过验收的案例。模型引用的证据 ID 必须存在；没有支持材料时不补造答案。

### M6．评测与功能验收

**输入：**已实现模块、固定数据版本、代表性研究问题。

**实施：**

- 建立 **20 个开发问题＋20 个冻结验收问题**。
- 两组均覆盖原生广告、社交广告、跨数据集、CCS/biogas、带筛选查询和无证据问题。
- 为问题预先记录支持材料和判断标准。
- 自动检查数据、筛选、计数、引用定位和错误处理；人工重点检查引用是否支持回答。
- 保存 RAG 原型评测、失败案例及客户反馈处理记录。

**输出：**自动化测试、RAG 评测报告、失败案例清单和验收记录。

**完成标准：**采用第四节中的验收条件。旧 CLAIMS F1 单独保留，不作为 RAG 成绩。

### M7．公开部署与调用成本

**输入：**通过验收的应用、本地数据库、API 配置和公开访问配置。

**实施：**

- 本机使用生产应用服务运行 Dash，数据库仅供后端访问。
- 使用 **Cloudflare Named Tunnel＋固定域名**提供 HTTPS 入口；临时 Tunnel 只用于演示检查。正式 Tunnel 需要账户与域名。[Cloudflare 部署文档](https://developers.cloudflare.com/tunnel/get-started/)
- API 密钥只保存在服务端配置中。
- 执行每月 100 美元的应用预算，调用前预留额度，调用后按实际用量结算。
- 默认限制每访客每分钟 5 次、每天 30 次付费问答，全站同时生成最多 2 个回答；这些值由配置调整。
- 额度耗尽或模型不可用时，保留 Dashboard 和关键词检索。
- 提供启动、停止、健康检查、备份与恢复操作。

**输出：**公众访问地址、部署配置、用量记录和运行说明。

**完成标准：**从本机以外的网络完成浏览、筛选、问答和来源访问。预算、限流、服务重启和数据库恢复都有测试证据。服务可用时间随本机开机与网络状态变化。

### M8．源码、文档与最终演示

**输入：**全部模块及其验收结果。

**实施：**

- 将源码、测试、依赖锁定和部署配置提交指定 GitHub 仓库。
- 随实现维护架构图、字段映射、数据更新流程和 RAG 说明。
- 编写面向非技术用户的筛选、搜索与来源核对指南。
- 准备演示：比较媒体/公司数量 → 查看赞助关系 → 日期筛选 → 查询 CCS/biogas → 打开支持证据。
- 明确未来工作：CLAIMS 后端、动物农业、更多社交平台及进一步主题分析。

**输出：**可定位的交付版本、技术文档、用户指南、演示材料和交接索引。

**完成标准：**另一位实施者能按照文档启动系统、导入数据、运行测试并复现演示。

## 三、最小工程结构与接口

采用**一个 Python 应用、一套数据库、一组批处理命令**组织，便于单人维护。

- `records`：记录身份、元数据、正文版本、来源与质量状态。
- `chunks`：正文片段、定位、embedding 与模型版本。
- `annotations`：历史 CLAIMS 标签、版本及关联依据。

导入日志、用量和配置作为运行辅助数据保存。

| 接口 | 输入 | 输出 |
| --- | --- | --- |
| 导入 | 数据集类型、来源文件 | 记录版本、导入统计、问题清单 |
| 浏览与统计 | 数据集、媒体/平台、公司、日期等筛选 | 分页明细、分组数量与比例 |
| 检索 | 问题、相同筛选条件 | 排序后的记录与证据片段 |
| 回答 | 问题、筛选、支持证据 | 回答、引用、完成/资料不足/服务不可用状态 |

看板、检索和引用使用同一数据版本。正文变化只重新处理受影响记录，旧版本保留用于核对历史引用。

默认公开界面使用英文，技术交接提供中文说明；原文保持原语言。公众浏览无需注册，数据导入与维护由本机命令执行。

## 四、验收条件

以下是本计划提出的工程目标，不是附件已有指标，也不是已达到的成绩。

| 类别 | 必须检查的场景 |
| --- | --- |
| 数据 | 重复导入、坏行隔离、日期冲突、视频占位、正文版本变化、旧标签错配 |
| Dashboard | 六字段、组合筛选、零结果、未知值、数量/比例/导出一致、双视图切换 |
| 来源 | 原链接正常、有公开归档、无可用外链、关闭链接开关、引用定位错误 |
| RAG | 筛选条件不被越过、证据归属正确、无证据不编造、广告中的指令不被执行 |
| 公开服务 | API 超时、限流、预算耗尽、并发预算预留、密钥不出现在浏览器、重启恢复 |

RAG 冻结验收集的目标：

- 可回答问题的 **Hit@5 ≥ 90%**：前五条记录中找到预先确定的必要支持记录。
- **引用定位成功率 100%**。
- 人工核对的**引用支持率 ≥ 95%**。
- 无证据测试题全部明确说明资料不足。
- 分别报告两类数据的结果、分母、延迟与调用成本，不只给一个汇总分数。

若未达到目标，先定位问题来自正文、检索还是回答生成，再修改对应模块并重新验收。

## 五、实施顺序与外部依赖

```text
M1 统一数据
 ├─ M2 正文与来源 ── M5 RAG
 ├─ M3 原生广告页面
 └─ M4 社交广告页面

M3＋M4＋M5 → M6 综合验收 → M7 公开部署 → M8 最终交接
```

文档与测试随各模块维护，最后统一交接。开始时登记并跟进四项外部输入：

1. 真实社交样本、字段说明和原型访问资料。
2. 指定 GitHub 仓库及提交权限；旧仓库链接不自动等于本学期指定仓库。
3. OpenAI API 项目、密钥及模型访问能力。
4. 固定公开域名与 Cloudflare Tunnel 配置。

这些输入缺失时可以继续实施不依赖它们的模块，但对应交付物保持未完成状态。**最终完成条件是：真实双数据集、Dashboard、RAG、公开部署和交接材料全部通过验收。**

<!-- FA26_RESOURCE_APPENDIX -->

## 六、文件与资料用途附录

核对日期：2026-09-16。基准是最新版 [FA26 介绍文档](<C:/Users/yaobc/Downloads/[FA26] DS 549_ CISS Fossil Fuel and Animal Agriculture Advertising Observatory (1).docx>)。本附录对应模块 M1–M8；用途是本计划中的使用方式，不把参考材料转换为额外交付要求。

### 阅读口径

- 最新附件实际引用 **16 个网页/资料链接＋1 个邮箱链接**，没有嵌入文件；附录 A 完整覆盖这 16 项。
- `P` 是 OOXML 中包含表格和空段的段落序号，不是 Word 页码。
- 在线访问情况沿用 **2026-09-15** 的阅读记录，本轮没有重新登录、联网检查或请求权限；这些状态可能已经变化。本轮重新核对了文档引用和本地路径。
- 附录 B 是从文档所链文件夹进一步查得的文件；附录 D 是计划将来创建的交付文件；附录 E 是本地审计补充。它们都不计入 A 的 16 项。
- 文档正文唯一写出扩展名的具体文件名是 `Poster Board CS549 DEV.pptx`。其他数据文件名来自目录/本地审计，不能冒称为附件逐一列出的文件。

### 附录 A．最新文档直接引用的全部资料

#### 数据输入

| 编号 / 原文位置 | 文件或资料入口 | 用处与对应模块 | 已有内容 / 访问记录 |
| --- | --- | --- | --- |
| R01 / P65 | [Fossil fuel advertising data and documentation](https://drive.google.com/drive/folders/1QYuGCrPctiwY03w46O_urHtrnKUgXij9?usp=sharing)；Google Drive 文件夹 | M1、M4、M5、M6：取得社交样本、原帖/归档关联、已有 CLAIMS 标签和字段文档；支持社交视图及跨数据集检索。 | 2026-09-15 未取得目录内容；不能确认实际文件名、37k 数量或字段。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_links.md>) |
| R02 / P66 | [Native advertising data](https://drive.google.com/drive/folders/1zm3jVtZPedDG0bN_s7OAWxwjCwOs9cQl?usp=drive_link)；Google Drive 文件夹 | M1、M2、M3、M5、M6：取得原生广告元数据、正文和手标样本，核对 PDF/截图来源；用于入库、统计和证据检索。 | 2026-09-15 读到四个直接子项，见附录 B；目录当层未列 PDF 子目录。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_links.md>) |
| R07 / P76 | [Example Junkipedia post](https://www.junkipedia.org/posts/920047974)；单条来源记录 | M2、M4、M5：理解账号、平台、正文、图像、互动与来源跳转的关系；作为社交记录详情和引用样例。 | 2026-09-15 读到正文与图片；单条示例不证明整个样本的付费投放身份。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_prototype_sources.md>) |

#### 产品参考

| 编号 / 原文位置 | 文件或资料入口 | 用处与对应模块 | 已有内容 / 访问记录 |
| --- | --- | --- | --- |
| R03 / P70 | [How Do They Lobby? — Brown University project article and video](https://ibes.brown.edu/news/2024-03-20/cdl-lobbying-website)；项目介绍网页 | M3、M4、M8：参考从筛选、图表到明细与证据的公共研究工具流程；用于线框、用户流程和计数口径说明。 | 已有网页/实际门户阅读记录；链接中的视频没有完成观看。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_reference_sites.md>) |
| R04 / P73 | [The Big Green Machine](https://www.the-big-green-machine.com/)；研究看板网站 | M3、M4：参考时间趋势、筛选联动和记录状态展示；不因此增加地图或 Tableau 迁移任务。 | 已有首页及关键子页阅读记录，未全面验收动态交互。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_reference_sites.md>) |
| R05 / P74 | [Big Ag Network](https://acre.wisc.edu/big-ag-network)；研究工具网站 | M1、M3、M8：参考公司名称消歧、关系类型与来源记录；为未来动物农业扩展保留接口。 | 已有界面说明与方法阅读记录；不是本期动物农业数据输入。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_reference_sites.md>) |
| R06 / P75 | [University Of Miami Prototype](https://seahorse-app-kjzfk.ondigitalocean.app/)；受限访问原型 | M4：核对社交数据适用的筛选、指标和记录详情；新应用从头建设，原型用于需求参考。 | 项目文档注明受限；2026-09-15 到 Auth0 登录页，未读内部看板。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_prototype_sources.md>) |

#### 历史成果

| 编号 / 原文位置 | 文件或资料入口 | 用处与对应模块 | 已有内容 / 访问记录 |
| --- | --- | --- | --- |
| R08 / P78 | [BU-Spark/ml-ciss-native-ads](https://github.com/BU-Spark/ml-ciss-native-ads)；GitHub 仓库 | M1、M6、M8：追溯前届代码、依赖、处理流程与运行版本；不能自动认定为本学期指定交付仓库。 | 2026-09-15 请求返回 404，未取得该仓库源码；原因未确认。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_prototype_sources.md>) |
| R09 / P79 | [DS549: CISS Native Ads Deliverable 5 (Final)](https://docs.google.com/presentation/d/1GZ_NKJqyrKQ4ln4CRO7Tor9ZC2W8RYGIECsRlucPKfQ/edit?usp=share_link)；客户最终汇报 | M8：了解前届向客户交付的内容和限制，为本期客户演示与交接查漏；不能从标题推定已验收功能。 | 2026-09-15 未取得正文；没有可靠内容副本。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_links.md>) |
| R10 / P80 | [DS549: CISS Native Ads Final Presentation](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit?usp=share_link)；课程最终汇报 | M1、M3、M6、M8：理解 CARDS/CLAIMS 路线、历史分类流程和指标版本问题；用于历史方法说明及未来工作边界。 | 已有 26 页文本/返回讲稿，未逐页渲染图表；文本快照不是完整 PPTX。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_class_slides.md>) |
| R11 / P81 | [Poster Board CS549 DEV.pptx](https://docs.google.com/presentation/d/12K_Iqgf22KvxFHZ_eF0z2aH9NzmQaBoA/edit?usp=share_link&ouid=101170222743202658595&rtpof=true&sd=true)；Demo Day 海报/PPTX 链接 | M8：参考面向展示活动的项目摘要组织；取得内容后再核对可复用图示与文字。 | 2026-09-15 页面未找到，未取得海报；不能代替本期最终演示。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_links.md>) |

#### 研究背景

| 编号 / 原文位置 | 文件或资料入口 | 用处与对应模块 | 已有内容 / 访问记录 |
| --- | --- | --- | --- |
| R12 / P184 | [Native Ads Are Shaping Climate Opinions. BU Researchers Say There’s a Way to Resist](https://www.bu.edu/articles/2025/how-to-resist-shaping-climate-opinions/?utm_campaign=bu_today&utm_source=email_20250520&utm_medium=intrograph&utm_content=research_humanities)；BU 研究介绍 | M8：解释项目动机及研究用户为何需要广告来源与赞助信息；用于背景介绍和用户指南。 | 有原站 HTML 快照；它与下项 Nature 论文介绍同一研究，不是独立实验。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_web_sources/bu.html>) |
| R13 / P185 | [The “Future of Energy”? Building resilience to ExxonMobil’s disinformation through disclosures and inoculation](https://www.nature.com/articles/s44168-025-00209-6)；研究论文 | M5、M6、M8：帮助区分广告识别、披露与信念变化；约束项目论述，不把看板效果当作已验证实验效果。 | 有 Nature HTML 和正文提取；当前没有保存 Nature PDF。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_web_sources/nature.txt>) |
| R14 / P186 | [Discourses of climate delay](https://www.researchgate.net/publication/342596080_Discourses_of_climate_delay)；研究论文入口 | M5、M6：提供叙事与论证方式的研究词汇，辅助设计检索问题；其中 12 类不等于 CLAIMS 的 12 字段。 | 已有全文/出版社核读笔记，当前没有原文文件副本。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_background_readings.md>) |
| R15 / P187 | [Agenda-Cutting Versus Agenda-Building: Does Sponsored Content Influence Corporate News Coverage in U.S. Media?](https://ijoc.org/index.php/ijoc/article/view/17824/3614)；研究论文入口 | M3、M8：解释赞助商—媒体—日期关系的研究意义；广告库本身不能证明赞助影响新闻报道的因果关系。 | 已有同站论文下载阅读笔记，当前没有原文文件副本。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_background_readings.md>) |
| R16 / P188 | [Three Shades of Green(washing) Content Analysis of Social Media Discourse by European OIl, Car, and Airline Companies](https://www.greenpeace.org/static/planet4-netherlands-stateless/2022/09/0ded952d-threeshadesofgreenwashing.pdf)；内容分析报告 PDF | M1、M4、M6：参考社交采样、文本/图像、重叠标签和统计分母；区分企业自然帖子与付费广告。 | 本地是 Greenpeace España 官方压缩版，未证明与原链接字节相同。 [本地证据](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_web_sources/greenpeace_compressed.pdf>) |

### 附录 B．原生广告文件夹已查得的四个文件

来源是 R02 文件夹在 2026-09-15 的直接子项清单；没有把整个文件夹递归内容视为已列全。云端名称与本地文件对应不代表已经证明内容同版。

| 云端目录文件名 / 链接 | 本地对应入口 | 用处 |
| --- | --- | --- |
| [native_ad_dataset.xlsx](https://docs.google.com/spreadsheets/d/1Roi9kkNUSO3DzO5cPi2kH49Cx1ft9Ymd/edit?usp=drivesdk&ouid=104077804716156129302&rtpof=true&sd=true) | [本地文件](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/native_ad_dataset.xlsx>) | M1、M2、M3：原始元数据、披露文字、媒体链接与字段追溯。 |
| [final_dataset_CLEANED](https://docs.google.com/spreadsheets/d/1jnuf5yZVun_PYnWgUTQRxIG-i47q2BRM60iy9ASMRFg/edit?usp=drivesdk) | [本地文件](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/final_dataset_CLEANED.xlsx>) | M1、M2：历史清理字段及正文，供版本比较；已知 H220 数值错误，不作为正文优先来源。 |
| [handcoded_labels.csv](https://drive.google.com/file/d/1tvuG-g-JDjRdDCcQxExI6GASztd1-uop/view?usp=drivesdk) | [本地文件](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/handcoded_labels.csv>) | M3、M6：理解旧标签及验证对应的历史预测；不作为新 RAG 的问答金标准。 |
| [combined_ads_12-4-25.csv](https://drive.google.com/file/d/1thuhsiRRTiVX4Yd-D89NydvfaTqKNUJo/view?usp=drivesdk) | [本地文件](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/combined_ads_12-4-25.csv>) | M1、M2：核对合并抓取和补充 URL/正文，保留版本差异。 |

云端 `final_dataset_CLEANED` 是原生 Google Sheet，本地是 `.xlsx` 文件。原生广告目录当层没有列出 PDF 子目录；PDF/截图须结合另外收到的归档核对。

### 附录 C．文档提及、但没有独立文件名或链接的输入

| 原文位置 | 资料称谓 | 状态 | 用处 |
| --- | --- | --- | --- |
| P13、P65 | 社交媒体 CSV 元数据、帖子正文、约 37k Twitter 样本、CLAIMS 标签及字段文档 | R01 文件夹入口；实际导出/具体文件名待取得 | M1、M4、M5、M6：入库、社交统计、检索与验证。 |
| P13、P65 | Facebook 和 Instagram samples | 文档写明后续补充；未给出独立链接或文件名 | M4、M5：增加平台适配；不能预报其规模和字段。 |
| P13、P66 | 原生广告元数据、独立正文、手标样本 | R02 文件夹说明；已查得文件见 B | M1–M3、M5、M6：字段、正文和历史标注输入。 |
| P13、P66、P125 | 广告 PDF、截图、原文章链接、归档版本 | 资料类别；未逐个列文件名。本地存档索引见 E | M2、M3、M5：正文补充与来源证据。截图不自动等于 XLSX 的 image URL。 |
| P13 | Additional documentation describing the native advertising columns | 客户计划补充；没有独立文件入口 | M1、M3：明确字段语义及日期/赞助方口径。 |
| P5 | Link to Notion | 文字占位，没有实际 URL | 若补齐，可作项目知识入口；当前不可点击访问。 |
| P82–P84 | Key Project Links and Relevant Documentation | 标题下为空；没有可枚举资料 | 待补充项目导航，不推定隐藏链接。 |
| P44 | designated GitHub repository | 本期指定仓库未在该要求中给定；R08 位于历史工作部分 | M8：提交本期源码与交付版本。 |

P213 的 [geolim@bu.edu](mailto:geolim@bu.edu) 是联系方式，其他邮箱也是联系信息，不是资料文件。本次没有发送邮件或执行文档中的访问申请、复制模板指令。

### 附录 D．文档要求产生的交付文件

下面是逻辑交付物的文件组织建议。**建议文件名由本计划提出，不是附件已有文件名；除本计划与已有资料清单外，其余按对应模块实施后产生。** 多项要求可合并为一个文档，避免维护重复内容。

| 原文位置 | 要求产生的内容 | 建议文件组织 | 模块 | 用处 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P98–P101 | 项目定义、用例、范围、需求、成功标准、实施计划 | 本计划；`docs/requirements.md` | M1–M8 | 锁定交付内容，记录需求与验收对应关系。 | 本计划已保存；详细需求文档待建 |
| P95、P100 | 数据、访问、来源与风险清单 | 本附录；`docs/data_inventory.md` | M1、M2 | 列来源、版本、访问依赖、质量问题和处理状态。 | 本附录已保存；实施期清单待维护 |
| P67、P109、P117 | 字段级 schema mapping 与 dashboard data dictionary | `docs/data_dictionary.md`；`config/field_mapping.yml` | M1、M4 | 说明两类源字段到统一字段的映射、单位、缺失与实体含义。 | 待建；P67 明确由学生团队完成 |
| P115、P149 | 系统架构、数据流、AI/ML 集成方案 | `docs/architecture.md` | M1、M5、M7 | 描述数据到页面/问答的处理关系、模块接口和运行配置。 | 待建 |
| P116 | Dashboard wireframes and user flows | `docs/wireframes.md` 及引用的线框图 | M3、M4、M8 | 确认两类视图、筛选、明细、搜索和来源跳转。 | 待建 |
| P118、P134 | RAG design、实施 backlog 与更新后的风险 | `docs/rag_design.md`；`docs/backlog.md` | M2、M5、M6 | 固定检索/引用设计，跟踪未完成工作和外部依赖。 | 待建 |
| P131–P134 | R&D 发现、技术建议、已验证处理与检索方案 | `docs/technical_findings.md` | M1、M2、M5、M6 | 记录实际比较、选择依据、失败及证据，避免只写架构设想。 | 待建 |
| P133、P144 | 代表性 RAG 问题集与评价计划 | `eval/questions.jsonl`；`docs/evaluation_protocol.md` | M6 | 保存问题、支持记录、判断标准、开发/验收分组和指标口径。 | 待建；计划为20开发＋20验收题 |
| P148、P166 | RAG 评价、失败案例、功能与 RAG 测试结果 | `reports/evaluation.md`；`reports/failure_cases.csv`；测试结果 | M6 | 交代实际质量、分母、延迟、成本和未解决失败。 | 待建；旧 CLAIMS 指标不能替代 |
| P145、P150、P163 | 客户审阅的 RAG POC/产品及优先反馈 | `docs/client_review.md` 与对应演示版本 | M5、M6、M8 | 保存审阅版本、反馈和处理决定；不能先行写为已接受。 | 待建 |
| P44–P46、P165、P180 | 最终源码、可复用组件、测试与部署配置 | `src/`、`tests/`、依赖锁定、`.env.example` 和部署配置 | M1–M8 | 让后续接手者从指定 GitHub 交付版本运行和维护系统。 | 待建；不是旧仓库链接或历史静态输出 |
| P46、P173、P175、P181 | setup、部署、配置、数据库/嵌入工作流与更新说明 | `README.md`；`docs/operations.md` | M7、M8 | 说明安装、启动、数据更新、预算、公开入口、备份和故障恢复。 | 待建；示例配置不包含真实密钥 |
| P49、P176、P181 | User guide | `docs/user_guide.md` | M3–M5、M8 | 指导非技术用户筛选、比较、搜索和核对证据。 | 待建 |
| P50、P176、P182 | 未来工作边界与建议 | `docs/future_work.md` | M8 | 说明 CLAIMS 后端、动物农业、更多平台和可选主题分析。 | 待建 |
| P51、P177、P182 | Final presentation、demonstration、handoff materials | `deliverables/final_presentation.pptx`；演示脚本；交接索引 | M8 | 覆盖双数据集、统计、RAG、引用与运行限制，汇总所有交付入口。 | 待建；旧海报/汇报不算本期产物 |

### 附录 E．与计划直接相关的本地审计补充

这些入口不由最新版 DOCX 逐一命名；来自用户提供的本地资料与此前审计。以下按用途给出主要入口，单个广告 PDF 在已有访问目录中展开。

| 资料 | 本地入口 | 用处 |
| --- | --- | --- |
| 主 CSV 正文候选 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>) | M1、M2、M3、M5：当前268记录起点；26条video占位不入正文索引。 |
| CLAIMS 文章标签与调整说明 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/predictions_calibrated.csv>) | M3：按URL＋全文核对后导入历史标签，保留原标签和调整后标签。 |
| CLAIMS 全量句子预测 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/sentence_predictions.csv>) | M3、M6：8,285句历史输出；可与上述全文关联，不直接连接人工验证ID。 |
| CLAIMS 对应验证预测 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/validation_sentence_predictions.csv>) | M6：与B中的517句人工表对应，复核历史分类成绩。 |
| CLAIMS 另一组文章结果 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/CLAIMS 1.0 Runs/CSVS/model_results.json>) | M6：历史运行对照；缺来源链，不能按数字ID直接当同一次结果。 |
| 人员标注工作表 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/label_batch_1_sentences.xlsx>) | M6：追溯标注底稿、空白与标签结构变化；不能将空白自行当阴性。 |
| 全部外层PDF的本地与原文目录 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/PDF_SOURCE_INDEX.zh-CN.md>) | M2：逐篇访问309个外层PDF及来源候选；标题匹配不是正文一致性验证。 |
| 秋季JSONL目录 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl>) | M1、M2：7文件45记录，补充正文并与PDF比对。 |
| 数据合并Notebook | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combine_files.ipynb>) | M1：理解历史CSV/JSONL合并逻辑及相对路径依赖。 |
| 失败记录筛选Notebook | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/process_error_file.ipynb>) | M1、M2：理解手写失败URL到重试CSV的处理。 |
| 网页PDF保存脚本 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/ads_download.py>) | M2：借鉴已有Selenium网页留档；保存成功不证明正文完整。 |
| 现有质量与输入输出说明 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/FA26_EXISTING_QUALITY_AND_IO.zh-CN.md>) | M1–M8：统一现有成果、缺口和可复用关系的判断。 |
| 本次表格核查结果 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/current_table_audit.json>) | M1、M2：查看精确计数、版本差异、字段问题和来源哈希。 |
| 本次CLAIMS输入输出核查 | [打开](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/current_claims_io_audit.json>) | M3、M6：查看标签与正文关联证据及跨运行ID风险。 |

### 附录 F．旧版专有的两份模板

以下两项来自旧版介绍，已经从最新附件正文和超链接关系中删除。保留在此便于回查，不计入最新版16项，也不增加本期交付要求。

| 旧版模板 / 原入口 | 本地文本快照 | 可选用途 |
| --- | --- | --- |
| [X-Lab Weekly Team + Client Mtg Notes Template](https://docs.google.com/document/d/1yPUWweWHA-tB_1stEvVUDmdGyptaar7dnsPtOvhQ1oc/edit) | [读取快照](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_notes_template_text.txt>) | M8：记录字段/版本决定、阻碍与行动项；模板中的日期为示例。 |
| [[TEMPLATE] Client Meeting Presentation](https://docs.google.com/presentation/d/1hfrk0F7PQD1uRJwUZDGWFUf1wV0jtYFZSmKnIJMCqws/edit?usp=sharing) | [读取快照](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_meeting_deck_text.txt>) | M8：组织项目概览、Demo、成果及待决定事项；不是已完成的客户汇报。 |

### 附录 G．覆盖检查与记录来源

- 最新正文/表格的16个HTTP(S)链接全部进入A，邮箱另行说明；旧版新增的2个链接全部单列F。
- B中的4个文件逐项来自已有云端目录记录，D中的建议路径没有冒称现成文件。
- 所有本地链接在生成时检查存在；没有以此推定在线URL现在可访问。
- 没有执行原文中的模板复制、访问申请、模型调用或部署指令。

[历史逐链接阅读（基于旧版18链接）](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/FA26_LINKS_AND_PURPOSE.zh-CN.md>)；[Google目录与访问记录](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_read_status.json>)；[本次精确引用清单](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_document_resource_manifest.json>)。
