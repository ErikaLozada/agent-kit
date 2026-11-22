#!/usr/bin/env python3
"""
Lightweight stdlib HTTP server for the Living Project & Learning Hub.

Zero external dependencies. Supports two modes:

1. Unified multi-project mode (--multi, recommended):
   One single port & bookmarkable Projects Index for ALL registered projects
   (registered in ~/.config/agent-hub/projects.json via `build_hub.py --register`):
     - GET  /                                -> Fern & Stone Projects Index
     - GET  /api/projects                    -> JSON list of registered projects
     - POST /api/projects/remove             -> unregister a project slug (never touches repo files)
     - GET  /p/<slug>/                       -> serves that project's .scratch/project-hub.html
     - GET  /p/<slug>/api/log|state|snapshots
     - GET  /p/<slug>/snapshots/<name>.html
     - POST /p/<slug>/api/feedback           -> writes that project's .scratch/owner-feedback.md/.json
     - GET  /health                          -> {"ok": true, "mode": "multi"}

2. Single-project mode (default when --multi is not passed):
   Serves one project's git-ignored .scratch/ directory directly at /.

Bind strictly to 127.0.0.1 (exposed privately over Tailscale Serve) or a
Tailscale IPv4 address via --host. Never bind to 0.0.0.0 on untrusted networks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB cap
SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SAFE_HTML_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.html$")


def default_scratch_dir() -> Path:
    here = Path(__file__).resolve().parent
    if here.name == ".scratch":
        return here
    return Path.cwd() / ".scratch"


def default_registry_path() -> Path:
    return Path(os.environ.get("AGENT_HUB_REGISTRY", Path.home() / ".config" / "agent-hub" / "projects.json")).expanduser()


def load_registry(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        projs = raw.get("projects", {}) if isinstance(raw, dict) else {}
        return projs if isinstance(projs, dict) else {}
    except Exception:
        return {}


def save_registry(path: Path, projects: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projects": projects}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_regular_nofollow(path: Path) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        with os.fdopen(fd, "rb") as fh:
            return fh.read()
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
        return None


def git_branch_short(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
    except Exception:
        return ""


def inspect_project(slug: str, meta: dict) -> dict:
    root = Path(str(meta.get("root", ""))).expanduser()
    scratch = root / ".scratch"
    hub_file = scratch / "project-hub.html"
    hub_multi_index = scratch / "hub" / "index.html"
    target = hub_file if hub_file.is_file() else (hub_multi_index if hub_multi_index.is_file() else None)

    log_count = 0
    log_file = scratch / "execution-log.json"
    if log_file.is_file():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                log_count = len(entries)
        except Exception:
            pass

    snap_count = 0
    snap_dir = scratch / "snapshots"
    if snap_dir.is_dir():
        snap_count = sum(1 for p in snap_dir.glob("*.html") if p.is_file() and not p.is_symlink())

    mtime = 0.0
    mtime_human = "Not built yet"
    if target is not None:
        try:
            mtime = target.stat().st_mtime
            mtime_human = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            pass

    return {
        "slug": slug,
        "name": str(meta.get("name") or slug),
        "root": str(root),
        "ready": target is not None,
        "branch": git_branch_short(root) if root.is_dir() else "",
        "log_count": log_count,
        "snapshot_count": snap_count,
        "mtime": mtime,
        "mtime_human": mtime_human,
        "url": f"/p/{quote(slug)}/",
    }


PROJECTS_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Project Hubs</title>
<style>
  /* Fern & Stone · Tidepool (follows system Dark Mode + manual toggle) */
  :root {
    --bg: #f8faf8; --card: #fcfdfc; --muted-bg: #eef2ef;
    --ink: #111a15; --muted: #5b6960; --border: #d6ded8; --input: #77857c;
    --accent: #1d6a44; --accent-hover: #155234; --accent-fg: #ffffff; --accent-soft: #e2efe6;
    --good: #3a64ad; --good-soft: #edf2fa;
    --warn: #9c5520; --warn-soft: #fbf2ea;
    --danger: #b42318; --danger-fg: #ffffff; --danger-soft: #fef2f2;
    --radius-sm: 4px; --radius: 8px;
    --font: "Geist", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0f1411; --card: #151b17; --muted-bg: #1c241f;
      --ink: #e8eeea; --muted: #8a988f; --border: #2a342e; --input: #6e7c73;
      --accent: #6cc08f; --accent-hover: #83cea2; --accent-fg: #0b130e; --accent-soft: #17291f;
      --good: #7fa3e6; --good-soft: #162033;
      --warn: #d88b52; --warn-soft: #2a1d13;
      --danger: #f28b82; --danger-fg: #2a0b09; --danger-soft: #2e1513;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0f1411; --card: #151b17; --muted-bg: #1c241f;
    --ink: #e8eeea; --muted: #8a988f; --border: #2a342e; --input: #6e7c73;
    --accent: #6cc08f; --accent-hover: #83cea2; --accent-fg: #0b130e; --accent-soft: #17291f;
    --good: #7fa3e6; --good-soft: #162033;
    --warn: #d88b52; --warn-soft: #2a1d13;
    --danger: #f28b82; --danger-fg: #2a0b09; --danger-soft: #2e1513;
  }
  * { box-sizing: border-box; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  }
  body { margin: 0; font-family: var(--font); background: var(--bg); color: var(--ink); font-size: 14.5px; line-height: 1.55; -webkit-font-smoothing: antialiased; }
  .topbar { position: sticky; top: 0; z-index: 20; height: 40px; padding: 0 20px; background: var(--bg); border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
  .mark { width: 10px; height: 10px; border-radius: 2px; background: var(--accent); flex: none; }
  .topbar h1 { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: -0.01em; }
  .topbar-sub { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .spacer { flex: 1; }
  .wrap { width: 100%; max-width: 1200px; margin: 0 auto; padding: 20px 20px 72px; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 16px; }
  .search { flex: 1 1 220px; min-height: 40px; padding: 7px 12px; border: 1px solid var(--input); border-radius: var(--radius-sm); background: var(--card); color: var(--ink); font: inherit; font-size: 14px; }
  .btn { border: 1px solid var(--border); background: var(--card); color: var(--ink); font: inherit; font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: var(--radius); cursor: pointer; min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; text-decoration: none; }
  .btn:hover { background: var(--accent-soft); }
  .btn-sm { min-height: 28px; padding: 3px 10px; font-size: 12px; background: transparent; }
  .btn-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  .btn-danger { color: var(--danger); border-color: var(--border); background: var(--card); }
  .btn-danger:hover { background: var(--danger-soft); border-color: var(--danger); }
  .btn-danger.confirming { background: var(--danger); border-color: var(--danger); color: var(--danger-fg); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
  .card-main { flex: 1 1 320px; min-width: 0; text-decoration: none; color: inherit; display: block; }
  .card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .card-title { font-size: 15.5px; font-weight: 600; color: var(--ink); }
  .card-main:hover .card-title { color: var(--accent); }
  .tag { font-size: 12px; font-weight: 600; padding: 1px 7px; border-radius: var(--radius-sm); background: var(--muted-bg); color: var(--muted); }
  .tag-ok { background: var(--good-soft); color: var(--good); }
  .tag-warn { background: var(--warn-soft); color: var(--warn); }
  .card-meta { margin-top: 4px; font-size: 12.5px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 6px 14px; font-variant-numeric: tabular-nums; }
  .mono { font-family: var(--mono); font-size: 12px; }
  .card-actions { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
  .empty { background: var(--card); border: 1px dashed var(--border); border-radius: var(--radius); padding: 36px 20px; text-align: center; color: var(--muted); }
  code { font-family: var(--mono); font-size: 12px; background: var(--muted-bg); padding: 1px 5px; border-radius: var(--radius-sm); border: 1px solid var(--border); }
  .toast { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%) translateY(20px); background: var(--ink); color: var(--bg); padding: 9px 15px; border-radius: var(--radius); font-size: 13px; font-weight: 600; opacity: 0; pointer-events: none; transition: opacity 0.18s, transform 0.18s; }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  @media (max-width: 600px) { .topbar-sub { display: none; } .wrap { padding: 14px; } .card-actions { width: 100%; } .card-actions .btn { flex: 1 1 auto; } }
</style>
</head>
<body>
  <header class="topbar">
    <span class="mark" aria-hidden="true"></span>
    <h1>Living Project Hubs</h1>
    <span class="topbar-sub">All active projects on one bookmarkable port</span>
    <span class="spacer"></span>
    <button class="btn btn-sm" id="themeBtn" type="button">Dark</button>
    <button class="btn btn-sm" id="refreshBtn" type="button">↻ Refresh</button>
  </header>
  <div class="wrap">
    <div class="controls">
      <input class="search" id="searchInput" type="search" placeholder="Filter projects by name, slug, or branch…" autocomplete="off">
    </div>
    <main class="list" id="projectList"></main>
  </div>
  <div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
(() => {
  const themeBtn = document.getElementById("themeBtn");
  const mqDark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function effectiveTheme() {
    const ex = document.documentElement.getAttribute("data-theme");
    if (ex === "dark" || ex === "light") return ex;
    return mqDark && mqDark.matches ? "dark" : "light";
  }
  function syncThemeLabel() { themeBtn.textContent = effectiveTheme() === "dark" ? "Light" : "Dark"; }
  function applyTheme(t, persist) {
    document.documentElement.setAttribute("data-theme", t);
    syncThemeLabel();
    if (persist) { try { localStorage.setItem("project-hub-theme", t); } catch (e) {} }
  }
  try {
    const saved = localStorage.getItem("project-hub-theme");
    if (saved === "dark" || saved === "light") applyTheme(saved, false);
    else syncThemeLabel();
  } catch (e) { syncThemeLabel(); }
  if (mqDark) {
    const onSys = () => { if (!document.documentElement.getAttribute("data-theme")) syncThemeLabel(); };
    if (mqDark.addEventListener) mqDark.addEventListener("change", onSys);
    else if (mqDark.addListener) mqDark.addListener(onSys);
  }
  themeBtn.addEventListener("click", () => applyTheme(effectiveTheme() === "dark" ? "light" : "dark", true));

  let projects = [];
  let query = "";
  let confirmSlug = null;
  let confirmTimer = null;
  const listEl = document.getElementById("projectList");
  const toastEl = document.getElementById("toast");
  let toastTimer = null;

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  async function loadProjects(quiet) {
    try {
      const res = await fetch("/api/projects", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      projects = data.projects || [];
      render();
      if (!quiet) showToast("Refreshed");
    } catch (err) {
      showToast("Failed to load projects: " + err.message);
    }
  }
  function render() {
    const q = query.trim().toLowerCase();
    const filtered = q ? projects.filter(p => (p.name + " " + p.slug + " " + p.branch).toLowerCase().includes(q)) : projects;
    if (!filtered.length) {
      listEl.innerHTML = '<div class="empty">' + (q ? "No projects match your filter." : "No projects registered yet. Run <code>build-project-hub --register</code> inside any project repo.") + "</div>";
      return;
    }
    listEl.innerHTML = filtered.map(p => {
      const confirming = confirmSlug === p.slug;
      const badge = p.ready ? '<span class="tag tag-ok">Ready</span>' : '<span class="tag tag-warn">Not built</span>';
      return '<article class="card">' +
        '<a class="card-main" href="' + esc(p.url) + '">' +
          '<div class="card-head"><span class="card-title">' + esc(p.name) + '</span>' + badge + (p.branch ? '<span class="tag mono">' + esc(p.branch) + '</span>' : '') + '</div>' +
          '<div class="card-meta"><span class="mono">/p/' + esc(p.slug) + '/</span><span>' + esc(p.mtime_human) + '</span><span>' + p.log_count + ' log entries</span><span>' + p.snapshot_count + ' snapshots</span></div>' +
        '</a>' +
        '<div class="card-actions">' +
          '<a class="btn btn-primary" href="' + esc(p.url) + '">Open Hub</a>' +
          '<button class="btn btn-danger' + (confirming ? " confirming" : "") + '" type="button" data-remove="' + esc(p.slug) + '">' + (confirming ? "Confirm Remove?" : "Remove") + '</button>' +
        '</div>' +
      '</article>';
    }).join("");
  }
  document.getElementById("searchInput").addEventListener("input", e => { query = e.target.value; render(); });
  document.getElementById("refreshBtn").addEventListener("click", () => loadProjects(false));
  listEl.addEventListener("click", async e => {
    const btn = e.target.closest("button[data-remove]");
    if (!btn) return;
    const slug = btn.dataset.remove;
    if (confirmSlug !== slug) {
      confirmSlug = slug;
      clearTimeout(confirmTimer);
      confirmTimer = setTimeout(() => { confirmSlug = null; render(); }, 4000);
      render();
      return;
    }
    confirmSlug = null;
    try {
      const res = await fetch("/api/projects/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      await loadProjects(true);
      showToast("Removed " + slug + " from index");
    } catch (err) {
      showToast("Remove failed: " + err.message);
    }
  });
  loadProjects(true);
})();
</script>
</body>
</html>
"""


def make_handler(scratch_dir: Path | None = None, registry_path: Path | None = None, multi: bool = False):
    class HubHandler(BaseHTTPRequestHandler):
        def _send_bytes(self, code: int, content_type: str, data: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, code: int, payload: dict):
            self._send_bytes(code, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def _send_html(self, data: bytes):
            self._send_bytes(200, "text/html; charset=utf-8", data)

        def _read_json_body(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return None
            if length <= 0 or length > MAX_BODY_BYTES:
                self.send_error(413, "Payload too large or empty")
                return None
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
            except Exception:
                self.send_error(400, "Invalid JSON")
                return None

        def _serve_project_get(self, proj_scratch: Path, subpath: str):
            html_file = proj_scratch / "project-hub.html"
            hub_dir = proj_scratch / "hub"
            snapshots_dir = proj_scratch / "snapshots"
            feedback_json = proj_scratch / "owner-feedback.json"
            exec_log_json = proj_scratch / "execution-log.json"

            if subpath in ("/", "/project-hub.html", "/index.html"):
                target = html_file if html_file.is_file() else (hub_dir / "index.html")
                data = read_regular_nofollow(target)
                if data is None:
                    self.send_error(404, "project-hub.html not built yet")
                    return
                self._send_html(data)
                return

            if subpath == "/api/state":
                if feedback_json.is_file():
                    try:
                        self._send_json(200, json.loads(feedback_json.read_text(encoding="utf-8")))
                        return
                    except Exception:
                        pass
                self._send_json(200, {"state": None})
                return

            if subpath == "/api/log":
                if exec_log_json.is_file():
                    try:
                        entries = json.loads(exec_log_json.read_text(encoding="utf-8"))
                        if isinstance(entries, list):
                            self._send_json(200, {"entries": entries})
                            return
                    except Exception:
                        pass
                self._send_json(200, {"entries": []})
                return

            if subpath == "/api/snapshots":
                snaps = []
                if snapshots_dir.is_dir():
                    for p in sorted(snapshots_dir.glob("*.html")):
                        if p.is_file() and not p.is_symlink() and SAFE_HTML_RE.fullmatch(p.name):
                            snaps.append({"name": p.name, "url": f"/snapshots/{p.name}"})
                self._send_json(200, {"snapshots": snaps})
                return

            if subpath.startswith("/snapshots/") and subpath.endswith(".html"):
                fname = unquote(subpath[len("/snapshots/"):])
                if not SAFE_HTML_RE.fullmatch(fname) or "/" in fname or "\\" in fname or ".." in fname:
                    self.send_error(400, "Invalid snapshot name")
                    return
                target = (snapshots_dir / fname).resolve()
                try:
                    target.relative_to(snapshots_dir.resolve())
                except ValueError:
                    self.send_error(400, "Invalid snapshot path")
                    return
                data = read_regular_nofollow(target)
                if data is None:
                    self.send_error(404, "Snapshot not found")
                    return
                self._send_html(data)
                return

            # Optional multi-page hub subpages inside .scratch/hub/<page>.html
            if subpath.startswith("/") and subpath.endswith(".html"):
                fname = unquote(subpath[1:])
                if SAFE_HTML_RE.fullmatch(fname) and hub_dir.is_dir():
                    target = (hub_dir / fname).resolve()
                    try:
                        target.relative_to(hub_dir.resolve())
                    except ValueError:
                        self.send_error(400, "Invalid page path")
                        return
                    data = read_regular_nofollow(target)
                    if data is not None:
                        self._send_html(data)
                        return

            self.send_error(404, "Not found")

        def _serve_project_feedback_post(self, proj_scratch: Path):
            payload = self._read_json_body()
            if payload is None:
                return
            saved_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            markdown = str(payload.get("markdown", "")).strip()
            state = payload.get("state", {})

            proj_scratch.mkdir(parents=True, exist_ok=True)
            (proj_scratch / "owner-feedback.md").write_text(
                f"<!-- Saved from Living Project Hub at {saved_at} -->\n\n{markdown}\n",
                encoding="utf-8",
            )
            (proj_scratch / "owner-feedback.json").write_text(
                json.dumps({"savedAt": saved_at, "round": payload.get("round", ""), "state": state}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._send_json(200, {"ok": True, "savedAt": saved_at, "file": ".scratch/owner-feedback.md"})

        def _resolve_multi_project(self, path: str) -> tuple[str | None, Path | None, str]:
            # Matches /p/<slug> or /p/<slug>/...
            rest = path[len("/p/"):]
            if "/" not in rest:
                slug = unquote(rest)
                return slug, None, ""
            slug_raw, tail = rest.split("/", 1)
            slug = unquote(slug_raw)
            if not SAFE_SLUG_RE.fullmatch(slug):
                return None, None, ""
            projects = load_registry(registry_path)
            meta = projects.get(slug)
            if not meta or not meta.get("root"):
                return None, None, ""
            proj_scratch = Path(str(meta["root"])).expanduser().resolve() / ".scratch"
            return slug, proj_scratch, "/" + tail

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            if path == "/health":
                self._send_json(200, {"ok": True, "mode": "multi" if multi else "single"})
                return

            if not multi:
                self._serve_project_get(scratch_dir, path)
                return

            if path in ("/", "/index.html"):
                self._send_html(PROJECTS_INDEX_HTML.encode("utf-8"))
                return

            if path == "/api/projects":
                projects = load_registry(registry_path)
                items = [inspect_project(slug, meta) for slug, meta in projects.items() if SAFE_SLUG_RE.fullmatch(slug)]
                items.sort(key=lambda item: (item["mtime"], item["name"].lower()), reverse=True)
                self._send_json(200, {"projects": items})
                return

            if path.startswith("/p/"):
                slug, proj_scratch, subpath = self._resolve_multi_project(path)
                if slug and proj_scratch is None and subpath == "":
                    if SAFE_SLUG_RE.fullmatch(slug) and slug in load_registry(registry_path):
                        self.send_response(302)
                        self.send_header("Location", f"/p/{quote(slug)}/")
                        self.end_headers()
                        return
                if proj_scratch is None:
                    self.send_error(404, "Project not registered")
                    return
                self._serve_project_get(proj_scratch, subpath)
                return

            self.send_error(404, "Not found")

        def do_POST(self):
            path = self.path.split("?", 1)[0]

            if not multi:
                if path != "/api/feedback":
                    self.send_error(404, "Not found")
                    return
                self._serve_project_feedback_post(scratch_dir)
                return

            if path == "/api/projects/remove":
                payload = self._read_json_body()
                if payload is None:
                    return
                slug = str(payload.get("slug", "")).strip()
                if not SAFE_SLUG_RE.fullmatch(slug):
                    self.send_error(400, "Invalid project slug")
                    return
                projects = load_registry(registry_path)
                projects.pop(slug, None)
                save_registry(registry_path, projects)
                self._send_json(200, {"ok": True, "removed": slug})
                return

            if path.startswith("/p/"):
                _, proj_scratch, subpath = self._resolve_multi_project(path)
                if proj_scratch is None or subpath != "/api/feedback":
                    self.send_error(404, "Not found")
                    return
                self._serve_project_feedback_post(proj_scratch)
                return

            self.send_error(404, "Not found")

        def log_message(self, fmt, *args):
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {self.address_string()} {fmt % args}", flush=True)

    return HubHandler


def main():
    parser = argparse.ArgumentParser(description="Serve the Living Project & Learning Hub (single-project or unified --multi)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--multi", action="store_true", help="Serve a unified Projects Index for all registered projects on one port")
    parser.add_argument("--registry", default=None, help="Registry JSON path for --multi (default: ~/.config/agent-hub/projects.json)")
    parser.add_argument(
        "--scratch-dir",
        default=None,
        help="Single-project mode: path to the project's .scratch directory (default: ./.scratch)",
    )
    parser.add_argument("--title", default="Project Hub", help="Label for startup log output")
    args = parser.parse_args()

    if args.multi:
        reg_path = Path(args.registry).expanduser() if args.registry else default_registry_path()
        server = ThreadingHTTPServer((args.host, args.port), make_handler(registry_path=reg_path, multi=True))
        print(f"{args.title} (multi-project) listening on http://{args.host}:{args.port}/", flush=True)
        print(f"Registry: {reg_path}", flush=True)
    else:
        scratch_dir = Path(args.scratch_dir).resolve() if args.scratch_dir else default_scratch_dir()
        server = ThreadingHTTPServer((args.host, args.port), make_handler(scratch_dir=scratch_dir, multi=False))
        print(f"{args.title} listening on http://{args.host}:{args.port}/project-hub.html", flush=True)
        print(f"Serving from: {scratch_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
