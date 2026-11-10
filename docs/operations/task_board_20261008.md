# Project work board

Snapshot cutoff: 8 October 2026, 18:34 America/New_York. This is a repository copy of the local task organization, ready for team review. It does not indicate that Notion has been updated or that management has approved completed work.

A later isolated retrieval-evaluation pilot is in progress. Its local scoring adapter and runtime harness were prepared after this cutoff and are excluded from this upload. The rows below retain their snapshot scope; they do not describe the later pilot as unstarted or claim its results.

The 35 original tasks retain their IDs. Seven retrieval-evaluation tasks and four scoped deliverables are listed separately; child cards do not close their parent tasks. Work that starts after this snapshot belongs in a later update.

Owner, reviewer and due date are unassigned unless a separate confirmed record exists. Reviewable means the current scoped material can be inspected; remaining validation is shown in each row.

## Backlog

| ID | Task | Current scope | Next step |
| --- | --- | --- | --- |
| T02 | 确认本期范围及范围变更 | 本期范围及后续变更仍有待确认事项。 | 记录正式范围决定、来源及未纳入项。 |
| T03 | 确认广告计数和实体口径 | 公司、协会、会议组织、日期及广告计数口径尚未全部确认。 | 确认统计单位和实体规则；据此验收。 |
| T04 | 获得正式社交数据及字段说明 | Twitter资料已收到并导入；待确认付费身份、字段口径及Facebook/Instagram范围。 | 补齐或明确不纳入的材料，记录客户口径。 |
| T05 | 获得原型访问并记录参考结论 | 参考原型的访问与结论仍缺完整交接记录。 | 整理可访问入口、参考结论及无法访问项。 |
| T14 | 展示数据支持的主题探索 | 已有历史主题标签可探索；标签解释和可发布边界待确认。 | 明确哪些标签可展示及其来源、审核状态。 |
| T15 | 确认知识图谱的实体与关系定义 | 图谱已实现来源记录关系；实体与关系含义待客户确认。 | 确认公司、协会、会议和媒体关系定义。 |
| T26 | 完成人工语义与客户任务验收 | 客户任务验收仍未完成；24题全量人工标注已移出当前执行。 | 后续确认验收安排；沿用参考须注明实际AI辅助来源。 |
| T27 | 确认并验证真实规模性能 | 已有本地真实社交范围性能检查，生产规模和客户性能目标待确定。 | 确认运行环境与目标，测试真实入口的耗时和失败。 |
| T28 | 复核部署配置与完整恢复 | 有阶段性部署和安装记录，当前完整恢复及异机复现未验收。 | 核对应用版本、数据和配置，完成恢复与接手验证。 |
| T29 | 收口技术文档和用户交接 | 架构、操作说明及汇报材料已有，最终独立交接未完成。 | 对齐最终发布版本，由接手者验证运行和维护。 |
| T30 | 记录未来动物农业与可选主题边界 | 动物农业为原文未来扩展范围，不列为当前必做开发。 | 确认并保留范围边界，避免误计本期完成度。 |
| T32 | 确认来源链接与归档展示规则 | 原文和附件入口可配置；完整归档覆盖及展示规则待确认。 | 明确可展示材料、缺失状态和归档边界。 |
| T33 | 完成最终双数据集演示与签收 | 最终双集合演示及签收未完成。 | 完成必需前置或记录正式范围调整，再进行最终演示。 |
| RE03 | 建立检索相关性标注集 | 尚未创建真实分级相关性标注集。 | 核对可复用资料，构建缺失问题与来源相关性表。 |
| RE04 | 接入检索评分器与排序记录 | 标准评分器和分阶段真实排序捕获尚未实现。 | 接入NDCG等指标，验证重复、缺标、空结果和名次。 |
| RE05 | 运行检索基线与对照 | 尚无新规范下真实NDCG成绩。 | 依赖RE03/RE04，冻结后运行，保留失败和标注覆盖。 |
| RE06 | 测试运行网页的实际回答 | 现有进程内测试不能代替部署网页实测。 | 冻结服务版本与范围，核对答案、引用、拒答、耗时和费用。 |
| RE07 | 评价报告与客户确认 | 需等待RE05/RE06的实际结果。 | 提交可复现结果和限制，另记客户确认。 |

## In Progress

| ID | Task | Current scope | Next step |
| --- | --- | --- | --- |
| T06 | 维护完整数据及质量清单 | 已有数据质量和全文覆盖检查；仍需保持当前版本及缺失材料清单一致。 | 更新两集合质量清单，核对版本和未覆盖项。 |
| T07 | 完成共享及专属字段映射和数据字典 | 字段字典和共享模型已有；来源身份及部分口径仍需收口。 | 核对当前字段、接口与客户确认的口径。 |
| T08 | 复核原生导入与更新管线 | 原生导入、正文更新有阶段性工程记录。 | 固定当前版本复核新增、更新和来源回退。 |
| T09 | 实现真实社交导入与更新管线 | 真实社交资料已本地导入，并保留唯一帖子与观察记录；不再标为尚未入库。 | 复核更新、重复、冲突与部署版本；付费身份单独确认。 |
| T17 | 复核广告详情与原文材料呈现 | 正文、原始链接及已有附件入口存在，材料覆盖仍不完整。 | 复核缺失、失效链接及可用附件显示。 |
| T18 | 完成真实社交筛选和可视化 | 本地社交筛选和公司帖子探索已有实现，不再标为未接入。 | 验证账号、平台、日期、标签及导出；记录客户使用反馈。 |
| T20 | 修正自然语言统计与关系问题路径 | 统计与关系查询持续改进；10月8日本地修复已单列送审。 | 审核修复后冻结新版，验证真实问题理解与调用效果。 |
| T21 | 复核RAG输入索引与检索路线 | 保存正文检索覆盖已检查；检索相关性、排序及跨集合表现仍需评价。 | 完成RE03–RE05，区分关键词与混合检索。 |
| T22 | 复核有据回答和无证据处理 | 引用约束、缺资料和服务失败处理已有；新修复未做模型效果复测。 | 验证语义支持、误拒答和外部补充的展示边界。 |
| T23 | 完成社交与跨数据集RAG | 社交与跨集合工具路径已有，已跑过模型评价；实际问答仍有失败。 | 针对通用原因改进并冻结实测，不把工具存在当整链通过。 |
| T24 | 维护模型只读工具和MCP扩展契约 | 只读工具、范围和原文版本检查已有；当前候选代码需复核交接。 | 核对工具契约、越界拒绝和最新修改的发布范围。 |
| T25 | 建立版本化开发与独立评价题库 | 冻结题集与自动评价已有；新增检索评价另见RE01–RE07。 | 维护版本与来源，保留全部失败；不恢复24题全量人工标注安排。 |
| T31 | 推进CLAIMS最小审核接入 | CLAIMS来源审查、导入/读取接口已有；获准分类发布尚未完成。 | 绑定文章、正文和分类版本，复核后离线发布合格项。 |
| T34 | 建立每周会议和异步反馈闭环 | 本轮整理五阶段看板与同步规则；外部Notion/GitHub尚未写入。 | 登记真实看板链接、会议决定和任务更新，确认维护角色。 |
| T35 | 复核指定GitHub仓库、代码与发布记录 | 10月8日已有版本发布成功；后续本地源码和PPT并未全部推送。 | 审核最新候选，分别核对GitHub与实际应用版本。 |

## Ready for Review

| ID | Task | Current scope | Next step |
| --- | --- | --- | --- |
| T01 | 建立可追溯的客户需求目录 | 目录、来源和旧35项台账已建立；旧工程完成记录保留，尚无管理人员Done确认。 | 审核目录与本次状态映射；管理人员确认关闭。 |
| T10 | 复核公司与媒体数量及占比矩阵 | 公司×媒体统计、占比矩阵及选定范围对账已有。 | 审核当前范围下矩阵、导出和完整名单一致性。 |
| T11 | 验证公司到全部媒体的探索路径 | 公司到媒体探索已实现，选定关系和记录已有核对。 | 代表用户验证完整媒体名单及记录入口。 |
| T12 | 验证媒体到全部赞助方的探索路径 | 媒体到赞助方探索已实现，选定关系已有核对。 | 代表用户验证赞助方名单、数量与具体文章。 |
| T13 | 验证日期和组合筛选 | 日期和组合筛选已有实现与工程检查。 | 审核未知日期、并列、两时段及组合范围。 |
| T16 | 复核图谱每次点选的具体关系和图表 | 图谱点击关联分布和文章已有，部分具名关系已验证。 | 审核不同节点、边及筛选后的对应名单，而非只看总数。 |
| T19 | 复核导航和非计算用户体验 | 导航和探索界面已有可审阅原型。 | 代表用户完成查询、关系探索与来源查看，记录困惑。 |
| RE01 | 检索与问答评价规范 | 方法、指标和来源已登记；文档结构检查通过。 | 审核定义、分母、未标注和失败处理。 |
| RE02 | 评价输入输出模板 | 6份空白CSV和运行清单已准备并校验。 | 审核字段后用于构题、标注及实际运行。 |
| T20-FIX-20261008 | 本轮查询修复与代码审查 | 本地4477项通过、8项跳过；未进行这批修改的真实模型复测或发布。 | 审阅日期范围、记录ID传递、别名、校验和失败提示；确定后续复测。 |
| T25-RUN-20261008 | 本轮模型评价报告 | 固定版本278题运行与自动评分已有；不是人工审定准确率。 | 审核参考来源、分子分母、未答原因和具体失败；不套用到后续代码。 |
| T29-DECK-20261008 | 客户汇报与工程指标说明 | 客户PPT v11及英文工程页EN_v2已生成；管理/客户审核待记录。 | 审核用词、流程、指标含义和示例，确认对外版本。 |
| T35-PUBLISH-20261008 | 已有版本GitHub与Pages发布核对 | 保存回执为原库d33b256、公开库17807e4，CI/Pages成功；不含后来修改。 | 审核已发布范围并登记管理确认；最新应用版本另核对。 |

## Ready for Merge

No confirmed entries. Review and management decisions are recorded separately.

## Done

No confirmed entries. Review and management decisions are recorded separately.

## Update rules

Follow [Git collaboration](git_collaboration.md). Preserve the original source and completion criteria; update current scope, blockers and links after each change. Customer questions and private source documents remain outside the public board.

The scheduled full human annotation of the customer question set was removed from current execution. New retrieval-relevance judgments are a separate task. AI-assisted references retain that provenance.
