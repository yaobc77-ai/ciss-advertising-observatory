# 固定模型复测与 Claude 协作流程

本流程补充[共享协作协议](../AGENT_PROTOCOL.md)。每轮先确认当前用户授权、运行范围和费用界，再执行；旧批次预算不自动延续。原始记录、历史失败和旧成绩均保留。

## 执行顺序

```text
读取通讯 → 认领输出 → 冻结版本 → 发布运行前说明
    → 执行固定题目 → 核对结果与费用 → 发布结果 → 交接回执
```

| 步骤 | 操作 | 完成判断 |
| --- | --- | --- |
| 读取通讯 | 用自己的真实任务身份运行 `status`、阅读更新，再运行 `read`；读取 `goal.md`、`plan.md`、`work.md` | 知道当前认领、并行修改、未解决交接与用户授权范围 |
| 认领输出 | `claim` 本轮独立目录；共享路径有冲突时先协调 | 输出目录归属明确，未覆盖对方文件 |
| 冻结版本 | 固定源码、模型、提示、数据／索引、题目／参考、评分、超时、重试、预算和终止条件 | 保存哈希及来源适用性检查；并行开发时从独立冻结副本运行 |
| 运行前说明 | 再读最新通讯，发布 `progress`，关联冻结清单和授权来源 | 费用界、环境、执行范围与运行身份可核对；来源变化或冲突已处理 |
| 执行 | 每题一个主要尝试；模型只收到当前问题，不收到参考答案或整个客户题库 | 保存全部尝试、工具回执、响应和失败；不边跑边调提示，不自动重试收费未明的请求 |
| 核对 | 检查版本漂移、逐题唯一性、执行数、实际费用及未结算风险；停止本轮拥有的私有服务 | 失败仍在端到端分母中，各指标按自己的单位计分；来源失效另列，不静默删除 |
| 发布结果 | 发布 `paid_run --cost ...` 与 `result`，引用运行前事件和证据 | 按题型报告分母、结果和局限；区分用量计价、未结算风险与供应商账单 |
| 交接 | 发布 `handoff`，写接收者、下一步、边界与所需回执 | 接收者本人引用事件 ID 回复；没有回复就保留“待接收” |

主库作为来源时只读；测试、账本与缓存使用本轮拥有的隔离环境。不得因复测而启动或停止其他代理的服务。复测不授权训练、主库回写、推送或部署。

## 已记录、已读、已回执是三个状态

- **已记录**：事件已在共享日志中；不说明对方已经看到。
- **游标已读**：接收会话执行过读取工作流；不证明理解。当前 `read --all` 只展示最后 30 条却推进快照游标，不应用它证明整份历史已读。
- **已回执**：实际接收会话发出引用原事件的回复，明确接受、拒绝或有条件接收及其范围。回执不等于任务完成，也不增加操作授权。

现有脚本支持 `--refs`。接收者可用关联 `note` 作为回执；不需要新增消息系统。禁止冒充 Claude 发回执、修改 Claude 游标，或将发送者自己的审计报告写成 Claude 已确认。

Claude 尚未回执时，可继续无冲突、独立隔离且已获用户授权的工作；不得据此接管认领路径或依赖未确认的共享资源。记录待接收状态即可，不将等待回执变成所有工作的停机条件。

## 可复用命令

这些是流程命令，不含模型派发。运行者填写真实任务身份、路径、事件 ID 与已结算金额。

```powershell
$env:AGENT_NAME = '本轮真实任务身份'
python scripts/agent_sync.py status
python scripts/agent_sync.py read
python scripts/agent_sync.py claim '.runtime/本轮目录/**' --reason '固定复测输出与冻结副本'
python scripts/agent_sync.py post progress '范围、配置、费用界和授权来源见清单' --evidence .runtime/本轮目录/manifest.json

# 按冻结清单执行；结束后填写实际金额和运行前事件 ID。
python scripts/agent_sync.py post paid_run '实际用量及未结算风险见明细' --cost $settledUsd --refs $preflightEventId --evidence .runtime/本轮目录/cost.json
python scripts/agent_sync.py post result '按题型报告，保留失败与比较限制' --refs $preflightEventId --evidence .runtime/本轮目录/summary.json
python scripts/agent_sync.py post handoff 'To Claude: 请核对汇总和剩余事项，并引用本事件回执；不增加付费或发布授权' --evidence .runtime/本轮目录/summary.json
python scripts/agent_sync.py release '.runtime/本轮目录/**'
```

实际接收者阅读后，以自己的身份回复：

```powershell
python scripts/agent_sync.py post note '已收到；接受的范围、冲突及下一步见摘要' --refs $handoffEventId
```

## 2026-10-08 本轮边界

P56／U33 执行固定真实模型复测。运行负责人保存的源码快照时间为 **17:35:24 UTC**，规划／任务规则／生成提示版本为 **v14／v7／v9**；复制前后哈希一致。实际模型和数据身份以本轮冻结清单为准。

并行 P55 正在开发 QuestionIntent。其后续代码不自动进入 P56，也不能用 P56 成绩证明 P55 有效。客户 24 题及其参考、逐题输出继续仅限评价；开发侧只接收汇总和非题目专属的工程事实。历史接触记录保留，不称测试题从未见过。具体规则见[客户题隔离](client24_masking.zh-CN.md)；工程通过、真实模型成绩与客户验收分别报告，见[工程检查](test_gate.zh-CN.md)。

本机运行回执位于 `.runtime/fixed_rerun_20261008/`，不随源码文档发布；其中 `root/runtime_preparation.json` 记录快照，`protocol/receipt.json` 记录本次协议审查。两份文件只证明其各自检查时点的状态，不代表后续模型运行完成。
