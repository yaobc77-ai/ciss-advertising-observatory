# 当前 RAG 切片只读核验（2026-09-16）

## 范围与结论

从 `Settings.from_env()` 与 `Database.connect()` 取得配置后，在同一 `REPEATABLE READ READ ONLY` 事务读取 active 记录的 current_version 及对应 chunks。未输出连接信息，未调用生成或 embedding、未修改数据库或启动服务。读取时间为 **2026-09-16 20:19:49 -04:00**；数据版本 **5114ebc1cf9afe59cdaa715e3ea45166**。详细逐记录、逐切片诊断见[配套 JSON](rag_chunking_corpus_audit_20260916.json)。

**审查关于正文缺少段落、切片常接近 token 上限的判断有数据支持。句内边界普遍存在，但不能把句内边界数量直接解释为信息丢失数量，也不能声称引用端使用 pySBD 就使检索切片成为完整句。**

## 核实的数字

| 指标 | 实测值与分母 |
| --- | --- |
| 当前原生收录 / 可统计 / 可检索 | 275 / 263 / 226 条 |
| 当前切片 / 所属文章 / 独立保留区间 | 558 / 226 / 256 |
| 可检索正文没有 LF 换行 | 220/226（97.35%） |
| 有换行的正文 | 6/226；LF 数分别为 19、21、37、50、62、248 |
| 可检索正文没有空行分隔符 | 225/226（99.56%） |
| 按 chunker 实际规则识别的段落数 | 225 篇为 1 段，1 篇为 2 段 |
| 当前切片含换行 / 含空行分隔符 | 23/558 / 0/558 |
| token 中位数 / 平均数 / 最小–最大 | 600 / 472.244 / 11–600 |
| token ≥590 / =600 / >600 | 320/558（57.35%） / 303/558 / 0/558 |
| 原文切片与字符位置、哈希匹配 | 558/558 |
| 存储 token 数与本次 cl100k_base 重算一致 | 558/558 |
| 已声明保留区间的字符覆盖 | 256/256 区间无缺口；不代表被排除或原先缺失的正文已恢复 |

上述正文统计分母是 **226 篇可检索正文**，不是 275 条收录记录。若用全部 275 条：268 条没有 LF，274 条没有空行，含 1 条空正文。token 使用本地 tiktoken 0.14.0 的 `cl100k_base`，不是模型 usage 或英文 word 数。

## “句中断裂”的判定和分母

以每个完整的**保留区间**为分析单位，而不是只在已截断的 chunk 内断句。先按空段或 `\f` 拆硬边界，再将每个空白字符等长替换为一个空格，以 pySBD 0.3.4 `Segmenter(language='en', clean=False, char_span=True)` 得到跨度并核对原字符位置。trim 末尾空白后，满足 `sentence_start < chunk_end < sentence_end` 才记作“切片终点位于 pySBD 预测句内部”。不通过末尾标点代替此方法。

| 分母 | 位于预测句内部的切片终点 | 比例 |
| --- | ---: | ---: |
| 全部当前切片 | 292/558 | 52.33% |
| 每篇文章中除最后一块外 | 292/332 | 87.95% |
| 每个独立保留区间中除最后一块外 | 292/302 | 96.69% |

最后一种分母最接近**分块器在连续保留文本中新增的内部切口**。332 与 302 相差的 30 个切片位于原文的保留区间终点，包括已审核导航删除或有限正文恢复造成的边界；不能与 token 切口混为一谈。末块终点被 pySBD 当作输入结束，不证明原文章完整；现有截断/partial 限制仍然成立。

292 个句内终点对应的预测句中，**288 个在至少一个现有 chunk 内完整包含**，另 **4 个预测跨度未被任何单块完整包含**。全部已声明保留区间的字符仍被切片覆盖。因此这里证明的是完整上下文在一个 chunk 内的可获得性差异，不能声称 292 句丢失，更不能由 288 有覆盖推出检索一定返回该完整块。pySBD 预测跨度本身也可能因引号或源文问题包含多个语言学意义上的句子，4 不是人工确认的“4 个丢失句子”。

**末尾标点的反例**：`Can You Turn Your Home Into A Hydroelectric Plant?` 中有一个切口落在 `1.` 与 `5 litres per second.` 之间（原文字符 2855）。虽然切片以句点结束，实际是小数 `1.5` 内部；该例直接反驳“有句号就是句界”。仅末尾标点法在全量会得到 326 个无句末标点块，不能将其命名为 326 个断句错误。

## 四个单块未完整覆盖的预测跨度（算法诊断，非人工金标准）

| 文章及精确 URL | 记录 / 原文跨度 | 切口锚点 |
| --- | --- | --- |
| [BP Supercomputer](https://www.politico.com/sponsor-content/2015/12/journey-to-the-subsurface-of-the-earth) | `22c29667-e7b3-5811-b7fc-95f7fff26bd4`；[5208,5959) | `commercial research` / `supercomputer`，切口 5853 |
| [Can We Harvest Lightning For The Power Grid?](https://www.forbes.com/sites/statoil/2015/01/28/can-we-harvest-lightning-for-the-power-grid/) | `48a268b4-8cc7-593d-9e56-d6fd7c42afbd`；[1979,4496) | `expense to` / `the exercise`，切口 2932 |
| [Why Are Wind Turbine Blades So Thin?](https://www.forbes.com/sites/statoil/2013/10/14/why-are-wind-turbine-blades-so-thin/) | `5f0cc72d-f694-50cb-a5dc-7cf98c53384a`；[2162,4189) | `a complex` / `compromise`，切口 2856 |
| [LNG, a groundbreaking choice for the shipping industry](https://www.cnbc.com/advertorial/lng-a-groundbreaking-choice-for-the-shipping-industry-/) | `bf5713ae-5911-55b7-8171-6e130e797ff5`；[5917,8365) | `calculation method` / `used`，切口 7922 |

URL 来自当前版本 metadata，用于本地记录身份；本次没有重新访问原网站。JSON 同时保存 record_version、body_sha256、chunk_id、精确范围及短原文锚点，未按标题匹配跨文件身份。

## 代码所支持的结论与不能外推的判断

- [chunking.py](../src/observatory/chunking.py)（本次读取时 18–26、98–139 行）：空行识别段落，默认 600 tokens / 100 overlap；长段落在 token/Unicode 字符边界结束，未寻找句界。225/226 只有一个可识别段落，确实削弱了“段落优先”的实际效果。
- [rag.py](../src/observatory/rag.py)（72–110、113–132 行）：pySBD 在**已检索片段**上构建引用组，空段/分页为硬边界；通常按句累积到 60 words，超长句再用最多 60 words、15 words 重叠的窗口。它不负责数据库分块，不能补回片段外的句首句尾。
- 无换行不等于所有正文都被错误解析；缺少段落结构是已核实限制，原标题层级、表格及完整性是否受损仍需对应原文证据。
- 本次未执行新检索或生成，因此不能从这些静态数字推出 Recall@K、回答错误率，或保证换成句界切分后质量提高。应将本文作为可重跑的切分候选比较基线。
- 当前 558 个切片的字节/字符定位与 token 限制均成立。应分别评价**原文定位、句界对齐、检索完整上下文和回答语义**。
