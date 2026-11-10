# 独立语义编码手册 v1


冻结日期：2026-10-08。版本：`semantic-support-v1`。本手册是来源独立的工程规则，具名人审者待定，真实材料人审 **0**，客户批准 **未取得**，初始状态 **unreviewed / 非gold**。

任务范围：对候选答案的每条命题判断来源支持程度，分别记录文中提及、表达主体及推广立场、外部真伪。原生12项与社交13项历史标签缺少完整已审核定义，仍是未审核辅助；本手册没有把它们升级为完整客户codebook。

本次没有读取客户24题、参考、改写或逐题输出。下列例子全部独立虚构，不是客户题或真实评价结果。既有历史暴露另有记录，本轮不宣称整个项目从未见过测试。

## 一、冻结规则


### S1 supports：完整支持


同一主体、时间、范围、数量、条件和模态都得到原文直接支持或明确无跳步蕴含。保留可能、试点、引述等限制。支持来源陈述不等于证明外部真伪。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 银鹭实验室说：“试点可能减少用水。” | 银鹭实验室称试点可能减少用水。 | supports | 完整保留表达主体、试点范围及可能性。 |
| 银鹭实验室说：“试点可能减少用水。” | 试点已经保证减少用水。 | unsupported | 可能被改成保证，额外确定性没有依据。 |



### S2 partial：部分支持


复合命题有可定位的实质部分得到支持，但至少一项必要部分缺失或范围被夸大。列出支持部分和未支持部分；已明确冲突的部分必须单列矛盾，不用部分支持掩盖。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 桃湾园区在东楼安装了计量表。没有提供西楼资料。 | 桃湾园区东楼和西楼都安装了计量表。 | partial | 东楼有据；西楼未提供。 |
| 桃湾园区在东楼和西楼均安装了计量表。 | 桃湾园区两栋楼都安装了计量表。 | supports | 两项必要事实均被说明。 |



### S3 unsupported：证据不支持


来源可读取且身份范围明确，但不能支持命题的任何必要实质部分。主题相关或词项出现不足以支持因果、数字或立场。限定为所供材料内无支持；不能据此推断现实世界为假。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 岸松社介绍了一个雨水收集装置。 | 装置使成本下降了一半。 | unsupported | 没有成本、基准或比例依据。 |
| 岸松社介绍了一个雨水收集装置。 | 本文提到了雨水收集装置。 | supports | 限定提及命题有明确文字。 |



### S4 contradicted：明确矛盾


相同主体、对象、时段、范围和定义下，来源明确否定或给出不能同时为真的事实。指出冲突原句；未提及、范围不同、旧新版本不同不直接算矛盾。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 蓝铃协会说明：“本次试验没有测量排放。” | 本次试验测量了排放。 | contradicted | 同一次试验的有无测量直接冲突。 |
| 蓝铃协会说明：“去年没有测量排放，今年已开始测量。” | 今年开始测量排放。 | supports | 去年与今年不应混为同一时段。 |



### S5 uncertain：无法可靠判断


关键身份、来源完整性、表达指代或适用范围未解决，因而不能确定支持关系。写出缺口及所需材料；不要强行转成不支持或反对。未知独立于无结果。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 原句只保存为：“他们在该处……”，后文缺失。 | 北岚工坊在那里建成了项目。 | uncertain | 主体、动作及位置均不可定位。 |
| 北岚工坊明确说项目尚未建成。 | 北岚工坊项目已经建成。 | contradicted | 材料完整且明确冲突，应判矛盾而非不确定。 |



### L1 提及层


mentioned要求在所声明来源范围内有确切词项、概念或经人工说明的同义表达；not_observed仅表示完整所供范围内未观察到，必须保存该范围和提取限制。相关链接、标题与正文分开；未读图片或视频保留未知。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 正文：“我们安装了屋顶集水槽。” | 该段提到雨水收集。 | mentioned | 有清楚的概念表达；保留原句说明同义判断。 |
| 正文只谈水泵；相关链接标题为“集水槽指南”。 | 正文提到集水槽。 | not_observed | 链接提及不能转为正文提及；声明只审完整所供正文。 |



### L2 表达主体与推广立场层


分别记录谁表达、文章如何处理、该表达的favorable/opposed/neutral/mixed/uncertain。引述某公司积极宣传不自动等于作者认可；广告身份或公司名称也不能推断立场。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 暮鸢公司称装置“值得推广”；作者接着质疑其证据。 | 暮鸢公司积极推广该装置。 | favorable | 表达主体是公司；文章处理为quotes_distances。 |
| 暮鸢公司称装置“值得推广”；作者接着质疑其证据。 | 作者认可该装置。 | unsupported | 公司引述与作者态度不可互换。 |



### L3 外部真伪层


默认not_checked。只有另外提供、版本和原句可定位且对同一命题适用的独立核实材料，才可记录corroborated/refuted；冲突或不足用uncertain。原文中的主张、历史标签和引用位置不算外部核实。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 榆舟团队宣称其装置节能30%；未附独立核实。 | 现实节能幅度已被核实为30%。 | not_checked | 仅知道团队声称，不足以核实效果。 |
| 另附虚构独立测试报告，记录同装置同条件节能30%，范围明确。 | 该条件下的30%节能得到独立报告支持。 | corroborated | 须引用单独external_evidence来源及范围；本例仍是虚构教学材料。 |



### P1 原文与位置绑定


保存record_id/version_id/body_hash；社交观察额外保存三项观察绑定。所有quote必须严格等于body[start:end]，坐标为Python Unicode字符半开区间，不跨缺口、不改字、不换成显示正文。每条原句保存表达主体和文章处理方式。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 原文：苔鹿站说“可能改善”。候选引文定位到“可能改善”。 | 原句与精确字符切片一致。 | valid_locator | 可能一词保留，使用该正文的Unicode字符坐标。 |
| 原文：苔鹿站说“可能改善”。候选引文写“已经改善”。 | 把改写当原句保存。 | invalid_locator | 程序拒绝不匹配切片；语义判断不能修补原句。 |



### P2 逐命题与总体范围


先将候选答案拆为稳定claim_id，逐条编码；保留候选摘要、证据、限制。完整名单、总数或否定全库命题需要可对账完整成员及范围，top-K片段不能证明。v1不将状态加权为一个自动总体准确率。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 完整给定虚构范围只有两份记录，IDs均核对；两份均出现仪表。 | 这个给定两份记录范围都提到仪表。 | supports | 范围及所有成员齐全且逐项可审。 |
| 检索只返回两条提到仪表的片段；完整库大小未给出。 | 所有记录都提到仪表。 | uncertain | top-K不建立全库范围或完整成员。 |



### B1 双人盲标与第三方裁决


A/B是不同具名真人，独立保存且看不到对方标签；裁决者第三人，双方完成后读取当前审核哈希并说明裁决理由。AI不冒充真人。历史12原生/13社交标签只作未审辅助，默认不展示给盲标者；不得当完整codebook或客户批准。


| 虚构来源 | 候选命题 | 判断／边界 | 理由 |
| --- | --- | --- | --- |
| 两名独立真人提交后，第三人引用双方审核哈希解释分歧。 | 独立双标流程完成。 | eligible_for_adjudication | 仍非gold，客户和语义验收另行记录。 |
| 同一个AI角色先写A再改名写B，或B看过A标签。 | 形成两份标签就算真人独立审核。 | invalid_blind_review | 不是具名真人独立双标；不得报真人一致率。 |



## 二、结构化审核契约


机器契约及全部规则保存在 [semantic_codebook.v1.json](../../eval/semantic_review/semantic_codebook.v1.json)。其中 `packet_schema`、`review_schema`、`adjudication_schema` 与 [运行模块](../../src/observatory/semantic_review.py) 的Pydantic schema逐项绑定；字段漂移会拒绝打开审核包。

- 审核包保留来源literal body、record_id、version_id、body_hash；社交观察三项source_observation_id/source_version_id/source_body_hash须同时出现。正文UTF-8 SHA-256须相等。提供这些字段不自动验证网页完整性或来源身份。
- 候选保存task、稳定claim_id、命题层、摘要、证据、限制、明确source_scope和提取限制；status只能unreviewed、gold只能false。
- 每个审核覆盖每条claim恰好一次，保存support、mention、stance、external_truth、审核摘要、理由、限制和原句。原句含来源ID、字符[start,end)、expression_subject与article_handling。引用不等于正文切片则拒绝。
- supports/contradicted必须附原句；partial/unsupported/uncertain必须说明限制。corroborated/refuted须引用单独external_evidence材料，不能以原文自述证明外部真伪。
- 每份审核绑定冻结packet/codebook SHA-256、真人reviewer_id、human类型及独立真人声明。AI不是允许的审核者类型。

## 三、实际可保存的本地流程


独立程序复用项目已安装Pydantic及Python HTTP组件，未改变主app、8070服务或主业务数据库。入口 [serve_semantic_review.py](../../scripts/serve_semantic_review.py)，默认本机8072，仅127.0.0.1。

```powershell
# 空人审状态；未给 --packets 时仅准备一个明确标记的虚构演示
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo init
# 另有来源独立材料时，init --packets path/to/packets.jsonl，使用一个全新store目录
# 下列占位ID须替换为三名已指定真人；不要以AI或同一个人补足人数
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo assign --reviewer-a PERSON_A --reviewer-b PERSON_B --adjudicator PERSON_C
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo links
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo serve --port 8072
```

协调员将links输出分别交给对应真人，不公开带token的链接。先打开 [本机演示表单](http://127.0.0.1:8072/demo) 或 [状态入口](http://127.0.0.1:8072/)。角色待定、真实人审0。演示使用虚构材料，可单独保存synthetic_demo日志，不进入A/B，不计人审。入口页面提供操作说明；各私有审核页面按命题展示自然语言标题；用下拉选择支持程度、提及、立场及外部真伪，填写审核摘要、理由、限制、表达主体及文章处理方式。选择来源并粘贴原句，程序逐字匹配、自动填写精确Unicode字符位置；相同原句出现多处时选择上下文。完整原文可折叠展开。高级JSON只在折叠面板中查看，主要操作无需手写JSON。填写后点击保存。浏览器保存会实际POST到独立审核store，追加到A/reviews.jsonl或B/reviews.jsonl并fsync。导出原始日志保留旧审核，不覆盖；冻结来源文件或schema变化会拒绝保存。盲标页面隐藏历史辅助标签并且不能读取另一人的审核。

第三方只有双方独立审核保存后才可进入该case；页面显示双方标签而隐藏其真人身份。裁决必须写理由，绑定两份最新审核hash；原双标日志保留。其后任一审核修订会让旧裁决显示stale，需要再次裁决。任何保存或裁决均不自动成为gold或客户验收。

```powershell
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo status
python -X utf8 scripts/serve_semantic_review.py --store .runtime/semantic_review_20261008/review_demo export --destination .runtime/semantic_review_20261008/export_NEW
```

export目录必须全新。协调员CLI导出A、B、裁决完整追加JSONL和agreement.json；没有向A/B提供共同导出HTTP端点。匿名主页不显示审核结果、来源或私有链接。这个本机应用没有组织账号验证；指定真人身份和独立性由协调员登记及审核者声明，本轮真人尚未指定。

## 四、一致性计算与完成判断


单位为case_id＋claim_id，使用同一冻结版本的A/B最新完整审核。support五类是名义分类，uncertain不删除也不并入unsupported。每条轴分别报告混淆计数、标签边际、匹配数、双标单元数、原始一致率及Cohen κ。p_o＝匹配数/n；p_e＝ΣA边际比例×B边际比例；κ＝(p_o−p_e)/(1−p_e)。没有双标或p_e＝1时κ为null，不写0或满分。

同时报告总case/claim及已双标case/claim；未审核单元仍在覆盖分母。裁决单列，不回改原A/B一致率。没有批准参考时human_accuracy为null，一致率不能替代正确率。合格阈值、客户语义定义和接收标准均TBD。

当前完成的是11条操作规则、22个虚构正反/边界例、三种schema、可保存盲标/裁决/导出程序和免费工程验证。真实来源编目、三名具名真人、独立标注、裁决、正式gold以及客户验收均待办；不把演示保存或自动测试当真实人审。

## 五、冻结指纹


规则JSON文件字节SHA-256：`2750f6852d5ea35a12ef73842e9b4c146db44fea832490b272902d3068e09740`。修改规则或schema须另建v2，不原位解释为仍是同一冻结版本。每个store保存codebook.frozen.json、packets.jsonl和manifest.json；摘要绑定原句及来源版本。
