#!/bin/bash
# What is live, and what every worktree is doing. Run with `make status`.
cd "$(dirname "$0")/.."
. ./agent-kit.conf

if [ -n "$SERVICE" ]; then
  echo "LIVE"
  echo "  service:     $SERVICE $(systemctl --user is-active "$SERVICE" 2>/dev/null) since $(systemctl --user show "$SERVICE" -p ActiveEnterTimestamp --value 2>/dev/null)"
  if [ -s .deploys.log ]; then
    last="$(tail -1 .deploys.log)"; live="$(echo "$last" | cut -d' ' -f3)"
    echo "  last deploy: $last"
    behind="$(git rev-list --count "$live"..main 2>/dev/null)"
    [ "${behind:-0}" -gt 0 ] && echo "  main is $behind commit(s) ahead of what was deployed (make deploy)"
  else
    echo "  last deploy: none logged yet (make deploy logs each one)"
  fi
  echo
fi

echo "WORKTREES"
git worktree list --porcelain | awk '/^worktree /{print substr($0, 10)}' | while read -r path; do
  branch="$(git -C "$path" branch --show-current)"
  dirty="$(git -C "$path" status --porcelain | wc -l)"
  ahead="$(git rev-list --count main.."$branch" 2>/dev/null)"
  task=""
  if [ -f "$path/TASK.md" ]; then
    task="$(grep -m1 -i '^owner:' "$path/TASK.md" | cut -d: -f2- | xargs) · $(grep -m1 -i '^status:' "$path/TASK.md" | cut -d: -f2- | xargs)"
  fi
  printf '  %-12s %s\n' "$branch" "$path"
  printf '  %-12s %s uncommitted file(s)%s%s\n' "" "$dirty" "$([ "$branch" != main ] && echo ", ${ahead:-?} commit(s) not on main")" "${task:+ · $task}"
done

echo
echo "Other agent sessions: ListAgents in Claude Code; Codex sessions in ~/.codex/session_index.jsonl."
