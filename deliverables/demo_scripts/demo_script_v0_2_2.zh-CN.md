# FA26 CISS Observatory 0.2.2 研究预览讲稿

日期：2026-09-16。对应 [新版 PPTX](research_preview_v0_2_2.pptx)。这是当前原生语料已连接的研究预览，**最终验收仍待完成**。旧版演示保持原状。

## 演示口径与准备

- 数据版本固定为 `d85a98002e4493f0376c260ad82253ee`：275 条收录、263 条可计数、226 条可检索正文、554 个文本块。94 条疑似截断仍保留质量标记。
- 保存的开发运行是 `d26eb540a6114cfe9672a755c43f39a7`，见 [完整输出](../outputs/development_claim_contract_20260916.json) 和 [0.2.2 报告](../reports/claim_contract_v0_2_2.md)。演示保存结果不产生 API 费用。
- 本地服务入口为 `http://127.0.0.1:8050`。需启动时，在项目根目录运行 `./scripts/Start-Observatory.ps1`，再运行 `./scripts/Test-Observatory.ps1`。本机已经具备隔离的 PostgreSQL，无需重复下载。启动与停机细节以 [运行指南](../docs/operations.md) 为准。
- 保持公众界面英文，中文口头解释。默认使用免费 Search keywords，并展示已保存的 paid run。只有需要实际重新生成时才点击 Generate paid answer，该动作会消耗预算。
- 不将广告说法讲成经外部证明的事实，不将字符定位或 AI 辅助审阅讲成人工语义验收。

## 第 1 页：项目定位

“这次展示的是 FA26 广告观测站的研究预览。项目最终面向原生广告和社交广告两类数据，提供筛选、统计与带证据的问答。当前本地应用已经连接真实原生语料，社交导出、公开固定入口和人工验收仍待完成。”

不要称作最终产品验收或暗示已发布公共域名。

## 第 2 页：按模块说明交付

“我们按 M1–M8 组织工作：数据、正文、原生看板、社交视图、RAG、评价、部署和交接。原生链路已有本地实现；社交接口已经预留，页面明确显示 not connected。CLAIMS 在这里提供历史标签展示，本期没有重建其分类后端。”

强调 M1、M4、M5、M6 的双数据集目标继续保留。模块有可用实现不等于整个模块已验收。

## 第 3 页：数据口径与正文限制

“275 是收录数，263 是可以进入统计的记录数，226 是允许检索的正文数，554 是文本块数。这些数字描述不同层级，不应该混用。”

“94 条记录带有疑似截断标记。当前系统可以从保留的可用正文回答，同时展示质量边界；我们没有声称全文已经恢复。已有结构化文件没有确认可直接恢复的全文，3 个 PDF 有续文候选，仍需核对身份、页面和正文边界。”

依据：[数据修订](../reports/data_revision_v0_2.md)、[截断预检](../reports/truncation_recovery_preflight.md)。

## 第 4 页：实际看板演示

1. 打开 Native 视图。说明 URL、publisher、title、date、sponsor、keyword 六字段。
2. 选择 sponsor `exxonmobil`。核对当前筛选计数为 15，查看媒体／公司数量、占比、时间分布和赞助关系。
3. 导出当前集合。检查 CSV 的 record_id，说明保存的浏览器检查曾确认 15 个不同 ID 与筛选结果一致；本次若不实际打开 CSV，不称作重新验证。
4. 清除赞助方筛选，再演示日期范围与 Unknown。日期缺失仍单独可见，避免将其误认为某一年。
5. 解释来源链接的**服务端配置**：配置关闭时，页面、证据和导出中的 URL 一并隐藏。当前 UI 没有供访客点击的开关。本次只说明配置行为和已保存测试，不现场改配置或重启；链接出现也不代表已经在线核对网页。
6. 切换 Social，展示 not connected，再回到 Native。两个页面保存独立筛选状态。

提醒：keyword 是源词项字段，不能自动当成赞助方身份；历史自动标签也不是本次 RAG 的人工判断。

## 第 5 页：带原文证据的回答

先演示免费 Search keywords 搜索 `CCS`，查看记录、原文片段和来源。再在编辑器／文件预览中打开 [保存的 JSON](../outputs/development_claim_contract_20260916.json)，定位 `dev-07` 的 `answer` 与 `citations`，并对照本页引文。当前应用没有历史 run 选择器，保存输出通过文件展示；无需为了演示重复付费。

“这一原生广告说，设施建成后每天可能生产最多 10 亿立方英尺蓝氢。回答同时保留广告归因、蓝氢对象、每日单位，以及 could 和 once completed 的规划状态。它没有说明现实中的设施已经建成。”

实际广告引文：

> Once completed, the new facility could produce up to 1 billion cubic feet a day of blue hydrogen that can be used to help fuel the existing Baytown complex as well as other industrial facilities in the area.

- 题目：`dev-07`。
- record_id：`0d2b4bc2-4397-5604-8235-fcda8c7088f7`。
- version_id：`7edbf6617dc344578452865c341bfe53f5f18beb6b9bc30caa51aa6e96269cde`。
- 原文字符区间：`[688, 895)`，Python 半开区间；段落 `p1`。
- [原文章链接](https://partners.wsj.com/exxonmobil/business-of-carbon-capture-and-storage/hydrogen-another-chapter-in-exxonmobils-lower-emissions-ambitions/) 是保存的来源字段，没有在本轮重新在线验证。

随后在同一 JSON 中定位 dev-01 的 biogas 回答：广告说沼气池每日以 livestock slurry 供料，项目位于印度 Adilabad。说明本轮补上了广告归因。继续展示 dev-08 中文问题及中文回答，解释回答语言跟随问题；本地语言检查是保守启发式，短缩写不做强判断。

最后展示 dev-18：问题要求独立审计的实绩，选定广告资料不足，系统拒答。拒答避免把规划数字当已实现绩效。

## 第 6 页：实现与费用

“Dash、Plotly 和 AG Grid 负责界面。PostgreSQL 和 pgvector 保存版本、计算筛选结果并检索。pySBD 形成可定位原句目录，模型先选 passage_id，再写说明，程序从原文恢复引文与坐标。Luna 负责付费回答，embedding 模型负责向量，Lingua 在本地检查明显错语。”

“免费关键词搜索和 SQL 计数不调用模型。Paid answer 单独触发。应用预算目标为每月 100 美元，调用前预留、之后结算。模型故障时仍可使用看板和免费检索。”

这不是 $100 已经支出的意思。不要将本项目账本金额外推为整个 OpenAI 账户支出。

## 第 7 页：开发证据与验收边界

“本次保存的运行包含 8 个回答、2 个 SQL 计数和 3 个资料不足拒答。命中记录 8/8，必需片段 13/13，证据定位 85/85，引文定位 16/16，计数 2/2，拒答 3/3；语言检查 8 match。本轮实际结算 $0.01632325。”

“这些分母不同，不能加成一个准确率。4 道社交和 3 道跨库题仍等待数据。本轮 52 项相关测试通过；0.2.1 的 164 项全套测试是历史记录，没有在本轮重跑全套。”

“AI 辅助阅读发现旧的广告归因和蓝氢对象缺口在本次输出中已经补齐。但 dev-03 经济挑战的完整性，以及 dev-05 额外 BIOMEM 背景是否应删减，仍需要判断。16 行人工意见为空，所以没有人工语义支持率，也没有 ≥95% 或整体通过结论。开发题已用于迭代，不能当独立盲测。”

打开 [AI 辅助复核](../reports/assisted_semantic_review_v0_2_2.md) 和 [人工待审 CSV](../reports/citation_review_v0_2_2.csv) 说明如何逐条核对，而不是只看汇总数字。

## 第 8 页：交接和下一步

“接手者从 README 和 handoff 启动应用，按用户指南核对筛选、导出与免费搜索，再查看保存的问答和人工复核表。下一步按交付要求补真实社交导出、指定 GitHub、固定 Cloudflare 域名、独立人审与最终双数据集演示。”

入口：

- [README](../README.md) 和 [交接说明](../docs/handoff.md)。
- [运行指南](../docs/operations.md)、[用户指南](../docs/user_guide.md)、[数据字典](../docs/data_dictionary.md)、[架构](../docs/architecture.md)。
- [评价协议](../docs/evaluation_protocol.md) 和 [汇总评价](../reports/evaluation.md)。
- [模块化交付计划](../FA26_DELIVERY_PLAN.zh-CN.md) 与 [资源附录](../FA26_RESOURCE_APPENDIX.zh-CN.md)。
- [生成脚本](../scripts/build_preview_v0_2_2.js)。脚本读取指定的保存运行，使用可选的 Node.js、`@oai/artifact-tool` 与 Presentations 校验工具，不访问数据库或模型。这些只是制作 PPTX 的依赖，不是运行观测站的依赖。项目根目录从脚本位置计算；本机默认查找用户目录中的 bundled runtime，其他机器可用 `ARTIFACT_NODE_MODULES`、`PRESENTATIONS_SKILL_DIR`、`ARTIFACT_PYTHON` 指定已有制作工具路径。

可选重建命令（在已有上述制作工具的机器执行）：

```powershell
$env:PREVIEW_OUTPUT = 'deliverables/research_preview_v0_2_2_rebuilt.pptx'
node scripts/build_preview_v0_2_2.js
```

本机使用 bundled runtime 中的 `node.exe` 执行同一命令。`PREVIEW_OUTPUT` 允许采用新的文件名，脚本拒绝覆盖已经存在的最终文件。没有这些可选工具的接手者仍可直接阅读 PPTX 并运行应用。

源码交接不应包含真实密钥、数据库运行时或全部原始资料。原始语料需要另外提供。演示结束后如需停机，按运行指南先执行 `./scripts/Stop-Observatory.ps1`，确认没有写入任务后再执行 `./scripts/Stop-Postgres.ps1`。

## 本演示稿的检查范围

8 页中文 PPTX 保留可编辑文本、4 张原生表格和 1 张原生图表。制作过程检查 PPTX 包、布局几何、字体与原生图表数据，并逐页渲染查看。此检查不等于在 Microsoft PowerPoint 中打开、编辑并保存的兼容性测试，也不扩大应用测试或人工验收范围。
