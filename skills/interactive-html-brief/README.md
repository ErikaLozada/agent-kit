# Enabling `interactive-html-brief` (Linux & macOS)

This skill lets any AI coding agent (Claude Code, Codex, Antigravity/Gemini, pi, OpenCode, Hermes) turn long reviews, plans, or audits into clean, light-mode interactive HTML pages you can annotate from a laptop, tablet, or phone over Tailscale HTTPS and copy back as a single prompt.

No private hostnames, tailnet IDs, or IPs are stored in this repository. Each machine detects its own Tailscale DNS name locally into `~/.config/agent-briefs/config` (`chmod 600`).

## 1. Link the skill across your installed harnesses

Run once per machine (and again after `git pull`):

```sh
bash /path/to/agent-kit/install.sh --link-skills
```

This symlinks `skills/interactive-html-brief` into every existing global skills directory (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`, `~/.gemini/config/skills`, `~/.pi/agent/skills`, `~/.hermes/skills`) without overwriting anything you already have.

## 2. Add the global preference rule (optional, recommended)

Add these 3 lines to the global instruction file of each harness you use (for example `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.pi/agent/AGENTS.md`, `~/.config/opencode/AGENTS.md`, or `~/.gemini/config/GEMINI.md`):

```markdown
## Large Text Output Format (HTML Briefs)
- Whenever presenting a large chunk of structured text (reviews, plans, architecture proposals, audits, multi-option comparisons — roughly >15–20 lines or 3+ sections), do not dump a long markdown wall of text in chat.
- Follow the `interactive-html-brief` skill: save a self-contained, light-mode interactive HTML brief to `~/agent-briefs/YYYY-MM-DD-<slug>.html` (or save to scratch and run `publish-brief <file>`), and reply with a short 2–4 line summary plus the clickable URL printed by `publish-brief`.
```

## 3. Start the hardened local briefs server

Run once per machine (works on both Linux `systemd --user` and macOS `launchd`):

```sh
bash /path/to/agent-kit/skills/interactive-html-brief/scripts/setup-briefs-server.sh
```

What it sets up:
- Creates `~/agent-briefs/` and `~/agent-briefs/archive/` (`0700`).
- Links `agent-briefs-server` and `publish-brief` into `~/.local/bin/` (ensure `~/.local/bin` is on your `PATH`).
- Writes `~/.config/agent-briefs/config` (`0600`) with this machine's `BASE_URL` (auto-detected from `tailscale status --json`, or pass `--host <machine>.<tailnet>.ts.net`).
- Starts the background service bound strictly to `127.0.0.1:8766` (never LAN/Wi-Fi).

## 4. Expose privately over Tailscale HTTPS

Run once per machine so your tablet, phone, or other laptop can open briefs over valid HTTPS (required for one-tap clipboard copy on iPadOS/iOS):

- **Linux:**
  ```sh
  sudo tailscale serve --bg --https=8444 http://127.0.0.1:8766
  ```
- **macOS:**
  ```sh
  tailscale serve --bg --https=8444 http://127.0.0.1:8766
  ```

Bookmark `https://<your-machine>.<your-tailnet>.ts.net:8444/` on your devices. The index page lists all active briefs newest-first and provides one-tap **Archive**, **Restore**, **Delete**, and **Empty Archive** controls.

## 5. Security model & checklist

- **Strict Tailscale isolation:** The server is an inbound-only loopback listener (`127.0.0.1:8766`). Keep each machine's `~/agent-briefs/` local — do not sync it across machines with different trust levels.
- **Tailscale ACLs:** In your Tailscale Admin Console, allow only your client devices to reach port `8444` on the host, keep Funnel disabled, and keep any one-way isolation tags intact.
- **Prevent agents from reconfiguring Tailscale:** On Linux, clear any Tailscale operator user so agents cannot run `tailscale serve` or `tailscale funnel` without `sudo`:
  ```sh
  sudo tailscale set --operator=
  ```
- **Built-in server hardening:**
  - Brief pages are served with a strict `Content-Security-Policy` (`connect-src 'none'; form-action 'none'; frame-ancestors 'none'`) so agent-written JS cannot call `/api/*` or probe local networks while `localStorage` and clipboard copy still work.
  - `Host` allowlist prevents DNS rebinding; `POST /api/*` requires `Content-Type: application/json` plus same-origin `Sec-Fetch-Site` and `Origin`.
  - Files are opened with `O_NOFOLLOW`, symlinks are ignored, filenames are validated with `fullmatch`, overwrites on archive/restore return `409 Conflict`, and `publish-brief` accepts only `.html`/`.htm` files (`0600`).
  - On Linux, the `systemd --user` unit runs `python3 -I` with `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths=%h/agent-briefs`, and `MemoryMax=128M`.

## 6. Staying in sync across machines (Linux & macOS)

Whenever you improve the server, CLI, or skill on one machine:

```sh
git pull
bash install.sh --link-skills
bash skills/interactive-html-brief/scripts/setup-briefs-server.sh
```
