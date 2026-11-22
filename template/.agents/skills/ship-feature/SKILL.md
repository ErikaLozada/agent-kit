---
name: ship-feature
description: Make one change in this project, as a worker under a lead or working alone - read TASK.md, build test-first in your worktree on its test port, report to the lead (or review, commit and hand to the user when alone). Use when starting any code change, a feature or a fix. A lead running several agents uses the global ship-with-agents skill.
---

# Ship a feature

**Leading other agents?** Use the global `ship-with-agents` skill (`install.sh --link-skills` links it into your installed harnesses). It plans tasks, starts workers with `make worker`, relays prompts, reviews, commits and merges. If it isn't installed, follow the worker steps below for each task yourself.

**Worker** (the `Lead:` line in your `TASK.md` is not `none`):

1. **Read `TASK.md`**: goal, owned files, contracts, key decisions, worker discretion, failure cases, test server. Touch nothing else; if the task needs another file, ask the lead first. Never use `git stash`. Keep progress in the task; report reusable lessons with their reason and evidence so the lead can update the owning source once.
   **Check readiness before edits.** For `required` tasks (complex or materially ambiguous), use the brief and its referenced files (including project instructions) without requesting the lead's chat history. Send `[name] UNDERSTOOD` with the brief version, intended outcome, constraints, verification plan and unresolved gaps; record it under `## Readiness` or in the report the brief names. Do not edit code or tests until `[lead] PROCEED` for that version. Re-read and explain affected parts if the lead corrects the brief. For small, well-specified tasks marked `brief`, a short initial restatement and checks suffice unless a material ambiguity remains. If the mode is missing on complex or ambiguous work, use the required check. Readiness does not replace tests or review.
2. **Build test-first where you can.** Add or change tests in `tests/`, then the code, matching the surrounding style. Cover the failure cases `TASK.md` names (partial success, two operations at once, stale state, reruns) — bugs almost always hide in cases outside the happy path.
3. **Reuse existing helpers.** Never copy a rule or validation block into a second place when an existing helper can be shared.
4. **Check it in the running app** on your task's test port (`TASK.md`), never on the live service, and run `make test`. After fixing a bug, re-verify the exact failing scenario; changed code is not a confirmed fix.
5. **Check what it touches.** Write under `## Contracts` in `TASK.md` anything other work depends on that you changed (data format, API, prompt, command).
6. **Never commit, merge or deploy.** The lead reviews your diff and commits it in your worktree with your agent trailer.
7. **Report.** Under `## Report` in `TASK.md`: what changed (`file:line`), how you tested it, anything you could not verify, and any acceptance check you missed (with numbers). Then reply `[<your name>] READY`, or `[<your name>] BLOCKED <one line>` when you need a decision. Start every message with your name in brackets.

**Working alone** (no lead and no other active agents; check with `make status` and your terminal/harness peer list):

1. **Pin down done** in one or two sentences and which requirement or decision it serves (`AGENTS.md`, `docs/decisions.md`). If it changes a settled decision, ask the user first. For complex or materially ambiguous work, write a short design brief with outcome, constraints, acceptance checks and file references, and get a fresh context to critique it when available.
2. **Build test-first** on `main` (or a feature branch), covering failure/edge cases and reusing existing helpers.
3. **Commit** small commits whose message says why, staging explicit paths (avoid blind `git add -A`) with your agent trailer (`Co-Authored-By: ...`). The pre-commit hook runs tests, checks `PROTECTED` files, enforces append-only `docs/decisions.md`, and scans staged diffs for secrets.
4. **Review.** Run `make review KIND=<another-agent>` (or ask a second agent/the user to review the diff). Check for correctness, missed edge cases, and duplicated logic; re-verify fixes against the original failing scenarios.
5. **Hand over.** Before any push, confirm the remote repo's visibility and target branch. Run `make deploy` only when the user asks. Append settled decisions to `docs/decisions.md`. Tell the user what changed, what was tested, and what to check.
