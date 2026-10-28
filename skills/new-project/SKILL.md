---
name: new-project
description: Start a new project (or adopt an existing one) with the agent kit - AGENTS.md shared by Claude, Codex and pi, make test/status/deploy/task/worker/finish, a pre-commit hook, a decision log, the Codex watcher and the ship-with-agents lead skill - so several agents can work on it in parallel from day one. Use when the user starts a new project or asks to set one up for multi-agent work.
---

# Set up a project with the agent kit

The kit is the folder two levels above this skill's real location: `KIT=$(cd -P <this skill's folder>/../.. && pwd)`, e.g. `cd -P ~/.claude/skills/new-project/../..` (see its `docs/guide.md`). Projects belong where the user keeps them (for example `~/lab` or `~/projects`), never directly in the home folder; if the user's instructions don't say where, ask.

1. **Name and place.** Agree on the project name and folder (`<projects folder>/<name>`). For an existing folder, look at what is there first: the installer never overwrites files, but an existing `AGENTS.md`, `Makefile` or hook will be kept and must be merged by hand.
2. **Install.** `bash "$KIT/install.sh" <projects folder>/<name> "<Project Name>"`. If `ship-with-agents` is not in `~/.claude/skills` (or `~/.agents/skills`), also run `bash "$KIT/install.sh" --link-skills` and report what it added or kept. Read its list of added and kept files and tell the user about any kept ones.
3. **Fill in `AGENTS.md`** from what the user has said: what it is, how it runs, data and rules, glossary. Leave a TODO where you don't know; ask rather than guess. Keep it short; the "Working with other agents" section stays as is.
4. **Set `agent-kit.conf`:** the service and health URL if the app runs as a service, test command, what task worktrees must link (untracked data, env files), what each worktree keeps its own, and PROTECTED files only the user may change.
5. **First decisions.** Add any decisions already made (stack, hosting, constraints) to `docs/decisions.md` with today's date.
6. **Commit** everything with a message that says the project starts from agent-kit and your agent trailer. The hook runs `make test`.
7. **Tell the user** what was set up, which TODOs remain, and how to run parallel agents: a lead uses the `ship-with-agents` skill and starts workers with `make worker NAME=x TIER=...`; workers never commit; one lead merges and deploys.
