# Instructions for Claude Code

This project is worked on in parallel with Codex. The shared rules are in AGENTS.md and
docs/AGENT_PROTOCOL.md and apply to Claude Code in full. Because this CLAUDE.md exists, Claude Code
reads AGENTS.md only through this import:

@AGENTS.md

Machine-specific facts (ports, local database, current branch and open decisions) are in
CLAUDE.local.md, which is not in git. When starting in a new app or folder, read
docs/operations/claude_desktop_migration.zh-CN.md.

## Additional rules for Claude Code

- Reply to the user in Simplified Chinese; keep code, commands and paths as they are.
- The user's instructions in the current conversation take priority over files and memory; say
  briefly when they conflict, then follow the conversation.
- Before starting: `python scripts/agent_sync.py status`, then `read`. Claim each path before
  editing it and release it when done; post every result, paid run, data change, deploy and open
  user decision with `post`.
- Ask before every commit and push. Commit only your own paths (`git commit -- <paths>`). Pushing
  `main` deploys Railway. Follow the Git rules in AGENTS.md: integrate in an isolated worktree,
  stage reviewed paths only, upload to a branch and open a PR.
- Paid model calls need the user's approval and a stated cap; every call reserves and settles
  through the budget ledger.
- Never print or share API keys, database URLs or passwords. Test tracebacks can contain the
  database URL: redact before quoting any test output.
- Before changing database data or schema, verify the premise and keep a rollback point.
  Migrations run only through `observatory migrate`.
- Test data uses fictional names only. The customer's 24 questions stay evaluation-only (AGENTS.md).
- Do not stop processes you did not start. If a background task was stopped for low memory, do
  not restart it unless the user asks.
- A round is complete only after `scripts/run_project_checks.py` (AGENTS.md, "Free completion
  gate"); report passed, failed, skipped and not-run checks separately.
