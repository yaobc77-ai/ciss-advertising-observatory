# 在 Claude 桌面版中继续这个项目

2026-10-25 整理。适用于 Claude 桌面版的 Code 功能（与命令行版 Claude Code 是同一引擎）。本文只写公开仓库里可以写的内容；本机的端口、分支状态和待决定事项写在 `CLAUDE.local.md`（不进 git）。

## 1. 桌面版会自动读到什么

| 内容 | 位置 | 桌面版是否读取 |
|---|---|---|
| 项目规则 | `CLAUDE.md`，它导入 `AGENTS.md` | 读取。注意：存在 `CLAUDE.md` 时，Claude 不会单独读取 `AGENTS.md`，所以必须保留 `@AGENTS.md` 这一行 |
| 本机说明 | `CLAUDE.local.md` | 读取，与 `CLAUDE.md` 一起加载 |
| 用户级说明 | `~/.claude/CLAUDE.md` | 读取，所有项目都会加载 |
| 设置、权限、钩子 | `~/.claude/settings.json`、`~/.claude.json` | 与命令行版共用 |
| 技能 | `~/.claude/skills/`，以及账户同步的技能 | 读取 |
| 自动记忆 | `~/.claude/projects/<项目>/memory/` | 按 git 仓库区分。这个项目对应 `D--Projects-549-native-ads` |

来源：<https://code.claude.com/docs/en/desktop.md>、<https://code.claude.com/docs/en/memory.md>、<https://code.claude.com/docs/en/settings.md>。

**之前的记忆为什么要迁移**：之前的 Claude 会话是在 `C:\Users\yaobc` 下启动的，记忆存在那个目录对应的位置。桌面版打开本项目文件夹时，读的是本项目自己的记忆目录，不会自动带上旧的记忆。2026-10-25 已把和本项目有关的记忆整理进本项目的记忆目录。

## 2. 第一次在桌面版打开时

1. 在桌面版的 Code 中选择文件夹 `D:\Projects\549 native ads`。是否开启"隔离工作区（worktree）"：日常修改可以不开；整合别人的改动、准备上传时按 `AGENTS.md` 的 Git 规则开启。
2. 第一次加载 `@AGENTS.md` 时，如果提示是否允许导入，选择允许。
3. 先让 Claude 运行：
   ```
   python scripts/agent_sync.py --agent claude status
   python scripts/agent_sync.py --agent claude read
   ```
4. 检查是否加载完整：让 Claude 用一句话说出"回复语言、提交前是否要问、付费调用规则、当前分支"。答不全，说明 `CLAUDE.md` 或记忆没有读到。
5. 本机重启过的话，先启动数据库：`.\scripts\Start-Postgres.ps1`。

## 3. 环境

- 桌面版不读取 PowerShell 的 profile，需要的工具必须在用户或系统的 PATH 里。2026-10-25 已确认：git、gh、uv、python、codex 都在 PATH 中；node、psql、railway 命令行工具没有安装。
- Python 一律用 `.venv/Scripts/python -X utf8`。
- 需要环境变量时，写进桌面版的"本地环境"设置，或写进 `~/.claude/settings.json` 的 `env`。不要把密钥写进仓库里的任何文件。

## 4. 继续旧会话

- 桌面版里输入 `/resume`，可以列出本机命令行版启动过的会话。旧会话的工作目录是 `C:\Users\yaobc`，要在那个文件夹下才能看到。
- 继续前，先关掉命令行里同一个会话，避免两边同时写同一份记录。
- 更推荐在项目文件夹里开新会话：规则和记忆都已经整理好，不依赖旧会话的上下文。

## 5. 和 Codex 并行

不变：两边共用 `.coordination/` 日志和 `scripts/agent_sync.py`。改文件前认领，做完释放，结果用 `post` 记录。

## 6. 在 claude.ai（网页或桌面聊天）中使用

聊天版不读取本机文件和 Claude Code 的记忆。可以这样做：

- **记忆**：设置 → Your Claude（旧版为 Memory）→ Start import，粘贴整理好的偏好文本。这个功能标注为实验性，没有从 Claude Code 导入的官方途径。
- **Projects**：新建一个项目，把项目简介放进"项目指令"，把公开文档放进"项目知识"。客户私有题目、`config/private/`、`.env` 一律不要上传。

来源：<https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory>、<https://support.claude.com/en/articles/9517075-what-are-projects>。
