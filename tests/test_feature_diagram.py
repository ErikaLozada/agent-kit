import json
import os
import re
import shutil
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
    def test_skills_call_the_renderer_from_their_own_folder(self):
        """A fixed ~/.agents/skills path fails on machines without that folder (e.g. Claude Code only)."""
        for rel in ("skills/feature-diagram/SKILL.md", "skills/interactive-html-brief/SKILL.md"):
            self.assertNotIn("~/.agents/skills/feature-diagram", (KIT / rel).read_text(encoding="utf-8"), rel)

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

    @unittest.skipUnless(shutil.which("node"), "node runs the wire-drawing script")
    def test_wires_enter_the_middle_of_one_arrowhead_per_target(self):
        # a and b (in a tray) both point at z, far above/below it; z points at b to check the tray edge
        harness = render_diagram.DRAW_JS + """
        var rects={a:[0,0,100,20],b:[10,200,90,220],tray:[0,180,100,230],z:[160,100,260,120],w:[160,140,260,160],q:[-200,0,-100,20]};
        function rect(k){var r=rects[k];return{left:r[0],top:r[1],right:r[2],bottom:r[3],width:r[2]-r[0],height:r[3]-r[1]};}
        function node(k){return{getBoundingClientRect:function(){return rect(k);},
          closest:function(){return k==='b'?{getBoundingClientRect:function(){return rect('tray');}}:null;}};}
        var svg={innerHTML:'',setAttribute:function(){}};
        global.document={documentElement:{}};
        global.getComputedStyle=function(){return{display:'block',getPropertyValue:function(){return'';}};};
        rects.stage=[0,0,400,300];
        var stage={dataset:{prefix:'p-',edges:JSON.stringify([['a','z','solid','accent'],['b','z','dash'],['q','b','solid'],['z','w','dash','fail']])},
          getBoundingClientRect:function(){return rect('stage');},
          querySelector:function(s){if(s==='svg.fd-wires')return svg;return node(s.match(/"(.*)"/)[1]);}};
        fdDrawStage(stage);console.log(svg.innerHTML);
        """
        out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout
        heads = re.findall(r'<path class="fd-head" d="M([-\d.]+),([-\d.]+) L([-\d.]+),([-\d.]+) L([-\d.]+),([-\d.]+)z" fill="([^"]+)"', out)
        self.assertEqual(len(heads), 3, "one head per target")
        by_tip = {float(h[2]): h for h in heads}
        z_head, b_head = by_tip[159.0], by_tip[-1.0]  # 1 px before the card, and before the tray's edge (not the card inside it)
        for head, middle in ((z_head, 110.0), (b_head, 210.0)):
            self.assertEqual((float(head[1]) + float(head[5])) / 2, middle)
            self.assertEqual(float(head[3]), middle)
        self.assertEqual(z_head[6], "#1d6a44", "the strongest tone reaching a target colours its head")
        # a wire to a card below in the same column drops straight down from the middle of the one above
        w_head = by_tip[210.0]
        self.assertEqual((float(w_head[0]) + float(w_head[4])) / 2, 210.0)
        self.assertEqual(float(w_head[3]), 139.0)
        self.assertIn('d="M210,120 L210,131"', out)
        # every wire finishes with a solid, level run at the head's middle
        runs = re.findall(r'<path class="fd-lead" d="M([-\d.]+),([-\d.]+) L([-\d.]+),([-\d.]+)"([^>]*)>', out)
        self.assertEqual(len(runs), 3)
        for x1, y1, x2, y2, rest in runs:
            self.assertEqual(y1, y2)
            self.assertIn(float(y1), (110.0, 210.0))
            self.assertGreater(float(x2), float(x1))
            self.assertNotIn("dasharray", rest)

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
