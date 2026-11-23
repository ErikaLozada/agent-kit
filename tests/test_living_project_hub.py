"""Tests for the unified living-project-hub server's detection of hubs built outside the shared builder."""
import http.client, json, os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HUB_SERVER = KIT / "skills" / "living-project-hub" / "scripts" / "hub_server.py"


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


if __name__ == "__main__":
    unittest.main()
