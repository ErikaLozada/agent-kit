---
name: feature-diagram
description: >-
  Generate byte-stable, self-contained HTML flow diagrams (left-to-right stages,
  parallel fan-out/fan-in trays, and before/after tables) styled in the shared
  Fern & Stone palette. Use for major features, changes to how an existing
  feature works, multi-agent workflows, architecture sections of briefs, or
  whenever running `make diagram`.
---

# Feature Diagram (`make diagram`)

Document major features and architectural changes as generated, left-to-right flow diagrams in `docs/diagrams/*.html` (with an auto-generated `docs/diagrams/README.md` index).

## When to Draw One

- Shipping a **major new feature** or **changing how an existing feature works** (stages, locks, fallbacks, syncs, pipelines).
- Documenting a **multi-agent workflow** or release pipeline.
- Explaining an **architecture or feature change inside an `interactive-html-brief`** (embed the generated diagram inline via `--embed-slug` / `render_embed()`, never a screenshot).

## Core Rules

1. **Generate, never draw by hand.** Each diagram is a Python spec in the project (default `scripts/diagrams.py`). Model names, thresholds, limits, presets, and before/after numbers are **read from the project's code and result files at build time**, so the diagram updates whenever the code changes.
2. **Byte-stable output.** No timestamps, random IDs, or non-deterministic ordering — rebuilding when nothing changed produces zero git diff.
3. **Self-contained HTML.** Zero external URLs, fonts, or CDNs; strict `interactive-html-brief` CSP (`default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'`); stacks cleanly to one column on phones (`<= 1000px`).
4. **Shared theme (no duplicate tokens).** The renderer reads the Fern & Stone light/dark hex tokens directly from the sibling `interactive-html-brief` skill (`SKILL.md`): light by default, auto-follows system `prefers-color-scheme: dark`, manual Dark/Light toggle persisted on `agent-briefs-theme`, 40 px sticky top bar (`data-brief-chrome="1"`), semantic colours (blue good, burnt orange warning, red error only).
5. **Call the linked renderer; don't copy it.** Projects keep only their specs (`scripts/diagrams.py`). `make diagram` runs `scripts/diagram.sh`, which invokes `render_diagram.py` from the machine's linked skill folder (`install.sh --link-skills`).

## Spec Format

A project's `scripts/diagrams.py` exposes `get_specs()` (or `specs()` or `SPECS`) returning a list of spec dicts. Each spec dict has:

```python
{
    "slug": "checkout-pipeline",          # output filename: docs/diagrams/<slug>.html
    "short": "Checkout pipeline",         # short topbar & index label
    "project": "Example App",             # optional; defaults to repo folder name
    "kicker": "Checkout · since 2026-01", # small uppercase eyebrow
    "title": "From cart to confirmed order in three stages",
    "lede": "One-sentence summary of the flow.",
    "kpis": [("3", "stages"), ("2", "checks"), ("< 1 s", "p95")],
    "phases": [                           # (label, column_span, accent_bool)
        ("Validate · local", 2, False),
        ("Commit · external", 2, True),
    ],
    "columns": [
        {
            "name": "Input", "sub": "1 request", "width": ".95fr",
            "nodes": [
                {
                    "id": "req", "tag": "Start", "title": "Cart payload",
                    "body": "Validates items and totals before any charge.",
                    "chips": ["items", "currency", "idempotency key"],
                }
            ],
        },
        {
            "name": "Checks", "sub": "2 in parallel", "width": "1.15fr",
            "nodes": [
                {
                    "tag": "Parallel guards",
                    "tray": [
                        {"id": "stock", "title": "Inventory", "badge": "local", "body": "reserves stock"},
                        {"id": "fraud", "title": "Risk check", "body": "threshold from `config.py`"},
                    ],
                }
            ],
        },
        {
            "name": "Charge", "sub": "key stage", "width": "1.2fr",
            "nodes": [
                {
                    "id": "pay", "kind": "key", "tag": "Key stage", "title": "Payment",
                    "body": "Charges once using the idempotency key.",
                    "rows": [("Timeout", "10 s"), ("Retries", "2")],
                },
                {
                    "id": "err", "kind": "fail", "tag": "On failure", "title": "Release hold",
                    "body": "Rolls back the reservation and returns the error.",
                },
            ],
        },
        {
            "name": "Result", "sub": "output", "width": ".95fr",
            "nodes": [
                {
                    "id": "out", "kind": "out", "tag": "Output", "title": "Order receipt",
                    "body": "Stored atomically.",
                    "items": ["Order ID", "Line items", "Receipt URL"],
                }
            ],
        },
    ],
    # Edges: (from_id, to_id, style='solid'|'dash', tone='plain'|'accent'|'fail')
    "edges": [
        ("req", "stock", "solid"),
        ("req", "fraud", "solid"),
        ("stock", "pay", "dash"),
        ("fraud", "pay", "dash"),
        ("pay", "out", "solid", "accent"),
        ("pay", "err", "dash", "fail"),
    ],
    "panels": [
        {
            "kicker": "Before -> after",
            "title": "Measured impact",
            "table": [
                ("", "Before", "Now"),
                ("Duplicate charges", "3 / 1000", ("0 / 1000", "better")),
            ],
            "note": "Read from benchmark output.",
        },
        {
            "kicker": "Why it works",
            "title": "Design notes",
            "list": ["**Idempotent.** Retries never double-charge."],
        },
    ],
    "sources": "`config.py` and `checkout.py`",
    "flow": "request -> 2 checks -> payment -> receipt",
}
```

### Node Kinds & Edge Styles

- **Node `kind`:** `""` / `"card"` (default panel), `"key"` (highlighted fern stage), `"out"` (2 px fern output border), `"fail"` (dashed burnt-orange error/rejection path), `"dashed"` (optional/fallback stage), or a **`tray`** dict (`{"tag": "...", "tray": [...]}`) for parallel fan-out/fan-in parts.
- **Node extras:** `chips` (inline tags), `rows` (key/value pairs), `items` (bullet list), `foot` (`(left, right)` footer). Text supports `` `code` `` and `**bold**`.
- **Edges:** `(source_id, target_id, style, tone)` where `style` is `"solid"` or `"dash"`, and `tone` (optional) is `"plain"`, `"accent"`, or `"fail"`. Referencing an unknown node ID fails immediately with `ValueError`.
- **Before/after tables:** table cells may be plain strings or `(text, "better"|"worse"|"")` tuples.

## Commands

```sh
# Rebuild all project diagrams (from repo root)
make diagram

# Or run the renderer directly on a specs module or JSON file
python3 ~/.agents/skills/feature-diagram/scripts/render_diagram.py scripts/diagrams.py --out docs/diagrams

# Emit an inline embeddable HTML fragment for an interactive-html-brief
python3 ~/.agents/skills/feature-diagram/scripts/render_diagram.py scripts/diagrams.py --embed-slug <slug>
```

## Project Tests

Every project with `scripts/diagrams.py` should include a lightweight test (e.g. `tests/test_diagrams.py`) checking:
1. Key config/threshold values from code appear in the rendered HTML.
2. An edge pointing to an unknown node raises `ValueError`.
3. No external `http://` / `https://` `src` or `href` URLs appear.
4. Running the generator twice produces byte-identical output.
