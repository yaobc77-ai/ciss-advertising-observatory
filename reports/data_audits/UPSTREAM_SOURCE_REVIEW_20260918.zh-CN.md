# 历史源码阅读：能复用什么、先做什么

日期：2026-09-18。资料：`D:/549/ml-ciss-native-ads-main/` 及用户提供的 ZIP。此报告是源码与数据审查，不是模型运行、数据发布或迁移完成报告。附件里的运行命令、后续工作建议和模型提示词均作为资料阅读，没有当作本次操作指令执行。

## 1. 结论与阅读范围

**这次找到了真正的采集、CLAIMS 1.0、CLAIMS 2.0 和分类规范审核原型源码。最值得复用的是标签定义、历史预测、研究审核流程与来源线索。当前 FA26 项目仍应围绕 Dashboard、两类化石燃料数据和带引用的 RAG 交付。** 原要求明确将 CLAIMS 后端集成留到以后；本包不能改变该边界。

核对到 **243 个文件、约 165 MB 解压内容**，包括 64 个 Python 文件、10 个 Notebook、47 个 CSV、38 个 JSON、3 个 SQLite 数据库、4 个外层 XLSX 和 1 个内层 ZIP。全部 243 文件与外层 ZIP 字节一致，未发现新增或修改文件。[清单与 SHA-256](upstream_source_inventory_20260918.json)记录了逐文件身份。64 个 `.py` 均可通过静态语法解析；未发现 `test_*.py` 或 `pytest.ini`，这不证明代码能运行或分类正确。

重点阅读了采集、清洗、标签定义、分类和验证脚本、2.0 抽取与审核界面，并对随附 CSV/JSON/SQLite 做了只读计数和关联核验。没有逐页审阅所有 Notebook 图表，也没有执行原仓库脚本、加载 pickle、安装依赖、联网采集、调用模型或改变当前应用数据库。

当前比较基准为本项目 0.3.1 的源码和输入契约，而不是把旧仓库 README 的目标当成已实现功能。原始要求见[FA26 摘录](../analysis/FA26_project_brief.txt)，本期边界见[要求核对](FA26_REQUIREMENTS_AUDIT.zh-CN.md)。

## 2. 先列不好直接做的部分

| 难点／实际发现 | 会影响什么 | 当前处理与重新推进条件 |
|---|---|---|
| 16 条华邮记录的 sponsor 与采集关键词一致，采集器直接写 `sponsor=self.keyword` | 公司×媒体数量可能被误读为已核实付款方统计 | 保留来源值，列入独立披露核验；不能据此断言这 16 个身份全错，也不能自动认定全对。 |
| CLAIMS 2.0 多份运行与映射版本不同 | 错配主张层级、错误归因和错误图表 | 先冻结完整 run/bundle，按同一版本验证定义、映射、历史及原文。 |
| 50 条社交研究样本没有充分付费广告证据 | 社交页数据资格与广告分母 | 仅作隔离适配测试；正式统计等待本期数据及纳入标准。 |
| 没有新增 PDF；采集器未保存 URL→PDF 的可靠回执 | 现有 254 个标题关联归档候选仍待核 | 从精确 URL、采集日志、页面披露和内容一致性核验，不能批量升级标题匹配。 |
| 保存的验证 F1 与早先课件约 0.54 不一致，运行记录不完整 | 历史基线可比性与“是否进步”的结论 | 两个口径分开保留；补齐模型、提示、标注及划分来源后再比较。 |
| 旧清洗删除披露、特殊字符或短段落；缺日期有删行或补日的历史处理 | 引用定位、广告身份和日期精度 | 原文保留，清洗结果只作派生视图；有来源证据才补位置映射或日期精度。 |

## 3. 各模块的输入、输出和用途

下列路径均指用户提供的 `D:/549/ml-ciss-native-ads-main`。

| 模块／入口 | 输入 → 输出 | 技术与现在的复用方式 |
|---|---|---|
| [采集入口](D:/549/ml-ciss-native-ads-main/scraper/auto_run.py)、[媒体适配器](D:/549/ml-ciss-native-ads-main/scraper/outlet_scrapers/base_scraper.py) | 媒体、关键词、搜索结果 URL → JSONL/CSV、日志，选配 PDF | Python、Requests、BeautifulSoup、Selenium、搜索服务。优先抽取媒体适配器与配置，不直接重跑覆盖现表。 |
| [清洗与数据文档](D:/549/ml-ciss-native-ads-main/dataset-documentation/DATASETDOC-fa25.md) | 抓取字段／表格 → 清洗文章表 | pandas、Notebook、XLSX。用来追踪字段来历和错误，不覆盖当前不可变正文。 |
| [CLAIMS 1.0 绿色规范](D:/549/ml-ciss-native-ads-main/CLAIMS_model/basemodel/green_prompt.py:5)、[化石燃料规范](D:/549/ml-ciss-native-ads-main/CLAIMS_model/basemodel/fossil_fuel_prompt.py:5) | 一段文本 → 12 个布尔字段与解释 | OpenAI、Pydantic；另有 DSPy 提示优化和动态示例检索。可补真实历史标签说明和旧结果回看。 |
| [句级预测](D:/549/ml-ciss-native-ads-main/CLAIMS_model/runs/sentence_level/sentence_predictions.csv)、[人工标签](D:/549/ml-ciss-native-ads-main/data/handcoded_labels.csv) | 8,285 句历史预测；517 句人工标签 → 频次、每类指标、旧基线 | 预测覆盖 268 篇；人工标签来自 16 篇，且与已有附件字节相同，不是新增独立测试集。 |
| [CLAIMS 2.0 抽取](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/cal-open-coding/greenwashing_builder.py:327) | `id,text,+metadata` → 子主张、上位类、映射、snippet、修改历史及 SQLite | Python、OpenAI/Gemini 接口、JSON、SQLite；现阶段适合离线结果适配，后端重跑留到后续研究。 |
| [2.0 审核 UI](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/src/dashboard/README.md)、[后端](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/src/dashboard/backend/app.py:1459) | 段落／已有规范 → 类别候选、合并建议、审批提案 | HTML/CSS/JS、FastAPI/Pydantic；可选 PostgreSQL/Supabase/JSON 持久化。复用“证据—类别—审核状态”的交互。 |
| [Wordmap](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/src/wordmap/wordmap-main/src/App.jsx:4) | 文件中写死的 5/15/50 篇运行值 → 词云、类别趋势 | React、Vite、Tailwind、Recharts。可参考布局，但不能直接作为本项目实时统计。 |

### CLAIMS 到底做什么

1. **1.0 是叙事分类。** 输入通常已经是收集的广告或企业帖子，判断绿色与化石燃料信息如何出现；不是从整个互联网识别“是否付费软文”的分类器，也不是外部事实核查器。
2. **12 个字段不是 12 个平行主题。** 实际是绿色总类＋7 子类、化石燃料总类＋3 子类。历史绿色规则还要求正面或中性处理，不能直接解释成“这个话题曾出现”。
3. **2.0 是开放编码。** 模型按当前分类词表匹配、修改或新建主张，逐条积累类别。输入是句子、段落还是完整文章由输入文件决定；系统并不自动补齐全文上下文。
4. 代码内规范已找到，但仍需版本和业务裁决。尤其 `false_solutions` 是历史研究规范中的技术分类，不是系统逐项查证技术有效性后的事实结论。

例如，1.0 将 CCS 列入 `false_solutions`，而 2.0 段落 seed 中的 `SC_3` 文字为 “Carbon capture utilisation and storage is a viable solution”。后者可以表示广告提出的主张。**不能按标签名字把二者强行合并，也不能据此给文章盖真／假结论。**

## 4. 对现有数据的实际增量

### 原生广告：主要是血缘和版本，不是全新可用语料

- `data/final_dataset.xlsx` 的标准表有 270 个 URL，都已经在现有 `sources` 的表格中出现；其中 268 个与当前主 CSV 对应。
- 对这 268 个共同 URL，按空白规范化比较正文，95 个相同、173 个不同。但这些不同正文在旧来源表中已有，主要是清洗前后版本差异，不应称为新找到 173 篇完整正文。
- `data/raw` 合计 2,078 行原始结果；`data/prev_data/full_data.xlsx` 有 27,118 行历史候选。后者跨 22 家媒体，15,715 行 sponsor 为空，还包括非能源行业，不能按总行数扩充本项目广告分母。
- 内层 `Manual dataset Native Ads.zip` 为 268 个 TXT、2 个 XLSX 和 2 个目录成员；整个新包没有 PDF。现有归档核验缺口没有因此解决。

### 新的优先质量问题：赞助方来历

[华邮采集器](D:/549/ml-ciss-native-ads-main/scraper/outlet_scrapers/washingtonpost.py:61)在结果构造中直接使用关键词作为 sponsor；虽另有 `_find_sponsor`，该路径没有调用它。[清洗 Notebook](D:/549/ml-ciss-native-ads-main/data_cleaning/validate_data.ipynb:2107)也有 `wp_v2['sponsor'] = wp_v2['keyword']`。

原始／过滤表的 16 条现存华邮记录全部满足 sponsor==keyword，全部进入当前主 CSV，规范化名称也一致：API 6、ExxonMobil 5、Shell 2、AFPM 1、Chevron 1、Eni 1。这是**字段来源需核验**的证据，不是 16 条公司身份均错误的证据。逐 URL 清单见[赞助方来源审查表](upstream_sponsor_lineage_20260918.json)。

[FA25 数据说明](D:/549/ml-ciss-native-ads-main/dataset-documentation/DATASETDOC-fa25.md:103)还记载过“缺日补每月 1 日”。不能反过来认定所有 1 日都是假日期；需要原始日期值或采集证据才能标注 `date_precision`。

### 社交：找到 50 条可测试的历史样本

[test_run SQLite](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/cal-open-coding/runs/test_run/greenwashing_discourse_analysis.db)的 `post_analysis` 中有 50 个不同 ID、URL 和正文：38 条 Twitter/Junkipedia、12 条 Facebook/Meta Content Library，关联 11 个 `parent_entity`。

它能支持真实字段的离线适配测试：正文、账号、平台、原帖链接、企业实体、媒体链接和互动字段。Twitter `published_at` 跨 2017-02-20 至 2025-03-11；Facebook 缺这一字段，只有 `created_at`，不能自动等同发布日期。

但 `ads_data` 全部 NaN，Facebook 的 `is_branded_content` 全为 False；现包不足以确认其付费广告身份。账号与 parent_entity 也不能当 sponsor 自动互换。9 行有模型主张、没有人工真值。应单独标为 `historical_research_sample`，不混入正式广告统计。

metadata 外层带非标准 NaN，内层部分字段是 Python 字典字符串；适配时需限制解析大小／类型、将 NaN 转 null 并验证 schema，不能使用 `eval`。本次未导入这 50 条。

## 5. CLAIMS 2.0 的版本和证据缺口

| 保存位置 | 子主张 | 上位类 | 父子映射 | 运行材料 |
|---|---:|---:|---:|---|
| `src/data/sentence_run_Mar6` | 4,114 | 558 | 4,092 | SQLite 10,740 行，246 个文章 ID |
| `src/data` | 502 | 57 | 497 | 段落 SQLite 806 行，50 篇；输入为 810 段 |
| `src/dashboard` 及其 backend 副本 | 502 | 57 | 124 | 审核 UI 随附 JSON |
| `cal-open-coding/runs/test_run` | 36 | 4 | 10 | 50 条社交研究样本 |

- 文档中的 4,114/558 有对应句级运行，但不代表当前段落版本。段落 seed 是 18 子主张／7 上位类，早期 seed 是 27／4；同一个 SC ID 在不同 seed 中含义会变。关联键必须包含 bundle/run/version。
- 3,905 行 cleaned paragraph CSV 只有 239 个不同 `id`；直接用作 builder 续跑键会碰撞。50 篇抽样 CSV 才有 810 个唯一段落 ID。段落 DB 少了输入的 410、525、580、702 四个 ID；原因未由现包充分记录。
- 段落 DB 的 806 行均能对应输入正文，但 URL/sponsor/platform 字段为 unknown，主要靠 `metadata.article_id` 关联文章，不能直接 join 当前 UUID。
- 同一 codebook/history 的 dashboard map 是 124 条，而数据目录是 497 条；离线 collapse 文件保存的 map 哈希也与现 map 不同。需要重新对齐，不能混用图表。
- 随附 collapse 结果实际是 TF-IDF/SVD＋sklearn DBSCAN，不能仅因文件名有 BERTopic 就称该结果由深度主题模型生成。
- 段落结果里 659 个非空 snippet 中，597 个能原样找到；句级版 4,456 个中有 4,374 个能原样找到。定位失败可能来自删节或规范化，不全是编造；定位成功也不证明支持该类别。

审核 UI 支持提案、批准、驳回和应用，值得借鉴；但当前相似度、固定 0.6 或模型评分都不是校准概率。“validation”有一条路径只检查子类是否属于父类，不读文章。后端部分评分也只看类别文本，不看当前段落。不能把这些数字显示成“文章判断正确率”。

## 6. 旧版 F1 与可以重现的部分

[保存的总体指标](D:/549/ml-ciss-native-ads-main/CLAIMS_model/runs/sentence_level/validation_overall_metrics.csv:2)为 **micro F1 0.8204、macro F1 0.7767**。用独立 CSV 计算复核：金标准和预测均为 517 个唯一 `(doc_id,sent_idx)`，517/517 对齐、对应句子完全一致，重算得到相同数值，没有连接丢行。

这与此前课件／对话中的约 0.54 不同。缺少能把二者连接起来的完整运行 settings、模型版本、提示及划分记录，**不能解释为系统从 0.54 提升到 0.82**。这些结果也不是本次新调用模型所得。

还应报告每类支持数：回收标签仅 2 个阳性，F1=1；自然／动物也只有 2 个阳性，F1=0.5；基础设施有 38 个阳性，F1 约 0.581。总体分不能覆盖小样本和类别差异。

人工 517 句文件与已有附件字节相同；具体子类符合 OR 合并，other 列还有差异，不能宣称已经证明完整人工裁决过程。它适合历史复现和开发分析，不能当新增独立验收集。

不应直接照搬的实现包括：

- [fewshot_run.py](D:/549/ml-ciss-native-ads-main/CLAIMS_model/fewshot_run.py:99)实际关闭 dynamic fewshot；文件夹名字不能证明检索示例带来改进。
- [动态示例检索](D:/549/ml-ciss-native-ads-main/CLAIMS_model/dynamic_fewshot/fewshot_retriever.py:56)无条件丢第一条，没有文章组／测试集隔离，且存在标签字段名不一致。
- [API 失败处理](D:/549/ml-ciss-native-ads-main/CLAIMS_model/sentence_level_run_validation.py:106)返回全 False；应保留失败状态，不能把失败当阴性。
- DSPy 模块做提示和示例优化，不能叫训练出新权重；其输入划分文件不全，部分优化分数实际相当于标签位准确率，不能直接复用作多标签阳性 F1。
- 旧逐句模型没有原文字符位置和全文主体／反驳处理；新系统应继续使用当前版本、偏移和引文校验。

## 7. 可执行的后续顺序

这些是审查后的实施建议，**本次没有自动改网页、合并旧代码或发布数据**。

| 顺序 | 做什么 | 可审查的交付物／通过条件 | 需要新模型费用吗 |
|---|---|---|---|
| P0 | 处理赞助方与日期的来源问题 | 16 条 sponsor 来源清单、披露证据、字段 provenance；证据不足保留未知／待核，不从 keyword 推断身份 | 不需要；少量来源核验需要人工裁决 |
| P1 | 建立历史研究资料适配层 | 不同 run 独立 manifest；旧 article/doc_id→当前 record/version 的 URL＋正文对账；未匹配项留队列 | 不需要 |
| P1 | 补历史标签的解释和证据回看 | 真实代码规范、父子结构、运行版本、原句与上下文；点击标签能回到已核对原文，无法定位则明确待核 | 不需要重新跑模型 |
| P1 | 用 50 条社交样本测试适配器 | 单独 fixture、字段映射、日期语义、账号／企业区分、导出与页面空态测试；不改变正式广告分母 | 不需要 |
| P2 | 在现有 Dash 复用研究审阅交互 | 候选主张→原文→父类→审核状态；版本一致、修改有记录；结果不混入正式主题统计 | 展示旧结果不需要 |
| P2 | 改造已有采集器供后续更新 | 增量 URL 去重、正文版本、质量状态、PDF 路径＋哈希＋采集 URL 回执，旧记录保留 | 实际新采集可能涉及搜索服务费用，另定范围 |
| 后续研究 | 复跑或改进 CLAIMS 2.0 | 先冻结规范和文章分组，分别测定位、语义支持、父子归类与上下文；新类别先入提案队列 | 会，需要单独实验范围 |

推荐的最小接入链路：

```text
历史运行文件（各版本分开）
  → 定义、映射和文章身份对账
  → 对应现有 record_id + body version
  → 原句／段落定位与来源记录
  → 只读历史标签、证据与研究审核入口
```

**先做 P0 和 P1，能补足当前项目的解释性、数据来源和测试材料。无需换掉现有 Dash/PostgreSQL/RAG，也无需先安装整套旧依赖。** 旧 CLAIMS 固定 OpenAI 1.x 等依赖，与当前工程版本不同；以后复跑宜用独立环境。根 LICENSE、子目录 LICENSE 和 README 的许可元数据也不同，代码抽取前应核对对应文件来源与许可信息，本次没有复制旧实现进应用。

## 8. 建议阅读入口

- [原仓库总览](D:/549/ml-ciss-native-ads-main/README.md)：了解历届目标；不能单凭说明认定功能完整。
- [春季团队经验](D:/549/ml-ciss-native-ads-main/dataset-documentation/lessons_learned.md)：小样本偏差、全文阅读、规范迭代与聚类局限。
- [CLAIMS 1.0 规范](D:/549/ml-ciss-native-ads-main/CLAIMS_model/basemodel/green_prompt.py)：理解历史标签的实际含义。
- [2.0 段落 seed](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/src/data/seed_superclaims.json)：看新一轮研究想捕捉哪些主张。
- [审核原型](D:/549/ml-ciss-native-ads-main/CLAIMS_2.0_model/src/dashboard/README.md)：界面用途、输入文件及离线结果。
- [逐文件清单](upstream_source_inventory_20260918.json)、[16 条 sponsor 核验队列](upstream_sponsor_lineage_20260918.json)：本次审查的可复核材料。
