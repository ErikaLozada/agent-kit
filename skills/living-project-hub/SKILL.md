---
name: living-project-hub
description: >-
  Standard living, Fern & Stone styled interactive Project & Learning Hub for
  any multi-phase or multi-wave project (works cleanly with or without
  .planning/ / GSD workflows). Supports a single unified multi-project hub
  server (one port & Projects Index for all repos on the machine) with live
  progress tracks, clickable decisions & checklists, an Execution & Learning
  Log, formatted Markdown Document Library, frozen phase snapshots, automatic
  system Dark/Light mode + toggle, and one-click feedback save-back to each
  project's .scratch/owner-feedback.md.
---

# Living Project & Learning Hub

Source of truth: `skills/living-project-hub` in `agent-kit` (linked globally via `install.sh --link-skills`). Resolve its real path via `HUB_SKILL=$(cd -P <this skill's folder> && pwd)`.

Use this skill as the ongoing communication and learning control center across all agent harnesses for any multi-phase or multi-wave project (including repos using `.planning/` / GSD workflows). Styled in **Fern & Stone · Tidepool** (auto-follows system Dark/Light mode + manual toggle, zero external CDN dependencies, fluid `max-width: 1360px` tablet-landscape layout).

## 1. Unified Multi-Project Hub Server (Recommended — One Port for All Projects)

Instead of running a different port per project (`8765`, `8767`, `8768`...), run **one** background hub server for the whole machine with a bookmarkable Projects Index at `/` and each project mounted at `/p/<slug>/`:

```sh
# Once per machine (Linux systemd / macOS launchd; binds strictly to 127.0.0.1:8765)
bash "$HUB_SKILL/scripts/setup-hub-server.sh"
# Optional: expose privately over Tailscale HTTPS on one bookmarkable URL (Linux: prepend sudo)
tailscale serve --bg --https=8445 http://127.0.0.1:8765
```

Then, inside **any** project repository:

```sh
# Build .scratch/project-hub.html, register this repo in ~/.config/agent-hub/projects.json, and print its URL
build-project-hub --register
# (or: python3 "$HUB_SKILL/scripts/build_hub.py" --register)

# Save a frozen snapshot when a phase completes (and keep the live hub updated)
build-project-hub --snapshot phase-01-setup --register
```

- All projects appear on the single index page (`/`), and each project's `/p/<slug>/api/feedback` writes strictly into **that** project's `.scratch/owner-feedback.md` and `.scratch/owner-feedback.json`.
- Registry metadata (`~/.config/agent-hub/projects.json`, `0600`) stays strictly local — never commit it to git.
- **Single-project fallback:** If you prefer running an ad-hoc server for one repo without the registry, check listening ports (`ss -ltn` on Linux / `lsof -nP -iTCP -sTCP:LISTEN` on macOS) and run `python3 "$HUB_SKILL/scripts/hub_server.py" --host 127.0.0.1 --port <free-port>`.

## 2. File Layout (Git-Ignored)

Store all generated hub outputs and live state inside each project's git-ignored `.scratch/` directory (never commit `.scratch/` files):

- `.scratch/project-hub.html` — single-file, zero-dependency interactive HTML hub.
- `.scratch/snapshots/phase-<NN>-<slug>.html` — frozen, self-contained HTML snapshot saved at the close of each completed phase (served read-only at `/p/<slug>/snapshots/<name>.html` and linked from the sidebar).
- `.scratch/execution-log.json` — append-only JSON array of executed engineering steps (zero secrets, zero raw private IDs).
- `.scratch/hub-config.json` — optional JSON overrides for phase/wave trackers, active human checkpoints, status chips, and review round IDs (works out of the box without it).
  - **Keep it in sync with plans:** Whenever a project's plan or phases change, update phase names and deliverables in `.scratch/hub-config.json` and rebuild in the same step — or omit static `phases` from `hub-config.json` when `.planning/ROADMAP.md` is already the single source of truth.
- `.scratch/owner-feedback.md` & `.scratch/owner-feedback.json` — saved owner annotations/answers written by `hub_server.py`.
- Archive prior feedback rounds (e.g., `.scratch/owner-feedback-round1.md`) and bump `round_id` (or `--round`) whenever advancing to a new review round so stale answers never bleed into the next round.

## 3. Required Hub Sections

1. **Hero Dashboard & Progress Tracks:** "Where We Are" summary, git branch/commit chip, visual Phase Track (auto-parsed from `.planning/ROADMAP.md` or `.scratch/hub-config.json`), and active Wave Stepper.
2. **Active Blockers, Decisions & Human Checkpoints:** Optional interactive checklist + copyable commands + non-sensitive report-back form (never paste tokens, PATs, or secrets).
3. **Execution & Learning Log:** Populated from `.scratch/execution-log.json` (fetched live via `/api/log` with **↻ Refresh Live Log**). Each entry records `id`, `timestamp`, `wave`, `plan`, `arch_link`, `tool`, `title`, `command` (parameterized cleanly), `parameters`, `why`, `result`, and `learning` (1–2 sentence engineering takeaway), with **Agree / Question / Change / Skip** + note controls.
4. **Readable Markdown Document Library:** Auto-discovers `docs/`, `.planning/`, root playbooks, and `guides/` with a zero-dependency Formatted Markdown Reader (inline toggle, full-screen Reader Modal, Raw toggle, frontmatter `<details>`, and structured tag blocks).
5. **Phase Snapshots & Sticky Bottom Dock:** Sidebar links every frozen snapshot in `.scratch/snapshots/`. Bottom dock provides live counters, **Reset All**, **Copy Single Prompt** (modal with clipboard + `execCommand` fallback), and **Save Feedback to Host** (when served over HTTP/HTTPS).

## 4. Remote Access & Quality Checks

- Never hand out a local `file://` path alone when reviewing remotely over Tailscale; serve via the unified `agent-hub-server --multi` behind `tailscale serve --bg --https=8445 http://127.0.0.1:8765` (never bind `0.0.0.0` on untrusted networks).
- If a single-file hub grows large (> 250 KB from many docs), consider serving doc bodies lazily while keeping `--snapshot` self-contained.
- Always validate inline `<script>` syntax (`node --check`) after customizing the HTML template.
- Periodically distill recurring traps from `.scratch/execution-log.json` via the `wrap-up` skill into `AGENTS.md`, `docs/decisions.md`, a domain overlay, or `agent-kit`.
