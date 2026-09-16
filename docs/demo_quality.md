# Research preview 制作与证据记录

日期：2026-09-16。本记录仅说明预览文件的内容与版式检查，不替代项目验收、问答评价或人工金标准。

## 输出

- [7 页英文 PowerPoint](../deliverables/research_preview.pptx)
- [逐页中文演示讲稿](../deliverables/demo_script.zh-CN.md)

封面为 **Research preview / Native corpus connected**。没有将社交数据、GitHub remote 或固定公网域名标为完成。采用现有应用的 ivory / teal 配色。数据图、表格及文字使用原生可编辑对象，未使用示意截图或模拟社交数据。

## 内容依据

| 内容 | 可回查证据 |
|---|---|
| 268 收录、256 可计数、221 可检索、510 块、20 日期未知、20 前缀边界、94 疑似截断 | [数据字典的已核验快照](data_dictionary.md) |
| Python Dash、PostgreSQL / pgvector、免费关键词与 OpenAI 付费问答、引用检查 | [架构](architecture.md) 与 [运行指南](operations.md) |
| ExxonMobil 15 条及 CSV 15 个不同 record_id | 2026-09-16 本机 Edge 验证及当次 `C:/Users/yaobc/Downloads/native-advertising.csv` |
| CCUS 原句与成功生成 | [live_ccs_scoped.json](../outputs/live_ccs_scoped.json) |
| Biogas 原句与成功生成 | [live_biogas.json](../outputs/live_biogas.json) |
| 资料不足状态及空 citations | [live_no_evidence.json](../outputs/live_no_evidence.json) |

幻灯片第 6 页的两条引句直接读取保存 JSON，并在最终 PPTX 中再次做字符串一致性检查。完整 record/version/evidence ID 与来源文件列在幻灯片备注。引句标明为广告表达；三个展示案例不产生准确率估计。制作预览期间没有新调用模型。

## 文件与版式检查

- 使用 bundled `@oai/artifact-tool` 创建及重新导入最终 PPTX。
- 最终 7 页，16:9，字体 Arial。包含 1 个原生图表、3 个原生表格、1 份嵌入的图表数据工作簿。
- 结构检查通过，布局检查 0 finding / 0 warning。图表缓存值与嵌入工作簿对账通过。
- 已逐页查看最终文件的 1280 × 720 渲染。修正了第 4 页表格脚注重叠，并复查所有内容页。最终第 1、3 页与前一版已查看图像字节一致。
- 没有在 Microsoft PowerPoint 桌面应用中打开验证。渲染检查不替代目标应用中的播放与编辑检查。
- 中文讲稿中的本地 Markdown 链接已检查存在。

最终文件 SHA-256：`2ee65d393a63875d272a322a68de545223801f725fd889c1a341206d9ff89a7f`。

私有构建与渲染记录位于 `.tmp/research-preview-20260916/`；最终验证回执为 `validation-v3.json`，最终渲染为 `final-render-v3/`。这些临时产物不作为公众交付文件。

## 演示边界

讲稿中的日期范围及后续关键词检索是可执行演示步骤，不能将未重跑的某个具体范围记录数或目标文章排名当作本次验证结果。真实展示优先读取当前页面，必要时使用明确标注的已保存模型结果。完整问答质量与社交问题依照 [评价协议](evaluation_protocol.md) 继续验收。
