#!/bin/bash
# Rebuilds docs/diagrams/*.html from project specs using the linked feature-diagram skill.
# Projects keep only their specs (default: scripts/diagrams.py); the shared renderer lives in agent-kit.
set -euo pipefail

[ -f agent-kit.conf ] && source agent-kit.conf

SPECS="${DIAGRAM_SPECS:-scripts/diagrams.py}"
OUT="${DIAGRAM_OUT:-docs/diagrams}"

find_skill() {
  local cand
  for cand in \
    "${AGENT_KIT_DIAGRAM_SKILL:-}" \
    "$HOME/.claude/skills/feature-diagram" \
    "$HOME/.agents/skills/feature-diagram" \
    "$HOME/.codex/skills/feature-diagram" \
    "$HOME/.gemini/config/skills/feature-diagram" \
    "$HOME/.pi/agent/skills/feature-diagram" \
    "$HOME/.hermes/skills/feature-diagram"
  do
    if [ -n "$cand" ] && [ -f "$cand/scripts/render_diagram.py" ]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

SKILL_DIR="$(find_skill || true)"
if [ -z "$SKILL_DIR" ]; then
  echo "make diagram: feature-diagram skill not found in global skills folders." >&2
  echo "Link the agent-kit skills on this machine first:" >&2
  echo "  bash <path-to-agent-kit>/install.sh --link-skills" >&2
  exit 1
fi

if [ ! -f "$SPECS" ]; then
  echo "make diagram: spec file not found: $SPECS" >&2
  echo "Add feature diagram specs there (see the feature-diagram skill), or set DIAGRAM_SPECS in agent-kit.conf." >&2
  exit 1
fi

exec python3 "$SKILL_DIR/scripts/render_diagram.py" "$SPECS" --out "$OUT"
