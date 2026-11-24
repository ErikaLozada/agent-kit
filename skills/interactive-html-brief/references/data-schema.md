# Brief page data

One JSON object. Strings may contain inline HTML (`<code>`, `<strong>`, `<em>`, `<a>`); they are written by the agent, never by viewers. All `id` values (sections, cards, decisions) must be unique and stable across rebuilds because `localStorage` state and anchor links are keyed by `id`.

```json
{
  "title": "Architecture Review · Auth & Sessions",
  "subtitle": "Optional 1–2 sentence overview shown under the title.",
  "storageKey": "brief-auth-review-2026-11-24",
  "meta": ["2026-11-24", "4 points", "2 decisions"],
  "footer": "Optional footer HTML.",
  "sections": [ ... ]
}
```

- Required top-level fields: `title`, `sections` (non-empty array).
- `storageKey` is optional; if omitted, `build_brief.py` derives `brief-<slugified-title>`.

## Section

```json
{
  "id": "findings",
  "title": "Key Findings",
  "nav": "Findings",
  "lede": "Optional 1-sentence intro.",
  "blocks": [ ... ],
  "cards": [ ... ],
  "decisions": [ ... ]
}
```

Every section needs `id`, `title`, and at least one of `blocks`, `cards`, or `decisions`. `nav` overrides the sidebar label.

## Cards (annotatable points)

Each card gets **Agree / Question / Change / Skip** buttons and a **+ Add note / question** box.

```json
{
  "id": "c-token-ttl",
  "title": "Shorten refresh token TTL",
  "category": "Security",
  "tone": "warn",
  "body": "Refresh tokens currently live 90 days without rotation.",
  "paragraphs": ["Optional extra paragraphs."],
  "bullets": ["Bullet 1", "Bullet 2"],
  "code": "Optional preformatted code block (HTML-escaped automatically)",
  "table": { "columns": [{"label": "Metric"}, {"label": "Value", "num": true}], "rows": [["TTL", 90]] },
  "diagram": "<div class=\"fd-embed\">...</div>",
  "callout": { "label": "Fix", "text": "Rotate on use and cap at 14 days.", "tone": "good" }
}
```

- Required: `id`, `title`.
- `category`: shown as a badge and automatically adds a sidebar filter pill.
- `tone`: `neutral` (default), `good` (blue), `warn` (burnt orange), or `bad` (red).
- `callout`: either a plain HTML string or `{ "label"?, "text", "tone"? }`.

## Decisions (radio-option cards)

```json
{
  "id": "d-session-store",
  "title": "Where should active sessions live?",
  "category": "Decision",
  "body": "Optional context paragraph.",
  "options": [
    { "value": "redis", "label": "Redis with TTL", "desc": "Fast revocation.", "recommended": true },
    { "value": "db", "label": "Postgres table", "desc": "Fewer moving parts." }
  ]
}
```

- Required: `id`, `title`, `options` (non-empty; each option needs unique `value` and `label`).

## Blocks (non-card section content)

Optional supporting content rendered above a section's cards. Any block may include `heading` and `caption`.

| `type` | Required fields | Notes |
| --- | --- | --- |
| `prose` | `paragraphs: [html]` | Rendered as `<p>` elements (max 78ch) |
| `list` | `items: [html]` | Optional `ordered: true` |
| `kpis` | `items: [{label, value, unit?, sub?}]` | Responsive metric strip |
| `table` | `columns: [{label, num?}]`, `rows: [[cell]]` | Row width must match `columns` length |
| `callout` | `text` | Optional `label`, `tone` (`neutral`/`good`/`warn`/`bad`) |
| `diagram` | `html` | Raw `<div class="fd-embed">` from `feature-diagram` |
