# 向量补齐：离线材料准备

日期：2026-10-08（America/New_York）。本轮按用户要求准备材料，**API调用0、数据库写入0、新向量0、活动索引切换0**。状态为`prepared_unpaid`，不是向量补齐完成，也不是检索准确率提高或客户验收。

## 实际范围与费用估算

当前模型为`text-embedding-3-small`、1536维；活动profile为`sentence600-social-observations-v1`。输入仍为`original-chunk-text-v1`：直接使用保存片段的原字符，**不加标题、公司、日期、媒体或其他metadata prefix，不改原文、不重新切分**。

| 集合 | 活动片段 | 已缓存片段 | 缺向量片段 | 去重后缺失文本 | 输入token | 标准同步API估计美元 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 原生广告 | 622 | 520 | 102 | 98 | 39,656 | 0.00079312 |
| 公司社交帖子 | 37,086 | 0 | 37,086 | 35,818 | 2,039,265 | 0.04078530 |
| 全局去重合计 | 37,708 | 520 | 37,188 | 35,916 | 2,078,921 | **0.04157842** |

同文本只请求一次，其全部记录／版本／来源观察绑定保留。102个原生片段不是102个唯一输入。本次两集合的缺失文本没有交集；以后若有交集，集合费用不能直接相加，使用全局去重合计。

估计采用2026-10-08核对的[官方模型价格](https://developers.openai.com/api/docs/models/text-embedding-3-small)：标准同步输入每百万token 0.02美元，并复用项目`budget.price`。这不是实际提供商账单、授权或Batch API报价。`cl100k_base`／tiktoken 0.14.0逐文本实际计数；实际响应usage须在后续付费运行中结算。

现有`Rag.embed`按UTF-8字节数加每请求100计保守预留。同一1123批准备材料的该预留合计为**0.16534798美元**；它与0.04157842美元的token估计分开记录。账号吞吐额度、未来预算上限和运行授权仍需在实际付费前确定，当前材料不占用费用账本。

## 可执行准备与复核

在`D:/Projects/549 native ads`运行：

```powershell
.venv/Scripts/python.exe scripts/prepare_embedding_backfill.py --output .runtime/embedding_backfill_20261008/private02 --batch-size 32 --max-batch-tokens 100000
.venv/Scripts/python.exe scripts/prepare_embedding_backfill.py --verify .runtime/embedding_backfill_20261008/private02
```

第一条已实际执行成功，目录不可覆盖；再次准备请换新的目录名。第二条已独立执行成功。脚本只接受明确loopback主库地址，服务器连接默认`transaction_read_only=on`，所有读取在`REPEATABLE READ READ ONLY`事务内进行；不调用初始化、迁移、provider、预算预留、向量写入或索引激活。

复用`Database.pending_embeddings`与现有按`(text_hash,model)`保存的缓存，对其缺失集合与冻结profile成员独立对照。每片段检查文本hash、保存token数、当前record/version/body hash和原字符范围；社交观察再复用现有`validated_observations`检查源身份、版本和正文hash。原始观察不会拼成新正文。

私有文件在Git忽略的`.runtime/embedding_backfill_20261008/`内：

- [manifest.json](../../.runtime/embedding_backfill_20261008/private02/manifest.json)：模型、profile定义／hash、tokenizer、源码hash、缓存与源表指纹、费用、API限制、恢复绑定契约及授权为空。
- `private02/inputs.jsonl`：35,916个去重原文本、hash、token数、UTF-8字节数及全部原位置绑定。包含整批私有文字，不进入Git。
- `private02/batches.jsonl`：1123批的有序输入hash、请求hash、token及费用；没有请求API。
- [verification.json](../../.runtime/embedding_backfill_20261008/private02/verification.json)：实际前后来源、缓存、usage ledger和索引身份一致；新向量仍0。
- [审核入口](../../.runtime/embedding_backfill_20261008/README.md)：运行证据和检查结果。

当前冻结计划SHA256：`c3d298fe8a1104c3e37f6f88c9f99a1c7d6a41c4d24e7a0de0645e27084de6ba`。
当前manifest文件SHA256：`d1936ba2c046e9b84ce0e22302fe545d48609c2791c1185532eb410d1d3d133b`。

`private01`为修复恢复检查之前的旧版准备，完整保留，未原位覆盖。当前脚本源码指纹与旧计划不同，旧包不能通过当前`--verify`。修复没有改变输入JSONL或批次JSONL；重新读取主库后两者hash仍与旧版相同。

## 批次、漂移与后续断点策略

[官方Embeddings接口](https://developers.openai.com/api/reference/resources/embeddings/methods/create)规定非空输入、单输入最多8192 token、数组最多2048项、单请求合计最多300,000 token。本材料默认32文本／批、最多100,000 token／批，条数与总token均受检查；保持确定顺序，全局hash去重后才分批。API输入上限与账号RPM／TPM额度不同；本轮未查询账户额度，后续须限速、串行发送并保留SDK `max_retries=0`。

`--verify`拒绝manifest／JSONL变动，以及当前来源、完整payload、profile、成员、缓存、ledger和准备源码漂移。没有成功verification的目录不能作为已核验执行计划。任何漂移另建新材料，不覆盖旧计划。活动profile全体成员数必须与当前成员一致，不能遗漏旧成员或只改可检索布尔值。

脚本中的`resume_remaining`是**离线恢复规划检查**，没有付费执行入口。它只允许在来源／profile／源码／模型完全相同、旧缓存未改变时，按同一计划的整批checkpoint判断剩余hash。checkpoint必须绑定计划、批次请求hash、响应hash、1536维、真实`settled`的embedding账本记录以及主库当前缓存hash；普通`done`标记、未结算记录、错误请求或未经记录的缓存新增均拒绝。`pending/uncertain`立即阻止恢复，不自动重发，也不释放未知费用。

每个checkpoint须有非空`reservation_id`，同一个ID再次出现即拒绝，不能让一笔结算证明两个不同请求完成。后续执行器须从主库读实际账本行，把UUID序列化为字符串，并按`reservation_id`建立映射；映射中的行身份必须与checkpoint一致，`state=settled`、`kind=embedding`、model一致，实际费用须为有限非负数。仅提供结算ID与金额不足以跳过批次。

实际账本`usage.embedding_backfill`须保存下表字段；schema固定为`embedding-backfill-settlement-v1`，其余值与checkpoint完全一致。使用现有`usage` JSON字段，无需新表；未来执行器须把该绑定与提供商实际usage一起传入`Budget.settle`，不能从本地`done`标记臆造实际结算。

| 必要字段 | 绑定对象 |
| --- | --- |
| `schema` | 恢复结算契约版本 |
| `plan_sha256` | 本次冻结计划 |
| `batch_id` | 确定顺序下的一整个批次 |
| `request_sha256` | 原文本数组、model和dimensions组成的规范请求 |
| `response_sha256` | 实际收到并私有保存的响应字节 |
| `model`、`dimensions` | `text-embedding-3-small`、1536维 |

未来付费执行器仍需在授权后实现并审查：每次请求前重新核对冻结源／profile与剩余预算；复用现有`Budget.reserve → settle/uncertain`；收到响应先私有保存、核对实际响应bytes hash、model、索引／条数、有限数值和维度，再缓存向量并写checkpoint。当前恢复函数只检查传入证据的绑定，不能代替这些实际响应／缓存／账本验证。已知费用先结算；超时或未知费用停止，授权剩余批次不能成为自动重试授权。实际补齐以后仍要另做向量覆盖、检索成效和来源稳定性核对。

## 免费验证与限制

当前独立虚构数据54项检查通过，使用`run_masked_checks`的Python读取保护；`denied_events=[]`，未加载客户题、参考或逐题输出。检查包括全局去重并保留不同来源、Unicode／字面特殊token不改写、原范围和观察错绑定、批次限制、冻结文件篡改、源／缓存／ledger／代码漂移及断点假成功拒绝；本次新增重复reservation、真实账本绑定缺失／错配、非法实际费用，以及不同真实结算的正例。

首次收集因错误引用数据库类名失败，[原回执](../../.runtime/embedding_backfill_20261008/checks01/mask_receipt.json)保留，原34项[通过回执](../../.runtime/embedding_backfill_20261008/checks02/mask_receipt.json)保留。独立审核发现两批共用一次结算仍被放行；本轮先复现，[失败回执](../../.runtime/embedding_backfill_20261008/checks03/mask_receipt.json)保留，修复后的54项[通过回执](../../.runtime/embedding_backfill_20261008/checks04/mask_receipt.json)另存。Ruff通过。

独立审核代理的`test_backfill_relative_independent.py`由其拥有者补上真实账本绑定夹具，本轮只读重跑，18项通过，[掩码回执](../../.runtime/embedding_backfill_20261008/checks05/mask_receipt.json)另存，读取保护未触发拒绝。该18项含断点恢复和另一代理负责的相对日期保护，不能全部归作本脚本的验证数量。

以上证明准备材料与工程保护，**没有证明新增向量存在、向量能提高召回、真实模型答题更准确或客户已认可**。关键词检索继续可用；缺向量不等于保存帖子全部查不到。本轮不改客户基准、客户24题、参考、旧分数或生产运行源。
