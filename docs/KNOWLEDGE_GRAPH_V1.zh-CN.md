# 广告来源知识图谱 v1

本机入口：[Data → Relationships](http://127.0.0.1:8050/data)。此版本建立来源与历史标注层，尚不抽取新的广告主张，也不作外部事实核查。

试用步骤与实际验证见[本轮交付报告](../reports/KNOWLEDGE_GRAPH_V1_20260925.zh-CN.md)。

## 数据模型

图谱是现有 PostgreSQL 当前记录与不可变文本版本的确定性投影。稳定节点、类型化关系和来源声明可通过 API/JSON 导出，独立于 Plotly 展示；没有另外复制一套可能失步的事实库。

| 节点类型 | 身份与含义 |
| --- | --- |
| Article | dataset + record_id；代表来源记录，不承诺已完成跨站转载去重 |
| TextVersion | record_id + version_id，保留正文散列、长度、存储时间和提取限制 |
| SponsorCandidate | dataset + sponsor 字段原值；来源列示的候选主体，不等于已审核公司 |
| Outlet | dataset + publisher 字段原值；来源媒体名称，不自动推断其法律主体或母公司 |
| SourceArtifact | 原始网址、归档网址引用，或与版本绑定并通过散列核验的本地 PDF |
| Annotation | 文章版本 + 原始标注序号，保留标注版本、文本绑定、来源散列／行号和未审核状态 |
| Label | 标签词表版本 + 标签键；原始 codebook 缺失时明确标为 unavailable |
| EvidenceSpan | 精确文本版本 + Unicode 字符起止位置；仅在真实输入包含且校验通过时生成 |

组织名称的大小写显示修正不构成实体合并。CERAWeek 的活动类型及 API/AFPM 的协会类型只作现有显示提示。缺失 sponsor/publisher 存在 Article 的缺失标志中，不建立虚假的共用 Unknown 实体。

## 关系字典

| 谓词 | 方向 | 含义 |
| --- | --- | --- |
| source_lists_sponsor | Article → SponsorCandidate | 来源字段列示该赞助方，不证明付款 |
| published_in | Article → Outlet | 来源字段列示该媒体，不证明媒体认同文章主张 |
| has_text_version | Article → TextVersion | 当前存储文本版本，不保证正文完整 |
| has_source_reference | Article → SourceArtifact | 原始网址引用，不是网页内容的不可变快照 |
| has_archive_reference | Article → SourceArtifact | 已存归档网址，不自动核验其内容 |
| derived_from | TextVersion → SourceArtifact | 公共附件注册记录确认的恢复来源 |
| has_annotation_record | Article → Annotation | 文章关联的历史标注记录 |
| annotates | Annotation → TextVersion | 标注所记正文散列与该版本精确一致 |
| assigns_label | Annotation → Label | 此次标注赋予的类别，不是事实裁决 |
| has_evidence | Annotation → EvidenceSpan | 引用了校验过位置的片段，不保证语义支持 |
| located_in | EvidenceSpan → TextVersion | 该片段在确切文本版本中的位置 |

所有关系有独立 ID，并保存 record_id、version_id、来源字段、生成方法和审核状态；标注关系补充可用的原始文件散列及行号。私有文件路径、raw 原始导入和模型解释字段不会进入公共图谱。

## 查询与界面

- 延用现有赞助方、媒体、日期、收集检索词和历史标签筛选。
- 每页 5 篇文章，默认聚焦其中一篇；点击节点／关系或使用检查下拉框，在旁边看定义与来源。
- **Sources** 呈现来源关系，**Historical labels** 按标注版本呈现标签和证据关联。页面明确列出当前可见数量与该文章完整图谱数量；两层不改变完整数据。直角连线绕开节点框，关系名称在线旁显示，选中路径高亮且位置不变。
- JSON 下载包含当前页，而非所有 263 条默认合格记录。覆盖范围随筛选变化。
- Overview 矩阵仍由 SQL 统计完整筛选范围；图谱的 `relationship_counts` 可沿文章路径生成同口径计数，避免把多个标注／版本关系重复算作文章。
- 所有图谱查询均为只读操作，不调用 LLM，不重新导入文章或重算向量。

### API

`GET /api/knowledge-graph/schema` 返回版本、节点类型、关系定义与身份策略。

`POST /api/knowledge-graph` 接收：

```json
{
  "filters": {"dataset": "native", "sponsors": ["exxonmobil"]},
  "offset": 0,
  "limit": 5
}
```

limit 范围为 1–20；只支持 native。响应包含 `nodes`、`edges`、`records`、`coverage`、`filters`、`warnings` 及 schema。翻页请求各自读取当前一致快照；它不是跨多个请求锁定的永久语料版本。

## 校验与边界

结构校验覆盖节点／边 ID、端点、谓词的允许类型、关系来源与文章版本一致性。证据校验要求版本和正文散列匹配、字符区间合法、引文等于原文切片。字符匹配只证明引文存在，不证明其支持标签。

当前历史标签通常没有逐条证据片段；系统保留 `no_validated_spans`，不从 RAG 检索片段或模型解释里推造证据。若标注属于此前的正文，只保留历史状态，不连接到新正文。现有 PDF 恢复记录会明确提示此前标注未应用于恢复后的文本。

下一阶段需提供或审核：实体别名／组织归属映射、原始 codebook、可定位的标注证据。具体主张、表达主体、文章处理方式及外部核查结果应另行建模，不能用十二标签代替。

## 维护入口

- `knowledge_graph.py`：语义模型、稳定身份、来源声明、校验与统计投影。
- `db.py: knowledge_page`：过滤、当前版本与一致分页快照。
- `service.py: knowledge_graph`：公共字段和附件版本绑定。
- `knowledge_ui.py` / `knowledge_visual.py`：关系探索与图形展示。
- `knowledge_routes.py`：只读 schema 与分页导出 API。

概念依据：[Hogan 等知识图谱综述](https://aidanhogan.com/docs/knowledge-graphs-computing-surveys.pdf)、[RDF Concepts](https://www.w3.org/TR/rdf11-concepts/)、[PROV-O](https://www.w3.org/TR/prov-o/)。本实现是项目自定义 JSON 属性图，不宣称 RDF、OWL 或 SHACL 标准符合性。
