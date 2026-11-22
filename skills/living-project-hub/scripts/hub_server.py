#!/usr/bin/env python3
"""
Lightweight stdlib HTTP server for the Living Project & Learning Hub.

Zero external dependencies. Serves ONLY the hub HTML, snapshots, and JSON APIs
from a project's git-ignored .scratch/ directory:
  - GET  / or /project-hub.html -> serves .scratch/project-hub.html (no-store)
  - GET  /api/log               -> serves .scratch/execution-log.json
  - GET  /api/state             -> serves .scratch/owner-feedback.json (if any)
  - GET  /api/snapshots         -> lists .scratch/snapshots/*.html
  - GET  /snapshots/<name>.html -> serves a frozen phase snapshot (path-guarded)
  - POST /api/feedback          -> writes .scratch/owner-feedback.md and .json
  - GET  /health                -> returns {"ok": true}

Bind strictly to a Tailscale IPv4 address (recommended for remote access) or
127.0.0.1 via --host. Never bind to 0.0.0.0 on untrusted networks.
"""

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB cap


def default_scratch_dir() -> Path:
    here = Path(__file__).resolve().parent
    if here.name == ".scratch":
        return here
    return Path.cwd() / ".scratch"


def make_handler(scratch_dir: Path):
    html_file = scratch_dir / "project-hub.html"
    snapshots_dir = scratch_dir / "snapshots"
    feedback_md = scratch_dir / "owner-feedback.md"
    feedback_json = scratch_dir / "owner-feedback.json"
    exec_log_json = scratch_dir / "execution-log.json"

    class HubHandler(BaseHTTPRequestHandler):
        def _send_json(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, data: bytes):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            if path in ("/", "/project-hub.html"):
                if not html_file.is_file():
                    self.send_error(404, "project-hub.html not built yet")
                    return
                self._send_html(html_file.read_bytes())
                return

            if path == "/api/state":
                if feedback_json.is_file():
                    try:
                        saved = json.loads(feedback_json.read_text(encoding="utf-8"))
                        self._send_json(200, saved)
                        return
                    except Exception:
                        pass
                self._send_json(200, {"state": None})
                return

            if path == "/api/log":
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

            if path == "/api/snapshots":
                snaps = []
                if snapshots_dir.is_dir():
                    for p in sorted(snapshots_dir.glob("*.html")):
                        snaps.append({"name": p.name, "url": f"/snapshots/{p.name}"})
                self._send_json(200, {"snapshots": snaps})
                return

            if path.startswith("/snapshots/") and path.endswith(".html"):
                fname = path[len("/snapshots/"):]
                if not fname or "/" in fname or "\\" in fname or ".." in fname:
                    self.send_error(400, "Invalid snapshot name")
                    return
                target = (snapshots_dir / fname).resolve()
                try:
                    target.relative_to(snapshots_dir.resolve())
                except ValueError:
                    self.send_error(400, "Invalid snapshot path")
                    return
                if not target.is_file():
                    self.send_error(404, "Snapshot not found")
                    return
                self._send_html(target.read_bytes())
                return

            if path == "/health":
                self._send_json(200, {"ok": True})
                return

            self.send_error(404, "Not found")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/api/feedback":
                self.send_error(404, "Not found")
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400, "Invalid Content-Length")
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                self.send_error(413, "Payload too large or empty")
                return

            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self.send_error(400, "Invalid JSON")
                return

            saved_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            markdown = str(payload.get("markdown", "")).strip()
            state = payload.get("state", {})

            scratch_dir.mkdir(parents=True, exist_ok=True)
            md_doc = f"<!-- Saved from Living Project Hub at {saved_at} -->\n\n{markdown}\n"
            feedback_md.write_text(md_doc, encoding="utf-8")
            feedback_json.write_text(
                json.dumps(
                    {"savedAt": saved_at, "round": payload.get("round", ""), "state": state},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self._send_json(200, {"ok": True, "savedAt": saved_at, "file": ".scratch/owner-feedback.md"})

        def log_message(self, fmt, *args):
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {self.address_string()} {fmt % args}", flush=True)

    return HubHandler


def main():
    parser = argparse.ArgumentParser(description="Serve the Living Project & Learning Hub")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (use Tailscale IPv4 for remote access)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--scratch-dir",
        default=None,
        help="Path to the project's .scratch directory (default: script dir if .scratch, else ./.scratch)",
    )
    parser.add_argument("--title", default="Project Hub", help="Label for startup log output")
    args = parser.parse_args()

    scratch_dir = Path(args.scratch_dir).resolve() if args.scratch_dir else default_scratch_dir()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(scratch_dir))
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
