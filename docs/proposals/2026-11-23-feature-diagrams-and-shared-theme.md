# Proposal: a shared `feature-diagram` skill and `make diagram`

Status: implemented in 776165f (skill, `make diagram`, brief embedding). For the next agent working on agent-kit. Written by the lead agent of the first project to adopt it (Crate Digger).

## What the user wants

Major features, and changes to how an existing feature works, are documented as a left-to-right flow diagram: stages as columns, fan-out to parallel parts, fan-in to one result, before/after numbers underneath. The user finds this much clearer than prose and wants it as the standard in every project.

## Decisions already made (do not re-ask)

1. **The theme already exists. Do not create a theme folder.** The Fern & Stone tokens and chrome are defined in the `interactive-html-brief` skill (also used by `living-project-hub` and `session-retro`). The diagram skill uses that definition: light by default, follows system dark mode, manual toggle on the shared `agent-briefs-theme` key, 40 px top bar, no external fonts or CDNs, semantic colours (blue good, burnt orange warning, red for errors only).
2. **The command is `make diagram`, not `make report`.** A project's `make diagram` rebuilds its diagrams. An agent that runs it, or is asked for a diagram, uses this skill for theme, layout and rules.
3. **Shared skill.** It lives in `skills/` like the brief and hub skills, so every project and harness gets it via `install.sh --link-skills`.
4. **Briefs embed diagrams.** When a brief covers an architecture or a feature change, it includes the diagram for it. The brief skill should say when to do this and how: an inline block rendered with the same renderer, not a screenshot.

## Rules learned from the first build

- **Generate it, never draw it by hand.** Each diagram is a spec in code. Model names, thresholds, limits, presets and before/after results are read from the project's code and result files when it builds, so the diagram changes when the code does.
- **Byte-stable output.** No timestamps or random ids, so rebuilding doesn't create diffs.
- **Self-contained HTML.** The briefs' Content-Security-Policy, no external URLs, and it stacks to one column on phones.

## Reference implementation (in the adopting project)

- `scripts/diagrams.py`:
  - Spec format: columns with nodes.
  - Node kinds: `card`, `key` (the highlighted stage), `out`, `fail`, `dashed`, and `tray` (a group of parallel parts).
  - Edges are `solid` or `dash`, in `plain`, `accent` or `fail` tones.
  - The renderer writes one HTML file per spec plus an index `README.md`.
  - Connectors are drawn from element positions by a few lines of inline JS.
- `tests/test_diagrams.py`:
  - Values appear as read from the code.
  - An edge to an unknown node fails.
  - No external URLs.
  - Output is the same on every run.
- `Makefile`: `diagram: python3 scripts/diagrams.py`.

## Work to do in agent-kit

1. **Add `skills/feature-diagram/`:**
   - `SKILL.md`: when to draw one (major feature, a change to how one works, a multi-agent workflow, an architecture section of a brief), the spec format, and the rule to read values from code.
   - A generic renderer script. It takes the theme from the `interactive-html-brief` definition, so there is no second copy of the tokens.
   - Projects keep only their specs and call the renderer from the linked skill folder (see below).
2. **Update `interactive-html-brief`** (and the hub if useful): a "Diagram" block type that embeds a rendered diagram when the brief covers an architecture or a feature change.
3. **Template:**
   - A `diagram` target in `template/Makefile`.
   - One line in `template/AGENTS.md` pointing at the skill (mind the 3 KB budget).
   - A step in `ship-with-agents` saying a major feature ships with its diagram.
4. **Tests:** for the renderer, and that the diagram skill and the brief skill use the same token values.
5. **Keep it public-safe:** no personal paths, hostnames or model IDs; examples use placeholder names.

## Renderer location (decided)

Projects call the renderer from the linked skill folder; they do not copy it. A project keeps only its specs (for example `scripts/diagrams.py` returning spec dicts), and its `make diagram` runs the skill's renderer on them. This keeps every project on the same version, like the briefs and hub. Because it needs the skills linked on every machine (`install.sh --link-skills`), `make diagram` must fail with a clear message naming that command when the skill folder is missing.

After the skill ships, the first project (Crate Digger) moves to it: `scripts/diagrams.py` keeps its specs and drops its own copy of the renderer and theme, and `make diagram` calls the skill. Tell that project's lead when the skill is ready.
