# Merge plan review

## Findings

### P1 — high — plan items 2–4; `skills/ship-with-agents/SKILL.md:11–13,74–77`; `skills/ship-with-agents/references/templates.md:59–65`

**Problem:** The planned worker checklist says Claude workers commit and report `[name] READY`, while the lead skill and its worker brief still say every worker must not commit, must write a report file, and must reply `DONE`. Merely adding kit commands, a Codex trailer, and a shortened `ship-feature` does not reconcile those instructions.

**Scenario:** A lead starts a Claude worker with `make worker` and the global brief. The worker loads the project-local skill, commits, and says READY; the lead expects uncommitted changes and a `review/task-*.md` report, so its per-task commit and review workflow cannot be followed as written.

**Fix:** Choose one kit worker protocol and update the global skill, both brief templates, `ship-feature`, and `AGENTS.md` together. State explicitly whether Claude commits, who writes the report, and the exact completion message; keep a separate rule for non-kit repositories if needed.

### P2 — high — plan Delivery 4 (`docs/merge-plan.md:78–80`)

**Problem:** Pushing a new branch to the non-bare omarchy repository is valid while `main` is checked out, but `make test` run over SSH in that checkout tests the old `main`, not the pushed branch.

**Scenario:** The branch contains a Linux-only failure. `git push origin merge-ship-with-agents` succeeds, SSH runs `make test` in `~/lab/agent-kit` on `main`, and the green result is mistakenly used to approve the merge.

**Fix:** Test the pushed branch in a temporary omarchy worktree (or explicitly switch to it after verifying a clean checkout), then merge into `main` and test the merged `main` as well. Confirm the omarchy checkout is clean before merging; do not push into its checked-out branch.

### P3 — high — plan item 5 and Delivery 4 (`docs/merge-plan.md:49–51,80–81`); `install.sh:5–9`

**Problem:** The proposed standalone `install.sh --link-skills` command needs a separate argument path before the current project-directory handling. Today `$1` is always interpreted as `DIR`, and the script creates it, initializes Git, and copies the template.

**Scenario:** The Delivery command is run with only `--link-skills`; without early dispatch, it creates a project named `--link-skills` in the current directory instead of linking global skills.

**Fix:** Define and test the exact CLI grammar, dispatch `--link-skills` before `DIR`/`NAME`, and keep ordinary `install.sh <project> [name]` behavior unchanged. Make link mode operate from the kit root without initializing a project.

### P4 — high — plan Delivery 4 (`docs/merge-plan.md:78–80`)

**Problem:** The Mac is currently on `merge-ship-with-agents`, which has no upstream. A plain `git pull` after omarchy merges `main` either fails for lack of an upstream or pulls into the wrong local branch.

**Scenario:** Omarchy merges successfully, then the Mac's `git pull` stops with “There is no tracking information for the current branch”; the later symlink points into a checkout that still contains the feature branch.

**Fix:** After all review files and local changes are committed or otherwise preserved, switch the Mac checkout to `main` and run an explicit fast-forward pull from `origin main`. Verify its HEAD is the tested omarchy merge commit before replacing the skill path.

### P5 — medium — plan item 1 and Delivery 4 (`docs/merge-plan.md:30–31,80–81`)

**Problem:** The Mac's current `~/.claude/skills/ship-with-agents` is a real directory. “Swap” does not specify how to preserve it or recover if link creation fails; `--link-skills` deliberately skips a real directory under the never-overwrite rule.

**Scenario:** The copied repository skill is missing a local reference file, or the target path is wrong. Deleting the original and creating the symlink removes the working skill; calling `--link-skills` alone silently leaves the old copy in place.

**Fix:** Compare the committed copy with the source, move the existing directory to a uniquely named backup, create and resolve the symlink to the final Mac `main` checkout, and retain a rollback step. Only remove the backup after both the link and skill contents are verified.

### P6 — medium — plan items 3–4 (`docs/merge-plan.md:36–48`); `skills/ship-with-agents/SKILL.md:67–77`; `skills/ship-with-agents/references/backends.md:13–23`

**Problem:** The plan says kit isolation uses `make task`/`make worker`, but the global backend recipes still create a tab with `--cwd "$PWD"` and start an agent directly. They also unconditionally tell workers not to commit. A lead can therefore follow the global recipe in the main checkout and bypass the kit's task worktree and `TASK.md`.

**Scenario:** In a scaffolded project, the lead reads the backend recipe, runs it from `main`, and gives the worker a task. The worker edits `main` without its assigned port, owner record, or branch.

**Fix:** Make the kit path explicit in the lead skill and backends: run `make worker` from the main worktree, fill `TASK.md`, and prompt the named agent; reserve the direct herdr recipe for repositories without the kit. Document the owner-file/scratch-folder fallback when a worktree cannot carry required data.

### P7 — medium — plan item 3 (`docs/merge-plan.md:36–44`); `skills/new-project/SKILL.md:8–11`

**Problem:** Treating the presence of `agent-kit.conf` as proof that all six make targets have the template's behavior is unsafe for adapted kit projects. `new-project` also hard-codes `~/lab/agent-kit`, whereas the Mac checkout named in this plan is elsewhere.

**Scenario:** Crate Digger has adapted script copies or a removed target, but the lead assumes the current template behavior and runs `make worker` or `make finish` incorrectly. On the Mac, a new-project invocation points to a missing `~/lab/agent-kit/install.sh`.

**Fix:** Have the lead inspect the project's actual `Makefile`, config, and scripts before selecting commands; describe kit commands as available only when present. Update `new-project` to locate this repository's installer from the skill location or a documented configurable path, and test that path on both machines.

### P8 — medium — plan items 2, 4–5 (`docs/merge-plan.md:32–35,45–51`); `template/AGENTS.md:17,27–42`; `skills/new-project/SKILL.md:11–12`

**Problem:** The plan puts generic review rounds, permission handling, and isolation procedure in both `ship-with-agents` and template `AGENTS.md`, recreating the two sources of truth it aims to remove. It also tells project-local `ship-feature` to send a lead to a global skill that ordinary project installation and `new-project` do not ensure is installed.

**Scenario:** A fresh project is scaffolded with the normal installer. `AGENTS.md` and the worker skill refer to `ship-with-agents`, but no global link exists; a later update changes the lead skill's review procedure without updating the copied `AGENTS.md` in existing projects.

**Fix:** Keep project facts and non-negotiable rules in `AGENTS.md`, put the detailed lead procedure in the global skill, and make the project-local reference conditional or provide a working installation step. Update `new-project` and README to explain the opt-in link and how existing projects migrate their copied instructions; do not imply template edits update them.

### P9 — medium — plan items 6–7 (`docs/merge-plan.md:52–61`); `template/scripts/new-task.sh:21–22`; `template/scripts/status.sh:7–9`; `template/scripts/deploy.sh:7–13`

**Problem:** The tests planned for portability cover only the `sed` fix. They do not exercise the new macOS port fallback or the missing-`systemctl` status/deploy branches. The existing task test only proves ports listed in `TASK.md` are skipped, not ports already bound by a process.

**Scenario:** On macOS, another process listens on `TEST_PORT` and `ss` is unavailable. An incorrect `lsof` invocation assigns that busy port; all current and planned tests still pass. A status/deploy guard that checks after calling `systemctl` would likewise pass the default no-service test.

**Fix:** Add focused tests that hide `ss` and bind a local listening socket, then assert a different port is assigned; set `SERVICE` with `systemctl` unavailable and assert status's message and deploy's refusal. Run the full suite on both macOS and omarchy.

## Could not verify

- The actual contents of the Mac's original `~/.claude/skills/ship-with-agents` against the untracked copy in this checkout, or whether either laptop has pre-existing global skill links and local edits.
- The omarchy checkout's clean state, Git receive settings, branch state, installed commands, and Linux test result; this review used only the local repository.
- The completed merge: no implementation commits exist yet on `merge-ship-with-agents`. On this Mac, the current `make test` fails in `test_worker_commands_and_lead` because BSD `sed` treats `-e` as the `-i` backup suffix.
