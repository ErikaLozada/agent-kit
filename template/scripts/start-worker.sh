#!/bin/bash
# Starts a worker agent for a task: its worktree (make task), its own herdr tab named after the task, and the agent in it
# with bounded worker permissions.
#   make worker NAME=fix-search TIER=simple|medium|complex [OWNER=...] [MODEL=...] [EFFORT=low|medium|high]
#   make worker NAME=fix-search KIND=codex|claude|pi|gemini [OWNER=...] [MODEL=...] [EFFORT=...]   DRY=1 prints commands
# Optional per-user tier presets live in ~/.config/agent-kit/tiers.conf (override path with AGENT_KIT_TIERS),
# and can be overridden per project in agent-kit.conf (TIER_SIMPLE_KIND/MODEL/EFFORT, etc.) or WORKER_CMD.
{  # read the whole script before running any of it, so editing this file during a run cannot break that run
set -e
cd "$(dirname "$0")/.."
ENV_WORKER_CMD="${WORKER_CMD:-}"
TIERS_FILE="${AGENT_KIT_TIERS:-$HOME/.config/agent-kit/tiers.conf}"
[ -f "$TIERS_FILE" ] && . "$TIERS_FILE"
[ -f ./agent-kit.conf ] && . ./agent-kit.conf
WORKER_CMD="${ENV_WORKER_CMD:-${WORKER_CMD:-}}"

NAME="$1"; KIND="$2"; OWNER="$3"; MODEL="$4"; EFFORT="$5"
case "${TIER:-}" in                                         # user tiers (~/.config/agent-kit/tiers.conf); explicit args win
  simple)
    KIND="${KIND:-${TIER_SIMPLE_KIND:-codex}}"
    MODEL="${MODEL:-${TIER_SIMPLE_MODEL:-}}"
    EFFORT="${EFFORT:-${TIER_SIMPLE_EFFORT:-high}}"
    ;;
  medium)
    KIND="${KIND:-${TIER_MEDIUM_KIND:-claude}}"
    MODEL="${MODEL:-${TIER_MEDIUM_MODEL:-}}"
    EFFORT="${EFFORT:-${TIER_MEDIUM_EFFORT:-high}}"
    ;;
  complex)
    KIND="${KIND:-${TIER_COMPLEX_KIND:-claude}}"
    MODEL="${MODEL:-${TIER_COMPLEX_MODEL:-}}"
    EFFORT="${EFFORT:-${TIER_COMPLEX_EFFORT:-high}}"
    ;;
  "") ;;
  *) echo "TIER must be simple, medium or complex"; exit 1 ;;
esac

if [ -n "$WORKER_CMD" ]; then
  [ -n "$NAME" ] || { echo "usage: make worker NAME=<short-name> [OWNER=...] [MODEL=...] [EFFORT=...]"; exit 1; }
  KIND="${KIND:-custom}"
else
  [ -n "$NAME" ] && [[ "$KIND" =~ ^(codex|claude|pi|gemini)$ ]] || {
    echo "usage: make worker NAME=<short-name> TIER=simple|medium|complex (or KIND=codex|claude|pi|gemini) [OWNER=...] [MODEL=...] [EFFORT=...]"
    exit 1
  }
fi
OWNER="${OWNER:-$KIND worker}"
MAIN="$PWD"; WT="$(dirname "$MAIN")/$(basename "$MAIN")-$NAME"

ARGS=()
case "$KIND" in
  codex)  ARGS=(--sandbox workspace-write --ask-for-approval on-request -c sandbox_workspace_write.network_access=true)
          [ -n "$MODEL" ] && ARGS+=(-m "$MODEL"); [ -n "$EFFORT" ] && ARGS+=(-c "model_reasoning_effort=$EFFORT") ;;
  claude) ARGS=(--permission-mode auto)
          [ -n "$MODEL" ] && ARGS+=(--model "$MODEL"); [ -n "$EFFORT" ] && ARGS+=(--effort "$EFFORT") ;;
  pi)     ARGS=(-n "$NAME")
          [ -n "$MODEL" ] && ARGS+=(--model "$MODEL"); [ -n "$EFFORT" ] && ARGS+=(--thinking "$EFFORT") ;;
  gemini) ARGS=()
          [ -n "$MODEL" ] && ARGS+=(-m "$MODEL") ;;
esac
run() { if [ -n "$DRY" ]; then printf '%q ' "$@"; echo; else "$@"; fi; }

[ -d "$WT" ] || run bash scripts/new-task.sh "$NAME" "$OWNER"
NOTE="; never commits: the lead reviews and commits"
if [ -z "$DRY" ]; then                                      # awk + mv, not sed -i: GNU and BSD sed differ
  if [ -n "${HERDR_PANE_ID:-}" ]; then LEAD="herdr pane $HERDR_PANE_ID (report there"
  else LEAD="the session that started you, not in herdr (report in your reply to it"; fi
  awk -v lead="Lead: $LEAD; it reviews, commits and merges)" \
      -v agent="Agent: $KIND, model ${MODEL:-default}, effort ${EFFORT:-default}$NOTE" \
      'FNR == NR { if (/^Agent: /) has = 1; next }               # first pass: is there an Agent: line yet?
       /^Lead: / {print lead; next} /^Agent: / {print agent; next} {print}
       /^Owner: / && !has {print agent}' "$WT/TASK.md" "$WT/TASK.md" > "$WT/TASK.md.$$"
  mv "$WT/TASK.md.$$" "$WT/TASK.md"
fi

if [ -n "$WORKER_CMD" ]; then
  CMD="${WORKER_CMD//\{WT\}/$WT}"
  CMD="${CMD//\{NAME\}/$NAME}"
  CMD="${CMD//\{MODEL\}/$MODEL}"
  CMD="${CMD//\{EFFORT\}/$EFFORT}"
  if [ -n "$DRY" ]; then echo "$CMD"; exit 0; fi
  eval "$CMD"
  exit 0
fi

if [ "${HERDR_ENV:-}" != 1 ]; then
  echo "Not inside herdr: start it yourself with:  cd $WT && $KIND ${ARGS[*]}"; exit 0
fi
if [ -n "$DRY" ]; then
  echo "herdr tab create --label $NAME --cwd $WT --no-focus"
  run herdr agent start "$NAME" --kind "$KIND" --pane '<new pane>' -- "${ARGS[@]}"; exit 0
fi
PANE="$(herdr tab create ${HERDR_WORKSPACE_ID:+--workspace "$HERDR_WORKSPACE_ID"} --label "$NAME" --cwd "$WT" --no-focus \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")"
herdr agent start "$NAME" --kind "$KIND" --pane "$PANE" --timeout 60000 -- "${ARGS[@]}" >/dev/null \
  || echo "Worker $NAME started but is not ready: it may be waiting for an approval in pane $PANE"
echo "Worker $NAME ($KIND) in pane $PANE, folder $WT. Brief it: herdr agent prompt $NAME \"...\" --wait"
exit
}
