# 模型理解问题与 MCP 工具层：本机实施验证

日期：2026-09-29。范围：当前本机项目；本轮未提交 GitHub、部署 Railway、导入或重新分类源记录。

## 实施结果

截图中的 `Washington Post 有哪些赞助方?` 不再依赖固定中文句式。Query 开启 `OBS_RESEARCH_AGENT_ENABLED=true`，语言模型读取原问题、可信页面范围与实际实体名称，选择受限工具。程序校验参数、实体和范围，再计算统计或读取来源。模型自行生成的数量不会被发布为数据库统计。

网页内部使用 Responses function calling；真正的 MCP 服务通过官方 Python SDK 2.2 提供 stdio 协议，复用同一 `ToolCatalog`。这是两个接口，不把网页函数调用称作已经连接一个远程 MCP 服务器。

七个工具：实体解析、字段统计、正文候选检索、指定记录正文、指定记录来源、图谱 schema、分页图谱邻域。SQL 统计覆盖所有合格记录，包括没有可检索正文的记录。正文解释仍调用原有混合检索与引用约束，保留原问题；改写后的英文查询只用于检索。

## 三次真实模型检查

| 问题 | 实际工具与结果 | 模型调用 | 费用（美元） |
|---|---|---:|---:|
| 纽约时报这里收集了几篇原生广告？ | `record_statistics`；19 条，15 条可检索，1 条缺日期 | 1 | 0.00100275 |
| ExxonMobil 的广告出现在什么媒体？列出每家数量。 | `record_statistics`；15 条、4 家媒体，分组为 5／5／3／2 | 1 | 0.00032134 |
| Washington Post 有哪些赞助方? | `record_statistics`；18 条、7 个来源所列赞助方／组织 | 1 | 0.00031909 |

合计 0.00164318 美元。前两题通过真实模型和共享执行器运行；第三题通过本机网页提交并检查结果。Washington Post 表格：API 6、ExxonMobil 5、Shell 2、Southern Company 2、AFPM 1、Chevron 1、Eni 1。数量描述当前合格存储记录，不证明全部真实世界广告或付款合作。

费用按现有项目价格配置及提供方返回的用量记录。没有更换模型或提高预算；失败和未知费用沿用费用预留逻辑。问题理解收费，即使后续只有数据库计数；Data 浏览、图表、关键词搜索及 MCP 数据读取本身仍不调用模型。

## MCP 与来源实测

真实独立进程使用官方 MCP Client 完成初始化、列出七个工具和调用。对本机真实库读取 Washington Post 统计、单条文章图谱邻域和来源，返回记录版本及正文哈希。额外 `sql` 参数被拒绝。该进程的 API key 被置空，没有模型调用。

另以共享执行器核对图谱 schema、单篇五节点／四关系来源图谱、原始网址参考、500 字符正文区间与哈希。读取前后 `data_version` 未变：

`f19d4d697f4e6d2699d2c58b3ce80620b03e02c7e9447f24e012123adcb00f53`

这些检查没有改动广告正文或检索索引；API 使用账本和问答审计新增三次检查记录。可选本机 HTTP 传输已实现和限制绑定范围，本次未启动 HTTP 端到端检查。

## 工程验证

当前验证汇总见 [机器可读记录](research_tools_validation_20260929.json)。新模块专项检查覆盖模型工具调用、共享工具、MCP 协议、服务衔接和公开 UI，共 106 项通过。整个非 integration／非 live 回归与 Ruff 另列在该记录中。

工程检查覆盖范围交集、未知实体、未接入数据集不报零、额外参数拒绝、正文哈希和偏移、版本变化、所有模型阶段费用保留，以及提供方失败时不回退到虚构统计。模拟模型测试检查程序契约，不是自然语言理解准确率。

## 未完成与下一步

- 三个真实问题是有限连通检查，未冻结为独立语义评价集；不能据此宣称一般问法已经可靠。
- 当前一轮只完成一个终结工具，复合问题需要澄清；不解析前次查询中的多轮指代。
- 图谱记录的是来源字段和历史标注，未实现法人身份归并或事实判定。
- 正式 CLAIMS、社交正文／图谱、核验附件和外部事实核查适配器有明确接口空间，尚未接通。未把历史标签当作已验证漂绿。
- 公开远程 MCP 的身份认证和部署不在本次本机实现范围；没有修改外部客户端配置。
- 既有 RAG 回答的语义支持仍需独立评价和人工审查；没有用本次统计检查代替它。

## 使用入口和证据

- [本机 Query](http://127.0.0.1:8050/query)；展开 **How this question was answered** 查看工具与费用。
- [技术路线、七个契约及扩展](../docs/MCP_RESEARCH_TOOLS.zh-CN.md)。
- [工具与前两题真实模型记录](research_tools_smoke_20260929.json)。
- [网页第三题记录](research_tools_browser_smoke_20260929.json)。
- [真实 stdio／真实数据库协议记录](mcp_protocol_smoke_20260929.json)。
- [问题及答案页面](screenshots/model_tools_query_20260929.jpg) · [展开费用和执行工具](screenshots/model_tools_washington_post_20260929.jpg)。

采用 [OpenAI 官方工具调用接口](https://developers.openai.com/api/docs/guides/function-calling)及 [MCP 官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)，没有自行重写 MCP 协议或增加大型调度框架。
