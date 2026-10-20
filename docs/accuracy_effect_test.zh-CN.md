# 本轮准确率改动的成效测试

日期：2026-10-07，纽约时间。来源：用户U23“继续，先做测试看看成效”。这是开发诊断，不改变客户要求。

## 要回答什么

1. 在相同证据下，提示v6是否更完整、忠于原文。
2. 当前数据库能否找回指定的实际材料；检索状态与来源定位是否正确。
3. 每次调用、引用、费用与版本是否留下可核查记录。

## 方法

- 提示比较：16道冻结的新开发题，每题旧v5／新v6各答一次，模型gpt-5.6-luna，reasoning none，最多1,600输出token，自动重试0。相同证据、schema、后处理和参数，只有系统提示不同；每题交替先后次序。
- 参考隔离：AI参考单独保存，不传给模型。必要、可选及禁止回答点先冻结；另一代理只看X／Y匿名输出，评分后才还原提示版本。
- 判定：所有必要回答点满足、无禁止内容、引用支持回答，才记该题完整通过。遗漏、无依据、合理弃答、冗余分别记录。语义评分是AI辅助，具名人审尚未进行。
- 实际检索：按来源质量和集合选16份实际材料，执行54个固定关键词／标题／账号／空范围请求。已知目标是否找回是检索诊断，不是所有相关广告的召回率；目前没有可复现的旧检索对照。
- 费用：本轮明确获准上限2美元，32请求按项目计价保守预留0.204035美元。项目价格已与本轮查询的[OpenAI官方价目](https://developers.openai.com/api/docs/pricing)核对，实际费用按服务返回token含缓存读写计算，不能当作供应商账单。

## 实际材料检索结果

在当前活动索引`sentence600-social-observations-v1`上执行54次只读工具请求。16份材料包含8篇原生广告和8个社交帖子；来源是按质量分层的确定性样本，尚无人审相关性标准。

| 查询方式 | 请求及目标资格 | 找回指定目标 |
| --- | --- | --- |
| 保存原话词组 | 16个合格目标 | 13/16 |
| 从正文抽词，剔除元数据字段词 | 16个合格目标 | 12/16 |
| 原生标题 | 8个目标 | 8/8；其中1次返回名称歧义候选，未静默选定 |
| 社交账号内检索 | 8次；2个目标因规范账号冲突不属于当前筛选 | 5/6个合格目标；2个排除目标未越界返回 |
| 控制 | 6次空范围、未索引和明确记录范围等 | 6次符合预设行为；具体状态单列 |

8次目标未找回涉及5份不同材料，不能写成8篇文章。46次正文工具搜索的状态为complete 31、partial 11、empty 4、failed 0；另8次标题查找不使用search_status。complete表示搜索执行完整，不表示相关来源都找回。

187次返回来源的文本、位置、哈希核对均通过，涉及141个不同片段；另作187次当前版本及筛选成员核对，越界0。前后数据及统计版本稳定。这验证返回材料绑定，不证明搜索排名或生成语义正确。另2项掩码筛选检查通过、受保护文件读取0。

### 具体漏召回

1. **PETRONAS《Building On An Innovation Legacy Toward A Sustainable Future》**：查询`decarbonization petrochemicals transformation`没找回已知合格目标。保存原句含“a dynamic transformation anchored by its mission to deliver energy responsibly and sustainably”。返回竞争结果包括《How shale brought new growth to the petrochemical manufacturing industry》与《Energy Trilemma》。已确认查询按OR执行；竞争匹配与排名挤走目标是疑似原因，尚未追踪目标完整名次。
2. **ExxonMobil Australia帖子1034269953640153088**：原句是“Esso Deepwater Gippsland is drilling two exploration wells in Bass Strait as part of its investment program to find and bring online new #gas supplies.” 查询`Deepwater Gippsland is drilling two exploration wells`仍未进前5。精确词组在当前社交范围只能匹配这一个帖子；OR检索却返回其他帖子。已确认目标缺失，排名机制的具体贡献待追踪。
3. **U.S. Borax帖子1403404248193327109**：在其账号内搜索保存文字`the big B! (That's #boron) https://t.co/kXAkITtmeV`未找回。查询含短链URL，并不是审定的纯内容问题；单列为诊断局限，保留结果，不删病例重测来提高分数。

完整原句区间、原始查询、来源版本和竞争结果见[漏召回材料](../.runtime/accuracy_effect_test_20261007/retrieval/mismatch_examples.json)及[结果汇总](../.runtime/accuracy_effect_test_20261007/retrieval/summary.json)。当前没有旧检索对照，不能报告召回率提升。

## 调用与费用审计

32次调用已完成，实际用量计价0.01003420美元，未结算请求0，源码指纹保持不变。测试账本库已停止并保留。

独立审计逐条对齐32次尝试、32份HTTP、32份SDK解析、32份结果和32项账本；用token含缓存读写费用复算与账本一致。SDK序列化警告未造成所检查字段丢失。28次返回回答、4次返回证据不足，这些是运行状态，不是准确率。

28份引句均可在冻结合成正文定位，Evidence的记录、版本、hash及Unicode字符位置一致。Citation可选的来源版本／正文hash字段为空；不外推为真实社交来源观察的完整绑定。没有独立连接数据库核对`generation_outputs`表，只核对持久化文件与账本导出。

| 提示 | 请求 | 用量计价 | 延迟中位数 |
| --- | --- | --- | --- |
| v5 | 16 | 0.00497288美元 | 2.1015秒 |
| v6 | 16 | 0.00506132美元 | 1.898秒 |

缓存及调用次序影响费用和延迟，不能把这两个差异归因于提示词质量。[审计报告](../.runtime/accuracy_effect_test_20261007/audit/README.zh-CN.md)附所有检查、token分项与限制。

## 模型语义结果

**本轮看到来源表述改善，尚未看到核心内容失败被修复。** 32份匿名AI评分冻结后揭盲：

| 指标及定义 | 旧v5 | 新v6 |
| --- | --- | --- |
| 完整通过冻结规则：必要内容正确且没有待审来源描述；含合理弃答／有界回答 | 13/16 | 15/16 |
| 明确未通过 | 1/16 | 1/16 |
| 核心内容正确、额外来源表述待审 | 2/16 | 0/16 |
| 覆盖原文中可回答的全部必要内容 | 15/16 | 15/16 |
| 完整完成题目要求的事实任务；不含资料缺失导致的合理弃答／部分回答 | 12/16 | 12/16 |
| 错误拒答 | 1/16 | 1/16 |

成对结果：13题两组均通过，1题两组均失败，2题从旧提示“待审”变为新提示“通过”。**明确失败→通过0题、通过→明确失败0题**。13→15是AI审查状态改善，不能直接写成事实准确率提高12.5个百分点，更不能称总体准确率。

### 改善的具体例子

- **画廊开馆日期通知**：原文“The gallery opened on 4 May 2024.” 两组日期都正确。旧提示称“The advertisement states”，新提示称“The notice states”。冻结规则把旧的额外广告身份描述列为待审；新回答贴合合成通知的来源类型。不是日期答错被修复。
- **Cedar／Maple图书馆开放计划通知**：输入只有一份合并材料。旧回答分别称“The Cedar Library notice”“The Maple Library notice”，新回答明确“The same comparison notice”。两组都正确保留五月／检查、七月／员工培训及计划状态；新表述减少了来源数量歧义。旧表述也可能只是沿用问题的复数说法，所以保留待审，不强判事实错误。

### 仍失败的具体例子

**图书馆检查与估计通知**，问题“What does the library notice say about opening and inspection?”：

> If inspection passed, the curator would issue an opening estimate on Monday. No estimate has been issued.

两组实际回答均是：

> The selected records do not provide sufficient evidence to answer this question.

原文可以回答：检查通过是发布开放估计的条件；目前尚未发布估计。模型不应编造开放日期，但也不应抹去这两个已知事实。原始HTTP已返回`insufficient_evidence`及空claims，因此不是数据库未提供材料或引句定位丢失；模型为何选择该状态，以及提示／状态限制的影响，仍未分离验证。

预期解决：按问题的各部分区分已知事实、明确未知和无相关材料，允许有依据的有限回答，标出未回答部分。加入新主题的正反例与正确弃答，先作免费合同检查，再另冻开发集测整个调用流程。不能只把这一题改成必答。

### 同样通过的例子

学校原文“The school approved the building plan but did not complete the survey.” 两组都保留“批准计划、没有完成调查”，没有把批准写成建设已完成。这个例子验证两组在本次材料上的表现，不证明v6在该能力上优于v5。

## 下一步

1. 先追踪实际漏召回目标的名次及各词贡献，比较稀有词／短语覆盖和当前OR排序；保持筛选、来源定位与Top5评价一致。
2. 独立建立可审查的内容查询；保留本轮短链查询限制，不删失败来提高分数。帖子与来源观察分别定义计分单位。
3. 修“能答一部分却整题拒答”的通用行为，保留正确拒答对照。
4. 新开发题上测模型选择工具、MCP和真实SQL的完整路径。本轮固定证据对照没有测这些组件，因此不声称已解决SQL模型路由准确率。

具体执行项已记入plan.md的P48；新模型运行、主库变更和发布不属于本轮32次费用批准。参考与最终审核角色仍待定。

## 审核目录

[本轮完整目录](../.runtime/accuracy_effect_test_20261007/root/README.md)保留冻结材料、实际请求、原始HTTP、每题结果、账本、匿名评分和实际检索材料；[逐题阅读版](../.runtime/accuracy_effect_test_20261007/root/review.zh-CN.md)以具体中文标题并排显示原文、旧／新回答与必要内容检查，机器评分原件不改。

客户24题本轮不读取、不运行、不用于调试。历史暴露记录保留。小样本、合成材料、单次生成与AI参考均限制结论；不报告总体准确率或客户验收已完成。本轮没有发布、改主库或重新建立索引。
