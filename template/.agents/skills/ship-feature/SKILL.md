---
name: ship-feature
description: Make one change in this project, as a worker under a lead or working alone - read TASK.md, build test-first in your worktree on its test port, report to the lead (or review, commit and hand to the user when alone). Use when starting any code change, a feature or a fix. A lead running several agents uses the global ship-with-agents skill.
---

# Ship a feature

**Leading other agents?** Use the `ship-with-agents` skill from agent-kit (`install.sh --link-skills` links it into Claude, Codex and pi). It plans the tasks, starts workers with `make worker`, relays their prompts, reviews, commits and merges. If it isn't installed, follow `AGENTS.md` and run the worker steps below for each task yourself.

**Worker** (the `Lead:` line in your `TASK.md` is not `none`):

1. **Read `TASK.md`**: goal, the files you own, contracts, failure cases, test server. Touch nothing else; if the task needs another file, ask the lead first.
2. **Build test-first where you can.** Add or change tests in `tests/`, then the code, matching the surrounding style. Cover the failure cases `TASK.md` names (partial success, two operations at once, stale state, reruns).
3. **Check it in the running app** on your task's test port (`TASK.md`), never on the live service, and run `make test`.
4. **Check what it touches.** Write under Contracts in `TASK.md` anything other work depends on that you changed (data format, API, prompt, command).
5. **Never commit, merge or deploy.** The lead reviews your diff and commits it in your worktree with your agent trailer.
6. **Report.** Under `## Report` in `TASK.md`: what changed (file:line), how you tested it, anything you could not verify, and any acceptance check you missed, with the numbers. Then reply `[<your name>] READY`, or `[<your name>] BLOCKED <one line>` when you need a decision. Every message starts with your name in brackets.

**Working alone** (no lead and no other agents; check with `herdr agent list` and `make status`):

1. **Pin down done** in one or two sentences and which requirement or decision it serves (`AGENTS.md`, `docs/decisions.md`). If it changes a settled decision, ask the user first.
2. **Build test-first** on `main`, as in worker steps 2-3.
3. **Commit** small commits whose message says why, with your agent trailer (`Co-Authored-By: ...`). The pre-commit hook runs the tests.
4. **Review.** In Claude Code run `/code-review`; otherwise ask another agent or the user to read the diff. Besides correctness, check for duplicated logic: new code should build on existing helpers rather than copy their rules into a second place, which tests cannot catch. Fix what holds up.
5. **Hand over.** `make deploy` only when the user asks. New settled decisions go into `docs/decisions.md`. Tell the user what changed and what to check.
