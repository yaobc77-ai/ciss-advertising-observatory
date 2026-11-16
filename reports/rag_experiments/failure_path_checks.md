# M5/M7：故障降级与费用账本验证

2026-09-16 新增并执行 `tests/test_failure_paths.py`：**9 passed in 11.01s**，Ruff 检查通过。本轮只新增测试与此报告，没有修改 Service、Rag 或 Budget 的实现，也没有发现需要修补的失败项。

## 验证方法与范围

- 使用真实 PostgreSQL `obs_test`，运行前同时检查连接配置中的 dbname 与服务器返回的 `current_database()`，只接受固定名称 `obs_test`。
- 每题使用 disposable 测试表内容，开始与结束清理测试表；没有连接主库，也没有操作主库数据。
- 保留真实 `Service.answer → Rag → Budget → Database` 路径。仅在 SDK 边界注入假的 embeddings/responses；超时使用真实 OpenAI SDK 的 `APITimeoutError` 类型，未发送网络请求。
- 另将 Rag 的真实 `OpenAI` 构造器替换为立即失败的测试哨兵，防止遗漏注入后创建真实客户端。
- 五条人工记录分别涵盖允许来源、错误赞助方、错误媒体、错误日期与社交媒体。降级结果必须只返回 native＋媒体＋赞助方＋日期组合筛选允许的那条记录，并逐条通过数据库原始版本／字符定位检查。
- 测试保存的 `answer_runs.result` 与公共返回对象必须一致；这些失败场景不能留下伪造的 `generation_outputs`。

这些人工记录用于工程协议测试，不属于研究数据、开发评测题库或验收语料，不提供任何模型质量成绩。

## 场景与结果

| 场景 | SDK 调用 | 账本及降级结果 |
|---|---|---|
| 生成请求已发送后超时 | 1 次假 embedding，1 次假 generation | 返回 `service_unavailable` 和受筛选证据；generation 保留 `uncertain`、actual 为空、预留 0.04 USD；embedding 按假 usage 结算，总 exposure 和返回成本包括两者。 |
| embedding 请求超时 | 1 次假 embedding，0 次 generation | 未发送的 generation 变为 `cancelled`、actual=0；embedding 保留 `uncertain` 与预留额度；返回受筛选关键词证据。 |
| embedding 返回错误维度 | 1 次假 embedding，0 次 generation | 已获 usage 的 embedding 保持 `settled`，错误向量不写入缓存；未发送的 generation 取消；仍返回受筛选证据。 |
| 生成前本地引文准备失败 | 1 次假 embedding，0 次 generation | embedding 已结算；generation 取消；异常消息中的秘密哨兵不出现在返回结果。 |
| SDK 异常消息带秘密哨兵 | 1 次失败的假 embedding，0 次 generation | 公共结果与持久化回答不包含异常原文；账本只记录错误类型，不存秘密消息。 |
| 月预算不足 | 0 次 embedding，0 次 generation | `limited`＋受筛选证据；账本不新增预留，新增费用为零。 |
| 并发名额已满 | 0 次 embedding，0 次 generation | `limited`＋受筛选证据；已有请求的预留不变，未为被拒绝请求增加费用。 |
| 同访客每分钟限额 | 0 次 embedding，0 次 generation | 在付费调用前拒绝；账本不新增预留。 |
| 同访客每日限额 | 0 次 embedding，0 次 generation | 在付费调用前拒绝；账本不新增预留。 |

超时后的 `uncertain` 表示供应商最终计费情况尚未确定，保留额度是保守成本暴露，不声称该金额已经真实扣款。测试中所有 SDK usage 和费用均为人工协议输入，没有真实 API 支出。

## 复现

先运行 `scripts/Setup-TestDatabase.ps1` 准备测试库，再执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_failure_paths.py -q
.\.venv\Scripts\python.exe -m ruff check tests/test_failure_paths.py
```

此文件使用会清理表的固定测试库，应与其他使用 `obs_test` 的 integration 测试顺序运行，不要并行启动独立 pytest 进程。缺少 `OBS_TEST_DATABASE_URL` 时会明确 skip；本次实际执行为 9 passed，没有跳过。

## 证据边界

本轮证明上述代码路径在真实本机 PostgreSQL 与模拟 SDK 故障下的行为。没有模拟完整供应商网络、真实限流响应、数据库中断、进程被强制终止或恢复后的供应商账单对账；也不证明降级片段的语义足以回答问题。用户仍可检查证据，答案状态保持失败／受限，不能把它当成正常回答通过。
