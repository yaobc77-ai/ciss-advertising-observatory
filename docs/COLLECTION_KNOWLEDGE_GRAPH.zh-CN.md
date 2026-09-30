# 原生广告集合知识图谱：使用流程与技术契约

更新：2026-09-30。此文补充 0.4.2 的选取行为契约；发布及验证范围以[本轮选取修订报告](../reports/GRAPH_SELECTION_V0_4_2_20260930.zh-CN.md)为准，文档更新不代表生产已经升级。下文 9/29 的数字与核对证据保留原快照范围。

**9/29 详情第二版：** 节点点阵与正文可检索性外环、公司／媒体的完整分类环图、可点击数量／占比名单、扇区对应文章、精确文章子集与对象计数 CSV。客户六项要求复核见 [第二版交付报告](../reports/GRAPH_DETAILS_V2_20260929.zh-CN.md)，对应真实数据核对见 [占比分母与范围检查](../reports/graph_breakdowns_smoke_20260929.json)。0.4.2 将当前选取、父级分布、文章展开与导出范围进一步区分，见下面使用流程。

## 1. 这张图回答什么

在 **Data → Native advertising → Knowledge graph** 中，用户可以先点公司／赞助方候选，看来源记录列出的媒体；也可以先点媒体，看来源记录列出的赞助方。点关系线后，在旁边查看支持该关系的广告记录。

大图参考了 How Do They Lobby 的“全图 → 选定对象 → 关系计数与记录详情”流程，具体观察记录见[参考站核对报告](../reports/LOBBY_GRAPH_REFERENCE_20260929.zh-CN.md)。该站的游说关系与广告字段具有不同含义；本项目没有导入其数据或套用其政治关系定义。

图谱用于探索连接。**Overview** 的公司 × 媒体矩阵、数字与交叉表继续承担精确数量比较；**Records** 提供记录检索与详情。三个入口使用相同的集合筛选口径。

## 2. 当前完整范围与计数证据

以下数字来自[集合图谱数据库核对记录](../reports/collection_graph_smoke_20260929.json)，对应当时的完整原生广告选择，包含缺日期记录。它们是存储集合的记录数，不是整个广告市场的投放量。

| 项目 | 当前数量 | 含义 |
| --- | ---: | --- |
| 合格原生广告记录 | 263 | 全范围保留，不按正文能否检索排除 |
| 赞助方／组织源字段名称 | 19 | 包含公司、协会及会议等候选类别 |
| 媒体源字段名称 | 8 | 来源列出的媒体候选 |
| 可检索正文记录 | 226 | 不决定关系图中的计数资格 |
| 汇总关联 | 35 | 每对赞助方与媒体的共同记录集合 |
| 支持汇总关联的记录 | 262 | 另 1 条记录缺赞助方字段 |
| 缺媒体字段记录 | 0 | 本次快照中的字段缺失情况 |
| 源字段关系边 | 525 | 262 条赞助方边＋263 条媒体边 |

两种视图的全范围规模不同：

- **Entities**：19 个赞助方候选＋8 个媒体，合计 **27 个节点、35 条汇总线**。
- **Articles**：未限定展开对象时，263 个文章节点＋27 个实体节点，合计 **290 个节点、525 条源字段边**。

文章节点数为 263；不存在为补齐字段而创建的 `Unknown` 实体。缺赞助方的记录仍保留为文章，并连接到已知媒体。选定对象后再切换 Articles，会展开该对象的支持文章；页面同时说明当前展开范围和全选择总量。

已核对的例子：

| 选择 | 支持记录 | 连接对象 |
| --- | ---: | --- |
| ExxonMobil | 15 | 4 家媒体：Business Insider 5、Washington Post 5、New York Times 3、Wall Street Journal 2 |
| The Washington Post | 18 | 7 个赞助方／组织类别：API 6、ExxonMobil 5、Shell 2、Southern Company 2、AFPM 1、Chevron 1、Eni 1 |
| ExxonMobil × The Washington Post | 5 | 一条汇总关联，保留 5 条记录与各自版本见证 |

核对记录中的各选择与数据库矩阵计数一致。它证明这些快照上的计数与来源路径一致，不证明赞助关系已经由合同或付款材料核实。

## 3. 使用流程

1. 在 Data 选择 **Native advertising**，调整公司／赞助方、媒体、日期等集合筛选。上方显示当前范围。
2. 打开 **Knowledge graph**。默认 Entities 展示当前选择的全部实体与汇总关系，不只展示 Top 8 或 Top 10。
3. 点击公司／媒体节点，或用 **Find a node or relationship** 搜索名称。侧栏先给出命名的关联对象表、逐项记录数／占比，再显示分类环图。表和图明确写出父对象及全部支持记录的分母；缺失来源字段单独列为一项，并包含在分母中。
4. 点击关系线或 Article 节点，查看命名的 **source → predicate → target**，如 `ExxonMobil → Co-listed in source records → The Washington Post`，或 `文章标题 → Source lists sponsor → ExxonMobil` 与 `文章标题 → Published in → 媒体名称`。文章列表每页 10 条；翻页仅改变旁边的列表，不重新排列图。缺赞助方或媒体字段时明确说明缺失，不为该字段断言关系或编造实体。
5. 点环图扇区、名单中的名称或 **Show supporting records for** 后，大标题显示当前关系／分类及其 N 条支持记录，文章列表读取这一子集；下方图表仍保留明确命名的父级分布及完整分母。例如选中 ExxonMobil 下的 Washington Post，标题与列表是两者共同的 5 条，父分布仍是 ExxonMobil 的 15 条，所占比例仍为 5/15。分类颜色仅在这份分布中区分分类。
6. 切到 **Articles** 展开确切来源路径，包含缺来源字段的文章。此模式下，点击新节点／线、键盘选取名称或改变分类都会同步重建当前展开范围，使画布与侧栏描述同一选择；范围来自当前集合筛选，而不是沿用上一个对象的文章子集。未选对象时展开当前筛选的全部文章。文章标题进入既有正文和原始材料详情页。
7. **Download selected counts** 在选中分类时仅导出该分类的一行数据，仍保留父对象的分母和占比；选择 **All supporting records** 时导出全部分类。JSON 的 **Download complete filtered source map** 则始终导出当前集合筛选的完整图，不受节点、线、分类或局部展开限制。
8. 用 **Fit** 适应画布；用 `+`／`−` 或滚轮缩放；拖动节点与画布。默认 **By type** 将赞助方和媒体分组排列，优先让名称可读；另有 Network、Circle 或 Grid 布局。位置是排版，不代表地理或商业距离。**Reset** 清除选择并重置布局；**Expand view** 扩展图谱区域，Escape 可退出。打开或改变画布尺寸后自动适配，保留现有节点位置和选择，不需要先 Reset。

点选会高亮关联范围并淡化其他连接，不会在 Entities 中删除其他关系。**Entities** 的普通点选，以及两种模式中的记录翻页，保留现有布局、平移及缩放；**Articles** 改选节点／线／键盘名称或分类会重建对应的文章范围。切换视图、布局或集合筛选也会重建画面。

图中圆形是来源赞助方候选，圆角方形是媒体，小节点是具体文章。实体中的每个点代表一条记录；外环区分可检索正文与仅元数据，不表示正文完整或主张真假。Articles 中的点阵与数字对应展开的记录子集；完整当前筛选计数另保留。源字段边明确标注 Source lists sponsor／Published in；实体汇总线无付款方向箭头。

下方折叠区 **Inspect article versions, sources and historical annotations** 保留原有检查器：每次 5 篇文章，检查正文版本、来源引用、已核对材料及历史标注。它与全范围总览职责不同，不是把全库限制成 5 篇。

## 4. 节点、线与证据的含义

源字段路径为：

```text
赞助方候选 ← source_lists_sponsor ← 广告记录 → published_in → 媒体候选
```

`SponsorCandidate`、`Outlet`、`Article` 沿用既有来源图谱的稳定 ID。ID 基于相应的精确来源身份；展示名变化不改变源字段值，也不自动归并企业。例如 Williams、Williams Companies 与 The Williams Companies, Inc. 继续是独立类别。CERAWeek 的会议提示、API／AFPM 的协会提示仍是展示层提示，不是审定的组织分类。

Entities 中的直接线使用 **`derived_source_association`**，表示“同一批来源记录共同列出这两个名称”。每条线包含：

- `count`：不同合格记录的数量。
- `record_ids`：完整支持记录 ID。
- `witnesses`：每条支持记录的 `record_id`、`version_id`、`dataset`、文章节点 ID，以及两条原始源字段边 ID。
- `provenance`：来源字段路径的聚合方法与未独立核实状态。

这些见证允许从汇总线回到文章路径。直接线不表示已验证付款、合同、所有权、背书或商业合作，更不表示已判定漂绿。

视觉编码也有明确口径：

- 颜色与形状区分赞助方候选、媒体和文章。
- 实体节点数字是包含该名称的**记录数**，不是邻居数或图论中的度数；字号保持可读，节点大小采用有上限的非线性缩放。
- 汇总线宽按支持记录数缩放；选中关系显示计数。文章源字段边表达单条记录路径。
- 缺失字段以范围说明及文章状态保留，不造一个共同的 Unknown 企业节点。

## 5. 筛选、日期与导出

后台首先应用当前 `Filters`，再读取同一只读 SQL 快照内的全部合格记录。没有 Top-N 限制，也不会只取可检索正文的记录。空选择显示空图及零条匹配记录；这不证明外部世界不存在相应广告。

日期筛选沿用集合的 `include_unknown_dates` 开关。当前完整选择包含 **22 条缺日期记录**；关闭未知日期后，核对范围变为 **241 条记录、34 条汇总关联**。缺日期的记录不被赋予猜测日期；旁边的支持记录列表会明确显示未知日期数量。

| 导出 | 范围 | 可用于什么 |
| --- | --- | --- |
| **Download selected counts ↓** | 选中分类时仅该分类一行；All supporting records 时为父分布的全部分类。每行保留父分母、占比、精确源值及缺失标记 | 审核当前关系／分类的计数；不能把所选分类占比重置为 100% |
| **JSON ↓ — Download complete filtered source map** | 重新读取当前集合筛选的完整图，包含所有节点、文章边、汇总边、见证与公开记录 | 审核计数、关系路径与筛选范围；不受当前点选或局部展开限制 |
| **PNG ↓** | Cytoscape 当前渲染视图 | 分享当前 Entities 或 Articles 画面；不能代替完整 JSON 证据导出 |

集合筛选改变后，原选择被清除，避免把旧关系误认为新范围中的结果。显示来源链接关闭时，公开原文和归档链接也从图谱记录与导出中移除。

## 6. 技术实现与公开契约

### 数据到画布

```text
可信集合 Filters
  → Database.knowledge_map_rows(): 全选择、当前版本、只读 SQL 快照
  → Service.knowledge_map(): 来源链接配置＋公开筛选范围
  → build_collection_map(): 既有身份与源字段边＋有见证的汇总关系
  → collection_graph_visual: Entities / Articles 的 Cytoscape 元素与样式
  → collection_graph_ui: 点选、侧栏、布局、分页与导出
```

全图读取只在 Data 的原生广告 Knowledge graph 视图启用时执行；画布布局、缩放与拖动由浏览器中的 Cytoscape 完成。后端按可信筛选和规范 ID 重新解析点选，不把浏览器传入的计数或节点属性当作数据库事实。

复用已安装的 **`dash-cytoscape 1.0.2`**，没有自造图形引擎。组件能力见 [Dash Cytoscape 官方介绍](https://dash.plotly.com/cytoscape)、[属性参考](https://dash.plotly.com/cytoscape/reference)和[官方图像导出示例](https://dash.plotly.com/cytoscape/images)。当前实现使用既有布局、元素、样式和回调接口。

### 返回结构

| 字段 | 内容 |
| --- | --- |
| `schema_version` / `source_schema_version` | 集合视图与原来源图谱的版本 |
| `nodes` | 全部文章、赞助方候选、媒体及精确记录成员；`record_count` 计文章成员 |
| `article_edges` | `source_lists_sponsor`、`published_in` 原类型边与记录／版本来源 |
| `summary_edges` | `derived_source_association`、完整记录集合与路径见证 |
| `records` | 全部选中记录的公开字段、详情入口、版本 ID、正文哈希引用及安全链接 |
| `coverage` / `counts` | 完整选择、显示数量、缺失字段及检索资格统计 |
| `identity_policy` / `predicate_definitions` | 精确源值身份政策和关系含义 |
| `filters` / `limitations` / `warnings` | 当前范围、分析边界与必要的来源限制 |

总览**不载入正文或任意标注 payload**，也不公开 raw 导入内容、私有来源路径或凭据。`body_hash_status = "stored_reference_not_checked_in_overview"` 表示哈希只是数据库中存储的版本引用。真正的正文哈希、字符位置和原文证据核对继续由记录／证据检查器完成；缺少正文读取不被误报成哈希缺陷。

构建器拒绝重复记录输入，即使内容相同也不静默合并；汇总验证器检查计数、不同记录集合、版本与原始文章边是否相符。本版没有调用付费模型，没有重建索引，也没有改写广告原文或来源数据。已保存的核对结果注明 `no_model_calls = true`、`source_data_unchanged = true`；这是本次核对范围的证据。

## 7. 与 MCP、社交数据和 CLAIMS 的边界

本版新增的是网页的全选择关系图，**没有新增完整集合图谱 MCP 工具或修改现有 7 个工具 schema**。现有 `get_graph_schema` 与 `get_graph_neighborhood` 仍可读取图谱定义和最多 5 篇文章的来源邻域；邻域不能用于推算全库数量。统计继续使用 `record_statistics`。现有工具说明见 [MCP 研究工具文档](MCP_RESEARCH_TOOLS.zh-CN.md)。

后续扩展仍需要以下材料与决定：

- **社交广告**：正式数据导出、字段口径、来源引用与适当的实体关系；当前原生广告图不能直接冒充社交数据图。
- **正式 CLAIMS**：版本化标注规范、正文绑定、适用的分类结果及审核状态；历史自动标签不升级为已核实漂绿。
- **身份与计数审核**：企业别名归并、会议／协会是否纳入公司分析、重复广告或转载的研究计数规则及负责审核的人。
- **发布与验收**：浏览器交互、图像／文件导出及线上版本分别核对；工程与快照检查不能替代客户对使用流程和研究口径的确认。

这些扩展应保留当前的记录与版本见证、公开来源入口和关系定义，而不以更复杂的图形代替证据。
