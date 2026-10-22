---
name: ship-with-agents
description: Lead a team of agents (Claude and Codex, any mix) to ship a feature, a fix or a review-and-fix round in any repo - learn the project's own commands and rules, plan tasks with owned files and acceptance checks, start and watch workers, relay their permission prompts, review across providers, verify, commit. Use when the user asks to ship or build something with agents, to orchestrate, or to have Codex (or another model) review the code and agents fix it.
---

# Ship with agents

You are the **lead**. You plan, brief, watch, check and commit; workers do the edits; a **reviewer**, ideally from
another provider (Codex when the workers are Claude), finds problems and checks the fixes. The user makes the decisions.

**If you are a worker** (your brief names a lead and a task): read the brief and the plan file it points to, do only your
task, edit only the files it owns, follow its test rules, don't commit, write your report file, then reply with one
line, e.g. `DONE task B`. If you are blocked on a decision, write it in the report and stop instead of guessing.

Recipes for starting and reading agents (herdr, the Agent tool, `codex exec`) are in `references/backends.md`.
Brief, plan and report templates are in `references/templates.md`.

## 1. Learn the project (nothing here is assumed)

- `git status`, current branch, `git log --oneline -10`. Note the baseline commit: every later review diffs against it.
- Read the project's instructions: `CLAUDE.md`, `AGENTS.md`, `README*`, `CONTRIBUTING*`, any `docs/decisions*` or
  requirements file. Write down the **project rules** a worker must keep (language version, style, files never to
  touch, things never to run, e.g. renders, deploys, migrations on live data).
- Find the project's own commands instead of inventing them: `Makefile`/`justfile` targets, `package.json` scripts,
  `pyproject.toml`/`tox.ini`, scripts named in the README or CLAUDE.md. Note: test, lint/type check, build, run, deploy.
  If there are no tests, find what stands in for them (a check script, a byte-identical output comparison, a dry run).
- Pick the backend (`references/backends.md`): herdr if `HERDR_ENV=1` or `herdr` is on PATH, else the Agent tool.
  Check whether `codex` is installed for a cross-provider reviewer. Check for other active agents (`herdr agent list`)
  and avoid the files they own.
- Note untracked files the work needs (media, data, `.env`, local builds): a git worktree won't have them.

## 2. Pin down done

Say in one or two sentences what done looks like and which requirement or decision it serves. If it changes a settled
decision or the project rules, ask first. Ask the user's open questions as one numbered list so they can answer
`1. yes 2. later 3. ...`.

## 3. Review first (for "review and fix", or a large or risky change)

Start the reviewer read-only with the review brief (templates). It writes one file with ids (R1, R2...), severity,
file:line, defect, a concrete failing scenario and a fix, then what it could not verify. When it lands, **spot-check
every finding against the code yourself** before planning; mark which ones you confirmed. Drop or downgrade what
doesn't hold up, and tell the user.

## 4. Plan

Write the plan to a file in the repo (`review/plan.md`, or the project's own place for such notes) using the plan
template:
- **Rules for every task**: the project rules from step 1, how to check them (e.g. a parse check for the language
  version), where to test (a scratch copy or scratch folder per task, deleted after), what never to run.
- **Tasks**, one per independent unit: the findings or requirement it covers, **owner files** (no two parallel tasks
  share a file), steps, and **acceptance checks that can be measured** (tests pass, output byte-identical to before,
  a number within a bound, a synthetic case behaves as stated).
- **Order**: which tasks depend on others (a task that adds an argument another task calls runs first, or both agree
  on the exact signature in the plan).
- **Failure cases in every brief**: the brief sets the ceiling, since workers test what it names. Write in the
  edges: partial success (a remote write works, then a local step fails), two operations at once, stale state, reruns.
- **Contract before code**: when tasks depend on each other, fix the shared signatures in the plan (or land stubs on
  the main branch first) so they can run in parallel.
- **Model per task** by tier: *simple* (exact spec, no judgement: a rename, one function) to Codex or the smallest
  Claude; *medium* (a contained fix with a written contract and tests) to Haiku or Sonnet; *complex* (open design,
  cross-cutting, concurrency) to Opus. Move a worker up one tier on evidence: tests failed twice, keeps asking about
  the spec, or shipped a correctness bug. Show the user the table of task → agent → model before starting.
- **Lead-only work**: checks over shared outputs (full test suite, regenerating shared artifacts, comparisons on real
  data) are run by you at the end, so two workers never rebuild the same thing at once.

Isolation: use a worktree per task when everything the task needs is tracked in git; otherwise work in the main folder
with strict file ownership and per-task scratch folders, and say which you chose. Isolate **side effects**, not just
code: a worktree still shares real data, accounts, tokens and services, so every worker test runs with the project's
dry-run switches, its own test port and its own data/history files, and tests mock the network.

## 5. Start the workers

One agent per task, each in **its own tab** (not a side-by-side split, screens are narrow). The brief is short and
points to the plan file; it repeats the rules that matter most (owned files only, where to test, no commits, what
never to run) and asks for a report file `review/task-<x>.md` (what changed with file:line, how it was tested,
anything not verified) and a one-line `DONE` reply. Start dependent tasks after the task they need.

Every message between agents starts with the sender's name in brackets (`[lead]`, `[task-b] DONE`): text sent into
a pane looks exactly like the user typing, so untagged text is the user. Workers never answer approvals for the user.

## 6. Watch and relay

Watch from a background command that exits when any worker is **blocked** or all have settled (recipe in backends);
never sleep-poll in the foreground. When a worker is blocked on a permission prompt or a question:
1. Read its screen and tell the user in plain words what it wants to do and why.
2. Inside the project and its rules (editing its own files, running the project's checks in its scratch folder):
   approve it and say so. Outside them (other folders, network installs, global config, deleting, GUI/app actions,
   anything irreversible): ask the user first.
If a worker goes quiet or off-brief, read its output, correct it with a short prompt, or stop it and say so.

## 7. Integrate

- Read every report. Check each acceptance criterion yourself where it is cheap; if one is not met, say so plainly
  with the numbers and ask whether that's acceptable or what to do (don't quietly accept it).
- Run the project-wide checks from step 1 and any lead-only comparisons from the plan.
- Look at the combined diff for duplicated logic: new code should reuse existing helpers, not copy their rules.
- Commit one task per commit, message says why and cites the finding ids, with the agent trailer from the system
  reminder. Commit Codex workers' changes yourself (its sandbox can't write git metadata). Use the project's own
  commit hooks; never skip them. You are the only writer of the main branch: workers report and stop.
- Deploys, releases and other irreversible or outward-facing steps stay with the user. Merge several reviewed tasks,
  then ask for one deploy. Files a running service writes belong in `.gitignore`, or they block clean-tree deploys.
- Stop test servers you started by process id, never by a name pattern (a pattern can match your own shell).

## 8. Review the fixes (cross-provider)

Send the reviewer the re-review brief: diff `<baseline>..HEAD`, read the plan and reports, give each original finding
a status (resolved / partly / not resolved, with file:line evidence), then list new findings (N1, N2...) the fixes
introduced. Spot-check, then put new findings to the user as numbered decisions, plan a new round (add it to the same
plan file), and repeat steps 5-8 until no high findings remain or the user stops. In Claude Code, `/code-review` on the
branch is a second opinion, not a replacement for the other provider.

## 9. Close

- Close agent tabs/panes you opened (keep the reviewer only if another round is coming), delete scratch folders, and
  check `git status` is what you expect.
- Record new settled decisions where the project keeps them; update CLAUDE.md/README/skills if commands or rules changed.
- Tell the user, by task or finding id, what changed, what was tested, what wasn't, and what they should check.
- Add any lesson about running this skill to the user's `### Lessons` (e.g. a tool quirk you hit), and to the
  "went wrong before" list below, so the next project learns it too.

## Things that went wrong before (Crate Digger, 2026-10-19)

- Every bug the lead's review stopped had passed the worker's own tests: they sat in cases the brief left out (a
  retry after a remote write succeeded, a missing ownership row, buttons left stale). Hence failure cases in briefs and
  a full read of every diff.
- One reviewer finding came from the lead's own brief: the other-provider reviewer catches the lead's blind spots.
- Parallel workers bought speed, not quality: each diff still needed a full read.

## Things that went wrong before (reelkit, 2026-10-22)

- Codex hung at startup until it was upgraded; on first run it asks whether to trust the folder and macOS asks to open
  its downloaded helper binaries. Relay each prompt to the user; don't click through them.
- Codex reached for Computer Use during a code review: every reviewer brief says "code only, no screen, app or GUI
  actions".
- `herdr` and `codex` talk to sockets/state outside the project, so their commands fail inside the Bash sandbox with
  "Operation not permitted"; run them with the sandbox disabled (that goes through the permission prompt).
- Git worktrees lacked the untracked media, so workers shared the main folder: strict owner files and per-task scratch
  folders kept them apart, and only the lead ran checks on the real data.
- A worker missed its acceptance bound by about 1 dB and said so in its report; the lead took the trade-off to the user
  as a decision, and the follow-up was planned as a new task instead of being folded silently into another one.
- The second review found that a fix only partly solved two findings (a lock check that ignored later edits, a
  file-name collision moved one step down the pipeline). Always run the re-review; "the code changed" isn't "fixed".
