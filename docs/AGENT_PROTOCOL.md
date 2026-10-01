# Claude Code 与 Codex 协作协议

两个代理（Claude Code 和 Codex）在同一个项目上并行工作。本协议保证：任何一方的每项成果，另一方在下一步开始前都能读到；两边不会在不知情的情况下改同一批文件；需要用户决定的事项集中可见。

## 共享日志在哪里

固定位置：`D:/Projects/549 native ads/.coordination/`。可用环境变量 `OBS_COORD_DIR` 改到别处。

- 所有副本、克隆和工作区都写同一个目录，包括 `Documents/Codex/...` 下的副本。
- 该目录不进 git（已列入 `.gitignore`），追加记录不会产生合并冲突。

| 文件 | 内容 |
| --- | --- |
| `events.jsonl` | 只追加的事件日志，是唯一的事实来源 |
| `STATUS.md` | 每次写入后自动生成：待用户决定的事项、有效认领、各代理最近动态、最近 25 条事件。不要手改 |
| `claims.json` | 有效的文件认领（默认 4 小时后过期） |
| `cursors/<agent>.json` | 各代理的已读位置 |

## 每个代理必须做的事

1. **开工前**：运行 `python scripts/agent_sync.py status`，读完对方的未读更新，再运行 `read` 标记为已读。
2. **改文件前**：对要改的路径执行 `claim`。如果对方已认领，返回码为 2：先发 `note` 或 `decision_needed` 协调，不要直接改。改完执行 `release`。
3. **每项成果之后**都要发布一条，包括：
   - `result`：修复、功能、报告完成；
   - `paid_run`：付费模型或嵌入调用，用 `--cost` 写明费用；
   - `data_change`：数据库、索引、备份、导入等变动；
   - `deploy`：Railway 或静态页发布；
   - `decision_needed`：需要用户决定的事，用 `--needs` 写清问题；
   - `blocked`、`handoff`：被卡住，或交给对方接手。
4. **提交和推送会自动记录**（`.githooks/post-commit`、`.githooks/pre-push`）。自动记录只有提交标题；验证结果、费用、未解决的问题仍要另发一条 `result`。推送钩子只能记录**推送尝试**（git 没有推送成功后的钩子），确认推送和部署成功后要另发 `deploy`。钩子写日志失败时不阻止提交，而是记到 `.git/agent-sync-failed.log`，`status` 会提示补记。
5. **只提交自己的文件**：用 `git commit -- <paths>`，不要把对方未提交的改动带进来。
6. **影响对方的共享资源**：本机 PostgreSQL 的启动、停止和升级，Railway，付费预算，`.env`。使用前后都要发布事件。

## 命令示例

```sh
python scripts/agent_sync.py status
python scripts/agent_sync.py read
python scripts/agent_sync.py claim "src/observatory/research_tools.py" --reason "share denominator"
python scripts/agent_sync.py post result "U19 fixed: undated ads count 22" --commit HEAD --files src/observatory/db.py --evidence outputs/user-questions-run-X.json
python scripts/agent_sync.py post paid_run "U06/U19 rerun on d84910c" --cost 0.004
python scripts/agent_sync.py post decision_needed "Keep model-chosen share denominator?" --needs "user: approve or revert b4e4ee4"
python scripts/agent_sync.py release "src/observatory/research_tools.py"
```

同一代理开多个会话时共用一个已读位置；`read` 只把位置推进到本次实际显示过的事件。

代理身份按以下顺序判断：环境变量 `AGENT_NAME`；有 `CLAUDECODE` 时为 `claude`；有以 `CODEX` 开头的环境变量时为 `codex`；否则为 `human`。也可以用 `--agent codex` 指定。

## 新副本或克隆的设置

```sh
git config core.hooksPath .githooks
```

主项目目录不存在时，还要设置 `OBS_COORD_DIR` 指向共享目录。

## 不做什么

日志只记录事实和待办，不代替代码评审，不代替用户批准，也不存放密钥、连接串或付费 API 的原始响应。
