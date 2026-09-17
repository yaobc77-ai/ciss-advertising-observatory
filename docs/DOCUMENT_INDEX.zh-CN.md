# 项目文档阅读索引

更新：2026-09-17。按阅读目的查找文档；不移动、覆盖或删除历史材料。需要按路径或性质排序时，使用[文档清单](document_catalog.csv)。

**当前入口是 0.3.1 的原生广告研究预览。** 主导航为 Query / Data，线框图移到页脚；新增全量交叉表、记录详情、归档状态与词覆盖诊断，436 项非 live 测试通过。556 块句界索引沿用 0.3.0；两次真实 API 连通检查属于上一版，本轮没有付费调用。真实社交、公众部署、指定 GitHub 和独立人工验收仍未完成，具体状态以[本次界面修订](../reports/research_ui_v0_3_1_20260917.zh-CN.md)、[实施与验收状态](acceptance_status.md)及[原文要求核对](../reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md)为准。

文档性质：**当前**用于日常使用或说明现有契约；**证据**只证明记载的版本、运行和检查范围；**历史**保留当时认识，不能覆盖较新实现；**草案**尚未确认或验收。AI 阅读、字符定位、工程测试和人工语义验收是不同证据。

## 一、当前入口

| 想做什么 | 读哪份 | 性质及用途 |
|---|---|---|
| 核对研究界面审查修订 | [0.3.1 研究任务修订](../reports/research_ui_v0_3_1_20260917.zh-CN.md) | **当前本机发布证据**。全量交叉表、标签与年度图、记录详情、归档缺口、词覆盖诊断和英文界面。 |
| 打开并运行项目 | [README](../README.md) | **当前**。启动、停止、安装、测试和主要交付入口。 |
| 看已经完成与尚未完成的部分 | [实施与验收状态](acceptance_status.md) | **当前状态**。按内部模块汇总证据与依赖；M1–M8 是项目组织方式，不是原文条款编号。 |
| 使用网页的筛选、导出和问答 | [用户指南](user_guide.md) | **当前使用说明**。解释统计对象、未知日期、检索范围、来源链接配置及故障提示。 |
| 看上一版索引发布依据 | [0.3.0 句界索引与三页网页](../reports/release_v0_3_0_20260917.zh-CN.md) | **本机发布证据**。索引切换、回退、两次真实 API、费用、366 项测试和浏览器检查；含未通过人工验收的语义问题。 |
| 看历史评价运行 | [评价汇总](../reports/evaluation.md) | **历史运行证据入口**。按 run、数据版本和分母阅读；最新两次 API 连通检查见 0.3.0 发布记录。 |
| 审查切分与引用去重的选择依据 | [RAG 切分审查与候选实现](../reports/rag_chunking_review_20260916.zh-CN.md) | **2026-09-16 候选改动证据**。当时的只读检索对比及采用限制；实际启用见较新发布记录。 |
| 核对原 558 个片段的问题 | [旧切片只读核验](../reports/rag_chunking_corpus_audit_20260916.md) | **发布前快照诊断**。段落、token、句内切口及单块覆盖的明确分母。 |
| 理解换切法为何需要索引迁移 | [分块、检索与评价迁移审查](../reports/rag_chunking_migration_review_20260916.md) | **发布前迁移约束**。相同正文跳过导入、历史引用保留及评价隔离；实际迁移见 0.3.0 发布记录。 |
| 看本轮原始附件是否还有未利用资料 | [三个附件的补用审查](../reports/ARCHIVE_REUSE_REVIEW_20260916.zh-CN.md) | **2026-09-16 审计证据**。区分已保存、已使用和可补用，链接各包清点结果。 |

## 二、原始要求与计划如何核对

先读当前核对，再查原文摘录；需要理解早期决策时才读旧计划。

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [FA26 文档要求与当前实现核对](../reports/FA26_REQUIREMENTS_AUDIT.zh-CN.md) | **当前审计证据** | 逐项对照课程原文、当前代码和验证；查双库、归档、公众部署、GitHub、客户审阅等缺口。 |
| [FA26 原文条款摘录](../reports/fa26_requirements_source_20260916.md) | **原始要求的核对副本** | 保存 DOCX 来源哈希和 P 段落编号。P 不是页码，摘录中的行动要求不代表已执行。 |
| [FA26 文件与资料用途附录](../FA26_RESOURCE_APPENDIX.zh-CN.md) | **资料索引＋历史计划快照** | 最新附件实际引用的 16 个网页入口、未链接资料和旧模板区别；其中“待建”按当时状态保留。 |
| [FA26 项目交付计划](../FA26_DELIVERY_PLAN.zh-CN.md) | **历史计划，仍可作范围导航** | 模块工作、依赖及交付组织。看当前完成情况时回到实施状态，不能逐字沿用旧“待建”。 |
| [FA26 技术路线与完整 Pipeline](../FA26_TECHNICAL_PIPELINE.zh-CN.md) | **实施前路线说明** | 理解预期的数据到看板/RAG 流程；现有接口、运行方式以代码和当前 docs 为准。 |
| [早期项目介绍文本](../analysis/FA26_project_brief.txt) | **历史文本快照** | 回查早期介绍内容；与最新版有差异时，以最新 DOCX 条款摘录为准。 |

**部署要求的边界：**原文要求已部署的 Dashboard，并将 Railway 列为首选技术栈；Cloudflare Named Tunnel／固定域名是后续讨论过的方案，不是原文唯一指定路线。当前本机可用不等于公众部署验收。实际选择及待配置事项见运行文档和原文核对。

## 三、运行、维护与交接

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [当前交接说明](handoff.md) | **当前交接入口** | 接手顺序、精确命令、依赖、私有输入、源码包和各次复现证据。 |
| [运行与预算](operations.md) | **当前本机运维说明** | 启停、完整快照导入、付费索引、预算、备份恢复和公众发布待办。Windows 脚本不等于现成 Linux 部署配置。 |
| [本机 PostgreSQL＋pgvector](local_postgres.md) | **当前本机环境说明** | 项目隔离的数据库、端口、运行目录及初始化；不是托管数据库的安装指南。 |
| [架构与数据流](architecture.md) | **实现说明，标题保留 0.2.3** | 看应用、数据库、导入、检索和来源版本如何关联；较新的具体修复同时查版本报告。 |
| [C 盘迁到 D 盘的记录](../reports/project_migration_20260916.zh-CN.md) | **迁移证据** | 找当前工作目录和迁移检查；旧报告中的 C 盘绝对链接可能只在原环境可用。 |
| [当前快照备份恢复](../reports/backup_restore_v0_2_4.md) | **对应快照的恢复证据** | 查看 275 条当前快照、旧版本引用、账本和表结构的本机恢复核对；不是另一机器或云端灾备验收。 |
| [早期备份恢复](../reports/backup_restore.md) | **历史恢复证据** | 对应早期数据和运行；不能替代较新的当前快照恢复报告。 |
| [故障降级与费用账本检查](../reports/failure_path_checks.md) | **保存的工程证据** | 网络/模型失败、费用预留、降级等测试范围；测试数字只属于该报告记录的运行。 |
| [首版源码包隔离复现](../reports/handoff_validation.md) | **历史交接证据** | 首版包安装、离线测试及当时发现的可携带性缺口。 |
| [0.1.1 v2 包清单与链接核对](../reports/handoff_validation_v2.md) | **历史交接证据** | v2 对首版遗漏的修复；这一轮没有重跑安装和全套测试。 |
| [v3 包清单核对](../reports/handoff_validation_v3.md) | **历史交接证据** | 对该 ZIP 的内容哈希、关键文件和历史链接缺件做有界检查；不是当前包的自动证明。 |
| [早期协作接口约定](implementation_contract.md) | **历史工程约定** | 了解当时的接口与分工。文件中的人员职责不作为现在的任务授权或唯一实现规范。 |

## 四、数据契约、附件与正文质量

### 当前输入与来源证据

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [数据导入契约](data_dictionary.md) | **当前输入说明，标题保留 0.2.3** | 源字段、资格、未知值、历史标签、manifest、正文区间和证据坐标。数据版本变化由后续报告补充。 |
| [Native 数据包复核](../reports/archive_review_native_20260916.md) | **附件核对证据** | 原始 XLSX／清洗表／手标及合并表的内容、字段和差异；不因文件较大或较新就替换主表。 |
| [FA25_SP26 数据包复核](../reports/archive_review_fa25_20260916.md) | **附件核对证据** | 171 个文件的用途和同内容副本；区分模型输出、标注底稿、研究手稿与缺失源码。 |
| [前届原始 DATASETDOC](../sources/FA25_SP26/DATASETDOC-fa25.md) | **历史交接原件，本地配套资料** | 阅读旧字段字典、清理说明和远端代码线索；不把旧数据数量或待办当作当前状态。 |
| [Native Ads 单例 DOCX](<../sources/FA25_SP26/Readings/NATIVE ADS Demo Example.docx>) | **历史单例原件，本地配套资料** | 查阅原始正文和内嵌图片；对应的可检索文本快照见历史研究部分。 |
| [Wells／Amazeen／Weinberg 手稿 DOCX](<../sources/FA25_SP26/Readings/Wells Amazeen Weinberg IJPP Jan 2025_after MA.docx>) | **研究手稿原件，本地配套资料** | 核对采样、人工编码和图表；研究样本与变量不直接等同当前应用。 |
| [PDF 资料包阅读指南](../PDF_ARCHIVE_GUIDE.zh-CN.md) | **历史来源说明，仍可作导航** | 归档结构、媒体样本、代码和质量问题；具体已恢复正文看后续恢复报告。 |
| [309 个 PDF 的来源目录](../PDF_SOURCE_INDEX.zh-CN.md) | **逐件来源索引** | 按 PDF 编号打开存档与来源候选。编号不是广告 ID，标题匹配不是同篇或在线有效证明。 |
| [新增 12 个 URL 审阅](../reports/additional_url_review.md) | **采纳前的 AI 审阅证据** | 7 纳入／4 排除／1 待定的依据；是否已应用看下一项发布报告，不能沿用本报告当时的“未执行”。 |
| [0.2.0 数据修订](../reports/data_revision_v0_2.md) | **历史发布证据** | 新增记录、字段规范化和正文范围采纳；其 d85…／554 块是旧快照。 |

### 正文问题与有限恢复

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [20 个正文前缀边界审阅](../reports/prefix_boundary_review.md) | **AI 工程审阅证据** | 看导航为何不能连同后文全部裁掉，以及最小排除区间；人工判定列仍为空。 |
| [94 项疑似截断预检](../reports/truncation_recovery_preflight.md) | **恢复前的候选证据** | 说明仅凭合并 CSV／JSONL 不能完成全文恢复；后续一篇有限恢复见下面三项。 |
| [PDF-265 同篇身份核对](../reports/pdf265_identity_review.md) | **AI 来源核对证据** | 本地采集清单和跨页内容如何支持同篇身份；不是线上 canonical URL 确认。 |
| [PDF-265 保留区间独立检查](../reports/pdf265_independent_text_review.md) | **AI 区间审阅证据** | 六个保留区间、限定语和正文恢复范围；不是广告效果的外部事实核查。 |
| [PDF-265 有限正文恢复](../reports/pdf265_body_recovery.md) | **0.2.3 发布与定位证据** | 新旧正文版本、PDF／文本哈希、页映射和检索区间；有限续文不能称全文完整。 |

### 实施前审计与归档阅读底稿

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [现有资产质量、输入与输出](../FA26_EXISTING_QUALITY_AND_IO.zh-CN.md) | **实施前历史审计** | 看接手时的 CSV／标签／脚本质量。开头“未找到完整应用”描述当时附件，不代表今天尚无应用。 |
| [数据资产与问题底稿](../analysis/data_audit.md) | **历史只读审计** | 原始工作表、缺失值、行数和字段异常的早期证据。 |
| [历史 pipeline 重建](../analysis/pipeline_existing_review.md) | **历史源码／交接审查** | 区分已读采集代码、仅有文档描述和缺失组件；不是当前 Python 包实现说明。 |
| [数据到检索的早期契约提议](../analysis/pipeline_data_contract.md) | **历史待建方案** | 理解设计取舍；其中“未发现 schema/数据库”是实施前状态，不能当当前结论。 |
| [归档采集代码静态审查](../analysis/pdf_archive/code_review.md) | **历史代码证据** | 三份采集/合并/重试工具的真实作用和断点；未执行代码。 |
| [内层 ZIP 审查](../analysis/pdf_archive/nested_review.md) | **历史归档审计** | 系统附属文件、重复内容和 12 个独有文件的来源。 |
| [秋季 JSONL 内容阅读](../analysis/pdf_archive/fall_content_review.md) | **内容阅读分析（AI 编写）** | 7 文件、45 记录的格式、广告叙述及来源限制；不是新增 45 篇。 |
| [夏季有限样本阅读](../analysis/pdf_archive/summer_content_review.md) | **有限样本分析底稿（AI 编写）** | 明确阅读过的 8 个文本样本及质量；没有声称逐篇精读夏季全部 PDF。 |
| [合并 Notebook 文本](../analysis/pdf_archive/combine_files_source.txt)；[失败筛选 Notebook 文本](../analysis/pdf_archive/process_error_file_source.txt) | **历史代码文本快照** | 便于阅读 Notebook 单元格；文本在此不作为可直接执行的维护脚本。 |
| [逐件 PDF 提取文本目录](../analysis/pdf_archive/text/) | **312 份提取快照** | 309 个外层 PDF＋3 个内层样本；逐件访问交给 PDF 来源目录。提取文本可能漏图、混页或截断，不能覆盖已审核恢复版本。 |

JSON 哈希清单、CSV 对账和原始运行输出由相应审计报告链接，不在本索引重复铺列。PDF 包的本轮全量哈希核对从“三个附件的补用审查”进入。

## 五、评价协议与版本证据

### 先固定评价口径

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [开发评估与验收协议](evaluation_protocol.md) | **当前协议＋验收草案边界** | 20 开发题与 20 验收草案、ready/pending、人工冻结和评分口径；这些题数是项目方案，不是课程原文阈值。 |
| [0.2.5 Dashboard 一致性](../reports/dashboard_consistency_v0_2_5.md) | **当前应用修复证据** | 明细和图表共用一次查询、未知日期处理与相应工程验证；未重跑付费生成。 |
| [0.2.4 引文上下文与干净导入](../reports/quote_context_v0_2_4.md) | **最近付费 RAG／复现证据** | PDF 换行分句、开发集与独立两题 smoke、源码和 wheel 复现；定向 smoke 不替代验收题库。 |
| [0.2.4 AI 内容与引文审阅](../reports/assisted_semantic_review_v0_2_4.md) | **最近 AI 语义意见** | 21 条引用的归因、数量、完整性和聚焦问题；链接人工列全空的逐条 CSV，不提供人工通过率。 |

### 回看修复前后的运行

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [0.2.2 来源归因与数量对象](../reports/claim_contract_v0_2_2.md) | **历史改动／运行证据** | schema/prompt 对来源和数字对象的约束；旧 d85… 数据，不是当前模型重测。 |
| [0.2.2 AI 内容复核](../reports/assisted_semantic_review_v0_2_2.md) | **历史 AI 语义意见** | 广告归因、蓝氢对象、额外背景与必要指代；人工未验收。 |
| [0.2.1 语言修复](../reports/language_guard_v0_2_1.md) | **历史改动／运行证据** | Lingua 语言推断、保守错语拦截及短缩写边界。 |
| [0.2.1 AI 语义复核](../reports/assisted_semantic_review_v0_2_1.md) | **历史 AI 语义意见** | 语言修复后的残留归因和单位对象问题。 |
| [0.2.0 AI 语义复核](../reports/assisted_semantic_review_v0_2.md) | **历史 AI 语义意见** | 保存英语问题输出法语/西语等实际失败；不是当前重跑结果。 |
| [0.1.1 约束与交接修订](../reports/evaluation_v0_1_1.md) | **历史工程／运行证据** | 先选择引用再生成、故障路径和交接修订的早期版本。 |
| [Citation-first AI 审阅](../reports/assisted_semantic_review_citation_first.md) | **历史 AI 语义意见** | 0.1.1 所存 17 条回答单元及当时引用问题。 |
| [上下文检索 AI 审阅](../reports/assisted_semantic_review_context.md) | **历史 AI 语义意见** | 早期上下文检索运行及其待人工判读条目。 |
| [最初开发集 AI 审阅](../reports/assisted_semantic_review.md) | **历史 AI 语义意见** | 早期水处理、蓝氢、引文充分性等失败分析。 |

每份报告内的“本次”“当前”均指它记载的运行；不要相加或择优拼成总体成绩。重新浏览文档不等于重新执行测试，定位正确不等于广告中的事实成立。

## 六、历史研究、产品参考与文本快照

### 接手分析及旧项目方法

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [项目阅读与接手分析](../PROJECT_REVIEW.zh-CN.md) | **2026-09-15 历史综述** | 初始项目目标、旧方法、数据问题和链接状态；“源码未取得”指当时旧仓库和附件范围。 |
| [FA25/SP26 方法与验证审查](../analysis/prior_methods_review.md) | **历史方法审计** | 旧标签粒度、指标版本及可复现限制；句子分类成绩不能替代 RAG 成绩。 |
| [旧课程汇报逐页文本](../analysis/fa26_class_slides.md)；[汇报文本快照](../analysis/fa26_class_final_text.txt) | **历史演示文本** | 了解 CARDS/CLAIMS、旧模型与指标；不是当前项目演示或已验证源码。 |
| [Native Ads 单例说明文本](<../analysis/NATIVE ADS Demo Example.txt>) | **历史单例快照** | 一篇 CCS 广告的 CARDS/CLAIMS 解释，非完整标签规范或准确率证明。 |
| [Wells／Amazeen／Weinberg 手稿文本](<../analysis/Wells Amazeen Weinberg IJPP Jan 2025_after MA.txt>) | **研究手稿提取快照** | 采样、原生广告身份与人工内容编码；其样本和变量不是当前 12 标签的正式规范。 |

### 外部页面和研究背景的已有阅读

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [旧版 18 个链接的用途说明](../FA26_LINKS_AND_PURPOSE.zh-CN.md) | **历史访问记录** | 旧版介绍含两个沟通模板；最新版是 16 个网页入口，见资料附录。成功/受限状态只对应当时访问。 |
| [Google 资料逐项核读](../analysis/fa26_google_links.md) | **历史访问证据** | 当时实际读到的文件、目录与受限入口；404/登录页不能当成空目录。 |
| [Miami 原型／Junkipedia／旧仓库核读](../analysis/fa26_prototype_sources.md) | **历史产品／来源阅读** | 区分原型限制、单帖示例和未取得源码；不推定线上状态今天未变。 |
| [三个参考网站阅读](../analysis/fa26_reference_sites.md) | **历史产品研究** | How Do They Lobby?、The Big Green Machine、Big Ag Network 的用途与机制；参考设计不是新增课程要求。 |
| [五项背景阅读](../analysis/fa26_background_readings.md) | **历史研究分析** | 研究问题、方法与限制；不把每条广告自动认定为误导，也不证明看板社会效果。 |
| [BU 研究介绍 HTML](../analysis/fa26_web_sources/bu.html) | **网页快照** | 对应研究介绍的保存内容；不是现时网页或独立实验。 |
| [Nature 论文文本](../analysis/fa26_web_sources/nature.txt)；[HTML 快照](../analysis/fa26_web_sources/nature.html) | **同一来源的两种快照** | 查论文具体方法和结论；两份文件不算两个独立来源。 |
| [Greenpeace 报告提取文本](../analysis/fa26_web_sources/greenpeace_compressed.txt) | **报告文本快照** | 社交采样、文本/图像及标签口径；提取文本不代替图表和排版核对。 |
| [旧会议演示模板文本](../analysis/fa26_meeting_deck_text.txt)；[旧周会记录模板文本](../analysis/fa26_notes_template_text.txt) | **旧版模板快照** | 可参考沟通组织；两模板已从最新版介绍删除，模板内复制/日期指示不是当前任务。 |

### 从经验提炼维护方法

| 文档 | 性质 | 用途和阅读边界 |
|---|---|---|
| [RAG 经验提炼与当前待办](../reports/rag_skill_adoption_and_open_issues.zh-CN.md) | **方法总结＋待办记录** | 看数据难点、归因、检索和评估如何处理；外部截图经验不等于本项目已复现故障。 |
| [RAG skill 前向检查](../reports/rag_skill_forward_review.md) | **合成场景行为检查** | 三个模拟请求下的边界与处理方式；不是检索质量、RAG 准确率或通用效果证明。 |

## 七、演示与交付材料

| 文档或文件 | 性质 | 用途和阅读边界 |
|---|---|---|
| [最初研究预览制作记录](demo_quality.md) | **历史制作／视觉检查证据** | 对应第一版英文预览的内容与版式；不代表项目已验收。 |
| [第一版研究预览 PPTX](../deliverables/research_preview.pptx)；[中文讲稿](../deliverables/demo_script.zh-CN.md) | **历史 research preview** | 演示早期已接入 Native 的功能和 smoke；保留原快照，不引用为当前统计。 |
| [0.2.2 研究预览 PPTX](../deliverables/research_preview_v0_2_2.pptx)；[中文讲稿](../deliverables/demo_script_v0_2_2.zh-CN.md) | **历史 research preview** | 对应 0.2.2 的 554 块快照；当前为 556 块。不是双数据集、公众环境或最终客户验收演示。 |

源码 ZIP、wheel、哈希清单和复现命令从“当前交接说明”进入，避免把每个旧包混列成最新版。打包完整性与指定 GitHub 提交、云端运行、客户接受分别核对。

## 覆盖范围与链接说明

- 本索引逐项覆盖编制时根目录、`docs/`、`reports/` 的 Markdown 说明；自身作为导航入口，不重复列为一条资料。
- `analysis/` 中 25 份非逐件 PDF 的 Markdown／TXT／HTML 按主题列出；312 份逐 PDF 文本按目录和既有 PDF 来源索引覆盖。
- JSON、CSV 运行日志与逐条证据表由所属报告引导；可排序文档清单用于核对文件覆盖，不把原始日志堆进主阅读路径。
- 索引内部均用仓库相对链接。`analysis/`、原始 `sources/`、部分输出及演示材料可能不随指定源码包或 Git 提交分发；需要配套本地资料才能打开。链接存在不表示原报告里的外部网址仍可访问。
- 文档编目本身只核对文件、用途和链接；本轮实际代码发布、模型调用与工程检查另见 0.3.0 发布记录。旧报告自身的版本和结论保留。
