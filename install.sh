#!/bin/bash
# Adds the agent kit to a project:
#   bash <kit>/install.sh <project folder> ["Project Name"] [--overlay <path-or-name>]...
#   bash <kit>/install.sh --link-skills         link skills/* into each installed harness's global skills folder
#   bash <kit>/install.sh --check <project>     read-only check for missing or drifted kit files
# Works on a new or existing folder. Never overwrites an existing file or silently disables existing git hooks.
set -e

ROOT="$(cd -P "$(dirname "$0")" && pwd)"
KIT="$ROOT/template"

if [ "${1:-}" = --link-skills ]; then
  HOMES=(
    "$HOME/.claude/skills"
    "$HOME/.agents/skills"
    "$HOME/.codex/skills"
    "$HOME/.gemini/config/skills"
    "$HOME/.pi/agent/skills"
    "$HOME/.hermes/skills"
  )
  if [ -n "${AGENT_SKILLS_DIRS:-}" ]; then
    IFS=: read -r -a EXTRA_HOMES <<< "$AGENT_SKILLS_DIRS"
    HOMES+=("${EXTRA_HOMES[@]}")
  fi
  for home in "${HOMES[@]}"; do
    [ -n "$home" ] && [ -d "$home" ] || continue
    for skill in "$ROOT"/skills/*/; do
      skill="${skill%/}"; dst="$home/$(basename "$skill")"
      if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$skill" ]; then echo "  linked   $dst (already)"
      elif [ -e "$dst" ] || [ -L "$dst" ]; then echo "  kept     $dst (already there, not a link to this kit)"
      else ln -s "$skill" "$dst"; echo "  added    $dst -> $skill"; fi
    done
  done
  exit 0
fi

# Copy what the kit's git tracks (or would track): never caches such as __pycache__/*.pyc or .DS_Store.
template_files() {
  if git -C "$KIT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$KIT" ls-files -z --cached --others --exclude-standard -- . | while IFS= read -r -d '' rel; do
      [ -f "$KIT/$rel" ] && [ ! -L "$KIT/$rel" ] && [ "${rel##*/}" != .DS_Store ] && printf '%s\0' "$KIT/$rel"
    done
  else
    find "$KIT" -type f ! -name .DS_Store ! -name '*.pyc' ! -path '*/__pycache__/*' -print0
  fi
}

if [ "${1:-}" = --check ]; then
  TARGET="${2:-}"
  [ -n "$TARGET" ] && [ -d "$TARGET" ] || { echo "usage: install.sh --check <project folder>"; exit 1; }
  echo "Checking $TARGET against $KIT (read-only)"
  while IFS= read -r -d '' src; do
    rel="${src#$KIT/}"
    dst="$TARGET/$rel"
    if [ ! -e "$dst" ] && [ ! -L "$dst" ]; then
      echo "  missing     $rel"
    elif [ "$rel" = "AGENTS.md" ] || [ "$rel" = "agent-kit.conf" ] || [ "$rel" = "docs/decisions.md" ]; then
      echo "  project     $rel (present; project-owned)"
    elif cmp -s "$src" "$dst"; then
      echo "  ok          $rel"
    else
      echo "  customized  $rel"
    fi
  done < <(template_files | sort -z)
  exit 0
fi

OVERLAYS=()
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --overlay)
      [ $# -ge 2 ] || { echo "install.sh: --overlay requires a path or overlay name"; exit 1; }
      OVERLAYS+=("$2"); shift 2 ;;
    --overlay=*)
      OVERLAYS+=("${1#*=}"); shift ;;
    -h|--help)
      echo "usage: install.sh <project folder> [\"Project Name\"] [--overlay <path-or-name>]..."
      echo "       install.sh --link-skills"
      echo "       install.sh --check <project folder>"
      exit 0 ;;
    *)
      POSITIONAL+=("$1"); shift ;;
  esac
done

DIR="${POSITIONAL[0]:-}"
[ -n "$DIR" ] || { echo "usage: install.sh <project folder> [\"Project Name\"] [--overlay <path-or-name>]..."; exit 1; }

# Validate overlays before touching the target folder
RESOLVED_OVERLAYS=()
OVERLAY_NAMES=()
OVERLAY_ROOT="${AGENT_KIT_OVERLAYS:-$HOME/.config/agent-kit/overlays}"
for ov in "${OVERLAYS[@]}"; do
  if [ -d "$ov" ]; then
    RESOLVED_OVERLAYS+=("$(cd -P "$ov" && pwd)")
    OVERLAY_NAMES+=("$(basename "${ov%/}")")
  elif [ -d "$OVERLAY_ROOT/$ov" ]; then
    RESOLVED_OVERLAYS+=("$(cd -P "$OVERLAY_ROOT/$ov" && pwd)")
    OVERLAY_NAMES+=("$ov")
  else
    echo "install.sh: overlay not found: $ov (checked path and $OVERLAY_ROOT/$ov)"
    exit 1
  fi
done

mkdir -p "$DIR"; cd "$DIR"
NAME="${POSITIONAL[1]:-$(basename "$PWD")}"
[ -d .git ] || git init -q -b main

copied=(); skipped=(); notes=()
TODAY="$(date +%F)"

copy_template_file() {
  local src="$1" rel="$2"
  if [ -e "$rel" ] || [ -L "$rel" ]; then skipped+=("$rel"); return; fi
  mkdir -p "$(dirname "$rel")"
  sed -e "s|{{PROJECT}}|$NAME|g" -e "s|{{DATE}}|$TODAY|g" "$src" > "$rel"
  [ -x "$src" ] && chmod +x "$rel"
  copied+=("$rel")
}

while IFS= read -r -d '' src; do
  copy_template_file "$src" "${src#$KIT/}"
done < <(template_files | sort -z)

# Apply optional overlays (generic add-on packs layered after the core template)
for idx in "${!RESOLVED_OVERLAYS[@]}"; do
  ov_dir="${RESOLVED_OVERLAYS[$idx]}"
  ov_name="${OVERLAY_NAMES[$idx]}"
  while IFS= read -r -d '' src; do
    rel="${src#$ov_dir/}"
    case "$rel" in
      AGENTS.append.md|.gitignore.append) continue ;;
    esac
    copy_template_file "$src" "$rel"
  done < <(find "$ov_dir" -type f ! -name .DS_Store ! -name '*.pyc' ! -path '*/__pycache__/*' ! -path '*/.git/*' -print0 | sort -z)

  if [ -f "$ov_dir/AGENTS.append.md" ] && [ -f AGENTS.md ]; then
    marker="<!-- overlay: $ov_name -->"
    if ! grep -Fq "$marker" AGENTS.md; then
      {
        printf '\n%s\n' "$marker"
        sed -e "s|{{PROJECT}}|$NAME|g" -e "s|{{DATE}}|$TODAY|g" "$ov_dir/AGENTS.append.md"
      } >> AGENTS.md
      notes+=("appended overlay '$ov_name' snippet to AGENTS.md")
    fi
  fi
  if [ -f "$ov_dir/.gitignore.append" ]; then
    touch .gitignore
    while IFS= read -r line || [ -n "$line" ]; do
      [ -n "$line" ] || continue
      grep -Fxq "$line" .gitignore || printf '%s\n' "$line" >> .gitignore
    done < "$ov_dir/.gitignore.append"
    notes+=("merged overlay '$ov_name' entries into .gitignore")
  fi
done

if [ ! -e .claude/skills ]; then mkdir -p .claude && ln -s ../.agents/skills .claude/skills && copied+=(".claude/skills -> .agents/skills"); fi
chmod +x scripts/*.sh .githooks/pre-commit 2>/dev/null || true

# Protect existing git hooks in adopted repos instead of silently bypassing them
existing_hooks="$(git config --local core.hooksPath 2>/dev/null || true)"
if [ -n "$existing_hooks" ] && [ "$existing_hooks" != ".githooks" ]; then
  notes+=("kept existing git core.hooksPath ($existing_hooks); chain .githooks/pre-commit manually or run 'make setup' to switch")
elif [ -z "$existing_hooks" ] && [ -e .git/hooks/pre-commit ]; then
  notes+=("kept existing .git/hooks/pre-commit; chain .githooks/pre-commit manually or run 'make setup' to switch")
else
  git config core.hooksPath .githooks
fi

echo "Agent kit installed in $PWD"
[ ${#copied[@]} -eq 0 ] || printf '  added    %s\n' "${copied[@]}"
[ ${#skipped[@]} -eq 0 ] || printf '  kept     %s (already there)\n' "${skipped[@]}"
[ ${#notes[@]} -eq 0 ] || printf '  note     %s\n' "${notes[@]}"
echo
echo "Next: fill in AGENTS.md and agent-kit.conf, add tests or TEST_CMD, then commit (the hook runs make test)."
echo "No tests yet? Commit with ALLOW_NO_TESTS=1 git commit ...: allowed, but reported as NOT_EVALUATED."
