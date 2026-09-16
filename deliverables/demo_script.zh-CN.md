# Research preview 中文演示讲稿

配套文件：[research_preview.pptx](research_preview.pptx)。快照日期：2026-09-16。

本次展示 **Native corpus connected** 的研究预览。完整交付目标仍为双数据集 Dashboard 与 RAG。本文中的演示步骤是操作指引，已确认的数字单独标明；演示中出现的新结果以当时的数据版本为准。

## 演示前准备

- 打开本机应用：[http://127.0.0.1:8050](http://127.0.0.1:8050)。如服务未运行，按 [README](../README.md) 和 [运行指南](../docs/operations.md) 启动 PostgreSQL 与应用。
- 保持 Native advertising，清除赞助方、日期与其他筛选，勾选 **Include unknown dates**。
- 将下面三份已有模型结果放在本地阅读器中备用，无需为演示再次调用模型：[CCUS](../outputs/live_ccs_scoped.json)、[biogas](../outputs/live_biogas.json)、[资料不足](../outputs/live_no_evidence.json)。
- 先用 **Search keywords** 检索。只有讲解付费入口时才指向 **Generate paid answer**，默认不点击。再次调用会使用项目 API 预算，且结果可能变化。
- 展示公众页面与导出文件即可。密钥、连接串及数据库内部原始字段不属于演示内容。

## 第 1 页：Research preview

**讲述**

“这是 CISS Advertising Observatory 的研究预览。我们现在接入了真实的原生广告语料，可以在本机查看筛选结果、导出记录，并检查模型回答对应的原文证据。这里展示当前已经完成和核验的部分，完整项目的双数据集和公众部署验收仍需继续。”

## 第 2 页：FA26 dashboard and RAG

**讲述**

“项目目标是在同一个观测站中提供原生广告和社交广告两个独立数据集，以及基于检索证据的问答。原生语料已接入。社交数据目前只有适配器和独立界面，真实导出尚未提供，所以页面明确显示 not connected。CLAIMS 的历史标签可供探索，CLAIMS 后端集成仍留在后续范围。”

**操作**

1. 点击 **Social advertising**，展示 **Social advertising is not connected**。
2. 切回 **Native advertising**。解释两个数据集保留各自筛选状态，跨数据集搜索另有明确范围。

## 第 3 页：Native corpus and remaining text limits

**讲述**

“当前收录 268 条原生记录，256 条符合计数资格，221 条具有可检索正文或可用前缀，形成 510 个文本块。这三个记录数属于同一批语料的不同资格层次，不能加在一起。界面的 Selected records 显示可计数记录，并不等于原始文件的收录行数。”

“20 条日期冲突保留为未知。另有 20 条记录只索引明确导航标记之前的前缀，原始全文仍保留。94 条记录带疑似截断标记，这是一项检查提示，并没有确认截断原因。这些现有片段可以支持局部引文，但不足以证明整篇文章中没有某种说法。”

**已核验快照**

| 指标 | 当前值 |
|---|---:|
| 收录记录 | 268 |
| 可计数记录 | 256 |
| 可检索正文或前缀 | 221 |
| 索引文本块 | 510 |
| 日期未知 | 20 |
| 按导航边界保留可用前缀 | 20 |
| 疑似截断标记 | 94 |

依据：[数据字典的本机导入快照](../docs/data_dictionary.md)。质量标记可能重叠，不用其总和计算语料规模。

## 第 4 页：Implemented technical flow

**讲述**

“输入适配器读取 CSV 和 XLSX，保留来源位置、正文版本与异常。PostgreSQL 保存记录和片段，pgvector 保存向量。Python Dash 和 AG Grid 共用筛选服务，因此图表、明细与导出使用相同的记录集合。”

“免费搜索用关键词找原文。付费回答使用 OpenAI 的查询向量和 Responses，先限定数据集与筛选条件，再检索证据。程序检查引文 ID、引句是否确实位于该版本原文，并执行预算和失败处理。字符对得上不等于语义一定支持结论，后者仍需正式评估。”

**边界**

该流程以现有代码和 [架构文档](../docs/architecture.md) 为准。它不包含本次未实施的分类模型训练，也不代表已经完成 CLAIMS 后端重建。

## 第 5 页：Native demonstration

### A. 原生看板

1. 展示默认 **Native advertising**。
2. 指出 **Selected records 256 / Searchable records 221 / Unknown dates 20**。
3. 展示 **Count / Percent**，解释百分比的分母是当前筛选记录。
4. 展示新闻媒体、赞助方、时间分布、赞助关系和六字段明细。

**讲述**：“图表只显示相应的头部类别，表格和下载仍包含完整筛选集合。来源链接开关同时影响表格、证据和 CSV。”

### B. ExxonMobil 筛选与导出

1. 在 **Sponsor / advertiser** 选择 `exxonmobil`。
2. 展示 **15 selected / 13 searchable / 0 unknown dates**。
3. 点击 **Download selected records**。
4. 打开下载文件，确认 15 条数据行，且赞助方均为 `exxonmobil`。不把 CSV 表头算成数据行。

**已执行证据**：浏览器筛选为 15 条；`C:/Users/yaobc/Downloads/native-advertising.csv` 在当次验证中包含 15 个不同 record_id，均为 exxonmobil。后续下载可能自动更改文件名，应以刚下载的文件为准。

### C. 日期与未知值

1. 清除 sponsor 选择，避免日期演示受 ExxonMobil 限定。
2. 设置示例范围 `2020-01-01` 到 `2023-12-31`。
3. 对比勾选和取消 **Include unknown dates** 时的计数、时间线与明细。
4. 清除日期并重新勾选 **Include unknown dates**，再进入证据检索。

**讲述**：“日期未知记录可以独立纳入或排除，时间线只画有日期的记录。这个日期范围属于演示操作，具体结果以页面当时显示为准。”

### D. 免费检索原文

1. 搜索范围选择 **Current collection and its filters**，确认 sponsor/date 已清空。
2. 输入 `CCUS`，点击 **Search keywords**。
3. 展开一张证据卡的 **Read retrieved passage**，指出标题、短引文、record ID、text version 与来源链接。
4. 输入 `biogas`，再次点击 **Search keywords**，重复查看原文。
5. 说明 **Both collections · all eligible records** 会独立搜索两个集合的完整合格记录，不沿用当前某一数据集的筛选条件。

**讲述**：“每次结果都保存了提交时的问题和筛选范围。改变控件不会自动重新请求，必须再次点击搜索。当前排名可能变化；如果特定保存样例没有排进前五，使用下一页已有 JSON 讲解该样例，不把检索排名失败包装成成功。”

## 第 6 页：Early model checks

**讲述**

“这页展示两个保存的真实模型回答和一个资料不足拒答。它们验证了 API 连接、生成、引用回查与拒答路径，尚不能用来估计整体准确率。先区分广告表达了什么，再讨论这种说法是否有外部事实支持。”

### CCUS 样例

- 保存结果：[live_ccs_scoped.json](../outputs/live_ccs_scoped.json)，状态 `answered`。该次调用限定到目标文章。
- 文章：[CCUS, the industry that will change industry](https://www.cnbc.com/advertorial/ccus-the-industry-that-will-change-industry-/)。
- 原引句：`In some industries, CCUS can reduce carbon emissions by up to 90%.`
- record ID：`e3701f9b-e7b3-5811-9282-da6b0ad776c3`。
- version ID：`35e42f5f3e77b7b55d0095b7564216fa176930f4a5f76f56f702bc8b6ab6c327`。

**讲述**：“广告声称，在一些行业 CCUS 最多可以减少 90% 的碳排放。我们展示的是广告中的原句，尚未在这里验证技术效果。”

### Biogas 样例

- 保存结果：[live_biogas.json](../outputs/live_biogas.json)，状态 `answered`。
- 文章：[Biogas to offset air travel emissions](https://www.cnbc.com/advertorial/2018/11/09/biogas-to-offset-air-travel-emissions.html)。
- 原引句：`from reducing the number of trips to offsetting flights that can't be avoided`。
- record ID：`01374b51-3fae-5fe7-8c60-b4bffa2b7ba0`。
- version ID：`0d0146b9d07a012d9d6290df34030655fca31de01baf84cb3bd97006690a1acf`。

**讲述**：“这篇广告把减少员工出差与抵消无法避免的飞行相联系，并提到沼气项目。可以逐条回到引文检查模型是否忠实概括广告。”

### 资料不足样例

- 保存结果：[live_no_evidence.json](../outputs/live_no_evidence.json)。
- 问题主题：Mars 1890，当前集合缺少支持材料。
- 返回 `insufficient_evidence`，`citations` 为空。

**讲述**：“检索可能仍返回词义接近的片段，生成端需要承认这些材料不足以支持问题。一次成功拒答不代表所有无证据问题都能处理正确。”

正式质量评价见 [evaluation_protocol.md](../docs/evaluation_protocol.md)。目前未完成人工语义支持率与完整双数据集评价。不要从三个展示案例计算‘准确率’，也不要使用早期 JSON 成本字段作当前账单。

## 第 7 页：Current handoff and reserved integrations

**讲述**

“当前可以交接本机原生广告应用、可追溯证据、代码和操作文档。社交实料、指定 GitHub 仓库和固定域名由用户暂缓提供，我们已经保留对接位置。接下来需要补齐外部输入、更广的问答评价，以及另一网络上的公众访问验证。”

**交接入口**

- [README](../README.md)：安装与本机启动入口。
- [用户指南](../docs/user_guide.md)：筛选、导出、检索和付费问答。
- [数据字典](../docs/data_dictionary.md)：资格规则、版本和质量限制。
- [运行指南](../docs/operations.md)：预算、备份恢复与预留公网配置。
- [评价协议](../docs/evaluation_protocol.md)：问答评价边界和剩余人工工作。
- [实施与验收状态](../docs/acceptance_status.md)：完整交付目标与待完成项。

## 演示中断时

| 现象 | 当场处理 |
|---|---|
| 本机页打不开或数据服务失败 | 说明当前服务不可用，按运行指南检查；改用本 PPT 和保存 JSON，不展示模拟数据 |
| 免费关键词没有目标文章 | 清除错误筛选，换用精确关键词；仍无结果则展示保存案例并注明路径 |
| 付费接口故障或限额 | 保留免费搜索和记录浏览，展示保存结果；不反复重试 |
| 社交为空 | 解释真实数据尚未接入，这是当前边界 |
| 来源外站失效 | 展示本机保存的原文片段及版本 ID，不声称链接在线可用 |
