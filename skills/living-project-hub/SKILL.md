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

# Living Project Hub

A live web page for a multi-phase project: where it stands, open decisions, a log of what was done and learned, the project's docs, and frozen snapshots of finished phases. The owner annotates it and saves feedback straight back into the project. One server on the machine hosts every project's hub.

The skill's source is `skills/living-project-hub` in `agent-kit`; `install.sh --link-skills` links it into each agent tool. Below, `$HUB_SKILL` means its real path: `HUB_SKILL=$(cd -P <this skill's folder> && pwd)`.

## Build a project's hub

Run in the project repo:

```sh
build-project-hub --register                              # build the hub and list the project on the hub server
build-project-hub --snapshot phase-01-setup --register    # same, plus a frozen snapshot when a phase completes
```

`build-project-hub` is `$HUB_SKILL/scripts/build_hub.py`. The hub is then at `/p/<slug>/` on the hub server; after a rebuild, refreshing the browser is enough.

- **Never copy `build_hub.py` or `hub_server.py` into a project.** A local copy freezes an old version whose links break on the shared server. Customize through `.scratch/hub-config.json`; if the hub needs a new feature or gets too large, change this skill in `agent-kit` so every project benefits.
- Phases come from `.planning/ROADMAP.md` when it exists. Otherwise, or to override them, set them in `.scratch/hub-config.json`. When the plan changes, update that file and rebuild in the same step.
- Before a new review round, rename the old feedback (e.g. `.scratch/owner-feedback-round1.md`) and bump `round_id` (or pass `--round`) so old answers don't carry over.

## Files

All in the project's git-ignored `.scratch/` folder; never commit them.

| File | Contents |
| --- | --- |
| `project-hub.html` | The hub, as one self-contained HTML file |
| `snapshots/phase-<NN>-<slug>.html` | Frozen copy saved when a phase completes, linked from the sidebar |
| `execution-log.json` | Append-only list of engineering steps; never secrets or private IDs |
| `hub-config.json` | Optional: phases, waves, checkpoints, status chips, review round |
| `owner-feedback.md`, `owner-feedback.json` | The owner's saved notes, written by the server |

## What the hub shows

1. **Overview:** where the project stands, git branch and commit, a phase track and the current wave.
2. **Blockers, decisions and checkpoints:** an optional checklist, copyable commands and a report-back form. Never ask for tokens or secrets in it.
3. **Execution and learning log:** read live from `execution-log.json`. Each entry has `id`, `timestamp`, `wave`, `plan`, `arch_link`, `tool`, `title`, `command`, `parameters`, `why`, `result` and `learning` (a 1–2 sentence takeaway), with Agree / Question / Change / Skip buttons and a note.
4. **Docs library:** Markdown from `docs/`, `.planning/`, `guides/` and root playbooks, formatted for reading, with a raw view and a full-screen reader.
5. **Snapshots and feedback dock:** sidebar links to snapshots; a bottom dock with counts, **Reset All**, **Copy Single Prompt** and **Save Feedback to Host**.

It uses the Fern & Stone theme from `interactive-html-brief`: it follows the system's dark mode, has a toggle, loads nothing from CDNs, and is at most 1360px wide. After editing the HTML template, check the inline script with `node --check`.

Use the `wrap-up` skill to turn recurring lessons from the log into lasting rules.

## The hub server

One background service per machine serves every registered project on `127.0.0.1:8765`: the Projects Index at `/` and each project at `/p/<slug>/`. It is `agent-hub` under `systemd --user` on Linux and `local.agent-hub` under `launchd` on macOS.

Set up once per machine. Re-run the first command after `git pull`; it restarts the service on the new code.

```sh
bash "$HUB_SKILL/scripts/setup-hub-server.sh"
tailscale serve --bg --https=8445 http://127.0.0.1:8765   # private HTTPS from your devices; on Linux, with sudo
```

- Share the Tailscale URL, never a `file://` path, and never bind the server to `0.0.0.0`.
- Feedback saved from a project's page is written only into that project's `.scratch/`.
- The project list, `~/.config/agent-hub/projects.json`, belongs to this machine; never commit it.
- For a one-off server for a single repo without the project list, pick a free port (`ss -ltn` on Linux, `lsof -nP -iTCP -sTCP:LISTEN` on macOS) and run `python3 "$HUB_SKILL/scripts/hub_server.py" --host 127.0.0.1 --port <port>`.

## Restart, check and fix

```sh
# Restart (only needed after server code changes; rebuilt hubs just need a browser refresh)
systemctl --user restart agent-hub                         # Linux
launchctl kickstart -k "gui/$(id -u)/local.agent-hub"      # macOS

# Check
curl -s http://127.0.0.1:8765/api/projects                 # registered projects; "outdated": true needs a rebuild
systemctl --user status agent-hub --no-pager               # Linux: running? since when?
journalctl --user -u agent-hub --since today | grep -E ' 404 | 500 |Traceback'   # Linux log
tail -n 50 ~/Library/Logs/agent-hub*.log                   # macOS log
```

| Symptom | Cause | Fix |
| --- | --- | --- |
| A project card says **Outdated build**, or its overview loads but phase links, the log or snapshots show an error page | The hub was built by an old or project-local copy of `build_hub.py`. The server log shows requests like `GET /api/log 404` without `/p/<slug>/`. | In that repo, rename the local copy (e.g. to `.scratch/build_hub.py.retired`) and run `build-project-hub --register` |
| A rebuild doesn't show up | Browser cache, or the project is registered from a different folder | Hard-refresh. Check its `root` in `/api/projects`; if wrong, run `build-project-hub --register` from the right folder |
| New server features are missing after `git pull` | The service still runs the code it started with | Re-run `setup-hub-server.sh`, or restart |
| A project is missing from the index | It was never registered, or was removed | Run `build-project-hub --register` in that repo |
| Works on this machine but not from other devices | The `tailscale serve` mapping is missing | Run `tailscale serve status`; if port 8445 isn't listed, re-add it (command above) |
