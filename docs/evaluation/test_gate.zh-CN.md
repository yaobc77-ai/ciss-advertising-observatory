# 免费离线开发门禁

每轮免费工程验证从项目根目录运行同一入口（每次使用新的回执目录）：

```powershell
uv run --no-sync python scripts/run_project_checks.py --report-dir .runtime/project_checks_20261008_round01
```

依赖已安装时可直接使用当前虚拟环境的 Python。入口依次运行根 `tests` 的允许开发收集的完整 pytest、Python Ruff，以及 `src/observatory/assets` 下全部 JavaScript 的 `node --check`。任一步失败或关键回执缺失，门禁返回非零；独立步骤仍全部尝试，不因第一个错误跳过后续检查。

## 实际范围

pytest 通过 `scripts/run_masked_checks.py` 启动，保留现有读取保护，标记表达式固定为 `not integration and not live`。Ruff 检查 `src`、`tests` 和执行器自身，并使用同一份实际受保护测试文件排除清单。执行器只查看测试文件名，不打开被排除文件计算其中有多少用例。

每次运行动态发现 `tests` 下符合 pytest 默认命名的测试模块。`scope.json` 记录候选、允许开发收集及排除的模块数、逐个文件清单、7个直接保护文件名和7个直接保护前缀；个别前缀可能匹配多个文件，所以不能把14条规则写成14个文件。另有9个已观察到的间接依赖旧模块，在单独的 `dependent_legacy_exclusion_rules` 中记录导入路径。`excluded_module_reasons` 对每个排除文件标明 `direct_holdout` 或 `dependent_legacy`；两类分别有数量及实际文件清单。`pytest/collection.json` 另外记录实际收集、按标记排除和最终选择的用例数及模块清单。排除模块中的用例数留空，避免为计数而读取客户题依赖内容。

2026-10-08的 `full_gate01` 与私有集成初次运行在收集阶段观察到8个依赖失败；`full_gate02` 另确认 `test_rag_training.py` 动态加载已确认受保护准备脚本，累计为以下9个间接隔离模块。两次失败回执均保留。只根据拒绝前的导入／读取路径记录，未打开受保护 helper、catalog 或准备脚本正文，也没有将它们视为测试通过。pytest 的收集规则、掩码读取规则与 Ruff 排除使用同一份间接依赖名单。

| 间接隔离模块 | 观察到的受保护依赖 |
| --- | --- |
| `test_claims_research.py` | 导入 `tests/test_research_agent.py` |
| `test_claims_source_search.py` | 导入 `tests/test_research_agent.py` |
| `test_mcp_server.py` | 导入 `test_claims_research.py`，再导入 `tests/test_research_agent.py` |
| `test_rag_training.py` | 通过 `SPEC.loader.exec_module` 加载 `scripts/prepare_rag_training.py` |
| `test_selftest_cases.py` | 导入 `scripts/run_selftest.py`，其加载 `eval/selftest/cases.json` |
| `test_selftest_runner.py` | 导入 `scripts/run_selftest.py`，其加载 `eval/selftest/cases.json` |
| `test_structured_shares.py` | 导入 `tests/test_research_agent.py` |
| `test_user_questions.py` | 收集时加载 `eval/user_questions/cases.json` |
| `test_web_research.py` | 导入 `tests/test_research_agent.py` |

这些旧模块继续保留在评价侧；只有另建新的独立夹具后，新的开发模块才能进入门禁。不得把删除导入保护、复制旧题夹具或增加跳过标记当作完成迁移。

协作审查还确认 `scripts/prepare_statistical_validity.py`、`scripts/prepare_content_review.py` 和 `scripts/prepare_rag_training.py` 是带历史客户材料模板／默认入口的评价准备脚本。它们以精确文件名加入开发读取保护，连同 pyc 缓存拒绝；`protected_exact_source_names` 单独记录，不计入测试模块数量。本轮门禁维护只使用文件名和已确认的依赖元数据，不打开这些脚本正文或 AST。

受保护的核心旧模块没有进入本门禁。允许开发收集的测试通过，不能表述为“整个历史测试库通过”，也不能证明这些核心模块的客户题依赖逻辑全部被测。

新增核心回归应使用全新独立的虚构记录、问题和断言，放在不属于保护名单／前缀的测试模块中，例如 `test_research_core_independent.py`。根 `tests` 会自动收集它，无需维护选定文件白名单。不得复制或重命名旧受保护夹具来绕过保护，也不得使用客户题、参考、改写或逐题输出构造新开发用例。新测试只证明它实际检查的行为，不补算旧模块覆盖率。

## 免费和数据库边界

源码门禁子进程不继承数据库连接、模型密钥、私有审核材料或 `OBS_RELEASE_WHEEL` 的 `OBS_*` 环境变量。入口禁用本机 `.env` 加载、外部 pytest 自动插件和额外 `PYTEST_ADDOPTS`。源码阶段的两项 wheel 检查会明确跳过，随后由 CI 的独立 wheel 阶段运行。

pytest 插件在测试模块收集前拒绝真实 Python socket 连接／地址解析／数据发送，以及常用 psycopg 连接入口，允许测试把连接入口替换成自己的虚构对象。尝试被拒绝也记为门禁失败，不能因测试捕获了异常就隐藏该事件。门禁本身不启动、导入、迁移或停止数据库，也不触发模型评价。

Windows 的 asyncio 内部唤醒通道调用标准库 socketpair，需要一次数值回环连接。插件只在调用预先捕获的原始标准库 socketpair 期间设置 ContextVar，并只允许该上下文内、真实 TCP socket、端口1–65535、数值 `127.0.0.1`／`::1` 对应地址族的 connect；离开调用立即恢复。普通回环连接、DNS、sendto 和外部地址仍拒绝，允许次数写入 `offline_guard.json`。负例只向独立拒绝列表调用同一判断函数，不执行外部连接。实际本机 HTTP 页面检查 `test_actual_http_page_save_and_blind_access` 单项标记 integration，由私有集成阶段运行；其模块其他免费检查继续进入离线门禁。

掩码启动器只给两类离线子进程精确例外：本进程新建、checkout 外系统临时目录内的 Git 构建夹具命令，以及当前 Python 的 `-m observatory.cli --help`。Git 仅允许固定的 init／add／合成 commit／清单和状态参数，禁止 fetch／clone／show／任意配置及 shell；强制禁用 hooks、fsmonitor、签名和网络协议，清除全局 Git 配置与继承密钥／数据库设置。临时本地配置仅接受既有 core 安全字段，include／filter 和对象库 alternates 均拒绝。CLI 仅接受完整的帮助命令，使用当前 checkout 的 src 和禁用 dotenv 的环境。

普通文件先按精确包装后缀快速拒绝工程例外，避免每次 open 都对无关临时文件遍历别名与目录身份。正常 holdout 读取判断仍解析真实路径并执行；只有后缀完全匹配时才进入临时路径、别名、创建登记及文件身份检查，这些权限条件没有改变。

构建测试需要一个名为 `eval/customer_metrics/content_questions.v1.json` 的虚构包装文件。例外仅适用于本进程通过 Python open 包装器在本进程新建临时目录中首次创建的该精确后缀，随后记录文件身份；预存文件、别名、硬链接或替换文件不能取得读取权限。真实 checkout 下的同一路径、所有受保护旧测试名和任何 `24_answer.md` 仍拒绝。`mask_receipt.json` 单独记录这些工程例外的命令和路径。负例用新建的独立策略对象检查拒绝，因此不会把真实拒绝事件从门禁回执删除。以上措施是 Python 工作流控制，不是操作系统沙箱。

## 回执和 CI

回执目录保留 `scope.json`、`summary.json`、各步骤日志，以及 `pytest/junit.xml`、`mask_receipt.json`、`collection.json` 和 `offline_guard.json`。汇总保留失败、错误、跳过和排除；`offline_guard.json` 的 outcome_counts 分开记录 passed、failed、error、skipped、xfailed 和 xpassed。客户准确率及人审准确率留空。回执不能代替真实模型语义评价、人审或客户验收。

运行中的 `pytest/progress.json` 在每项开始及每10项完成时原子更新，记录 UTC、运行阶段、模块名、函数名和已完成数；先去除方括号参数，再提取函数，不保存参数／问题文本。最终阶段写为 finished。该文件只说明进度，不代表检查通过。pytest 固定启用 `faulthandler_timeout=60`，单项超过60秒会输出线程的文件／行号／函数栈；默认不终止测试，也不缩小收集范围。

Windows 读取者未启用删除共享时，进度快照替换可能报 WinError 5／32。仅该替换步骤遇到这两种 PermissionError 时保留旧有效快照、留下待写快照并在下次更新重试，次数写入 `offline_guard.json` 的 `progress_replace_sharing_failure_count`；进度显示允许暂时滞后。其他替换错误、待写文件写入错误以及必需的测试／保护回执错误仍报错。`full_gate04` 的进度替换错误导致 pytest 提前结束，该轮失败及未运行范围保留，不能当作测试完成。

现有 `.github/workflows/ci.yml` 先运行源码门禁，并在成功或失败时上传完整回执，保留30天；源码门禁通过后再构建、安装 wheel，并只运行 `tests/test_release_configuration.py` 的两项资源／实际安装／CLI 检查，另存 JUnit。wheel 阶段传入 `OBS_RELEASE_WHEEL`，源码阶段不传且入口主动清除它。掩码启动器优先载入当前 checkout 的 `src`，不能将这个源码阶段称为已安装 wheel 验证。此文件描述的是配置及本地入口；真正在线 CI 的结果要以之后的运行记录为准。

若需要运行受保护的历史检查，应在开发修改冻结后另建明确的本地评价会话，记录授权、冻结身份、允许读取的评价材料和结果范围；评价结果不得回流为客户题专用规则。该独立会话不属于此自动门禁，当前入口不会解除掩码或自行运行它。
