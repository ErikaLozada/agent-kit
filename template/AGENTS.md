# {{PROJECT}}

TODO: one or two sentences on what this is and who it is for. Requirements: TODO (file). Decisions: `docs/decisions.md`. Results or status: TODO.

## Commands

| Command | Does |
| --- | --- |
| `make test` | Runs the tests; also run by the pre-commit hook on every commit |
| `make status` | What is live, every worktree with its task and owner, uncommitted changes |
| `make deploy` | Refuses unless on a clean, tested `main`; restarts the service, checks it answers, logs the commit |
| `make task NAME=x OWNER=y` | New branch and sibling worktree for a task, untracked files linked in, own test port, `TASK.md` |
| `make finish NAME=x` | Removes a task's worktree and branch once merged |
| `make worker NAME=x KIND=codex\|claude` | A task worktree plus a worker agent in its own herdr tab (named after the task), with worker permissions |
| `make setup` | Once per clone: turns on the git hooks in `.githooks/` |

Project settings for these commands: `agent-kit.conf`. Skills (in `.agents/skills/`, shared by Claude, Codex and pi): `ship-feature` for any code change, as a worker or alone. A lead running several agents uses the global `ship-with-agents` skill from agent-kit (plan, review rounds with another provider and a re-review of the fixes, relaying workers' prompts).

## How it runs

TODO: how to start it, where it runs, where keys live (never commit, print or send them anywhere), what must never be exposed.

## Data and rules

TODO: what data exists, what is tracked in git, what only the user may change (list those files under PROTECTED in `agent-kit.conf`).

## Working with other agents

- Before starting: check for other agents (`herdr agent list`) and `git status` / `make status`. Tell any peer which files you will change.
- Agents run in herdr panes (check `HERDR_ENV=1`), and herdr is the default channel for Claude and Codex alike: `herdr agent list` (who is there, idle/working/blocked), `herdr agent prompt <name> "..." --wait` (send and wait for the turn to end), `herdr agent read <name>` (read its reply). Run `herdr --skill` once for the full guide.
- Starting a worker: `make worker NAME=x TIER=simple|medium|complex` (or `KIND=codex|claude`), which creates the worktree, opens its own herdr tab named after the task and starts the agent with worker permissions (Codex: writes only its worktree, network allowed, asks for anything else; Claude: auto mode). Optional `MODEL=` and `EFFORT=` pick a cheaper model or lower effort; `TASK.md` records what each worker ran with. Fill in `TASK.md`, then brief it with `herdr agent prompt`. Workers appear in herdr's agent panel.
- Every message between agents starts with the sender's name in brackets, e.g. `[fix-search] READY ...` or `[lead] approved`. Text typed into a pane through herdr looks exactly like the user typing; an untagged message is the user's.
- A worker (the `Lead:` line in its `TASK.md` is not `none`) does not repeat the lead's checks or announcements: it reads `TASK.md`, works in its worktree, and reports to the lead. It never commits, merges or deploys: it writes its report under `## Report` in `TASK.md` and replies `[name] READY` (or `[name] BLOCKED <reason>`). The lead reviews the diff and commits it in the worktree with the worker's trailer (Codex's sandbox can't write git metadata anyway), then merges.
- A worker waiting on an approval shows as `blocked`. Workers never answer approvals; the lead tells the user what the worker wants and why, approves only what stays inside this project's rules, and asks the user for anything else.
- Outside herdr: Claude sessions with `ListAgents`/`SendMessage`; a Codex session with `python3 scripts/watch-codex.py --send "..."` (prints its reply when its turn ends).
- Parallel work goes in its own worktree and branch, one per task (`make task`), with its own test port. If a worktree can't carry the data a task needs, the lead instead gives each task its own files and a scratch folder in the main checkout. Never use `git stash`.
- One lead owns `main` and merges. Only the lead runs `make deploy`, and only after the user says to; others never restart the live service.
- Shared files have one writer at a time; name them in `TASK.md` and in the Data section above.
- State the contracts between tasks before going parallel: anything one task changes that another depends on (a data format, an API, a prompt, a command). Write them in `TASK.md`.
- Message peers before touching shared state, and when a branch is ready.
- Every commit names the agent that made it in a trailer, e.g. `Co-Authored-By: Claude <noreply@anthropic.com>` or `Co-Authored-By: Codex <noreply@openai.com>`.
- Size parallel work to how fast the user can review it: start with two agents.

## Choosing models (decided by the user, 2026-10-18)

The lead (orchestrator) runs on Claude Opus 5.5, or a newer top Claude model as one is released. Workers are picked by task tier; `make worker NAME=x TIER=simple|medium|complex` applies the preset.

| Tier | When | Worker |
| --- | --- | --- |
| simple | One small, mechanical change with an exact spec and no judgement: a rename, a copy edit, a config value, one function with given inputs and outputs | Codex `gpt-6-luna`, effort high |
| medium | A feature or fix of up to a few hundred lines with a written contract, tests and lead review (the shelf-links tasks) | Claude Haiku 5.5, effort high (`claude-haiku-5-5`); Sonnet 5.5, effort medium (`claude-sonnet-5-5`) when speed matters or the spec is looser |
| complex | Open design, unclear requirements, cross-cutting changes, or reasoning the contract can't pin down | Claude Opus 5.5, effort high (`claude-opus-5-5`) |

Escalate on evidence: a worker that fails its tests twice, keeps asking QUESTION: about the spec, or whose review finds a correctness bug is restarted one tier up. Measured on replays of three tasks (docs/tasks/replays.md): Haiku 6/6, Sonnet 6/6, luna 6/7 (one small real bug on a medium task), sol 5/6.

## Conventions

- Match the surrounding code. Small commits whose message says why. Commit finished work promptly.
- Shell scripts wrap their body in `{ ... exit; }` after the header comments, so bash reads the whole file first and editing a script cannot break a run in progress.
- Settled decisions go into `docs/decisions.md` (append; supersede rather than rewrite).
- Results and status are generated by a script, never copied into notes by hand.
- Add a rule here only after a real mistake shows it is needed; keep this file short.

## Glossary

TODO: terms whose meaning in this project differs from everyday use, and UI names that differ from code names.
