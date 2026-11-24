---
name: interactive-html-brief
description: >-
  Use for long, multi-section structured outputs (reviews, plans, architecture
  proposals, audits, multi-option comparisons, or long reports — roughly 3+
  sections or 40+ lines) where browser reading, point-by-point annotation, or
  decision picking adds value. Builds a self-contained Fern & Stone HTML page
  from compact JSON so the user can annotate and copy feedback back as one prompt.
---

# Interactive HTML Brief

Turn long, multi-section structured output (reviews, plans, audits, comparisons) into one self-contained HTML page. The user reads it in a browser, annotates any point, picks decisions, and copies all their feedback back as a single prompt.

Machine setup, restarting the server and troubleshooting are in this folder's `README.md`.

## When to use (and when not to)

- **Use a brief** for long, multi-section outputs (roughly 3+ sections or 40+ lines) where structured reading and point-by-point annotation or decision picking add real value: architecture proposals, deep code/security audits, multi-option trade-off comparisons, multi-phase plans, or long review reports.
- **Reply directly in chat** for short answers, single-section summaries, quick status updates, simple checklists, small diffs/code snippets, or yes/no questions. Do not build a brief when a few paragraphs in chat are faster to read and answer.

## Build & Publish (default workflow)

Write a compact JSON data file following `references/data-schema.md` instead of hand-coding HTML/CSS/JS, then render and publish it with `scripts/build_brief.py` (which uses `template/brief.html`, validates IDs/types/table widths, and keeps Fern & Stone styling and JS deterministic):

```sh
BRIEF_SKILL="$(cd -P <this skill's folder> && pwd)"

# Build to a file and publish in one step (prints the clickable URL):
python3 -I "$BRIEF_SKILL/scripts/build_brief.py" /tmp/review.json --publish --slug auth-review

# Or pipe JSON via stdin without creating a temp file:
python3 -I "$BRIEF_SKILL/scripts/build_brief.py" - --publish --slug auth-review <<'EOF'
{ "title": "Auth Review", "sections": [ ... ] }
EOF

# Or write a local .html file (optionally also --publish):
python3 -I "$BRIEF_SKILL/scripts/build_brief.py" /tmp/review.json /tmp/review.html [--publish --slug auth-review]
```

Then reply in chat in 2–4 lines with the printed URL (add the index URL from `publish-brief --url` if useful). Never give only a `file://` path: the user's other devices can't open it.

If you ever hand-author a custom `.html` page instead of using `build_brief.py`:
1. Write it as one `.html` file with no external files, fonts or CDNs.
2. If `node` is available, check the inline `<script>` with `node --check`.
3. Publish with `publish-brief /path/to/brief.html [optional-slug]`.

Rules:
- Don't save briefs in the project repo unless the user asks.
- Never move, rename or recreate `~/agent-briefs/`. If briefs are missing from the index, or `curl -s http://127.0.0.1:8766/health` reports an error, follow "Restart, check and fix" in `README.md`.

## Layout

- **Top bar:** 40px, sticky, with `data-brief-chrome="1"`. It holds a `← All Briefs` link (`href="/"`, hidden on `file://`), a 10px fern-green square, a short title and a Dark/Light button.
- **Width:** `width: 100%; max-width: 1360px; margin: 0 auto` with 16–20px side padding. Keep prose at `max-width: 78ch`; cards, grids and tables use the full width.
- **Sidebar:** sticky, about 236px wide, one link per section with its annotation count. Hide it at 900px and narrower. Put filter pills at the top, including **Annotated**.
- **Content:** numbered sections of cards, each with a category badge. Use callout boxes for takeaways and fixes.

## Feedback

- Every card has **Agree**, **Question**, **Change** and **Skip** buttons and a **+ Add note / question** box, which opens and takes focus on Question or Change. Annotated cards are highlighted.
- Decisions are radio-option cards (mark the recommended one) with an optional note.
- End the page with an **Overall Notes / Extra Questions** box.
- Save all state in `localStorage` under a key unique to the page, with a **Reset** button.
- A sticky bottom dock shows counts (e.g. `3 points · 2 decisions`) and a **Build & Copy Single Prompt** button. It opens a modal with Markdown containing only the annotated points, stances, notes, chosen decisions and overall notes, and a **Copy Prompt to Clipboard** button that confirms the copy. Use `navigator.clipboard.writeText`, falling back to `textarea.select()` + `document.execCommand('copy')`.

## Diagrams

When a brief explains an architecture, a multi-stage pipeline or a feature change, embed a generated flow diagram from the `feature-diagram` skill, never a screenshot or hand-drawn SVG:

```sh
python3 ~/.agents/skills/feature-diagram/scripts/render_diagram.py scripts/diagrams.py --embed-slug <slug>
```

Place the returned `<div class="fd-embed">` block in a `diagram` block or card `diagram` field (or call `render_embed(spec)` from `render_diagram.py`). It uses the same theme and works within the page's security policy.

## Theme: Fern & Stone

Light by default. Follow the system's dark mode, including live changes (`matchMedia('(prefers-color-scheme: dark)')` with a `change` listener). The Dark/Light button sets `data-theme="dark"|"light"` on `<html>` and saves the choice in `localStorage` under the shared key `agent-briefs-theme`. Apply the dark tokens in both `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` and `:root[data-theme="dark"]`.

Colours. The `feature-diagram` renderer reads these three lines, so keep each label and the wording around every value when you edit them:

- **Light tokens (default):** canvas `#f8faf8`, thin panel surface `#fcfdfc`, raised modal/popover `#ffffff`, muted/secondary `#eef2ef`, text `#111a15` (16.9:1), secondary text `#46534b`, muted text `#5b6960` (5.5:1), hairline border `#d6ded8`, input border `#77857c` (3.7:1 WCAG 1.4.11), primary fern accent `#1d6a44` (`#ffffff` text), subtle hover/selection wash `#e2efe6`.
- **Dark tokens:** canvas `#0f1411`, surface/popover `#151b17`, muted `#1c241f`, text `#e8eeea`, secondary text `#c5d0c9`, muted text `#8a988f`, border `#2a342e`, input border `#6e7c73`, primary `#6cc08f` (`#0b130e` text), selection wash `#17291f`.
- **Semantic colours (colour-blind safe):** positive/good = blue (`#3a64ad` light / `#7fa3e6` dark), warning/change = burnt orange (`#9c5520` light / `#d88b52` dark) — never green-vs-red; red (`#b42318` light / `#f28b82` dark) strictly for destructive actions and errors, always paired with text.

Type and shape:
- Fonts: `"Geist", "Segoe UI", system-ui, -apple-system, sans-serif`; monospace `"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace`. Geist is used only if installed locally; never load fonts from Google or a CDN.
- Weights 400 and 600 only. Text at least 12px. `tabular-nums` on numbers, badges and tables. A visible 2px fern `:focus-visible` ring. Respect `prefers-reduced-motion`.
- Panels: 1px `var(--border)` hairline and 8px radius, no shadows on in-page cards (shadows only on modals and popovers). Radii: 4px inputs and tags, 8px buttons and cards, 12px modals.
- The page must work under this Content-Security-Policy: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'`.
- Older briefs without a top bar get one added automatically by the briefs server.
