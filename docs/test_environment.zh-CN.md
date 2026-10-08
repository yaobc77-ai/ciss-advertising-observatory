# 私有 PostgreSQL 测试环境

当前集成测试夹具要求显式提供 `OBS_TEST_DATABASE_URL`，目标须为数字回环地址、`obs_test*` 数据库，以及不同于主集群 55432 的端口。旧 `setup-test-db` 曾在主集群创建 `obs_test`，与这条隔离规则冲突。2026-10-08 起，兼容入口委托独立测试集群管理器。

测试集群复用工作区已安装的 PostgreSQL 18 / pgvector 二进制，在 `.runtime/private_test_postgres/<名称>/` 创建独立数据目录、随机凭据、标记、日志、连接文件及操作回执。默认名称为 `default`；首次从系统分配的空闲端口选取，拒绝 5432、55432 和进程环境中 `OBS_DATABASE_URL` 明示的主端口。后续启动沿用标记端口；端口冲突时报错，保留数据，不停止占用进程。检查与启动之间存在短暂端口竞争窗口，启动失败时保留日志供检查。

## PowerShell 操作

在项目根目录执行。命令直接使用 Python，支持 Windows PowerShell 5；无需改变脚本执行策略。

```powershell
# 首次初始化、启动、创建 obs_test、启用 vector；重跑保留已有数据。
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py setup

# 兼容旧 setup 入口，创建的是同一个独立 default 测试集群。
.\.venv\Scripts\python.exe -X utf8 scripts/local_postgres.py setup-test-db

# 核验独立实例及两条全新合成临时记录；临时表连接关闭后消失。
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py health

# 设置当前进程的测试连接，不把口令打印到终端。
$taskTestEnv = Join-Path $PWD '.runtime\private_test_postgres\default\test.env'
$taskTestLine = Get-Content -LiteralPath $taskTestEnv | Where-Object { $_.StartsWith('OBS_TEST_DATABASE_URL=') }
$env:OBS_TEST_DATABASE_URL = $taskTestLine.Substring('OBS_TEST_DATABASE_URL='.Length)

# 只收集这个新合成安全检查模块。其他开发模块须显式指定安全路径。
.\.venv\Scripts\python.exe -X utf8 scripts/run_masked_checks.py --report-dir '.runtime\private_test_checks_fresh01' -- tests/test_private_test_postgres.py -q

# 查看状态；停止前先结束使用这个测试实例的读写者。
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py status
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py stop
Remove-Item Env:\OBS_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

`--report-dir` 每次使用一个新目录。掩码启动器拒绝测试内的子进程，所以上述安全单元检查模拟进程和连接；实际 `setup/health/stop` 单独调用，只使用管理器自己的目录和全新合成记录。不要把客户题目、参考或逐题输出放入开发材料。

多个并行任务使用各自名称，例如：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py setup --cluster fresh_probe
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py health --cluster fresh_probe
.\.venv\Scripts\python.exe -X utf8 scripts/private_test_postgres.py stop --cluster fresh_probe
```

对应连接文件在 `.runtime/private_test_postgres/fresh_probe/test.env`。名称仅允许小写字母开头及小写字母、数字、下划线，不接受文件路径。

## 所属边界与保留

管理器仅连 `postgres` 和自己独立实例的 `obs_test`；应用角色没有超级用户、CREATEDB、CREATEROLE 或 REPLICATION 权限。初始化遇到无标记非空目录、错误大版本、目录链接或错误所属标记时拒绝覆盖。运行配置只允许 IPv4 回环和 SCRAM 密码认证。

停止前核对私有标记、真实服务器数据目录、监听地址、端口、管理角色，以及 PID 文件所指进程的可执行文件和 `-D` 数据路径；身份不一致就拒绝。仅向通过检查的私有数据目录调用 `pg_ctl stop`，不执行按端口杀进程，不删除数据。临时库、日志和回执停止后保留。

新入口不读取或改写项目 `.env`、主凭据、主数据目录；旧 `.env` 中的测试 URL 可能仍指向 55432，测试前应按上述命令显式装载私有连接。`docs/local_postgres.md` 的早期主集群测试库说明属于历史路径，本页说明当前开发入口。主集群的 start/stop/backup/restore 操作继续由原管理脚本负责。

这些检查验证测试环境隔离与基础 SQL/vector 操作；不证明真实模型效果、语义准确率或客户验收。
