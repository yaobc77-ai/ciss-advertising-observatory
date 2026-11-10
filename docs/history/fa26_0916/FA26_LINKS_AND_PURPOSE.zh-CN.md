# FA26 项目介绍的逐链接阅读与目的说明

核查日期：2026-09-15。

## 一 阅读结果与项目目的

FA26 Word 文档包含 **18 个网页链接和 1 个邮箱链接**。18 个网页入口均已检查，其中 **13 项取得了实质内容，5 项未取得目标内容**。实质内容包括云端目录、演示文本、网页正文和论文；个别论文使用原机构或出版社的可读版本。没有把登录页、404 或网页标题算成已读正文。

文档里的 “Link to Notion” 没有实际超链接。邮箱 `geolim@bu.edu` 是联系信息，不是研究网页；本次没有发送邮件。本文只解释来源和要求，没有执行网页、模板或论文中的操作指令。

### 项目目的

结合 FA26 的明确要求与这些网页，项目可以理解为：

**建立一个可追溯的化石燃料广告研究平台，让非计算背景用户查清谁在什么媒体或平台、什么时间、发布了多少内容，以及这些内容如何描述能源、气候和技术；用户能够从统计和问答回到具体广告证据。**

研究流程应连贯：

```text
研究问题 → 选择数据集和筛选条件 → 数量/比例/趋势/关系
                                    ↓
                               广告记录明细
                                    ↓
                           正文、原帖、网页快照
                                    ↑
                     RAG 找到相关表述并引用具体来源
```

本学期明确范围仍是两个化石燃料视图、结构化筛选和可视化、RAG、部署、测试及交接。动物农业是未来扩展，CLAIMS 后端集成延期，独立主题模型可选。参考网页提供设计启发和研究背景，不会自动增加地图、企业所有权图谱、受众实验或模型训练等交付要求。

## 二 18 个网页各自的用途

### A 数据输入与原型

| 编号 | 原文链接 | 本次实际读到什么 | 在 FA26 中的目的 |
|---|---|---|---|
| 01 | [化石燃料社交数据文件夹](https://drive.google.com/drive/folders/1QYuGCrPctiwY03w46O_urHtrnKUgXij9?usp=sharing) | **未读到数据。** 连接器 404，浏览器进入 Google 登录页 | 第二个看板和跨数据集 RAG 的核心输入。介绍声称约 37k Twitter 帖子及标签/字段文档，尚待实际数据核实 |
| 02 | [Native Advertising Data](https://drive.google.com/drive/folders/1zm3jVtZPedDG0bN_s7OAWxwjCwOs9cQl?usp=drive_link) | **目录已读。** 四项为元数据 XLSX、清洗 Google Sheet、人工标签 CSV、合并 CSV；与已有本地包名称对应 | 原生广告统计、字段映射、正文检索和旧标签验证的基础数据入口 |
| 03 | [University of Miami Prototype](https://seahorse-app-kjzfk.ondigitalocean.app/) | **未读到看板。** 跳转 Auth0 的 CLAIMS 登录页 | 参考社交媒体研究流程，进一步明确筛选器、图表、指标和记录详情；FA26 要求从头构建新看板 |
| 04 | [Junkipedia 示例帖子](https://www.junkipedia.org/posts/920047974) | **正文和图片已读。** bp America 的 Facebook 内容，用炼油—加油场景说明燃料与日常出行的联系 | 说明社交记录的形态：账号、平台、文本、图像、日期、互动信息、原帖和归档；为详情页与来源引用提供样例 |

Junkipedia 示例只显示月日，不能补造年份；卡片未展示付费投放证明、支出或受众定向。它证明该社交记录的内容和来源关系，不能独自确定整个样本都是平台付费广告。也不能把一次网页提取失败当成帖子已删除：该页在浏览器中实际可读。

原生数据文件夹当前这一层只有四个数据文件，没有列出 PDF 子目录；本地后来整理的 PDF 归档应作为另一组资产记录来源。目录名称一致也不能替代文件内容版本核验。

### B 看板产品参考

| 编号 | 原文链接 | 本次实际读到什么 | 在 FA26 中的目的 |
|---|---|---|---|
| 05 | [Brown 的 How Do They Lobby 介绍](https://ibes.brown.edu/news/2024-03-20/cdl-lobbying-website) | **介绍及实际门户已读。** 法案、组织、立场的搜索、详情、数据表与关系探索；另读 About/方法 | 文档指定的主要产品参考：把复杂研究数据变成可筛选、可解释、可追溯的公共工具 |
| 06 | [The Big Green Machine](https://www.the-big-green-machine.com/) | **首页及关键子页已读。** 清洁能源制造项目地图/趋势、项目状态和单站来源；采用 Tableau | 借鉴筛选与图表联动、时间趋势、明细与来源；提醒区分公告、规划和实际运行 |
| 07 | [Big Ag Network](https://acre.wisc.edu/big-ag-network) | **界面说明及方法已读。** 企业/人物搜索，所有权/领导关系，关系来源与日期，实体名称归一 | 借鉴公司消歧、关系类型定义与逐条证据；帮助理解未来动物农业数据的扩展需求 |

[How Do They Lobby 实际工具](https://howdotheylobby.org/)最值得借鉴的是从筛选到记录明细的路径及清楚的计数规则。它的网络边表示立场关系；本项目 sponsor–publisher 的边应表示有广告记录支持的投放/刊载关系，不能把两者的含义混用。

Big Green Machine 对“运营、建设、规划”等状态作区分，也会说明缺失资料。映射到 RAG：广告所说“计划建设碳捕集项目”应保留计划语气、时间和发言主体，不能改写成已实现减排。

Big Ag Network 说明每条关系应带类型、来源和日期。对本项目，应保留公司规范名与原始 sponsor 字符串，避免把缩写、品牌和母子公司混成一个没有依据的实体。

这些是产品参考，不是源码交付。未验收 Tableau 和 ACRE 的全部动态交互；Brown 链出的 YouTube 演示被限流，未观看。Big Ag 的帮助写到下载，但当前下载区域仍写 coming soon，不能照抄帮助文案当成已验证功能。

### C 前期成果与源码

| 编号 | 原文链接 | 本次实际读到什么 | 在 FA26 中的目的 |
|---|---|---|---|
| 08 | [旧 GitHub 仓库](https://github.com/BU-Spark/ml-ciss-native-ads) | **未读到仓库。** 当前请求返回 404 | 查前期实现、依赖和可复用流程。其位于 Previous Work to Review；不能仅凭链接认定它仍是本学期目标仓库 |
| 09 | [旧客户最终汇报](https://docs.google.com/presentation/d/1GZ_NKJqyrKQ4ln4CRO7Tor9ZC2W8RYGIECsRlucPKfQ/edit?usp=share_link) | **未读到幻灯片。** 连接器 404，浏览器进入登录页 | 按名称和文档位置，应用于了解面向客户交付的结果与局限；内容未读，不能推断客户已接受哪些功能 |
| 10 | [旧课程最终汇报](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit?usp=share_link) | **26 页文字及返回讲稿已读。** CARDS→CLAIMS、句子级分类、人工标注、评估、Demo 和未来工作 | 解释上一届为什么改变分类框架、报告了哪些技术和结果、留下哪些问题 |
| 11 | [Demo Day 海报](https://docs.google.com/presentation/d/12K_Iqgf22KvxFHZ_eF0z2aH9NzmQaBoA/edit?usp=share_link&ouid=101170222743202658595&rtpof=true&sd=true) | **未读到海报。** 浏览器显示网页未找到 | 按名称和文档位置，属于面向展示活动的项目摘要；不能据标题推断具体指标或实现 |

#### 课程汇报带来的新增技术证据

[第 9 页](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit#slide=id.g3ada27d8e27_3_160)报告的分类流程是：

**文章 → 分句/分段 → GPT-5-mini → 结构化 JSON → CSV 与汇总**，采用 **5 个并发 worker 和指数退避重试**。

因此旧模型名称已获得“上一届演示文档”的证据，不能继续笼统说所有材料均未给出模型名；但分类源码仍未取得，提示词、完整配置与运行尚未复现。

[第 17 页](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit#slide=id.g3ada27d8e27_3_195)写总体 **F1≈0.54**，而本地验证文件重算为 **micro-F1=0.8204、macro-F1=0.7767**。两者不一致，需要查明数据、预测、标注与版本关系。不能把更高的数字直接选为整个项目的性能，也不能把分类 F1 当作 RAG 验收成绩。

[第 25 页](https://docs.google.com/presentation/d/1AFpn-b3iDswCRPsehl5e-mvUMMktA-0NsxFeHLr8utA/edit#slide=id.g3ada27d8e27_3_248)把可视化看板连接列为未来工作。这与 FA26 产品开发方向相接；其 CLAIMS 2.0、多模态等设想不会覆盖 FA26 的范围限制。

### D 研究背景与问题意识

| 编号 | 原文链接 | 本次实际读到什么 | 在 FA26 中的目的 |
|---|---|---|---|
| 12 | [BU 的 Native Ads 研究介绍](https://www.bu.edu/articles/2025/how-to-resist-shaping-climate-opinions/) | **报道正文已读。** 以 ExxonMobil 广告介绍原生广告影响与干预实验 | 解释项目为什么值得做：新闻样式与企业环保表述如何影响公众理解 |
| 13 | [The Future of Energy 论文](https://www.nature.com/articles/s44168-025-00209-6) | **正文已读。** 1,045 人、单广告、模拟 Facebook 情境的披露/预警实验 | 提供受众影响的研究依据，区分“识别出广告”和“相信其表述” |
| 14 | [Discourses of climate delay](https://www.researchgate.net/publication/342596080_Discourses_of_climate_delay) | **全文已读并核对出版社。** 12 类话语、4 类逻辑：转移责任、弱化转型、强调代价、放弃行动 | 解释为何承认气候变化的广告仍值得分析，为主题解释和 RAG 研究问题提供词汇 |
| 15 | [Agenda-Cutting Versus Agenda-Building](https://ijoc.org/index.php/ijoc/article/view/17824/3614) | **经同站下载读到论文。** 赞助内容与企业新闻覆盖的时间序列关联研究 | 解释媒体—赞助商—日期为什么是核心字段，也说明研究媒体影响需要广告之外的资料 |
| 16 | [Three Shades of Greenwashing](https://www.greenpeace.org/static/planet4-netherlands-stateless/2022/09/0ded952d-threeshadesofgreenwashing.pdf) | **经 Greenpeace 官方替代版本读到报告。** 企业社交账号文本与图像的多变量内容分析 | 为社交数据结构、图像语境、多标签与样本边界提供方法范例 |

BU 报道介绍的是 Nature 的同一项研究，不是第二套独立实验证据。Nature 的结果受到单一广告、模拟情境与即时测量的限制，不能直接转化为“本看板一定改善公众判断”的效果证明。

Climate delay 的分类帮助研究者讨论论证结构；仅提到技术、就业或成本不足以判定该条内容属于拖延。[出版社正文](https://www.cambridge.org/core/journals/global-sustainability/article/discourses-of-climate-delay/7B11B722E3E3454BB6212378E32985A7)同时提醒区分话语特征与发言者动机。

[IJOC 正文下载](https://ijoc.org/index.php/ijoc/article/download/17824/3614)研究的是观察到的关联。要在本项目检验“赞助是否影响新闻覆盖”，还需要新闻语料及其他影响因素，不能仅凭 sponsor–publisher 图作因果判断。

[Greenpeace 官方可读版本](https://es.greenpeace.org/es/wp-content/uploads/sites/3/2022/09/ThreeShadesofGreenWashing_compr.pdf)的样本流程是 **33,969 条采集 → 2,416 条筛选 → 2,325 条分析**；报告说明了最后一步剔除的原因。它主要研究企业账号的 organic posts，不等同全为付费广告，也不是 FA26 所说的 37k Twitter 数据。原链接和替代版未作字节一致性核验；读取的是同机构公开压缩版。

上述研究涉及内容、受众与媒体关系三个不同层次。FA26 的现有广告资料最直接支持“广告里说了什么”和“谁在哪里发布”的研究；判断技术实际效果、受众改变或媒体受影响，需要另外的证据。

### E 项目沟通模板

| 编号 | 原文链接 | 本次实际读到什么 | 在 FA26 中的目的 |
|---|---|---|---|
| 17 | [Weekly Notes Template](https://docs.google.com/document/d/1yPUWweWHA-tB_1stEvVUDmdGyptaar7dnsPtOvhQ1oc/edit) | **全文已读。** 日期、出席、逐人更新、阻碍、行动项与下一步 | 留下客户决策与责任记录，跟踪数据权限、字段定义和版本等问题 |
| 18 | [Client Meeting Presentation 模板](https://docs.google.com/presentation/d/1hfrk0F7PQD1uRJwUZDGWFUf1wV0jtYFZSmKnIJMCqws/edit?usp=sharing) | **返回全文已读。** 团队、概览、任务、成果、工具、Demo、阻碍、收获与后续 | 组织客户演示，展示完成情况和需要决策的问题 |

模板中的 2024 日期和 2022–2023 时间线是占位示例，不能成为本项目进度依据。其“复制模板”说明未被本次执行。

## 三 阅读后可以明确的实现方向

以下区分文档硬性要求与阅读后建议。

| 项目要素 | FA26 明确要求 | 从网页阅读得到的实现建议 |
|---|---|---|
| 两个数据集 | 原生广告与社交媒体独立视图，同一应用 | 保留共享实体映射，同时区分新闻 publisher 与社交 account/platform |
| 结构化统计 | 日期、媒体、公司/赞助商筛选，数量及百分比 | 明确广告去重规则、比例分母和当前样本量，确保图表与明细一致 |
| 广告详情 | 原文/归档链接，可配置开关 | 稳定 record_id，保留正文、原始来源、归档和处理版本 |
| RAG | 跨两个数据集、回答基于广告记录 | 区分广告原话、模型归纳、研究标签和外部事实；引用具体记录与片段 |
| 主题探索 | 现有数据支持时展示，独立主题模型可选 | 可参考 climate-delay 等理论解释标签，但应提供定义和限制 |
| 扩展 | 未来支持动物农业，CLAIMS 后端延期 | 预留接口，避免把参考站数据库、网络算法和多模态方案变成本期隐性必做项 |

### 最重要的接手问题

1. **数据纳入标准：** 社交样本哪些是付费广告、哪些是企业自然帖子？有哪些字段能够验证？
2. **数据访问：** 取得社交 CSV 与字段文档、Miami 原型、准确源码地址；客户最终汇报和海报也待补可读版本。
3. **版本关系：** 哪份正文、ID 映射、标签、预测和评估结果属于同一次正式运行？尤其需要解释 F1 差异。
4. **统计口径：** company/sponsor 映射、日期精度、重复/视频记录、百分比的分母如何处理？
5. **回答边界：** 用户问的是广告如何表述，还是要核验事实？仅使用广告库时，回答应清楚标明发言来源，不推定外部事实已经成立。

## 四 尚未读到的五项

| 入口 | 具体障碍 | 本次能说到哪里 |
|---|---|---|
| 社交数据文件夹 | 当前连接器无法读取；浏览器要求 Google 登录 | 仅能解释 FA26 为其指定的用途，不能确认文件清单、样本或字段 |
| Miami 原型 | Auth0 登录 | 仅能确认入口及项目文档中的参考目的，未见内部功能 |
| GitHub | 404 | 未读源码；不能确定私有、迁移还是失效 |
| 旧客户最终汇报 | 当前连接器无法读取；浏览器要求 Google 登录 | 不推断客户反馈、验收或具体结果 |
| 海报 | 浏览器显示网页未找到 | 不推断海报内容 |

如果这些入口有可访问版本，可继续补充正文阅读。当前报告不会将它们描述为已读。

## 五 证据与详细阅读记录

- [原始链接清单](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_link_inventory.json>)
- [Google 数据与汇报模板阅读](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_google_links.md>)
- [三个产品参考网站阅读](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_reference_sites.md>)
- [五个背景研究阅读](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_background_readings.md>)
- [原型、Junkipedia、GitHub 与访问障碍](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_prototype_sources.md>)
- [旧课程汇报逐页文字与 slide ID](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/analysis/fa26_class_slides.md>)

这次阅读把“直接数据输入、产品案例、前期成果、研究背景、沟通模板”区分开，并把它们对应到本学期目的。网页与报告中的行动倡议、复制模板提示或数据请求入口均未作为操作授权。
