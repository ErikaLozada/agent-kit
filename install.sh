#!/bin/bash
# Adds the agent kit to a project: bash <kit>/install.sh <project folder> ["Project Name"]
# Works on a new or an existing folder. Never overwrites a file that is already there; says what it skipped.
#   bash <kit>/install.sh --link-skills   links the kit's skills/* into each harness's global skills folder that
#   exists (~/.claude/skills, ~/.agents/skills, ~/.pi/agent/skills); keeps anything already there. Nothing else.
set -e
if [ "$1" = --link-skills ]; then
  ROOT="$(cd -P "$(dirname "$0")" && pwd)"
  for home in "$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.pi/agent/skills"; do
    [ -d "$home" ] || continue
    for skill in "$ROOT"/skills/*/; do
      skill="${skill%/}"; dst="$home/$(basename "$skill")"
      if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$skill" ]; then echo "  linked   $dst (already)"
      elif [ -e "$dst" ] || [ -L "$dst" ]; then echo "  kept     $dst (already there, not a link to this kit)"
      else ln -s "$skill" "$dst"; echo "  added    $dst -> $skill"; fi
    done
  done
  exit 0
fi
KIT="$(cd "$(dirname "$0")" && pwd)/template"
DIR="$1"; NAME="${2:-$(basename "${DIR%/}")}"
[ -n "$DIR" ] || { echo "usage: install.sh <project folder> [\"Project Name\"]"; exit 1; }
mkdir -p "$DIR"; cd "$DIR"
[ -d .git ] || git init -q -b main

copied=(); skipped=()
while IFS= read -r -d '' src; do
  rel="${src#$KIT/}"
  if [ -e "$rel" ] || [ -L "$rel" ]; then skipped+=("$rel"); continue; fi
  mkdir -p "$(dirname "$rel")"
  sed -e "s|{{PROJECT}}|$NAME|g" -e "s|{{DATE}}|$(date +%F)|g" "$src" > "$rel"
  [ -x "$src" ] && chmod +x "$rel"
  copied+=("$rel")
done < <(find "$KIT" -type f -print0 | sort -z)

if [ ! -e .claude/skills ]; then mkdir -p .claude && ln -s ../.agents/skills .claude/skills && copied+=(".claude/skills -> .agents/skills"); fi
chmod +x scripts/*.sh .githooks/pre-commit 2>/dev/null || true
git config core.hooksPath .githooks

echo "Agent kit installed in $PWD"
printf '  added    %s\n' "${copied[@]}"
[ ${#skipped[@]} -eq 0 ] || printf '  kept     %s (already there)\n' "${skipped[@]}"
echo
echo "Next: fill in the TODO sections of AGENTS.md, set agent-kit.conf, then commit (the hook runs make test)."
