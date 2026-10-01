# Instructions for Codex (and any other agent)

This project is worked on in parallel by Codex and Claude Code. Follow docs/AGENT_PROTOCOL.md:

1. Before starting: `python scripts/agent_sync.py status`, read the other agent's updates, then `python scripts/agent_sync.py read`.
2. Before editing files: `python scripts/agent_sync.py claim <path-or-glob> --reason "..."`. If another agent holds the claim (exit code 2), coordinate instead of editing. Release when done.
3. After every result, paid run, data change, deploy or blocked decision: `python scripts/agent_sync.py post <kind> "<summary>" [--commit HEAD] [--evidence ...] [--needs ...] [--cost ...]`.
4. Commit only your own paths (`git commit -- <paths>`). Commits and pushes are logged automatically by .githooks.
5. Shared log: `D:/Projects/549 native ads/.coordination/` (override with `OBS_COORD_DIR`). In a new clone run `git config core.hooksPath .githooks`.
6. Pushing `main` deploys Railway; paid model calls and pushes need the user's approval.
