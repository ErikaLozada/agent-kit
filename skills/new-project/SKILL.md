---
name: new-project
description: Start a new project (or adopt an existing one) with the agent kit - lean harness-neutral AGENTS.md, make test/review/status/deploy/task/worker/finish, a pre-commit hook, a decision log, and global skills (ship-with-agents, wrap-up, session-retro, interactive-html-brief, living-project-hub) - so any agent or parallel team starts with proven rules from day one. Use when the user starts a new project or asks to set one up.
---

# Set up a project with the agent kit

The kit is the folder two levels above this skill's real location: `KIT=$(cd -P <this skill's folder>/../.. && pwd)`, e.g. `cd -P ~/.agents/skills/new-project/../..` (see its `docs/guide.md`). Projects belong where the user keeps them (for example `~/lab` or `~/projects`), never directly in the home folder; if the user's instructions don't say where, ask.

1. **Name and place.** Agree on the project name and folder (`<projects folder>/<name>`), and whether any optional stack/domain overlay (`--overlay <path-or-name>`) should be layered on top. For an existing folder, inspect what is there first: the installer never overwrites files or silently disables existing git hooks, so an existing `AGENTS.md`, `Makefile`, or hook must be merged by hand.
2. **Install.** Run `bash "$KIT/install.sh" <projects folder>/<name> "<Project Name>"` (adding `--overlay <path-or-name>` if requested). If global skills are not yet linked, also run `bash "$KIT/install.sh" --link-skills` and report what it added or kept. Read the installer's output and tell the user about any kept files or hook notes.
3. **Fill in `AGENTS.md`** from what the user has said: what it is, outside the repo (read-only, needs a go-ahead, standing approvals), data and never-read paths, gates, defaults, glossary. Ask the user for the gates and defaults; they decide most of a project's speed. Leave a TODO where you don't know; ask rather than guess. Keep it under 3 KB: every agent reads it every session.
4. **Set `agent-kit.conf`:** `TEST_CMD`, `DEPLOY_CMD` (or `SERVICE` + `HEALTH_URL`), optional `REVIEW_CMD`/`WORKER_CMD`, what task worktrees must link (`LINKS`) or keep separate (`OWN`), and `PROTECTED` files only the user may change.
5. **First decisions.** Add any decisions already made (stack, hosting, constraints) to `docs/decisions.md` with today's date.
6. **Commit** everything with a message saying the project starts from agent-kit and your agent trailer. The hook runs `make test`; if the project has no tests yet, commit with `ALLOW_NO_TESTS=1 git commit ...` (reported as `NOT_EVALUATED`).
7. **Tell the user** what was set up, which TODOs remain, and the core workflow: `make test`, `make review KIND=<agent>`, `wrap-up` at the end of a session to capture lessons, and `ship-with-agents` + `make worker` when scaling to parallel agents.
