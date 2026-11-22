#!/usr/bin/env python3
"""
Reusable generator for the Living Project & Learning Hub.

Zero external dependencies (Python 3 stdlib only; zero external CDN links in
the generated HTML). Auto-discovers any repository's docs/, .planning/, root
playbooks, guides/, .scratch/execution-log.json, and .scratch/snapshots/ to
render a single-file, light-mode interactive HTML hub.

Usage:
    # Build live hub (.scratch/project-hub.html)
    python3 .agents/skills/living-project-hub/scripts/build_hub.py

    # Save a frozen phase snapshot AND update the live hub
    python3 .agents/skills/living-project-hub/scripts/build_hub.py --snapshot phase-01-setup

    # Optional overrides via .scratch/hub-config.json (phases, waves, checkpoint, round_id)
"""

import argparse
import html as html_lib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT_PLAYBOOKS = ["AGENTS.md", "README.md", "CONTRIBUTING.md"]
PRIORITY_DOCS = [
    "docs/requirements.md",
    "docs/architecture.md",
    "docs/decisions.md",
    "docs/scoring.md",
    "docs/status.md",
]
CORE_PLANNING = [
    ".planning/STATE.md",
    ".planning/ROADMAP.md",
    ".planning/REQUIREMENTS.md",
    ".planning/PROJECT.md",
    ".planning/MILESTONES.md",
]
SKIP_DIRS = {".git", ".scratch", "node_modules", ".venv", "__pycache__", "dist", "build"}


def resolve_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).resolve()
    here = Path(__file__).resolve().parent
    if here.name == ".scratch":
        return here.parent
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def get_git_info(root: Path) -> tuple[str, str]:
    branch, sha = "n/a", "n/a"
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or "n/a"
    except Exception:
        pass
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or "n/a"
    except Exception:
        pass
    return branch, sha


def slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return s or "project"


def strip_frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", text)
    if m:
        return m.group(1), text[m.end():]
    return "", text


def extract_title(text: str, fallback: str) -> str:
    _, body = strip_frontmatter(text)
    for line in body.splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            if title:
                return title
    return fallback


def extract_summary(text: str, max_len: int = 210) -> str:
    _, body = strip_frontmatter(text)
    buf: list[str] = []
    in_code = False
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line:
            if buf:
                break
            continue
        if (
            line.startswith("#")
            or line.startswith("|")
            or line.startswith("<!--")
            or line.startswith("<")
            or line.startswith("---")
            or line.startswith(">")
            or re.match(r"^[-*]\s+", line)
            or re.match(r"^\d+\.\s+", line)
        ):
            if buf:
                break
            continue
        buf.append(line)
        if len(" ".join(buf)) >= max_len:
            break
    summary = " ".join(buf)
    summary = re.sub(r"`([^`]+)`", r"\1", summary)
    summary = re.sub(r"\*\*([^*]+)\*\*", r"\1", summary)
    summary = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    if not summary:
        return "Markdown project document."
    if len(summary) > max_len:
        summary = summary[: max_len - 1].rstrip() + "…"
    return summary


def infer_doc_status(rel_path: str, text: str, path: Path) -> tuple[str, str]:
    upper_name = path.name.upper()
    head_sample = text[:800].upper()
    if "SUMMARY" in upper_name:
        return "SUMMARY", "ok"
    if "VERIFICATION" in upper_name or "UAT" in upper_name:
        return "VERIFICATION", "ok"
    if "PLAN" in upper_name:
        return "PLAN", "info"
    if "RESEARCH" in upper_name:
        return "RESEARCH", "info"
    if "CONCERNS" in upper_name:
        return "AUDIT", "warn"
    if "APPROVED" in head_sample and "NOT YET APPROVED" not in head_sample:
        return "APPROVED", "ok"
    if rel_path in ROOT_PLAYBOOKS or rel_path.startswith("guides/"):
        return "PLAYBOOK", "neutral"
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return f"Updated {mtime}", "neutral"


def walk_markdown(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    found: list[Path] = []
    for p in sorted(base.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if p.is_file():
            found.append(p)
    return found


def discover_documents(root: Path) -> list[dict]:
    entries: list[tuple[str, str, Path]] = []
    seen: set[str] = set()

    def add(group: str, p: Path):
        if not p.is_file():
            return
        rel = p.relative_to(root).as_posix()
        if rel in seen:
            return
        seen.add(rel)
        entries.append((group, rel, p))

    # 1. Project docs (priority order first, then any remaining docs/**/*.md)
    for rel in PRIORITY_DOCS:
        add("project_docs", root / rel)
    for p in walk_markdown(root / "docs"):
        add("project_docs", p)

    # 2. Core GSD planning docs
    for rel in CORE_PLANNING:
        add("core", root / rel)

    # 3. Planning phases (plans & summaries vs research) + remaining .planning docs
    for p in walk_markdown(root / ".planning"):
        rel = p.relative_to(root).as_posix()
        if rel in seen:
            continue
        upper = p.name.upper()
        if "/phases/" in f"/{rel}" and any(k in upper for k in ("PLAN", "SUMMARY", "VERIFICATION", "UAT")):
            add("plans", p)
        else:
            add("research", p)

    # 4. Root playbooks & guides (standard + any uppercase root playbook .md files)
    for rel in ROOT_PLAYBOOKS:
        add("playbooks", root / rel)
    for p in sorted(root.glob("*.md")):
        if p.name != "CLAUDE.md" and not p.name.upper().startswith("LICENSE") and p.stem == p.stem.upper():
            add("playbooks", p)
    for p in walk_markdown(root / "guides"):
        add("playbooks", p)

    docs = []
    for group, rel, path in entries:
        content = path.read_text(encoding="utf-8", errors="replace")
        title = extract_title(content, path.stem)
        status, status_kind = infer_doc_status(rel, content, path)
        docs.append(
            {
                "id": "doc-" + slugify(rel),
                "group": group,
                "title": title,
                "rel_path": rel,
                "status": status,
                "status_kind": status_kind,
                "summary": extract_summary(content),
                "line_count": len(content.splitlines()),
                "content": content,
            }
        )
    return docs


def infer_project_identity(root: Path, config: dict) -> tuple[str, str]:
    name = config.get("project_name")
    subtitle = config.get("subtitle")

    for candidate in ("AGENTS.md", ".planning/PROJECT.md", "README.md"):
        p = root / candidate
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not name:
            t = extract_title(text, "")
            if t and t.upper() != "PROJECT NAME":
                name = t
        if not subtitle:
            s = extract_summary(text, max_len=240)
            if s and not s.lower().startswith("one or two sentences:"):
                subtitle = s
        if name and subtitle:
            break

    if not name:
        name = root.name.replace("-", " ").replace("_", " ").title()
    if not subtitle:
        subtitle = "Living Project & Learning Hub — progress tracker, CLI execution log, and formatted project documentation."
    return name, subtitle


def parse_roadmap_phases(root: Path) -> list[dict]:
    roadmap = root / ".planning" / "ROADMAP.md"
    if not roadmap.is_file():
        return []
    text = roadmap.read_text(encoding="utf-8", errors="replace")
    phases: list[dict] = []
    seen_nums: set[str] = set()

    # Pattern 1: - [x] **Phase 1: Name** - description
    for m in re.finditer(
        r"^\s*[-*]\s+\[([ xX])\]\s+\*?\*?Phase\s+(\d+(?:\.\d+)?)\s*[:—-]\s*([^*\n]+)\*?\*?(?:\s*[-—:]\s*(.+))?$",
        text,
        re.MULTILINE,
    ):
        done = m.group(1).lower() == "x"
        num = m.group(2)
        if num in seen_nums:
            continue
        seen_nums.add(num)
        title = m.group(3).strip().rstrip("*")
        desc = (m.group(4) or "").strip()
        phases.append(
            {
                "num": num,
                "name": title,
                "state": "done" if done else "queued",
                "status": "Done" if done else "Queued",
                "deliverables": desc or "See ROADMAP.md for phase details.",
                "reqs": "",
            }
        )

    # Pattern 2 fallback: ## or ### Phase N: Name
    if not phases:
        for m in re.finditer(
            r"^\s*#{2,3}\s+Phase\s+(\d+(?:\.\d+)?)\s*[:—-]\s*(.+)$",
            text,
            re.MULTILINE,
        ):
            num = m.group(1)
            if num in seen_nums:
                continue
            seen_nums.add(num)
            phases.append(
                {
                    "num": num,
                    "name": m.group(2).strip(),
                    "state": "queued",
                    "status": "Planned",
                    "deliverables": "See ROADMAP.md for phase details.",
                    "reqs": "",
                }
            )

    # Mark first non-done phase as current
    for ph in phases:
        if ph["state"] != "done":
            ph["state"] = "current"
            ph["status"] = "Active"
            break
    return phases


def load_json_file(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def discover_snapshots(snapshots_dir: Path) -> list[dict]:
    if not snapshots_dir.is_dir():
        return []
    snaps = []
    for p in sorted(snapshots_dir.glob("*.html")):
        snaps.append({"name": p.name, "label": p.stem.replace("-", " ").title()})
    return snaps


def render_phase_track(phases: list[dict]) -> str:
    if not phases:
        return ""
    pills = []
    for ph in phases:
        st = ph.get("state", "queued")
        cls = "phase-pill"
        if st == "done":
            cls += " done"
        elif st in ("current", "active"):
            cls += " current"
        num = html_lib.escape(str(ph.get("num", "")))
        status = html_lib.escape(str(ph.get("status", "")))
        name = html_lib.escape(str(ph.get("name", "")))
        pills.append(
            f'<div class="{cls}">'
            f'<div class="phase-pill-num"><span>P{num}</span><span>{status}</span></div>'
            f'<div class="phase-pill-name">{name}</div>'
            f"</div>"
        )
    return (
        '<div class="track-label">Project Phases</div>'
        f'<div class="phase-track">{"".join(pills)}</div>'
    )


def render_wave_track(waves: list[dict]) -> str:
    if not waves:
        return ""
    steps = []
    for w in waves:
        st = w.get("state", "queued")
        cls = "wave-step"
        if st == "done":
            cls += " done"
        elif st in ("active", "current"):
            cls += " active"
        label = html_lib.escape(str(w.get("label", "")))
        badge = html_lib.escape(str(w.get("badge", "")))
        desc = html_lib.escape(str(w.get("desc", "")))
        steps.append(
            f'<div class="{cls}">'
            f'<div class="wave-step-top"><span>{label}</span><span>{badge}</span></div>'
            f'<div class="wave-step-desc">{desc}</div>'
            f"</div>"
        )
    return (
        '<div class="track-label">Active Phase Waves</div>'
        f'<div class="wave-track">{"".join(steps)}</div>'
    )


def render_checkpoint_section(checkpoint: dict | None) -> tuple[str, str, str]:
    """Returns (nav_item_html, filter_pill_html, section_html)."""
    if not checkpoint:
        return "", "", ""
    title = html_lib.escape(str(checkpoint.get("title", "Active Human Checkpoint")))
    badge = html_lib.escape(str(checkpoint.get("badge", "ACTION REQUIRED")))
    desc = html_lib.escape(str(checkpoint.get("description", "Complete the checklist and report back below (never paste tokens, PATs, or raw GUIDs).")))

    checks_html = []
    for idx, item in enumerate(checkpoint.get("checklist", []), start=1):
        checks_html.append(
            f'<li><input type="checkbox" data-check="cp_{idx}" />'
            f"<div>{html_lib.escape(str(item))}</div></li>"
        )
    checklist_block = f'<ul class="checklist">{"".join(checks_html)}</ul>' if checks_html else ""

    fields_html = []
    for idx, field in enumerate(checkpoint.get("fields", []), start=1):
        fid = "f-" + slugify(str(field.get("id", f"field-{idx}")))
        flabel = html_lib.escape(str(field.get("label", f"Field {idx}")))
        fph = html_lib.escape(str(field.get("placeholder", "")))
        ftype = field.get("type", "text")
        if ftype == "select" and field.get("options"):
            opts = ['<option value="">-- Select --</option>'] + [
                f'<option value="{html_lib.escape(str(o))}">{html_lib.escape(str(o))}</option>'
                for o in field["options"]
            ]
            ctrl = f'<select class="field-select" id="{fid}" data-form-field="{flabel}">{"".join(opts)}</select>'
        elif ftype == "textarea":
            ctrl = f'<textarea class="note-textarea" id="{fid}" data-form-field="{flabel}" placeholder="{fph}"></textarea>'
        else:
            ctrl = f'<input class="field-input" id="{fid}" data-form-field="{flabel}" placeholder="{fph}" />'
        fields_html.append(
            f'<div class="field-group"><label for="{fid}">{flabel}</label>{ctrl}</div>'
        )
    fields_block = f'<div class="form-grid">{"".join(fields_html)}</div>' if fields_html else ""

    nav_item = (
        '<li><a class="nav-link" href="#sec-checkpoint" data-sec="sec-checkpoint">'
        '<span class="nav-label"><span class="nav-num">!</span><span>Active Checkpoint</span></span>'
        '<span class="nav-count" data-sec-count="sec-checkpoint">0</span></a></li>'
    )
    pill = '<button class="pill" data-filter="action">Active Checkpoint</button>'
    section = f"""
    <section class="section" id="sec-checkpoint">
      <div class="section-head">
        <div>
          <h2 class="section-title"><span class="section-num">!</span> {title}</h2>
          <p class="section-desc">{desc}</p>
        </div>
      </div>
      <div class="card card-action" data-id="active-checkpoint" data-sec="sec-checkpoint" data-cat="action" data-type="form" data-title="{title}">
        <div class="card-top">
          <div class="card-title-wrap">
            <span class="badge badge-warn">{badge}</span>
            <h3 class="card-title">{title}</h3>
          </div>
        </div>
        <div class="card-body">
          {checklist_block}
          {fields_block}
        </div>
      </div>
    </section>
    """
    return nav_item, pill, section


def render_roadmap_section(phases: list[dict]) -> tuple[str, str, str]:
    if not phases:
        return "", "", ""
    rows = []
    for ph in phases:
        st = ph.get("state", "queued")
        badge_cls = "badge-ok" if st == "done" else ("badge-info" if st in ("current", "active") else "badge-neutral")
        num = html_lib.escape(str(ph.get("num", "")))
        name = html_lib.escape(str(ph.get("name", "")))
        status = html_lib.escape(str(ph.get("status", st.title())))
        deliverables = html_lib.escape(str(ph.get("deliverables", "")))
        reqs = html_lib.escape(str(ph.get("reqs", "")))
        reqs_cell = f"<code>{reqs}</code>" if reqs else "—"
        rows.append(
            f"<tr><td><strong>{num}. {name}</strong></td>"
            f'<td><span class="badge {badge_cls}">{status}</span></td>'
            f"<td>{deliverables}</td><td>{reqs_cell}</td></tr>"
        )
    nav_item = (
        '<li><a class="nav-link" href="#sec-roadmap" data-sec="sec-roadmap">'
        '<span class="nav-label"><span class="nav-num">2</span><span>Roadmap</span></span>'
        '<span class="nav-count" data-sec-count="sec-roadmap">0</span></a></li>'
    )
    pill = '<button class="pill" data-filter="roadmap">Roadmap</button>'
    section = f"""
    <section class="section" id="sec-roadmap">
      <div class="section-head">
        <div>
          <h2 class="section-title"><span class="section-num">2</span> Project Roadmap</h2>
          <p class="section-desc">Phases parsed from <code>.planning/ROADMAP.md</code> or <code>.scratch/hub-config.json</code>.</p>
        </div>
      </div>
      <div class="card-stack">
        <article class="card" data-id="rm-summary" data-sec="sec-roadmap" data-cat="roadmap" data-title="Project Delivery Roadmap">
          <div class="card-body">
            <div class="data-table-wrap">
              <table class="data-table">
                <thead><tr><th>Phase</th><th>Status</th><th>Deliverables</th><th>Reqs</th></tr></thead>
                <tbody>{"".join(rows)}</tbody>
              </table>
            </div>
          </div>
          <div class="card-actions" data-card-controls></div>
        </article>
      </div>
    </section>
    """
    return nav_item, pill, section


def render_doc_tabs(docs: list[dict]) -> str:
    group_labels = [
        ("project_docs", "Project Docs"),
        ("core", "Core Planning"),
        ("plans", "Plans & Summaries"),
        ("research", "Research & Audits"),
        ("playbooks", "Playbooks & Guides"),
    ]
    counts: dict[str, int] = {}
    for d in docs:
        counts[d["group"]] = counts.get(d["group"], 0) + 1
    tabs = [f'<button class="doc-tab active" data-doc-group="all">All Documents ({len(docs)})</button>']
    for key, label in group_labels:
        if counts.get(key, 0) > 0:
            tabs.append(
                f'<button class="doc-tab" data-doc-group="{key}">{html_lib.escape(label)} ({counts[key]})</button>'
            )
    return "\n        ".join(tabs)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>__PROJECT_NAME__ — Living Project &amp; Learning Hub</title>
<style>
  /* Fern & Stone · Tidepool tokens (Light default + optional Dark toggle, zero external CDNs) */
  :root {
    --bg: #f8faf8;
    --surface: #fcfdfc;
    --popover: #ffffff;
    --surface-subtle: #eef2ef;
    --surface-tint: #e2efe6;
    --text: #111a15;
    --text-muted: #5b6960;
    --text-soft: #46534b;
    --border: #d6ded8;
    --border-strong: #77857c;

    --accent: #1d6a44;
    --accent-hover: #155234;
    --accent-fg: #ffffff;
    --accent-soft: #e2efe6;
    --accent-border: #b8d3c2;

    --blocker: #b42318;
    --blocker-bg: #fef2f2;
    --blocker-border: #f5c2be;

    --warn: #9c5520;
    --warn-bg: #fbf2ea;
    --warn-border: #e8cbb4;

    --ok: #3a64ad;
    --ok-bg: #edf2fa;
    --ok-border: #c5d5ee;

    --decision: #007270;
    --decision-bg: #ebf6f5;
    --decision-border: #b7dedb;

    --radius-sm: 4px;
    --radius: 8px;
    --radius-lg: 12px;
    --shadow-lg: 0 14px 36px rgba(17, 26, 21, 0.2);
    --font: "Geist", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  :root[data-theme="dark"] {
    --bg: #0f1411;
    --surface: #151b17;
    --popover: #151b17;
    --surface-subtle: #1c241f;
    --surface-tint: #17291f;
    --text: #e8eeea;
    --text-muted: #8a988f;
    --text-soft: #c5d0c9;
    --border: #2a342e;
    --border-strong: #6e7c73;

    --accent: #6cc08f;
    --accent-hover: #83cea2;
    --accent-fg: #0b130e;
    --accent-soft: #17291f;
    --accent-border: #2e533e;

    --blocker: #f28b82;
    --blocker-bg: #2e1513;
    --blocker-border: #632b27;

    --warn: #d88b52;
    --warn-bg: #2a1d13;
    --warn-border: #593b25;

    --ok: #7fa3e6;
    --ok-bg: #162033;
    --ok-border: #2d4266;

    --decision: #2fa8a5;
    --decision-bg: #122929;
    --decision-border: #255755;
  }

  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  }
  body {
    margin: 0;
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.56;
    font-size: 14.5px;
    -webkit-font-smoothing: antialiased;
    padding-bottom: 92px;
  }

  .topbar {
    position: sticky; top: 0; z-index: 30;
    height: 40px; padding: 0 20px;
    background: var(--bg); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
  }
  .mark { width: 10px; height: 10px; border-radius: 2px; background: var(--accent); flex: none; }
  .topbar-title { font-size: 13px; font-weight: 600; letter-spacing: -0.01em; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .topbar-sub { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .spacer { flex: 1; }

  .page-shell { width: 100%; max-width: 1360px; margin: 0 auto; display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: 24px; padding: 20px 20px 40px; align-items: start; }
  @media (max-width: 960px) { .page-shell { grid-template-columns: 1fr; padding: 14px; } .sidebar { position: static !important; max-height: none !important; } .topbar-sub { display: none; } }

  .sidebar { position: sticky; top: 56px; max-height: calc(100vh - 130px); overflow-y: auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; }
  .brand-header { padding-bottom: 12px; margin-bottom: 12px; border-bottom: 1px solid var(--border); }
  .brand-kicker { font-size: 12px; font-weight: 600; color: var(--accent); margin-bottom: 2px; }
  .brand-title { font-size: 16px; font-weight: 600; margin: 0 0 3px; color: var(--text); }
  .brand-sub { font-size: 12px; color: var(--text-muted); margin: 0; }

  .sidebar-status-box { background: var(--accent-soft); border: 1px solid var(--accent-border); border-radius: var(--radius); padding: 9px 11px; margin-bottom: 12px; font-size: 12.5px; }
  .sidebar-status-box.snapshot-mode { background: var(--warn-bg); border-color: var(--warn-border); }
  .sidebar-status-box strong { display: block; color: var(--accent); font-size: 12px; font-weight: 600; margin-bottom: 2px; }
  .sidebar-status-box.snapshot-mode strong { color: var(--warn); }

  .nav-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .nav-link { display: flex; align-items: center; justify-content: space-between; gap: 8px; text-decoration: none; color: var(--text-muted); font-size: 13px; font-weight: 400; padding: 6px 8px; border-radius: var(--radius); }
  .nav-link:hover { background: var(--surface-subtle); color: var(--text); }
  .nav-link.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .nav-num { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: var(--radius-sm); background: var(--surface-subtle); font-size: 12px; font-weight: 600; color: var(--text-muted); flex-shrink: 0; }
  .nav-link.active .nav-num { background: var(--accent); color: var(--accent-fg); }
  .nav-label { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .nav-label span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nav-count { font-size: 11.5px; font-weight: 600; font-variant-numeric: tabular-nums; padding: 1px 7px; border-radius: 999px; background: var(--accent); color: var(--accent-fg); display: none; flex-shrink: 0; }
  .nav-count.visible { display: inline-block; }

  .sidebar-snapshots { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
  .sidebar-snapshots-title { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
  .snapshot-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
  .snapshot-link { display: block; font-size: 12.5px; color: var(--accent); text-decoration: none; padding: 4px 8px; border-radius: var(--radius-sm); background: var(--surface-subtle); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .snapshot-link:hover { background: var(--accent-soft); }
  .snapshot-empty { font-size: 12px; color: var(--text-muted); margin: 0; }

  .sidebar-footer { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-muted); display: flex; flex-direction: column; gap: 5px; font-variant-numeric: tabular-nums; }

  .main-col { min-width: 0; display: flex; flex-direction: column; gap: 20px; }

  .hero-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 20px; }
  .hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
  .hero-title { font-size: 21px; font-weight: 600; margin: 0 0 5px; letter-spacing: -0.02em; }
  .hero-subtitle { margin: 0; color: var(--text-soft); font-size: 14px; max-width: 78ch; }
  .meta-chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .meta-chip { font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: var(--radius-sm); background: var(--surface-subtle); color: var(--text-muted); border: 1px solid var(--border); }
  .meta-chip.ok { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-border); }
  .meta-chip.info { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-border); }
  .meta-chip.warn { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-border); }

  .track-label { font-size: 12px; font-weight: 600; color: var(--text-muted); margin: 14px 0 6px; }
  .phase-track, .wave-track { display: grid; grid-template-columns: repeat(auto-fit, minmax(136px, 1fr)); gap: 6px; }

  .phase-pill { border: 1px solid var(--border); background: var(--bg); border-radius: var(--radius); padding: 8px 10px; font-size: 12.5px; }
  .phase-pill.done { background: var(--ok-bg); border-color: var(--ok-border); }
  .phase-pill.current { background: var(--accent-soft); border-color: var(--accent); }
  .phase-pill-num { font-size: 12px; font-weight: 600; color: var(--text-muted); display: flex; justify-content: space-between; font-variant-numeric: tabular-nums; }
  .phase-pill.done .phase-pill-num { color: var(--ok); }
  .phase-pill.current .phase-pill-num { color: var(--accent); }
  .phase-pill-name { font-weight: 600; color: var(--text); margin-top: 2px; line-height: 1.25; }

  .wave-step { border: 1px solid var(--border); background: var(--bg); border-radius: var(--radius); padding: 7px 9px; font-size: 12px; }
  .wave-step.done { border-color: var(--ok-border); background: var(--ok-bg); }
  .wave-step.active { border-color: var(--accent); background: var(--accent-soft); }
  .wave-step-top { font-weight: 600; font-size: 12px; display: flex; justify-content: space-between; }
  .wave-step.done .wave-step-top { color: var(--ok); }
  .wave-step.active .wave-step-top { color: var(--accent); }
  .wave-step-desc { color: var(--text-muted); margin-top: 2px; line-height: 1.25; }

  .toolbar { position: sticky; top: 40px; z-index: 20; background: var(--bg); padding: 9px 0; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .filter-pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill { appearance: none; border: 1px solid var(--border); background: var(--surface); color: var(--text-muted); font: inherit; font-size: 12.5px; font-weight: 600; padding: 4px 11px; border-radius: 999px; cursor: pointer; }
  .pill:hover { background: var(--surface-subtle); color: var(--text); }
  .pill.active { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
  .pill .pill-badge { display: inline-block; margin-left: 5px; padding: 0 6px; border-radius: 999px; font-size: 11.5px; background: rgba(0, 0, 0, 0.08); }
  .pill.active .pill-badge { background: rgba(255, 255, 255, 0.25); color: var(--accent-fg); }
  .search-input { border: 1px solid var(--border-strong); background: var(--surface); border-radius: var(--radius-sm); padding: 6px 12px; font: inherit; font-size: 13px; color: var(--text); width: 240px; }

  .section { scroll-margin-top: 100px; }
  .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
  .section-title { font-size: 17.5px; font-weight: 600; margin: 0; display: flex; align-items: center; gap: 8px; }
  .section-num { display: inline-flex; align-items: center; justify-content: center; min-width: 24px; height: 22px; padding: 0 6px; border-radius: var(--radius-sm); background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-border); font-family: var(--mono); font-size: 12px; font-weight: 600; }
  .section-desc { margin: 4px 0 0; color: var(--text-muted); font-size: 13.5px; max-width: 78ch; }
  .card-stack { display: flex; flex-direction: column; gap: 10px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 15px 17px; }
  .card.annotated { border-color: var(--accent); background: var(--accent-soft); }
  .card.card-action { border-left: 3px solid var(--warn); }
  .card.card-log { border-left: 3px solid var(--decision); }
  .card.hidden { display: none !important; }

  .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 7px; flex-wrap: wrap; }
  .card-title-wrap { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .card-title { font-size: 15px; font-weight: 600; margin: 0; color: var(--text); }

  .badge { display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: var(--radius-sm); border: 1px solid transparent; white-space: nowrap; }
  .badge-blocker  { background: var(--blocker-bg); color: var(--blocker); border-color: var(--blocker-border); }
  .badge-warn     { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-border); }
  .badge-ok       { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-border); }
  .badge-decision { background: var(--decision-bg); color: var(--decision); border-color: var(--decision-border); }
  .badge-info     { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-border); }
  .badge-neutral  { background: var(--surface-subtle); color: var(--text-muted); border-color: var(--border); }

  .card-body { font-size: 14px; color: var(--text); }
  .card-body p { margin: 0 0 8px; max-width: 78ch; }
  .card-body p:last-child { margin-bottom: 0; }
  .card-body ul, .card-body ol { margin: 6px 0 8px; padding-left: 20px; max-width: 78ch; }
  .card-body li { margin-bottom: 4px; }

  .callout { background: var(--bg); border: 1px solid var(--border); border-left: 2px solid var(--accent); border-radius: var(--radius-sm); padding: 9px 12px; margin: 9px 0; font-size: 13.5px; }
  .callout-ok { background: var(--ok-bg); border-color: var(--ok-border); border-left-color: var(--ok); }
  .callout-learn { background: var(--decision-bg); border-color: var(--decision-border); border-left-color: var(--decision); }

  .log-meta-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; font-size: 12.5px; color: var(--text-muted); }
  .log-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; margin: 9px 0; }
  .log-box { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 11px; font-size: 13px; }
  .log-box-label { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 3px; }
  .cmd-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }

  code { font-family: var(--mono); font-size: 12.5px; background: var(--surface-subtle); border: 1px solid var(--border); padding: 1px 5px; border-radius: var(--radius-sm); color: var(--text); }
  pre { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; overflow-x: auto; font-size: 12.5px; line-height: 1.5; margin: 7px 0 9px; }
  pre code { background: none; border: none; padding: 0; color: var(--text); }

  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 10px; }
  .field-group { display: flex; flex-direction: column; gap: 4px; }
  .field-group label { font-size: 12.5px; font-weight: 600; color: var(--text); }
  .field-input, .field-select { border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 7px 10px; font-family: inherit; font-size: 13.5px; color: var(--text); background: var(--bg); }

  .checklist { list-style: none; padding: 0; margin: 9px 0; display: flex; flex-direction: column; gap: 7px; }
  .checklist li { display: flex; align-items: flex-start; gap: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 11px; font-size: 13.5px; }
  .checklist input[type="checkbox"] { margin-top: 3px; width: 16px; height: 16px; accent-color: var(--accent); flex-shrink: 0; cursor: pointer; }

  .data-table-wrap { overflow-x: auto; margin: 9px 0; border: 1px solid var(--border); border-radius: var(--radius-sm); }
  table.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.data-table th { background: var(--surface-subtle); text-align: left; padding: 7px 10px; font-size: 12px; font-weight: 600; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
  table.data-table td { padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  table.data-table tr:last-child td { border-bottom: none; }

  .card-actions { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
  .stance-group { display: flex; gap: 6px; flex-wrap: wrap; }
  .stance-btn { appearance: none; border: 1px solid var(--border); background: var(--bg); color: var(--text-muted); font: inherit; font-size: 12.5px; font-weight: 600; padding: 4px 10px; border-radius: var(--radius); cursor: pointer; }
  .stance-btn:hover { background: var(--surface-subtle); color: var(--text); }
  .stance-btn.active[data-stance="agree"]    { background: var(--ok-bg); color: var(--ok); border-color: var(--ok); }
  .stance-btn.active[data-stance="question"] { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
  .stance-btn.active[data-stance="change"]   { background: var(--warn-bg); color: var(--warn); border-color: var(--warn); }
  .stance-btn.active[data-stance="skip"]     { background: var(--surface-subtle); color: var(--text-muted); border-color: var(--border-strong); }

  .note-toggle-btn { appearance: none; border: 1px dashed var(--border-strong); background: transparent; color: var(--accent); font: inherit; font-size: 12.5px; font-weight: 600; padding: 4px 10px; border-radius: var(--radius); cursor: pointer; }
  .note-toggle-btn:hover { background: var(--accent-soft); }
  .note-box { margin-top: 9px; display: none; }
  .note-box.open { display: block; }
  .note-textarea { width: 100%; min-height: 70px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 9px 11px; font-family: inherit; font-size: 13.5px; color: var(--text); background: var(--bg); resize: vertical; }

  .btn { appearance: none; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: inherit; font-size: 13px; font-weight: 600; padding: 6px 13px; border-radius: var(--radius); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
  .btn:hover { background: var(--accent-soft); }
  .btn-primary { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
  .btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  .btn-danger-ghost { background: transparent; color: var(--blocker); border-color: var(--border); }
  .btn-danger-ghost:hover { background: var(--blocker-bg); border-color: var(--blocker); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }

  .doc-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
  .doc-tab { appearance: none; border: 1px solid var(--border); background: var(--surface); color: var(--text-muted); font: inherit; font-size: 12.5px; font-weight: 600; padding: 5px 12px; border-radius: var(--radius); cursor: pointer; }
  .doc-tab.active { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
  .doc-meta-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12.5px; color: var(--text-muted); margin: 4px 0 7px; font-variant-numeric: tabular-nums; }
  .doc-viewer-wrap { margin-top: 10px; border-top: 1px solid var(--border); padding-top: 12px; display: none; }
  .doc-viewer-wrap.open { display: block; }
  .doc-viewer-bar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 9px; flex-wrap: wrap; }

  .md-rendered { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 16px 20px; font-size: 14px; line-height: 1.62; max-height: 540px; overflow-y: auto; }
  .modal-body .md-rendered { max-height: none; border: none; background: var(--popover); padding: 4px 2px; }
  .md-rendered h1 { font-size: 19px; font-weight: 600; margin: 0 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  .md-rendered h2 { font-size: 16px; font-weight: 600; margin: 18px 0 8px; color: var(--accent); }
  .md-rendered h3 { font-size: 14.5px; font-weight: 600; margin: 14px 0 6px; color: var(--text); }
  .md-rendered blockquote { margin: 10px 0; padding: 8px 13px; border-left: 2px solid var(--accent); background: var(--surface-subtle); color: var(--text-soft); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
  .md-rendered hr { border: none; border-top: 1px solid var(--border); margin: 14px 0; }
  .md-frontmatter { background: var(--surface-subtle); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 11px; margin-bottom: 12px; font-size: 12px; color: var(--text-muted); }
  .md-frontmatter summary { cursor: pointer; font-weight: 600; color: var(--text); }
  .md-gsd-block { border: 1px solid var(--border); border-left: 2px solid var(--accent); background: var(--surface); border-radius: var(--radius-sm); padding: 10px 13px; margin: 10px 0; }
  .md-gsd-label { font-size: 12px; font-weight: 600; color: var(--accent); margin-bottom: 5px; }
  .md-raw { display: none; max-height: 540px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
  .md-raw.show { display: block; }
  .md-rendered.hide { display: none; }

  .bottom-dock { position: fixed; bottom: 0; left: 0; right: 0; z-index: 40; background: var(--surface); border-top: 1px solid var(--border); padding: 10px 20px; }
  .dock-inner { width: 100%; max-width: 1360px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; }
  .dock-stats { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-muted); font-variant-numeric: tabular-nums; flex-wrap: wrap; }
  .dock-stats strong { color: var(--text); font-weight: 600; }
  .dock-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

  .modal-backdrop { position: fixed; inset: 0; z-index: 100; background: rgba(17, 26, 21, 0.45); display: none; align-items: center; justify-content: center; padding: 20px; }
  .modal-backdrop.open { display: flex; }
  .modal-dialog { background: var(--popover); border: 1px solid var(--border); border-radius: var(--radius-lg); width: 100%; max-width: 880px; max-height: 88vh; display: flex; flex-direction: column; box-shadow: var(--shadow-lg); overflow: hidden; }
  .modal-dialog.reader-dialog { max-width: 1040px; }
  .modal-head { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .modal-head h3 { margin: 0; font-size: 16px; font-weight: 600; }
  .modal-body { padding: 16px 18px; overflow-y: auto; flex: 1; }
  .modal-foot { padding: 12px 18px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .prompt-output { width: 100%; min-height: 320px; font-family: var(--mono); font-size: 12.5px; line-height: 1.55; padding: 12px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); resize: vertical; }
  .copy-status { font-size: 13px; font-weight: 600; color: var(--accent); opacity: 0; transition: opacity 0.2s; }
  .copy-status.show { opacity: 1; }
</style>
</head>
<body>

<header class="topbar">
  <span class="mark" aria-hidden="true"></span>
  <h1 class="topbar-title">__PROJECT_NAME__</h1>
  <span class="topbar-sub">Living Project &amp; Learning Hub</span>
  <span class="spacer"></span>
  <button type="button" class="btn btn-sm" id="themeToggleBtn">Dark</button>
</header>

<div class="page-shell">

  <!-- SIDEBAR -->
  <aside class="sidebar">
    <div class="brand-header">
      <div class="brand-kicker">Living Project &amp; Learning Hub</div>
      <h1 class="brand-title">__PROJECT_NAME__</h1>
      <p class="brand-sub">__BRAND_SUB__</p>
    </div>

    <div class="sidebar-status-box __STATUS_BOX_CLASS__">
      <strong>__STATUS_BADGE__</strong>
      <span>__STATUS_SUMMARY__</span>
    </div>

    <nav aria-label="Sections">
      <ul class="nav-list" id="sidebarNav">
        __CHECKPOINT_NAV__
        <li><a class="nav-link active" href="#sec-log" data-sec="sec-log"><span class="nav-label"><span class="nav-num">1</span><span>Execution &amp; CLI Log</span></span><span class="nav-count" data-sec-count="sec-log">0</span></a></li>
        __ROADMAP_NAV__
        <li><a class="nav-link" href="#sec-docs" data-sec="sec-docs"><span class="nav-label"><span class="nav-num">3</span><span>Markdown Library</span></span><span class="nav-count" data-sec-count="sec-docs">0</span></a></li>
        <li><a class="nav-link" href="#sec-notes" data-sec="sec-notes"><span class="nav-label"><span class="nav-num">+</span><span>Overall Notes</span></span><span class="nav-count" data-sec-count="sec-notes">0</span></a></li>
      </ul>
    </nav>

    <div class="sidebar-snapshots">
      <div class="sidebar-snapshots-title">Phase Snapshots</div>
      <ul class="snapshot-list" id="snapshotList"></ul>
    </div>

    <div class="sidebar-footer">
      <div><strong>Branch:</strong> <code>__GIT_BRANCH__</code> (<code>__GIT_SHA__</code>)</div>
      <div><strong>Docs:</strong> __DOC_COUNT__ · <strong>Log:</strong> <span id="sidebarLogCount">__LOG_COUNT__</span></div>
      <div><strong>Built:</strong> __GENERATED_AT__</div>
    </div>
  </aside>

  <!-- MAIN COLUMN -->
  <main class="main-col">

    <!-- HERO -->
    <section class="hero-card">
      <div class="hero-top">
        <div>
          <h1 class="hero-title">__HERO_TITLE__</h1>
          <p class="hero-subtitle">__PROJECT_SUBTITLE__</p>
        </div>
        <div class="meta-chips">__META_CHIPS__</div>
      </div>
      __PHASE_TRACK__
      __WAVE_TRACK__
    </section>

    <!-- FILTER TOOLBAR -->
    <div class="toolbar">
      <div class="filter-pills" id="filterBar">
        <button class="pill active" data-filter="all">All</button>
        __CHECKPOINT_PILL__
        <button class="pill" data-filter="log">Execution &amp; CLI Log</button>
        __ROADMAP_PILL__
        <button class="pill" data-filter="doc">Markdown Library</button>
        <button class="pill" data-filter="annotated">Annotated <span class="pill-badge" id="annotatedFilterCount">0</span></button>
      </div>
      <input type="search" id="searchInput" class="search-input" placeholder="Search commands, tools, docs..." aria-label="Search commands, tools, docs" />
    </div>

    __CHECKPOINT_SECTION__

    <!-- EXECUTION & LEARNING LOG -->
    <section class="section" id="sec-log">
      <div class="section-head">
        <div>
          <h2 class="section-title"><span class="section-num">1</span> Execution &amp; Learning Log</h2>
          <p class="section-desc">Live feed from <code>.scratch/execution-log.json</code> (and <code>/api/log</code> when served). Every significant command, flags explained, architecture link, verified result, and engineering takeaway.</p>
        </div>
        <button type="button" class="btn btn-sm" id="refreshLogBtn">↻ Refresh Live Log</button>
      </div>
      <div class="card-stack" id="execLogContainer"></div>
    </section>

    __ROADMAP_SECTION__

    <!-- READABLE MARKDOWN LIBRARY -->
    <section class="section" id="sec-docs">
      <div class="section-head">
        <div>
          <h2 class="section-title"><span class="section-num">3</span> Readable Markdown Document Library</h2>
          <p class="section-desc">All __DOC_COUNT__ auto-discovered repository documents formatted cleanly for human reading.</p>
        </div>
      </div>
      <div class="doc-tabs" id="docTabs">
        __DOC_TABS__
      </div>
      <div class="card-stack" id="docLibraryContainer"></div>
    </section>

    <!-- OVERALL NOTES -->
    <section class="section" id="sec-notes">
      <div class="section-head">
        <div>
          <h2 class="section-title"><span class="section-num">+</span> Overall Notes / Questions</h2>
          <p class="section-desc">Leave any overall questions, decisions, or follow-up instructions for the next turn.</p>
        </div>
      </div>
      <div class="card">
        <textarea id="overallNotes" class="note-textarea" style="min-height: 90px;" placeholder="Add any overall notes or questions here..."></textarea>
      </div>
    </section>

  </main>
</div>

<!-- BOTTOM DOCK -->
<div class="bottom-dock">
  <div class="dock-inner">
    <div class="dock-stats"><span id="dockSummary"><strong>0</strong> notes</span></div>
    <div class="dock-actions">
      <span class="copy-status" id="saveStatus" style="margin-right:4px;">Saved!</span>
      <button class="btn btn-danger-ghost btn-sm" id="resetAllBtn">Reset All</button>
      <button class="btn" id="buildPromptBtn">Copy Single Prompt</button>
      <button class="btn btn-primary" id="saveServerBtn" style="display:none;">Save Feedback to Host</button>
    </div>
  </div>
</div>

<!-- PROMPT MODAL -->
<div class="modal-backdrop" id="promptModal" role="dialog" aria-modal="true">
  <div class="modal-dialog">
    <div class="modal-head"><h3>Your Feedback &amp; Questions</h3><button class="btn btn-sm" id="closePromptModal">Close</button></div>
    <div class="modal-body"><textarea id="promptOutput" class="prompt-output" readonly></textarea></div>
    <div class="modal-foot">
      <span class="copy-status" id="copyStatus">Copied!</span>
      <div style="display:flex; gap:8px;">
        <button class="btn" id="closePromptModal2">Close</button>
        <button class="btn btn-primary" id="copyPromptBtn">Copy Prompt to Clipboard</button>
      </div>
    </div>
  </div>
</div>

<!-- READER MODAL -->
<div class="modal-backdrop" id="readerModal" role="dialog" aria-modal="true">
  <div class="modal-dialog reader-dialog">
    <div class="modal-head">
      <div><h3 id="readerModalTitle">Document</h3><div id="readerModalPath" style="font-size:12px; color:var(--text-soft); margin-top:2px;"></div></div>
      <div style="display:flex; gap:8px;"><button class="btn btn-sm" id="readerToggleRawBtn">Show Raw Markdown</button><button class="btn btn-sm" id="closeReaderModal">Close</button></div>
    </div>
    <div class="modal-body">
      <div id="readerModalRendered" class="md-rendered"></div>
      <pre id="readerModalRaw" class="md-raw"></pre>
    </div>
  </div>
</div>

<script id="hub-meta" type="application/json">__HUB_META_JSON__</script>
<script id="docs-data" type="application/json">__DOCS_JSON__</script>
<script id="exec-log-data" type="application/json">__EXEC_LOG_JSON__</script>
<script id="snapshots-data" type="application/json">__SNAPSHOTS_JSON__</script>

<script>
(function() {
  const META = JSON.parse(document.getElementById("hub-meta").textContent);
  const themeBtn = document.getElementById("themeToggleBtn");
  function applyTheme(t) {
    if (t === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      if (themeBtn) themeBtn.textContent = "Light";
    } else {
      document.documentElement.removeAttribute("data-theme");
      if (themeBtn) themeBtn.textContent = "Dark";
    }
    try { localStorage.setItem("project-hub-theme", t); } catch (e) {}
  }
  try {
    if (localStorage.getItem("project-hub-theme") === "dark") applyTheme("dark");
  } catch (e) {}
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  }
  const STORAGE_KEY = "project-hub-" + META.repoSlug + "-" + META.roundId;
  const ROUND_ID = META.roundId;
  const DOCS = JSON.parse(document.getElementById("docs-data").textContent);
  let EXEC_LOG = JSON.parse(document.getElementById("exec-log-data").textContent);
  let SNAPSHOTS = JSON.parse(document.getElementById("snapshots-data").textContent);
  let state = loadState();

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const p = JSON.parse(raw);
        return { cards: p.cards || {}, form: p.form || {}, checks: p.checks || {}, overall: p.overall || "" };
      }
    } catch (e) {}
    return { cards: {}, form: {}, checks: {}, overall: "" };
  }
  function saveState() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
    updateUIState();
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatInline(text) {
    let s = escapeHtml(text);
    const slots = [];
    s = s.replace(/`([^`]+)`/g, (_, inner) => {
      slots.push("<code>" + inner + "</code>");
      return "\u0000C" + (slots.length - 1) + "\u0000";
    });
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
      const safeUrl = /^(https?:|\/|#|\.\.?\/)/i.test(url.trim()) ? url.trim() : "#";
      return '<a href="' + safeUrl + '" target="_blank" rel="noopener">' + label + "</a>";
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^A-Za-z0-9_])\*([^*]+)\*(?![A-Za-z0-9_])/g, "$1<em>$2</em>");
    s = s.replace(/\u0000C(\d+)\u0000/g, (_, i) => slots[Number(i)]);
    return s;
  }

  function renderMarkdown(md) {
    let src = (md || "").replace(/\r\n/g, "\n");
    const parts = [];
    const fm = src.match(/^---\n([\s\S]*?)\n---\n?/);
    if (fm) {
      parts.push('<details class="md-frontmatter"><summary>Document Metadata</summary><pre><code>' + escapeHtml(fm[1].trim()) + "</code></pre></details>");
      src = src.slice(fm[0].length);
    }
    const lines = src.split("\n");
    let i = 0;
    const isSep = l => /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(l);
    const splitR = l => {
      let t = l.trim();
      if (t.startsWith("|")) t = t.slice(1);
      if (t.endsWith("|")) t = t.slice(0, -1);
      return t.split("|").map(c => c.trim());
    };
    const tags = {
      objective: "Objective", context: "Context", tasks: "Tasks", task: "Task",
      name: "Task Name", files: "Files", read_first: "Read First", action: "Action",
      instructions: "Instructions", verify: "Verify", automated: "Automated Check",
      fails_when: "Fails When", acceptance_criteria: "Acceptance Criteria",
      done: "Done When", threat_model: "Threat Model", verification: "Verification",
      success_criteria: "Success Criteria", output: "Output",
      "resume-signal": "Resume Signal", precondition: "Precondition", reversibility: "Reversibility"
    };
    while (i < lines.length) {
      const l = lines[i];
      if (/^\s*$/.test(l) || /^\s*<!--[\s\S]*?-->\s*$/.test(l)) { i++; continue; }
      if (/^\s*```/.test(l)) {
        const c = []; i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { c.push(lines[i]); i++; }
        i++;
        parts.push("<pre><code>" + escapeHtml(c.join("\n")) + "</code></pre>");
        continue;
      }
      const st = l.match(/^\s*<([a-zA-Z_-]+)(?:\s+[^>]*)?>(.*)<\/\1>\s*$/);
      if (st && tags[st[1]]) {
        parts.push('<div class="md-gsd-block"><div class="md-gsd-label">' + tags[st[1]] + "</div><div>" + formatInline(st[2].trim()) + "</div></div>");
        i++; continue;
      }
      const ot = l.match(/^\s*<([a-zA-Z_-]+)(?:\s+([^>]*))?>\s*$/);
      if (ot && tags[ot[1]]) {
        parts.push('<div class="md-gsd-label" style="margin-top:14px;">▸ ' + tags[ot[1]] + "</div>");
        i++; continue;
      }
      const ct = l.match(/^\s*<\/([a-zA-Z_-]+)>\s*$/);
      if (ct && tags[ct[1]]) { i++; continue; }
      const h = l.match(/^(#{1,4})\s+(.*)$/);
      if (h) {
        parts.push("<h" + h[1].length + ">" + formatInline(h[2].trim()) + "</h" + h[1].length + ">");
        i++; continue;
      }
      if (/^\s*---+\s*$/.test(l)) { parts.push("<hr/>"); i++; continue; }
      if (l.includes("|") && i + 1 < lines.length && isSep(lines[i + 1])) {
        const hd = splitR(l); i += 2; const rows = [];
        while (i < lines.length && lines[i].includes("|") && !/^\s*$/.test(lines[i])) { rows.push(splitR(lines[i])); i++; }
        let tbl = '<div class="data-table-wrap"><table class="data-table"><thead><tr>' + hd.map(x => "<th>" + formatInline(x) + "</th>").join("") + "</tr></thead><tbody>";
        rows.forEach(r => { tbl += "<tr>" + hd.map((_, idx) => "<td>" + formatInline(r[idx] || "") + "</td>").join("") + "</tr>"; });
        parts.push(tbl + "</tbody></table></div>");
        continue;
      }
      if (/^\s*>\s?/.test(l)) {
        const b = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) { b.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        parts.push("<blockquote>" + b.map(formatInline).join("<br/>") + "</blockquote>");
        continue;
      }
      if (/^\s*[-*]\s+/.test(l)) {
        const it = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          let t = lines[i].replace(/^\s*[-*]\s+/, "");
          if (/^\[x\]\s+/i.test(t)) t = "✅ " + formatInline(t.replace(/^\[x\]\s+/i, ""));
          else if (/^\[ \]\s+/.test(t)) t = "⬜ " + formatInline(t.replace(/^\[ \]\s+/, ""));
          else t = formatInline(t);
          it.push("<li>" + t + "</li>"); i++;
        }
        parts.push("<ul>" + it.join("") + "</ul>");
        continue;
      }
      if (/^\s*\d+\.\s+/.test(l)) {
        const it = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          it.push("<li>" + formatInline(lines[i].replace(/^\s*\d+\.\s+/, "")) + "</li>"); i++;
        }
        parts.push("<ol>" + it.join("") + "</ol>");
        continue;
      }
      const p = [];
      while (
        i < lines.length &&
        !/^\s*$/.test(lines[i]) &&
        !/^(#{1,4})\s+/.test(lines[i]) &&
        !/^\s*```/.test(lines[i]) &&
        !/^\s*[-*]\s+/.test(lines[i]) &&
        !/^\s*\d+\.\s+/.test(lines[i]) &&
        !/^\s*>\s?/.test(lines[i]) &&
        !/^\s*---+\s*$/.test(lines[i]) &&
        !(lines[i].includes("|") && i + 1 < lines.length && isSep(lines[i + 1])) &&
        !/^\s*<\/?[a-zA-Z_-]+/.test(lines[i])
      ) { p.push(lines[i].trim()); i++; }
      parts.push("<p>" + formatInline(p.length ? p.join(" ") : lines[i++]) + "</p>");
    }
    return parts.join("\n");
  }

  function renderSnapshots(snaps) {
    const list = document.getElementById("snapshotList");
    list.innerHTML = "";
    if (!snaps || !snaps.length) {
      list.innerHTML = '<li><p class="snapshot-empty">No phase snapshots saved yet. Run with <code>--snapshot phase-01-slug</code> on phase completion.</p></li>';
      return;
    }
    const isHttp = location.protocol === "http:" || location.protocol === "https:";
    const inSnapshotsDir = /\/snapshots\//.test(location.pathname);
    snaps.forEach(s => {
      const li = document.createElement("li");
      const href = isHttp ? "/snapshots/" + encodeURIComponent(s.name) : (inSnapshotsDir ? "./" : "snapshots/") + encodeURIComponent(s.name);
      li.innerHTML = `<a class="snapshot-link" href="${href}" target="_blank" rel="noopener" title="${escapeHtml(s.name)}">${escapeHtml(s.label || s.name)}</a>`;
      list.appendChild(li);
    });
  }

  function renderExecLog(entries) {
    const container = document.getElementById("execLogContainer");
    container.innerHTML = "";
    const countEl = document.getElementById("sidebarLogCount");
    if (countEl) countEl.textContent = String((entries || []).length);

    if (!entries || !entries.length) {
      container.innerHTML = `
        <article class="card">
          <div class="card-body">
            <p><strong>No execution log entries yet.</strong> Append objects to <code>.scratch/execution-log.json</code> (with <code>id</code>, <code>timestamp</code>, <code>wave</code>, <code>plan</code>, <code>arch_link</code>, <code>tool</code>, <code>title</code>, <code>command</code>, <code>parameters</code>, <code>why</code>, <code>result</code>, and <code>learning</code>) and click <strong>Refresh Live Log</strong>.</p>
          </div>
        </article>`;
      return;
    }

    const ordered = [...entries].reverse();
    ordered.forEach((entry, idx) => {
      const eid = entry.id || ("log-" + (entries.length - idx));
      const card = document.createElement("article");
      card.className = "card card-log";
      card.dataset.id = eid;
      card.dataset.sec = "sec-log";
      card.dataset.cat = "log";
      card.dataset.title = `[${entry.wave || "Log"}] ${entry.title || eid}`;
      card.innerHTML = `
        <div class="card-top">
          <div class="card-title-wrap">
            ${entry.wave ? `<span class="badge badge-info">${escapeHtml(entry.wave)}</span>` : ""}
            ${entry.tool ? `<span class="badge badge-decision">${escapeHtml(entry.tool)}</span>` : ""}
            <h3 class="card-title">${escapeHtml(entry.title || eid)}</h3>
          </div>
          <span style="font-size:12px; color:var(--text-soft);">${escapeHtml(entry.timestamp || "")}</span>
        </div>
        <div class="log-meta-bar">
          ${entry.plan ? `<span><strong>Plan:</strong> <code>${escapeHtml(entry.plan)}</code></span>` : ""}
          ${entry.plan && entry.arch_link ? "<span>·</span>" : ""}
          ${entry.arch_link ? `<span><strong>Maps to:</strong> ${escapeHtml(entry.arch_link)}</span>` : ""}
        </div>
        <div class="card-body">
          ${entry.command ? `
            <div class="cmd-head">
              <span style="font-size:12px; font-weight:700; color:var(--text-muted);">CLI Command(s) Run:</span>
              <button type="button" class="btn btn-sm" data-copy-cmd="${escapeHtml(eid)}">Copy</button>
            </div>
            <pre><code id="cmd-${escapeHtml(eid)}">${escapeHtml(entry.command)}</code></pre>
          ` : ""}
          <div class="log-grid">
            ${entry.parameters ? `<div class="log-box"><div class="log-box-label">Parameters &amp; Flags Explained</div><div>${formatInline(entry.parameters)}</div></div>` : ""}
            ${entry.why ? `<div class="log-box"><div class="log-box-label">Why We Ran This (Architecture Link)</div><div>${formatInline(entry.why)}</div></div>` : ""}
          </div>
          ${entry.result ? `<div class="callout callout-ok"><strong>Observed Result:</strong> ${formatInline(entry.result)}</div>` : ""}
          ${entry.learning ? `<div class="callout callout-learn"><strong>Key Engineering Takeaway:</strong> ${formatInline(entry.learning)}</div>` : ""}
        </div>
        <div class="card-actions" data-card-controls></div>
      `;
      container.appendChild(card);
    });
    attachCardControlsIn(container);
    updateUIState();
  }

  document.getElementById("execLogContainer").addEventListener("click", async e => {
    const btn = e.target.closest("[data-copy-cmd]");
    if (!btn) return;
    const codeEl = document.getElementById("cmd-" + btn.dataset.copyCmd);
    if (!codeEl) return;
    try {
      await navigator.clipboard.writeText(codeEl.textContent);
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = prev; }, 1600);
    } catch (err) {}
  });

  // Reader Modal
  const readerModal = document.getElementById("readerModal");
  const readerTitle = document.getElementById("readerModalTitle");
  const readerPath = document.getElementById("readerModalPath");
  const readerRendered = document.getElementById("readerModalRendered");
  const readerRaw = document.getElementById("readerModalRaw");
  const readerToggleRawBtn = document.getElementById("readerToggleRawBtn");

  function openDocReaderModal(docId) {
    const doc = DOCS.find(d => d.id === docId);
    if (!doc) return;
    readerTitle.textContent = doc.title;
    readerPath.textContent = doc.rel_path + " · " + doc.line_count + " lines";
    readerRendered.innerHTML = renderMarkdown(doc.content);
    readerRaw.textContent = doc.content;
    readerRaw.classList.remove("show");
    readerRendered.classList.remove("hide");
    readerToggleRawBtn.textContent = "Show Raw Markdown";
    readerModal.classList.add("open");
  }
  readerToggleRawBtn.addEventListener("click", () => {
    const s = readerRaw.classList.toggle("show");
    readerRendered.classList.toggle("hide", s);
    readerToggleRawBtn.textContent = s ? "Show Formatted" : "Show Raw Markdown";
  });
  document.getElementById("closeReaderModal").addEventListener("click", () => readerModal.classList.remove("open"));
  readerModal.addEventListener("click", e => { if (e.target === readerModal) readerModal.classList.remove("open"); });

  function buildDocumentLibrary() {
    const container = document.getElementById("docLibraryContainer");
    const badgeMap = { blocker: "badge-blocker", warn: "badge-warn", ok: "badge-ok", info: "badge-info", neutral: "badge-neutral" };
    if (!DOCS.length) {
      container.innerHTML = '<article class="card"><div class="card-body"><p>No markdown documents found in <code>docs/</code>, <code>.planning/</code>, or repo root.</p></div></article>';
      return;
    }
    DOCS.forEach(doc => {
      const card = document.createElement("article");
      card.className = "card";
      card.dataset.id = doc.id;
      card.dataset.sec = "sec-docs";
      card.dataset.cat = "doc";
      card.dataset.docGroup = doc.group;
      card.dataset.title = doc.title + " (" + doc.rel_path + ")";
      card.innerHTML = `
        <div class="card-top">
          <div class="card-title-wrap">
            <span class="badge ${badgeMap[doc.status_kind] || "badge-neutral"}">${escapeHtml(doc.status)}</span>
            <h3 class="card-title">${escapeHtml(doc.title)}</h3>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-sm" data-expand-doc="${doc.id}">Read Inline</button>
            <button class="btn btn-primary btn-sm" data-modal-doc="${doc.id}">Open Reader</button>
          </div>
        </div>
        <div class="doc-meta-row"><code>${escapeHtml(doc.rel_path)}</code><span>· ${doc.line_count} lines</span></div>
        <div class="card-body"><p>${escapeHtml(doc.summary)}</p></div>
        <div class="doc-viewer-wrap" id="viewer-${doc.id}">
          <div class="doc-viewer-bar">
            <span style="font-size:12.5px; font-weight:600; color:var(--text-muted);">Formatted Markdown View</span>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-sm" data-toggle-raw="${doc.id}">Show Raw Markdown</button>
              <button class="btn btn-sm" data-expand-doc="${doc.id}">Collapse</button>
            </div>
          </div>
          <div class="md-rendered" id="md-html-${doc.id}"></div>
          <pre class="md-raw" id="md-raw-${doc.id}"></pre>
        </div>
        <div class="card-actions" data-card-controls></div>
      `;
      container.appendChild(card);
    });
    container.addEventListener("click", e => {
      const ex = e.target.closest("[data-expand-doc]");
      if (ex) {
        const id = ex.dataset.expandDoc;
        const w = document.getElementById("viewer-" + id);
        const h = document.getElementById("md-html-" + id);
        const r = document.getElementById("md-raw-" + id);
        const doc = DOCS.find(d => d.id === id);
        if (!h.dataset.rendered && doc) {
          h.innerHTML = renderMarkdown(doc.content);
          r.textContent = doc.content;
          h.dataset.rendered = "1";
        }
        const open = w.classList.toggle("open");
        const top = w.parentElement.querySelector(".card-top [data-expand-doc]");
        if (top) top.textContent = open ? "Hide Inline" : "Read Inline";
        return;
      }
      const rw = e.target.closest("[data-toggle-raw]");
      if (rw) {
        const id = rw.dataset.toggleRaw;
        const h = document.getElementById("md-html-" + id);
        const r = document.getElementById("md-raw-" + id);
        const s = r.classList.toggle("show");
        h.classList.toggle("hide", s);
        rw.textContent = s ? "Show Formatted" : "Show Raw Markdown";
        return;
      }
      const mb = e.target.closest("[data-modal-doc]");
      if (mb) openDocReaderModal(mb.dataset.modalDoc);
    });
  }

  function attachCardControlsIn(rootEl) {
    rootEl.querySelectorAll("[data-card-controls]").forEach(host => {
      if (host.dataset.wired) return;
      host.dataset.wired = "1";
      const card = host.closest(".card"), id = card.dataset.id;
      host.innerHTML = `
        <div class="stance-group">
          <button type="button" class="stance-btn" data-stance="agree">Agree</button>
          <button type="button" class="stance-btn" data-stance="question">Question</button>
          <button type="button" class="stance-btn" data-stance="change">Change</button>
          <button type="button" class="stance-btn" data-stance="skip">Skip</button>
        </div>
        <button type="button" class="note-toggle-btn">+ Add note / question</button>
      `;
      const nb = document.createElement("div");
      nb.className = "note-box";
      nb.innerHTML = '<textarea class="note-textarea" placeholder="Ask a question or leave a note on this item..."></textarea>';
      host.after(nb);
      const ta = nb.querySelector("textarea");
      host.querySelectorAll(".stance-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const st = btn.dataset.stance;
          if (!state.cards[id]) state.cards[id] = { stance: "", note: "" };
          state.cards[id].stance = state.cards[id].stance === st ? "" : st;
          if (state.cards[id].stance === "question" || state.cards[id].stance === "change") {
            nb.classList.add("open");
            setTimeout(() => ta.focus(), 10);
          }
          saveState();
        });
      });
      host.querySelector(".note-toggle-btn").addEventListener("click", () => { if (nb.classList.toggle("open")) ta.focus(); });
      ta.addEventListener("input", () => {
        if (!state.cards[id]) state.cards[id] = { stance: "", note: "" };
        state.cards[id].note = ta.value;
        saveState();
      });
    });
  }

  function attachFormAndStaticControls() {
    attachCardControlsIn(document);
    document.querySelectorAll("[data-check]").forEach(cb => {
      cb.checked = Boolean(state.checks[cb.dataset.check]);
      cb.addEventListener("change", () => { state.checks[cb.dataset.check] = cb.checked; saveState(); });
    });
    document.querySelectorAll("[data-form-field]").forEach(el => {
      el.value = state.form[el.id] || "";
      const h = () => { state.form[el.id] = el.value; saveState(); };
      el.addEventListener("input", h);
      el.addEventListener("change", h);
    });
    const o = document.getElementById("overallNotes");
    o.value = state.overall || "";
    o.addEventListener("input", () => { state.overall = o.value; saveState(); });
  }

  function isCardAnnotated(card) {
    if (card.dataset.type === "form") return Object.values(state.form || {}).some(v => v && String(v).trim());
    const c = state.cards[card.dataset.id];
    return Boolean(c && (c.stance || (c.note && c.note.trim())));
  }

  function updateUIState() {
    let pointCount = 0;
    const totalFormFields = document.querySelectorAll("[data-form-field]").length;
    const formFilled = Object.values(state.form || {}).filter(v => v && String(v).trim()).length;
    const secCounts = {};
    document.querySelectorAll(".card[data-id]").forEach(card => {
      const ann = isCardAnnotated(card);
      card.classList.toggle("annotated", ann);
      if (ann) secCounts[card.dataset.sec] = (secCounts[card.dataset.sec] || 0) + (card.dataset.type === "form" ? formFilled : 1);
      if (card.dataset.type !== "form") {
        const c = state.cards[card.dataset.id] || { stance: "", note: "" };
        if (c.stance || (c.note && c.note.trim())) pointCount++;
        card.querySelectorAll(".stance-btn").forEach(b => b.classList.toggle("active", b.dataset.stance === c.stance));
        const ta = card.querySelector(".note-textarea");
        if (ta && ta.value !== (c.note || "")) ta.value = c.note || "";
        const nb = card.querySelector(".note-box");
        if (nb && c.note && c.note.trim()) nb.classList.add("open");
      }
    });
    const ov = Boolean(state.overall && state.overall.trim());
    if (ov) secCounts["sec-notes"] = 1;
    document.querySelectorAll("[data-sec-count]").forEach(b => {
      const n = secCounts[b.dataset.secCount] || 0;
      b.textContent = n;
      b.classList.toggle("visible", n > 0);
    });
    document.getElementById("annotatedFilterCount").textContent = pointCount + (formFilled > 0 ? 1 : 0);
    const parts = [];
    if (totalFormFields > 0) parts.push(`<strong>${formFilled}</strong>/${totalFormFields} checkpoint fields`);
    parts.push(`<strong>${pointCount}</strong> note${pointCount === 1 ? "" : "s"}`);
    if (ov) parts.push("<strong>+ overall note</strong>");
    document.getElementById("dockSummary").innerHTML = parts.join(" · ");
    applyFilters();
  }

  let activeFilter = "all", activeDocGroup = "all", searchQuery = "";
  function applyFilters() {
    const q = searchQuery.trim().toLowerCase();
    document.querySelectorAll(".card[data-id]").forEach(card => {
      let v = true;
      if (activeFilter === "annotated") v = isCardAnnotated(card);
      else if (activeFilter !== "all") v = card.dataset.cat === activeFilter;
      if (v && card.dataset.cat === "doc" && activeDocGroup !== "all") v = card.dataset.docGroup === activeDocGroup;
      if (v && q) v = (card.dataset.title + " " + card.textContent).toLowerCase().includes(q);
      card.classList.toggle("hidden", !v);
    });
  }
  document.getElementById("filterBar").addEventListener("click", e => {
    const b = e.target.closest(".pill[data-filter]"); if (!b) return;
    activeFilter = b.dataset.filter;
    document.querySelectorAll("#filterBar .pill").forEach(p => p.classList.toggle("active", p === b));
    applyFilters();
  });
  document.getElementById("docTabs").addEventListener("click", e => {
    const b = e.target.closest(".doc-tab[data-doc-group]"); if (!b) return;
    activeDocGroup = b.dataset.docGroup;
    document.querySelectorAll("#docTabs .doc-tab").forEach(t => t.classList.toggle("active", t === b));
    applyFilters();
  });
  document.getElementById("searchInput").addEventListener("input", e => { searchQuery = e.target.value; applyFilters(); });

  const sections = Array.from(document.querySelectorAll("section[id]"));
  const navLinks = Array.from(document.querySelectorAll("#sidebarNav .nav-link"));
  window.addEventListener("scroll", () => {
    let cur = sections[0] && sections[0].id;
    for (const s of sections) if (s.getBoundingClientRect().top <= 120) cur = s.id;
    navLinks.forEach(a => a.classList.toggle("active", a.dataset.sec === cur));
  }, { passive: true });

  document.getElementById("resetAllBtn").addEventListener("click", () => {
    if (!confirm("Clear all checkpoint fields, checkboxes, and notes?")) return;
    state = { cards: {}, form: {}, checks: {}, overall: "" };
    document.querySelectorAll("[data-check]").forEach(cb => { cb.checked = false; });
    document.querySelectorAll("[data-form-field]").forEach(el => { el.value = ""; });
    document.getElementById("overallNotes").value = "";
    document.querySelectorAll(".note-box").forEach(nb => nb.classList.remove("open"));
    saveState();
  });

  function buildSinglePrompt() {
    const lines = [`# ${META.projectName} — Owner Feedback & Questions`, ""];
    const formLines = [];
    document.querySelectorAll("[data-form-field]").forEach(el => {
      const val = (state.form[el.id] || "").trim();
      if (val) formLines.push(`- **${el.dataset.formField}:** ${val.replace(/\n/g, " ")}`);
    });
    if (formLines.length) lines.push("## Active Checkpoint Responses", ...formLines, "");

    const bySec = {};
    const secNames = {
      "sec-log": "Execution & CLI Log Notes",
      "sec-roadmap": "Roadmap Notes",
      "sec-docs": "Markdown Document Notes"
    };
    document.querySelectorAll('.card[data-id]:not([data-type="form"])').forEach(card => {
      const c = state.cards[card.dataset.id];
      if (!c || (!c.stance && !(c.note && c.note.trim()))) return;
      if (!bySec[card.dataset.sec]) bySec[card.dataset.sec] = [];
      const tag = c.stance ? `[${c.stance.toUpperCase()}] ` : "";
      let item = `- ${tag}**${card.dataset.title}**`;
      if (c.note && c.note.trim()) item += `\n  - Note: ${c.note.trim().replace(/\n/g, "\n    ")}`;
      bySec[card.dataset.sec].push(item);
    });
    Object.keys(secNames).forEach(sec => {
      if (bySec[sec] && bySec[sec].length) lines.push(`## ${secNames[sec]}`, ...bySec[sec], "");
    });
    if (state.overall && state.overall.trim()) lines.push("## Overall Notes", state.overall.trim(), "");
    return lines.length <= 2 ? "No fields or notes filled yet." : lines.join("\n").trim();
  }

  const promptModal = document.getElementById("promptModal");
  const promptOutput = document.getElementById("promptOutput");
  const copyStatus = document.getElementById("copyStatus");
  document.getElementById("buildPromptBtn").addEventListener("click", () => {
    promptOutput.value = buildSinglePrompt();
    copyStatus.classList.remove("show");
    promptModal.classList.add("open");
  });
  const closeP = () => promptModal.classList.remove("open");
  document.getElementById("closePromptModal").addEventListener("click", closeP);
  document.getElementById("closePromptModal2").addEventListener("click", closeP);
  promptModal.addEventListener("click", e => { if (e.target === promptModal) closeP(); });
  document.getElementById("copyPromptBtn").addEventListener("click", async () => {
    let ok = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try { await navigator.clipboard.writeText(promptOutput.value); ok = true; } catch (e) {}
    }
    if (!ok) {
      promptOutput.focus();
      promptOutput.select();
      try { ok = document.execCommand("copy"); } catch (e) {}
    }
    copyStatus.textContent = ok ? "Copied to clipboard!" : "Selected — press Ctrl+C / Cmd+C";
    copyStatus.classList.add("show");
    setTimeout(() => copyStatus.classList.remove("show"), 3500);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { promptModal.classList.remove("open"); readerModal.classList.remove("open"); }
  });

  const isHttp = location.protocol === "http:" || location.protocol === "https:";
  const saveServerBtn = document.getElementById("saveServerBtn");
  const saveStatus = document.getElementById("saveStatus");

  async function saveFeedbackToServer() {
    saveServerBtn.disabled = true;
    const orig = saveServerBtn.textContent;
    saveServerBtn.textContent = "Saving...";
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ savedAt: new Date().toISOString(), round: ROUND_ID, state, markdown: buildSinglePrompt() })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      saveStatus.textContent = "Saved to " + (data.file || ".scratch/owner-feedback.md") + "!";
      saveStatus.classList.add("show");
      setTimeout(() => saveStatus.classList.remove("show"), 4500);
    } catch (err) {
      saveStatus.style.color = "var(--blocker)";
      saveStatus.textContent = "Save failed — use Copy Single Prompt";
      saveStatus.classList.add("show");
      setTimeout(() => { saveStatus.classList.remove("show"); saveStatus.style.color = ""; }, 4500);
    } finally {
      saveServerBtn.disabled = false;
      saveServerBtn.textContent = orig;
    }
  }

  async function refreshLiveLog() {
    if (!isHttp || META.isSnapshot) return;
    try {
      const res = await fetch("/api/log");
      if (!res.ok) return;
      const d = await res.json();
      if (d && Array.isArray(d.entries)) {
        EXEC_LOG = d.entries;
        renderExecLog(EXEC_LOG);
      }
    } catch (e) {}
  }

  async function refreshSnapshots() {
    if (!isHttp) return;
    try {
      const res = await fetch("/api/snapshots");
      if (!res.ok) return;
      const d = await res.json();
      if (d && Array.isArray(d.snapshots)) {
        SNAPSHOTS = d.snapshots.map(s => ({
          name: s.name,
          label: s.name.replace(/\.html$/i, "").replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase())
        }));
        renderSnapshots(SNAPSHOTS);
      }
    } catch (e) {}
  }

  document.getElementById("refreshLogBtn").addEventListener("click", refreshLiveLog);

  async function hydrateFromServer() {
    if (!isHttp) return;
    if (!META.isSnapshot) {
      saveServerBtn.style.display = "inline-flex";
      saveServerBtn.addEventListener("click", saveFeedbackToServer);
      await refreshLiveLog();
    }
    await refreshSnapshots();
    if (META.isSnapshot) return;
    try {
      const res = await fetch("/api/state");
      if (!res.ok) return;
      const d = await res.json();
      if (d && d.round === ROUND_ID && d.state) {
        const empty = !Object.keys(state.cards || {}).length && !Object.values(state.form || {}).some(Boolean) && !(state.overall || "").trim();
        if (empty) {
          state = { cards: d.state.cards || {}, form: d.state.form || {}, checks: d.state.checks || {}, overall: d.state.overall || "" };
          document.querySelectorAll("[data-check]").forEach(cb => { cb.checked = Boolean(state.checks[cb.dataset.check]); });
          document.querySelectorAll("[data-form-field]").forEach(el => { el.value = state.form[el.id] || ""; });
          document.getElementById("overallNotes").value = state.overall;
          saveState();
        }
      }
    } catch (e) {}
  }

  renderSnapshots(SNAPSHOTS);
  renderExecLog(EXEC_LOG);
  buildDocumentLibrary();
  attachFormAndStaticControls();
  updateUIState();
  hydrateFromServer();
})();
</script>
</body>
</html>
"""


def build_html(
    root: Path,
    config: dict,
    docs: list[dict],
    exec_log: list[dict],
    snapshots: list[dict],
    title_override: str | None = None,
    subtitle_override: str | None = None,
    round_override: str | None = None,
    snapshot_label: str | None = None,
) -> str:
    project_name, subtitle = infer_project_identity(root, config)
    if title_override:
        project_name = title_override
    if subtitle_override:
        subtitle = subtitle_override

    branch, sha = get_git_info(root)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    round_id = round_override or config.get("round_id") or "live"
    is_snapshot = bool(snapshot_label)

    phases = config.get("phases") or parse_roadmap_phases(root)
    waves = config.get("waves") or []
    checkpoint = None if is_snapshot else config.get("checkpoint")

    status_badge = f"FROZEN SNAPSHOT · {snapshot_label}" if is_snapshot else str(config.get("status_badge") or "Live Workspace")
    status_summary = (
        f"Captured on {generated_at} ({branch} @ {sha})."
        if is_snapshot
        else str(config.get("status_summary") or f"{len(docs)} docs · {len(exec_log)} CLI log entries")
    )
    brand_sub = str(config.get("brand_sub") or "Project & Learning Control Center")
    hero_title = (
        f"{project_name} — Snapshot: {snapshot_label}"
        if is_snapshot
        else str(config.get("hero_title") or project_name)
    )

    chips = config.get("chips")
    if chips:
        chips_html = "".join(
            f'<span class="meta-chip {html_lib.escape(str(c.get("kind", "")))}">{html_lib.escape(str(c.get("label", "")))}</span>'
            for c in chips
        )
    else:
        chips_html = (
            f'<span class="meta-chip info">{html_lib.escape(branch)} · {html_lib.escape(sha)}</span>'
            f'<span class="meta-chip">{len(docs)} Docs</span>'
            f'<span class="meta-chip">{len(exec_log)} Log Steps</span>'
        )
        if is_snapshot:
            chips_html = f'<span class="meta-chip warn">Frozen Snapshot</span>' + chips_html

    cp_nav, cp_pill, cp_sec = render_checkpoint_section(checkpoint)
    rm_nav, rm_pill, rm_sec = render_roadmap_section(phases)

    hub_meta = {
        "projectName": project_name,
        "repoSlug": slugify(root.name),
        "roundId": slugify(round_id),
        "isSnapshot": is_snapshot,
    }

    safe_json = lambda obj: json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    replacements = {
        "__PROJECT_NAME__": html_lib.escape(project_name),
        "__BRAND_SUB__": html_lib.escape(brand_sub),
        "__STATUS_BOX_CLASS__": "snapshot-mode" if is_snapshot else "",
        "__STATUS_BADGE__": html_lib.escape(status_badge),
        "__STATUS_SUMMARY__": html_lib.escape(status_summary),
        "__GIT_BRANCH__": html_lib.escape(branch),
        "__GIT_SHA__": html_lib.escape(sha),
        "__DOC_COUNT__": str(len(docs)),
        "__LOG_COUNT__": str(len(exec_log)),
        "__GENERATED_AT__": html_lib.escape(generated_at),
        "__HERO_TITLE__": html_lib.escape(hero_title),
        "__PROJECT_SUBTITLE__": html_lib.escape(subtitle),
        "__META_CHIPS__": chips_html,
        "__PHASE_TRACK__": render_phase_track(phases),
        "__WAVE_TRACK__": render_wave_track(waves),
        "__CHECKPOINT_NAV__": cp_nav,
        "__CHECKPOINT_PILL__": cp_pill,
        "__CHECKPOINT_SECTION__": cp_sec,
        "__ROADMAP_NAV__": rm_nav,
        "__ROADMAP_PILL__": rm_pill,
        "__ROADMAP_SECTION__": rm_sec,
        "__DOC_TABS__": render_doc_tabs(docs),
        "__HUB_META_JSON__": safe_json(hub_meta),
        "__DOCS_JSON__": safe_json(docs),
        "__EXEC_LOG_JSON__": safe_json(exec_log),
        "__SNAPSHOTS_JSON__": safe_json(snapshots),
    }

    out = HTML_TEMPLATE
    for token, val in replacements.items():
        out = out.replace(token, val)
    return out


def main():
    parser = argparse.ArgumentParser(description="Build the Living Project & Learning Hub HTML page")
    parser.add_argument("--root", default=None, help="Repository root directory (default: auto-detect git root or cwd)")
    parser.add_argument("--out", default=None, help="Output HTML path (default: <root>/.scratch/project-hub.html)")
    parser.add_argument("--title", default=None, help="Override project title")
    parser.add_argument("--subtitle", default=None, help="Override hero subtitle")
    parser.add_argument("--round", default=None, help="Feedback round ID (changes localStorage key)")
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Also save a frozen phase snapshot to .scratch/snapshots/<slug>.html (e.g. phase-01-setup)",
    )
    args = parser.parse_args()

    root = resolve_root(args.root)
    scratch_dir = root / ".scratch"
    snapshots_dir = scratch_dir / "snapshots"
    out_html = Path(args.out).resolve() if args.out else scratch_dir / "project-hub.html"

    config = load_json_file(scratch_dir / "hub-config.json", {})
    if not isinstance(config, dict):
        config = {}
    exec_log = load_json_file(scratch_dir / "execution-log.json", [])
    if not isinstance(exec_log, list):
        exec_log = []
    docs = discover_documents(root)

    if args.snapshot:
        snap_slug = slugify(args.snapshot.removesuffix(".html"))
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snap_path = snapshots_dir / f"{snap_slug}.html"
        existing_snaps = discover_snapshots(snapshots_dir)
        snap_html = build_html(
            root=root,
            config=config,
            docs=docs,
            exec_log=exec_log,
            snapshots=existing_snaps,
            title_override=args.title,
            subtitle_override=args.subtitle,
            round_override=args.round,
            snapshot_label=snap_slug,
        )
        snap_path.write_text(snap_html, encoding="utf-8")
        print(f"Wrote snapshot {snap_path} ({len(snap_html):,} bytes)")

    snapshots = discover_snapshots(snapshots_dir)
    live_html = build_html(
        root=root,
        config=config,
        docs=docs,
        exec_log=exec_log,
        snapshots=snapshots,
        title_override=args.title,
        subtitle_override=args.subtitle,
        round_override=args.round,
        snapshot_label=None,
    )
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(live_html, encoding="utf-8")
    print(f"Wrote {out_html} ({len(live_html):,} bytes, {len(docs)} docs, {len(exec_log)} log entries, {len(snapshots)} snapshots)")


if __name__ == "__main__":
    main()
