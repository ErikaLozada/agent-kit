# Agent briefs: machine setup

Agents turn long reviews, plans and audits into HTML pages ("briefs"). A small server on each machine lists them at one address you can open from your laptop, tablet or phone over Tailscale, where you can read, annotate, archive and delete them.

This repository stores nothing machine-specific: each machine keeps its own address in `~/.config/agent-briefs/config`.

## How it fits together

| Piece | What it does |
| --- | --- |
| `~/agent-briefs/` | Holds the briefs (`archive/` inside it holds archived ones). Keep it at this path; don't move or rename it. |
| `publish-brief` | Copies an `.html` file into `~/agent-briefs/` and prints its URL. |
| `agent-briefs` service | Serves that folder on `127.0.0.1:8766`, reachable from this machine only. |
| `tailscale serve` | Makes it reachable from your devices at `https://<machine>.<tailnet>.ts.net:8444/`. |

Briefs are copies. Deleting one in the index removes only the copy in `~/agent-briefs/`; the file it was published from (for example a project's `docs/diagrams/`) is untouched.

## Set up a machine (once)

1. Link the skills into your agent tools:
   ```sh
   bash /path/to/agent-kit/install.sh --link-skills
   ```
2. Install and start the server:
   ```sh
   bash /path/to/agent-kit/skills/interactive-html-brief/scripts/setup-briefs-server.sh
   ```
   This creates `~/agent-briefs/`, links `agent-briefs-server` and `publish-brief` into `~/.local/bin/` (which must be on your `PATH`), saves this machine's URL (detected from Tailscale, or pass `--host <machine>.<tailnet>.ts.net`), and starts the service: `systemd --user` on Linux, `launchd` on macOS. It's safe to re-run at any time.
3. Make it reachable from your devices. HTTPS is also what lets the copy button work on iPad and iPhone.
   ```sh
   sudo tailscale serve --bg --https=8444 http://127.0.0.1:8766   # on macOS, without sudo
   ```
   Bookmark `https://<machine>.<tailnet>.ts.net:8444/`.
4. Optional: tell agents to use briefs. Add this to each tool's global instructions file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.pi/agent/AGENTS.md`, …):
   ```markdown
   ## Long answers as HTML briefs
   - For long structured output (reviews, plans, audits, comparisons; roughly 15+ lines or 3+ sections), follow the `interactive-html-brief` skill instead of writing it in chat.
   - Publish with `publish-brief <file>` and reply with a 2–4 line summary and the URL it prints.
   ```

## Update after `git pull`

```sh
git pull
bash install.sh --link-skills
bash skills/interactive-html-brief/scripts/setup-briefs-server.sh   # restarts the server on the new code
```

## Restart, check and fix

```sh
# Restart
systemctl --user restart agent-briefs                        # Linux
launchctl kickstart -k "gui/$(id -u)/local.agent-briefs"     # macOS

# Check
curl -s http://127.0.0.1:8766/health                         # {"ok": true}, or an error saying what's wrong and how to fix it
systemctl --user status agent-briefs --no-pager              # Linux: running? since when?
journalctl --user -u agent-briefs --since today | grep -E 'Error|Traceback'   # Linux log
tail -n 50 ~/Library/Logs/agent-briefs*.log                  # macOS log
```

| Symptom | Cause | Fix |
| --- | --- | --- |
| Older briefs are missing from the index; only recent ones show | `~/agent-briefs` was moved or renamed while the server ran, and the next publish created a new, empty folder | Find the old folder (`find ~ -maxdepth 3 -type d -name agent-briefs`), move its files back with `mv -n <old>/*.html ~/agent-briefs/`, then restart |
| The index or `/health` says the folder is "missing or read-only" | Same cause: the server lost access to the folder | Put the folder back at `~/agent-briefs`, then restart |
| Nothing changed after re-running setup or pulling new code | Setup scripts from before 2026-11-23 didn't restart a running server | Restart |
| Works on this machine but not from other devices | The `tailscale serve` mapping is missing | Run `tailscale serve status`; if port 8444 isn't listed, re-run step 3 |

## Security

- The server listens on `127.0.0.1` only; Tailscale is the only way in. Keep Funnel off, and in your Tailscale access rules allow only your own devices to reach port 8444.
- On Linux, stop agents from changing Tailscale settings without `sudo`: `sudo tailscale set --operator=`.
- Don't sync `~/agent-briefs/` between machines you trust differently.
- What the server enforces:
  - Briefs run under a strict Content-Security-Policy (`connect-src 'none'; form-action 'none'; frame-ancestors 'none'`). Their scripts can't call the server or reach the network, but saving notes (`localStorage`) and copying still work.
  - Only known host names are answered, which blocks DNS rebinding. Archive, restore and delete requests must be JSON and come from the index page itself.
  - Symlinks are never followed, filenames are strictly checked, archive and restore never overwrite (`409 Conflict`), and `publish-brief` accepts only `.html`/`.htm` files and saves them private (`0600`).
  - On Linux the service runs with `python3 -I`, `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `MemoryMax=128M`, and a read-only home except `~/agent-briefs`. That last rule is why moving the folder cuts off a running server.
