#!/usr/bin/env python3
"""Build an interactive HTML brief from a compact JSON data file.

Usage:
  build_brief.py data.json output.html
  build_brief.py data.json output.html --publish [--slug my-review]
  build_brief.py data.json --publish [--slug my-review]
  cat data.json | build_brief.py - --publish --slug my-review

Static HTML is rendered here from the JSON data, so the brief reads cleanly in
previews, print, and without JavaScript; the template's inline script adds
stance buttons, decision radios, filtering, localStorage state, Markdown prompt
export, and the Fern & Stone Dark/Light switch. The template is never edited per
brief. Data shape: ../references/data-schema.md.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "template" / "brief.html"
PUBLISH_SCRIPT = Path(__file__).resolve().parent / "publish-brief"

BLOCK_TYPES = {"prose", "list", "kpis", "table", "callout", "diagram"}
BLOCK_REQUIRED = {
    "prose": ["paragraphs"],
    "list": ["items"],
    "kpis": ["items"],
    "table": ["columns", "rows"],
    "callout": ["text"],
    "diagram": ["html"],
}
TONES = {"neutral", "good", "warn", "bad"}


def _plain(value) -> str:
    return re.sub(r"<[^>]+>", "", str(value))


def _attr(value) -> str:
    return html.escape(_plain(value), quote=True)


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", _plain(value).strip().lower()).strip("-")
    return s or "brief"


def _fmt(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def check(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top-level JSON must be an object"]

    if not isinstance(data.get("title"), str) or not data["title"].strip():
        errors.append("missing or empty top-level 'title'")

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("top-level 'sections' must be a non-empty list")
        return errors

    ids: set[str] = set()

    def claim_id(value, where: str, required: bool = True):
        if not isinstance(value, str) or not value.strip():
            if required:
                errors.append(f"{where}: missing or empty 'id'")
            return
        if value in ids:
            errors.append(f"{where}: duplicate id '{value}' (state and anchors are keyed by id)")
        ids.add(value)

    for s_idx, sec in enumerate(sections):
        sw = f"sections[{s_idx}]"
        if not isinstance(sec, dict):
            errors.append(f"{sw}: must be an object")
            continue
        claim_id(sec.get("id"), sw)
        if not isinstance(sec.get("title"), str) or not sec["title"].strip():
            errors.append(f"{sw}: missing or empty 'title'")

        blocks = sec.get("blocks") or []
        cards = sec.get("cards") or []
        decisions = sec.get("decisions") or []
        if not (blocks or cards or decisions):
            errors.append(f"{sw}: section must contain at least one of 'blocks', 'cards', or 'decisions'")

        for b_idx, block in enumerate(blocks):
            bw = f"{sw}.blocks[{b_idx}]"
            _check_block(block, bw, errors)

        for c_idx, card in enumerate(cards):
            cw = f"{sw}.cards[{c_idx}]"
            if not isinstance(card, dict):
                errors.append(f"{cw}: must be an object")
                continue
            claim_id(card.get("id"), cw)
            if not isinstance(card.get("title"), str) or not card["title"].strip():
                errors.append(f"{cw}: missing or empty 'title'")
            tone = card.get("tone")
            if tone is not None and tone not in TONES:
                errors.append(f"{cw}: tone must be one of {sorted(TONES)}")
            if "table" in card and card["table"] is not None:
                _check_table(card["table"], f"{cw}.table", errors)
            callout = card.get("callout")
            if isinstance(callout, dict):
                ct = callout.get("tone")
                if ct is not None and ct not in TONES:
                    errors.append(f"{cw}.callout: tone must be one of {sorted(TONES)}")
                if not callout.get("text"):
                    errors.append(f"{cw}.callout: missing 'text'")

        for d_idx, dec in enumerate(decisions):
            dw = f"{sw}.decisions[{d_idx}]"
            if not isinstance(dec, dict):
                errors.append(f"{dw}: must be an object")
                continue
            claim_id(dec.get("id"), dw)
            if not isinstance(dec.get("title"), str) or not dec["title"].strip():
                errors.append(f"{dw}: missing or empty 'title'")
            opts = dec.get("options")
            if not isinstance(opts, list) or not opts:
                errors.append(f"{dw}: 'options' must be a non-empty list")
                continue
            opt_vals: set[str] = set()
            for o_idx, opt in enumerate(opts):
                ow = f"{dw}.options[{o_idx}]"
                if not isinstance(opt, dict):
                    errors.append(f"{ow}: must be an object")
                    continue
                val = opt.get("value")
                lbl = opt.get("label")
                if not isinstance(val, str) or not val.strip():
                    errors.append(f"{ow}: missing or empty 'value'")
                elif val in opt_vals:
                    errors.append(f"{ow}: duplicate option value '{val}'")
                else:
                    opt_vals.add(val)
                if not isinstance(lbl, str) or not lbl.strip():
                    errors.append(f"{ow}: missing or empty 'label'")

    return errors


def _check_table(tbl, where: str, errors: list[str]) -> None:
    if not isinstance(tbl, dict):
        errors.append(f"{where}: must be an object")
        return
    cols = tbl.get("columns")
    rows = tbl.get("rows")
    if not isinstance(cols, list) or not cols:
        errors.append(f"{where}: 'columns' must be a non-empty list")
        return
    if not isinstance(rows, list):
        errors.append(f"{where}: 'rows' must be a list")
        return
    width = len(cols)
    for r_idx, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != width:
            got = len(row) if isinstance(row, list) else type(row).__name__
            errors.append(f"{where}.rows[{r_idx}]: {got} cells, {width} columns")


def _check_block(block, bw: str, errors: list[str]) -> None:
    if not isinstance(block, dict):
        errors.append(f"{bw}: must be an object")
        return
    kind = block.get("type")
    if kind not in BLOCK_TYPES:
        errors.append(f"{bw}: unknown type '{kind}' (one of {sorted(BLOCK_TYPES)})")
        return
    for key in BLOCK_REQUIRED[kind]:
        if key not in block:
            errors.append(f"{bw}: '{kind}' needs '{key}'")
    if kind == "table" and "columns" in block and "rows" in block:
        _check_table(block, bw, errors)
    if kind == "callout":
        tone = block.get("tone")
        if tone is not None and tone not in TONES:
            errors.append(f"{bw}: tone must be one of {sorted(TONES)}")


# ---------------------------------------------------------------- rendering


def _render_table(tbl: dict) -> str:
    cols = tbl["columns"]
    head = "".join(
        f'<th class="num">{c["label"]}</th>' if isinstance(c, dict) and c.get("num")
        else f'<th>{c["label"] if isinstance(c, dict) else c}</th>'
        for c in cols
    )
    body_rows = []
    for row in tbl["rows"]:
        cells = []
        for idx, cell in enumerate(row):
            is_num = isinstance(cols[idx], dict) and cols[idx].get("num")
            cls = ' class="num"' if is_num else ""
            cells.append(f"<td{cls}>{_fmt(cell)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'


def _render_callout(callout) -> str:
    if isinstance(callout, str):
        return f'<div class="callout">{callout}</div>'
    tone = callout.get("tone", "neutral")
    cls = f"callout tone-{tone}" if tone != "neutral" else "callout"
    label = f'<span class="callout-label">{callout["label"]}:</span>' if callout.get("label") else ""
    return f'<div class="{cls}">{label}{callout["text"]}</div>'


def _render_block(b: dict) -> str:
    kind = b["type"]
    parts = []
    if b.get("heading"):
        parts.append(f'<h3>{b["heading"]}</h3>')
    if kind == "prose":
        parts.append("".join(f"<p>{p}</p>" for p in b["paragraphs"]))
    elif kind == "list":
        tag = "ol" if b.get("ordered") else "ul"
        parts.append(f'<{tag} class="plain">' + "".join(f"<li>{i}</li>" for i in b["items"]) + f"</{tag}>")
    elif kind == "kpis":
        items = []
        for k in b["items"]:
            unit = f'<span class="unit">{k["unit"]}</span>' if k.get("unit") else ""
            sub = f'<span class="sub">{k["sub"]}</span>' if k.get("sub") else ""
            items.append(f'<div class="kpi"><dt>{k["label"]}</dt><dd>{_fmt(k["value"])}{unit}{sub}</dd></div>')
        parts.append('<dl class="kpis">' + "".join(items) + "</dl>")
    elif kind == "table":
        parts.append(_render_table(b))
    elif kind == "callout":
        parts.append(_render_callout(b))
    elif kind == "diagram":
        parts.append(b["html"])
    if b.get("caption"):
        parts.append(f'<p class="caption">{b["caption"]}</p>')
    return '<div class="block">' + "".join(parts) + "</div>"


def _render_card(card: dict, sec_id: str) -> str:
    cid = _attr(card["id"])
    title_plain = _attr(card["title"])
    cat_raw = str(card.get("category") or "point").strip()
    cat_slug = _slugify(cat_raw)
    tone = card.get("tone", "neutral")
    badge_cls = f"badge tone-{tone}" if tone != "neutral" else "badge"
    badge = f'<span class="{badge_cls}">{html.escape(cat_raw)}</span>' if card.get("category") else ""

    body_parts = []
    if card.get("body"):
        body_parts.append(f'<p>{card["body"]}</p>')
    for p in card.get("paragraphs") or []:
        body_parts.append(f"<p>{p}</p>")
    if card.get("bullets"):
        body_parts.append('<ul class="plain">' + "".join(f"<li>{b}</li>" for b in card["bullets"]) + "</ul>")
    if card.get("code"):
        body_parts.append(f'<pre><code>{html.escape(str(card["code"]))}</code></pre>')
    if card.get("table"):
        body_parts.append(_render_table(card["table"]))
    if card.get("diagram"):
        body_parts.append(card["diagram"])
    if card.get("callout"):
        body_parts.append(_render_callout(card["callout"]))

    controls = (
        '<div class="card-controls">'
        '<button type="button" class="stance-btn" data-stance="agree" aria-pressed="false">Agree</button>'
        '<button type="button" class="stance-btn" data-stance="question" aria-pressed="false">Question</button>'
        '<button type="button" class="stance-btn" data-stance="change" aria-pressed="false">Change</button>'
        '<button type="button" class="stance-btn" data-stance="skip" aria-pressed="false">Skip</button>'
        '<button type="button" class="note-toggle">+ Add note / question</button>'
        '</div>'
        '<div class="note-wrap" hidden>'
        f'<textarea class="note-input" rows="2" placeholder="Add a note or question on {title_plain}…" aria-label="Note on {title_plain}"></textarea>'
        '</div>'
    )
    return (
        f'<article class="card" id="{cid}" data-kind="point" data-id="{cid}" '
        f'data-sec="{_attr(sec_id)}" data-cat="{_attr(cat_slug)}" data-title="{title_plain}">'
        f'<div class="card-head"><div class="card-title-wrap">{badge}<h3>{card["title"]}</h3></div></div>'
        f'<div class="card-body">{"".join(body_parts)}</div>'
        f'{controls}'
        '</article>'
    )


def _render_decision(dec: dict, sec_id: str) -> str:
    did = _attr(dec["id"])
    title_plain = _attr(dec["title"])
    cat_raw = str(dec.get("category") or "Decision").strip()
    cat_slug = _slugify(cat_raw)

    body_parts = []
    if dec.get("body"):
        body_parts.append(f'<p>{dec["body"]}</p>')

    opts_html = []
    for opt in dec["options"]:
        val = _attr(opt["value"])
        lbl_plain = _attr(opt["label"])
        rec = '<span class="opt-rec">Recommended</span>' if opt.get("recommended") else ""
        desc = f'<div class="opt-desc">{opt["desc"]}</div>' if opt.get("desc") else ""
        opts_html.append(
            '<label class="opt-label">'
            f'<input type="radio" name="dec-{did}" value="{val}" data-label="{lbl_plain}" />'
            f'<div><div class="opt-title">{opt["label"]}{rec}</div>{desc}</div>'
            '</label>'
        )
    body_parts.append('<div class="options">' + "".join(opts_html) + "</div>")

    controls = (
        '<div class="card-controls">'
        '<button type="button" class="note-toggle">+ Add note / question</button>'
        '</div>'
        '<div class="note-wrap" hidden>'
        f'<textarea class="note-input" rows="2" placeholder="Optional note on {title_plain}…" aria-label="Note on {title_plain}"></textarea>'
        '</div>'
    )
    return (
        f'<article class="card" id="{did}" data-kind="decision" data-id="{did}" '
        f'data-sec="{_attr(sec_id)}" data-cat="{_attr(cat_slug)}" data-title="{title_plain}">'
        f'<div class="card-head"><div class="card-title-wrap"><span class="badge tone-good">{html.escape(cat_raw)}</span>'
        f'<h3>{dec["title"]}</h3></div></div>'
        f'<div class="card-body">{"".join(body_parts)}</div>'
        f'{controls}'
        '</article>'
    )


def render(data: dict) -> tuple[str, str, str, str]:
    """Returns (header_extra_html, filter_pills_html, nav_html, body_html)."""
    header_parts = []
    if data.get("subtitle"):
        header_parts.append(f'<p class="brief-sub">{data["subtitle"]}</p>')
    if data.get("meta"):
        chips = "".join(f'<span class="meta-chip">{m}</span>' for m in data["meta"])
        header_parts.append(f'<div class="meta-row">{chips}</div>')

    categories: dict[str, str] = {}
    nav_items = []
    sections_html = []

    for idx, sec in enumerate(data["sections"], 1):
        sid = _attr(sec["id"])
        sec_parts = [
            f'<section class="section" id="{sid}">',
            f'<div class="sec-head"><span class="sec-num">{idx}</span><h2>{sec["title"]}</h2></div>',
        ]
        if sec.get("lede"):
            sec_parts.append(f'<p class="lede">{sec["lede"]}</p>')
        for block in sec.get("blocks") or []:
            sec_parts.append(_render_block(block))

        stack = []
        for card in sec.get("cards") or []:
            if card.get("category"):
                cat_raw = str(card["category"]).strip()
                categories.setdefault(_slugify(cat_raw), cat_raw)
            stack.append(_render_card(card, sec["id"]))
        for dec in sec.get("decisions") or []:
            cat_raw = str(dec.get("category") or "Decision").strip()
            categories.setdefault(_slugify(cat_raw), cat_raw)
            stack.append(_render_decision(dec, sec["id"]))
        if stack:
            sec_parts.append('<div class="card-stack">' + "\n".join(stack) + "</div>")
        sec_parts.append("</section>")
        sections_html.append("\n".join(sec_parts))

        nav_label = html.escape(_plain(sec.get("nav") or sec["title"]))
        nav_items.append(
            f'<li><a class="nav-link" href="#{sid}">'
            f'<span class="nav-text">{idx}. {nav_label}</span>'
            f'<span class="nav-count" data-sec-count="{sid}">0</span></a></li>'
        )

    nav_items.append('<li><a class="nav-link" href="#sec-overall"><span class="nav-text">Overall Notes</span></a></li>')
    pills_html = "".join(
        f'<button class="pill" type="button" data-filter="{_attr(slug)}">{html.escape(label)}</button>'
        for slug, label in categories.items()
    )
    return "\n".join(header_parts), pills_html, "\n".join(nav_items), "\n".join(sections_html)


def build_page(data: dict) -> str:
    page = TEMPLATE.read_text(encoding="utf-8")
    markers = [
        "/*__BRIEF_META__*/",
        "<!--__BRIEF_TITLE__-->",
        "<!--__BRIEF_HEADER_EXTRA__-->",
        "<!--__BRIEF_FILTER_PILLS__-->",
        "<!--__BRIEF_NAV__-->",
        "<!--__BRIEF_BODY__-->",
        "<!--__BRIEF_FOOTER__-->",
    ]
    missing = [m for m in markers if m not in page]
    if missing:
        raise ValueError(f"template is missing markers: {missing}")

    header_extra, pills_html, nav_html, body_html = render(data)
    title_plain = _plain(data["title"])
    storage_key = data.get("storageKey") or f"brief-{_slugify(title_plain)}"
    meta = {"title": title_plain, "storageKey": storage_key}
    meta_json = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")

    return (
        page.replace("/*__BRIEF_META__*/", meta_json)
        .replace("<!--__BRIEF_TITLE__-->", html.escape(title_plain))
        .replace("<!--__BRIEF_HEADER_EXTRA__-->", header_extra)
        .replace("<!--__BRIEF_FILTER_PILLS__-->", pills_html)
        .replace("<!--__BRIEF_NAV__-->", nav_html)
        .replace("<!--__BRIEF_BODY__-->", body_html)
        .replace("<!--__BRIEF_FOOTER__-->", data.get("footer", ""))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an interactive HTML brief from JSON data.")
    parser.add_argument("source", help="Path to JSON data file, or '-' to read JSON from stdin")
    parser.add_argument("output", nargs="?", default=None, help="Output .html path (optional when --publish is used)")
    parser.add_argument("--publish", action="store_true", help="Publish the built HTML via publish-brief and print its URL")
    parser.add_argument("--slug", default=None, help="Optional slug when using --publish")
    args = parser.parse_args(argv)

    if not args.output and not args.publish:
        parser.error("provide an output .html path, or pass --publish")

    try:
        raw = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to read JSON input: {exc}", file=sys.stderr)
        return 1

    errors = check(data)
    if errors:
        print("Data check failed:", *(f"  - {e}" for e in errors), sep="\n", file=sys.stderr)
        return 1

    try:
        page = build_page(data)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    cards = sum(len(s.get("cards") or []) for s in data["sections"])
    decisions = sum(len(s.get("decisions") or []) for s in data["sections"])

    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"wrote {target} ({len(data['sections'])} sections, {cards} cards, {decisions} decisions)", file=sys.stderr if args.publish else sys.stdout)
        if not args.publish:
            return 0
        publish_target = target
        cleanup_tmp = None
    else:
        slug_base = args.slug or (Path(args.source).stem if args.source != "-" else _slugify(data["title"]))
        tmp_dir = tempfile.TemporaryDirectory()
        cleanup_tmp = tmp_dir
        publish_target = Path(tmp_dir.name) / f"{_slugify(slug_base)}.html"
        publish_target.write_text(page, encoding="utf-8")

    try:
        cmd = [sys.executable, str(PUBLISH_SCRIPT), str(publish_target)]
        if args.slug:
            cmd.append(args.slug)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr.rstrip(), file=sys.stderr)
            return proc.returncode
        print(proc.stdout.strip())
        return 0
    finally:
        if cleanup_tmp is not None:
            cleanup_tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
