# PDF-265 同篇身份核验

结论：建议将该候选视为“本地采集清单与跨页内容交叉确认的同篇材料”，可支持有限、带来源定位的续文恢复。它不是线上 canonical URL 核验，也不是完整正文恢复证明。

目标：https://www.cnbc.com/advertorial/2018/12/28/using-mollusks-to-monitor-industrial-sites.html；record_id `d340f887-efa7-5746-aaf8-14aabba6b63f`。

## 已直接复核的证据

1. 直接读取现存原嵌套 ZIP：final_dataset.csv 逻辑行62及 final_dataset-original.csv 行81均为目标完整 URL。标题、publisher、日期字符串 2018-12-28T10:21:52-0500 一致，两份提取后的本地 CSV 与 ZIP 条目字节相同。
2. 依据同包脚本的 publisher/date/去空格标题规则，这两行各唯一生成原 ZIP PDF 条目 `native-ads-download/pdfs/CNBC/2018-12-28T10:21:52-0500_Usingmolluskstomonitorindustrialsites.pdf`。直接重算该 PDF 条目 SHA-256，与当前 PDF-265 相同：`20b2ec33f808d96dc749ce0c62cd8b35dec43da48d7df0db44905544cb93479c`。
3. 原清单正文 3000 字符，基准正文2998字符；唯一差异是原清单在字符2050处含导航项目符号“• ”，没有正文内容冲突。不要把这个长度差说成新增续文。
4. 四处独特原文锚点跨 PDF 第1–3页，对应开头、CNRS/Arcachon/Bordeaux、传感器小型化、十六只贝类及250万数据。只允许布局空白差异即可匹配；每个锚点在268基准记录中只命中目标记录，具体原字符位置见 JSON。
5. 最后一个锚点与已有CSV截点一致，PDF随后接 daily over long periods 等内容。同一人物、方法和截点续接提供的证据强于标题相似。

## 没有得到的证据

- CNBC 原网页读取受到 restricted/robots 限制；未取得官方正文。两次定向搜索没有获得可用目标页/公开归档链接，不能据此断言不存在归档。
- archive.org availability 请求被工具 safe-open 拒绝，没有得到归档服务器的可用性回复。
- 当前下载脚本读 remaining_files.csv，本条不在该表；两个 notebook 没有目标 URL/文件名的运行日志。因此文件命名规则吻合不是本次成功抓取日志。
- 本轮没有重复 PDF 注释扫描。完整自身 URI 缺失的既有检查保留，但不能仅因 URI 缺失否定上述本地内容链。

## 恢复范围

根代理的逐页视觉审阅发现导航遮挡、白字链接及未抽取的信息图；这些发现不是本子任务重新看图所得。线上正文获取失败，因此本轮不能补这些缺口。建议只恢复已审阅的可见同篇续文，保留 partial/visual_omissions，不作“完整文章”或“全文没有某论点”的声明。

原URL关联可以基于本地采集与内容审核加强，但原始来源、PDF、旧基准正文、原始文本抽取和页面缺陷都要保留。新正文/检索版本由根任务另行决定；本轮未改数据库、配置或原材料。

结构化证据：[pdf265_identity_review.json](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/reports/pdf265_identity_review.json>)。

## 根任务的新抽取文本关联

只读核对 [PDF-265.pypdf-6.10.0.txt](<C:/Users/yaobc/Documents/ChatGPT/549 native ads/sources/recovered_native/PDF-265.pypdf-6.10.0.txt>)：7,098 字符，SHA-256 `28110347b8b96cd32ac4b7bcac41d1f3b80c67798e220f9043382eb40a622b67`。四个身份锚点也在该抽取中匹配，具体位置已加入 JSON。新抽取全文仍不是“完整可见正文”的证明；根任务拟仅发布已核对的 partial 续文，不拼接跨页半句、不从本次抽取缺失的信息图补造数字。
