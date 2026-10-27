# 流水线第 3 步设计稿：名单只实现一遍，标准确认放在逐篇判定之前（第三稿）

2026-10-26，依据分支 `claude/sync-20261025`（提交 `60775b3`，第 2 步之后）的代码。这是设计稿，还没有改代码；第 6 节列出需要你决定的地方。两轮 Codex 复核：第 2 节（名单合一，S3-a）已通过，可以单独开工；第 3 节（两阶段）按两轮意见改到第三稿，等你定第 6 节的三项产品规则再开工。改动记录见第 8 节。上位文档：`pipeline_current_vs_target.zh-CN.md` 第 4 节第 3 步；用户 2026-10-26 的意见见 plan.md"名单题：标准确认放在逐篇判定之前"。

---

## 0. 一页看懂

做两件事：

- **A. 名单只实现一遍。** 今天单库名单（`_answer_evidence` 的名单分支）和两库名单（`_screen_both`）是两套代码，分流（relevance_triage）接了两遍。合成一个函数：对每个集合循环，一个集合也走它。
- **B. 两阶段问答。** 名单题先检索、起草标准、把标准和排名靠前文章里的原句给人看，人选定标准之后才逐篇判定（花钱的一步），最后出名单。

不变的：三组（通过／待审／排除）和"名单 = 通过 ∪ 待审"；起草标准的模型只看问题；引文逐字核对；每个付费调用先预留后结算。用户 2026-10-27 定：模型起草、未经人确认的标准不给筛查模型（10-24 实验），人确认后的标准给分流也给筛查；人写进规则的原句随规则进模型。

费用：本设计稿 $0。实现后每道名单题多出的只是把今天已经花的 $0.003 标准起草提前到判定前。用户看完卡片放弃时，已经花掉的是理解（研究代理约 $0.01–0.02）、嵌入（约 $0.00002）和起草（$0.003），没有花判定的钱——判定才是名单题的大头。5 道人工标注题的付费复测（约 $0.08）另行申请。

---

## 1. 现状（提交 60775b3）

### 1.1 名单题今天怎么走

```
_answer_evidence（已读计划：plan.shape == "list"）
├─ 检索：关键词搜索兜底 → 预留 $0.04 → 向量 + 关键词混合检索，每库 120 篇、每篇 2 段
└─ 名单分支（取消 $0.04 预留，各批自己结算）
     ├─ 两库（plan.datasets 为两个）→ _screen_both：每库并行——短语搜索 → 字面名单，或
     │     合并整篇段落 → 一个标准（起草一次）→ 分流 → 筛查；合并 → list_answer(scopes=…) → 概括或逐源阅读
     ├─ 关系名单（plan.list_kind == "relation"）→ _relation_list：按来源字段列出，不调模型
     ├─ 字面名单（plan.list_kind == "literal"）→ 短语搜索 → literal_results → list_answer(literal=…)
     └─ 单库筛查 → 短语搜索 → 合并整篇段落 → 关系提示（社交且有关系选择时）→
           标准（无引号短语且无关系提示时）→ _triaged_screen 或 screen_list → list_answer → 概括或逐源阅读
```

单库和两库两条路做同样的事，但细节不同，见 2.2 的差异表。

### 1.2 标准（criterion）今天在哪

- `relevance_triage.make_criterion(rag, question, visitor)`：输入只有系统提示和问题，输出 1–4 条"算"的规则和 0–3 条"不算"的例外（gpt-5.6-luna，约 $0.003）。这一点符合用户定的规则。
- 起草后立刻用于 Decisions 分流（`triage_questions` 把规则写进每篇的判题）和三组路由；筛查模型不看标准。
- 用户在名单出来之后才看到标准：`relevance_eval_ui.criterion_card` 显示规则、例外和三组数字；每篇旁边有"Relevant／Not relevant"投票（`relevance_reviews` 表，迁移 0008）。
- 所以标准宽窄选错时，贵的逐篇判定已经花掉；范围大时候选之外的也已漏掉。

### 1.3 问答入口今天怎么接

- 网页：`app.py` 的 `research` 回调（按钮 `answer-paid`），`run_research` → `service.answer(question, filters, visitor, progress)`，结果经 `_render_answer_result` 渲染；进度用 `progress_registry` 的令牌轮询。
- 接口：`POST /api/v1/ask`（api.py）→ `service.answer`，返回 Answer 的 JSON。MCP 服务器没有问答工具。
- `Service.answer` 用 `QUESTIONS.question(visitor)` 包住整次回答；按访客的限次在第一个付费调用时计 1 次问题（`QuestionGate.admit`），统计类免费回答不计。
- 每次回答写一行 `answer_runs`（`db.save_answer`）。

---

## 2. A：名单只实现一遍

### 2.1 目标

一个函数负责所有要筛查的名单：

```
_list_answer(question, plan, scopes, evidence, visitor, progress, relation_listing=None) -> (Answer, cost)
  scopes：按 plan.datasets 得到的 Filters 列表（一个或两个集合），已校验不比用户范围大
  evidence：检索阶段得到的候选段落（两个集合时各自排好名）
```

步骤：

1. 关系名单（`plan.list_kind == "relation"`）直接交给 `_relation_list`，不进下面的循环（它不读内容，也没有标准）。
2. 标准：`plan.phrases` 为空且没有关系提示时起草一次（或使用阶段二传入的已确认标准，见第 3 节）；两个集合共用一份。
3. 对每个集合（两个时并行，和今天的 `_screen_both` 一样）：
   - `total = _scope_count(scope)`；
   - 有引号短语：`phrase_search(phrases, scope, limit_records=total + 1)`；
   - 字面名单（`plan.list_kind == "literal"`）：`literal_results(literal, phrases[0])`，不调模型；
   - 否则：候选 = 该集合的字面命中 ∪ 该集合的检索候选 → `_merge_article_passages` 补全整篇 → `reread` 闭包 → 有标准走 `_triaged_screen`，没有走 `screen_list`（首读 `max(MAX_CANDIDATES, 字面命中篇数)`，最多 `max(MAX_WIDENED, 字面命中篇数)`）；
   - 返回该集合的结果、花费、读过的段落、分流摘要。
4. 合并：结果按集合顺序拼接并标 `dataset`；段落去重；`_with_accounts`；分流摘要一个集合时保持今天的平铺形状，两个集合时 `by_dataset` + 合计（和今天的 `_screen_both` 一样）。
5. `list_answer(question, results, pool, scope_total=合计, scopes=两个集合时才传, literal=…, criterion=…, triage=…)`。
6. 字面名单到此为止；其余按 `plan.read_sources` 走 `_read_matched_sources`，否则 `_summarize_list`。

### 2.2 两条路的差异和统一办法

| 项目 | 单库今天 | 两库今天 | 统一后 | 对外可见变化 |
|---|---|---|---|---|
| 范围总数 | `len(db.public_rows(filters))` | `_scope_count(scope)`（有 `count_public` 用它） | `_scope_count` | 无（数字相同，少读一次全表） |
| 字面名单 | 按 `plan.list_kind == "literal"` 整题走字面 | 每库自己判 `pure_literal_question` | 按 `plan.list_kind == "literal"`，每库字面 | 无；计划里两库字面题的 list_kind 从 "screen" 改回 "literal"（2.3） |
| 关系提示（有关系选择但不是关系名单） | 社交库拼进筛查问题 | 没有（两库时没有关系选择） | 只在单个社交集合且有关系选择时拼进（和今天一样；不推广到两库），有提示则不起草标准 | 无 |
| 起草标准的条件与时机 | 无引号短语且无关系提示；在计数、短语搜索、补全整篇之后起草 | 无引号短语且非字面；在各库计数之前起草 | 条件统一为：非字面且无引号短语且无关系提示。时机保持各自今天的顺序：单库先准备（计数、短语、补全）再起草再判定；两库先起草，再各库各自并行地准备并判定（没有全局屏障，一库准备失败不影响另一库已发出的调用） | 无 |
| 筛查调用参数 | `screen_list(limit=max(40, 字面命中篇数), widen_to=max(120, 字面命中篇数))` | 每库同样的 `limit`／`widen_to` | 不变 | 无 |
| 记录字段 `first_read` | `max(40, 字面命中篇数)` | 固定 40（调用参数其实是 `max(40, …)`，记录写少了） | 每库 `max(40, 该库字面命中篇数)`；顶层取最大，两库另记 `first_read_by_dataset`（不改 `by_dataset`，它同时是 `structured_result` 的一部分） | 两库的顶层值可能从 40 变大，并多一个记录键；调用参数本来就一样，只是记录改对 |
| 跨库去重与账号 | 单库无，结果不标 `dataset`；筛查名单补账号（`_with_accounts`），字面名单不补 | 段落池按 `evidence_id` 去重；结果按库各自保留并标 `dataset`；都补账号 | 段落池统一去重；只有两个集合时才标 `dataset`；单库字面名单仍不补账号（补了会改变社交帖的行格式，另议） | 无 |
| 字面名单的后处理 | `list_answer(literal=短语)` 后直接返回，不概括 | 同 | 同 | 无 |
| 一个集合失败 | 异常→整题失败（`_answer_evidence` 的 except） | 线程里的异常传回主线程→整题失败 | 同今天：整题失败，不出半张名单（线程池退出时等另一库结束，所以失败时读过的段落是确定的） | 无 |
| 失败答案附带的可浏览证据 | 字面命中 ∪ 补全后的整篇 ∪ 重读段落（已读到的，去重后） | 只有检索候选 | 和今天一样：单库回填去重后的已读段落，两库保留检索候选（提交前复核两轮都要求保持原行为） | 无 |
| 费用结算 | 每批筛查自己预留结算；标准起草算一次 | 同；起草只算一次 | 同 | 无 |
| 分流摘要 | 平铺 + `criterion_cost_usd` | `by_dataset` + 合计 + `criterion_cost_usd` | 一个集合平铺，两个集合 `by_dataset`（同今天） | 无 |
| 并行 | 否 | 每库一线程 | 集合数 > 1 时并行 | 无 |
| 概括／逐源阅读 | `plan.read_sources` | `sources_content_request(question)` | `plan.read_sources` | 无（同一谓词） |
| 返回 | Answer + 费用 | Answer + 费用 | 同 | 无 |

### 2.3 计划的变化

- 第 2 步为了镜像当时的代码，把"两库 + 一个引号短语的字面题"记为 `list_kind="screen"`。统一后两库字面题也按 "literal" 处理（每库做字面匹配，结果和今天 `_screen_both` 的 `literal_only` 分支一样），计划改回 `literal`。`test_question_plan` 里对应的断言和 864 组差分 oracle 随之改（oracle 是"改前代码"，第 3 步后 oracle 应是第 2 步后的行为，这一项是刻意的变化，单独列出）。
- `plan.datasets` 决定 scopes；`_answer_evidence` 不再有 `both_list` 变量。
- 计划版本 `question-plan-v2` → `question-plan-v3`（规则变了一处，运行记录能区分）。金样本比较把 `question_plan.version` 列入白名单。

### 2.4 验证（免费）

- 金样本对照：合并之前，用固定的一组虚构场景（单库／两库 × 有无引号短语 × 有无关系选择 × 有无标准，含零命中和部分命中）跑今天的代码，把名单、引文、每种模型调用的次数与顺序、费用、`list_screening` 记录存成 JSON 放在 `tests/fixtures/list_golden/`；合并后同样的场景必须逐项一致，允许的差异只有 2.2 表里标明的记录字段（白名单写在测试里）。不许为了消除差异去改金样本。
  已做（2026-10-26）：22 个场景（第二轮提交前复核后补了一库计数失败、单库和两库写手触限三个），录制入口拒绝覆盖已有文件并用 git 核验基线（HEAD 60775b3 且 `src/` 干净）；预算按每笔预约记录最终状态（结算／不确定／取消／拒绝）；同库内的筛查调用按候选位置、评审调用按记录排序，不锁线程交错；比较只看行为部分（回答、模型调用、数据库调用、预算），场景元数据只核对问题和范围。
- 现有 25 个证据路线套件原样通过（第 2 步基线 389 项）。
- 新测试：同一道题、同一 fixture，`Filters(dataset="native")` 和 `Filters(dataset="all")` 走同一个函数，断言两者的分流摘要形状符合 2.2；两库字面题每库各一次短语搜索且不调模型。
- `_screen_both` 删除；grep 确认没有第二份分流接线。

---

## 3. B：两阶段问答

### 3.1 顺序

用户 2026-10-26 的六步，对应到代码：

| 用户的步骤 | 代码里的阶段 | 花钱吗 |
|---|---|---|
| ① 提问、定范围 | 入口 + 理解（研究代理 → QuestionPlan） | 代理调用（今天已有） |
| ② 检索，得到排好名的候选 | `_answer_evidence` 的检索步（向量 + 关键词，一次） | 嵌入约 $0.00002 |
| ③ 起草标准；卡片用排名靠前文章的原句当例子 | `make_criterion`（只看问题）+ 新增 `criterion_examples`（只给人看，不调模型） | $0.003（今天已有，只是提前） |
| ④ 用户选标准 | **阶段一在此结束**，返回待确认的回答；用户在网页上接受／改宽改窄／编辑／放弃。凡是要让模型逐篇判定的名单都在这里停，包括没有起草标准的引号短语题和关系提示题（卡片上写明将用的判定条件） | 0 |
| ⑤ 按标准逐篇判定 | **阶段二**：带确认后的标准重新进入证据路线 → `_list_answer`（分流 + 筛查） | 今天的名单费用 |
| ⑥ 出名单 | `list_answer` → 概括或逐源阅读 → 三组展示 | 今天已有 |

ask 模式的含义是"模型逐篇判定之前先经人确认"：`plan.list_kind == "screen"` 的名单题都走两阶段，不论标准能不能起草——卡片上写明将要用的判定条件（起草的规则；或引号短语必须出现；或"没有判定标准，分流已关闭，筛查只按问题找句子"）。关系名单（按来源字段列出）和字面名单（纯字面匹配）不调模型判定，一阶段就答完；普通问题不变。

### 3.2 阶段一的产物：待确认的回答

不加新的 `Answer.status`（四个状态被接口、网页和 `_ensure_answer` 到处判断）。用已有的"澄清"形态：

| 字段 | 值 |
|---|---|
| `status` | `insufficient_evidence` |
| `answer_mode` | `clarification` |
| `failure_reason` | `criterion_confirmation_required`（加进 `_ensure_answer` 的保护清单，不许联网补救） |
| `answer` | 一段话："这道题会按下面的规则逐篇判定。请确认规则，或按例句选宽窄。范围内共 N 篇……"（两种文案，见 3.9） |
| `structured_result` | `{"kind": "criterion_confirmation", "criterion": {counts, does_not_count}, "examples": [...], "candidates": {"native": {"scope_total": 263, "retrieved": 120, "whole_scope": true}, ...}, "continuation": "<签名令牌>", "expires_at": "...", "data_version": "..."}` |
| `evidence` | 排名靠前的候选段落（免费可看；放弃判定时就是结果） |
| `research_trace` | `question_plan`（含 `criterion_mode="ask"`）、`list_screening` 暂无、`criterion_draft`（规则、花费、例句来源） |
| `cost_usd` | 嵌入 + 起草 |

统一的暂停标记是 `structured_result.kind == "criterion_confirmation"`，由一个辅助函数 `pending_confirmation(result)` 判断，所有消费者都用它，不各自看 `failure_reason`：

| 消费者 | 遇到待确认时 |
|---|---|
| `_ensure_answer`（联网补救） | 不补救（原因也在保护清单里，双保险） |
| `_answer_with_tools` 的馆藏优先回退 | ask 随父请求传下去；回退本身若停在待确认，就把待确认卡片当作这次的回答返回（比澄清更有用，且没花判定的钱）；父请求已是待确认时不用回退替换它 |
| 复合题（`_tool_composite_answer`）的子问 | ask 随父请求传下去，不自动降成 auto；名单子问停在待确认时，复合结果把该子问标为"待确认，请单独提问这一部分"，不为它付费筛查（v1 不在复合题里续问）；没有人看卡片的入口（接口默认、`topic_compare` 等内部调用）用 auto（用户 10-27 决定 1） |
| `_record_web_trace`、概括、逐源阅读 | 走不到（名单还没生成） |
| `plan_check` | 计划 ask 且回答待确认 = 一致 |
| 网页 `_render_answer_result` | 渲染卡片（3.10） |
| 接口 | 原样返回 JSON，HTTP 200，`kind` 就是标记 |

网页把它渲染成卡片（3.10）；接口原样返回 JSON。

### 3.3 例句怎么选（不自动进模型；人写进规则的原句随规则进模型）

- 来源：检索排名前 N 篇（建议 N = 5，每库各 5）的已检索段落，不再读库、不调模型。
- 每条规则选一句：把规则去掉停用词后的实词和段落按句切开后逐句比词面重叠，取重叠最多的一句；没有任何重叠的规则用排名第一篇的首句兜底（`_opening_words` 已有）。一句最长 `MAX_QUOTE` 字符，逐字取自段落，附标题／出处／日期和记录链接。
- 守住：例句**不进** `make_criterion` 的输入；起草模型仍只看问题。例句只出现在卡片和 `research_trace["criterion_draft"]["examples"]` 里。
- 例句**不自动进任何模型**：不进起草模型；用户没动手时也不进分流和筛查。用户在例句上点"算"或"不算"，网页把它变成规则文本框里的一行草稿（算：`含有"<原句>"这样的说法也算`；不算：`"<原句>"这类不算`），人可改、可删、可保留原句；最终进入判定的只有人在文本框里确认的规则文字（用户 2026-10-27 决定 2：人写进规则的原句可以给判定模型看——"用户就是要找到自己想找的"）。记号和被标的例句记在 `research_trace["criterion_draft"]["example_choices"]`，与规则分开保存。
- 服务端记录：续问时检测确认后的规则文字是否含展示过的例句（规范化后的子串比对），含有则在 `list_screening.criterion_quotes_examples` 记下是哪几句，不拒绝、照常判定（决定 2）。
- 词面重叠选句是 v1，便宜且可解释；若例句经常文不对题，v2 可改为每条规则一次向量检索（每条约 $0.00001，嵌入可缓存），列为后续。

### 3.4 用户在卡片上能做什么

1. **按这些规则判定**（主按钮，付费的一步从这里开始）。
2. 对每条例句点**算／不算**：选择变成规则的追加行（3.3）。
3. **编辑规则**：一个文本框，预填规则（一行一条）和"不算："之后的例外，可改可删可加；空行忽略；最多 4 条规则、3 条例外（和 `Criterion` 模型一致），超出在网页上提示。
4. **不判定，只看检索结果**：免费，把阶段一的候选段落当普通证据卡显示；回答状态保持"未判定"。

这四样 v1 全做还是先做 1、3、4，见第 6 节。

### 3.4a 确认后的标准怎么控制最终名单

今天的三组路由：分流模型按标准判（meets／borderline／does_not_meet），筛查模型按**原问题**找一句可引用的句子；通过 = 分流 meets ≥ 0.5 且筛查有句子；排除 = 分流确信不符且没有单条规则 ≥ 0.3；其余待审。标准只给分流模型，不给筛查模型（10-24：给了漏 5/29，那是模型起草的标准）。

后果：人把标准**改宽**（例如"clean energy 也算"）时，分流会说 meets，但筛查按原问题可能找不到句子，这些篇目落到**待审组**——名单 = 通过 ∪ 待审，它们仍在名单里，只是标为"需要人核对"，不在通过组；人把标准**改窄**时，分流排除得更多，通过组和待审组都变短。也就是：改窄对三组都生效，改宽只能把篇目送进待审组。两种处理，**同一份确认后的标准只能有一种筛查策略，不因人是点"接受"还是编辑过而不同**：

- (a) 保持今天的分工：筛查始终按原问题找句子；人的标准只驱动分流和三组路由。改宽的篇目进待审组，名单里标明"符合你确认的规则，但原问题字面上没有可引用的句子"。保留 10-24 的发现（标准给筛查会漏）。
- (b) 人确认之后（接受或编辑都一样），筛查按确认后的标准找句子（提示里写明"按研究者确认的标准"），改宽的篇目能进通过组，仍要有逐字核对的句子。代价：接受未改的草稿时，等于把模型起草的标准给了筛查，10-24 测得漏 5/29。

**用户 2026-10-27 选 (b)**：人确认后的标准（接受或编辑同一策略）同时给分流和筛查，筛查提示写明"按研究者确认的标准找句子"；改宽的篇目可进通过组，仍要逐字核对的句子。未经人确认的模型草稿（auto 模式）仍按 (a)：标准只给分流，筛查按原问题（10-24 实验）。`list_screening.screening_basis` 记 `question` 或 `confirmed_criterion`。S3-e 按 (b) 复测并与 10-24 基线并列；(a) 可并列测一次作对照，不据此改选择。

### 3.5 阶段二怎么续

- 入口：`Service.answer(question, filters, visitor, progress=None, *, continuation=None)`。`continuation = {"token": ..., "criterion": {counts, does_not_count}}`。
- 令牌：`itsdangerous.TimestampSigner`（Flask 自带），密钥用 `settings.cookie_secret`（没有则进程内随机，和 `app.server.secret_key` 一样）。签名内容：`flow_id`（阶段一生成的随机 id）、访客、问题、用户原始范围、阶段一的 `QuestionPlan`（含收窄后的有效范围、检索词、计划版本）、起草标准的哈希、数据版本（含索引版本）。有效期 30 分钟。
- 校验：签名、有效期、访客一致、数据版本和当前相同、`validate_share_scope`（有效范围不比原始范围大）。任何一项不过→明确回答"确认已失效，请重新提问"（`failure_reason=continuation_invalid`），**不自动重新发起付费流程**。数据版本变了也一样失效，并说明"数据更新了"。
- 防重放：进程内 `FlowRegistry`（和 `progress_registry` 同一类做法）按 `flow_id` 原子登记状态：阶段一结束时登记 `pending`（30 分钟 TTL）；续问时原子地从 `pending` 改成 `judging` 并绑定规范化后的标准哈希；判定结束改 `done`（记结果所在的 `answer_runs` 行）或 `failed`。规则：登记里没有这个 `flow_id`（重启过、或 `pending` 过期被清）→即使签名有效也**不执行**，明确回答失效；`judging`／`done` 的记录不按 TTL 清除（最多保留 24 小时，执行中永不清除），同一 `flow_id` 再来就返回"正在判定中"或已有结果，不再付费；同一 `flow_id` 带不同标准哈希再来→返回"冲突：这道题已按另一份标准判定"，不付费；执行被打断（进程停了）→重启后登记不存在，按失效处理，不会被当作新任务收费。网页按钮在回调运行期间禁用（Dash `running`）是第二层。限制：登记表在进程内，多进程部署时不跨进程；现部署是单进程，和进度登记表一样的限制，写进 operations 文档。
- 两阶段用 `flow_id` 关联（阶段一和阶段二的 `answer_runs` 行都记它），不靠问题文本。
- 阶段二**不再调研究代理**：从令牌里恢复 `QuestionPlan`（`QuestionPlan(**data)`），`validate_share_scope` 再校验一次，直接 `_answer_evidence(question, Filters(plan.filters), visitor, plan=plan, criterion=确认后的标准)`。检索重做一次（嵌入按文本哈希缓存，`db.search` 一两秒），不信任客户端传回的候选。同一数据版本下同样的检索词和范围给出同样的候选（同一索引、同一缓存向量、确定性的融合排序），所以阶段二的候选和卡片上的一致；版本变了就按上面失效处理，不会判定一组用户没见过的候选。
- `_answer_evidence` 新参数 `criterion=None`：有则跳过 `make_criterion`，分流和筛查都用它（3.4a 的 (b)），`list_screening` 记 `criterion_source="confirmed"`（原样接受）或 `"edited"`（人改过）、`screening_basis="confirmed_criterion"`；没有且 `plan.criterion_mode == "ask"` → 走阶段一返回待确认回答；没有且 `"auto"` → 今天的行为，记 `"draft_unconfirmed"`、`screening_basis="question"`。
- 服务器除 `FlowRegistry` 外不保存阶段状态；阶段一和阶段二各写一行 `answer_runs`（阶段一的 `result` 里有 `flow_id` 和令牌哈希，不是令牌本身）。
- 实现说明（S3-c，2026-10-27，按 Codex 计划复核改）：① 令牌签的是证据路线被调用时的范围（`scope`）和计划（含有效范围）；阶段二先核令牌范围在本次请求范围之内、计划范围在令牌范围之内，再按令牌的范围与计划进证据路线；问题文本签发与校验用同一规范化（压空白）。② 数据版本在入口核一次、在证据路线读版本后再核一次（`expected_version`），中途变了按失效拒绝，流程终态。③ 没起草标准的条件（引号短语、关系提示、分流关闭）可以不写规则直接确认：记 `criterion_source="confirmed"`、`screening_basis="question"`、不记 `criterion`，另记 `list_screening.confirmed_condition` 和 `research_trace.criterion_confirmation`；起草过或起草失败的卡片没有规则就不判定（`criterion_invalid`／`rules_required`）。④ 流程在 `_answer_question` 的完整包装（联网补救、记录、plan_check、审计保存）之后才标 done，判定中再来返回“正在判定中”；done 存紧凑副本（只留引文和结构化结果引用的段落），回放是新副本、费用 0、记 `continuation_replay`，回放和复合题里被推迟的子问都不再联网补救；failed／limited 终态，重来要重新提问（损失起草费）。名单在预留取消之后失败或触限的回答，`cost_usd` = 本次嵌入费 + 失败前已结算的模型调用（请求内逐笔收集：筛查批次、复核、Decisions 评审、起草、写手各部分；无 usage 的 Decisions 回复按预估计费），不确定的预留不计入、留在账本里；`research_trace.cost_basis` 说明口径并同时写进 `structured_result`（这一点对 auto 的失败回答也成立，5 个冻结失败场景按精确规则核对）。⑤ 登记表：流程在起草前以 preparing 登记（占位），卡片发出后转 pending，30 分钟从发卡时起算；preparing 和 judging 永不被淘汰，满员时在起草前拒绝（`confirmation_registry_full`，状态 limited）；阶段一失败则撤销登记；准备期间被清理则不发卡（`confirmation_unavailable`，状态 service_unavailable）。模型起草的空白或超限规则按起草失败处理（费用保留）。例句截断按原文词尾位置，逐字。接口精简输出保留卡片的全部候选段落。⑧ 判定前的最后一次核对：`_consistent_version` 在判定要用的最后一次读取之后（短语搜索、补全整篇、小范围补读）、第一次付费判定调用之前再核一次数据版本，变了就按 `data_changed_during_retrieval` 停下、流程终态；auto 模式同样核对（数据不动时无差别）。⑥ 复合题子问 v1 不出卡片、不起草、不登记：用 S3-b 的拒绝，正文加“请单独提问这一部分”，复合结果原因记 `criterion_confirmation_required`（不联网），馆藏优先回退对它不启动。⑦ `Service.answer(criterion_confirmation=None)` 一律 auto，网页在 S3-d 显式传开关值；接口只在请求带字段时转发。
- ask 模式下任何要模型逐篇判定的名单都先停，没有悄悄退回今天筛查的路：起草失败或规则为空→待确认卡片的规则栏为空并说明"标准起草失败，请自己写规则，或只看检索结果"，没有人写规则就不判定；引号短语题、关系提示题（今天不起草标准）→卡片写明判定条件（短语必须出现／关系已由来源字段满足，只判其余条件），人确认后才筛查；分流被运维关掉（`OBS_RELEVANCE_TRIAGE=off`）→卡片写明"没有判定标准（分流已关闭），筛查只按问题找句子"，仍要人确认才花钱，计划记 `criterion_mode=ask`、`criterion_available=false`；令牌失效→上面的明确失败。

### 3.6 非交互入口的默认

- `POST /api/v1/ask` 默认 `criterion_mode="auto"`（用户 2026-10-27 决定 1）：和今天一样起草后直接判定，回答文字和 `list_screening.criterion_source` 标明"标准由模型起草，未经人确认"。
- 接口也能两阶段：请求加 `"criterion_confirmation": "ask"` 得到 3.2 的 JSON；再发 `"continuation": {"token": ..., "criterion": {...}}` 续。文档写进 `docs/api`（如有）。
- `topic_compare_ui.ask_about` 等内部调用保持 auto。

### 3.7 限次与预算

- 预算台账不变：嵌入、起草、分流、筛查各自预留结算。
- 按访客限次（每分钟 5、每天 30）按"第一个付费调用"计 1 次问题。阶段一有起草调用，会计 1 次；阶段二再计 1 次。一道两阶段名单题占 2 次。两种处理：(a) 照计，简单，文案说明；(b) 阶段一的起草调用不计次（给 `QuestionGate` 加一个"续问"标记）。建议 (a) 先上，观察后再定。

### 3.8 记录与核对

- `QuestionPlan` 新字段：`criterion_mode`（`ask`／`auto`／`none`：关系名单、字面名单和普通题为 none）、`criterion_available`（分流开着且会起草）；原因记 `reasons["criterion_mode"]`（`entry:dashboard`／`entry:api`／`flag:off`／`kind:literal` 等）。
- `research_trace["list_screening"]` 新字段：`criterion_source`（`confirmed`／`edited`／`draft_unconfirmed`／`none`）、`screening_basis`（`question`／`confirmed_criterion`）、`criterion_draft`（起草原文，便于对照人改了什么）、`criterion_quotes_examples`（规则里引用了哪些展示过的例句）。
- `plan_check` 新比较：`criterion_matches`——计划 ask 的题，最终 `criterion_source` 必须是 confirmed／edited 或回答停在待确认；计划 auto 的题不能出现待确认。
- `answer_runs` 两行靠 `flow_id` 关联（都记在 `research_trace["flow_id"]`），不靠问题文本；阶段一那行的 `structured_result.kind == "criterion_confirmation"`。

### 3.9 范围大小的边界（用户的边界）

卡片第一句按范围说清判定会覆盖谁：

- 某个集合在范围内的记录数 ≤ 400（`TRIAGE_ALL_MAX`，按集合分别算，今天 `_triaged_screen` 就是这样：检索前 120 名之外的记录也取全文一起判）："范围内的 N 篇都会按规则判定；下面的例句来自最相关的几篇。"排名只决定例句从哪来，不筛掉任何一篇。这是集合级的保证——判定的输入是该集合全部有正文的记录，不是"把检索到的文章补全"；没有正文的记录计数说明。
- 范围更大（主要是社交帖）："范围内有 N 条，会判定检索到的前 120 条候选；规则选错会漏掉候选之外的，请在这里确认。"

两种文案都写进 `structured_result.candidates`，网页和接口用同一份数据。

实现说明（S3-c，提交前复核第一轮后恢复为设计）：卡片的承诺就是 `_list_answer` 在确认之后实际读的，与分流开关无关：该集合 ≤ 400 篇→`whole_scope`（分流开着走 Decisions 全读，关着则筛查补读范围内所有有正文的记录，首读 = 全部）；更大→`candidates`（检索到的候选全部读完，没有“前 40 篇无命中就停”的规则）。`with_rules` 是有规则时的覆盖，`condition_only` 是不写规则只确认条件时的覆盖（按问题筛查；引号短语题在大范围时先读含短语的每一篇，`phrase_hits` 用阶段一同一 `phrase_search` 数出）。auto 模式不变（分流开着才全读；筛查保留 40→120 的渐进规则）。计划稿曾想把小范围全读收窄到“只有分流开着时”，Codex 指出这是未经用户授权的范围缩减，已改回。

### 3.10 网页

- 渲染：`_render_answer_result` 识别 `kind == "criterion_confirmation"`，输出卡片：规则列表（每条下面是例句 + 算／不算按钮）、例外列表、编辑文本框、"按这些规则判定"、"不判定，只看检索结果"；下面是候选证据卡（免费）。
- 回调：按钮用模式匹配 id（`{"type": "criterion-continue", "q": <问题哈希>}` 等，和投票按钮 `rel-vote` 同一套做法）；`research` 回调增加这些 Input；点击后拼 `continuation`，走同一个 `run_research` → `service.answer(..., continuation=...)`。算／不算按钮只改一个 `dcc.Store` 里的选择，不发请求。
- 进度标签（`query_progress.py`）新增 "drafting"（起草标准）和 "judging"（逐篇判定）。
- 本机没有 Node，三项浏览器 JS 检查不能跑；本设计不加浏览器端 JS，回调逻辑用 Python 测试，卡片交互人工走一遍。

### 3.11 开关

- `OBS_CRITERION_CONFIRMATION`：`ask`（网页两阶段）／`auto`（今天的行为），默认 auto（S3-c）；只有网页入口读它（S3-d），接口和内部调用一律 auto，接口可按请求要求 ask（决定 1）。分流本身仍受 `OBS_RELEVANCE_TRIAGE` 控制；分流关着时卡片写明“没有判定规则（分流已关闭），筛查只按问题找句子”，仍要人确认才花钱（3.5），不是没有两阶段。

---

## 4. 分步实施（每步单独提交、单独门禁、可单独回退）

| 步 | 内容 | 行为变化 | 检查 |
|---|---|---|---|
| S3-a（已做，2026-10-26） | 先存金样本（2.4，全模拟调用，22 个场景），再合成 `_list_answer`（共用 prepare／judge；单库：准备→起草→判定，两库：起草→各库并行准备并判定，都和今天一样），删 `_screen_both`；计划里两库字面题改回 literal（v3）；不顺带启用任何确认流程 | 只有 2.2 列出的记录字段 | 金样本逐项一致（白名单外零差异，白名单内的实际差异见 work.md）+ 25 套件 + 6 项新测试（同一函数、两库字面题每库一次短语搜索且零模型调用、每库各自编号与重读、>40 命中每库各自首读、触限答案的证据不重复、接线只有一份）；门禁 |
| S3-b（已做，2026-10-27） | 计划加 `criterion_mode`（auto／ask／none）、`criterion_available`（分流开着且本题会起草；未知为 None）、`signals.relation_hint`、`reasons.criterion_mode`，版本 v4；`screen(criterion=)` 把确认后的标准附在判题问题后（`CONFIRMED_CRITERION_NOTE`：按标准判，引用满足规则的句子；必含短语仍只取自原问题），首读、重读、复核同一文本；`triaged_screen(screen_with_criterion=)`；`_answer_evidence`／`_list_answer` 加 `criterion=`、`criterion_source=`、`criterion_draft=`：有则不起草、分流开着时分流也用它、筛查按它找句子；记录 `criterion_source`（confirmed／edited／draft_unconfirmed／none）、`screening_basis`（confirmed_criterion／question）、`criterion_draft`（只记真正的草稿）；带标准的调用其路线计划记 `criterion_mode=ask`；来源只接受省略（= confirmed）、confirmed、edited，其他显式值在花钱前拒绝（`criterion_source_invalid`）；传入 auto 计划加标准在花钱前拒绝（`criterion_plan_mismatch`）；计划 ask 而没有标准→拒绝（`criterion_confirmation_required`，附检索候选，不起草不判定，`_ensure_answer` 不联网补救）；开 norms 时题型仍按原问题选，提示的 payload 带标准；`plan_check` 加 `criterion_matches`（筛查过却没记来源 = 不一致，没筛查 = 未知） | 无（auto = 今天；还没有调用方传标准或 ask 计划） | `tests/test_list_criterion_mode.py` 18 项（含开 norms 的完整提示、分流关闭／评审全失败仍按标准筛查、字面与关系名单不查分流开关）；22 个金样本白名单外一致（白名单只加新记录键并核对版本 = v4）；29 个文件通过数见 work.md；门禁见 work.md |
| S3-c（已做，2026-10-27） | 新模块 `criterion_confirmation.py`：`pending_confirmation`、标准规范化与哈希、`ConfirmationTokens`（itsdangerous，30 分钟，没配 cookie secret 则每进程随机）、`FlowRegistry`（pending→judging→done／failed，pending 30 分钟、done／failed 保留 24 小时、judging 永不清除，满员拒绝新卡片）、例句选择（每库检索前 5 篇按词面重叠，无重叠取首句，不进任何模型）、`example_choice_line`、`quoted_examples`、覆盖说明与卡片文案（中英）、`mark_unconfirmed`、拒绝文案。`Service.answer(criterion_confirmation=None, continuation=None)`：None = auto（接口与内部调用永不继承网页开关，决定 1），模式随计划传到证据路线、复合子问、馆藏优先回退；`_confirmation_card`（阶段一：先登记流程再起草，起草只看问题；条件种类 draft／draft_failed／phrases／relation_hint／triage_off；令牌签 flow_id、访客、问题、调用范围、计划、草稿哈希、条件、数据版本）；`_continue_confirmation`（阶段二：按序校验形状、令牌、访客、问题、数据版本、范围、标准，再原子登记，再进证据路线并在检索前再核数据版本；confirmed／edited 由服务器按哈希判定）；流程在完整包装与审计保存之后才标 done；同标准重试回放紧凑副本、不同标准冲突、判定中拒绝、失败／触限终态；auto 名单正文首段标注“规则由模型起草、未经研究者确认”，`structured_result.criterion_source`；所有 `save_answer` 只存令牌哈希。接口字段 `criterion_confirmation`、`continuation`；`OBS_CRITERION_CONFIRMATION` 默认 auto（S3-d 网页读）；进度阶段 drafting／judging | 开关不开时：筛查名单多 `structured_result.criterion_source`，有草稿的名单正文多一句“未经确认”，名单在预留取消后失败／触限的回答 `cost_usd` 记本次嵌入费并记 `cost_basis`（都按金样本的精确规则核对） | `tests/test_criterion_confirmation.py` 57 项（含参数化；卡片、确认／编辑／引用例句、回放、冲突、并发与满员、失败与触限终态、已结算后触限、数据版本在入口／检索中／补读整篇后／只在补读漏掉记录时四处核对（分流开关两种）、有效期从发卡起算与准备超时不发卡、九种无效续问、重启、七种无效规则、起草失败与空白草稿、分流关闭、开关两阶段间翻转、大范围候选全读、引号短语、关系提示、复合子问（含自带原因）、回退卡片、未完成结果回放、并发起草、例句逐字、auto 标注、开关不继承、真实 Service 接口往返、纯函数）；22 个金样本按规则一致；接口 +2、配置 +1；门禁见 work.md |
| S3-d | 网页卡片与回调；网页默认 ask | 网页名单题变两阶段 | Python 回调测试；人工走一遍；记录截图路径 |
| S3-e | 人工标注集 5 道题按确认后的标准（(b)：分流和筛查都用）重跑三组数字，与 10-24 基线（30／21／24）并列；(a) 并列一次作对照 | — | 约 $0.08，另行申请 |

S3-a 可以先做；S3-b 起依赖 S3-a。每步完成都更新 `pipeline_current_vs_target.zh-CN.md` 第 4 节的进度注。

---

## 5. 不变的部分与边界

- 三组和并集；阈值（`EXCLUDE_AT` 0.8、`RULE_GUARD` 0.3、`PASS_AT` 0.5）不动；改阈值要在人工标注集上重跑并报告三组数字。
- 未经人确认的模型草稿不给筛查模型（10-24 实验：给了漏 5/29）；人确认后的标准给分流也给筛查（用户 10-27 决定 3）。
- 起草标准的模型只看问题；例句不自动进任何模型，人写进规则的原句随规则进判定（用户 10-27 决定 2）。
- 候选和范围只能收窄不能放大；阶段二重新校验范围。
- 客户 24 题仍只用于评价，不进任何例子、提示或测试。
- 不删 `_answer_legacy`（第 6 步），不动 `_ensure_answer` 的联网条件（第 4 步），只往保护清单加一个原因。

---

## 6. 需要你决定的（已定，2026-10-27）

S3-a（名单合一）Codex 已通过并已提交（b1e1f0b）。两阶段部分的三项产品规则用户 2026-10-27 已定（原话："A，B，B。不用怕循环论证，用户就是要找到自己想找的"）：

1. **接口和内部调用保留"不经人确认"的 auto 模式（选 A）。** `POST /api/v1/ask` 默认 auto；复合题子问、馆藏优先回退、`topic_compare` 等没有人看卡片的内部调用 auto；回答文字和记录里标明"标准由模型起草，未经人确认"；接口可显式要求两阶段（3.6）。
2. **人确认的规则里可以写进库里的原句（选 B）。** 例句点选变成规则文本框里的草稿行，人可改可留；服务端只记录规则里引用了哪些展示过的例句，不拒绝（3.3）。起草模型仍只看问题（用户 10-26 的原话未变）。
3. **人确认之后，筛查按确认后的标准找句子（选 (b)）。** 接受和编辑同一策略；改宽的篇目可进通过组，仍要逐字核对的句子；未经人确认的草稿（auto 模式）仍按原问题筛查（3.4a）。S3-e 按 (b) 复测，与 10-24 基线并列。

工程默认（不请示，可随时改）：卡片 v1 做接受、例句点选→草稿行、编辑、放弃四样；两阶段占访客 2 次问题；网页默认 `ask`；例句用词面重叠选；令牌 30 分钟。

---

## 7. 验收清单

- 免费，S3-a：金样本逐项一致（名单、引文、按角色计的模型调用次数与顺序、费用、记录），白名单外零差异，不改金样本；25 套件原样通过；新平行测试通过；门禁 pytest／Ruff 通过。
- 免费，S3-c：按调用角色计数——ask 模式确认前只允许起草调用，Decisions、逐篇筛查和后续付费处理为零，确认后才有；起草失败、分流关闭、引号短语题、关系提示题、父 ask + 复合名单子问、无效编辑（超过 4 条规则／3 条例外、空规则）各有测试且都不进入筛查；规则含展示例句→记录 `criterion_quotes_examples` 且照常判定；确认后的标准进入筛查提示且 `screening_basis` 正确，auto 的草稿不进筛查提示；令牌过期、跨访客、范围篡改、版本变化→明确失效且零模型调用；双击、并发、重试只启动一次判定；重启后登记缺失→失效不执行；执行中断的记录不被当新任务收费；同一标准重试复用结果、不同标准返回冲突；同一份确认标准经"接受"或"编辑"得到同一种筛查策略；小范围里检索排名之外的记录仍被判定；改宽／改窄标准确实改变三组结果；待确认回答经过 `Service.answer` 的完整包装（`_ensure_answer`、记录、`answer_runs` 持久化）后仍是待确认；起草模型的输入不含任何候选文本；`criterion_source` 四种值各有测试；接口两阶段往返。
- 人工：网页上走一遍两种范围（小范围全判、大范围只判候选），记录到 work.md。
- 完整免费门禁照跑；三项浏览器 JS 检查本机没有 Node 不能跑，照常单列为"未运行"，不因本设计没有新增 JS 而算通过。
- 付费（待批准）：S3-e 的三组数字与 10-24 基线（30／21／24）并列报告，不据此调阈值。

---

## 8. 复核记录

- 2026-10-27 Codex 计划复核（S3-c，依据内联设计节、计划与代码摘录）：范围认可，要求①接口／内部入口显式默认 auto，不继承全局 ask→`Service.answer` 的 None 一律 auto，网页 S3-d 显式传开关；②卡片覆盖承诺与实际执行一致，短语搜索追加的候选也要说明→`candidate_summary` 的 `with_rules`／`condition_only`／`phrase_hits`（3.9 实现说明）；计划稿本想只在分流开着时承诺小范围全读，提交前复核指出这是范围缩减，已按设计恢复：确认后 ≤ 400 篇全读、更大范围候选全读；③执行时再绑定数据版本，令牌保留原始范围和有效范围→`expected_version` 在检索前再核，令牌签 `scope` + 计划；④完整包装结束后才标 done→流程在 `_answer_question` 包装与审计保存后 finish／fail。边界：无规则确认记 confirmed 并保留条件种类与 `screening_basis=question`→已做；failed／limited 终态且费用如实→已做；回放复制最终结果并保留结构化结果引用的证据→已做；复合子问的“请单独提问”要经完整包装保留→原因进保护清单、回退不启动；问题规范化一致、登记表满员拒绝、修正 3.11 旧表述→已做。提交前复核见 work.md。
- 2026-10-27 Codex 计划复核（S3-b，依据内联设计节与计划）：要求①传入标准的调用其计划要能表达 ask，否则 plan_check 必报错，且 ask 缺标准不得退回 auto→计划加 `criterion_confirmation`，路线为带标准的调用建 ask 计划，ask 无标准返回明确拒绝；②`criterion_draft` 只记真正的草稿→已做；③"回答文字标明未经确认"留到 S3-c→本步正文不变；④`screen_with_criterion` 按"是否传入标准"决定，不看起草后非空→已做；⑤提示词不要把原问题变成额外门槛→改为"按确认后的标准判，引用满足规则的句子"，原问题的短语约束和逐字核对保留；⑥标准贯穿筛查、重读、分流关闭时的回退→已做并有测试；⑦`criterion_available` 只有一个含义→"本题会起草"；⑧白名单精确到新增字段并核对版本→已做。提交前复核见 work.md。
- 2026-10-27 用户定两阶段的三项产品规则（原话："A，B，B。不用怕循环论证，用户就是要找到自己想找的"）：1 接口和内部调用允许 auto 并标注未经人确认；2 人写的规则可以引用库内原句，服务端记录不拒绝；3 确认后筛查按确认后的标准找句子（(b)）。据此改了 0、3.3、3.4a、3.5、3.6、3.8、5、6、7 节和第 4 节的 S3-b／S3-c／S3-e 行。

- 2026-10-26 Codex 提交前复核第二轮（S3-a 实现，依据内联代码）：认可双库失败证据、关系父范围、单社交库字面、预算按预约记录、录制保护的修正；要求①两库保持旧调度（先起草，再各库各自准备并判定，不加全局准备屏障）→ 已改回，补金样本 `both_social_prepare_fails`；②单库失败快照去重→已改，补 `native_writer_limit`／`both_writer_limit`；③预算桩把被拒绝的预约单列为 denied→已改，`native_limit_reached` 重录；④停下的过期门禁不删报告→第二次停下的半截报告保留，最终门禁用新目录；第一次停下的已在收到意见前删除，work.md 如实记录。
- 2026-10-26 Codex 提交前复核第一轮（S3-a 实现，依据内联代码）：要求①恢复双库失败时的原有证据（不作为新差异列入）→已改；②关系提示只限单社交库→已改；③单库起草时机不能提前到计数和补全之前→已改；④关系名单用父范围 `filters` 而不是 `scopes[0]`（关系名单可与比较分组并存）→已改，补金样本 `social_relation_list_groups`；⑤单社交库字面名单不能顺带补账号→已改，补 `social_literal`；⑥补 >40 命中场景与 `first_read_by_dataset` 断言→补 `native_many_phrase`／`both_many_phrase`；⑦预算记录保留每笔预约的对应关系→按预约记录生命周期；⑧录制入口拒绝覆盖并核验基线→已加；⑨门禁未完成、JS 未运行不能报完成→照办。

- 2026-10-26 Codex 第二次计划复核（依据第二稿，工具通信失败、未读源码）：**S3-a 通过，可单独开工（只做冻结基线后的纯合并和列明的记录变化，不顺带启用确认流程）；两阶段未通过**，要点与处理：① 同一份确认标准不能因"接受"或"编辑"而用不同筛查策略，且要分清"名单 = 通过 ∪ 待审"与"改宽只进待审"→3.4a 改为两种一致策略，说明改宽的篇目仍在名单里只是进待审组；② ask 遇分流关闭改成 none 仍会进筛查，与验收矛盾；确认应覆盖所有要模型逐篇判定的名单（含引号短语题、关系提示题）→3.1、3.5 改为"逐篇判定之前一律先停"，卡片写明将用的判定条件；③ 复合子问和回退不能把父请求的 ask 自动降成 auto→3.2 改为 ask 随父请求传下去，不支持续问处就明确返回待确认；④ 防重放缺失效规则→3.5 补 pending／judging／done 的状态机、重启或过期后不执行、不同标准冲突、执行中不清除；⑤ 例句例外未获准→3.3 改为点选只做记号、不预填原句、服务端拒绝含例句的规则；⑥ 3.8 用 `flow_id` 关联；⑦ 验收补：全模拟基线、每库顺序比较不锁线程交错、分流关闭／起草失败／引号题／父 ask + 复合子问、重启／TTL／中断／同标准重试／不同标准冲突。

- 2026-10-26 Codex 第一次计划复核（依据第一稿，工具通信失败、未读源码）要点与处理：① 例句追加进分流判题仍是模型看了例句→改为默认例句不进任何模型，点击只生成人可编辑的草稿行，是否允许人保留原句交你定（6.2）；② ask 模式不能因分流关闭、起草失败、规则为空而悄悄退回筛查→写明三种情形的停法（3.5）；③ 确认后的标准如何控制名单不清→新增 3.4a，给出 (a)／(b) 交你定（6.3）；④ 阶段一还有代理和嵌入费用→改说法（第 0 节）；⑤ 待确认状态要统一的类型标记并列出所有消费者→3.2 的 `pending_confirmation` 与消费者表；⑥ 签名不防重放→`flow_id` + 进程内 `FlowRegistry` 原子登记，失效不自动重起付费流程（3.5）；⑦ 全读要集合级保证、阈值按库算、阶段二候选一致性→3.9、3.5；⑧ 差异表补调用参数、跨库去重、字面后处理、部分失败、费用结算→2.2，`first_read` 只是记录改对；⑨ 验收要冻结旧实现对照、按角色计调用、防重放和改宽改窄生效的测试、JS 不豁免→2.4 金样本与第 7 节；⑩ 需要用户澄清的只有接口 auto 模式一项→第 6 节收成三项产品规则，其余按默认。
