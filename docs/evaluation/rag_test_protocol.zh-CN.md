# RAG 分层测试方案（P60）

更新：2026-10-09。补充[检索与回答评价方法](retrieval_evaluation.zh-CN.md)：按题型分层，并把“路由选错”和“检索排序差”分开测。阈值是团队建议，客户尚未批准。

## 1. 指标口径

Recall@K、MRR、NDCG@K 是信息检索的经典指标，但并没有“RAG 必须同时用这三项”的统一标准。它们只评价检索阶段，不能说明最终回答可靠。本项目分三层测，每层单独报告，不合并成一个总分。

| 层 | 测什么 | 指标 | 计算工具 |
| --- | --- | --- | --- |
| L0 路由 | 问题是否交给了正确的工具（正文搜索／标题查找／统计） | 首次路由准确率、到达预期工具且成功的比例、错误类型 | `scripts/score_routing.py` |
| L1 检索 | 正确材料是否进入前 K，并排在前面 | 主：Recall@5、NDCG@5；辅：P@5、MAP@5、Hit@5；单篇定位题加 MRR@5；另报 @10 | 已知来源：`score_routing.py`；分级：`score_retrieval_run.py` |
| L2 回答 | 回答是否正确、有依据、引用对 | Faithfulness、Answer Correctness、Context Recall、引用精确率、Response Relevancy、正确拒答率 | `scripts/score_answers.py`（读 `answer_reviews.csv`） |

### 知名指标覆盖表

下列各来源列出的指标全部纳入；除 DCG 以 NDCG 代替外，均有脚本直接计算并有单元测试：

| 指标 | 出处 | 本项目实现 | 层 |
| --- | --- | --- | --- |
| Recall@K | Microsoft Azure、BEIR、Databricks | `score_retrieval_run.py` `recall`（R rel≥2）；已知来源版见 `score_routing.py` | L1 |
| Precision@K | Microsoft Azure、BEIR、Databricks | `precision`（P rel≥2） | L1 |
| MRR@K | Microsoft Azure、BEIR | `mrr`（RR rel≥2，截断在 K） | L1 |
| NDCG@K | BEIR、Databricks | `ndcg`（线性增益 0–3，log2 折扣），@5 与 @10 | L1 |
| DCG@10 | Databricks 主指标 | 不单独输出原始 DCG，用 NDCG@10 代替：NDCG = DCG／理想 DCG，同一排序、同一折扣，归一化后才能跨题平均 | L1 |
| MAP@K | BEIR | `map`（AP rel≥2 @K，分母为全部已知相关项） | L1 |
| Hit@K（Success@K） | 常用补充 | `hit`（前 K 至少一个相关） | L1 |
| Context Precision | Ragas | 近似：在 `generation_context` 阶段计算 MAP@K（相关片段是否排在送给模型的上下文前面） | L1/L2 |
| Context Recall | Ragas | `score_answers.py` `context_recall` = 上下文中能找到的必需要点／全部必需要点 | L2 |
| Faithfulness | Ragas | `faithfulness` = 有原文支持的陈述／全部可核查陈述 | L2 |
| Answer Correctness | Ragas、Microsoft Foundry | `answer_correctness` = 答对的封存要点／全部要点 | L2 |
| Response Relevancy | Ragas | `response_relevancy`，审阅者 0–1 打分 | L2 |
| Citation Correctness | Microsoft Foundry（Groundedness 相关） | `citation_precision` = 正确引用／全部引用；引文逐字核对由应用内置 | L2 |
| Query Routing Accuracy | 项目补充 | `score_routing.py` | L0 |

说明：Ragas 原库用 LLM 当评委自动打分；本项目用相同定义，由人审或 AI 辅助审填写计数，再由脚本计算，结果可复核。如需与 Ragas 原库交叉验证，可在隔离环境另跑一次（需联网安装并产生评委模型费用，运行前另批）。

- **P@5 的上限**：单篇来源题只有 1 个相关项，P@5 最高 0.2。P@5 只在多文档题有比较意义，单篇题看 MRR@5 与 Recall@5。
- **Recall 的分母**：只覆盖已标注的相关来源（已知来源或候选池），不是全库召回率，报告必须写明。
- **失败不删除**：未运行、报错、被拦截的题留在分母，记 0 分，并写明原因。

## 2. 题型分层

| 题型 `query_class` | 例子 | 预期路由 | 适用指标 |
| --- | --- | --- | --- |
| `title_lookup` 按标题查记录 | 标题为 “BP Supercomputer” 的广告的媒体、赞助方、日期 | `find_records` → `get_record_metadata` | L0、字段正确率 |
| `content_single` 单篇内容 | Enbridge 的 Politico 广告说什么应取代“能源或环境” | `search_records` | L0、Recall@5、MRR@5、NDCG@5、L2 |
| `content_multi` 多篇内容 | Total 关于 LNG 航运的广告（多个版本）说了哪些选项 | `search_records` | L0、Recall@5、NDCG@5、P@5、L2 |
| `cross_collection` 跨集合 | API 社交帖与华盛顿邮报广告分别说什么 | `search_records`（两个集合） | L0、每个集合分别 Recall@5、L2 |
| `statistics` 计数 | ExxonMobil LNG 账号 2023 年发了多少条帖子 | `record_statistics` | L0、数值与独立 SQL 一致 |
| `no_answer` 陷阱 | 只用 2031 年的广告总结氢能内容 | 先查集合范围，不得编造 | L0、正确拒答率 |

客户反馈的“内容题被送进标题检索”在 L0 里记为 `content_sent_to_title_lookup`，与排序问题分开统计。

## 3. 现有基线（离线复算，未调用模型，$0）

数据来自已运行的两套随机 18 题（P59 修复后完整一轮 `root_fix2`，R2 首轮 `root_r2`）的服务事件日志；修复前一轮 `root` 作对照。题目标签：`.runtime/rag_eval_test_20261008/p60_baseline/labels.json`。

| 轮次 | L0 首次路由正确 | 内容题已知来源 Recall@5 | MRR@5 | 内容题未找到来源的原因 |
| --- | ---: | ---: | ---: | --- |
| P59 修复前 | 8/18 | 0.25 | 0.21 | 9 题没有搜正文（6 题直接联网、3 题送去标题查找） |
| P59 修复后 | 17/18 | 0.71 | 0.65 | 3 题搜索被范围校验拦下，1 题跨集合只找到一半 |
| R2 首轮 | 15/18 | 0.67 | 0.62 | 3 题本机数据同步故障，1 题跨集合被范围校验拦下 |
| 两轮合计（修复后＋R2） | **32/36** | **0.69** | **0.64** | 24 道内容题：16 找到、1 找到一半、4 被拦、3 故障 |

**结论：只要搜索真正执行，已知来源就几乎都进了前 5（17 次中 16 次全部找到、1 次找到一半）。** 内容题的 8 次损失都发生在排序之前或之外：范围校验误拦 4 题、本机数据故障 3 题、跨集合只搜到一边 1 题。另有 4 题首次路由出错（2 题直接联网、1 题送去标题查找、1 题未调用集合工具），其中 2 题靠“先查集合”兜底搜索仍找到了来源。所以下一步先修 L0 与校验，再谈换检索器或调排序。

**分级排序基线（P59 12 道内容题，修复前的检索版本，AI 辅助分级标注，前 5 全部已判）**：

| 检索方式 | NDCG@5 | P@5 | Recall@5 | MRR@5 | MAP@5 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 关键词 | 0.68 | 0.28 | 0.73 | 0.78 | 0.66 | 0.83 |
| 向量 | 0.87 | 0.32 | 0.89 | 0.93 | 0.85 | 1.00 |
| 混合（应用实际选出） | 0.78 | 0.32 | 0.83 | 0.79 | 0.72 | 0.92 |

这组数据早于按集合分开检索与 HNSW 索引的修改，P60 会在新版本上重测同一批指标。

分题型（两轮合计）：内容单篇 16/20 路由正确、Recall@5 0.75；跨集合 3/3 路由正确但 Recall@5 0.50；统计 6/6；标题查找 2/2；陷阱 4/4。标题查找题只有 2 道，样本不足以下结论。

## 4. 下一轮 P60 设计

**题量 36 题**，按种子随机抽源，题目与标准答案在运行前封存，每题一次主要尝试。比前两轮增加标题题与多文档题，以便分别测 Title-based、Content-based、Multi-document：

| 题型 | 数量 | 说明 |
| --- | ---: | --- |
| `title_lookup` | 6 | 3 道给出准确标题，3 道给出标题片段 |
| `content_single` | 12 | 8 原生、4 社交；其中 4 道问题里带标题词但问正文内容（专测误路由） |
| `content_multi` | 4 | 同一主题有 ≥2 篇相关广告，测 Recall@5 与 P@5 |
| `cross_collection` | 4 | 原生＋社交各至少一篇 |
| `statistics` | 6 | 独立 SQL 参考值，含分时段比较 2 道 |
| `no_answer` | 4 | 空日期范围或不存在的主体 |

**分级标注（NDCG@5、P@5 需要）**：每道内容题取关键词、向量、混合三路前 10，加应用实际选出的前 5 与已知来源，打乱顺序、隐藏来源系统后按 0–3 分级（定义见[方法说明](retrieval_evaluation.zh-CN.md)第 3 节）。AI 辅助初标，人工抽查 ≥20%，未复核标签标明 `ai_assisted`。

**运行步骤**

1. 修复本机社交数据版本故障（见 `.coordination` 中 decision_needed）后再运行；否则社交题全部记为故障，结果无效。
2. 生成并封存题目：`questions_only.jsonl` 写入 SHA256。
3. 用全新私有测试库启动冻结副本（同 R2 流程），HTTP 提交 36 题，保存 `server/events.jsonl`。
4. L0 与已知来源 L1：
   ```powershell
   python scripts/score_routing.py --labels <P60>/labels.json --events <P60>/server/events.jsonl --out-dir <P60>/routing
   ```
5. 三路诊断检索＋分级标注后，导出到模板格式（`evaluation_cutoffs: [5, 10]`），用 `score_retrieval_run.py` 计算 NDCG、P、Recall、MRR、MAP、Hit 的 @5 与 @10，按题型分组；`generation_context` 阶段的 MAP 即 Context Precision。
6. L2 逐题审回答，写 `answer_reviews.csv`，运行 `python scripts/score_answers.py --reviews <P60>/answer_reviews.csv --labels <P60>/labels.json --out-dir <P60>/answers`。
7. 报告按“题型 × 层”成表，失败逐题列出原因。

**费用估计**：36 题问答约 $0.20–0.25（按前两轮每 18 题约 $0.10），三路诊断检索的查询向量 <$0.01，AI 辅助标注视方式另计；运行前需批准上限。

## 4.1 P60 实测结果（2026-10-09）

已按上述设计运行，$0.185，主库未动（故障前备份恢复到私有库）。详见 `.runtime/rag_eval_test_20261008/root_p60/README.zh-CN.md`。

- **回答**：36 题完全正确 28 题（78%），部分正确 4 题；Answer Correctness 0.84、Faithfulness 0.92、引用精确率 0.90；陷阱题 4/4 正确拒答。
- **检索**：应用选出的前 5 篇 NDCG@5 0.75、Recall@5 0.90、MRR@5 0.90、MAP@5 0.81、Hit@5 1.00；跨集合最弱（NDCG@5 0.60）。
- **路由**：首次路由正确 27/36，主要是过早澄清；未出现内容题误送标题检索。
- **新暴露的通用问题**：中文问题未翻译就搜英文语料；多时段统计计划被拒（R2 已知）；部分标题查找超步数；跨集合署名与选文错误。

## 4.2 P61 留出复测（2026-10-09）

按根因修复后，在新种子、排除前三轮来源的 36 题上复测，$0.155，主库未动。完全正确 30/36（P60 为 28/36）；首次路由 35/36（27/36）；应用前 5 NDCG@5 0.80（0.75）、MRR@5 0.93；引用精确率 0.95；陷阱 4/4。详见 `.runtime/rag_eval_test_20261008/root_p61/README.zh-CN.md`。复测后修复的 4 个根因与跨集合按账号过滤，待下一轮新题验证。

## 4.3 P63 新题验证（2026-10-09）

新种子 36 题，$0.166：完全正确 29/36；按标题查 6/6（含描述性标题）、单篇内容 12/12、陷阱 4/4。新暴露的跨集合账号与统计规划根因已修，失败 6 题回归全部答对。详见 `.runtime/rag_eval_test_20261008/root_p63/README.zh-CN.md`。

## 4.4 P64 新题验证（2026-10-09）

新种子 36 题：完全正确 30/36，首选路由 32/36，应用前 5 NDCG@5 0.863（仅封存来源计为相关，下限）。新增一条测前数据检查：运行 `scripts/audit_retrieval_quality.py`，`excluded_unique_prose` 列出被审查区间排除、但在保留正文中找不到的整句正文——这类记录的内容题失败属于数据问题，不应归因于检索或生成。详见 `.runtime/rag_eval_test_20261008/root_p64/README.zh-CN.md`。

## 5. 建议的通过线（待客户确认）

| 层 | 建议 |
| --- | --- |
| L0 路由 | 首次路由正确 ≥ 95%；`content_sent_to_title_lookup` 为 0 |
| L1 检索 | 搜索执行时已知来源 Recall@5 ≥ 0.90；NDCG@5 不低于 P59 混合检索基线 0.78；MRR@5 ≥ 0.80 |
| L2 回答 | 统计与字段 ≥ 90% 正确；内容题人审后 Answer Correctness ≥ 0.80、Faithfulness ≥ 0.95；陷阱题 100% 不编造 |

客户 24 题仍只作最终验收，不参与构题或调参。

## 参考

- Microsoft Learn：RAG 信息检索评估（Precision@K、Recall@K、MRR）。
- BEIR 基准：NDCG@K、MAP@K、Recall@K、Precision@K。
- Databricks：检索质量评估，按业务目标选指标。
- Ragas：Context Precision／Recall、Faithfulness、Response Relevancy，检索与生成分开评估。
