# 20 个正文前缀边界的集中审阅

日期：2026-09-16。这是 AI 辅助工程边界审阅，不是人工金标准；所有人工判定列留空。正文内容真实性、来源完整性与导航边界分别记录。

## 结论

20 项均已实际阅读当前保留前缀和其余源文本，导航位于正文内部。**19 项删除了含完整句段的同篇后文，1 项删除了同篇残句；没有一项可把整个后缀判为纯导航。** 26 个导航块可以按原文定位最小排除区间，本轮为全部 20 项给出明确保留区间建议。后 10 项的 15 个区间经过第二个 AI 审阅者独立核对，数值一致；这不等于人工通过率。

这 20 项源文本共 62,389 字符。旧前缀合计 32,852 字符；建议保留 60,410 字符、只排除 1,979 字符导航。旧边界后恢复 27,624 字符，同时从旧前缀中移除 66 字符系列横幅。字符增量不是新增事实数量，也不是完整文档恢复率。

- 最严重的是基准逻辑行 4 的农村教育广告：旧边界 365，原文 5590 字符；正文在 383 恢复，横幅实际从 299 开始。因此保留 [0,299) 与 [383,5590)，而不是把边界简单放到文末。
- 19 篇 CNBC 文本的 For more on the subject 是插入式相关文章链接，链接标题后继续目标文章。Lacq、两篇 CES、R&D Priorities、机器人油井与太阳能服务站中有第二个链接块，均逐一排除。
- Seven sustainable mobility（pb-07）在链接后只剩 90 字符残句。它确实属于文章后文，仍不宜单独用来支持一个完整事实。
- CNBC 19 项仍有源文本尾部省略/截断问题；Lubricating electric vehicles 与 R&D Priorities 还可见未展开的清单提示。修正导航不会凭空恢复这些缺失内容。
- Using mollusks 的 Biogas to offset air travel emissions 是链接标题，已作为导航排除；其后真正应恢复的是贝类监测方法。不同人物在同一篇 CES 报道中的演讲不是混篇证据。

## 文件与范围规则

- [审阅 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/reports/prefix_boundary_review.csv>)：20 行，保存 record_id、源行、正文 hash、旧边界、前后原文锚点、全部导航原文与建议区间；human_verdict 全空。
- [可采纳配置](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/config/native_body_ranges.json>)：schema_version=1，review_id=native-body-ranges-20260916-v1，reviewer_type=ai；20 项均有明确区间，无猜测项。
- [基准 CSV](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/FA25_SP26/final_dataset_cleaned.csv>)：SHA-256 `689f330321e42ea608070b2590fa24ee6c2bfb06dbc671941b1f0a927f4ceffa`；所有 source_row 都是含表头的逻辑行，不能当成多行 CSV 的物理行号。
- 区间使用 Python Unicode 字符索引，半开 [start,end)。retained_ranges 按原位置有序排列，分别切块且保留全局 offset；不能把跨删除区间的文字拼接后冒充连续原文引用。
- 配置采纳前需验证源文件 hash、URL、逻辑行、正文 hash、区间顺序/边界及导航锚点。正文或来源版本变化时必须重新匹配，不能裸用旧数字 offset。
- 报告/配置只描述本轮建议；本审阅没有改写原 body、主库、导入代码、归档状态或历史报告。父任务若采纳，需在新版本中记录应用结果。

## 证据边界

本轮读的是现有 CSV 里的全部字符，并核对读取时 load_native 的旧 retrieval_end 和原字段；没有线上穷尽、付费模型调用或重新认证整个网页/PDF。source_integrity_assessment 只证明本次正文与指定本地源文件一致。判断某段是同篇后文，不等于广告中的数量、环境承诺或公司自述已经查实。

保留完整原 body；只改变可检索字符范围。截断风险继续保留，不能用恢复后的片段作“全文没有提到某事”的阴性断言。范围明确的导航修正可先作工程采纳，人工语义验收仍独立。

## 汇总

| ID | 源行 | 标题 | 旧边界 / 原长 | 建议保留区间 | 判断 |
|---|---:|---|---:|---|---|
| pb-01 | 4 | The New Science of Rural Education | 365 / 5590 | `[[0, 299], [383, 5590]]` | 同篇正文被排除 |
| pb-02 | 38 | Explaining energy to future citizens | 1176 / 2852 | `[[0, 1176], [1201, 2852]]` | 同篇正文被排除 |
| pb-03 | 41 | Babyloan and Total, microfinancing access to energy | 932 / 3000 | `[[0, 932], [1006, 3000]]` | 同篇正文被排除 |
| pb-04 | 43 | Total's innovation-boosting production pilots | 2334 / 2998 | `[[0, 2334], [2396, 2998]]` | 同篇正文被排除 |
| pb-05 | 44 | Can R&D solve the daunting challenges of taking carbon out of the equation? | 2110 / 2993 | `[[0, 2110], [2179, 2993]]` | 同篇正文被排除 |
| pb-06 | 45 | Algorithms to make energy smarter | 2277 / 2998 | `[[0, 2277], [2362, 2998]]` | 同篇正文被排除 |
| pb-07 | 67 | Seven sustainable mobility solutions that work, in less than 10 years | 2830 / 2998 | `[[0, 2830], [2908, 2998]]` | 同篇残句被排除 |
| pb-08 | 70 | World Gas Conference 2018: The major challenges of natural gas | 2348 / 2996 | `[[0, 2348], [2460, 2996]]` | 同篇正文被排除 |
| pb-09 | 71 | A competitive Lacq embraces the circular economy | 1029 / 2995 | `[[0, 1029], [1089, 2774], [2859, 2995]]` | 同篇正文被排除 |
| pb-10 | 78 | 10 million tons of carbon not emitted | 1682 / 2998 | `[[0, 1682], [1761, 2998]]` | 同篇正文被排除 |
| pb-11 | 80 | Using mollusks to monitor industrial sites | 2050 / 2998 | `[[0, 2050], [2113, 2998]]` | 同篇正文被排除 |
| pb-12 | 82 | Lampiris 'tanks up' on electric vehicles | 1425 / 2998 | `[[0, 1425], [1505, 2998]]` | 同篇正文被排除 |
| pb-13 | 83 | Lubricating electric vehicles | 1227 / 2998 | `[[0, 1227], [1307, 2998]]` | 同篇正文被排除 |
| pb-14 | 84 | CES 2019: The Epicenter of Innovative Technology | 1616 / 2996 | `[[0, 1616], [1687, 2862], [2952, 2996]]` | 同篇正文被排除 |
| pb-15 | 85 | Total at the 2019 CES: Digital Inspiration | 1547 / 2996 | `[[0, 1547], [1621, 2558], [2624, 2996]]` | 同篇正文被排除 |
| pb-16 | 86 | R&D Priorities: Cost Reduction and the Environment | 1055 / 2999 | `[[0, 1055], [1124, 1872], [1973, 2999]]` | 同篇正文被排除 |
| pb-17 | 88 | How natural gas will help make beautiful China real | 1612 / 2996 | `[[0, 1612], [1691, 2996]]` | 同篇正文被排除 |
| pb-18 | 89 | Polystyrene: Focus on Recycling | 2289 / 2998 | `[[0, 2289], [2358, 2998]]` | 同篇正文被排除 |
| pb-19 | 92 | Getting ready for robot-operated oil rigs | 1238 / 2996 | `[[0, 1238], [1314, 2724], [2814, 2996]]` | 同篇正文被排除 |
| pb-20 | 93 | Total plans to solarize 5,000 service stations as part of its decarbonization drive | 1710 / 2996 | `[[0, 1710], [1817, 2637], [2688, 2996]]` | 同篇正文被排除 |

## 逐项审阅

### pb-01

**The New Science of Rural Education**

- 来源：[原 URL](https://www.theatlantic.com/sponsored/chevron-stem-education/the-science-of-rural-education/207/)；基准 CSV 逻辑行 4；record_id=`56c271d4-5075-58fa-b874-58ac2b02e372`。
- 正文 SHA-256：`75dcef52f15e8a8ae5fe0ba5b94e51978ecbc6f04c1068a19de39a94f21fe5bc`；5590 字符；旧前缀 [0,365)。
- 旧边界前原文锚点：facing most Americans around the U.S.A Multi-part Series:Re-engineering the Futureof American Education
- 旧边界后原文锚点：Read More Stories Although the country as a whole had lost 3.7
- AI 判断：系列横幅插在第一段与同篇就业/STEM 叙事之间。当前前缀还保留了横幅前半段，并漏掉 Chevron、Benedum 与教育计划的主体。
- 建议保留：`[[0, 299], [383, 5590]]`。仅排除以下已定位导航：
  - [299,383)：`A Multi-part Series:Re-engineering the Futureof American EducationRead More Stories `
    正文恢复点 383：Although the country as a whole had lost 3.7 million jobs since
- 完整性单独结论：未见文尾硬截断；未核实网页全篇完整性。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-02

**Explaining energy to future citizens**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2016/09/29/explaining-energy-to-future-citizens.html)；基准 CSV 逻辑行 38；record_id=`2123540e-b363-5daf-9308-4655f00e0d8e`。
- 正文 SHA-256：`9fec020f4b985da1f03d7ad075a4718575cd9ea8eec5bf1da338c050e8db808a`；2852 字符；旧前缀 [0,1176)。
- 旧边界前原文锚点：site for knowledge and facts about energy — every type of energy.
- 旧边界后原文锚点：For more on the subject: This goal did not go unnoticed by
- AI 判断：导航标记后立即继续前文的教育目标，并介绍 Nathan 与 Total 的教学材料合作、学校推广及教师反馈；不能视为导航页脚。
- 建议保留：`[[0, 1176], [1201, 2852]]`。仅排除以下已定位导航：
  - [1176,1201)：`For more on the subject: `
    正文恢复点 1201：This goal did not go unnoticed by a major French educational publisher,
- 完整性单独结论：原文末尾省略，且开头/正文的网站名称疑似丢失；区间修正不补造名称。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-03

**Babyloan and Total, microfinancing access to energy**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2016/11/14/babyloan-and-total-microfinancing-access-to-energy.html)；基准 CSV 逻辑行 41；record_id=`44f246bc-5fe4-516d-b402-c7498cb0263e`。
- 正文 SHA-256：`dc470f4e9201218663d64017f5a42a073f27274780007e80c74ac4c644326135`；3000 字符；旧前缀 [0,932)。
- 旧边界前原文锚点：— and jumped at the chance to work on a joint project.
- 旧边界后原文锚点：For more on the subject: Awango by Total: Global Vision, Local Deployment
- AI 判断：Awango 是相关链接标题；AP/PC 对话随后继续 Babyloan 与 Total 合作的项目管理、微贷机构筛选及融资机制。
- 建议保留：`[[0, 932], [1006, 3000]]`。仅排除以下已定位导航：
  - [932,1006)：`For more on the subject: Awango by Total: Global Vision, Local Deployment `
    正文恢复点 1006：AP: There are several. For starters, working with Total involves lots of
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-04

**Total's innovation-boosting production pilots**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2017/01/18/totals-innovation-boosting-production-pilots.html)；基准 CSV 逻辑行 43；record_id=`f0787f9b-dd46-5650-9bac-8fb1712de882`。
- 正文 SHA-256：`257ae01629ec60ec5349d6fe74bb733e3972cdc9210307bb2c2094f7d49373f8`；2998 字符；旧前缀 [0,2334)。
- 旧边界前原文锚点：six front-line projects were picked to move on to the incubation phase.
- 旧边界后原文锚点：For more on the subject: Total at the forefront of transition There
- AI 判断：相关链接结束后继续 Miguel 对 Plant 4.0、员工与初创企业合作方式的论述，沿用同一人物和主题。
- 建议保留：`[[0, 2334], [2396, 2998]]`。仅排除以下已定位导航：
  - [2334,2396)：`For more on the subject: Total at the forefront of transition `
    正文恢复点 2396：There are, of course, technical solutions, or genuine innovations, "Some of which
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-05

**Can R&D solve the daunting challenges of taking carbon out of the equation?**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2017/02/07/can-rd-solve-the-daunting-challenges-of-taking-carbon-out-of-the-equation.html)；基准 CSV 逻辑行 44；record_id=`99195345-0b7d-55ac-8249-9d5a47f5d23c`。
- 正文 SHA-256：`d7dd8c181bd09be93632a1343def76a12691aca61aa050621ca8b355c6073af9`；2993 字符；旧前缀 [0,2110)。
- 旧边界前原文锚点：to find new processes and disruptive technologies, innovate, and improve existing ones.
- 旧边界后原文锚点：For more on the subject: Total Energy Ventures Invests in the Future
- AI 判断：链接后仍是 Total CCUS 研发挑战，包括捕集效率损失、运输材料、储层完整性与市场条件；这些限制会被现边界遗漏。
- 建议保留：`[[0, 2110], [2179, 2993]]`。仅排除以下已定位导航：
  - [2110,2179)：`For more on the subject: Total Energy Ventures Invests in the Future `
    正文恢复点 2179：And the challenges abound. For example, capturing the carbon from a coal-fired
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-06

**Algorithms to make energy smarter**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2017/02/17/algorithms-to-make-energy-smarter.html)；基准 CSV 逻辑行 45；record_id=`b3f111b8-a190-57d1-ad50-9a111773f1fd`。
- 正文 SHA-256：`580a0d42a1b6b9264477463df6915f8093cabc1ab67b2077c54ad56dc866a1fd`；2998 字符；旧前缀 [0,2277)。
- 旧边界前原文锚点：disparate objects, and using them to operate and manage grids more efficiently.
- 旧边界后原文锚点：For more on the subject: Pangea, High Performance Computing for 3D Oilfield
- AI 判断：Pangea 油田建模是链接标题；随后回到 AutoGrid 与 TEV 投资、数字能源管理和同篇受访者观点。
- 建议保留：`[[0, 2277], [2362, 2998]]`。仅排除以下已定位导航：
  - [2277,2362)：`For more on the subject: Pangea, High Performance Computing for 3D Oilfield Modeling `
    正文恢复点 2362：That is right up AutoGrid's alley. Total Energy Ventures, the Group's corporate
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-07

**Seven sustainable mobility solutions that work, in less than 10 years**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2018/05/29/seven-sustainable-mobility-solutions-that-work-in-less-than-10-years.html)；基准 CSV 逻辑行 67；record_id=`b34253c5-213e-5057-8fc5-1a9872709cab`。
- 正文 SHA-256：`0c07ce770f58c8af88d0dfe7e1ed05345f0ccee0ad6314fc1eed81ff6229c7be`；2998 字符；旧前缀 [0,2830)。
- 旧边界前原文锚点：make their voices count and take very concrete, short- and medium-term action.
- 旧边界后原文锚点：For more on the subject: Addressing the challenge of 1.8 billion cars
- AI 判断：交通链接标题之后是本篇回答的开头，但现有源文件只余 90 字符残句。它不是导航；恢复该片段不意味着得到一个完整可引用事实。
- 建议保留：`[[0, 2830], [2908, 2998]]`。仅排除以下已定位导航：
  - [2830,2908)：`For more on the subject: Addressing the challenge of 1.8 billion cars in 2035 `
    正文恢复点 2908：First, sustainable mobility articulates perfectly with Total's ambition to be the respo...
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-08

**World Gas Conference 2018: The major challenges of natural gas**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2018/07/18/world-gas-conference-2018-the-major-challenges-of-natural-gas.html)；基准 CSV 逻辑行 70；record_id=`f8d21b65-795c-58b0-b3b1-33e68c200534`。
- 正文 SHA-256：`026268aa8ad87be179e03ba8ae4419c245359f43ed1ab937e7db89047d7f06fb`；2996 字符；旧前缀 [0,2348)。
- 旧边界前原文锚点：with cheaper fuels, such as coal, that have a greater environmental impact.
- 旧边界后原文锚点：For more on the subject: Total at WGC 2015: Propelling Natural Gas
- AI 判断：2015 WGC 是相关链接标题；后文继续当前 WGC 的行业活动、Total 参会及天然气投资历史。
- 建议保留：`[[0, 2348], [2460, 2996]]`。仅排除以下已定位导航：
  - [2348,2460)：`For more on the subject: Total at WGC 2015: Propelling Natural Gas to the Center of the Future World Energy Mix `
    正文恢复点 2460：The WGC is a must-attend event. Since 1931, it has been the
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-09

**A competitive Lacq embraces the circular economy**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2018/08/03/a-competitive-lacq-embraces-the-circular-economy.html)；基准 CSV 逻辑行 71；record_id=`f13fa000-f2b1-5551-a93b-bf09e31d784e`。
- 正文 SHA-256：`ad12ac1801636bf6233e6fa7e709c83c4a93f2ee2107cf0af0b914af99f4a209`；2995 字符；旧前缀 [0,1029)。
- 旧边界前原文锚点：as Arkema, Toray CFE and Vertex. Continuity and renewal, in one package.
- 旧边界后原文锚点：For more on the subject: Delivering on all of gas' promises Here
- AI 判断：两块相关链接之间是本篇 SOBEGI/PEGAZE 联产机制、H2S 与甲烷处理、发电容量和供能比例；第二块之后仍回到 Lacq 本地生产优势。
- 建议保留：`[[0, 1029], [1089, 2774], [2859, 2995]]`。仅排除以下已定位导航：
  - [1029,1089)：`For more on the subject: Delivering on all of gas' promises `
    正文恢复点 1089：Here at Lacq in southwestern France, SOBEGI's customers reap the benefits of
  - [2774,2859)：`For more on the subject: Flaring: Equivalent to taking 77 million cars off the road? `
    正文恢复点 2859：There are many advantages to producing energy locally. Taken from the Lacq
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-10

**10 million tons of carbon not emitted**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2018/11/26/10-million-tons-of-carbon-not-emitted.html)；基准 CSV 逻辑行 78；record_id=`2e992194-2799-5a0c-a62d-34fe0492f605`。
- 正文 SHA-256：`407e4350147088666803b53d18f55d18d0e43ca60e0b2d2129b86ae8a82a65f8`；2998 字符；旧前缀 [0,1682)。
- 旧边界前原文锚点：offer at least one Total Ecosolutions product or service in every market."
- 旧边界后原文锚点：For more on the subject: The Bitumen Industry Tackles Environmental Challenges What
- AI 判断：沥青文章是链接标题；后文继续本篇 Ecosolutions 的 ISO 14020/14021、EY 核验、申请材料及营销团队流程。
- 建议保留：`[[0, 1682], [1761, 2998]]`。仅排除以下已定位导航：
  - [1682,1761)：`For more on the subject: The Bitumen Industry Tackles Environmental Challenges `
    正文恢复点 1761：What makes the Total Ecosolutions label reliable is the labeling process, which
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-11

**Using mollusks to monitor industrial sites**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2018/12/28/using-mollusks-to-monitor-industrial-sites.html)；基准 CSV 逻辑行 80；record_id=`d340f887-efa7-5746-aaf8-14aabba6b63f`。
- 正文 SHA-256：`fdd9c9ffd4d1934e15e74c3be0a3bf687ccb7a1989b109e226dba4bc28e35ff7`；2998 字符；旧前缀 [0,2050)。
- 旧边界前原文锚点：aim is to interpret and understand what these animals can tell us."
- 旧边界后原文锚点：For more on the subject: Biogas to offset air travel emissions The
- AI 判断：Biogas 是相关链接标题，不能当成 mollusks 文章主题；后文继续 HFNI 贝类开合监测、传感器布置及同一受访者对技术挑战的说明。
- 建议保留：`[[0, 2050], [2113, 2998]]`。仅排除以下已定位导航：
  - [2050,2113)：`For more on the subject: Biogas to offset air travel emissions `
    正文恢复点 2113：The principle of high-frequency, non-invasive (HFNI) valvometry involves observing the mollusks' natural
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-12

**Lampiris 'tanks up' on electric vehicles**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/01/09/lampiris-tanks-up-on-electric-vehicles.html)；基准 CSV 逻辑行 82；record_id=`4f7bf2c4-3f13-5fac-b623-5ea46039ab37`。
- 正文 SHA-256：`085359eeeb35794c9d74ce5ffa714a19a39890ac84df0ef42a6eaa4f9525d29e`；2998 字符；旧前缀 [0,1425)。
- 旧边界前原文锚点：in his gasoline-powered car, an executive sedan, for a smaller electric model.
- 旧边界后原文锚点：For more on the subject: Who Wins from the Internal Combustion Engine's
- AI 判断：内燃机命运是链接标题；后文继续 Lampiris 车队电动化，包括充电站、进度、员工顾虑及公司政策。
- 建议保留：`[[0, 1425], [1505, 2998]]`。仅排除以下已定位导航：
  - [1425,1505)：`For more on the subject: Who Wins from the Internal Combustion Engine's Demise? `
    正文恢复点 1505：Lampiris has installed 14 EV charging stations at its headquarters and gradually
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-13

**Lubricating electric vehicles**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/01/10/lubricating-electric-vehicles.html)；基准 CSV 逻辑行 83；record_id=`29d7b1c7-2492-5319-9dfe-8f4821303260`。
- 正文 SHA-256：`725fab9a7be6c582d62d346d27804f551906a1158a7ed8520fc0f5ae3b71312f`；2998 字符；旧前缀 [0,1227)。
- 旧边界前原文锚点：by Total, which recently introduced its first lubricant range for electric vehicles.
- 旧边界后原文锚点：For more on the subject: Who Wins from the Internal Combustion Engine's
- AI 判断：链接后继续电动车润滑与冷却液、转速/电压要求及 Total Lubrifiants 产品。
- 建议保留：`[[0, 1227], [1307, 2998]]`。仅排除以下已定位导航：
  - [1227,1307)：`For more on the subject: Who Wins from the Internal Combustion Engine's Demise? `
    正文恢复点 1307：Although users aren't always aware of their role, lubricants fulfill a crucial
- 完整性单独结论：原文末尾省略；前缀 Four key factors 后没有可辨的四项清单。删除导航不能修复缺失清单。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-14

**CES 2019: The Epicenter of Innovative Technology**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/01/15/ces-2019-the-epicenter-of-innovative-technology.html)；基准 CSV 逻辑行 84；record_id=`c49154b2-8ff9-507c-b212-e079c3d21964`。
- 正文 SHA-256：`ff8fa06417840b6baa1ef9b79bfe8a49cdd6e89d6ec92023c69b465c2dd115e7`；2996 字符；旧前缀 [0,1616)。
- 旧边界前原文锚点：work devices, from TV sets to industrial monitoring, vehicles and golf gear.
- 旧边界后原文锚点：For more on the subject: Total's Innovation-Boosting Production Pilots For an energy
- AI 判断：两块相关链接之间及之后继续 CES 2019 的 Total 数字化预算、合作伙伴与参展目标；最后恢复点后仍是截断片段。
- 建议保留：`[[0, 1616], [1687, 2862], [2952, 2996]]`。仅排除以下已定位导航：
  - [1616,1687)：`For more on the subject: Total's Innovation-Boosting Production Pilots `
    正文恢复点 1687：For an energy major such as Total, going digital is a key
  - [2862,2952)：`For more on the subject: Innovate or Disappear: Big Companies Look for the Right Solution `
    正文恢复点 2952：Total came to CES 2019 alongside and supp...
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-15

**Total at the 2019 CES: Digital Inspiration**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/01/31/total-at-the-2019-ces-digital-inspiration.html)；基准 CSV 逻辑行 85；record_id=`83beab24-2f9e-57e8-9bdf-0584d6565b40`。
- 正文 SHA-256：`7c13bf1c17f418021a509a4b0b2bf92eb9682b70d521aa680af4827ea9bfcec2`；2996 字符；旧前缀 [0,1547)。
- 旧边界前原文锚点：and help us build the Total of tomorrow," summed up Patrick Pouyanné.
- 旧边界后原文锚点：For more on the subject: CES 2019: The Epicenter of Innovative Technology
- AI 判断：两块链接后分别继续同篇 CES 的 5G 与 AI 演讲及 Total 的应用思考；引用不同公司的演讲属于该篇内容，不能因换了发言者就判为混篇。
- 建议保留：`[[0, 1547], [1621, 2558], [2624, 2996]]`。仅排除以下已定位导航：
  - [1547,1621)：`For more on the subject: CES 2019: The Epicenter of Innovative Technology `
    正文恢复点 1621："5G will change everything – 5G is the promise of so much
  - [2558,2624)：`For more on the subject: Entrepreneurs Dedicated to Energy Access `
    正文恢复点 2624："AI will prove data is the 'world's greatest natural resource,' enabling revolutions
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-16

**R&D Priorities: Cost Reduction and the Environment**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/02/13/rd-priorities-cost-reduction-and-the-environment.html)；基准 CSV 逻辑行 86；record_id=`63f69dad-9d9b-5c75-9d95-92af575789d2`。
- 正文 SHA-256：`b16c83eb0ecadcd689236406f9dd334c2efb92ff3b9f07eb74730135595f05cb`；2999 字符；旧前缀 [0,1055)。
- 旧边界前原文锚点：research projects produce 19 patent filings between 2014 and 2018. (See infographic).
- 旧边界后原文锚点：For more on the subject: Five Barrels of Water for One Barrel
- AI 判断：两块链接后继续 PERL 实验设施、开放创新、研发周期、环境方向与成本限制。
- 建议保留：`[[0, 1055], [1124, 1872], [1973, 2999]]`。仅排除以下已定位导航：
  - [1055,1124)：`For more on the subject: Five Barrels of Water for One Barrel of Oil `
    正文恢复点 1124：The center is home to facilities where work ranges from basic research
  - [1872,1973)：`For more on the subject: Can R&D Solve the Daunting Challenges of Taking Carbon Out of the Equation? `
    正文恢复点 1973：It takes five to ten years to complete an R&D project, depending
- 完整性单独结论：原文末尾省略；前缀 three areas 后及后文 Examples include: 后未见对应完整清单，保持抽取缺项风险。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-17

**How natural gas will help make beautiful China real**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/05/02/how-natural-gas-will-help-make-beautiful-china-real.html)；基准 CSV 逻辑行 88；record_id=`5d891ac9-fd3f-5a8f-8a71-9e08fda5159a`。
- 正文 SHA-256：`68341398b8d957b9bbaa1bb0ec6b760474bc3233ae277761f84a0151e4f67000`；2996 字符；旧前缀 [0,1612)。
- 旧边界前原文锚点：This spectacular growth will eventually add up to 25% of global demand.
- 旧边界后原文锚点：For more on the subject: Energy needs and climate challenges: Gas on
- AI 判断：相关链接之后继续 Total 在 LNG2019 的业务地位、对华 LNG 市场与 Guanghui 供气合同；同篇主体明确。
- 建议保留：`[[0, 1612], [1691, 2996]]`。仅排除以下已定位导航：
  - [1612,1691)：`For more on the subject: Energy needs and climate challenges: Gas on the march `
    正文恢复点 1691：For Total, LNG2019 was an event not to be missed. Present in
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-18

**Polystyrene: Focus on Recycling**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/06/11/polystyrene-focus-on-recycling.html)；基准 CSV 逻辑行 89；record_id=`58773e8b-3b66-5dfd-a5e4-7d79f6afcdd3`。
- 正文 SHA-256：`4dcb228044e4f0902adbba15b9238e3dfdb98301d95f999f6f260b2b448f251c`；2998 字符；旧前缀 [0,2289)。
- 旧边界前原文锚点：has been to show that there's a financial benefit to recycling polystyrene."
- 旧边界后原文锚点：For more on the subject: Climate and Waste, Plastic's Two Challenges In
- AI 判断：塑料气候与废物文章是链接标题；后文继续本篇法国聚苯乙烯回收联盟、参与公司及回收流程困难。
- 建议保留：`[[0, 2289], [2358, 2998]]`。仅排除以下已定位导航：
  - [2289,2358)：`For more on the subject: Climate and Waste, Plastic's Two Challenges `
    正文恢复点 2358：In June 2018, as part of their voluntary commitments under the French
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-19

**Getting ready for robot-operated oil rigs**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/08/12/getting-ready-for-robot-operated-oil-rigs.html)；基准 CSV 逻辑行 92；record_id=`5981b215-a15b-5034-a9c7-1b7fb918c507`。
- 正文 SHA-256：`4394c4f9c89d120880321c4771d44d194806748a2cf6f2bcd3fddbfb2f2ae6ff`；2996 字符；旧前缀 [0,1238)。
- 旧边界前原文锚点：are located in isolated forests or deserts, or in the open sea.
- 旧边界后原文锚点：For more on the subject: R&D Priorities: Cost Reduction and the Environment
- AI 判断：两块链接后分别继续同篇 ARGOS 比赛、Taurob/ATEX 机器人和后续无人设施路线；2017 后续段末尾仍截断。
- 建议保留：`[[0, 1238], [1314, 2724], [2814, 2996]]`。仅排除以下已定位导航：
  - [1238,1314)：`For more on the subject: R&D Priorities: Cost Reduction and the Environment `
    正文恢复点 1314：It was with these requirements in mind that the R&D team in
  - [2724,2814)：`For more on the subject: The Genius Robotics Upstarts That Are Making Energy Giants Safer `
    正文恢复点 2814：In 2017, at the end of this first stage in the process,
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

### pb-20

**Total plans to solarize 5,000 service stations as part of its decarbonization drive**

- 来源：[原 URL](https://www.cnbc.com/advertorial/2019/10/28/total-plans-to-solarize-5000-service-stations-as-part-of-its-decarbonization-drive.html)；基准 CSV 逻辑行 93；record_id=`261c863a-5f17-52cb-89e3-a746ef0b3f94`。
- 正文 SHA-256：`4abfc15774b2d04ab3308d7fc6abc6378960e13dab0e6704c37aa54af01e6fd4`；2996 字符；旧前缀 [0,1710)。
- 旧边界前原文锚点：and avoid more than 50,000 tons of carbon dioxide emissions a year.
- 旧边界后原文锚点：For more on the subject: Total Gives Itself 15 Years to Make
- AI 判断：两块链接后继续本篇服务站太阳能预算、节费/覆盖比例及向厂区办公楼的扩展。不能把 linked 标题的 15 年/15% 或云观测当成此项目论证。
- 建议保留：`[[0, 1710], [1817, 2637], [2688, 2996]]`。仅排除以下已定位导航：
  - [1710,1817)：`For more on the subject: Total Gives Itself 15 Years to Make Its Products 15 Percent Less Carbon Intensive `
    正文恢复点 1817：The project also represents a budget of several hundred million dollars. "That
  - [2637,2688)：`For more on the subject: Watching the Clouds Go By `
    正文恢复点 2688：In addition to solarizing service stations, Total is installing photovoltaic panels at
- 完整性单独结论：原文在约 3000 字符处以省略号结束，保持 body_truncated_suspected；恢复区间不能证明全文完整。
- 来源/真实性单独结论：与指定 hash 的本地 CSV 正文一致；未认证完整线上文章，也未核实广告事实。
- 建议状态：明确区间，可工程采纳；本审阅未执行导入。人工 verdict 留空。

## 本轮验证

- 20 个 record_id / URL / 源行与固定基准一致，正文长度匹配，旧边界确为当时第一处导航标记。
- 26 个最小排除区间的原文逐一保存；保留和排除区间无重叠、无越界，合计覆盖全部原字符。
- 建议保留区间中不再含上述显式导航标记；没有对原文做空白折叠、润色、补字或跨 gap 拼接。
- 本轮只写两个新报告和一个新配置；源 CSV/XLSX 与原候选快照在写入前后 hash 一致。
