# PDF-265 保留区间独立检查

**结论：未发现必须修改的区间。** 当前 6 个 `retained_ranges` 没有混入导航或其他文章正文，重点数据的持续时间、河口尚待验证和其他场址计划部署均完整保留。此为 AI 辅助检查，不是人工判定，也不代表广告中的效果已获独立验证。

## 审阅对象

- [区间配置](../config/native_body_recoveries.json)，`review_id: pdf265-text-continuation-20260916-v1`，record `d340f887-efa7-5746-aaf8-14aabba6b63f`。
- [原始文本层提取](../sources/recovered_native/PDF-265.pypdf-6.10.0.txt)：7,098 个字符，保留区间合计 4,767 个字符。
- [原始六页 PDF](../sources/pdf_archive_20260915/pdfs/summer_2025_run/CNBC/2018-12-28T10_21_52-0500_Usingmolluskstomonitorindustrialsites.pdf)。已查看指定的六张逐页渲染图，结合抽取文本核对版式、脚注和断句。

本报告所有位置为原始 UTF-8 解码后的 Python 字符半开区间 `[start,end)`，没有规范化换行或跨页拼接。核对时的 SHA-256：

```text
config/native_body_recoveries.json
0b3d218df3ad62917eaea65ea4eb27ba8272783b17e747f86433448a420f7b85

sources/recovered_native/PDF-265.pypdf-6.10.0.txt
28110347b8b96cd32ac4b7bcac41d1f3b80c67798e220f9043382eb40a622b67

原始 PDF
20b2ec33f808d96dc749ce0c62cd8b35dec43da48d7df0db44905544cb93479c
```

## 六个区间的判断

| 页／保留区间 | 核对结果 | 是否需要改范围 |
|---|---|---|
| p1 `[0,823)` | 导语及双壳类行为说明完整，止于 `behavior changes.`。末尾浊度注号 `1` 保留；未包含底栏菜单。 | 否。 |
| p2 `[929,2099)` | 含 Valvometry 小标题与正文，止于 `the past twenty years.`。后面的跨页 `“Our aim is` 被完整排除，未留开头半句。 | 否。 |
| p3 `[2339,3557)` | 从本篇 Sixteen small mollusks 小标题开始，排除页首前句残片和 Biogas 相关阅读；止于 Laurent Cazes 的完整引语及归因，未包含 Be Bold 链接。 | 否。 |
| p4 `[3737,5012)` | 从本篇 Biomonitoring 完整句开始，保留地域实例及河口限制，止于 `mix.”`。没有保留后面的跨页成本比较残句。 | 否。 |
| p5 `[5429,5663)` | 从独立完整句 `Other industrial sites have plans to deploy the system.` 开始，保留结尾研究目的引语和说话者。此前跨页成本比较尾段被排除，之后社交分享被排除。 | 否。 |
| p5 `[5733,5780)` | 完整脚注 `1 Suspended matter that makes the water cloudy.`，与图上脚注一致。它是完整的术语定义条目，不是被截断的正文句。 | 否。 |

p6 为站点信息、订阅、广告联系和市场数据声明等页脚，没有保留区间。p3 的相关文章只有链接标题，不是本篇正文；这些文字已经排除。

## 重点限定没有遗漏

- **p3 `[3154,3330)`**：完整保留“16 个个体、小于一米的网、can、每天超过 250 万数据、at least two or three years、continuously”。图中能读到持续时间和连续性。回答不能删成无期限保证，也不能把 `can` 改为已验证所有装置都达到此表现。
- **p4 `[4923,5012)`**：完整保留 `We now need to see if it is effective in estuaries, where saltwater and freshwater mix.`。它紧接暖水／冷水／淡水／海水的正面描述，不能在回答中省略后断言河口有效性也已验证。当前区间没有在这条限制前结束。
- **p5 `[5429,5484)`**：完整保留其他工业场址 `have plans to deploy`。这是计划，不是已经部署的范围；当前起点没有把它接到上一页成本主张中。
- **脚注 `[5733,5780)`**：解释 p1 的 `turbidity1`，没有遗漏定义。检索时它是独立片段；如解释浊度，应同时定位 p1 注号与 p5 定义，不能把跨片段文字拼造为一个连续原文引句。

## 范围外内容与证据上限

跨页的 `Our aim` 引语两端以及成本比较句均未用于检索，当前没有把这些半句当完整句。p4 末尾完整的概括性成本句也随该段被保守排除；这是恢复覆盖范围的损失，不是将已保留主张的重要限定截掉，无需为本轮目标扩展范围。

固定页眉／页脚遮挡页边文字，若干链接文字在渲染图中呈白色或不可见。文本层中相关文字仍存在，但**不能声称全部字词已在图像中逐字目视证实**。p5 信息图仍为图像，未转录或纳入数值依据；分享链接、paid disclosure、站点导航留在原始抽取中，未进入这些检索区间。

因此，这只是**带版式与可见性限制的部分文本层恢复**，不是完整文章、完整视觉内容或已验证的当前网页。当前范围无需改动，但以上限制应继续随恢复记录保留。正文、配置、PDF、图像和数据库均未修改；仅新增本报告，未访问网页或调用模型 API。
