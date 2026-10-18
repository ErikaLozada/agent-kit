#!/bin/bash
# Starts a task in its own worktree and branch, beside this folder: make task NAME=fix-search [OWNER="Codex"]
# Untracked files listed in LINKS (agent-kit.conf) are symlinked in; tracked ones come from the branch.
set -e
cd "$(dirname "$0")/.."
. ./agent-kit.conf
NAME="$1"; OWNER="${2:-unassigned}"
[ -n "$NAME" ] || { echo "usage: make task NAME=<short-name> [OWNER=<agent>]"; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "Run from the main worktree."; exit 1; }
MAIN="$PWD"; WT="$(dirname "$MAIN")/$(basename "$MAIN")-$NAME"

git worktree add -q -b "$NAME" "$WT" main
for f in $LINKS; do
  [[ " $OWN " == *" $f "* ]] && continue
  if [ -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1 && [ ! -e "$WT/$f" ]; then
    mkdir -p "$WT/$(dirname "$f")"; ln -s "$MAIN/$f" "$WT/$f"
  fi
done

used="$(cat "$(dirname "$MAIN")"/"$(basename "$MAIN")"-*/TASK.md 2>/dev/null | sed -n 's/^Port: *//p')"
PORT="${TEST_PORT:-8001}"; while echo "$used" | grep -qx "$PORT" || ss -ltn 2>/dev/null | grep -q ":$PORT "; do PORT=$((PORT+1)); done

cat > "$WT/TASK.md" <<EOF
# Task: $NAME
Owner: $OWNER
Status: working
Branch: $NAME
Port: $PORT
Lead: none (make worker fills this in)

## Goal
(what done looks like, and the requirement or decision it serves)

## Files
(files this task changes; tell peers before touching anything else)

## Contracts
(anything other work depends on: a data format, API, prompt, command)

## Test server
${TEST_SERVER//\{PORT\}/$PORT}

## Notes
EOF
echo "Task $NAME: $WT (branch $NAME, test port $PORT). Fill in TASK.md; finish with: make finish NAME=$NAME"
