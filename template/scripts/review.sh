#!/bin/bash
# Starts a second agent to review the changes, waits for it, and prints its findings.
#   make review KIND=codex|pi|claude|gemini [BASE=<git ref>] [MODEL=...]   DRY=1 prints the commands instead
# Or configure REVIEW_CMD in agent-kit.conf (or env) for any custom CLI ({BASE}, {OUT}, {PROMPT} placeholders).
# BASE defaults to HEAD when there are uncommitted changes, else HEAD~1 (the last commit; all of it if it is the first).
# Headless runs (outside herdr) enforce read-only mode where supported and write .reviews/<ts>-<kind>.md themselves.
# Inside herdr (HERDR_ENV=1) the reviewer gets a repo-scoped tab (<repo>-review-<kind>) for follow-up questions.
{  # read the whole script before running any of it, so editing this file during a run cannot break that run
set -e
cd "$(dirname "$0")/.."
ENV_REVIEW_CMD="${REVIEW_CMD:-}"
[ -f ./agent-kit.conf ] && . ./agent-kit.conf
REVIEW_CMD="${ENV_REVIEW_CMD:-${REVIEW_CMD:-}}"

KIND="$1"; BASE="$2"; MODEL="$3"
if [ -z "$REVIEW_CMD" ]; then
  [[ "$KIND" =~ ^(codex|pi|claude|gemini)$ ]] || {
    echo "usage: make review KIND=codex|pi|claude|gemini [BASE=<git ref>] [MODEL=...] (or set REVIEW_CMD)"
    exit 1
  }
fi
if [ -z "$BASE" ]; then
  if [ -n "$(git status --porcelain)" ]; then BASE=HEAD; else BASE=HEAD~1; fi
  # first commit (or empty repo): review all of it against git's empty tree
  git rev-parse --verify -q "$BASE^{commit}" >/dev/null || BASE="$(git hash-object -t tree /dev/null)"
else
  git rev-parse --verify -q "$BASE^{commit}" >/dev/null || { echo "review: $BASE is not a commit"; exit 1; }
fi

REPO_SLUG="$(basename "$PWD" | tr -cs 'A-Za-z0-9_-' '-' | sed 's/^-//;s/-$//')"
LABEL="${KIND:-custom}"
NAME="${REPO_SLUG:-repo}-review-$LABEL"
OUT=".reviews/$(date +%Y-%m-%d-%H%M%S)-$LABEL.md"

COMMON_PROMPT="[lead] Review the changes in this repo since $BASE: run \`git diff $BASE\` and \`git status\` (new files count). \
Keep to the project's rules in AGENTS.md. Code only: no Computer Use, screen, app or GUI actions. \
Look for correctness bugs, missed requirements, edge/failure cases, broken project rules and logic duplicated instead of reused. \
Report findings most severe first as R1, R2... with severity (critical/high/medium/low), file:line, one-sentence defect, \
a concrete failing scenario, and a concise fix; write 'No findings.' if there are none."

HERDR_PROMPT="$COMMON_PROMPT Do not edit any file except $OUT. Write your findings to $OUT, then reply with one line: DONE <number of findings>."
HEADLESS_PROMPT="$COMMON_PROMPT Do not edit any files. Output ONLY the Markdown findings report directly in your final response."

run() { if [ -n "$DRY" ]; then echo "$*"; else "$@"; fi; }
run_capture() {
  if [ -n "$DRY" ]; then
    echo "$* > $OUT"
  else
    local tmp="${OUT}.tmp.$$"
    if "$@" > "$tmp"; then
      mv "$tmp" "$OUT"
    else
      rm -f "$tmp"
      return 1
    fi
  fi
}

[ -n "$DRY" ] || { mkdir -p .reviews; rm -f "$OUT"; }

if [ -n "$REVIEW_CMD" ]; then
  CMD="${REVIEW_CMD//\{BASE\}/$BASE}"
  CMD="${CMD//\{OUT\}/$OUT}"
  CMD="${CMD//\{PROMPT\}/$HEADLESS_PROMPT}"
  if [ -n "$DRY" ]; then echo "$CMD"; exit 0; fi
  eval "$CMD"
elif [ "${HERDR_ENV:-}" = 1 ]; then
  case "$KIND" in
    codex)  ARGS=(-s workspace-write -a never -c 'model_reasoning_effort="high"'); [ -n "$MODEL" ] && ARGS+=(-m "$MODEL") ;;
    claude) ARGS=(--permission-mode auto -n "$NAME"); [ -n "$MODEL" ] && ARGS+=(--model "$MODEL") ;;
    pi)     ARGS=(--tools read,bash,write --thinking high -n "$NAME"); [ -n "$MODEL" ] && ARGS+=(--model "$MODEL") ;;
    gemini) ARGS=(); [ -n "$MODEL" ] && ARGS+=(-m "$MODEL") ;;
  esac
  if [ -n "$DRY" ]; then
    echo "herdr tab create --label $NAME --cwd $PWD --no-focus   (unless $NAME is already running)"
    run herdr agent start "$NAME" --kind "$KIND" --pane '<new pane>' --timeout 120000 -- "${ARGS[@]}"
    run herdr agent prompt "$NAME" "$HERDR_PROMPT" --wait --timeout 3600000
    exit 0
  elif ! herdr agent get "$NAME" >/dev/null 2>&1; then
    PANE="$(herdr tab create ${HERDR_WORKSPACE_ID:+--workspace "$HERDR_WORKSPACE_ID"} --label "$NAME" --cwd "$PWD" --no-focus \
      | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")"
    herdr agent start "$NAME" --kind "$KIND" --pane "$PANE" --timeout 120000 -- "${ARGS[@]}" >/dev/null \
      || { echo "review: $NAME did not become ready; look at its tab (it may be asking to trust this folder)"; exit 1; }
  fi
  herdr agent prompt "$NAME" "$HERDR_PROMPT" --wait --timeout 3600000 >/dev/null
  [ -f "$OUT" ] || herdr agent read "$NAME" --source recent-unwrapped --lines 40
else
  case "$KIND" in
    codex)  run codex exec -s read-only -c 'model_reasoning_effort="high"' ${MODEL:+-m "$MODEL"} -o "$OUT" "$HEADLESS_PROMPT" ;;
    claude) run_capture claude -p --permission-mode plan ${MODEL:+--model "$MODEL"} "$HEADLESS_PROMPT" ;;
    pi)     run_capture pi -p --tools read,bash --thinking high ${MODEL:+--model "$MODEL"} "$HEADLESS_PROMPT" ;;
    gemini) run_capture gemini -p "$HEADLESS_PROMPT" ${MODEL:+-m "$MODEL"} ;;
  esac
fi

[ -n "$DRY" ] && exit 0
if [ -f "$OUT" ]; then echo "--- $OUT"; cat "$OUT"; else echo "review: $NAME wrote no $OUT"; exit 1; fi
exit
}
