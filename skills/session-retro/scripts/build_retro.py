#!/usr/bin/env python3
"""Build the interactive retrospective page from a data file.

  build_retro.py docs/retro-2026-11-14.json docs/retro-2026-11-14.html

The page is static HTML rendered here from the data, so it reads correctly in
previews, print and without JavaScript; the template's script only adds the note
controls, storage, Markdown export and the theme switch. The template is never
edited per project. The data shape is in ../references/data-schema.md.
Checks the data first and refuses to build on an error.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "template" / "retro.html"
TYPES = {"prose", "list", "kpis", "stack", "bars", "timeline", "table", "findings", "claims", "qa"}
REQUIRED = {
    "prose": ["paragraphs"], "list": ["items"], "kpis": ["items"], "stack": ["segments"], "bars": ["items"],
    "timeline": ["items"], "table": ["columns", "rows"], "findings": ["items"], "claims": ["items"], "qa": ["items"],
}
SEVERITIES = {"high", "medium", "low"}
VERDICTS = {"holds", "partly", "wrong", "unverified"}
TONES = {"model", "tool", "human", "other"}


def check(data: dict) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()

    def claim_id(value, where):
        if value is None:
            return
        if value in ids:
            errors.append(f"{where}: duplicate id '{value}' (notes are keyed by id)")
        ids.add(value)

    for key in ("title", "storageKey", "sections"):
        if key not in data:
            errors.append(f"missing top-level '{key}'")
    for s_index, section in enumerate(data.get("sections", [])):
        where = f"sections[{s_index}]"
        for key in ("id", "title"):
            if key not in section:
                errors.append(f"{where}: missing '{key}'")
        claim_id(section.get("id"), where)
        blocks = section.get("blocks") or ([section] if section.get("type") else [])
        for b_index, block in enumerate(blocks):
            bw = f"{where}.blocks[{b_index}]"
            kind = block.get("type")
            if kind not in TYPES:
                errors.append(f"{bw}: unknown type '{kind}' (one of {sorted(TYPES)})")
                continue
            for key in REQUIRED[kind]:
                if key not in block:
                    errors.append(f"{bw}: '{kind}' needs '{key}'")
            for i_index, item in enumerate(block.get("items", []) if isinstance(block.get("items"), list) else []):
                iw = f"{bw}.items[{i_index}]"
                if isinstance(item, dict):
                    claim_id(item.get("id"), iw)
                    if kind == "findings" and item.get("severity") and item["severity"] not in SEVERITIES:
                        errors.append(f"{iw}: severity must be one of {sorted(SEVERITIES)}")
                    if kind == "claims" and item.get("verdict") not in VERDICTS:
                        errors.append(f"{iw}: verdict must be one of {sorted(VERDICTS)}")
                    if kind in ("bars",) and not isinstance(item.get("value"), (int, float)):
                        errors.append(f"{iw}: bars need a numeric 'value'")
            if kind == "stack":
                for g in block.get("segments", []):
                    if g.get("tone", "other") not in TONES:
                        errors.append(f"{bw}: tone must be one of {sorted(TONES)}")
                    if not isinstance(g.get("value"), (int, float)):
                        errors.append(f"{bw}: segment '{g.get('label')}' needs a numeric value")
            if kind == "table":
                width = len(block.get("columns", []))
                for r_index, row in enumerate(block.get("rows", [])):
                    if len(row) != width:
                        errors.append(f"{bw}.rows[{r_index}]: {len(row)} cells, {width} columns")
    return errors


# ---------------------------------------------------------------- rendering
# Strings in the data are authored HTML (the agent writes them, viewers never do).


def _plain(value) -> str:
    return re.sub(r"<[^>]+>", "", str(value))


def _attr(value) -> str:
    return html.escape(_plain(value), quote=True)


def _fmt(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _note(note_id: str, title: str, placeholder: str | None = None) -> str:
    ph = f' data-placeholder="{_attr(placeholder)}"' if placeholder else ""
    return f'<div class="note" data-id="{_attr(note_id)}" data-title="{_attr(title)}"{ph}></div>'


def r_prose(b, t):
    return "".join(f"<p>{p}</p>" for p in b["paragraphs"])


def r_list(b, t):
    tag = "ol" if b.get("ordered") else "ul"
    return f'<{tag} class="plain">' + "".join(f"<li>{i}</li>" for i in b["items"]) + f"</{tag}>"


def r_kpis(b, t):
    cls = "k6" if len(b["items"]) >= 6 else "k4"
    out = []
    for k in b["items"]:
        unit = f'<span class="unit">{k["unit"]}</span>' if k.get("unit") else ""
        sub = f'<span class="sub">{k["sub"]}</span>' if k.get("sub") else ""
        out.append(f'<div class="kpi"><dt>{k["label"]}</dt><dd>{_fmt(k["value"])}{unit}{sub}</dd></div>')
    return f'<dl class="kpis {cls}">' + "".join(out) + "</dl>"


def r_stack(b, t):
    unit = b.get("unit", "")
    total = sum(g["value"] for g in b["segments"]) or 1
    label = ", ".join(f'{_plain(g["label"])} {g["value"]} {unit}' for g in b["segments"])
    segs, legend = [], []
    for g in b["segments"]:
        tone = g.get("tone", "other")
        pct = round(100 * g["value"] / total)
        inner = f'<span>{_fmt(g["value"])} {unit}</span>' if g["value"] / total > 0.12 else ""
        segs.append(f'<div class="seg tone-{tone}" style="flex:{g["value"]}" title="{_attr(g["label"])}: {g["value"]} {unit} ({pct}%)">{inner}</div>')
        legend.append(f'<li><i class="tone-{tone}"></i>{g["label"]} · {_fmt(g["value"])} {unit} ({pct}%)</li>')
    return (f'<div class="stack" role="img" aria-label="{_attr(label)}">' + "".join(segs) + "</div>"
            + '<ul class="legend">' + "".join(legend) + "</ul>")


def r_bars(b, t):
    unit = b.get("unit", "")
    top = max((i["value"] for i in b["items"]), default=1) or 1
    rows = []
    for i in b["items"]:
        detail = f' <small>· {i["detail"]}</small>' if i.get("detail") else ""
        hot = " hot" if i.get("hot") else ""
        rows.append(f'<div class="bar-row" role="listitem" title="{_attr(i["label"])}: {i["value"]} {unit}">'
                    f'<div class="bar-label"><span class="name">{i["label"]}{detail}</span>'
                    f'<span class="track"><span class="fill{hot}" style="width:{100 * i["value"] / top:.1f}%"></span></span></div>'
                    f'<span class="bar-val">{_fmt(i["value"])} {unit}</span></div>')
    return '<div class="bars" role="list">' + "".join(rows) + "</div>"


def r_timeline(b, t):
    out = []
    for i in b["items"]:
        cls = "human" if i.get("kind") == "human" else ("hot" if i.get("hot") else "")
        dur = f'<span class="tl-dur">{i["dur"]}</span>' if i.get("dur") else ""
        body = f'<p class="tl-body">{i["body"]}</p>' if i.get("body") else ""
        note = _note(i["id"], f'{t} · {i["name"]}') if i.get("id") else ""
        out.append(f'<li class="{cls}"><div class="tl-head"><span class="tl-time">{i["time"]}</span>'
                   f'<span class="tl-name">{i["name"]}</span>{dur}</div>{body}{note}</li>')
    return '<ol class="timeline">' + "".join(out) + "</ol>"


def r_table(b, t):
    cols = b["columns"]
    head = "".join(f'<th class="num">{c["label"]}</th>' if c.get("num") else f'<th>{c["label"]}</th>' for c in cols)
    body = "".join("<tr>" + "".join(
        f'<td class="num">{_fmt(cell)}</td>' if cols[n].get("num") else f"<td>{_fmt(cell)}</td>"
        for n, cell in enumerate(row)) + "</tr>" for row in b["rows"])
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def r_findings(b, t):
    out = []
    for n, f in enumerate(b["items"], 1):
        num = "" if b.get("numbered") is False else f"{n}. "
        tag = ""
        if f.get("severity"):
            mins = f' · {f["minutes"]} min' if f.get("minutes") is not None else ""
            tag = f'<span class="tag sev-{f["severity"]}">{f["severity"]}{mins}</span>'
        parts = [f'<div class="card-head"><h3>{num}{f["title"]}</h3>{tag}</div>']
        if f.get("body"):
            parts.append(f'<p>{f["body"]}</p>')
        if f.get("evidence"):
            parts.append(f'<p class="small"><span class="label">Evidence</span>{f["evidence"]}</p>')
        if f.get("fix"):
            parts.append(f'<p><span class="label">Change</span>{f["fix"]}</p>')
        if f.get("id"):
            parts.append(_note(f["id"], f'{t} · {f["title"]}'))
        out.append('<article class="card">' + "".join(parts) + "</article>")
    return '<div class="cards">' + "".join(out) + "</div>"


def r_claims(b, t):
    out = []
    for c in b["items"]:
        parts = [f'<div class="card-head"><span class="tag v-{c["verdict"]}">{c["verdict"]}</span><h3>“{c["claim"]}”</h3></div>',
                 f'<p>{c.get("finding", "")}</p>']
        if c.get("evidence"):
            parts.append(f'<p class="small"><span class="label">Evidence</span>{c["evidence"]}</p>')
        if c.get("id"):
            parts.append(_note(c["id"], f'Claim · {c["claim"]}'))
        out.append('<article class="card">' + "".join(parts) + "</article>")
    return '<div class="cards">' + "".join(out) + "</div>"


def r_qa(b, t):
    out = []
    for q in b["items"]:
        note = _note(q["id"], q["q"]) if q.get("id") else ""
        out.append(f'<dt>{q["q"]}</dt><dd>{q["a"]}{note}</dd>')
    return '<dl class="qa">' + "".join(out) + "</dl>"


RENDER = {"prose": r_prose, "list": r_list, "kpis": r_kpis, "stack": r_stack, "bars": r_bars,
          "timeline": r_timeline, "table": r_table, "findings": r_findings, "claims": r_claims, "qa": r_qa}


def render(data: dict) -> tuple[str, str]:
    body, nav = [], []
    for s in data["sections"]:
        parts = [f'<section id="{_attr(s["id"])}">', f'<h2>{s["title"]}</h2>']
        if s.get("lede"):
            parts.append(f'<p class="lede">{s["lede"]}</p>')
        for b in s.get("blocks") or [s]:
            if b.get("heading"):
                parts.append(f'<h3 style="margin-top:18px">{b["heading"]}</h3>')
            parts.append(RENDER[b["type"]](b, _plain(s["title"])))
            if b.get("caption"):
                parts.append(f'<p class="small">{b["caption"]}</p>')
        if s.get("note"):
            parts.append(_note(s["id"], _plain(s["title"]), None if s["note"] is True else s["note"]))
        parts.append("</section>")
        body.append("\n".join(parts))
        if s.get("nav") is not False:
            nav.append(f'<a href="#{_attr(s["id"])}">{s.get("nav") or s["title"]}</a>')
    nav.append('<a href="#notes">My notes</a>')
    return "\n".join(body), "".join(nav)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    source, target = Path(argv[1]), Path(argv[2])
    data = json.loads(source.read_text(encoding="utf-8"))
    errors = check(data)
    if errors:
        print("Data check failed:", *(f"  - {e}" for e in errors), sep="\n", file=sys.stderr)
        return 1
    page = TEMPLATE.read_text(encoding="utf-8")
    markers = ["/*__RETRO_DATA__*/", "<!--__RETRO_BODY__-->", "<!--__RETRO_NAV__-->", "<!--__RETRO_TITLE__-->",
               "<!--__RETRO_FOOTER__-->"]
    missing = [m for m in markers if m not in page]
    if missing:
        print(f"template is missing markers: {missing}", file=sys.stderr)
        return 1
    body, nav = render(data)
    meta = {k: data.get(k) for k in ("title", "storageKey", "notesFile")}  # the script needs only these
    page = (page.replace("/*__RETRO_DATA__*/", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))
                .replace("<!--__RETRO_BODY__-->", body)
                .replace("<!--__RETRO_NAV__-->", nav)
                .replace("<!--__RETRO_TITLE__-->", html.escape(_plain(data["title"])))
                .replace("<!--__RETRO_FOOTER__-->", data.get("footer", "")))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    notes = sum(1 for _ in _note_ids(data))
    print(f"wrote {target} ({len(data['sections'])} sections, {notes} note points)")
    return 0


def _note_ids(data):
    for section in data["sections"]:
        if section.get("note"):
            yield section["id"]
        for block in section.get("blocks") or [section]:
            for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
                if isinstance(item, dict) and item.get("id"):
                    yield item["id"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
