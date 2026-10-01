# Instructions for Claude Code

This project is worked on in parallel with Codex. Follow docs/AGENT_PROTOCOL.md (same rules as AGENTS.md):

1. Before starting: `python scripts/agent_sync.py status`, then `python scripts/agent_sync.py read`.
2. Claim paths before editing (`claim`); never edit a path another agent has claimed without coordinating.
3. Post every result, paid run, data change, deploy and open user decision with `post`; commits and pushes are logged by .githooks.
4. Commit only your own paths with `git commit -- <paths>`; pushing `main` deploys Railway and needs user approval.
5. Reply to the user in Simplified Chinese.
