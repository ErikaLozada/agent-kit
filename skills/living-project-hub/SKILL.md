---
name: living-project-hub
description: >-
  Standard living, Fern & Stone styled interactive Project & Learning Hub for
  any multi-phase or multi-wave project (works cleanly with or without
  .planning/ / GSD workflows). Replaces walls of markdown with a bookmarkable
  HTML control center featuring live progress tracks, clickable decisions &
  checklists, an Execution & Learning Log (tools, exact parameterized CLI
  commands, architecture link, key takeaways), a formatted Markdown Document
  Library, frozen phase snapshots, Light/Dark toggle, and one-click feedback
  save-back to .scratch/owner-feedback.md.
---

# Living Project & Learning Hub

Source of truth: `skills/living-project-hub` in `agent-kit` (linked globally via `install.sh --link-skills`). Resolve its real path via `HUB_SKILL=$(cd -P <this skill's folder> && pwd)`.

Use this skill as the ongoing communication and learning control center across all agent harnesses for any multi-phase or multi-wave project (including repos using `.planning/` / GSD workflows). Styled in **Fern & Stone · Tidepool** (Light default + Dark toggle, zero external CDN dependencies, fluid `max-width: 1360px` tablet-landscape layout).

## 1. File Layout (Git-Ignored)

Store all generated hub outputs and live state inside the project's git-ignored `.scratch/` directory (never commit `.scratch/` files):

- `.scratch/project-hub.html` — single-file, zero-dependency interactive HTML hub.
- `.scratch/snapshots/phase-<NN>-<slug>.html` — frozen, self-contained HTML snapshot saved at the close of each completed phase (served read-only at `/snapshots/<name>.html` and linked from the sidebar).
- `.scratch/execution-log.json` — append-only JSON array of executed engineering steps (zero secrets, zero raw private IDs).
- `.scratch/hub-config.json` — optional JSON overrides for phase/wave trackers, active human checkpoints, status chips, and review round IDs (works out of the box without it).
- `.scratch/owner-feedback.md` & `.scratch/owner-feedback.json` — saved owner annotations/answers written by `hub_server.py`.
- Archive prior feedback rounds (e.g., `.scratch/owner-feedback-round1.md`) and bump `round_id` (or `--round`) whenever advancing to a new review round so stale answers never bleed into the next round.

Run directly from the global skill (or copy into `.scratch/` if a project needs custom pages):

```sh
# Build the live hub (auto-discovers docs/, .planning/, root playbooks, guides/, execution-log.json, snapshots/)
python3 "$HUB_SKILL/scripts/build_hub.py"

# Save a frozen snapshot when a phase completes (also rebuilds live hub with the snapshot linked)
python3 "$HUB_SKILL/scripts/build_hub.py" --snapshot phase-01-setup

# Serve locally or over Tailscale (zero external dependencies)
python3 "$HUB_SKILL/scripts/hub_server.py" --host "$(tailscale ip -4)" --port 8765
```

`hub_server.py` exposes only:
- `GET /` and `GET /project-hub.html` → serves `.scratch/project-hub.html` dynamically from disk (`no-store`)
- `GET /api/log` → serves `.scratch/execution-log.json` live
- `GET /api/state` → serves saved `.scratch/owner-feedback.json`
- `GET /api/snapshots` → lists `.scratch/snapshots/*.html`
- `GET /snapshots/<name>.html` → serves frozen phase snapshots (path-traversal guarded)
- `POST /api/feedback` → writes `.scratch/owner-feedback.md` and `.scratch/owner-feedback.json`
- `GET /health` → `{"ok": true}`

## 2. Required Hub Sections

1. **Hero Dashboard & Progress Tracks:** "Where We Are" summary, git branch/commit chip, visual Phase Track (auto-parsed from `.planning/ROADMAP.md` or `.scratch/hub-config.json`), and active Wave Stepper.
2. **Active Blockers, Decisions & Human Checkpoints:** Optional interactive checklist + copyable commands + non-sensitive report-back form (never paste tokens, PATs, or secrets).
3. **Execution & Learning Log:** Populated from `.scratch/execution-log.json` (fetched live via `/api/log` with **↻ Refresh Live Log**). Each entry records `id`, `timestamp`, `wave`, `plan`, `arch_link`, `tool`, `title`, `command` (parameterized cleanly), `parameters`, `why`, `result`, and `learning` (1–2 sentence engineering takeaway), with **Agree / Question / Change / Skip** + note controls.
4. **Readable Markdown Document Library:** Auto-discovers `docs/`, `.planning/`, root playbooks, and `guides/` with a zero-dependency Formatted Markdown Reader (inline toggle, full-screen Reader Modal, Raw toggle, frontmatter `<details>`, and structured tag blocks).
5. **Phase Snapshots & Sticky Bottom Dock:** Sidebar links every frozen snapshot in `.scratch/snapshots/`. Bottom dock provides live counters, **Reset All**, **Copy Single Prompt** (modal with clipboard + `execCommand` fallback), and **Save Feedback to Host** (when served over HTTP/HTTPS).

## 3. Remote Access & Quality Checks

- Never hand out a local `file://` path alone when reviewing remotely over Tailscale; bind `hub_server.py` strictly to `tailscale ip -4` (or `127.0.0.1` for local use), never `0.0.0.0` on untrusted networks.
- If a single-file hub grows large (> 250 KB from many docs), consider serving doc bodies lazily via `/api/doc?id=...` while keeping `--snapshot` self-contained.
- Always validate inline `<script>` syntax (`node --check`) after customizing the HTML template.
- Periodically distill recurring traps from `.scratch/execution-log.json` via the `wrap-up` skill into `AGENTS.md`, `docs/decisions.md`, a domain overlay, or `agent-kit`.
