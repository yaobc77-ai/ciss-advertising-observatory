# 合并表新增 12 个 URL：集中审核与纳入建议

审核日期：2026-09-16。方式：AI 辅助本地来源审阅；不是人工金标准，也不是已执行的主库变更。

## 结论

12 项已逐项阅读现有源行、候选状态及可用归档线索，集中审核已完成。建议 **7 项纳入、4 项排除独立广告计数、1 项保留待核**。7 项中，5 项已有可用 CSV 主体，2 项适合先仅纳入元数据。add-04 的纳入以继续覆盖现有 CERAWeek 行业活动付费内容为前提；若范围必须要求已确认的化石燃料公司付款方，则改为待核。

此前已有候选字段和正文启发式检查，并非 12 项从未读过。本次补全的是逐项语义、资源类型、商业身份和范围依据。剩余工作主要是正式纳入决策及少数已列明的来源补证；没有必要把“12 项待审批”表述为“12 个文件未审核”。

**本报告没有执行建议。** 当前 268 条主记录、256 条可计数、221 条可检索的已导入版本保持不变；报告不改原始数据、导入代码、数据库或现有候选快照。CSV 的 `decision_applied` 全为 `false`，`human_decision` 留空。以上为建议，不可直接把建议数量加到当前已导入统计。

| 审核 ID | CSV 逻辑行 | 标题 | 正文字符 | 建议 | 接入方式 |
|---|---:|---|---:|---|---|
| add-01 | 21 | How much CO2 is emitted when you travel? | 0 | 建议纳入 | metadata_only |
| add-02 | 145 | Paid Program: CERAWeek Connection — CeraWeek_DarrenWoods_Video_FB | 0 | 建议排除 | asset_only |
| add-03 | 272 | Paid Program: Why We Need Better Energy Solutions | 5721 | 建议纳入 | text |
| add-04 | 273 | Paid Program: CERAWeek Connection — How Sustainable Is the U.S. Oil and Gas Revolution? | 8389 | 建议纳入 | text_sponsor_unknown |
| add-05 | 274 | Paid Program: CERAWeek Connection — CeraWeek_Article1_Hero | 374 | 建议排除 | asset_only |
| add-06 | 275 | Powering Progress: How Southern Company is ensuring America’s energy future | 7647 | 建议纳入 | text |
| add-07 | 276 | Responsibly Green | 7559 | 建议纳入 | text_date_unknown |
| add-08 | 277 | Who will power the power of tomorrow? | 449 | 建议纳入 | metadata_only |
| add-09 | 278 | （缺标题） | 0 | 保留待核 | pending_evidence |
| add-10 | 279 | Customer Connection | 6612 | 建议排除 | out_of_scope |
| add-11 | 280 | PAID POST by Chevron — Meet The Problem Solvers | 9384 | 建议纳入 | text_date_unknown |
| add-12 | 281 | Unknown Title | 0 | 建议排除 | asset_only |

## 对实施有影响的核实结果

- 4 项正文为空（add-01/02/09/12），2 项只有通用披露或页脚（add-05/08），6 项有实质内容（add-03/04/06/07/10/11）；其中 add-10 范围不符。
- add-05 的 `body_available=True` 是通用披露被误认为正文的具体例子；建议排除附件，没有在本轮改动启发式。add-02 同样有明确 JPG 附件证据。
- add-10 有 Synchrony Financial 直接付款披露；TotalEnergies 仅是错配关键词。add-04/05 的 sponsor 原值是标题；关键词、署名机构和访谈嘉宾均不能代替付款证据。
- add-07 的 6 月 2 日 / 6 月 5 日冲突，以及 add-11 的 1970 日期 / JSONL 20250613 冲突，建议置未知日期并保留来源候选；不阻塞不依赖日期的正文检索。
- 11 个候选 PDF 的实际文件 SHA-256 与索引记录一致，但索引关联依据均为“唯一标题匹配”，因此仍是 `candidate_unverified`。文件完整性检查不等于文章身份、正文完整性或父子关系已经证实；add-12 的 Unknown Title 尤其弱。
- add-06/11 的 PDF 抽取很少，但 CSV 正文可用；add-01/08 的 CSV 不可用，不能把 PDF 自动替换为正文。归档质量和当前正文质量分别判断。
- 6 个超过 500 字符的候选正文与基准表没有逐字或折叠空白后的完全重复；这不是近重复检测或跨版本身份认证。两张 WSJ 附件的父 URL 则与基准表精确匹配。

## 来源与核验边界

- [候选快照](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/outputs/native_import_final.json>)：12 项与本轮读取的 `load_native` candidates 一致。
- [合并 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/nested_unique/native-ads-download/combined_ads_12-4-25.csv>)：SHA-256 `a677a6de6a8c10a4f872456263af72f0f99be4c3c561bf8b7449bce9b892dd57`。行号指**含表头的逻辑记录序号**，不是含换行正文的物理文本行号；12 项 raw 字段均与该行一致。
- [268 基准 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>)：用于 URL 集合、父 URL 和完全重复正文对照。
- [归档索引](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/source_index.json>)：路径、SHA-256、候选来源及文本抽取状态。PDF 关联未升级为 verified。
- [当前导入实现](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/src/observatory/ingest.py>)、[数据字典](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/docs/data_dictionary.md>)：用于区分现有候选判断与本次建议。
- 对存在对应 JSONL 的项目，以 URL 和正文逐字对照；add-12 单独记录 JSONL `null` 与 CSV 空串均表示缺失，不能称两者字符串逐字一致。JSONL 行号是其物理单行 JSON 记录位置。
- 本轮未访问线上页面、未调用模型/付费 API、未把 PDF 文本写回数据。使用现有 PDF 文本抽取和源文件线索，不宣称重新完成了逐页视觉完整性核验。下列可点击网址只标明源地址，不表示本轮已验证其当前在线状态。

## 逐项记录

### add-01 — How much CO2 is emitted when you travel?

- 来源：[原 URL](https://www.cnbc.com/advertorial/2015/05/05/how-much-co2-is-emitted-when-you-travel.html)；CSV 逻辑行 **21**；`record_id=de086de6-209d-5b9c-9ff2-95ed6e4c20fd`。
- 原始字段：publisher=CNBC；title=How much CO2 is emitted when you travel?；date=2015-05-05 06:29:25-04:00；sponsor=TOTALENERGIES；keyword=TOTALENERGIES。
- 正文（0 字符）：CSV 正文为空。PDF 文本含付费标题、日期、Total 披露，但主要是图示标题、推荐文章与导航，不能直接当成完整文章。
- 范围关系：CNBC advertorial；付费披露与 Total 身份相互支持，属于化石燃料企业原生广告候选。
- 公司/赞助依据：PDF 文本有 PAID POST BY TOTALENERGIES，并有 THIS PAGE WAS PAID FOR BY TOTAL；保留 Total 与 TotalEnergies 两种历史写法及证据，不由关键词统一改写。
- 元数据处理建议：保留原始发布日期 2015-05-05；PDF 同时记载更新日 2019-03-19，应分开保存，不使用 2025 归档日期。
- 定位线索：PDF-254.txt：第 3 行付费标题，第 10 行发布日期/更新日期，第 37 行 Total 付费披露。
- 归档候选：[PDF-254 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/How much CO2 is emitted when you travel_.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-254.txt>)；7 页 / 3572 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `f18a8172959b670f1b8a6f96463f7f69238fe6db75ee5e1ecbbfd5ea507a7d19` 已与实际文件对照。
- **建议：建议纳入（`metadata_only`）。** 商业身份和范围已有本地披露证据，可建议作为仅元数据记录；正文不足单独阻止 RAG。
- 剩余动作：确认纳入决策；若需要内容问答，再恢复图示主内容并复核页面边界。PDF 推荐区的 Workday 内容不能归于 Total。

### add-02 — Paid Program: CERAWeek Connection — CeraWeek_DarrenWoods_Video_FB

- 来源：[原 URL](https://partners.wsj.com/ceraweek/connection/darren-woods-chairman-ceo-exxonmobil-speaks-daniel-yergin-vice-chairman-ihs-markit/ceraweek_darrenwoods_video_fb/)；CSV 逻辑行 **145**；`record_id=f1b7f3c2-4049-55e7-9717-1a196d6b4336`。
- 原始字段：publisher=The Wall Street Journal；title=Paid Program: CERAWeek Connection — CeraWeek_DarrenWoods_Video_FB；date=2017-03-08 02:06:38+00:00；sponsor=Cera；keyword=Cera。
- 正文（0 字符）：CSV 正文为空。PDF 仅一页，展示资源标题、图片 URL 与通用披露。
- 范围关系：URL 位于已有 CERAWeek 文章下的附件路径；PDF 明确链接同名 .jpg，支持图片附件而非独立广告文章。
- 公司/赞助依据：原 sponsor=Cera 仅保留为原始值；Darren Woods/ExxonMobil 是访谈人物和机构，不能据此确认付款方。
- 元数据处理建议：保留原 URL 和原始字段，作为父文章资源候选；不增加独立文章计数。
- 定位线索：PDF-036.txt 第 2 行资源标题，第 4 行 CeraWeek_DarrenWoods_Video_FB.jpg。
- 归档候选：[PDF-036 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/summer_2025_run/TheWallStreetJournal/2017-03-08 02_06_38 GMT+0000_PaidProgram_CERAWeekConnection—CeraWeek_DarrenWoods_Video_FB.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-036.txt>)；1 页 / 905 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `3ba3086125a1e1f6edbdd01096937532c89bd8a342f8978fc13aead5d5cf46d5` 已与实际文件对照。
- 基准父文章：[父 URL](https://partners.wsj.com/ceraweek/connection/darren-woods-chairman-ceo-exxonmobil-speaks-daniel-yergin-vice-chairman-ihs-markit/) 与 268 基准表精确一致；此证据只支持 URL 层级关系，未合并附件为新文章。
- **建议：建议排除（`asset_only`）。** 同名 .jpg 与父文章 URL 已有记录是具体附件证据；不是凭标题含 Video 就判定视频文章。
- 剩余动作：将资源关系候选交纳入者确认；当前主库不变。

### add-03 — Paid Program: Why We Need Better Energy Solutions

- 来源：[原 URL](https://partners.wsj.com/api/a-road-map-for-bipartisan-energy-progress/)；CSV 逻辑行 **272**；`record_id=1d7d06d8-433c-5b05-bec6-ab91acf1aaae`。
- 原始字段：publisher=WSJ；title=Paid Program: Why We Need Better Energy Solutions；date=2022-11-17 07:23:13+00:00；sponsor=API；keyword=API。
- 正文（5721 字符）：CSV 有连续正文、署名、论证、来源及 WSJ 广告部门披露；适合进入正常正文质量与切块流程。
- 范围关系：API 负责人倡导美国油气生产、管线/LNG、许可改革及低碳技术；主题、作者机构和商业渠道均明确。
- 公司/赞助依据：正文署名 Mike Sommers，President and CEO, American Petroleum Institute；结合 API 品牌 URL 与付费栏目，支持原 sponsor=API，而不是只依赖 keyword。
- 元数据处理建议：CSV/HTML 标题 Why We Need Better Energy Solutions 与 PDF 可见标题 A Road Map for Bipartisan Energy Progress 不同；作为不同来源标题保留，不静默覆盖。
- 定位线索：CSV 全文；PDF-149.txt 第 2 行可见标题；对应 WSJ JSONL 第 1 行。
- 归档候选：[PDF-149 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/WSJ_Paid_Program_Why_We_Need_Better_Energy_Solutions_2022-11-17.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-149.txt>)；3 页 / 7498 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `4eade6b3af797160ab66d7e7530909362edc4c32db92b1ce9e812dd44ced5f32` 已与实际文件对照。
- 对应源记录：[The Wall Street Journal_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The Wall Street Journal_dataset_2025-11-07.jsonl:1>) 第 1 行；URL 精确一致，正文关系 `exact_match`，原 date=`2022-11-17T07:23:13+00:00`。
- **建议：建议纳入（`text`）。** 有可读主体、API 身份及 WSJ 付费栏目证据，建议纳入正文与统计。
- 剩余动作：确认纳入并保留两种标题角色；按现有版本、来源、切块机制接入。

### add-04 — Paid Program: CERAWeek Connection — How Sustainable Is the U.S. Oil and Gas Revolution?

- 来源：[原 URL](https://partners.wsj.com/ceraweek/connection/sustainable-u-s-oil-gas-revolution/)；CSV 逻辑行 **273**；`record_id=0a562ee8-feff-58cd-963b-861b7a441ad7`。
- 原始字段：publisher=WSJ；title=Paid Program: CERAWeek Connection — How Sustainable Is the U.S. Oil and Gas Revolution?；date=2017-03-07 23:08:17+00:00；sponsor=Paid Program: CERAWeek Connection — How Sustainable Is the U.S. Oil and Gas Revolution?；keyword=Ceraweek。
- 正文（8389 字符）：CSV 有完整油气行业分析，开头付费/广告部门说明、作者与末尾机构介绍。
- 范围关系：CERAWeek 付费行业内容讨论美国油气与压裂革命；与当前库已收录的 CERAWeek 行业内容范围一致。
- 公司/赞助依据：原 sponsor 错填整篇标题，不能作为赞助方。作者 IHS Markit 机构身份也不能证明付款方；规范 sponsor 应保持 unknown。
- 元数据处理建议：保留坏 sponsor_raw，规范赞助方置空/unknown。若项目边界要求付款方必须是已确认化石燃料公司，则该项应先待核，而非用 CERAWeek/IHS Markit 自动填充。
- 定位线索：CSV 开头 paid advertiser / WSJ advertising department 说明，末尾作者机构；WSJ JSONL 第 2 行重复坏 sponsor。
- 归档候选：[PDF-010 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/WSJ_Paid_Program_CERAWeek_Connection_How_Sustainable_Is_the_U_S_Oil_and_Gas_Revolution_2017-03-07.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-010.txt>)；2 页 / 9300 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `2b3621ab4cea4ff2829d84639369787d704cd738825f7927be14efd34380da35` 已与实际文件对照。
- 对应源记录：[The Wall Street Journal_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The Wall Street Journal_dataset_2025-11-07.jsonl:2>) 第 2 行；URL 精确一致，正文关系 `exact_match`，原 date=`2017-03-07T23:08:17+00:00`。
- **建议：建议纳入（`text_sponsor_unknown`）。** 按当前包含行业活动付费内容的范围，建议纳入；赞助方缺失不必阻塞正文检索。该建议有明确范围前提。
- 剩余动作：确认是否维持现有 CERAWeek 范围；如维持则以赞助方未知纳入，如要求确认公司付款则转待核。

### add-05 — Paid Program: CERAWeek Connection — CeraWeek_Article1_Hero

- 来源：[原 URL](https://partners.wsj.com/ceraweek/connection/will-u-s-become-swing-producer-global-gas-market/ceraweek_article1_hero/)；CSV 逻辑行 **274**；`record_id=2f4fcd27-c8f1-57d6-9f78-febcae517810`。
- 原始字段：publisher=WSJ；title=Paid Program: CERAWeek Connection — CeraWeek_Article1_Hero；date=2017-03-07 16:26:45+00:00；sponsor=Paid Program: CERAWeek Connection — CeraWeek_Article1_Hero；keyword=Cera。
- 正文（374 字符）：CSV 374 字符、61 个空白分词，只有两段 WSJ 通用披露，没有文章主体；快照 body_available=True 是本条启发式误判。
- 范围关系：原 URL 为已有文章的 CeraWeek_Article1_Hero 附件页；PDF 中同名 .jpg 是明确资源证据。
- 公司/赞助依据：原 sponsor 错填附件标题；不能据标题推断付款方。
- 元数据处理建议：保留附件候选及原始值；不计独立广告，不将通用披露当 RAG 正文。
- 定位线索：CSV 正文仅两段通用披露；PDF-003.txt 第 4 行 CeraWeek_Article1_Hero.jpg；WSJ JSONL 第 3 行。
- 归档候选：[PDF-003 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/WSJ_Paid_Program_CERAWeek_Connection_CeraWeek_Article1_Hero_2017-03-07.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-003.txt>)；1 页 / 933 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `77eba5e5537e7d9d961c221176764ed1877defb2757b9685890acce75d8316a8` 已与实际文件对照。
- 对应源记录：[The Wall Street Journal_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The Wall Street Journal_dataset_2025-11-07.jsonl:3>) 第 3 行；URL 精确一致，正文关系 `exact_match`，原 date=`2017-03-07T16:26:45+00:00`。
- 基准父文章：[父 URL](https://partners.wsj.com/ceraweek/connection/will-u-s-become-swing-producer-global-gas-market/) 与 268 基准表精确一致；此证据只支持 URL 层级关系，未合并附件为新文章。
- **建议：建议排除（`asset_only`）。** 同名图片资源与已存在父文章相互支持；这是应排除的独立文章计数项。
- 剩余动作：纳入决策记录为附件排除；本报告不修改当前 body_available 实现或候选快照。

### add-06 — Powering Progress: How Southern Company is ensuring America’s energy future

- 来源：[原 URL](https://www.washingtonpost.com/creativegroup/southern-company/powering-progress-how-southern-company-is-ensuring-americas-energy-future/)；CSV 逻辑行 **275**；`record_id=5799d6c7-1ca5-5a63-afa2-df243f6a2a60`。
- 原始字段：publisher=The Washington Post；title=Powering Progress: How Southern Company is ensuring America’s energy future；date=2024-09-04；sponsor=Southern Company；keyword=Southern Company。
- 正文（7647 字符）：CSV 有完整问答和日期署名。PDF 10 页仅 466 文本字符，主要重复披露；PDF 抽取缺失不能否定可用 CSV 正文。
- 范围关系：Southern Company CEO 讨论能源组合、天然气、化石燃料减排/CCS、核电与净零，直接涉及项目范围。
- 公司/赞助依据：品牌 URL、问答中的公司 CEO 身份与 PDF 重复 Content from Southern Company 支持公司归属。
- 元数据处理建议：CSV 2024-09-04 与正文日期一致。保持 CSV 为此次正文来源，PDF 仍为归档候选。
- 定位线索：CSV 全文与署名日期；PDF-033.txt 第 8 行等 Content from Southern Company；WaPo JSONL 第 17 行。
- 归档候选：[PDF-033 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/The_Washington_Post_Powering_Progress_How_Southern_Company_is_ensuring_America_s_energy_future_2024-09-04.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-033.txt>)；10 页 / 466 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `067f9e570a570008651ddbdea2a448ed9818825238a075485fe23fd32159af96` 已与实际文件对照。
- 对应源记录：[The Washington Post_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The Washington Post_dataset_2025-11-07.jsonl:17>) 第 17 行；URL 精确一致，正文关系 `exact_match`，原 date=`2024-09-04 19:33:21`。
- **建议：建议纳入（`text`）。** 明确商业公司归属和可用正文；归档文本残缺单独记录，不阻塞 CSV 检索。
- 剩余动作：确认纳入；PDF 如需作为正文替代来源需另行恢复验证。

### add-07 — Responsibly Green

- 来源：[原 URL](https://www.washingtonpost.com/creativegroup/southern-company/responsibly-green/)；CSV 逻辑行 **276**；`record_id=128102c5-6632-5fe7-abe3-dca6920ccf11`。
- 原始字段：publisher=The Washington Post；title=Responsibly Green；date=2023-06-02；sponsor=Southern Company；keyword=Southern Company。
- 正文（7559 字符）：CSV 有连续正文，讨论天然气/煤炭组合、减排、CCS、核电等。
- 范围关系：Southern Company 付费内容，自述能源组合与减排路径；在化石燃料广告分析范围内。
- 公司/赞助依据：品牌 URL、正文公司身份/CEO 引语和对应品牌档案支持 Southern Company；并非只靠关键词。
- 元数据处理建议：CSV/JSONL 为 2023-06-02，正文署名与 PDF 可见日期为 June 5, 2023。规范日期应暂为 unknown，保留两候选与来源，不能静默选一个。
- 定位线索：CSV 正文署名 June 5, 2023；PDF-084.txt 第 6 行；WaPo JSONL 第 18 行日期 2023-06-02T19:24:29。
- 归档候选：[PDF-084 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/The_Washington_Post_Responsibly_Green_2023-06-02.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-084.txt>)；7 页 / 8861 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `4f703091fa44c0d4b66ffe0050d8bd969025fbdbcfe73a531c6d06eb66d6339a` 已与实际文件对照。
- 对应源记录：[The Washington Post_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The Washington Post_dataset_2025-11-07.jsonl:18>) 第 18 行；URL 精确一致，正文关系 `exact_match`，原 date=`2023-06-02T19:24:29`。
- **建议：建议纳入（`text_date_unknown`）。** 商业身份和正文可用；日期冲突只影响日期统计/筛选，不应自动阻塞全文检索。
- 剩余动作：确认纳入；日期语义核对前，在未知日期组展示，保留日期冲突标记。

### add-08 — Who will power the power of tomorrow?

- 来源：[原 URL](https://www.cnbc.com/advertorial/2023/03/09/who-will-power-the-power-of-tomorrow-.html)；CSV 逻辑行 **277**；`record_id=0ba2f283-4ea6-5c44-9df3-a4ecfe393bc4`。
- 原始字段：publisher=CNBC；title=Who will power the power of tomorrow?；date=2023-03-09 19:25:11+00:00；sponsor=THE WILLIAMS COMPANIES, INC.；keyword=Williams。
- 正文（449 字符）：CSV 449 字符、74 个空白分词，只有 CNBC 页脚。PDF 文本有完整度较好的天然气论述，但夹杂重复导航，尚不能直接替换 CSV。
- 范围关系：Williams CEO 倡导天然气与管线、许可改革等；原生广告身份及化石燃料范围明确。
- 公司/赞助依据：PDF 有 PAID POST FOR THE WILLIAMS COMPANIES, INC.、CEO Alan Armstrong 署名和付款披露；支持原 sponsor。
- 元数据处理建议：保留 2023-03-09 发布候选；页脚版权 2025 不得当发布日期。归档正文恢复前 RAG 关闭。
- 定位线索：PDF-014.txt 第 4 行署名、第 15 行付费标题、第 103 行付款披露；CNBC JSONL 第 3 行仅同一页脚。
- 归档候选：[PDF-014 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/CNBC_Who_will_power_the_power_of_tomorrow_2023-03-09.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-014.txt>)；5 页 / 6498 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `7e89123093454c1b8781d13b3fc3b1f915dc9477430d5a8f4906076f9e54b32f` 已与实际文件对照。
- 对应源记录：[CNBC_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/CNBC_dataset_2025-11-07.jsonl:3>) 第 3 行；URL 精确一致，正文关系 `exact_match`，原 date=`2023-03-09T19:25:11+0000`。
- **建议：建议纳入（`metadata_only`）。** 品牌与付费披露充分，可先作元数据记录；现有 CSV 无可用主体。
- 剩余动作：确认元数据纳入；将 PDF 主体边界清理、来源核验和新正文版本作为独立后续项。

### add-09 — （缺失）

- 来源：[原 URL](https://www.theatlantic.com/sponsored/bayer-2024/demystifying-menopause/3935/?sr_source=facebook&sr_lift=true)；CSV 逻辑行 **278**；`record_id=ea80e728-aa1d-5bbb-b77a-5e1a26b64457`。
- 原始字段：publisher=The Atlantic；title=（缺失）；date=（缺失）；sponsor=（缺失）；keyword=PTT。
- 正文（0 字符）：CSV 正文、标题、赞助方、日期均为空；没有本次索引中的匹配 PDF 或 JSONL 来源线索。
- 范围关系：URL 路径提到 Bayer / demystifying-menopause，但这只能作为查证线索，不能据此确认页面内容、付款方或化石燃料范围。
- 公司/赞助依据：keyword=PTT 无正文/披露支持。既不能将 PTT 当赞助方，也不能只凭 URL 改填 Bayer。
- 元数据处理建议：不从 bayer-2024 路径猜发布日期；所有缺失保留 unknown。
- 定位线索：combined CSV 逻辑行 278，只有 URL/媒体/关键词可读。
- 归档线索：本轮索引中无对应 URL 候选；未将相似标题当作匹配。
- **建议：保留待核（`pending_evidence`）。** 缺乏实际广告内容和身份依据，证据不足以纳入，也不足以断言完整文章范围。
- 剩余动作：取得真实页面主内容/付费披露后再定范围；本轮不联网穷尽。

### add-10 — Customer Connection

- 来源：[原 URL](https://www.businessinsider.com/sc/mobile-technology-helps-businesses-connect-with-consumers)；CSV 逻辑行 **279**；`record_id=ae93de49-ce84-5980-ac68-99213f11f7ea`。
- 原始字段：publisher=Business Insider；title=Customer Connection；date=（缺失）；sponsor=（缺失）；keyword=TotalEnergies。
- 正文（6612 字符）：CSV 有金融/移动商业推广主体，但以 That success includes 开始，前文不完整，且重复 Tillys 图片说明。
- 范围关系：内容讨论餐车支付、零售 App 和金融服务；明确赞助方为 Synchrony Financial，不是化石燃料企业推广。
- 公司/赞助依据：正文明确 This post is sponsored by Synchrony Financial.；keyword=TotalEnergies 与直接披露冲突，应保留原值并标错，不能据 keyword 归属 TotalEnergies。
- 元数据处理建议：若另存通用原生广告语料，规范赞助方应以 Synchrony Financial 披露为依据；本项目不纳入。版权 2018 不是已确认发布日期。
- 定位线索：CSV 尾部明确赞助披露及 BI Studios 说明；PDF-184.txt 第 104 行及下一行；BI JSONL 第 1 行。
- 归档候选：[PDF-184 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/Business_Insider_Customer_Connection_NA.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-184.txt>)；18 页 / 6678 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `6a3514b2e761c60dfd092b753ba78aa1525c111ee3ab96dfa179b21d1237c194` 已与实际文件对照。
- 对应源记录：[Business Insider_dataset_2025-11-07.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/Business Insider_dataset_2025-11-07.jsonl:1>) 第 1 行；URL 精确一致，正文关系 `exact_match`，原 date=``。
- **建议：建议排除（`out_of_scope`）。** 有明确商业身份，但属于金融推广，化石燃料范围不成立。
- 剩余动作：记录范围排除；不要为扩充数量纳入，不自动修改原始关键词。

### add-11 — PAID POST by Chevron — Meet The Problem Solvers

- 来源：[原 URL](https://www.nytimes.com/paidpost/chevron/meet-the-problem-solvers.html)；CSV 逻辑行 **280**；`record_id=a513c5b5-5a7e-54ee-abdd-6f8156c77243`。
- 原始字段：publisher=The New York Times；title=PAID POST by Chevron — Meet The Problem Solvers；date=1970-08-23；sponsor=Chevron；keyword=Chevron。
- 正文（9384 字符）：CSV 有完整多人物叙事，涉及油气、CCUS、RNG、氢/CNG 等。PDF 18 页仅 673 文本字符，不能拿它替换可读 CSV。
- 范围关系：Chevron 员工与公司能源/减排项目的原生广告，范围明确。
- 公司/赞助依据：NYT paidpost/chevron URL、PAID POST by Chevron 标题与正文公司/员工身份相互支持。
- 元数据处理建议：CSV 为 1970-08-23；对应 URL 与全文一致的 JSONL 原始 date 为 20250613。后者形似 2025-06-13，但发布日期语义尚未独立确认；规范日期暂 unknown，保留两原值。
- 定位线索：CSV 全文；NYT JSONL 第 5 行 date=20250613，URL 与正文逐字一致。
- 归档候选：[PDF-093 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/The_New_York_Times_PAID_POST_by_Chevron_Meet_The_Problem_Solvers_NA.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-093.txt>)；18 页 / 673 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `b1ce7e630cc743d0fc34a3696de9d8a9ecef538a38ac77ced3b864ac897c9e83` 已与实际文件对照。
- 对应源记录：[The New York Times_dataset_2025-11-06.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The New York Times_dataset_2025-11-06.jsonl:5>) 第 5 行；URL 精确一致，正文关系 `exact_match`，原 date=`20250613`。
- **建议：建议纳入（`text_date_unknown`）。** 公司身份与正文可靠到足以推荐纳入；异常日期单独隔离，不阻塞不依赖日期的功能。
- 剩余动作：确认纳入；进一步核实日期来源语义后才改规范日期，保留来源版本。

### add-12 — Unknown Title

- 来源：[原 URL](https://ad-assets.nytimes.com/paidpost/shell/sky/assets/Shell-LP-Sky-Legal-Disclaimer.pdf)；CSV 逻辑行 **281**；`record_id=b723d7d8-1130-5183-a7e6-a7d6e7aff69a`。
- 原始字段：publisher=The New York Times；title=Unknown Title；date=（缺失）；sponsor=Shell；keyword=Shell。
- 正文（0 字符）：CSV 正文为空，JSONL article=null；两者均为缺失但表示不同。候选 PDF 一页且抽取文本为零。
- 范围关系：URL 明确为 Shell-LP-Sky-Legal-Disclaimer.pdf 法律附件，而不是独立广告文章。
- 公司/赞助依据：Shell 出现在明确资源路径及源字段；这支持资源线索，不代表已确认其应关联哪一篇主文章。
- 元数据处理建议：Unknown Title 不提供可靠身份匹配；仅保留法律附件候选，不增加独立文章计数。
- 定位线索：原 URL 的 legal-disclaimer PDF 路径；NYT JSONL 第 9 行 URL 一致、article/date 为 null。
- 归档候选：[PDF-079 PDF](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/The_New_York_Times_Unknown_Title_NA.pdf>)；[已有抽取文本](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/pdf_archive/text/PDF-079.txt>)；1 页 / 0 文本字符；`candidate_unverified`，索引依据 唯一标题匹配。SHA-256 `85f741e14d3558fdde80501840aabc7523517ea5e83aa5399c715347b7f2fd20` 已与实际文件对照。
- 对应源记录：[The New York Times_dataset_2025-11-06.jsonl](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/pdf_archive_20260915/pdfs/fall_2025_run/jsonl/The New York Times_dataset_2025-11-06.jsonl:9>) 第 9 行；URL 精确一致，正文关系 `both_missing_null_vs_empty`，原 date=`None`。
- **建议：建议排除（`asset_only`）。** 明确 PDF 法律资源 URL 足以排除独立广告计数；不能凭弱标题匹配声称 PDF 完整正文或特定父文章已确认。
- 剩余动作：若需要补齐父文章资产关系，再按具体父页面与资源链接核验；不自动挂接任意 Shell 文章。

## 决策与接入边界

1. 可以直接审阅本报告完成 7 项纳入、4 项范围/资源排除、1 项待核的决定；add-04 另确认现有 CERAWeek 范围前提。纳入决定不能从 `needs_review` 字段自动推导。
2. 如果采纳建议，按当前导入与版本流程增加新版本，保留源行、原字段、正文 hash 和归档候选状态。缺日期/赞助方进入 unknown 分组；缺正文只关闭 RAG，不必阻塞已明确身份的元数据统计。
3. add-01/08 的正文恢复、add-07/11 的日期确认、add-09 的真实页面取证是独立后续项。不得用抓取日期、版权年份、URL 年份、关键词或 PDF 标题命中填补。
4. 结构化 CSV 每项一行，共 12 行，保留原字段与建议字段，便于负责人填写 `human_decision`。本轮只新建本 Markdown 和 CSV 两个交付件。
