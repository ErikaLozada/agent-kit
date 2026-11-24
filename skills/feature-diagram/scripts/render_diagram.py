#!/usr/bin/env python3
"""Shared Fern & Stone flow-diagram renderer for agent-kit projects.

Reads Fern & Stone light/dark colour tokens directly from the sibling
`interactive-html-brief/SKILL.md` definition (single source of truth), validates
diagram specs, and writes byte-stable, self-contained HTML pages plus a
`README.md` index — or emits an inline `<div class="fd-embed">` block for
embedding inside an interactive HTML brief.

Usage:
    python3 render_diagram.py scripts/diagrams.py [--out docs/diagrams] [--project "My App"]
    python3 render_diagram.py specs.json --out docs/diagrams
    python3 render_diagram.py scripts/diagrams.py --embed-slug my-feature
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

BRIEF_SKILL_MD = Path(__file__).resolve().parents[2] / "interactive-html-brief" / "SKILL.md"
CSP_HEADER = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; connect-src 'none'"
)
VALID_KINDS = {"", "card", "key", "out", "fail", "dashed"}
VALID_EDGE_STYLES = {"solid", "dash"}
VALID_EDGE_TONES = {"plain", "accent", "fail"}


def _extract_hex(text: str, pattern: str, label: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        raise ValueError(f"Could not parse Fern & Stone token '{label}' from {BRIEF_SKILL_MD}")
    return m.group(1).lower()


def load_theme_tokens(skill_md: Path = BRIEF_SKILL_MD) -> dict[str, dict[str, str]]:
    """Parse Fern & Stone light & dark hex tokens from interactive-html-brief/SKILL.md."""
    text = skill_md.read_text(encoding="utf-8")
    light_line = next((l for l in text.splitlines() if "**Light tokens" in l), "")
    dark_line = next((l for l in text.splitlines() if "**Dark tokens" in l), "")
    sem_line = next((l for l in text.splitlines() if "**Semantic colours" in l), "")
    if not (light_line and dark_line and sem_line):
        raise ValueError(f"Missing Fern & Stone token definitions in {skill_md}")

    light = {
        "bg": _extract_hex(light_line, r"canvas\s+`(#[0-9a-f]{6})`", "light.bg"),
        "panel": _extract_hex(light_line, r"thin panel surface\s+`(#[0-9a-f]{6})`", "light.panel"),
        "raised": _extract_hex(light_line, r"raised modal/popover\s+`(#[0-9a-f]{6})`", "light.raised"),
        "muted": _extract_hex(light_line, r"muted/secondary\s+`(#[0-9a-f]{6})`", "light.muted"),
        "text": _extract_hex(light_line, r"text\s+`(#[0-9a-f]{6})`", "light.text"),
        "sub": _extract_hex(light_line, r"secondary text\s+`(#[0-9a-f]{6})`", "light.sub"),
        "mute": _extract_hex(light_line, r"muted text\s+`(#[0-9a-f]{6})`", "light.mute"),
        "border": _extract_hex(light_line, r"hairline border\s+`(#[0-9a-f]{6})`", "light.border"),
        "input": _extract_hex(light_line, r"input border\s+`(#[0-9a-f]{6})`", "light.input"),
        "fern": _extract_hex(light_line, r"primary fern accent\s+`(#[0-9a-f]{6})`", "light.fern"),
        "on-fern": _extract_hex(light_line, r"primary fern accent\s+`#[0-9a-f]{6}`\s*\(`(#[0-9a-f]{6})`\s*text\)", "light.on-fern"),
        "wash": _extract_hex(light_line, r"selection wash\s+`(#[0-9a-f]{6})`", "light.wash"),
        "good": _extract_hex(sem_line, r"positive/good\s*=\s*blue\s*\(`(#[0-9a-f]{6})`\s*light", "light.good"),
        "warn": _extract_hex(sem_line, r"warning/change\s*=\s*burnt orange\s*\(`(#[0-9a-f]{6})`\s*light", "light.warn"),
        "bad": _extract_hex(sem_line, r"red\s*\(`(#[0-9a-f]{6})`\s*light", "light.bad"),
    }
    dark_surface = _extract_hex(dark_line, r"surface/popover\s+`(#[0-9a-f]{6})`", "dark.panel")
    dark = {
        "bg": _extract_hex(dark_line, r"canvas\s+`(#[0-9a-f]{6})`", "dark.bg"),
        "panel": dark_surface,
        "raised": dark_surface,
        "muted": _extract_hex(dark_line, r"muted\s+`(#[0-9a-f]{6})`", "dark.muted"),
        "text": _extract_hex(dark_line, r"text\s+`(#[0-9a-f]{6})`", "dark.text"),
        "sub": _extract_hex(dark_line, r"secondary text\s+`(#[0-9a-f]{6})`", "dark.sub"),
        "mute": _extract_hex(dark_line, r"muted text\s+`(#[0-9a-f]{6})`", "dark.mute"),
        "border": _extract_hex(dark_line, r"border\s+`(#[0-9a-f]{6})`", "dark.border"),
        "input": _extract_hex(dark_line, r"input border\s+`(#[0-9a-f]{6})`", "dark.input"),
        "fern": _extract_hex(dark_line, r"primary\s+`(#[0-9a-f]{6})`", "dark.fern"),
        "on-fern": _extract_hex(dark_line, r"primary\s+`#[0-9a-f]{6}`\s*\(`(#[0-9a-f]{6})`\s*text\)", "dark.on-fern"),
        "wash": _extract_hex(dark_line, r"selection wash\s+`(#[0-9a-f]{6})`", "dark.wash"),
        "good": _extract_hex(sem_line, r"positive/good\s*=\s*blue\s*\(`#[0-9a-f]{6}`\s*light\s*/\s*`(#[0-9a-f]{6})`\s*dark", "dark.good"),
        "warn": _extract_hex(sem_line, r"warning/change\s*=\s*burnt orange\s*\(`#[0-9a-f]{6}`\s*light\s*/\s*`(#[0-9a-f]{6})`\s*dark", "dark.warn"),
        "bad": _extract_hex(sem_line, r"red\s*\(`#[0-9a-f]{6}`\s*light\s*/\s*`(#[0-9a-f]{6})`\s*dark", "dark.bad"),
    }
    return {"light": light, "dark": dark}


def _css_vars(tokens: dict[str, str], prefix: str = "") -> str:
    return ";".join(f"--{prefix}{k}:{v}" for k, v in tokens.items())


def theme_css(prefix: str = "") -> str:
    tok = load_theme_tokens()
    l_vars = _css_vars(tok["light"], prefix)
    d_vars = _css_vars(tok["dark"], prefix)
    return (
        f":root{{{l_vars}}}\n"
        f'@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{d_vars}}}}}\n'
        f':root[data-theme="dark"]{{{d_vars}}}\n'
    )


PAGE_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:400 13px/1.5 "Geist","Segoe UI",system-ui,-apple-system,sans-serif}
code,.mono{font-family:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
code{font-size:.92em;background:var(--muted);border-radius:4px;padding:0 4px}
.mono{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--mute)}
.mono code{text-transform:none;letter-spacing:0}
b,h1,h2,h3,th{font-weight:600}
.top{position:sticky;top:0;z-index:5;height:40px;display:flex;align-items:center;gap:10px;padding:0 20px;background:var(--panel);border-bottom:1px solid var(--border)}
.top .mark{width:10px;height:10px;border-radius:2px;background:var(--fern);flex:none}
.top a{color:var(--sub);text-decoration:none}.top a:hover{color:var(--fern)}.top .sp{flex:1}
.top button{font:inherit;font-size:12px;background:var(--panel);color:var(--text);border:1px solid var(--input);border-radius:8px;padding:3px 10px;cursor:pointer}
.top button:hover{background:var(--wash)}
:focus-visible{outline:2px solid var(--fern);outline-offset:2px}
.wrap{width:100%;max-width:1360px;margin:0 auto;padding:24px 20px 32px}
.fd-header{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;border-bottom:1px solid var(--border);padding-bottom:16px}
.fd-kick{color:var(--fern)}
.fd-header h1,.fd-header h2{font-size:26px;line-height:1.25;margin:6px 0}
.fd-header p{margin:0;color:var(--sub);max-width:78ch}
.fd-kpis{display:flex;flex:none}
.fd-kpi{padding:0 14px;border-left:1px solid var(--border)}.fd-kpi:first-child{border-left:0}
.fd-kpi b{display:block;font-size:20px;white-space:nowrap;font-variant-numeric:tabular-nums}
.fd-phases{display:grid;column-gap:40px;margin:22px 0 6px}
.fd-phases div{display:flex;align-items:center;gap:10px}
.fd-phases div:before,.fd-phases div:after{content:"";flex:1;height:1px;background:var(--border)}
.fd-phases .accent{color:var(--fern)}.fd-phases .accent:before,.fd-phases .accent:after{background:var(--fern);opacity:.5}
.fd-heads,.fd-stage{display:grid;column-gap:40px}
.fd-heads{text-align:center;margin-bottom:4px}
.fd-heads b{display:block;font-size:13px;text-transform:none;letter-spacing:0;color:var(--text)}
.fd-heads .n{color:var(--fern)}
.fd-stage{position:relative;align-items:center;padding:20px 0}
svg.fd-wires{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.fd-col{display:flex;flex-direction:column;gap:24px;position:relative;z-index:1;min-width:0}
.fd-card{background:var(--panel);border:1px solid var(--input);border-radius:8px;padding:12px 14px}
.fd-card h3{font-size:16px;margin:2px 0 4px}
.fd-card p{margin:0;color:var(--sub);font-size:12.5px}
.fd-card.dashed{border-style:dashed}
.fd-card.key{background:var(--fern);border-color:var(--fern);color:var(--on-fern)}
.fd-card.key p,.fd-card.key .mono,.fd-card.key .fd-rows span:last-child{color:var(--on-fern);opacity:.88}
.fd-card.key code{background:transparent;padding:0;color:inherit}
.fd-card.out{border:2px solid var(--fern)}.fd-card.out .mono:first-child{color:var(--fern)}
.fd-card.fail{border-color:var(--warn);border-style:dashed}.fd-card.fail .mono:first-child{color:var(--warn)}
.fd-foot{display:flex;justify-content:space-between;gap:8px;border-top:1px solid var(--border);margin-top:10px;padding-top:6px;font-size:12px}
.fd-foot span:first-child{font-weight:600}.fd-foot span:last-child{color:var(--mute)}
.fd-rows{border-top:1px solid currentColor;margin-top:10px;padding-top:4px}
.fd-rows div{display:flex;justify-content:space-between;gap:10px;font-size:12px;padding:3px 0}
.fd-rows div span:first-child{font-weight:600}
.fd-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.fd-chips span{border:1px solid var(--border);background:var(--muted);border-radius:4px;padding:1px 6px;font-size:12px;color:var(--sub)}
ul.fd-items{list-style:none;margin:10px 0 0;padding:8px 0 0;border-top:1px solid var(--border)}
ul.fd-items li{font-size:12.5px;font-weight:600;padding:2px 0}
ul.fd-items li:before{content:"";display:inline-block;width:6px;height:6px;background:var(--fern);margin-right:8px;vertical-align:1px}
.fd-tray{background:var(--muted);border:1px solid var(--border);border-radius:8px;padding:18px 10px 10px;position:relative;display:flex;flex-direction:column;gap:8px}
.fd-tray>.mono{position:absolute;top:-10px;right:10px;background:var(--panel);border:1px solid var(--border);border-radius:4px;padding:0 6px}
.fd-mini{background:var(--panel);border:1px solid var(--border);border-radius:4px;padding:7px 10px}
.fd-mini b{display:block;font-size:12.5px}.fd-mini span{color:var(--mute);font-size:12px}
.fd-mini em{float:right;font-style:normal;color:var(--fern);font-size:12px}
.fd-panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px;margin-top:24px}
.fd-panel{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px 18px}
.fd-panel h2{font-size:17px;margin:4px 0 10px}
.fd-panel ol{margin:0;padding-left:18px;max-width:78ch}.fd-panel li{margin:5px 0;color:var(--sub)}.fd-panel li b{color:var(--text)}
.fd-panel table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.fd-panel th,.fd-panel td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12.5px}
.fd-panel th{color:var(--mute)}.fd-panel td.better{color:var(--good);font-weight:600}.fd-panel td.worse{color:var(--warn);font-weight:600}
.fd-note{color:var(--mute);font-size:12px;margin:8px 0 0}
.fd-footer{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;border-top:1px solid var(--border);margin-top:24px;padding-top:10px}
.fd-embed{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:18px 20px;margin:12px 0}
.fd-embed .fd-header h2{font-size:20px}
@media (max-width:1000px){.fd-heads,.fd-phases,svg.fd-wires{display:none}.fd-kpis{flex-wrap:wrap;row-gap:8px}.fd-stage{grid-template-columns:1fr!important;row-gap:14px}.fd-header{flex-direction:column;align-items:flex-start}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

DRAW_JS = """
function fdDrawStage(stage){
  var svg=stage.querySelector('svg.fd-wires');
  if(!svg||getComputedStyle(svg).display==='none')return;
  var r=document.documentElement,cs=getComputedStyle(r);
  var c={
    plain:(cs.getPropertyValue('--fd-input')||cs.getPropertyValue('--input')||'#77857c').trim(),
    accent:(cs.getPropertyValue('--fd-fern')||cs.getPropertyValue('--fern')||'#1d6a44').trim(),
    fail:(cs.getPropertyValue('--fd-warn')||cs.getPropertyValue('--warn')||'#9c5520').trim()
  };
  var s=stage.getBoundingClientRect(),edges=JSON.parse(stage.dataset.edges||'[]');
  function box(id){
    var el=stage.querySelector('[data-node-id="'+id+'"]');
    if(!el)return null;
    var e=el.getBoundingClientRect(),tray=el.closest('.fd-tray'),o=tray?tray.getBoundingClientRect():e;
    return{l:o.left-s.left,r:o.right-s.left,t:e.top-s.top,b:e.bottom-s.top,cx:(e.left+e.right)/2-s.left,cy:(e.top+e.bottom)/2-s.top};
  }
  svg.setAttribute('viewBox','0 0 '+s.width+' '+s.height);
  // Each wire bends, then runs level into the middle of its arrowhead; a target gets one head per side, in its
  // strongest tone. Cards in the same column are joined by a straight vertical wire.
  var HEAD=9,LEAD=8,rank={plain:0,accent:1,fail:2},heads={},h='';
  function head(key,tone,pts){if(!heads[key]||rank[tone]>rank[heads[key].tone])heads[key]={pts:pts,tone:tone};}
  edges.forEach(function(e){
    var a=box(e[0]),z=box(e[1]);
    if(!a||!z)return;
    var tone=e[3]||'plain';
    var line=' fill="none" stroke="'+c[tone]+'" stroke-width="'+(tone==='plain'?1.2:1.7)+'"';
    if(Math.abs(a.l-z.l)<2){
      var down=z.cy>a.cy,k=down?1:-1,end=down?z.t-1:z.b+1,b0=end-k*HEAD;
      h+='<path class="fd-wire" d="M'+a.cx+','+(down?a.b:a.t)+' L'+a.cx+','+(b0+k)+'"'+line+(e[2]==='dash'?' stroke-dasharray="4 4"':'')+'/>';
      head(e[1]+(down?'-top':'-bottom'),tone,[[a.cx-HEAD/2,b0],[a.cx,end],[a.cx+HEAD/2,b0]]);
      return;
    }
    var tip=z.l-1,base=tip-HEAD,bend=base-LEAD,m=(a.r+bend)/2,y=z.cy;
    h+='<path class="fd-wire" d="M'+a.r+','+a.cy+' C'+m+','+a.cy+' '+m+','+y+' '+bend+','+y+'"'+line+(e[2]==='dash'?' stroke-dasharray="4 4"':'')+'/>';
    h+='<path class="fd-lead" d="M'+bend+','+y+' L'+(base+1)+','+y+'"'+line+'/>';
    head(e[1],tone,[[base,y-HEAD/2],[tip,y],[base,y+HEAD/2]]);
  });
  Object.keys(heads).forEach(function(k){
    var d=heads[k];
    h+='<path class="fd-head" d="M'+d.pts.join(' L')+'z" fill="'+c[d.tone]+'"/>';
  });
  svg.innerHTML=h;
}
function fdDrawAll(){document.querySelectorAll('.fd-stage').forEach(fdDrawStage);}
"""

PAGE_JS = (
    "(function(){\n"
    + DRAW_JS
    + """
var K='agent-briefs-theme',r=document.documentElement,b=document.getElementById('theme');
var mq=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
function dark(){return r.dataset.theme?r.dataset.theme==='dark':Boolean(mq&&mq.matches);}
function label(){if(b)b.textContent=dark()?'Light':'Dark';}
try{var t=localStorage.getItem(K);if(t==='dark'||t==='light')r.dataset.theme=t;}catch(e){}
if(b){b.onclick=function(){r.dataset.theme=dark()?'light':'dark';try{localStorage.setItem(K,r.dataset.theme);}catch(e){}label();fdDrawAll();};}
if(mq){
  var onSys=function(){label();fdDrawAll();};
  if(mq.addEventListener)mq.addEventListener('change',onSys);
  else if(mq.addListener)mq.addListener(onSys);
}
label();
var home=document.getElementById('home');
if(home&&location.protocol==='file:')home.style.display='none';
addEventListener('resize',fdDrawAll);addEventListener('load',fdDrawAll);fdDrawAll();
})();
"""
)

EMBED_JS = (
    "(function(){\n"
    + DRAW_JS
    + """
if(!window.__fdEmbedWired){
  window.__fdEmbedWired=true;
  addEventListener('resize',fdDrawAll);
  addEventListener('load',fdDrawAll);
  var mq=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
  if(mq){if(mq.addEventListener)mq.addEventListener('change',fdDrawAll);else if(mq.addListener)mq.addListener(fdDrawAll);}
  if(window.MutationObserver){
    new MutationObserver(fdDrawAll).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  }
}
fdDrawAll();
})();
"""
)


def fmt_text(s: object) -> str:
    """Escape HTML; `backticks` become <code>, **double stars** become <b>."""
    out = html.escape(str(s), quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)


def iter_node_ids(spec: dict) -> list[str]:
    result: list[str] = []
    for col in spec.get("columns", []):
        for n in col.get("nodes", []):
            if n.get("tray"):
                for m in n["tray"]:
                    result.append(str(m["id"]))
            else:
                result.append(str(n["id"]))
    return result


def validate_spec(spec: dict) -> None:
    slug = spec.get("slug") or "<unnamed>"
    for req in ("slug", "short", "title", "columns", "edges"):
        if req not in spec:
            raise ValueError(f"{slug}: missing required key '{req}'")
    node_ids = iter_node_ids(spec)
    seen: set[str] = set()
    for nid in node_ids:
        if nid in seen:
            raise ValueError(f"{slug}: duplicate node id '{nid}'")
        seen.add(nid)
    for col in spec["columns"]:
        for n in col.get("nodes", []):
            if not n.get("tray"):
                kind = n.get("kind", "")
                if kind not in VALID_KINDS:
                    raise ValueError(f"{slug}: node '{n.get('id')}' has unknown kind '{kind}'")
    for edge in spec["edges"]:
        if len(edge) < 2:
            raise ValueError(f"{slug}: malformed edge {edge!r}")
        a, b = str(edge[0]), str(edge[1])
        if a not in seen or b not in seen:
            raise ValueError(f"{slug}: edge {a} -> {b} names an unknown node")
        style = edge[2] if len(edge) > 2 else "solid"
        tone = edge[3] if len(edge) > 3 else "plain"
        if style not in VALID_EDGE_STYLES:
            raise ValueError(f"{slug}: edge {a} -> {b} has invalid style '{style}'")
        if tone not in VALID_EDGE_TONES:
            raise ValueError(f"{slug}: edge {a} -> {b} has invalid tone '{tone}'")


def _render_node(n: dict, id_prefix: str = "") -> str:
    if n.get("tray"):
        minis = "".join(
            '<div class="fd-mini" id="%s" data-node-id="%s">%s<b>%s</b><span>%s</span></div>'
            % (
                html.escape(id_prefix + str(m["id"]), quote=True),
                html.escape(str(m["id"]), quote=True),
                "<em>%s</em>" % fmt_text(m["badge"]) if m.get("badge") else "",
                fmt_text(m["title"]),
                fmt_text(m.get("body", "")),
            )
            for m in n["tray"]
        )
        return '<div class="fd-tray"><div class="mono">%s</div>%s</div>' % (fmt_text(n.get("tag", "")), minis)
    kind = n.get("kind", "")
    cls = "fd-card" + (f" {kind}" if kind and kind != "card" else "")
    nid = str(n["id"])
    parts = [
        '<div class="%s" id="%s" data-node-id="%s">' % (cls, html.escape(id_prefix + nid, quote=True), html.escape(nid, quote=True)),
        '<div class="mono">%s</div><h3>%s</h3><p>%s</p>' % (fmt_text(n.get("tag", "")), fmt_text(n["title"]), fmt_text(n.get("body", ""))),
    ]
    if n.get("chips"):
        parts.append('<div class="fd-chips">%s</div>' % "".join("<span>%s</span>" % fmt_text(c) for c in n["chips"]))
    if n.get("rows"):
        parts.append('<div class="fd-rows">%s</div>' % "".join("<div><span>%s</span><span>%s</span></div>" % (fmt_text(a), fmt_text(b)) for a, b in n["rows"]))
    if n.get("items"):
        parts.append('<ul class="fd-items">%s</ul>' % "".join("<li>%s</li>" % fmt_text(i) for i in n["items"]))
    if n.get("foot"):
        left, right = n["foot"]
        parts.append('<div class="fd-foot"><span>%s</span><span>%s</span></div>' % (fmt_text(left), fmt_text(right)))
    return "".join(parts) + "</div>"


def _render_panel(p: dict) -> str:
    body = ""
    if p.get("table"):
        head, *rows = p["table"]
        body = "<table><tr>%s</tr>%s</table>" % (
            "".join("<th>%s</th>" % fmt_text(h) for h in head),
            "".join(
                "<tr>%s</tr>"
                % "".join(
                    '<td class="%s">%s</td>' % (html.escape(str(c[1]), quote=True), fmt_text(c[0]))
                    if isinstance(c, (tuple, list)) and len(c) == 2
                    else "<td>%s</td>" % fmt_text(c)
                    for c in r
                )
                for r in rows
            ),
        )
    if p.get("list"):
        body += "<ol>%s</ol>" % "".join("<li>%s</li>" % fmt_text(i) for i in p["list"])
    if p.get("note"):
        body += '<p class="fd-note">%s</p>' % fmt_text(p["note"])
    return '<div class="fd-panel"><div class="mono fd-kick">%s</div><h2>%s</h2>%s</div>' % (
        fmt_text(p.get("kicker", "")),
        fmt_text(p.get("title", "")),
        body,
    )


def _render_body(spec: dict, *, heading_tag: str = "h1", id_prefix: str = "") -> str:
    widths = " ".join(str(c.get("width", "1fr")) for c in spec["columns"])
    phases_html = ""
    if spec.get("phases"):
        phases_inner = "".join(
            '<div class="mono%s" style="grid-column:span %d">%s</div>'
            % (" accent" if accent else "", int(span), fmt_text(label))
            for label, span, accent in spec["phases"]
        )
        phases_html = f'<div class="fd-phases" style="grid-template-columns:{widths}">{phases_inner}</div>'
    heads = "".join(
        '<div class="mono"><span class="n">%02d</span><b>%s</b>%s</div>'
        % (i + 1, fmt_text(c["name"]), fmt_text(c.get("sub", "")))
        for i, c in enumerate(spec["columns"])
    )
    cols = "".join(
        '<div class="fd-col">%s</div>' % "".join(_render_node(n, id_prefix=id_prefix) for n in c.get("nodes", []))
        for c in spec["columns"]
    )
    kpis = "".join(
        '<div class="fd-kpi"><b>%s</b><span class="mono">%s</span></div>' % (fmt_text(v), fmt_text(k))
        for v, k in spec.get("kpis", [])
    )
    edges = html.escape(json.dumps([list(e) for e in spec["edges"]]), quote=True)
    panels = "".join(_render_panel(p) for p in spec.get("panels", []))
    panels_html = f'<div class="fd-panels">{panels}</div>' if panels else ""
    sources = spec.get("sources", "project code")
    flow = spec.get("flow", "")
    return (
        f'<div class="fd-header"><div>'
        f'<div class="mono fd-kick">{fmt_text(spec.get("kicker", ""))}</div>'
        f'<{heading_tag}>{fmt_text(spec["title"])}</{heading_tag}>'
        f'<p>{fmt_text(spec.get("lede", ""))}</p>'
        f'</div><div class="fd-kpis">{kpis}</div></div>\n'
        f"{phases_html}\n"
        f'<div class="fd-heads" style="grid-template-columns:{widths}">{heads}</div>\n'
        f'<div class="fd-stage" style="grid-template-columns:{widths}" data-prefix="{html.escape(id_prefix, quote=True)}" data-edges="{edges}">'
        f'<svg class="fd-wires" aria-hidden="true"></svg>{cols}</div>\n'
        f"{panels_html}\n"
        f'<div class="fd-footer mono"><span>Generated by make diagram from {fmt_text(sources)}. Do not edit by hand.</span>'
        f'<span>{fmt_text(flow)}</span></div>'
    )


def render(spec: dict, project: str | None = None) -> str:
    """Render a standalone, byte-stable, self-contained HTML flow diagram page."""
    validate_spec(spec)
    proj = project or spec.get("project") or ""
    topbar_label = f"{fmt_text(proj)} · {fmt_text(spec['short'])}" if proj else fmt_text(spec["short"])
    body = _render_body(spec, heading_tag="h1", id_prefix="")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP_HEADER}">\n'
        f"<title>{fmt_text(spec['title'])}</title><style>{theme_css()}{PAGE_CSS}</style></head><body>\n"
        f'<div class="top" data-brief-chrome="1"><a id="home" href="/">← All Briefs</a>'
        f'<span class="mark" aria-hidden="true"></span><b>{topbar_label}</b>'
        f'<span class="sp"></span><button id="theme" type="button">Dark</button></div>\n'
        f'<div class="wrap">\n{body}\n</div><script>{PAGE_JS}</script></body></html>\n'
    )


def render_embed(spec: dict, diagram_id: str | None = None) -> str:
    """Render a self-contained inline diagram fragment for embedding in an interactive-html-brief."""
    validate_spec(spec)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", diagram_id or str(spec["slug"])).strip("-") or "diagram"
    prefix = f"fd-{slug}-"
    body = _render_body(spec, heading_tag="h2", id_prefix=prefix)
    return (
        f'<style data-feature-diagram-css>{theme_css()}{PAGE_CSS}</style>\n'
        f'<div class="fd-embed" id="diagram-{html.escape(slug, quote=True)}">\n{body}\n</div>\n'
        f'<script data-feature-diagram-js>{EMBED_JS}</script>\n'
    )


def write_all(
    specs: list[dict],
    out: str | Path = "docs/diagrams",
    project: str | None = None,
    source_hint: str = "scripts/diagrams.py",
) -> list[str]:
    """Write `<slug>.html` for each spec plus a byte-stable `README.md` index."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[dict, str]] = []
    for spec in specs:
        html_doc = render(spec, project=project)
        path = out_dir / f"{spec['slug']}.html"
        path.write_text(html_doc, encoding="utf-8")
        written.append((spec, str(path)))
    index = [
        "# Feature diagrams",
        "",
        f"Generated by `make diagram` from `{source_hint}`. Do not edit by hand. Open the HTML files in a browser.",
        "",
    ]
    index += [f"- [{s['short']}]({s['slug']}.html) — {s['title']}" for s, _ in written]
    (out_dir / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return [p for _, p in written]


def load_specs_from_path(source: Path) -> list[dict]:
    """Load spec dicts from a `.json` file or a `.py` module exposing get_specs()/specs()/SPECS."""
    if source.suffix.lower() == ".json":
        raw = json.loads(source.read_text(encoding="utf-8"))
        return [raw] if isinstance(raw, dict) else list(raw)

    if source.suffix.lower() != ".py":
        raise ValueError(f"Unsupported spec source '{source}' (expected .py or .json)")

    repo_root = str(source.resolve().parent.parent if source.resolve().parent.name == "scripts" else source.resolve().parent)
    src_dir = str(source.resolve().parent)
    for p in (repo_root, src_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    mod_spec = importlib.util.spec_from_file_location("project_diagram_specs", str(source.resolve()))
    if mod_spec is None or mod_spec.loader is None:
        raise ImportError(f"Could not load specs module from {source}")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)

    if hasattr(mod, "get_specs") and callable(mod.get_specs):
        return list(mod.get_specs())
    if hasattr(mod, "specs") and callable(mod.specs):
        return list(mod.specs())
    if hasattr(mod, "SPECS"):
        return list(mod.SPECS)
    raise AttributeError(f"{source} must define get_specs(), specs(), or SPECS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Fern & Stone feature flow diagrams.")
    parser.add_argument("source", help="Path to project specs (.py exposing get_specs()/specs()/SPECS, or .json)")
    parser.add_argument("--out", default="docs/diagrams", help="Output directory (default: docs/diagrams)")
    parser.add_argument("--project", default=None, help="Project name shown in top bar")
    parser.add_argument("--embed-slug", default=None, help="Print inline embed HTML for one spec slug to stdout")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_file():
        print(f"feature-diagram: spec source not found: {source}", file=sys.stderr)
        return 1

    specs = load_specs_from_path(source)
    if args.embed_slug:
        match = next((s for s in specs if s.get("slug") == args.embed_slug), None)
        if not match:
            avail = ", ".join(str(s.get("slug", "")) for s in specs)
            print(f"feature-diagram: unknown slug '{args.embed_slug}' (available: {avail})", file=sys.stderr)
            return 1
        sys.stdout.write(render_embed(match))
        return 0

    project = args.project
    if not project:
        # Derive a clean default from cwd if none provided in spec or flag
        cwd_name = Path.cwd().name
        project = cwd_name.replace("-", " ").replace("_", " ").title() if cwd_name else None

    rel_hint = os.path.relpath(source, Path.cwd()) if source.is_absolute() else str(source)
    for path in write_all(specs, out=args.out, project=project, source_hint=rel_hint):
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
