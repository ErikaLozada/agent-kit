## Third check (69c572e)

| Finding | Status | Evidence against the original scenario |
| --- | --- | --- |
| M1 | resolved | `tests/test_install.py:109–118` now asks the OS for an ephemeral port and skips if local listening is prohibited. `make test` here completed with 17 tests, 1 skipped, and no errors. The live-listener branch remains unverified in this sandbox. |
| M2 | resolved | `template/scripts/start-worker.sh:32–37` replaces existing `Lead:` and `Agent:` lines. In a throwaway installed project, two `make worker NAME=retry` calls (Claude, then Codex, with different pane IDs) left exactly one `Lead:` with the second pane and one `Agent:` naming Codex. `tests/test_install.py:96–103` covers the retry. |
| M3 | resolved | `skills/ship-with-agents/SKILL.md:32–34,82–87` and `references/backends.md:6–14` now require `HERDR_ENV=1` for the automated kit path and explicitly say no agent is started outside herdr. The original mistaken `herdr agent prompt` step is no longer instructed. The newly documented outside-herdr path has a task-record defect (N1). |
| M4 | resolved | `template/AGENTS.md:37`, `README.md:46`, and `skills/ship-with-agents/SKILL.md:119–120` now agree: only the lead deploys, and only after the user's go-ahead. |
| M5 | resolved | `template/AGENTS.md:36` now states the owner-file and per-task scratch-folder exception when a worktree cannot carry the data, matching `skills/ship-with-agents/SKILL.md:74–76`. |

### N1 — medium — `skills/ship-with-agents/SKILL.md:85–87`; `template/scripts/start-worker.sh:32,39–40`; `template/AGENTS.md:33`

**Problem:** The fix now tells leads outside herdr to run `make worker` and then start an agent with the Agent tool or `codex exec`, but `make worker` still rewrites `TASK.md` to say `Lead: herdr pane unknown (report there...)`. This contradicts the actual communication channel recorded for that task.

**Scenario:** In a throwaway install with `HERDR_ENV=0` and no `HERDR_PANE_ID`, `make worker NAME=solo KIND=codex` exited successfully, printed “Not inside herdr,” and wrote `Lead: herdr pane unknown (report there; it reviews, commits and merges)`. A worker following `TASK.md` cannot report to that pane.

**Fix:** In the non-herdr path, write the actual lead channel into `TASK.md` (or leave a clear `Lead: <fill in before briefing>` placeholder) and require the lead to fill it before starting the worker. Keep the herdr pane text only when `HERDR_ENV=1`.
