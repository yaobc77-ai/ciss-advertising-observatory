# 网页审美元素与第二轮简化

> 后续按用户指定的 INDRA 外形继续调整；当前实现与验证见 [INDRA 外形参考](UI_INDRA_REFERENCE_20260925.zh-CN.md)。本文保留为第二轮设计记录。

按“更干净、简洁”的反馈，替代同日第一轮偏出版物风格的界面。改动已在本机运行，尚未发布到 Railway。

## 参考原则与本项目的取舍

| 要素 | 参考依据 | 本次采用 |
|---|---|---|
| 视觉层级 | [NN/g：Visual hierarchy](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/)：按信息的重要性组织注意力，优先用空间分组 | 一个页标题；查询区直接进入输入框，移除重复标题、徽章和标语 |
| 内容密度 | [NN/g：Aesthetic and minimalist design](https://www.nngroup.com/articles/aesthetic-minimalist-design/)：减少与任务无关的信息，同时保留完成任务所需内容 | 删除三步教程、装饰编号；保留筛选范围、费用、日期缺失、标签局限和证据来源 |
| 按需展开 | [GOV.UK：Details](https://design-system.service.gov.uk/components/details/)：把只对部分用户有用的补充解释放入可展开区域 | 较长的筛选解释放入 About these filters；原有技术详情继续折叠 |
| 字体与交互一致性 | [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)：清楚的标签、可见焦点、数字对齐、长内容处理 | 统一系统无衬线字体；标题依字号和字重区分；保留输入边框、焦点样式和等宽数字 |
| 简单布局 | [USWDS：Accessibility](https://designsystem.digital.gov/documentation/accessibility/)：可读对比度、简单布局、响应式与键盘操作 | 白底、少量强调色、细分隔线；缩小页头，增加表单和数据的可用空间 |

具体字号、间距和颜色是本项目的设计选择，以上来源并不规定本项目必须使用这些数值。没有引入新 UI 框架、字体服务或他站品牌资产。

## 已落实的位置

- `src/observatory/app.py:845`：筛选长说明改为原生 details/summary，支持键盘展开。
- `src/observatory/app.py:926`：图表保留标题、单位与说明，去掉无业务含义的编号。
- `src/observatory/app.py:1210`：单列页头，去掉右侧标语与重复介绍。
- `src/observatory/app.py:1335`：查询空状态改为一句话，保留结果容器、加载提示与 live region。
- `src/observatory/assets/observatory.css:17`：字体统一，标题层级简化。
- `src/observatory/assets/observatory.css:77`：统计数字去掉卡片外框和粗顶线。
- `src/observatory/assets/observatory.css:116`：查询区去掉外框与内层重复布局。
- `src/observatory/assets/observatory.css:133`：证据卡用分隔线组织，继续呈现标题、日期、匹配词、引文和来源链接。
- `src/observatory/record_view.py`：同步去掉装饰标记与重复小标题，保留元数据、正文、档案状态和附件。

## 验证

- 相关既有回归测试：**76 passed in 20.36s**。
- 修改的 Python 文件通过 Ruff；diff 空白检查通过。
- 浏览器核对 Query、Data 和免费关键词查询：`carbon capture` 返回 5 条证据，付费 API 未调用。
- Data 保留 263 条选中记录、226 条可检索记录、22 条缺日期统计。
- 390px 窄屏下，两页未发生页面级横向溢出，查询框与图表保持容器内布局。检查后恢复默认尺寸。
- 这次是视觉与内容层级调整，未改变检索算法、生成策略、过滤条件和数据口径，也不代表已完成全部可访问性或客户验收。

## 预览

- [Query](http://127.0.0.1:8050/query)
- [Data](http://127.0.0.1:8050/data)

维护时优先保留：一个主要标题、明确的输入标签、一个主要按钮、靠近数据的必要说明。新增标签、徽章或面板前，先确认它是否帮助用户理解数据或完成操作。
