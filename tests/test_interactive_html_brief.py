"""Tests for skills/interactive-html-brief server, CLI, hardening, and privacy hygiene."""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
SKILL_DIR = KIT / "skills" / "interactive-html-brief"
SERVER_SCRIPT = SKILL_DIR / "scripts" / "agent-briefs-server"
PUBLISH_SCRIPT = SKILL_DIR / "scripts" / "publish-brief"
BUILD_SCRIPT = SKILL_DIR / "scripts" / "build_brief.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class InteractiveHtmlBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.briefs_dir = self.root / "agent-briefs"
        self.config_file = self.root / "config"
        self.port = free_port()
        self.remote_host = "example-host.example-tailnet.ts.net:8444"
        self.config_file.write_text(f"BASE_URL=https://{self.remote_host}\n", encoding="utf-8")
        self.env = {
            **os.environ,
            "AGENT_BRIEFS_DIR": str(self.briefs_dir),
            "AGENT_BRIEFS_CONFIG": str(self.config_file),
        }
        self.env.pop("AGENT_BRIEFS_URL", None)

        self.proc = subprocess.Popen(
            [sys.executable, "-I", str(SERVER_SCRIPT), "--host", "127.0.0.1", "--port", str(self.port)],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(self._stop_server)

        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                status, _, _ = self.request("GET", "/health")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("agent-briefs-server failed to start in time")

    def _stop_server(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def request(self, method: str, path: str, headers: dict | None = None, body: str | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            hdrs = dict(headers or {})
            conn.request(method, path, body=body, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, dict(resp.getheaders()), data
        finally:
            conn.close()

    def test_publish_cli_and_security_controls(self):
        # 1. publish-brief rejects non-HTML files
        bad = self.root / "secret.txt"
        bad.write_text("not html", encoding="utf-8")
        r = subprocess.run([sys.executable, str(PUBLISH_SCRIPT), str(bad)], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only .html/.htm", r.stderr)

        # 2. publish-brief publishes valid HTML with 0600 permissions & config BASE_URL
        src = self.root / "review.html"
        src.write_text("<!doctype html><title>Sample Review</title><p>Hello</p>", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(PUBLISH_SCRIPT), str(src), "my..weird..slug"],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        url = r.stdout.strip()
        self.assertTrue(url.startswith(f"https://{self.remote_host}/"))
        filename = url.rsplit("/", 1)[-1]
        self.assertNotIn("..", filename)
        published = self.briefs_dir / filename
        self.assertTrue(published.is_file())
        self.assertEqual(stat.S_IMODE(published.stat().st_mode), 0o600)

        # 3. Symlinks placed inside briefs_dir are ignored in listing and blocked on GET
        outside = self.root / "outside.html"
        outside.write_text("<title>Outside</title>", encoding="utf-8")
        os.symlink(outside, self.briefs_dir / "escape.html")

        status, hdrs, body = self.request("GET", "/api/briefs")
        self.assertEqual(status, 200)
        listing = json.loads(body)
        self.assertEqual([item["file"] for item in listing["active"]], [filename])
        self.assertEqual(listing["active"][0]["title"], "Sample Review")

        status, _, _ = self.request("GET", "/escape.html")
        self.assertEqual(status, 404)

        # 4. Path traversal & dotfiles blocked
        for bad_path in ("/..%2f..%2fetc%2fpasswd", "/.hidden.html", "/notes.txt"):
            status, _, _ = self.request("GET", bad_path)
            self.assertEqual(status, 404, bad_path)

        # 5. CSP headers on index vs brief
        status, idx_hdrs, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("connect-src 'self'", idx_hdrs["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", idx_hdrs["Content-Security-Policy"])

        status, brief_hdrs, brief_body = self.request("GET", f"/{filename}")
        self.assertEqual(status, 200)
        self.assertIn("connect-src 'none'", brief_hdrs["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", brief_hdrs["Content-Security-Policy"])
        self.assertIn(b'href="/"', brief_body)
        self.assertIn(b"abChromeThemeBtn", brief_body)
        self.assertIn(b"prefers-color-scheme:dark", brief_body)
        self.assertIn(b'data-theme="dark"', brief_body)

        # Native brief with its own topbar (data-brief-chrome="1") is not double-wrapped
        native = self.root / "native.html"
        native.write_text('<!doctype html><html><head><title>Native</title></head><body><header data-brief-chrome="1"><a href="/">Back</a></header></body></html>', encoding="utf-8")
        r2 = subprocess.run([sys.executable, str(PUBLISH_SCRIPT), str(native), "native-brief"], env=self.env, capture_output=True, text=True, check=True)
        native_name = r2.stdout.strip().rsplit("/", 1)[-1]
        status, _, native_body = self.request("GET", f"/{native_name}")
        self.assertEqual(status, 200)
        self.assertNotIn(b"abChromeThemeBtn", native_body)

        # 6. Host allowlist accepts configured Tailscale host and rejects foreign hosts (DNS rebinding)
        status, _, _ = self.request("GET", "/health", headers={"Host": self.remote_host})
        self.assertEqual(status, 200)
        status, _, _ = self.request("GET", "/health", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 421)

        # 7. CSRF defenses on POST
        status, _, _ = self.request("POST", "/api/clear-archive", headers={"Content-Type": "text/plain"}, body="{}")
        self.assertEqual(status, 415)
        status, _, _ = self.request(
            "POST",
            "/api/clear-archive",
            headers={"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"},
            body="{}",
        )
        self.assertEqual(status, 403)
        status, _, _ = self.request(
            "POST",
            "/api/clear-archive",
            headers={"Content-Type": "application/json", "Origin": "https://evil.example.com"},
            body="{}",
        )
        self.assertEqual(status, 403)

        # 8. Valid archive -> conflict on duplicate -> restore -> delete
        valid_headers = {
            "Content-Type": "application/json",
            "Sec-Fetch-Site": "same-origin",
            "Origin": f"http://127.0.0.1:{self.port}",
        }
        status, _, _ = self.request("POST", "/api/archive", headers=valid_headers, body=json.dumps({"file": filename}))
        self.assertEqual(status, 200)

        # Recreate same filename in active and verify archive refuses silent overwrite (409)
        (self.briefs_dir / filename).write_text("<title>Dup</title>", encoding="utf-8")
        status, _, _ = self.request("POST", "/api/archive", headers=valid_headers, body=json.dumps({"file": filename}))
        self.assertEqual(status, 409)

        # Delete active copy, then restore archived copy, then delete
        status, _, _ = self.request(
            "POST", "/api/delete", headers=valid_headers, body=json.dumps({"file": filename, "scope": "active"})
        )
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", "/api/restore", headers=valid_headers, body=json.dumps({"file": filename}))
        self.assertEqual(status, 200)
        self.assertTrue((self.briefs_dir / filename).is_file())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory permissions")
    def test_unwritable_briefs_folder_explains_recovery(self):
        # Moving ~/agent-briefs while the systemd unit runs leaves the server with a read-only view;
        # it must say what happened and how to recover instead of failing with a traceback.
        self.briefs_dir.chmod(0o500)
        self.addCleanup(self.briefs_dir.chmod, 0o700)
        for path in ("/api/briefs", "/health"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 503, path)
            error = json.loads(body)["error"]
            self.assertIn("moved, renamed or replaced", error)
            self.assertIn("systemctl --user restart agent-briefs", error)
            self.assertIn("launchctl kickstart -k", error)

    def test_setup_script_restarts_running_service(self):
        # `enable --now` does not restart a running unit, so re-running setup used to keep stale code and folders.
        text = (SKILL_DIR / "scripts" / "setup-briefs-server.sh").read_text(encoding="utf-8")
        self.assertIn("systemctl --user restart agent-briefs.service", text)

    def test_no_sensitive_hostnames_or_ips_in_skill(self):
        """Guard against committing real tailnet domains, Tailscale CGNAT IPs, or personal paths."""
        ts_ip_re = re.compile(r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")
        personal_re = re.compile(r"/home/[a-z0-9_-]+|/Users/[a-z0-9_-]+|@gmail\.com", re.IGNORECASE)
        real_ts_net_re = re.compile(r"\b[a-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net\b", re.IGNORECASE)

        for path in SKILL_DIR.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertIsNone(ts_ip_re.search(text), f"Tailscale IP leaked in {path}")
            self.assertIsNone(personal_re.search(text), f"Personal path/domain leaked in {path}")
            self.assertIsNone(real_ts_net_re.search(text), f"Real tailnet domain leaked in {path}")

    def test_build_brief_renders_valid_html_and_publishes(self):
        sample = {
            "title": "Architecture Review · Auth",
            "subtitle": "Review of session storage and token rotation.",
            "storageKey": "brief-auth-test",
            "meta": ["2026-11-24", "1 point", "1 decision"],
            "footer": "Generated in test.",
            "sections": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "lede": "Summary metrics and comparison.",
                    "blocks": [
                        {"type": "prose", "paragraphs": ["First paragraph."]},
                        {"type": "list", "ordered": True, "items": ["Step 1", "Step 2"]},
                        {"type": "kpis", "items": [{"label": "Endpoints", "value": 12, "unit": "routes"}]},
                        {
                            "type": "table",
                            "columns": [{"label": "Store"}, {"label": "Latency ms", "num": True}],
                            "rows": [["Redis", 2], ["Postgres", 14]],
                        },
                        {"type": "callout", "label": "Takeaway", "text": "Rotate refresh tokens.", "tone": "good"},
                        {"type": "diagram", "html": '<div class="fd-embed">diagram</div>'},
                    ],
                    "cards": [
                        {
                            "id": "c-ttl",
                            "title": "Shorten refresh token TTL",
                            "category": "Security",
                            "tone": "warn",
                            "body": "Tokens currently live 90 days.",
                            "bullets": ["Cap at 14 days", "Rotate on use"],
                            "code": "if (ttl > 14) { rotate(); }",
                            "callout": {"label": "Fix", "text": "Update config.", "tone": "good"},
                        }
                    ],
                    "decisions": [
                        {
                            "id": "d-store",
                            "title": "Session store",
                            "body": "Pick the backing store.",
                            "options": [
                                {"value": "redis", "label": "Redis", "desc": "Fast revocation", "recommended": True},
                                {"value": "pg", "label": "Postgres", "desc": "Fewer services"},
                            ],
                        }
                    ],
                }
            ],
        }
        src = self.root / "brief.json"
        out = self.root / "brief.html"
        src.write_text(json.dumps(sample), encoding="utf-8")

        r = subprocess.run([sys.executable, "-I", str(BUILD_SCRIPT), str(src), str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = out.read_text(encoding="utf-8")
        for marker in ("__BRIEF_", "/*__"):
            self.assertNotIn(marker, page)
        self.assertIn('data-brief-chrome="1"', page)
        self.assertIn("Shorten refresh token TTL", page)
        self.assertIn('data-filter="security"', page)
        self.assertIn('data-kind="decision"', page)
        self.assertIn("Build &amp; Copy Single Prompt", page)
        self.assertIn("agent-briefs-theme", page)
        self.assertIn("brief-auth-test", page)

        # Validate inline JS syntax with node --check when node is available
        if subprocess.run(["which", "node"], capture_output=True).returncode == 0:
            scripts = re.findall(r"<script>(.*?)</script>", page, flags=re.DOTALL)
            self.assertEqual(len(scripts), 1)
            js_file = self.root / "brief.js"
            js_file.write_text(scripts[0], encoding="utf-8")
            chk = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
            self.assertEqual(chk.returncode, 0, chk.stderr)

        # Build from stdin and --publish directly
        r_pub = subprocess.run(
            [sys.executable, "-I", str(BUILD_SCRIPT), "-", "--publish", "--slug", "stdin-auth"],
            input=json.dumps(sample),
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r_pub.returncode, 0, r_pub.stderr)
        url = r_pub.stdout.strip()
        self.assertTrue(url.startswith(f"https://{self.remote_host}/"))
        pub_name = url.rsplit("/", 1)[-1]
        self.assertTrue(pub_name.endswith("-stdin-auth.html"))
        status, _, served = self.request("GET", f"/{pub_name}")
        self.assertEqual(status, 200)
        self.assertNotIn(b"abChromeThemeBtn", served)

    def test_build_brief_rejects_bad_data_and_escapes_script_close(self):
        bad = {
            "title": "Bad",
            "sections": [
                {
                    "id": "dup",
                    "title": "S1",
                    "blocks": [{"type": "table", "columns": [{"label": "A"}], "rows": [[1, 2]]}],
                    "cards": [{"id": "dup", "title": "C1", "tone": "bogus"}],
                    "decisions": [{"id": "d1", "title": "D1", "options": []}],
                }
            ],
        }
        r = subprocess.run(
            [sys.executable, "-I", str(BUILD_SCRIPT), "-", str(self.root / "bad.html")],
            input=json.dumps(bad),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 1)
        for expected in ("duplicate id 'dup'", "2 cells, 1 columns", "tone must be one of", "'options' must be a non-empty list"):
            self.assertIn(expected, r.stderr)

        tricky = {
            "title": "</script><b>Title",
            "storageKey": "</script>k",
            "sections": [{"id": "s1", "title": "S1", "blocks": [{"type": "prose", "paragraphs": ["ok"]}]}],
        }
        out = self.root / "tricky.html"
        r2 = subprocess.run(
            [sys.executable, "-I", str(BUILD_SCRIPT), "-", str(out)],
            input=json.dumps(tricky),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r2.returncode, 0, r2.stderr)
        page = out.read_text(encoding="utf-8")
        meta_block = page.split('id="brief-meta">', 1)[1].split("</script>", 1)[0]
        self.assertIn("<\\/script>", meta_block)

    def test_skill_md_documents_builder_and_trigger_threshold(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("build_brief.py", text)
        self.assertIn("--publish", text)
        self.assertIn("When to use", text)
        self.assertIn("Reply directly in chat", text)


if __name__ == "__main__":
    unittest.main()
