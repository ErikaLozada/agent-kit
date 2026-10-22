# Merge plan: ship-with-agents into agent-kit

Lead: Claude (Opus 5.5, on the Mac). Reviewer: Codex, high reasoning. Branch `merge-ship-with-agents`, base `a4f7608`.
Approved by the user on 2026-10-23: merge (not delete), kit at `~/Desktop/projects/agent-kit` on the Mac, Codex
reviews this plan and then the merge.

## Why

The kit (this repo, on omarchy at `~/lab/agent-kit`) scaffolds a project for multi-agent work: template, `make`
commands, hooks, `new-project`. `ship-with-agents` (written on the Mac on 2026-10-23 from the Crate Digger and reelkit
sessions, currently in `~/.claude/skills/ship-with-agents` on the Mac only) is the lead's playbook for any repo:
review rounds, re-review of fixes, plan and brief templates, permission relay, isolation without worktrees, backends
(herdr, the Agent tool, `codex exec`). The overlap is the template's `ship-feature`, a second description of the
lead's work that has already drifted (the Mac has a Crate Digger copy).

## Target layout

```
agent-kit/
  skills/new-project/          unchanged except the link step (5)
  skills/ship-with-agents/     moved here: the one source; SKILL.md + references/backends.md, templates.md
  template/.agents/skills/ship-feature/   shortened: a worker checklist using the kit's make commands (2)
  template/AGENTS.md           synced with the skill (4)
  template/scripts/*.sh        macOS-safe (6)
  install.sh                   unchanged behaviour; links global skills only with --link-skills (5)
```

## Changes

1. **Move the skill.** Copy `~/.claude/skills/ship-with-agents/` into `skills/ship-with-agents/`. The Mac's
   `~/.claude/skills/ship-with-agents` becomes a symlink to it (done after the user approves the merge).
2. **Shrink `template/.agents/skills/ship-feature`** to a worker's checklist for kit projects: read `TASK.md`, work in
   the worktree, test-first, the task's test port, commit (Claude) or leave uncommitted (Codex), report
   `[name] READY` to the lead, never merge or deploy. Its description says: lead or solo work uses
   `ship-with-agents`. Keep the name so existing `AGENTS.md` references still resolve.
3. **Teach the skill about the kit.** In `ship-with-agents`:
   - Step 1: if the project has `agent-kit.conf`, its commands are `make test/status/task/worker/finish/deploy`;
     isolation is `make task`/`make worker` (worktree, links, test port, `TASK.md`); `PROTECTED` files are the user's.
   - Backends: kit worker settings as the defaults (Codex `--sandbox workspace-write --ask-for-approval on-request
     -c sandbox_workspace_write.network_access=true`; Claude `--permission-mode auto`, optional `--model`/`--effort`),
     replacing `-a never` for workers (keep `-a never` only for a read-only reviewer). `scripts/watch-codex.py` as the
     fallback for an interactive Codex session outside herdr, next to `codex exec`.
   - Commit trailer for Codex work: `Co-Authored-By: Codex <noreply@openai.com>`.
   - "Start with two agents; scale to how fast the user can review." Model IDs from the kit's table.
4. **Sync `template/AGENTS.md` "Working with other agents"** with the skill: a blocked worker's prompt is relayed by
   the lead with context (approve inside the project's rules, ask the user outside them) instead of "tell the user
   which pane"; review rounds use another provider and a re-review of the fixes against the baseline; when worktrees
   can't carry the data, owner files plus a scratch folder per task. Point to `ship-with-agents` for the lead.
5. **Global skill links.** `install.sh --link-skills` (new, opt-in) links every `skills/*` into `~/.claude/skills`,
   `~/.agents/skills` and `~/.pi/agent/skills` when those folders exist, never replacing a real folder or a link that
   points elsewhere (says what it skipped). Same rule as the installer: never overwrite. README documents it.
6. **macOS portability** (tests fail on the Mac today: `start-worker.sh` uses GNU `sed -i -e` with `\n` in the
   replacement):
   - `start-worker.sh`: edit `TASK.md` without `sed -i` (write to a temp file and move, or a small `python3`).
   - `new-task.sh`: port check falls back to `lsof -iTCP:$PORT -sTCP:LISTEN` when `ss` is missing.
   - `status.sh` / `deploy.sh`: `systemctl --user` is Linux-only; when `SERVICE` is set and `systemctl` is missing,
     say so plainly (deploy refuses; status prints "service status needs systemd") instead of failing oddly.
     A launchd deploy path is out of scope (no Mac project has a service yet).
7. **Tests.** Add: `--link-skills` (links into fake HOME folders, skips a real folder and a foreign link);
   `start-worker` writes `Lead:` and `Agent:` lines on macOS sed and GNU sed alike (the existing test already covers
   this once sed is gone); `ship-feature` mentions `ship-with-agents`. `make test` passes on the Mac and on omarchy.
8. **Docs.** README: what a project gets now includes the worker checklist and where the lead's skill lives;
   "Developing the kit" says both laptops share this repo. `docs/decisions.md` in the kit is not created (the kit has
   no decisions file); record the merge in the README's history line instead.

## Revisions after Codex's plan review (docs/review-plan.md, P1-P9; these win over the items above)

- **P1, worker protocol (user's decision: B).** Workers never commit, Claude or Codex, in any repo. In a kit project
  the lead reviews the diff in the task's worktree and commits there on the task branch with the worker's trailer
  (the pre-commit hook runs), then merges; elsewhere the lead commits in the shared folder, one commit per task.
  Every worker ends with `[name] READY` (or `[name] BLOCKED <reason>`). The report goes in `TASK.md` under
  `## Report` when the task has one, else in `review/task-<x>.md`. Updated together in: the skill's worker paragraph,
  step 7 and templates; the shortened `ship-feature`; `template/AGENTS.md`; `start-worker.sh`'s `Agent:` note
  ("leave work uncommitted" for both kinds).
- **P2, testing on omarchy.** After the push: `git -C ~/lab/agent-kit status --porcelain` must be empty; test the
  branch in a temporary worktree (`git worktree add /tmp/kit-merge merge-ship-with-agents && make -C /tmp/kit-merge
  test`), remove it, merge into `main` with `--ff-only` when possible, run `make test` on `main` again.
- **P3, `--link-skills`.** `install.sh --link-skills` is handled before the project argument and does nothing else
  (no folder, no git init). Tests: link mode with a fake HOME (links made, a real folder and a foreign link skipped
  and reported, rerun is a no-op), and the normal `install.sh <dir>` unchanged.
- **P4, Mac checkout.** After the merge on omarchy: commit everything on the branch first, then `git switch main &&
  git pull --ff-only origin main`, and check `git rev-parse HEAD` equals omarchy's tested `main`.
- **P5, skill swap.** Diff `~/.claude/skills/ship-with-agents` against the repo copy first (must be identical apart
  from this merge's edits); move it to `~/.claude/skills-backup/ship-with-agents-<date>` (outside the skills folder so
  it isn't loaded twice), link, check the link resolves and `SKILL.md` reads; delete the backup only after the user
  has used the linked skill once. Same on omarchy via `--link-skills` (nothing to back up there).
- **P6, kit path in the skill.** Steps 4-5 and backends: in a project with `agent-kit.conf` and a `worker` target,
  start workers with `make worker NAME=x TIER=...` from the main worktree, fill in `TASK.md`, then
  `herdr agent prompt`; the raw herdr recipe is for repos without the kit.
- **P7, adapted projects.** The skill reads the project's actual `Makefile`/scripts before using kit commands
  ("available only when present"). `new-project` finds the installer from its own resolved location
  (`<skill dir>/../../install.sh`), not `~/lab`, and says projects go where the user keeps them (`~/lab` on omarchy,
  `~/Desktop/projects` on the Mac).
- **P8, one source of truth.** `AGENTS.md` keeps project facts and short non-negotiable rules (tags, one lead,
  workers never commit or answer approvals, worktree per task) and points to `ship-with-agents` for the lead's
  procedure; the review-round and permission-relay procedure lives only in the skill. `new-project` runs
  `install.sh --link-skills` when `ship-with-agents` isn't linked. README says template edits don't reach existing
  projects (they adopt changes by hand).
- **P9, portability tests.** Add: `ss` hidden from PATH plus a bound local socket on `TEST_PORT` gives the next port
  (uses `lsof` on the Mac; skip if neither tool exists); `SERVICE` set with `systemctl` hidden gives status's message
  and deploy's refusal. Full suite on the Mac and on omarchy.

## Out of scope

- Crate Digger's adapted copies of the scripts and its own `ship-feature` (bring back separately).
- The Mac's stale `~/.claude/skills/ship-feature` (Crate Digger copy): left alone; the user decides.
- A GitHub remote.

## Delivery

1. Codex reviews this plan (file `docs/review-plan.md`); the lead adjusts the plan.
2. The lead implements on `merge-ship-with-agents`, one commit per numbered change, `make test` green on the Mac.
3. Codex reviews the merge: `git diff a4f7608..HEAD` (file `docs/review-merge.md`), status per plan item and new
   findings; fix round if needed.
4. With the user's go-ahead: push the branch to omarchy (`git push origin merge-ship-with-agents`; the checked-out
   `main` there is not touched), run `make test` there over SSH, merge into `main` on omarchy, pull on the Mac, then
   swap the Mac's `~/.claude/skills/ship-with-agents` for a link and link the skill on omarchy (`install.sh
   --link-skills`).
