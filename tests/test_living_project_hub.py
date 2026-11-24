"""Tests for the unified living-project-hub server's detection of hubs built outside the shared builder."""
import http.client, json, os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HUB_SERVER = KIT / "skills" / "living-project-hub" / "scripts" / "hub_server.py"
BUILD_HUB = KIT / "skills" / "living-project-hub" / "scripts" / "build_hub.py"


class OutdatedHubBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        pages = {
            # Shared builder output resolves links against /p/<slug>/ through API_BASE.
            "current": ("project-hub.html", '<script>const API_BASE = "";fetch(API_BASE + "/api/log")</script>'),
            # An old or project-local builder hard-codes root-relative links that 404 under --multi.
            "forked": ("project-hub.html", '<a href="/phase-01.html">Phase 1</a><script>fetch("/api/log")</script>'),
            # The pre-unification multi-page layout (.scratch/hub/index.html only).
            "multipage": ("hub/index.html", '<script>const API_BASE = "";</script>'),
        }
        registry = {"projects": {}}
        for slug, (rel, html) in pages.items():
            page = root / slug / ".scratch" / rel
            page.parent.mkdir(parents=True)
            page.write_text(html, encoding="utf-8")
            registry["projects"][slug] = {"name": slug, "root": str(root / slug)}
        reg_file = root / "projects.json"
        reg_file.write_text(json.dumps(registry), encoding="utf-8")

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]
        proc = subprocess.Popen(
            [sys.executable, "-I", str(HUB_SERVER), "--multi", "--host", "127.0.0.1",
             "--port", str(self.port), "--registry", str(reg_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: (proc.terminate(), proc.wait(timeout=3)))
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                if self.get("/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("hub_server --multi failed to start")

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            c.request("GET", path)
            r = c.getresponse(); return r.status, r.read()
        finally:
            c.close()

    def test_flags_hubs_not_built_by_shared_builder(self):
        status, body = self.get("/api/projects")
        self.assertEqual(status, 200)
        flags = {p["slug"]: p["outdated"] for p in json.loads(body)["projects"]}
        self.assertEqual(flags, {"current": False, "forked": True, "multipage": True})

    def test_index_tells_owner_how_to_fix_outdated_build(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Outdated build: run build-project-hub --register", body)


class BuildHubAppendLogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / "README.md").write_text("# Demo Repo\n\nA sample project.\n", encoding="utf-8")

    def run_builder(self, *args, stdin_text=None):
        return subprocess.run(
            [sys.executable, "-I", str(BUILD_HUB), "--root", str(self.repo), *args],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def test_append_log_json_string_and_stdin_rebuilds_hub(self):
        # 1. Append single object via CLI string (auto-generates id and timestamp)
        entry1 = {"title": "Init repo", "tool": "git", "command": "git init", "result": "ok", "learning": "Keep it clean."}
        r1 = self.run_builder("--append-log", json.dumps(entry1))
        self.assertEqual(r1.returncode, 0, r1.stderr)

        log_file = self.repo / ".scratch" / "execution-log.json"
        hub_file = self.repo / ".scratch" / "project-hub.html"
        self.assertTrue(log_file.is_file())
        self.assertTrue(hub_file.is_file())

        entries = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "step-001")
        self.assertTrue(entries[0]["timestamp"])
        self.assertEqual(entries[0]["title"], "Init repo")
        self.assertIn("Init repo", hub_file.read_text(encoding="utf-8"))

        # 2. Append array of entries via stdin ('-')
        batch = [
            {"id": "custom-2", "title": "Run tests", "tool": "pytest", "result": "pass"},
            {"title": "Deploy", "tool": "make", "result": "live"},
        ]
        r2 = self.run_builder("--append-log", "-", stdin_text=json.dumps(batch))
        self.assertEqual(r2.returncode, 0, r2.stderr)

        entries = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["title"] for e in entries], ["Init repo", "Run tests", "Deploy"])
        self.assertEqual(entries[1]["id"], "custom-2")
        self.assertEqual(entries[2]["id"], "step-003")
        hub_html = hub_file.read_text(encoding="utf-8")
        self.assertIn("Run tests", hub_html)
        self.assertIn("Deploy", hub_html)

    def test_append_log_rejects_invalid_json_without_clobbering(self):
        log_file = self.repo / ".scratch" / "execution-log.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        original = [{"id": "keep-1", "title": "Existing"}]
        log_file.write_text(json.dumps(original), encoding="utf-8")

        for bad in ("{not json", '"just a string"', "[1, 2, 3]"):
            r = self.run_builder("--append-log", bad)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(json.loads(log_file.read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
