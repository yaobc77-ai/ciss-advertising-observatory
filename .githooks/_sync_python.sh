# Shared helper for hooks: run scripts/agent_sync.py with the best available Python.
# Hooks never block a commit or push. A failed post is written to
# .git/agent-sync-failed.log, which "agent_sync.py status" reports.
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
failed="$(git rev-parse --absolute-git-dir 2>/dev/null)/agent-sync-failed.log"
for candidate in "$root/.venv/Scripts/python.exe" "$root/.venv/bin/python" python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    if ! "$candidate" -X utf8 "$root/scripts/agent_sync.py" "$@" >/dev/null 2>&1; then
      printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$failed"
    fi
    exit 0
  fi
done
printf '%s\tno python found\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$failed"
exit 0
