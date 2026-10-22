# Merge review against `a4f7608`

Reviewed `git log --oneline a4f7608..HEAD` and `git diff a4f7608..HEAD` through `cd7e3db`. The revised plan at `docs/merge-plan.md:66–101` expressly supersedes the older change and Delivery text.

## Plan-review findings

| ID | Status | Evidence against the original scenario |
| --- | --- | --- |
| P1 | resolved | Workers of both kinds are told never to commit and to report `[name] READY` in `skills/ship-with-agents/SKILL.md:11–15,86–89,110–115`, `references/templates.md:59–67`, `template/.agents/skills/ship-feature/SKILL.md:10–17`, `template/AGENTS.md:33`, and `template/scripts/start-worker.sh:5–6,30`. The lead commits in the task worktree. |
| P2 | resolved | The superseding Delivery instructions require a clean omarchy checkout, testing `merge-ship-with-agents` in a temporary worktree, then testing merged `main` (`docs/merge-plan.md:75–77`). This prevents an old `main` test from standing in for the branch test. Execution on omarchy remains unverified. |
| P3 | resolved | `install.sh:7–19` dispatches `--link-skills` before parsing a project directory and exits without `git init` or template copying. `tests/test_install.py:118–132` checks a fake HOME, existing destinations, and rerun; a separate throwaway path-with-spaces check also linked all three harness folders. |
| P4 | resolved | The superseding Delivery instructions explicitly switch the Mac to `main`, pull `origin main` with `--ff-only`, and compare HEAD with omarchy (`docs/merge-plan.md:81–82`). The actual pull is still pending. |
| P5 | resolved | The superseding swap steps require comparing the Mac copy, moving it to a backup outside the skill folder, checking the new link and `SKILL.md`, and retaining the backup until the linked skill has been used (`docs/merge-plan.md:83–86`). The actual swap is still pending. |
| P6 | partly | The lead skill and backend now direct kit workers through `make worker` from `main` (`skills/ship-with-agents/SKILL.md:79–84`, `references/backends.md:6–10`), avoiding the raw recipe's `--cwd "$PWD"`. They do not handle the case where herdr is installed but `HERDR_ENV` is not 1: `make worker` creates a task but starts no worker (M3). |
| P7 | resolved | The lead checks the project's actual Makefile and scripts before assuming kit targets (`skills/ship-with-agents/SKILL.md:26–31`). `new-project` derives the kit root from the resolved skill location (`skills/new-project/SKILL.md:8–11`); a throwaway symlink-path check resolved to the repository root. |
| P8 | partly | `new-project` invokes optional global linking when the lead skill is absent (`skills/new-project/SKILL.md:11`), README says copied templates require manual adoption (`README.md:54`), and detailed review rounds stay in the lead skill. `template/AGENTS.md:34,36–37` still duplicates or contradicts the skill's permission, shared-folder, and deploy rules (M4–M5). |
| P9 | partly | Missing-`systemctl` tests and a bound-port fallback test were added (`tests/test_install.py:103–116`), and the scripts have the corresponding branches (`template/scripts/new-task.sh:21–27`, `status.sh:7–13`, `deploy.sh:7–8`). On this Mac sandbox, `make test` has 16 passing tests and one error: the new test cannot bind port 8001 (`PermissionError: [Errno 1] Operation not permitted`; M1). Omarchy was not tested here. |

## Numbered plan changes

| Item | Status | Evidence |
| --- | --- | --- |
| 1. Move skill | partly | The committed skill and two references exist (`skills/ship-with-agents/SKILL.md:1–18`, `references/backends.md:1–10`, `references/templates.md:1–3`); the Mac source comparison and global symlink swap are Delivery actions still pending (`docs/merge-plan.md:83–86`). |
| 2. Shorten `ship-feature` | resolved | It now has a worker checklist, a separate solo section, and lead-skill pointer (`template/.agents/skills/ship-feature/SKILL.md:3–25`); its worker protocol matches P1. |
| 3. Teach lead skill about kit | partly | Kit commands, PROTECTED, tier table, worker settings, watcher, Codex trailer, and team size are present (`skills/ship-with-agents/SKILL.md:29–31,65–69,77,110–115`; `references/backends.md:6–10,23–33,81–92`). The unconditional `make worker` instruction has the no-herdr gap in M3. |
| 4. Sync `AGENTS.md` | partly | Worker reporting, approval relay, and lead-skill pointer changed (`template/AGENTS.md:17,31–34`), but the worktree and deploy rules still disagree with the lead skill (M4–M5). |
| 5. Global links | resolved | Link mode avoids overwriting a real directory or foreign link and checks link text before treating an existing link as current (`install.sh:7–18`; `tests/test_install.py:118–132`). The actual omarchy links could not be inspected; their stated absolute targets will compare equal if `cd -P` yields `/home/erikaloz/lab/agent-kit`. |
| 6. macOS portability | partly | `sed -i` was replaced by portable awk plus mv; port and systemd branches were added (`template/scripts/start-worker.sh:31–36`, `new-task.sh:21–27`, `status.sh:7–13`, `deploy.sh:7–8`). A restart duplicates `Agent:` and leaves stale `Lead:` (M2); the Linux result is unverified. |
| 7. Tests | partly | New cases cover link mode, worker metadata, port fallback, and missing systemd (`tests/test_install.py:89–132`), but the full suite currently errors in a restricted environment (M1). There is no assertion that a second worker start leaves exactly one current metadata line (M2). |
| 8. Docs | resolved | README records the merge, lead/worker skill locations, both checkout paths, and the manual migration rule for existing projects (`README.md:3,12–23,50–54`). |

## New findings

### M1 — medium — `tests/test_install.py:103–110`

**Problem:** The new port test assumes it can bind the fixed port 8001. Its setup errors before exercising `new-task.sh` in a restricted environment, and it is also sensitive to any existing listener on that port.

**Scenario:** `make test` in this Mac sandbox raises `PermissionError: [Errno 1] Operation not permitted` at line 106; none of the test's assertions run. On a machine where another service owns 8001, it similarly errors with address-in-use.

**Fix:** Allocate an available ephemeral port and set `TEST_PORT` to that port in the temporary project's config; skip with a clear reason if local binding is prohibited, and use a deterministic fake `lsof`/`ss` test to still verify fallback command selection in such environments. Keep the real-socket check where binding is allowed.

### M2 — medium — `template/scripts/start-worker.sh:29–35`

**Problem:** The awk edit appends `Agent:` after every `Owner:` on every invocation, but only updates `Lead:` when its value starts with `none`. Starting a worker again on the same task leaves stale lead information and duplicates agent metadata.

**Scenario:** In a throwaway installed project, two `make worker NAME=retry KIND=claude` calls with different `HERDR_PANE_ID` values yielded two `Agent:` lines and `Lead: herdr pane first:pane`; the second pane was absent from `TASK.md`. This happens when startup fails and the lead retries.

**Fix:** Replace the existing `Agent:` and `Lead:` lines, inserting `Agent:` only if absent; write through a unique temporary file and assert exactly one of each line in a retry test. Preserve the rest of `TASK.md` verbatim.

### M3 — medium — `skills/ship-with-agents/SKILL.md:32,79–84`; `skills/ship-with-agents/references/backends.md:6–12`; `template/scripts/start-worker.sh:37–39`

**Problem:** The lead skill selects herdr when it is merely on PATH and then says kit workers start with `make worker`. The script actually starts a worker only when `HERDR_ENV=1`; otherwise it creates the task and prints a manual command, without starting an agent.

**Scenario:** A lead runs from a normal shell with `herdr` installed. It follows the kit instruction, fills `TASK.md`, and calls `herdr agent prompt task-b`, but no `task-b` agent exists. The returned `make worker` command had exit status zero, so the failure is easy to miss.

**Fix:** In the skill, require `HERDR_ENV=1` for the automated kit path, and spell out the manual or Agent-tool route otherwise; alternatively, make `start-worker.sh` actually launch through herdr whenever the CLI is available. Do not claim a worker started when only a worktree was made.

### M4 — high — `template/AGENTS.md:37`; `README.md:46`; `skills/ship-with-agents/SKILL.md:116–117`

**Problem:** The project instructions still say the lead merges and runs `make deploy`, while the lead skill says deploys stay with the user and the lead asks for approval before one deploy. The shortened worker/solo skill also says `make deploy` only when the user asks (`template/.agents/skills/ship-feature/SKILL.md:25`).

**Scenario:** A kit-project lead follows `AGENTS.md` after merging a branch and runs `make deploy` immediately, restarting a live service before the user has decided to deploy.

**Fix:** Make the short project rule say that the lead is the only agent permitted to run `make deploy`, and only after the user's go-ahead. Use the same wording in README and the global skill.

### M5 — medium — `template/AGENTS.md:36`; `skills/ship-with-agents/SKILL.md:73–76`; `docs/merge-plan.md:94–98`

**Problem:** `AGENTS.md` still requires every parallel task to have its own worktree, while the global skill explicitly uses the main folder with owner files and per-task scratch folders when untracked data cannot be carried into worktrees. The revised plan intended `AGENTS.md` to hold only short, consistent rules.

**Scenario:** A project depends on untracked media that its worktrees cannot access. A lead following the global skill shares the main folder; a worker following the project's `AGENTS.md` instead creates an unusable worktree or treats the lead's assignment as a rule violation.

**Fix:** State the default and exception in one short project rule: use a worktree per task when it has the required data; otherwise the lead assigns disjoint files and a scratch folder per task. Keep the detailed procedure in the global skill.

## Could not verify

- Linux/GNU behavior, omarchy's actual symlink targets and checkout state, and the branch test/merge/pull/swap Delivery actions; no remote or external state was changed.
- A real listening-port fallback on this Mac sandbox because local socket binding is denied. The new test's failure is reported above; other tests completed successfully.
- The original Mac skill folder against the committed copy, because it lies outside this repository and the swap is not yet performed.
