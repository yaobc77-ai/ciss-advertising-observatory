# 94 项疑似截断：本地正文恢复预检

日期：2026-09-16。AI 辅助只读候选分析；没有改原文、导入代码、数据库或既有审核决定。

## 结论

**现有 JSONL / 合并 CSV 中，按精确 URL 可直接恢复完整正文的记录为 0。** 94 项在合并表中的对应正文也全部不超过 3,000 字符，并以 `...` 结束。不能将“有同 URL”或“字符稍多”算作全文恢复。

另精读了 3 份已有 PDF 抽取文本，均有 CSV 截点之后的同篇续文与可辨收尾，可作为下一轮有界恢复试点；但**本轮没有确认任何一篇完整正文已恢复**。三个 PDF 都缺完整目标 URL 的直接文本/链接证据，索引仍是标题候选；两份还存在明显字形抽取错误。

## 精确统计

| 检查 | 结果 |
|---|---:|
| 快照中的截断警告 / 不同记录 | 94 / 94 |
| 媒体分布 | CNBC 83；WSJ 9；Business Insider 2 |
| 本地 fall JSONL | 7 文件 / 45 行 |
| JSONL 与这 94 项精确 URL 命中 | 0 |
| combined CSV | 2 份文件、同一 SHA-256；280 行 / 280 URL |
| combined 与这 94 项精确 URL 命中 | 94 |
| 对应正文字符数较长 / 相同 / 较短 | 53 / 41 / 0 |
| 合并表对应正文仍以省略号结束 | 94 |
| 合并表对应正文超过 3,000 字符 | 0 |
| 逐字一致 / 仅空白差异 | 39 / 6 |
| NFKC、标点或空白规范后相同 / 其他差异 | 9 / 40 |
| 已确认的结构化全文恢复 | 0 |

两份合并表只是相同文件内容的不同本地副本，不能作为两份独立采集结果。比较用的 Unicode/标点/空白处理只用于诊断，没有写回任何正文；40 项其他差异没有被擅自认定为排版差异。字符增加最多的一项也只有 189 字符。

例如 Explaining energy to future citizens：基准逻辑行 38 为 2,852 字符，combined 行 39 为 3,000 字符；合并表补有 planete-energies.com 等中间文字，但结尾仍停在教学包问卷结果的半句话，不能据此清除截断标记。

## 三个可执行的下一步入口

下表的 PDF 来源关联均保留 `candidate_unverified`。身份支持来自目标 URL 的表格记录加上跨位置正文对应、人物/主题与截点续接，不只看标题；仍不等于完整 URL、版本和视觉完整性已经确认。

| 优先级 | 记录 / 归档 | 能补什么 | 尚缺什么 |
|---|---|---|---|
| 1 | Using mollusks… / PDF-265 | 2.5 million data 后的持续时间、应用环境、河口待验证、成本与收尾 | 页导航清理；正文身份与页面核对；自身完整 URL 未捕获 |
| 2 | Explaining energy… / PDF-206 | 问卷结果、教师材料选择、交叉核对信息、文章结论 | 字体抽取错字；URL 页眉被省略；补中间网站名与补结尾分开处理 |
| 3 | Can R&D solve… / PDF-177 | R&D 周期之后的合作、市场及主论述结尾 | 字形异常；页眉/内嵌链接；创新排行侧栏的角色边界 |

### candidate-01 — Using mollusks to monitor industrial sites

- [原 URL](https://www.cnbc.com/advertorial/2018/12/28/using-mollusks-to-monitor-industrial-sites.html)；基准逻辑行 80；record_id=`d340f887-efa7-5746-aaf8-14aabba6b63f`。
- [PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/2018-12-28T10_21_52-0500_Usingmolluskstomonitorindustrialsites.pdf>) / [已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-265.txt>)；6 页、7098 抽取字符。PDF SHA-256 `20b2ec33f808d96dc749ce0c62cd8b35dec43da48d7df0db44905544cb93479c` 已与实际文件一致性核对。
- 身份与续文证据：源 CSV 与 PDF 开头的贝类监测、Total/CNRS、Laurent Cazes 以及截点前十六只贝类/250万数据叙事一致；PDF 第3页接上 daily，并继续应用环境、河口待验证、成本及结尾。
- 页面候选范围：1–5；不是本轮已发布的正文区间。
- continuation 锚点（PDF 第 3 页；文本行 111；原字符 [3257,3330)）：`daily over long periods — at least two or three years — and continuously.`。JSON 保存未折叠换行的原始锚点。
- main_ending 锚点（PDF 第 5 页；文本行 187；原字符 [5429,5484)）：`Other industrial sites have plans to deploy the system.`。JSON 保存未折叠换行的原始锚点。
- 不能自动恢复的原因：PDF 自身未提取到完整目标 URL；当前关联仍是标题候选，但正文对应和截点续接提供额外内容证据。每页重复导航和付费栏，且第3页有另一个 Be Bold 链接；不可整份文本直接入库。
- 建议下一步：三篇中优先的小试点。先核对原PDF页面/边界与CSV内容身份，再生成有逐段定位的新正文版本；保留原始URL身份的不确定性，不能仅靠标题升级。

### candidate-02 — Explaining energy to future citizens

- [原 URL](https://www.cnbc.com/advertorial/2016/09/29/explaining-energy-to-future-citizens.html)；基准逻辑行 38；record_id=`2123540e-b363-5daf-9308-4655f00e0d8e`。
- [PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/Explaining energy to future citizens.pdf>) / [已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-206.txt>)；8 页、7511 抽取字符。PDF SHA-256 `16f5452dc0c9f9c7fd99536f5437dd732e40a96bc94ddafb5c6b21af545268cf` 已与实际文件一致性核对。
- 身份与续文证据：精确 URL 对照的 combined 行39可补回 planete-energies.com 等中间内容，却仍在 teachers...show that 截断；PDF 第4页补完问卷结果，第5–6页继续教师选择、交叉核对信息和结论，随后是付费披露。
- 页面候选范围：1–6；不是本轮已发布的正文区间。
- continuation 锚点（PDF 第 4 页；文本行 94；原字符 [3564,3607)）：`that they’re fans of the content’s quality.`。JSON 保存未折叠换行的原始锚点。
- main_ending 锚点（PDF 第 6 页；文本行 150；原字符 [5821,5854)）：`Ms. Dizel-Doumenge in conclusion.`。JSON 保存未折叠换行的原始锚点。
- 不能自动恢复的原因：PDF 页眉只有目标 URL 前缀；字体抽取有 diTerently、justi[ed 等异常，不能无依据全局替字。缺网站名与文尾缺失是两个不同问题。
- 建议下一步：先尝试从PDF重新提取并按页面核对字形，确认去掉页眉/链接后续文完整；不得用combined中间差异冒充结尾恢复。

### candidate-03 — Can R&D solve the daunting challenges of taking carbon out of the equation?

- [原 URL](https://www.cnbc.com/advertorial/2017/02/07/can-rd-solve-the-daunting-challenges-of-taking-carbon-out-of-the-equation.html)；基准逻辑行 44；record_id=`99195345-0b7d-55ac-8249-9d5a47f5d23c`。
- [PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/Can R&D solve the daunting challenges of taking carbon out of the equation_.pdf>) / [已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-177.txt>)；13 页、13052 抽取字符。PDF SHA-256 `a239078a7a46c44513e6618140854afe32229ed58401c76eb193d57c6697fe84` 已与实际文件一致性核对。
- 身份与续文证据：CSV、合并表与PDF共有 David Nevicato、CCUS成本/效率限制及 R&D long cycles 段；PDF 第5页接上 must adapt，随后谈合作、投资和商业化；第9页主论述有收尾。
- 页面候选范围：1–9（主论述）；9–11另有创新排行侧栏；不是本轮已发布的正文区间。
- continuation 锚点（PDF 第 5 页；文本行 95；原字符 [3845,3869)）：`concept, R&D must adapt.`。JSON 保存未折叠换行的原始锚点。
- main_ending 锚点（PDF 第 9 页；文本行 246；原字符 [9632,9672)）：`Total is ready to tackle the challenges.`。JSON 保存未折叠换行的原始锚点。
- 不能自动恢复的原因：页眉只有目标 URL 前缀；抽取出现 Arst/eDciency/diMerently 等字形异常。第9–11页是 Total Ranks Among the Top 100 Global Innovators 侧栏，须明确正文/附栏角色，不能与主论述无缝拼接。
- 建议下一步：待较简单试点完成后处理；逐页核对字体和侧栏边界，再决定是否收录附栏。存在更多文字不等于已完成全文恢复。

## 最小恢复流程与限制

1. 先只处理 PDF-265 一个候选，核对页首、CSV 截点与正文收尾；确认是目标文章，再记录实际来源版本及内容身份依据。若仍仅有弱标题证据，继续保留候选。
2. 对已确认的 PDF 保存提取器版本、文件 hash、页面/字符定位与清理区间。去掉页眉、导航和披露时保留原始抽取全文，不能跨间隙伪造连续短引文；206/177 的字体错字需回到页面核验。
3. 恢复正文使用新 record_version，并重新生成 chunk/检索范围；旧正文、旧版本和引用仍可回溯。当前 native_body_ranges 配置绑定旧正文 hash，不能把旧 offset 套到恢复后的正文。
4. 旧 CLAIMS 标签若依据旧全文，需要保留其旧版本依据，不能把它们说成对新全文重新分析的结果。embedding 更新和付费评测属于后续单独执行，本轮没有触发。
5. 只有核实正文结尾与缺失内容后才能调整该项截断状态。无需等待全部 94 项处理完才上线单篇已验证的改进，也不能一次批量清除 94 条警告。

## 可访问输入与输出

- [输入导入快照](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/outputs/native_import_v0_2_published_repeat_20260916.json>)；SHA-256 `057775e230ca3edb34356b7e279bcae0b09aaf3f0644d0bd848ae609bdfd8ef4`。
- [268 基准 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>)；SHA-256 `689f330321e42ea608070b2590fa24ee6c2bfb06dbc671941b1f0a927f4ceffa`。
- [合并表副本一](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/Native Advertising Data/combined_ads_12-4-25.csv>) / [副本二](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv>)；共同 SHA-256 `a677a6de6a8c10a4f872456263af72f0f99be4c3c561bf8b7449bce9b892dd57`。
- [逐项 JSON 预检](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/reports/truncation_recovery_preflight.json>)：94 条记录的 URL/源行/原文 hash/字符关系/终点锚点，以及 7 个 JSONL 的路径、hash 和行数，3 个 PDF 候选的原文定位。
- CSV 行号为含表头的逻辑记录；JSONL 行号为物理单行记录。没有按数字 ID 跨文件盲目拼接，也没有根据标题相似度升级文章身份。
- 预检只证明这些本地材料目前包含什么。疑似截断是模式标记，不证明具体采集工具为何截断，也不证明网上不存在完整文章。

## 补充身份检查：实际 PDF 注释与元数据

根据主任务要求，本轮另外直接读取三份 PDF 的所有页面注释，递归检查链接动作（含 A/AA/Next），并检查 Info 元数据、XMP 与 catalog URI base；没有执行任何 PDF 动作。检查的是实际文件对象，不只复用索引或打印页眉。

| PDF | 页数 | URI 注释 / 唯一 URI | 完整自身 URL 命中 | Info / XMP |
|---|---:|---:|---:|---|
| PDF-265 | 6 | 113 / 53 | 0 | Info 有标题；无 XMP |
| PDF-206 | 8 | 116 / 40 | 0 | Info 有标题；无 XMP |
| PDF-177 | 13 | 157 / 45 | 0 | Info 有标题；无 XMP |

结果：没有在成功读取的注释字符串、URI 动作或 Info 元数据中发现目标文章的完整自身 URL；三份都没有 XMP 流或 catalog URI base。标题元数据与目标标题相符，但不能单独证明 canonical URL、发表日期或全文完整性。PDF-265 的相关链接确实指向 biogas / Be Bold 等另一篇文章，不是其自身 URL。

PDF-206 与 PDF-177 的创建器为 Firefox / Quartz，创建时间分别为 2025-11-14；PDF-265 为 HeadlessChrome / Skia，创建时间为 2025-11-07。这些是捕获文件时间，不能当成原文章发表时间。

解析 PDF-206/177 时 pypdf 报告少量指向 offset 0 的对象警告，读取仍完成。完整警告和实际 URI 列表保存在 JSON。因此结论限定为成功读取的附着注释/元数据中没有找到，而不是认证所有孤立或损坏对象都绝无信息。文件 SHA-256 前后相同。

当前 candidate_unverified 状态保持不变。缺自身链接不证明关联错误，也不否定跨位置正文一致的辅助证据；后续可结合原页面、截点续接和原始采集清单作内容身份审核，不能仅以标题自动升级。
