# 问答查询逻辑（代码级说明，2026-10-23 本地版本）

本文说明一个问题从输入到回答的完整过程。依据的是本地工作版本：分支 `codex/fa26-observatory`，含未提交改动。

- 行号写作 `文件:行`，文件都在 `src/observatory/` 下。
- 文中的"本地"指项目 `.env` 的配置：`OBS_RESEARCH_AGENT_ENABLED=true`、问题意图解析关闭、答题规范文件存在。
- 内容由四路逐行阅读汇总而成，关键处已回到代码核对。标【未核实】的地方没有运行验证。

---

## 0. 一页看懂

```
用户提问（网页按钮 或 POST /api/v1/ask）
  └─ Service.answer                         service.py:751
       ├─ 研究代理开着 → _answer_with_tools  service.py:916   ← 本地走这条
       │     └─ ResearchAgent.run：模型最多 4 步，每步必须调用 1 个工具，由调用的工具决定"路线"
       │          ├─ 统计路线 → 直接查数据库算数，不调生成模型
       │          ├─ 元数据 / 单条记录 / 来源 / 图谱 / CLAIMS 路线 → 读库后直接组织回答
       │          └─ 证据路线（内容类问题）→ _answer_evidence   service.py:1867
       │                ├─ 重新检索：关键词 + 向量 + 标题，用 RRF 融合
       │                ├─ 名单题 → 每 4 篇一批让模型判断"符合 / 不符合 / 不确定"，每个"符合"必须附原文句子
       │                │      └─ 再由写作模型写要点（6 篇）或逐篇描述（12 篇）
       │                └─ 普通题 → Rag.generate：模型只能从给定段落挑引文，服务器逐字核对
       └─ 研究代理关着 → _answer_legacy（旧路径，规则判断统计题，其余直接走 _answer_evidence）
  └─ 答不出（insufficient_evidence）且没说"只用馆藏" → 可选的网页补充
```

一个问题可能花钱的模型调用有四类：

| 用途 | 模型 | 推理强度 | 位置 |
|---|---|---|---|
| 研究代理规划 | `gpt-5.6-luna` | none，输出上限 900 token | research_agent.py:669 |
| 检索词向量 | `text-embedding-3-small`，1536 维 | — | rag.py:629 |
| 名单逐篇筛选 | `gpt-5.6-luna` | low | list_screening.py:295、330 |
| 写回答 | `gpt-5.6-luna` | none，输出上限 1600 token | rag.py:873-884 |

---

## 1. 入口

### 1.1 网页上的 "Generate answer"（app.py）

1. 输入框 `research-question` 最多 2,000 字（app.py:2035-2043）。范围单选 `search-scope` 有两个值（app.py:2063-2079）：
   - `current`：当前集合及其筛选，默认值；
   - `all`：两个集合的全部记录。
2. 访客 id 存在 session cookie 里，为空时生成 `secrets.token_urlsafe(24)`（app.py:1934-1939）。
3. 回调 `research`（app.py:2979-3023）把问题、范围、集合和三套筛选交给 `run_research`（app.py:3025-3098）。
   - 问题为空或超过 2,000 字：提示重新输入。
   - 选了 `all`：直接用 `Filters(dataset="all")`，**界面上的其他筛选全部丢掉**。
   - 选了 `current`：由 `_filters` 拼出 Filters（app.py:431-449）。dataset 为 all 时，只要选了媒体、平台、标签、账号等集合专属筛选就报错。
   - 点 "Generate answer"：调用 `service.answer(question, filters, visitor, progress=…)`。
   - 出现任何异常：退回免费关键词搜索，并提示 "Answer service unavailable"。
4. 进度条每 600 毫秒轮询一次。阶段名有 interpreting、database、media、web、organizing、citations（query_progress.py:16-23）。

### 1.2 接口 `POST /api/v1/ask`（api.py:271-285）

1. 请求体只允许 `question`（1–2,000 字）和 `filters`。不传 `filters` 时默认 `{"dataset":"all"}`。注意：传空的 `{}` 时会用模型默认值 `native`（models.py:103）。
2. 访客 id 的取法（api.py:120-126）：有 `X-Visitor-Id` 头就用 `api:<头的值>`，否则用 IP 加浏览器标识算出的哈希。这个头由客户端控制，换个值就能绕开按人限流。
3. 被限流时返回 HTTP 429。每条引文会补上 `location`（在原文中的位置），默认输出精简版，不带 `research_trace`。

### 1.3 筛选条件 Filters（models.py:102-125）

| 字段 | 说明 |
|---|---|
| dataset | native / social / all |
| 列表字段 | publishers、sponsors、platforms、accounts、keywords、labels、record_ids |
| replies | 只在 social 有效 |
| 日期 | `date_from`、`date_to`、`include_unknown_dates`（默认 True）、`date_presence` |
| include_inferred_dates | 模型默认 False。但 `Service._answer_question` 在调用方没显式设置时改成 True（service.py:758-759），所以网页提问一律用推断日期补齐缺失日期 |

筛选转成 SQL 的规则（`Database.where`，db.py:335-395）：

- 固定条件：记录 active 且可计数。
- 名称类字段按存储值精确匹配，空值算作 "(Unknown)"。
- 日期取 `published_at`；打开推断日期时，用可用的日级推断日期补上。

---

## 2. 选路线

### 2.1 外层（service.py:751-774）

1. `answer` 先把该访客的"进行中问题数"加 1（`QUESTIONS.question`），见第 8 节。
2. 研究代理或问题意图解析任一打开，走 `_answer_with_tools`；否则走 `_answer_legacy`。**本地走前者。**
3. 结束时：
   - `_ensure_answer` 判断是否需要网页补充（第 9 节）；
   - 写入 `latency_ms`；
   - `_save_supplement` 把问答写进 `answer_runs` 表。这只是审计记录，**没有答案缓存**，同一个问题每次都重新算。

### 2.2 工具路径 `_answer_with_tools`（service.py:916-1067）

1. 先调 `health()`，必须拿到数据版本 `data_version`，否则返回 service_unavailable。
2. 新建研究代理：`ResearchAgent(rag, ToolCatalog(self, filters), max_output_tokens=900, repairs=1)`，最多 4 步、4 次工具调用（research_agent.py:565-585）。
3. `agent.run(...)` 返回一条路线 `run.route`，service 按路线分发（service.py:947-994）：

| 路线 | 由哪个工具触发 | 之后怎么处理 | 花钱吗 |
|---|---|---|---|
| statistics | record_statistics | `_tool_statistics_answer`：数据库直接算数 | 只花规划费 |
| evidence | search_records | `_answer_evidence`（第 4 节起）**重新检索并生成** | 要花 |
| metadata | get_record_metadata | 返回原始表格里的字段 | 只花规划费 |
| record / sources / graph / claims | get_record / get_record_sources / get_graph_neighborhood / get_claims_matches | 直接组织结果 | 只花规划费 |
| composite | 2–3 个子任务都完成 | 逐个回答，其中的内容部分同样走 `_answer_evidence` | 视情况 |
| clarify | request_clarification 或校验失败 | 返回 insufficient_evidence 和一句澄清 | 只花规划费 |
| limited | 预算或次数用完 | status="limited" | — |

4. 兜底（service.py:995-1015）：结果是 clarify 或 composite、答不出，而且不是只问原始字段、也没调过统计，就用模型最后写的英文检索词（没有就用原问题）再跑一次 `_answer_evidence`。答出来了就替换原结果。
5. 读完再查一次 `data_version`。数据在这期间变了，就返回 `data_changed_during_tool_research`。

### 2.3 旧路径 `_answer_legacy`（service.py:1454-1543，本地不用）

依次判断：

1. 只问原始字段，或一句话里有多个任务：拒答。
2. 问题正好是 "how many records" 等 6 句之一：直接计数。
3. `plan_question` 用正则识别 "how many … ads"、"what percentage of …"、"which publishers/sponsors …" 等句式：数据库计数，不调模型。
4. 含 how many / count / percentage 但识别不了：拒答，并说明支持哪些计数。
5. 其余问题：`_answer_evidence`。

---

## 3. 研究代理怎么决定（research_agent.py:778-1281）

### 3.1 先用规则给问题贴标签：`question_contract`（question_policy.py:903-949）

先把弯引号换成直引号、合并空白、去掉引号里的字面量，再按下表判断：

| 标签 | 规则（大意） |
|---|---|
| task | 按顺序判断：disclosure（disclose、披露、广告标识……）→ content_framing（present、position、portray、claim、describe、say、声称、强调……）→ content_mentions（mention、refer to、discuss、提及……，或 "ads about …"）→ content_unspecified（"which … ads" 后面还有不属于存储字段的词）→ 否则 metadata_or_unspecified |
| requires_complete_list | 有内容条件，**并且**句式是 "which … ads"、"list/show/find … ads"、"every/all … ads" 或 "哪些/所有…广告"。注意 "How do ads describe X?" 不符合，这一项为假 |
| content_search | 含 says/describe/explain/mention/how does/说/描述/如何 等内容动词，并且不是计数、分组、披露、原始字段问题 |
| compound_read_request | 一句话里有多个读取请求，例如 "… and how many …"，有若干豁免 |
| original_metadata_only | 同时提到"原表格、Excel、保存的"和"标题、日期、链接"等字段 |
| explicit_datasets | 问题里点名了 native ads / social posts / 两个集合 |
| quoted_title | 有引号或《》包住的标题 |

这些标签放进发给模型的消息里，也决定每一步模型能用哪些工具。

### 3.2 每一步

1. **发给模型的内容**：
   - system 是 `prompts.RESEARCH_SYSTEM`，共 10 节。规定内容题只调一次 `search_records`，检索词改写成英文，并说明社交帖和广告的数量比约 130:1。
   - user 是一个 JSON：问题、当前范围、上面的标签、实体名称上下文（最多约 6,000 字节）、参考日期。
2. **调用方式**：`responses.create(tool_choice="required", parallel_tool_calls=False, reasoning none, max_output_tokens=900)`，所以每步**必须且只能**调用 1 个工具。
   - 调用前输入不能超过 60,000 字节。
   - 按估价的 1.25 倍预留预算（research_agent.py:636-704）。
3. **本步开放哪些工具**（`_step_definitions`，research_agent.py:272-326）：
   - 内容题（content_search）只开放 `search_records`、`resolve_entity`、`request_clarification`；
   - 多任务题必须先调 `set_research_plan`；
   - 原始字段题只开放查记录和查元数据。
4. **执行前的检查**（research_agent.py:936-1090），任何一项不过，要么给模型一次修正提示，要么直接 clarify：
   - 问题点名的集合，工具参数里必须对上；
   - 有内容条件的问题不能调统计工具；
   - 统计请求不能丢掉问题里的条件（年份、分组、占比……）；
   - 检索词以中日韩字符为主时，退回让模型改成英文，因为库里正文是英文；
   - 问题里以来源身份出现的公司或账号（例如 "ExxonMobil's ads"）、以及唯一的过去时间段，会自动补进筛选（`_complete_search_scope`）；
   - 模型填了问题里没出现的公司或媒体名：先退回一次，再不改就 clarify。
5. **执行工具**：`ToolCatalog.call`（research_tools.py:800-893）。
   - 先校验参数。
   - 用 `narrow()` 把模型给的筛选和用户原来的范围取交集，**只能缩小，不能扩大**。
   - 执行前后各查一次数据版本。
6. **结果处理**：
   - 调用的是终结工具：路线就此确定，没有多任务计划时立即结束。
   - 调用的是中间工具（resolve_entity、find_records、get_graph_schema）：结果作为函数输出回填给模型，进入下一步。
   - 4 步内没有结束：返回 `research_step_limit`。
7. **证据路线带给下一阶段的东西**：
   - 模型写的英文检索词 `search_query`；
   - `answer_shape`，即模型声明的回答形态，例如 `every_matching_source` 表示"列出所有符合的来源"；
   - 收窄后的筛选；
   - 可选的 `retrieval_groups`（对比题的 2–3 组）。

   **代理在这一步用 `search_records` 查到的段落只用于判断，不用于写回答。** 写回答的证据在第 4 节重新检索。

---

## 4. 证据检索 `_answer_evidence`（service.py:1867-2075）

### 4.1 先决定按什么形态回答（service.py:1896-1911）

- `wants_list` = 规则判定是名单题（`requires_complete_list`），**或**代理声明 `answer_shape == "every_matching_source"`。
- `list_mode`：wants_list，并且 dataset 是 native 或 social。
- `both_list`：wants_list，并且 dataset 是 all，没有 labels。此时两个集合**分别**筛选（第 6.5 节）。
- 其他问题按普通题生成（第 5 节）。

> 规则对 "How do ads describe X?" 判不出名单题。这类题能进名单路径，靠的是代理声明了 every_matching_source。10 月 22 日测的 6 个主题题全部进了名单路径。

### 4.2 取候选

1. 问题里出现了某篇广告的完整标题（规范化后至少 20 字），就把范围收窄到这篇（service.py:1918-1920，`_title_scope`）。
2. 先跑一遍纯关键词检索作保底，每组 5 条（对比题 3 条）。拿到向量结果后清掉。
3. 为整个问题预留 **$0.04**（service.py:1970-1975）。这是第一次计入访客的问题次数。
4. 用 `Rag.embed` 给检索词算向量（rag.py:629-677）：
   - 先用 `sha256(文本)` 加模型名查 `embeddings` 表，命中就不花钱；
   - 没命中才调 OpenAI，并写回同一张表。所以同一个检索词再问一次就不收费。
5. 调用 `db.search(检索词, 范围, vector=向量, chunks_per_record=…, limit=…)`，取多少由下表决定：

| 情况 | limit（记录数） | 每条记录最多几段 |
|---|---|---|
| 名单题 | `MAX_WIDENED` = 120 | 2 |
| 对比题每组 | 3 | 3 |
| 范围很小（有公司、媒体、账号、记录或日期筛选，记录数在 6–30 条） | 范围内全部记录 | 3 |
| 其他 | 5 | 3 |

6. 非名单题把证据截到 **30,000 字符**，从排名靠后的开始丢（`_fit_evidence_budget`，service.py:73-87）。
7. 检索前后数据版本变了就报错。

### 4.3 `db.search` 内部（db.py:1296-1446）

1. **分词**：`[\w-]+`，转小写，去掉 20 个停用词（what、which、how、the、of、about、say 等）和单字符，最多保留 40 个词。
2. **dataset 为 all 时，原生和社交各跑一遍全部通道**（db.py:1352）。不这样做的话，社交帖数量约是广告的 130 倍，会把广告淹没。
3. 每个通道取 `max(50, 2×limit)` 行。整个检索在一个只读快照事务里完成。四个通道：
   - **关键词**：Postgres 英文全文检索。`search_vector @@ websearch_to_tsquery('english', "词1" OR "词2" …)`。排序先看"命中了几个不同的检索词"，再看 `ts_rank_cd`。
   - **向量**：pgvector 余弦距离。
     - 原生走精确扫描。
     - 社交和 all 先用 HNSW 索引取全局最近的 400 个（`ef_search=400`），再按范围过滤；不够时退回精确扫描。
   - **标题**：只查原生。标题命中至少 2 个检索词才算，最多 20 条。
   - **字面兜底**：只在前三个通道都为空时启用，只查社交，`strpos(lower(text), lower(问题))`。
4. **融合（RRF）**：每个通道给排在第 r 位的段落加 `1/(60+r)` 分，同一段在多个通道出现就累加。四个通道权重相同。
5. **选记录**：两个集合按融合后的顺序**轮流**取记录，凑满 `limit` 条。一方不够时名额让给另一方。每条记录保留 `chunks_per_record` 段。
6. **只读当前版本**（db.py:1280-1294）：`chunks JOIN records ON r.current_version = c.version_id`，并且只取当前激活的检索方案（`sentence600-social-observations-v1`）的段落。
7. **社交帖再核对一次**（`bind_search_row`，social_source_binding.py:55-85）：段落所属的采集记录必须和当前版本的载荷一致，文字必须逐字等于原文对应区间，否则这一段作废。10 月 9 日社交检索失效，就是卡在这一步。

### 4.4 检索块（chunk）是什么（chunking.py、indexing.py）

- 每块最多 600 token、重叠 100 token，分词器是 `cl100k_base`，尽量按整句打包（pysbd 分句）。
- 原生广告按正文切分。社交帖按**每一份采集到的原文**分别切分。
- 只切可检索的记录。正文里被排除的区间不切。
- 每块记录它在原文中的精确起止字符位置，所以引文能定位、能高亮。
- 向量用块的原文直接计算，不加标题或公司名。
- 现在共 37,708 块，全部有向量。

---

## 5. 普通题：生成回答并逐字核对（rag.py:697-963、1006-1110）

### 5.1 准备

1. 没有证据：不调模型，直接返回 insufficient_evidence。
2. 每条证据都要核对：版本仍是当前版本、文字等于原文对应区间（`db.validate_evidence`）。不过就报错。
3. **建引文目录**（`answer_quote_catalog`，rag.py:421-439）：
   - 同一来源相邻的段落合并成连续文本；
   - 按句子切成**不超过 60 词**的可引用片段，60 词窗口、步长 45，即相邻片段重叠 15 词；
   - 依次编号 `Q1, Q2, …`；
   - 每个片段附上上下文：前后片段编号、是否从句首开始或到句末结束、是否把句子截断了。
4. **证据清单**：本次提供了多少记录、来源、片段，编号为 R1… 和 S1…。并明确写明这只是这一次检索到的范围，不是全库统计。
5. **system 提示词**依次拼接：
   - `prompts.ANSWER_SYSTEM`（11 节，见 5.4）；
   - 答题规范中的 general 规范：只在问题不是"哪些/列出…广告"句式时附加，内容是"先概述，再列举"；
   - 有社交帖时的规则：按具体某次采集归属，公司帖子不等于付费广告；
   - 需要时附加"每个来源一条结论"、"优先引用问题所问时间段内的来源"、"必须用 X 语言回答"。

### 5.2 调用模型

- `responses.parse(..., text_format=<结构>, reasoning none, max_output_tokens=1600, store=False)`，没有重试（客户端 `max_retries=0`）。
- 输入估算超过 100,000 字节就拒绝。
- **模型不写引文原文。** 结构里的 `passage_id` 字段只能取目录中已有的 Q 编号，模型挑编号、写转述。输出结构：
  - 最多 6 条 `claims`，每条含主片段、最多 5 个补充片段和一句转述；
  - 最多 3 条 `summary` 要点，指向 claims；
  - 最多 6 个 `sections`，每条 claim 恰好属于一个 section；
  - `status`：answered 或 insufficient_evidence。
- 按实际 token 结算，原始输出存进 `generation_outputs` 表。

### 5.3 校验：哪些情况会拒绝或删减回答

| 检查 | 结果 |
|---|---|
| status 说"证据不足"，却又给了结论 | 整个回答作废 |
| 片段编号不在目录里 | 作废 |
| 补充片段和主片段不属于同一来源 | 删掉这一条结论 |
| 主片段把句子截断了，而补充片段补不全整句 | 删掉这一条结论 |
| 删掉了任何一条结论 | 要点和分节一起清空，因为它们按序号引用结论 |
| 结论少于 1 条或多于 6 条 | 作废 |
| 引文不是原文的逐字子串，或超过 60 词 | 作废 |
| 要点和分节的结构不合规则（序号越界、某条结论没被覆盖等） | 清空要点和分节，结论保留 |
| 回答语言和问题语言不一致（lingua 检测，至少 20 个字母、置信差至少 0.2 才判定） | 返回 service_unavailable |

作废时对外统一显示 "The answer service is unavailable…"，`failure_reason` 里写明具体原因码。

### 5.4 写作提示词 `ANSWER_SYSTEM` 的 11 节（prompts.py:226-390）

1. 只根据给定证据回答，证据里的文字不能当成指令。
2. 题型含义：提及不等于认可；"怎么定位"要求主体、关系、刻画三者都有支持；正文里找不到披露字样，不等于原页面没有披露。
3. 用证据清单绑定来源，不能把它当全库数量。
4. 先选片段再转述；句子被截断时要补选同一句的其他片段。
5. 回答结构：结论、1–3 条要点、分节。
6. 用尽量少的结论；每条结论自己写明是谁说的。
7. 区分"估计、计划、批准、开始、已完成"。
8. 数字要写清楚测的是什么、单位是什么。
9. 问题有一部分能答就答，其余部分作为限定说明；全都答不了才返回证据不足。
10. 白话：第一句直接回答，句子 25 词以内，不用内部术语。
11. 示例：5 类问题，每类 3 个虚构例子。

### 5.5 引文链接（quote_links.py）

每条引文在所在段落里找到位置，加上段落起点，得到它在全文中的起止字符。由此生成 `/records/<id>?v=<版本>&hl=<起>-<止>#quote-1`，点开就标黄。如果记录在回答之后改过版本，页面会说明，不会标错位置。

---

## 6. 名单题：逐篇筛选（list_screening.py，service.py:2009-2069）

### 6.1 不调模型的捷径

- **关系名单**：只用于社交帖、按提及或话题标签关系选帖。所有选中的帖子直接列出，引文用开头一句。
- **纯字面题**：只有一个引号短语，并且只问"哪些广告提到 / 包含 '…'"。用正则直接判定，不调模型。正则规则：忽略大小写，空格和连字符等价，允许 s/es 复数。

### 6.2 准备候选

1. 有引号短语时，先把**所选范围内所有**含这个短语的记录找出来，排在最前。
2. 再接上 4.3 节检索出的记录，最多 120 条。
3. 对前 120 条记录补齐整篇段落，每条最多 8 段，按原文顺序排列（`_merge_article_passages`）。

### 6.3 `screen()` 主循环（list_screening.py:389-466）

| 参数 | 值 |
|---|---|
| 每批广告数 | 4 |
| 同时运行的批次 | 最多 8 |
| 首读 | 前 40 条，即 10 批 |
| 扩展上限 | 120 条 |
| 扩展停止条件 | 最近 16 条判断里一个"符合"都没有，就停止扩展；已发出的批次照样计费 |

1. 首读前 40 条，之后每波 8 批，也就是 32 条，向后扩展。
2. **重读**：首轮判为"不符合"或"不确定"、而且整篇还有没看过的段落的记录，取回全文再判一次，以第二次为准。每批最多 4 条，总字数不超过 40,000 字符。
3. **复核**：默认关闭（`VERIFY_LISTED=False`）。在封存题上，它删掉了 10 个错误条目，也删掉了 8 个正确条目。

### 6.4 一批怎么判（`_judge`，list_screening.py:251-280）

1. 发给模型的内容：问题，以及 4 篇广告，每篇带标题、媒体、赞助方、日期和编号段落（`A1.1`、`A1.2`……）。有引号短语时，另外附上含该短语的整句。
2. system 规则（list_screening.py:48-57）：
   - 判为"符合"时必须**逐字抄一句**支持句（最多 300 字符）并给出段落编号；
   - 只提到话题，不等于满足"怎么定位"类条件；
   - 计划不等于成就；
   - 引号短语必须字面出现。
3. 两种调用方式：
   - **有答题规范时**（本地默认）：用私有模板，要求模型先在 `<think>` 里写推理、再在 `<answer>` 里给 JSON（`_judge_tagged`）。JSON 解析失败就退回第二种方式再调一次，两次都计费。
   - **没有规范时**：结构化输出 `Batch{decisions:[{ref, decision ∈ matches / does_not_match / unclear, passage_id, quote}]}`。
4. **服务器核对引文**（`_checked_results`，list_screening.py:208-245、350-364），只要有一项不过，就把"符合"改成"不确定"：
   - 段落编号必须属于这篇广告；
   - 引文规范化后（统一弯引号、破折号和空白），必须是该段落或同篇其他段落的子串。还找不到时，再试忽略空白的匹配，要求至少 12 个字符；
   - 问题里有引号短语时，引文必须包含这个短语。
5. 最后存下来的引文**取自原文**，不是模型抄的文字。

### 6.5 两个集合一起筛（`_screen_both`，service.py:1611-1674）

原生和社交各自取候选、各自首读 40 条、各自扩展到 120 条，两边并行。显示时社交至少占一半名额，原生不够时把名额让出来。

### 6.6 筛完之后怎么写

开头一句由服务器生成。例如："Checked the 120 most relevant of the 263 native ads and the 120 most relevant of the 36,182 company social posts: found 107 matching ads and 110 matching posts."

1. **问"这些广告怎么说"**：判断函数是 `sources_content_request`，匹配 what do … say、how do … describe/explain/discuss/present、说了什么、如何描述等。
   - 取前 12 条符合的记录，每 4 条调一次写作模型，要求每个来源写一条结论（`_read_matched_sources`）。
   - 写作模型没写到、或只读了部分内容的记录，在结尾加一句"N of the M matching ads were only partly read…"。
   - 其余符合的记录放在 "Other matching ads (screening quote only)" 下，只显示筛选时的引文，最多 10 条。
2. **其他名单题**：取前 6 条符合的记录，让写作模型写要点（`_summarize_list`），然后列出前 10 条，其余只计数。
3. 符合 3 条以上时，附上按赞助方、年份、媒体统计的柱状图。数字全部来自数据库字段，不经过模型（`list_charts`）。
4. 名单题**不做**网页补充。

---

## 7. 答题规范（answer_norms.py）

- **加载**：先看 `OBS_ANSWER_NORMS` 是否为 off；再看 `..._B64`；再看 `..._PATH`；都没有就读默认的 `config/private/answer_norms.json`。文件不存在或格式错误时，行为和没有规范完全一样。
- **题型判断**（只看第一个问号之前的部分）：
  1. 含 disclos 或 "labelled as sponsored" 等：disclosure；
  2. 不是以 which/what/list/find/show 开头并提到 ads/posts/articles 的句子：**general**；
  3. 提到 "the/its sponsor"：sponsor_claim；
  4. 含 present/position/frame/claim/promote 等：framing；
  5. 含 mention/refer/discuss/include 等：mention；
  6. 都不是：general_list。
- **筛选时**用该题型的规则和 3 个示例。没有示例的题型只用规则。
- **写回答时**：只有 general 题型附加"先概述再列举"。

---

## 8. 费用与限流（budget.py）

1. **价格**（每百万 token）：
   - `gpt-5.6-luna`：输入 $0.20，缓存读取 $0.02，缓存写入 $0.25，输出 $1.20；
   - `text-embedding-3-small`：$0.02；
   - 其他模型直接报错。
2. **每次调用前预留**：估算金额的 1.25 倍。写入一条 `usage_ledger` 记录，状态为 pending，180 秒后过期。
3. **检查顺序**：
   - 本月已花（包括未结算的预留）加上本次预留，超过 `monthly_budget_usd`（默认 $100）就拒绝。这条对向量计算也生效。
   - **按问题计次，不按模型调用计次**：一个问题里不管调多少次模型，只算 1 次。每个访客每分钟 5 次、每天 30 次；全站同时进行的付费问题最多 2 个。计数只存在内存里，重启后清零。
4. **调用后**：
   - 成功：按实际 token 结算（settled）。
   - 出错：标为 uncertain，**预留的钱不退回**。
   - 确定没发出去：取消（cancelled），记 0 元。
5. **被限流时**：网页显示 "Your question limit or the API budget has been reached"，接口返回 429。

---

## 9. 网页补充（service.py:776-856、2160-2164）

触发条件，全部满足才会执行：

- 回答是"证据不足"，或原始元数据只拿到一部分；
- 问题没有说"只用馆藏 / 仅根据所选"（`_COLLECTION_ONLY`）；
- 不是名单题；
- 不是限流或故障；
- 不是 citation_mismatch 等 12 种受保护的失败；
- `web_search_enabled` 为真。注意这个开关的代码默认值是 False，但从环境变量读取时默认是 true。

补充成功时，`answer_mode="web_supplement"`，正文开头会说明馆藏答不了，列出网页来源，并标明"馆藏任务仍未完成"。

---

## 10. 已发现的问题（读代码时确认）

1. **主题分析题被当成名单题。** "How do ads describe/discuss X?" 只要代理声明了 `every_matching_source`，就进入逐篇筛选，结果是"找到 107 篇"加逐条罗列，题目里的追问（有没有、多常、是否）没有正面回答。10 月 22 日测的 6 题就是这样。
2. **【我写的 bug】这类题筛选时用错了规范。** `screening_prompt` 按题型取规范（answer_norms.py:112）。"How do ads…" 被判为 general，于是取到 general 的规范。这条规范是写作用的"先概述再列举"，不是筛选规则。本应退回 general_list。
3. **覆盖上限。** 每个集合最多读 120 条；"怎么说"类题只详细描述前 12 条。气候题 217 条符合，只详细写了 9 条。
4. **trace 记录与实际不一致。** 两个集合一起筛时，trace 里 `first_read` 固定记为 40（service.py:1667），和单集合的写法不同。只影响记录，不影响结果。
5. **接口的访客头可伪造。** 改 `X-Visitor-Id` 就能绕开按人限流，但月度总预算仍然有效。
6. **向量候选会被问题向量占名额。** 社交向量检索先从整张 `embeddings` 表取最近的 400 个，问题向量也存在这张表里，会占掉一部分候选。这是推断，没有实际测量。
