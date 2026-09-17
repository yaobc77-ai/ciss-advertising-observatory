# 分块、检索与评价迁移审查

2026-09-16，只读源码/题库检查；未调用模型、embedding 或写数据库。以下行号基于审查时 0.2.5 文件，项目根目录为 `D:/Projects/549 native ads`。

## 1. 首要难点：改函数不等于更新索引

- `src/observatory/db.py:67–71` 用整个 `RecordInput` payload 的 JSON 哈希计算 `version_id`，不包含 chunker 代码/配置。`:80–86` 发现版本相同就直接 `continue`，不会重新分块。因此只改切分函数再运行 import，旧记录仍会 unchanged。
- 仅改 `chunk_body` 默认值连空库都不够：`src/observatory/chunking.py:143–146` 的 wrapper 自己默认 600/100，并在 `:160–161` 显式传入；`db.py:107–111` 没有分块参数入口。
- `db.py:115–117` 的 chunk ID 是 version/start/end 哈希，插入 `ON CONFLICT DO NOTHING`。`schema.sql:16–28` 没有独立 chunk/index generation。绕过 unchanged 并在同版本直接追加，会混合两种切法；删除旧块会破坏保存的引用。
- `db.py:203` 的 `data_version` 只聚合活动 record 的 current_version，不感知 chunk 集合变化。`evaluate.py:165–168` 的版本检查和模块哈希记录不能证明数据库索引由该次模块产生。

**结论：先做内存派生分块＋只读 SQL 评分的隔离比较，不把调参变成主库迁移。** 如果将来采纳新切法，需要显式记录索引配置/版本及一次原子发布；不能改正文哈希冒充原文变化，也不能清理掉旧引用依赖的块。

## 2. 当前检索具体做了什么

| 层 | 代码证据与当前行为 | 对比较的影响 |
|---|---|---|
| 元数据范围 | `db.py:140–180`：active/countable、dataset、record IDs、媒体、赞助方、平台、关键词、日期/未知日期、当前版本历史标签 | 保持相同 SQL 范围，不能用模型/关键词代替结构化条件。 |
| 标题限定 | `service.py:126–141`：完整标题规范化后不少于20字符，且是问题的子串，才在现有筛选内收窄 record IDs | 是确定性标题限定，不是通用实体解析；含完整标题的题与开放检索题应分开解释。 |
| 词项检索 | `schema.sql:21` 仅正文生成 English tsvector；`db.py:233–270` 提取词项、去固定停用词、OR 查询、`ts_rank_cd` 前50块 | 不是 BM25；标题/赞助方未拼入全文索引或 embedding。中文词项不自动翻成英语，中文对照只能测真实边界。 |
| 向量与融合 | `db.py:273–289` cosine 精确查询前50块，与词项排名用 RRF `1/(60+rank)` 融合 | 无外部 reranker；不能把纯词项比较称完整 hybrid。 |
| 文档与块选择 | `db.py:291–307` 先取前5个不同记录，再每记录限块并按原文 start 排序 | `limit=5` 是记录数，不是块数；小块可能挤占同篇限额。 |
| 免费/付费差异 | `service.py:118–123` 免费每记录默认1块；`:197–207` 付费先查询 embedding、每记录最多3块 | 比较必须固定并记录限块政策，避免同时改检索模式或上下文预算。 |
| 分句所在层 | `rag.py:72–110` 已有 pySBD 等长空白视图/硬段落页界；`:113–126` 用于返回块内的60词短引文 | 它不能补回检索块外半句。可以复用 pySBD 和原字符映射机制，不照搬60词引文限制为检索块大小。 |

重叠去重/合并也应单独实验：只能对同 record、version、同一个 retained interval 的连续原文范围处理。跨删除间隙拼接会造出不存在的引文。将多块合成新 Evidence 后，现有 `db.validate_evidence` 不认识这个未入库 ID；最小初步方案是报告重复区间比例、保留各原证据身份，不冒充已持久化合并块。

## 3. 现有评价能复用什么

- `evaluate.py:79–91,103–143` 已有题库解析、完整筛选集合和 gold 原句/范围校验。Gold 必须完整位于一个 accepted interval；导航两侧不能拼成一句。
- 默认 `evaluate.py:269–291` 只调用免费检索；支持句覆盖的含义是**完整 gold quote 出现在某一个返回块中**。同一句分散在两个块，当前指标仍记未覆盖。保留该原指标，再单列区间并集覆盖或重复率，不能悄悄改评分让新切法赢。
- `evaluate.py:272–275` 的 Hit@5 是所有 required records 是否均在前5个不同记录中；计数题直接 SQL 全集合，不能被 chunk 数改变。
- `docs/evaluation_protocol.md:3–22` 明确两组各20题、13 ready/7 pending。开发题多次用于修复，验收草案尚未冻结且来源重叠，二者都不构成未见文章泛化证明。
- `eval/pdf265_recovery_smoke.jsonl:1–2` 显式指定单篇 record_id，是两题分句/归因 smoke，不可当独立开放检索集。
- `required_record_ids` 和支持句只进入评分，搜索仍只接问题与显式 filters。不要把 gold ID 塞入原无该筛选的题。中文翻译对照应另标成配对诊断，不称新的独立题目。

## 4. 最小实施方案

1. 从一个 PostgreSQL `REPEATABLE READ READ ONLY` 快照读取当前原文/payload和筛选集合；只读连接强制设置，禁止回落到可写连接。复用 `load_cases`、`load_snapshot`、`validate_gold` 和现有 `Database.where`。
2. 保留旧切法作为 legacy；候选为 legacy 300/400/600、sentence 600。单位是 `cl100k_base` tokens，显式 overlap=100。同一来源、范围和查询不变，记录 strategy/算法版本/代码哈希/参数；sentence600与legacy600用于隔离句界变化。
3. 派生块只在内存，借 `jsonb_to_recordset` CTE 执行当前 English OR/ts_rank 排名和同样的 RRF/记录限块规则。无需临时表、重导主库、改 source version 或删除当前558块。
4. 开发集与 PDF smoke 分开输出。返回 Hit@5、完整支持句覆盖、原文坐标有效率、返回 token 数、区间重复比例、候选块数和耗时；保留逐题失败。另报告标题限定是否生效与实际筛选规模。
5. 本阶段不调用生成或 embedding。可按新 text_hash 查询旧 embedding cache 的覆盖率；缺向量时只能报告未测 hybrid，不能用旧块向量顶替新块，不能对不同候选使用不等覆盖的部分向量结果宣称优劣（`rag.py:185–245` 缺缓存会付费生成）。
6. 比较后再决定是否值得做完整向量/回答阶段和发布迁移。长期迁移应显式索引代次并保留旧记录/块；无需为首轮研究先扩展生产 schema。

可复用 `scripts/verify_clean_import.py:85–112` 的专用库防误连模式，但不要原样运行其清库/固定558块验收，它仅为固定快照复现。此次只读 CTE 比较比反复清空测试库更小。`Service(settings,db=...)` 已支持注入仓库（`service.py:64–67`）。

## 5. 必须保留的历史引用约束

- `db.py:310–324` 校验的是原保存 chunk_id、record_id、version_id、start/end、body切片及存储text的完全一致；它刻意不要求旧块仍属 current_version。
- 现存 `answer_runs`、`generation_outputs` 通过 JSON 保存引用（`schema.sql:44–51`），数据库外键不会替系统阻止删除旧块。因此不得仅以“没有FK依赖”为理由删除。
- 原文/页码/字符映射和历史标签依据均维持原版本。新切法不能重算旧答案的 evidence ID、偏移或引用文字。
- 现有 `tests/test_retrieval_ranges.py:163–184` 已验证切换范围后新旧证据同时可定位；`tests/test_chunking.py:9–50`、`tests/test_quote_context.py:33–55` 覆盖 Unicode、CRLF、缩写、小数、段落/页界及残缺尾句，可复用而不编新分句器。

本报告是代码与评价合同审查，不是300/400/600的实际优劣结果。后续独立runner只产生新比较记录，不改变既有 gold 或生产索引。
