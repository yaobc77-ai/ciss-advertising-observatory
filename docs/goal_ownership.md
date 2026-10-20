# 目标归属与历史核对

更新：2026-10-06，America/New_York。依据本轮用户明确指示，目标按来源分开；文件位于“客户需求”目录本身不能证明它属于客户。

## 归属规则

1. **client goal：客户目标。** 用户明确指定为客户要求，或已明确指定的客户原件／会议／邮件。转述保留“用户确认转述”的来源类型。
2. **user goal：用户追加目标。** 用户直接选择的页面、工具、工作方式和效率取舍。
3. **团队方案。** 从目标推导的库、参数、测试、预算方案；不冒充任何一方的原话。
4. **待确认。** 归属模糊先询问，独立工程可继续，不由等待时间替代回答。

本轮用户明确确认 **R11“全文输入、离线分类与审核”为客户要求**。因此当前归属为client goal；这是2026-10-06确认后的记录，不改写较早的GitHub快照。R12视频省力是user goal，文章、统计和来源标准保持原要求。

| 修订 | 当前归属 | 来源判断 |
| --- | --- | --- |
| R1 | client goal | 原FA26项目说明 |
| R2 | client goal | 客户9/25会议，原件年份未注明 |
| R3 | client goal | Michelle客户反馈邮件，原始邮件日期未提供 |
| R4 | user goal | 页面组织、简洁外形和工具箱偏好 |
| R5 | client goal，用户转述 | 用户明确说客户要求推进CLAIMS；验收边界仍待确认 |
| R6 | user goal | MCP实现、统一总结／证据、具体统计扩展、联网及加载提示 |
| R7 | client goal／团队实施安排 | 客户／团队后续职责及24题；具体公式、阈值和测试不是客户批准标准 |
| R8 | **拆分** | PD3中的要求保留client来源；修prompt和work/plan是user goal；收到资料不是新目标或准入决定 |
| R9 | user goal | 用户要求公开评价指标；16项是团队实现选择 |
| R10 | user goal | 持续维护goal/plan/work与可复用工具查找 |
| R11 | client goal，用户确认转述 | 本轮明确确认技术路线；真实模型运行、审核和发布未完成 |
| R12 | user goal | 仅视频允许转写准确性与效率取舍；3条试跑等上限属团队建议 |
| R13 | user goal | 本轮要求区分目标来源、核对GitHub历史及具体失败、登记完成部分 |

## GitHub核对结果

只读核查时间：2026-10-06纽约时间11:37–11:39。保存的是当时默认分支快照，不代表随后远程不会变化。

| 请求的仓库 | 核查结果 |
| --- | --- |
| [ciss-advertising-observatory](https://github.com/yaobc77-ai/ciss-advertising-observatory) | main HEAD `7e2fdcb08f9de435d3bd701afe888b3f74377b84` |
| [ciss-advertising-observatory-549](https://github.com/yaobc77-ai/ciss-advertising-observatory-549) | main HEAD `6b2899b626a44ff79e43d10559d41899914fb237` |
| 原ciss-advertising-observatory-en | 重定向到-549，同仓库ID；不是第三独立仓库。未据此推断谁要求改名 |

两份远程README相同，只记录 **R1–R6**；最后提交时间为2026-10-02T01:10:11Z。R7–R12目前只见本机README。远程goal.md、plan.md、work.md返回404，主仓库完整递归树也没有三份文件。[固定提交README](https://github.com/yaobc77-ai/ciss-advertising-observatory/blob/7e2fdcb08f9de435d3bd701afe888b3f74377b84/README.md)

本轮新增的R13和分开的目标／完成文件也尚未推送；上述快照保留核查时的内容，不把当前本机修改回填到历史远程记录。

历史意图包括：同步原仓库、额外仓库、README两个网页链接、简单技术说明及不强调语言版本。这些属于用户选择的交付方式；不自动等同于客户指定了这些仓库。旧README中“尚未收到社交资料”不再适用于目前本机已收到资料的状态。

完整快照、URL、提交、404及SHA保存在私有 [GitHub核查目录](../.runtime/goal_ownership_review_20261006/github/)，入口为 [inventory.json](../.runtime/goal_ownership_review_20261006/github/inventory.json)。本次没有提交、推送或部署。

## 完成与验收

[client_finish.md](../client_finish.md)记录已核实的原子交付部分：完成时间、证据、完成条件及未覆盖范围。**工程部分完成、模型语义通过、客户签收分别判断。** 不因一个页面、一次测试或一个审查包完成，就把整个研究问题记为完成。

原35项任务的来源和条件继续保留；其中T01“建立客户需求目录”是从来源推导的团队管理任务、同时来自用户请求，不能仅因目录名就登记成客户已验收目标。
