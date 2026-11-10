# Observatory 界面更新 — 2026-09-25

> 本文记录第一轮样式。用户随后要求更干净简洁，当前实现见 [第二轮简化](UI_SIMPLIFICATION_20260925.zh-CN.md)。下文的衬线标题、图表编号和三步引导不再是当前样式。

## 设计参考

- [How Do They Lobby?](https://howdotheylobby.org/)：已读首页和[搜索页](https://howdotheylobby.org/search/positions)的 HTML/CSS。借鉴衬线标题、克制的青绿色、任务导航、从搜索到来源详情的层级。
- [INDRA](https://indra.stanford.edu/)：页面 HTTP 200；读取了页面元信息与 CSS，正文为客户端渲染。本次仅将其浅色与蓝色体系作为参考，没有声称完成全部交互评审。
- [Our World in Data](https://ourworldindata.org/grapher/annual-co2-emissions-per-country)：借鉴图表附近的说明、数据口径和来源信息组织。未复制其代码、机构标志或品牌资产。

## 本次实现

- 深蓝、暖白、青绿的统一配色；Georgia 页标题、Segoe UI/Arial 控件与正文，使用系统字体，无新增字体服务或前端依赖。
- Query / Data 保持两个主入口；线框图仍在页脚。
- 页头加入 Research preview 状态说明；筛选区域减轻边框，数据区保留明确视觉边界。
- 三个统计数增加含义说明，数字使用一致的版式。
- 图表增加编号、统一标题和坐标样式；媒体与赞助方横条图直接显示数字或百分比；热图保留全部单元格数字和图例。
- 查询页完善输入与操作层级，初始状态给出三步使用说明；证据卡使用更适合阅读的引文排版，技术信息继续折叠。
- 记录详情增加面包屑与媒体、赞助方、日期分组；来源、附件和正文保持原有信息完整。
- CSS 按区域整理，保留窄屏适配、键盘焦点、减少动画偏好与表格内滚动。

## 验证

- `python -m pytest tests/test_app.py tests/test_research_ui.py tests/test_analytics.py -q`：**76 passed in 21.54s**。
- 修改的 Python 文件 Ruff 检查通过，`git diff --check` 通过。
- 浏览器读取真实本地库：默认选择 263 条，226 条可检索，22 条缺日期。
- 手动选择 CNBC 后：116 条、103 条可检索、19 条缺日期；清除筛选后恢复全量选择。
- 免费关键词查询 `carbon capture and storage biogas`：5 条证据；保留 biogas 在当前选择中有 3 篇、未进入当前返回片段的提示；未调用付费生成。
- 社交数据空状态：只有说明，筛选和空图表保持隐藏。
- 390px 窄屏检查：Query、Data 均未出现页面级横向溢出；图表保持容器内布局，热图/数据表允许内部滚动。恢复正常浏览器尺寸。
- 打开真实文章详情确认新标题、元数据和来源区；现有测试覆盖了正文转义与 PDF 节点。

本次为界面更新，未重新导入数据、重算向量或修改检索/生成算法。验证范围不等于完整用户验收或真实付费模型测试。

## 预览与发布状态

- 本机：[Data](http://127.0.0.1:8050/data)、[Query](http://127.0.0.1:8050/query)。已启动项目运行服务。
- 本次未提交、推送或部署 Railway；线上地址仍需按现有发布流程更新。
- 主要修改：`src/observatory/app.py`、`src/observatory/assets/observatory.css`、`src/observatory/record_view.py`。
