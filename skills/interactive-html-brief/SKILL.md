---
name: interactive-html-brief
description: >-
  Use whenever presenting a large chunk of structured text to the user (reviews,
  plans, architecture proposals, audits, multi-option comparisons, or long
  reports) so the user can read comfortably in a browser page styled with the
  Fern & Stone palette, leave notes or questions on any point, and copy all
  feedback back as a single prompt.
---

# Interactive HTML Brief (Fern & Stone)

Generate a single-file, zero-dependency interactive HTML app whenever conveying large amounts of structured information to the user. Opens in calm **Fern & Stone Light** mode by default with an optional **Dark** toggle in the top bar.

## File Location & Remote-Ready Publishing

- Save to `~/agent-briefs/YYYY-MM-DD-<descriptive-slug>.html` (never pollute the project git repository unless the user asks).
- Before publishing, validate the inline `<script>` block for JS syntax errors when `node` is available (e.g., extract `<script>` to `/tmp/check.js` and run `node --check /tmp/check.js`).
- If your harness or sandbox requires writing to a scratch or temp directory first, save there and run:
  ```sh
  publish-brief /path/to/brief.html [optional-slug]
  ```
  `publish-brief` copies the `.html` file into `~/agent-briefs/` (`0600` permissions) and prints the clickable HTTPS URL for the current machine (configured via `~/.config/agent-briefs/config` or auto-detected from Tailscale).
- After writing/publishing the file, keep the chat reply short (2–4 lines) with the exact clickable URL printed by `publish-brief` (and the index URL from `publish-brief --url` when helpful).
- Never rely on a local `file://` URL alone when `publish-brief` is available — remote clients (tablets, phones, or another laptop over Tailscale) cannot open another machine's local `file://` paths.

## Required Design & UX (Fern & Stone · Tidepool)

1. **Palette & Theme Toggle (Follows System + Manual Dark/Light Toggle)**
   - **Light tokens (default):** canvas `#f8faf8`, thin panel surface `#fcfdfc`, raised modal/popover `#ffffff`, muted/secondary `#eef2ef`, text `#111a15` (16.9:1), secondary text `#46534b`, muted text `#5b6960` (5.5:1), hairline border `#d6ded8`, input border `#77857c` (3.7:1 WCAG 1.4.11), primary fern accent `#1d6a44` (`#ffffff` text), subtle hover/selection wash `#e2efe6`.
   - **Dark tokens (both `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` AND `:root[data-theme="dark"]`):** canvas `#0f1411`, surface/popover `#151b17`, muted `#1c241f`, text `#e8eeea`, muted text `#8a988f`, border `#2a342e`, input border `#6e7c73`, primary `#6cc08f` (`#0b130e` text), selection wash `#17291f`.
   - **Auto system theme + manual override:** Automatically follow `prefers-color-scheme: dark` (including live `window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)` updates when iPadOS/macOS/Linux switches appearance), and provide a **Dark / Light** button in the 40px topbar that sets `data-theme="dark"|"light"` and persists the explicit override in `localStorage`.
   - **Semantic colours (colour-blind safe):** positive/good = blue (`#3a64ad` light / `#7fa3e6` dark), warning/change = burnt orange (`#9c5520` light / `#d88b52` dark) — never green-vs-red; red (`#b42318` light / `#f28b82` dark) strictly for destructive actions and errors, always paired with text.
   - **Typography & Chrome (zero external CDNs):**
     - Fonts: `"Geist", "Segoe UI", system-ui, -apple-system, sans-serif` and `"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace` (uses Geist if installed locally; zero external Google Fonts or CDN links — strictly compliant with `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'`).
     - Weights `400` and `600` only; minimum text size `12px`; `tabular-nums` on KPIs, badges, and tables; visible 2px fern `:focus-visible` ring; respect `prefers-reduced-motion`.
     - **40px sticky topbar** (`data-brief-chrome="1"`) with a **`← All Briefs`** link (`href="/"`, hidden on `file://`), a 10px fern-green square mark, concise title, and **Dark / Light** toggle button persisted under the shared `agent-briefs-theme` `localStorage` key (matching `agent-briefs-server`, which also injects a fallback bar automatically for legacy briefs).
     - Thin hairline panels (`1px solid var(--border)`, `8px` radius, **no drop shadows on in-page cards**; shadows only on raised modals/popovers). Radii: `4px` inputs/tags, `8px` buttons/cards, `12px` modals.
2. **Responsive Screen Width (Tablet Landscape & Wide Monitors)**
   - Use fluid `width: 100%; max-width: 1360px; margin: 0 auto` with comfortable `16px–20px` side padding so tablets in landscape (`1024–1366px`) use the screen cleanly without wasted margins, while ultrawide displays cap neatly at `1360px` instead of stretching edge-to-edge.
   - Keep prose paragraphs and lists readable (`max-width: 78ch`) while letting cards, grids, KPI strips, and tables breathe across the full column width.
   - Sticky left section sidebar (`~236px`, with per-section annotation counters) on desktop/tablet-landscape; collapses gracefully on narrow viewports (`<= 900px`). Include top filter pills (including an **Annotated** filter).
3. **Card-based structure & Interactive feedback on every point**
   - Group scannable cards into numbered sections with clear category badges and callout boxes for takeaways/fixes.
   - Every content card includes toggleable stance buttons (**Agree**, **Question**, **Change**, **Skip**) and an expandable **+ Add note / question** textarea (auto-opens and focuses on **Question** or **Change**).
   - Decision points render as selectable radio-option cards (marking recommended options) plus an optional note box.
   - Include a final **Overall Notes / Extra Questions** textarea at the bottom.
   - Visually highlight annotated cards and persist all state in `localStorage` (unique key per document) with a **Reset** button.
4. **Single-Prompt Export**
   - Sticky bottom dock showing live feedback counts (e.g., `3 points · 2 decisions`) and a **Build & Copy Single Prompt** button.
   - Modal displaying clean structured Markdown containing *only* annotated points, stances, notes/questions, selected decisions, and general notes.
   - **Copy Prompt to Clipboard** button using `navigator.clipboard.writeText` with a `textarea.select()` + `document.execCommand('copy')` fallback and visible confirmation.
