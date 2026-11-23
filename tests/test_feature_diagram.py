import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
RENDERER = KIT / "skills" / "feature-diagram" / "scripts" / "render_diagram.py"
BRIEF_SKILL = KIT / "skills" / "interactive-html-brief" / "SKILL.md"
BRIEF_SERVER = KIT / "skills" / "interactive-html-brief" / "scripts" / "agent-briefs-server"

sys.path.insert(0, str(RENDERER.parent))
import render_diagram  # noqa: E402


def sample_spec(threshold: float = 0.75, cap_mb: int = 12) -> dict:
    return {
        "slug": "ingest-pipeline",
        "short": "Ingest pipeline",
        "project": "Demo App",
        "kicker": "Ingest · since 2026-01",
        "title": "From upload to indexed record in three stages",
        "lede": "Uploads fan out to parallel checks, pass a gate, then publish atomically.",
        "kpis": [("3", "stages"), (f"{cap_mb} MB", "cap"), (f"{threshold:.2f}", "gate")],
        "phases": [("Validate · local", 2, False), ("Publish · atomic", 2, True)],
        "columns": [
            {
                "name": "Input",
                "sub": "1 file",
                "width": ".95fr",
                "nodes": [
                    {
                        "id": "upload",
                        "tag": "Start",
                        "title": "Incoming payload",
                        "body": "Reads `payload.json` before any write.",
                        "chips": ["JSON", "gzip"],
                    }
                ],
            },
            {
                "name": "Checks",
                "sub": "2 in parallel",
                "width": "1.15fr",
                "nodes": [
                    {
                        "tag": "Parallel guards",
                        "tray": [
                            {"id": "size", "title": "Size guard", "badge": f"{cap_mb} MB", "body": "rejects oversize"},
                            {"id": "schema", "title": "Schema", "body": "validates fields"},
                        ],
                    }
                ],
            },
            {
                "name": "Gate",
                "sub": "decision",
                "width": "1.2fr",
                "nodes": [
                    {
                        "id": "gate",
                        "kind": "key",
                        "tag": "Key stage",
                        "title": "Quality gate",
                        "body": f"Score must be >= **{threshold:.2f}**.",
                        "rows": [("Threshold", f"{threshold:.2f}"), ("Retries", "2")],
                        "foot": ("`gate.py`", "deterministic"),
                    },
                    {
                        "id": "reject",
                        "kind": "fail",
                        "tag": "On failure",
                        "title": "Reject",
                        "body": "Keeps previous data intact.",
                    },
                ],
            },
            {
                "name": "Output",
                "sub": "result",
                "width": ".95fr",
                "nodes": [
                    {
                        "id": "out",
                        "kind": "out",
                        "tag": "Output",
                        "title": "Published index",
                        "body": "Atomic swap.",
                        "items": ["Versioned snapshot", "Audit row"],
                    },
                    {
                        "id": "fallback",
                        "kind": "dashed",
                        "tag": "Fallback",
                        "title": "Cached copy",
                        "body": "Served if rebuild is skipped.",
                    },
                ],
            },
        ],
        "edges": [
            ("upload", "size", "solid"),
            ("upload", "schema", "solid"),
            ("size", "gate", "dash"),
            ("schema", "gate", "dash"),
            ("gate", "out", "solid", "accent"),
            ("gate", "reject", "dash", "fail"),
            ("reject", "fallback", "dash"),
        ],
        "panels": [
            {
                "kicker": "Before -> after",
                "title": "Measured change",
                "table": [
                    ("", "Before", "Now"),
                    ("Bad writes", "4 / 100", ("0 / 100", "better")),
                    ("Latency", "1.2 s", ("1.4 s", "worse")),
                ],
                "note": "Read from benchmark output.",
            },
            {
                "kicker": "Why it works",
                "title": "Design notes",
                "list": ["**Atomic.** Half-written files are never visible."],
            },
        ],
        "sources": "`gate.py` and `config.py`",
        "flow": "upload -> 2 checks -> gate -> index",
    }


class FeatureDiagramTests(unittest.TestCase):
    def test_theme_tokens_match_interactive_html_brief(self):
        tokens = render_diagram.load_theme_tokens()
        brief_md = BRIEF_SKILL.read_text(encoding="utf-8").lower()
        server_src = BRIEF_SERVER.read_text(encoding="utf-8").lower()
        for mode in ("light", "dark"):
            for key, hex_val in tokens[mode].items():
                self.assertRegex(hex_val, r"^#[0-9a-f]{6}$", f"{mode}.{key}")
                self.assertIn(hex_val, brief_md, f"{mode}.{key}={hex_val} missing from interactive-html-brief/SKILL.md")
        # Core canvas and fern accent also match agent-briefs-server
        for val in (tokens["light"]["bg"], tokens["light"]["fern"], tokens["dark"]["bg"], tokens["dark"]["fern"]):
            self.assertIn(val, server_src)

    def test_render_self_contained_byte_stable_and_valid_js(self):
        spec = sample_spec(threshold=0.83, cap_mb=16)
        html1 = render_diagram.render(spec)
        html2 = render_diagram.render(spec)
        self.assertEqual(html1, html2)
        self.assertIn("0.83", html1)
        self.assertIn("16 MB", html1)
        self.assertIn('<td class="better">0 / 100</td>', html1)
        self.assertIn('<td class="worse">1.4 s</td>', html1)
        self.assertIn('data-brief-chrome="1"', html1)
        self.assertIn("agent-briefs-theme", html1)
        self.assertIn("prefers-color-scheme:dark", html1)
        self.assertIn("default-src 'none'", html1)
        self.assertIn("@media (max-width:1000px)", html1)
        self.assertIsNone(re.search(r'(src|href)="https?:', html1))

        # Validate inline JS syntax for both standalone and embed modes
        embed = render_diagram.render_embed(spec)
        self.assertIn('class="fd-embed"', embed)
        self.assertIsNone(re.search(r'(src|href)="https?:', embed))
        for label, doc in (("standalone", html1), ("embed", embed)):
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", doc, re.S)
            self.assertTrue(scripts, f"missing script in {label}")
            for js in scripts:
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                    f.write(js)
                    js_path = f.name
                try:
                    r = subprocess.run(["node", "--check", js_path], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, f"{label} JS syntax error: {r.stderr}")
                finally:
                    os.unlink(js_path)

    def test_unknown_edge_raises_value_error(self):
        spec = sample_spec()
        spec["edges"].append(("upload", "missing-node", "solid"))
        with self.assertRaises(ValueError):
            render_diagram.render(spec)

    def test_cli_python_and_json_sources_and_embed_flag(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])

        # JSON source
        json_src = tmp / "specs.json"
        json_src.write_text(json.dumps([sample_spec()]), encoding="utf-8")
        out_dir = tmp / "out"
        r = subprocess.run(
            [sys.executable, str(RENDERER), str(json_src), "--out", str(out_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("ingest-pipeline.html", r.stdout)
        self.assertTrue((out_dir / "ingest-pipeline.html").is_file())
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("(ingest-pipeline.html)", readme)

        # --embed-slug flag
        emb = subprocess.run(
            [sys.executable, str(RENDERER), str(json_src), "--embed-slug", "ingest-pipeline"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn('class="fd-embed"', emb.stdout)
        self.assertIn("fdDrawAll", emb.stdout)

    def test_template_make_diagram_missing_skill_and_happy_path(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        proj = tmp / "proj"
        subprocess.run(["bash", str(KIT / "install.sh"), str(proj), "Demo"], check=True, capture_output=True)

        # 1. Missing linked skill fails with clear message naming install.sh --link-skills
        empty_home = tmp / "empty-home"
        empty_home.mkdir()
        env_missing = {**os.environ, "HOME": str(empty_home)}
        env_missing.pop("AGENT_KIT_DIAGRAM_SKILL", None)
        fail = subprocess.run(["make", "diagram"], cwd=proj, env=env_missing, capture_output=True, text=True)
        self.assertNotEqual(fail.returncode, 0)
        self.assertIn("install.sh --link-skills", fail.stderr)

        # 2. With linked skill + scripts/diagrams.py, make diagram writes docs/diagrams/*
        fake_home = tmp / "home"
        (fake_home / ".agents" / "skills").mkdir(parents=True)
        subprocess.run(
            ["bash", str(KIT / "install.sh"), "--link-skills"],
            env={**os.environ, "HOME": str(fake_home)},
            check=True,
            capture_output=True,
        )
        (proj / "scripts" / "diagrams.py").write_text(
            "SPECS = [\n"
            f"    {sample_spec()!r}\n"
            "]\n",
            encoding="utf-8",
        )
        ok = subprocess.run(
            ["make", "diagram"],
            cwd=proj,
            env={**os.environ, "HOME": str(fake_home)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr + ok.stdout)
        self.assertTrue((proj / "docs" / "diagrams" / "ingest-pipeline.html").is_file())
        self.assertTrue((proj / "docs" / "diagrams" / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
