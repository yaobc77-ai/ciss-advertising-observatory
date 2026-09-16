# 源码交接 ZIP 的隔离复现检查

检查日期：2026-09-16。

**结论：所检查源码包可以在新的项目虚拟环境中安装锁定依赖，离线测试 74 passed / 9 deselected，CLI 帮助正常。发现 2 类资料可携带性缺口，已通知主任务修复。** 这项检查没有安装第二个 PostgreSQL、连接主库、运行集成测试或调用模型，也不代表另一台全新 Windows 的完整验收。

## 1. 精确检查对象

| 项目 | 记录 |
|---|---|
| 源码包 | `deliverables/observatory-research-preview-20260916.zip` |
| 包 SHA-256 | `eda956bd644f466f2c71ba1b936cfece9c8448e60f9b89780e9a7f24553895ab` |
| 包大小 | 659,006 bytes |
| ZIP 条目 | 80，包含 `CONTENTS.sha256` |
| manifest 覆盖 | 79 / 79 个载荷条目，逐个 SHA-256 一致 |
| 独立解压目录 | `.runtime/handoff-check/source-20260916-e2cef2b08d/` |
| 检查解释器 | CPython 3.12.14，已有 bundled Python |
| uv | 0.12.7 |

解压前检查了重复条目、绝对路径、`..` 路径逃逸及最终解压路径，所有目标均位于新的检查目录。manifest 不包含自身哈希，其余载荷无缺失、无多余、无哈希差异。结论只绑定上述包哈希，后来重建的 ZIP 需另核清单。

## 2. 安装与离线执行证据

在解压目录运行：

```powershell
$env:UV_PROJECT_ENVIRONMENT='C:\Users\yaobc\Documents\ChatGPT\549 native ads\.runtime\handoff-check\source-20260916-e2cef2b08d\.venv'
$env:UV_PYTHON_DOWNLOADS='never'
uv sync --frozen --extra test --python 'C:\Users\yaobc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

命令退出 0，构建该解压源码并安装 65 个锁定包。锁文件 SHA-256 为 `c4b34f6aeec8a6f2edc6d5c7528f91236370190b82614a38021fd53e805f51d3`，没有为通过安装修改锁文件。使用了本机已有解释器和可用依赖缓存，不证明冷缓存下载或另一台机器安装已经完成。

离线测试使用解压目录的 `.venv`，执行等价于：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not integration and not live"
.\.venv\Scripts\python.exe -m observatory.cli --help
.\.venv\Scripts\python.exe -m observatory.evaluate --help
```

实际测试另加隔离保护：在测试进程内禁用 dotenv 自动读取、把数据库连接和 API 凭据设为无效占位，并阻断 Python socket 连接，防止检查目录位于原工作区下时读取父级配置或意外联网。没有输出真实连接值或密钥。

| 验证 | 结果 |
|---|---|
| 非 integration / 非 live 测试 | **74 passed, 9 deselected in 10.50s** |
| `observatory.cli --help` | 退出 0，列出当前管理子命令 |
| `observatory.evaluate --help` | 退出 0，显示 `--cases`、`--paid`、`--expected-data-version` |
| schema 与 UI 资源 | `schema.sql`、CSS、JS 均随包存在；应用资源测试通过 |
| 启停与测试库脚本 | Start/Stop/Test-Observatory、PostgreSQL 管理及 Setup-TestDatabase 脚本均存在 |

`evaluate --help` 首次导入 pySBD 0.3.4 时出现依赖内部的 Python `SyntaxWarning`，涉及正则字符串转义；命令仍正常退出。本次没有将其认定为功能失败，也没有修改依赖。

## 3. 数据和评估依赖是否齐全

- `eval/development.jsonl`：20 题，13 ready / 7 pending_social。
- `eval/acceptance.draft.jsonl`：20 题，13 ready / 7 pending_social。
- 当前付费开发运行、此前开发运行、两轮复核 CSV、评估报告和研究预览在包内。
- 草案不是已冻结验收集；本次只核对文件与结构，没有执行草案检索、生成或数据库验证。
- 包内没有完整 `sources/`、`analysis/`、数据库、凭据或 `.venv`。选定运行 JSON 和导入报告含广告原文片段/候选资料，不是可以还原完整基线语料的数据库备份。

README 第 32、86 行明确说明新机器需要另行提供数据字典列出的私有来源。数据字典第 7–13 行列出基线 CSV、原始 XLSX、候选合并表、可选历史标签与来源索引。只拿源码 ZIP 执行 `import-native` 而未补齐所需基线文件会失败，这是已声明的输入前提，不应把随包评估 JSON 当作完整原生数据集导入。

## 4. 已发现的具体缺口

以下行号和路径均指**本次 ZIP 解压内容**，不冒称后来工作区修改已经进入旧包。

### A. 演示拒答结果未随包

- `deliverables/demo_script.zh-CN.md:11` 和 `:133` 引用 `../outputs/live_no_evidence.json`。
- `docs/demo_quality.md:21` 同样引用该文件。
- ZIP 只纳入了 `live_biogas.json` 和 `live_ccs_scoped.json`，缺少拒答结果。因此脱离原工作区后，演示脚本的第三个备用案例无法打开。
- 建议：把 `live_no_evidence.json` 加入显式允许清单并重建新版本，或将对应文档明确标为包外材料。已即时通知主任务。

### B. 已随包文件仍有原电脑绝对链接

- Markdown 中有 **16 个**绝对链接指向实际已经随包的目标；在不同用户名或目录中不会自动指向解压文件。
- 当前审阅的具体例子为 `reports/assisted_semantic_review_context.md:13`（复核 CSV）、`:56`（当前运行 JSON）、`:57`（development 题库）。旧轮审阅也有同类 3 处。
- 另有 **449 个**绝对工作区链接指向未随包的原始来源或历史审计。这类包外依赖已在交接说明中声明，应保留来源边界，不能通过制造空文件使链接“通过”。此外有 6 个工作区以外的绝对附件链接，总绝对链接数为 471。
- 建议：仅将“目标确实在包内”的绝对链接改为相对路径，或在打包时按允许清单转换；保留包外来源的明确说明。已即时通知主任务。

相对 Markdown 链接检查为 94 处，缺失 3 处，均指向同一个 `live_no_evidence.json`。上述文档缺口不阻止锁定安装及离线测试，但会影响另一实施者按讲稿复核保存证据。

## 5. 证据边界与下一步

本次证明的是指定源码 ZIP 的文件完整性、隔离依赖安装、离线工程测试和 CLI 导入路径。没有在新机器从零创建 PostgreSQL、导入完整原生数据、运行社交数据、进行付费问答、访问公网或执行人工语义验收。

主任务修复资料清单后应重建一个新文件名的 ZIP，并核对新 manifest、演示 JSON 及包内相对链接。若仅修改文档和允许清单，无需把本次 74 项测试当作新模型或数据库验收，也无需自动重复付费评估。
