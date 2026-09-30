# Michelle 反馈：项目要求、线上状态与修正重点

日期：2026-09-29，America/New_York。范围：用户转贴的客户邮件、FA26 要求提取稿、实施反馈修正前的本机代码，以及 Railway 的只读 HTTP 检查。产品差异记录修正前基线；下方记录数随后在团队启动既有本机数据库后通过 Service／SQL 重新核对。此审计没有向客户发送信息、执行付费模型调用、启动数据库或修改产品代码。

## 判断

这次反馈首先要求把已有统计变成用户能找到、能直接使用的研究入口。客户已经给出了三个明确的真实问题：NYT 广告数、ExxonMobil 所列媒体、Washington Post 所列赞助方。不应再把索要问题清单作为修复它们的前提。

修正前本机代码已有完整 sponsor × publisher 数字矩阵、完整交叉表、筛选后的数量／比例及年度柱状图；缺的是公司与媒体的双向入口、清晰的操作结果，以及自然语言问题通往数据库统计的路径。单篇文章来源图谱有审计价值，但不能代替“某公司涉及哪些媒体”的全库聚合。客户是否使用饼图是设计询问，不是要求必须采用饼图。

最直接的修正是：在 Overview 明确提供 **Explore a company** 和 **Explore a news outlet**，选择一个对象后显示所有对应对象的横向条形图、精确数值和可进入的记录列表；完整矩阵用于比较多个对象。每张图写明当前筛选范围、计数单位及分母。无未知日期、未知 sponsor、协会／活动等值时不得静默删除；有这些值时明确说明。

## 2026-09-29 已完成的本机修正

- **Overview** 顶部加入 **Explore a company or a news outlet**。可从 **Company / sponsor** 查看所有所列媒体，或从 **News outlet** 查看所有所列 sponsor／organization。条形图直接显示数字，**View every count as a table** 展开完整计数；不截取 Top 10。点击条形或使用 **Show records for**，就在旁边查看对应文章，每页 10 条，支持翻页和正文详情。当前日期及其他筛选继续生效。
- **Query** 的三个示例只填入输入框，用户点击 **Generate answer** 后才提交。支持的数量和公司／媒体列表问题已路由到只读数据库统计，显示 **Collection statistics · no model charge**、实际筛选范围、全量类别计数与可检查的记录示例；内容解释继续使用有原文引用约束的付费生成流程。
- 统计计算涵盖当前范围内全部 `active AND countable` 记录，包含没有可检索正文的记录。列表的完整类别计数与最多 10 条示例记录分开呈现，示例数量不充当统计分母。未知日期、附加问题条件与缺失正文覆盖明确显示。
- 公司／赞助方保留来源字段身份，协会／活动不被改成公司；商业合作和付款关系不由字段值推断。历史自动标签仍有未审核状态，尚不能回答经验证的“哪些广告包含漂绿主张”或其总量。

真实本机数据库验证见 [michelle_statistics_smoke_20260929.json](michelle_statistics_smoke_20260929.json)：状态 `passed`、`no_model_calls=true`，NYT 问题返回 19 条，ExxonMobil 问题返回 4 个媒体／15 条，Washington Post 问题返回 7 个来源所列组织／18 条；`NYT in 2021` 返回当前集合的 0 条，默认全集返回 263 条。漂绿计数问题保留澄清／未充分支持的状态，没有产生替代标签判定。本轮计数验证没有模型调用；它不代替生成答案的语义评价或客户操作验收。

最新操作说明见 [user_guide.md](../docs/user_guide.md)。**Railway 本轮未更新**；下方线上检查仍反映旧部署。下方差异表和错误原因保留修正前基线，便于追踪这次反馈如何改变实现。

## 六个问题逐项对照：修正前基线

| 客户问题 | 修正前本机代码 | 线上检查和已知差异 | 应当交付的结果 |
| --- | --- | --- | --- |
| 1. 比较公司与媒体的广告量 | `Database.dashboard()` 用同一只读快照聚合；完整数字矩阵、交叉表及 CSV 已实现 | 线上布局包含完整矩阵和交叉表，但客户无法完成任务；新 Overview / Relationships / Records 布局未在线上出现 | 可直接选公司或媒体；展示所有对应对象与数值；多对象比较用矩阵；每个数值回到对应记录 |
| 2. 每家媒体有哪些赞助公司 | sponsor／publisher 筛选、组合计数及记录详情已实现 | 线上有对应筛选字段，缺明确的“选媒体 → 看赞助方”的研究入口 | 媒体选择后出现完整赞助方列表／条形图，含计数；把公司、行业协会、会议及未知值写清楚 |
| 3. 按日期、媒体、公司／赞助方计数 | `Filters` 支持日期上下界、Unknown 日期策略、媒体与 sponsor 的 AND 组合；年度统计和未知日期数已实现 | 健康接口只证明部署／索引状态；本轮未完成线上组合筛选的操作验收 | 当前范围直接可见；条形图、矩阵、记录与导出合计一致；自然语言统计沿用当前筛选且注明追加条件 |
| 4. 现有数据支持的主题／话题 | 历史自动标签筛选和分布已实现；collection search term 与 sponsor 已分开 | 线上标明历史分类。它们还不是经领域审核的主题或“漂绿事实” | 保持历史／自动／未审核的状态说明，先支持探索和原文核对；后续 CLAIMS 标签查询绑定模型／taxonomy／正文版本和证据 |
| 5. 社交广告筛选与可视化 | 社交字段契约、导入入口及共享界面已有 | 线上健康接口只列 native；社交 platform facets 为空。不能把缺少 social 计数键单独解释成严格 SQL 的零 | Ned 提供正式导出及字段语义后，按广告主／账号／平台／日期建立筛选、数量与可用主题探索；接入前只显示明确的未接入状态 |
| 6. 两个数据集的有依据 RAG | 已接付费 LLM、混合检索与原文引用约束；确切统计只有一个固定问句白名单 | 本机 `Service.answer()` 对 NYT 这类 how-many 问句主动返回 `insufficient_evidence`；对象列表问题则进入正文 RAG，无法保证全库完备 | 把数量和对象枚举路由到数据库统计；文本解释用检索＋生成。两种结果共享记录详情、筛选及来源；正式社交数据到位后再验收跨库 |

原始 FA26 文档明确写明 CLAIMS backend integration 应留待后续学期。Michelle 这次说 “Once the CLAIMS integration is added” 是未来问题示例；邮件没有给出实施期限或明确取消原范围。可以预留正式 CLAIMS 查询接口，并向 PM 确认时间安排，不能因此把当前统计修复扩展为模型重建。

## 修正前 “insufficient evidence” 的具体原因

本次读取时的 `src/observatory/service.py` 中，`answer()` 只认可少量固定计数问句，例如 `How many records match the current filters?`。其后正则匹配到 `how many / count / percentage / percent / total number` 就主动返回 `insufficient_evidence`，要求用户改用仪表盘。NYT 问题在这个分支直接结束，没有尝试匹配媒体名称。

这不是已经证明语料中没有 NYT 广告。线上公开筛选项实际包含 `The New York Times`。应当允许问题 `How many native ads are from the New York Times?` 匹配这个字段，再由参数化查询给出精确当前范围计数。返回值应写作 “records in this collection”，不能外推为该媒体所有真实历史广告总数。

对 `Which publishers is ExxonMobil working with?`，结果应准确表达为 “Publishers appearing in this collection's ExxonMobil sponsor records”。source sponsor 字段不足以证明合同、资金关系或所有商业合作。对 `Which fossil fuel companies ... Washington Post?`，API／AFPM 等协会需要单列，而不是直接包装为公司。

## 2026-09-29 的线上／本机状态

只读回执：[michelle_feedback_audit_evidence_20260929.json](michelle_feedback_audit_evidence_20260929.json)。

- Railway `/data`、`/_dash-layout`、`/_dash-dependencies`、`/healthz` 返回 200。
- `/healthz`：`status=ok`，`record_counts={native:275}`，`active_profile=sentence600-v1`，`chunks=556`。
- `data_version=f19d4d697f4e6d2699d2c58b3ce80620b03e02c7e9447f24e012123adcb00f53`；`index_version=d580c5962a6222e595db2ed8681f9787cef648dad653b055120b6bed10e3af75`。
- 线上布局没有本机新代码的 `native-view` 或 `knowledge-*` 组件；知识图谱 schema URL 返回 HTML，而非预期 JSON。可据此确认新图谱／分视图还未出现在线上公开应用，不能宣称客户已试用了它们。
- 线上筛选确实包含 `The New York Times`、`The Washington Post` 和 source sponsor `exxonmobil`。
- 初次检查时本机 8050 未监听，数据库连接超时。随后主任务启动了既有本机数据库，本审计通过只读 Service／SQL 重新取得计数；应用交互和新实现测试由主任务另外记录。
- 刷新核对得到：275 条活动 native 记录，263 条可统计，226 条可检索，22 条缺发布日期；数据库没有 social 记录。当前文本绑定 255 条 `claims-calibrated` 与 255 条 `claims-original` 历史标注。图谱的旧证据检查中没有有效定位片段，本轮没有运行新的标签语义验证。
- 本机与线上健康接口的 data／index 标识相同，读取计数前后的标识也未变。该一致性不是两库所有表、附件或答案相等的证明。

`275` 是健康接口里的活动记录数，未应用 dashboard 的 `countable` 条件，不能替代页面可统计总量。所有公开 dashboard 查询遵循 `records.current_version`，只计 `active AND countable`，再应用数据集、对象、标签、日期及 record ID 筛选。可检索正文条件不会限制普通数量统计。重复 URL、资产链接、重复正文及准入处理的结果必须沿用导入规则和待确认口径，不能让 RAG 的前五条检索结果成为统计全集。

## 客户示例的当日数据库答案

以下通过当日本机 `Service.dashboard()` 与公开记录集合重新读取，默认范围是 native、所有日期、保留未知日期、无其他筛选。完整记录 ID、版本及过滤条件保存在只读回执中；读取前后 data／index 标识未变化。另从 [2026-09-17 交叉表](sponsor_outlet_crosstab_20260917.csv) 对照，以下计数一致。

| 客户任务 | 当日只读查询结果 |
| --- | --- |
| NYT 原生广告数 | 19 篇；其中 15 篇有可检索正文，1 篇缺发布日期。计数必须保留没有正文的 4 篇 |
| ExxonMobil 所列媒体 | Business Insider 5；The Washington Post 5；The New York Times 3；The Wall Street Journal 2。合计 15 篇、4 个媒体；13 篇有可检索正文 |
| Washington Post 所列 sponsors | API 6；ExxonMobil 5；Shell 2；Southern Company 2；Chevron 1；AFPM 1；Eni 1。合计 18 篇，全部有可检索正文，2 篇缺发布日期；其中 API／AFPM 是行业协会 |

旧来源审查还记录 Washington Post sponsor 与采集词的赋值策略问题。该问题尚未由 sponsor 披露证据和客户裁决关闭；上述数字只表明来源表所列值的记录统计，不证明每条付费赞助身份准确。

## 材料请求应缩小到真正的剩余依赖

当前不需要再向客户索要这三个基础问题、重复 ZIP 或让她从头写标准答案。团队先把三个问题做成固定回归任务，提供完整记录列表，让 Michelle 核对研究含义和操作是否直观。

仍需请求／确认：

1. 指定权威 native 数据版本、唯一广告计数规则、公司别名／母子公司归并，以及协会和 CERAWeek 是否纳入公司统计；团队准备具体争议行供裁决。
2. Ned 的正式社交导出、字段字典、范围及稳定帖子 ID，广告纳入标准、账号与广告主的关系，归档映射及 Miami 原型访问。
3. 对主题探索应采用的标签／taxonomy／运行版本和审核责任；如要求本期加入 CLAIMS，明确期望、时间安排与可验收输出。
4. 对当前三个问题及后续文本问题，由领域负责人检查完整性、用语、必须保留的限定与来源。统计问题的正确性由团队全量对账，不能要求客户逐行代替程序核算。

## 可供 PM 转发的回复草稿（未发送）

> Thank you, Michelle. Your examples identified a gap in the prototype: users need a direct way to explore a company or a publisher, and the query page should answer record counts from the database. The previous query path rejected most counting questions, which is why the New York Times question returned “insufficient evidence.” That response did not mean the collection contained no New York Times records.
>
> We have implemented direct company-to-publisher and publisher-to-sponsor exploration locally, using labeled bars, exact counts, and links to matching records. The complete company-by-publisher matrix supports comparisons. The local query page now routes supported counting and entity-list questions to the same eligible records used by the dashboard, while retaining cited RAG answers for questions about advertisement content. These changes have not yet been deployed to the shared Railway site.
>
> We have recorded your three examples as regression and usability tasks. The displayed relationships will be described as source-listed sponsor relationships; they do not independently establish all commercial partnerships. Trade associations and events will be identified separately from companies. Historical CLAIMS labels will retain their current review status until the intended taxonomy and integration scope are agreed.
>
> To complete the remaining dataset work, we still need Ned’s formal social-media export and field definitions, and confirmation of the authoritative native dataset and counting rules. We will provide a short updated walkthrough and the records behind these answers for your review.

此草稿描述已实现的本机修正和仍待完成的共享部署，不表示客户已经能在线上使用新版本。正式发送前应加入实际发布版本、可点击操作入口及复测结果。
