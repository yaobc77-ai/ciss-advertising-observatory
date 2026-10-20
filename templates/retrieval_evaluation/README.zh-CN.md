# 检索评价输入模板

这些文件只有表头／占位字段，**没有客户题、真实标注或运行结果**。复制到本机评价专用目录后填写；不要把真实客户题与参考加入开发测试或正常MCP上下文。

| 文件 | 一行／一个对象代表什么 |
| --- | --- |
| `queries.csv` | 一道问题和固定范围；来源、分组、预期可答状态、评价子集必须记录 |
| `judgments.csv` | 一个问题与一个评价单位的相关性判断；记录原文版本、等级、依据与标注方式 |
| `retrieval_runs.csv` | 实际检索的一个结果位置；文章或片段、阶段和集合不得混用 |
| `rankings.csv` | 一条排序流的身份、预先请求的K、实际范围及结果／失败状态 |
| `query_outcomes.csv` | 一个问题的一次尝试，包括空结果、超时、未运行及不可评分原因 |
| `answer_reviews.csv` | 一道题的回答评价及分母；不是模型置信度 |
| `run_manifest.json` | 一轮固定运行身份与预先确定的规则；null表示尚未填写，不代表没有费用或没有限制 |

约定：

- `eval_unit_id`由固定manifest定义：文章级是记录＋版本的唯一ID；片段级还绑定chunk／原文位置。实际ID必须能回查，不能用标题替代。
- `relevance`只能是0、1、2、3或空。`judgment_status=unjudged`时留空；缺原文、分歧和版本失配另记原因。0必须代表实际判断不相关。
- `judgment_method`记录human／ai_assisted／rule_derived；审核状态另填，不根据文件名推断。`pool_complete`只表示定义的候选池已判完，不能代表全库完整。
- `run_manifest.query_ids`列出全部计划题。`query_outcomes.csv`必须为每题保留一条`is_primary=true`的主要尝试；空检索、异常和未运行题也有行。`status`为completed／empty／error／timeout／not_run；`metric_eligibility_json`按ranking_id和指标名分别记录eligible／unjudged_provisional／zero_idcg／no_binary_reference／verified_no_answer／reference_missing，另填写原因。例如同一题的NDCG可评分而Recall没有二值正例，不能用一个可评分布尔值代替。重试另用attempt_id，不能替换主要尝试。
- `rank`从1开始、连续且不重复；文章级按实际结果首次出现去重，保留原始片段结果另表。导出TREC时可按`-rank`构造严格顺序；`raw_score`留存原值。
- `ranking_id`唯一标识一次尝试中的一条排序，`rankings.csv`绑定它的query、attempt、stage、retrieval_mode、retrieval_group_id、collection、unit_type和effective_filters_json。`stage`区分candidate、record_selection和generation_context；模式区分keyword／vector／hybrid。比较组分别登记，rank只在同一ranking_id内有意义；两条candidate流不能因都是rank=1发生冲突。跨集合最终交错展示单建collection=all的排序流。
- `requested_k`运行前固定，`returned_count`实际填入。未进入检索的错误保留query_outcomes；已计划排序流即使没有任何结果，也在rankings留status、failure_stage与reason。实际结果行的request／attempt须与这两表一致。
- `qrels_scope_id`绑定明确筛选和评价候选池。评分用的topic由query_id、qrels_scope_id和unit_type组成，不将同一问题在不同对象／日期范围下的参考混用；不同检索方式比较时保持相同topic与参考。
- 表内`filters_json`保存实际范围；`evidence_locator_json`保存字符区间／页码／时间戳，按真实来源填写，不能为视频捏造时间。
- 无可评分参考的指标留空并填写reason；空白不等于0分。未回答题不能从完整任务分母删除。

格式准备好后，评分适配器将把已判定单位导出为TREC qrels（query_id、iteration、doc_id、relevance）及run。适配器、真实标签与实际测试仍待执行；本模板不包含自动评分脚本。

完整口径见[方法说明](../../docs/retrieval_evaluation.zh-CN.md)。
