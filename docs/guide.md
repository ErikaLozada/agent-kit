# agent-kit guide

A lightweight, harness- and model-agnostic starting kit for AI-assisted projects — from solo sessions to parallel multi-agent teams. Built from real project lessons, keeping what worked and encoding recurring safeguards in hooks, scripts, and lean skills.

## Setup & commands

```sh
git clone <repo-url> ~/lab/agent-kit
bash ~/lab/agent-kit/install.sh --link-skills
bash ~/lab/agent-kit/install.sh ~/projects/my-project "My Project"
```

- **Linking skills (`--link-skills`):** Symlinks `skills/*` into every existing global skills directory (`~/.claude/skills`, `~/.agents/skills`, `~/.codex/skills`, `~/.gemini/config/skills`, `~/.pi/agent/skills`, `~/.hermes/skills`, plus any colon-separated paths in `AGENT_SKILLS_DIRS`). Never replaces an existing skill or foreign link. Because skills are symlinks, `git pull` updates them everywhere at once.
- **Checking drift (`--check <project>`):** Read-only report showing which template files are `ok`, `customized`, `missing`, or `project` (project-owned files like `AGENTS.md`, `agent-kit.conf`, `docs/decisions.md`).
- **Composing overlays (`--overlay <path-or-name>`):** Layers an optional external directory (or `~/.config/agent-kit/overlays/<name>`) on top of the generic starter template. Copies non-existing files (with `{{PROJECT}}`/`{{DATE}}` substitution), idempotently appends `AGENTS.append.md` to `AGENTS.md`, and merges `.gitignore.append` into `.gitignore`. This keeps `agent-kit` 100% generic while letting separate stack or domain kits plug cleanly on top.
- **Existing git hooks:** When adopting an existing repository that already sets `core.hooksPath` or has `.git/hooks/pre-commit`, `install.sh` preserves the existing hook setup and prints instructions to chain `.githooks/pre-commit` or opt in via `make setup`.
- **Self-test:** Run `make test` on Linux or macOS to verify installer behavior, test outcomes, review/worker/deploy scripts, `session-retro`, `interactive-html-brief`, and public-repo privacy hygiene.

## Global skills (`skills/`)

| Skill | Purpose |
| --- | --- |
| `new-project` | Runs `install.sh`, fills in `AGENTS.md` and `agent-kit.conf`, records initial decisions |
| `wrap-up` | Fast end-of-session hygiene & lesson capture: checks git state, mines session friction, routes approved lessons to their single owning source |
| `ship-with-agents` | Lead orchestration: learn the project, plan tasks with owned files and failure cases, start workers, relay prompts, cross-provider review, merge |
| `session-retro` | Quantitative retrospective from pi, Claude Code, and Codex transcripts, built into a Fern & Stone HTML page (zero external CDNs) |
| `interactive-html-brief` | Generates zero-dependency Fern & Stone interactive HTML briefs (Light default + Dark toggle) with single-prompt feedback export and an optional hardened local/Tailscale HTTPS server |
| `living-project-hub` | Multi-phase project & learning control center (progress tracks, `.scratch/execution-log.json`, formatted Markdown library, frozen phase snapshots, feedback save-back); pairs cleanly with `.planning/` / GSD workflows when installed |

## What a project gets (`template/`)

| File | Purpose |
| --- | --- |
| `AGENTS.md` | Instructions every harness reads, under 3 KB: commands, outside the repo, data, gates, defaults, working speed, conventions, glossary |
| `CLAUDE.md` | `@AGENTS.md`, so Claude Code reads the same file |
| `agent-kit.conf` | Project settings: `TEST_CMD`, `DEPLOY_CMD` / `SERVICE`, `HEALTH_URL`, `REVIEW_CMD`, `WORKER_CMD`, worktree `LINKS`/`OWN`, `PROTECTED` files |
| `Makefile` | `test`, `review`, `status`, `deploy`, `setup`, `task`, `worker`, `finish` |
| `scripts/test.sh` | Runs `TEST_CMD`, or discovers `unittest` and `node --test` suites with explicit `PASS` / `FAIL` / `SKIP` / `NOT_EVALUATED` outcomes |
| `scripts/review.sh` | `make review`: runs a second agent (`codex`, `claude`, `pi`, `gemini`, or custom `REVIEW_CMD`). Enforces read-only mode in headless runs and uses a repo-scoped tab inside herdr |
| `scripts/deploy.sh` | Enforces `main` branch, clean tree, and `scripts/test.sh --require-tests`, then runs `DEPLOY_CMD` (or `systemctl --user restart $SERVICE`), checks `HEALTH_URL`, and logs to `.deploys.log` |
| `scripts/status.sh` | Shows deploy status (when configured) and every git worktree's branch, dirty count, and task owner/status |
| `scripts/new-task.sh`, `finish-task.sh` | Creates a worktree, branch, symlinks (`LINKS` minus `OWN`), free test port, and `TASK.md`; cleans up only once merged into `main` |
| `scripts/start-worker.sh` | `make worker`: starts a worker using user tier presets from `~/.config/agent-kit/tiers.conf` (or explicit `KIND`/`MODEL`/`EFFORT` / `WORKER_CMD`) |
| `.githooks/pre-commit` | Runs `make test` on every commit; blocks `PROTECTED` edits, enforces append-only `docs/decisions.md`, and scans staged diffs for secret patterns (filenames/counts only) |
| `docs/decisions.md` | Append-only decision log |
| `.agents/skills/ship-feature` | Worker & solo change checklist; `.claude/skills` symlinks to `.agents/skills` |

## Harness- and model-agnostic configuration

- **Worker model tiers:** Configure personal tier preferences once in `~/.config/agent-kit/tiers.conf` (see `skills/ship-with-agents/references/models.md`), or override per project in `agent-kit.conf`. No vendor model IDs are hardcoded in project templates.
- **Custom CLIs:** Set `REVIEW_CMD` (with `{BASE}`, `{OUT}`, `{PROMPT}` placeholders) or `WORKER_CMD` (with `{WT}`, `{NAME}`, `{MODEL}`, `{EFFORT}` placeholders) in `agent-kit.conf` to plug in any current or future agent CLI.
- **Stack-agnostic deploys:** Set `DEPLOY_CMD` in `agent-kit.conf` to deploy via Docker, cloud CLIs, static hosting, or scripts on Linux or macOS while keeping all clean-tree, `--require-tests`, `HEALTH_URL`, and `.deploys.log` guardrails.
- **Harness sandboxes are runtime-specific:** Never assume a guardrail configured inside one CLI (such as one harness's deny-list or plugin) protects other CLIs. Enforce repo-wide invariants in git hooks and scripts, and mirror path restrictions in each harness you use.
- **Optional multi-phase planners (e.g. GSD):** `agent-kit` owns repo-level rules, hooks, and cross-session skills; if you use an external multi-phase planner that writes `.planning/` files (such as `gsd-core`), `living-project-hub` auto-discovers its roadmaps, plans, and summaries without making any planner a dependency of `agent-kit`.

## Concise memory & continuous learning

Keep one owning source for each kind of information:
- Current project rules → `AGENTS.md` (kept under 3 KB)
- Settled project choices → `docs/decisions.md`
- Domain/stack recurring traps → an external domain kit or overlay
- Universal workflow/guardrail improvements → `agent-kit` (`template/` or `skills/`)
- Temporary task state → `TASK.md` (deleted on `make finish`)

Run `wrap-up` at the end of a working session to mine real friction while context is fresh, filter out one-off noise, and promote only approved lessons (1–3 sentences: trigger → action → reason). Run `session-retro` at major milestones when you want quantitative transcript timing and turn-latency analysis.

## Readiness before complex work

For complex or materially ambiguous tasks, the lead marks readiness `required` and supplies a versioned brief with the intended outcome, constraints, acceptance checks, and file references. A worker in a fresh context reads that material and explains the outcome, constraints, verification plan, and unresolved gaps before editing code or tests. The lead checks the explanation against the evidence, fixes material gaps, records the checked version under `## Readiness`, and sends `[lead] PROCEED`. Small, well-specified tasks use readiness `brief` (a short restatement without a separate proceed exchange).

## Test outcomes and bootstrap policy

In installed projects, `make test` runs `TEST_CMD` when configured, otherwise discovers Python and JavaScript suites. Required runtimes must be available. The runner reports `PASS`, `FAIL`, `SKIP`, and `NOT_EVALUATED` separately; the commit hook keeps those summaries visible.

- By default, no suites executed returns exit 2 and blocks a commit. Empty or entirely skipped Python or JavaScript suites do not count as executed checks. JavaScript suites use `scripts/node-count-reporter.mjs` (Node 20+) to count executed cases cleanly.
- For initial scaffolding only, commit with `ALLOW_NO_TESTS=1 git commit ...` (or set `ALLOW_NO_TESTS=1` in `agent-kit.conf`). The commit succeeds while visibly reporting `NOT_EVALUATED`, never `PASS`.
- `OPTIONAL_TEST_SUITES="javascript"` (or `python`, or both) allows a missing runtime to skip only the named suite. Actual test failures always fail.
- `make deploy` calls `scripts/test.sh --require-tests`, so bootstrap policy can never deploy without executed checks.
- A custom `TEST_CMD` owns its own discovery and exit status; configure it to fail when required checks are missing.

## Developing the kit

Run `make test` before committing. Keep `template/` lightweight and generic: global analysis/briefing/orchestration tools belong in `skills/`, and stack-specific packs belong in external overlays. Template updates reach new installs automatically; existing projects can inspect drift with `install.sh --check <project>` and adopt changes selectively.
