# Templates

Fill the `<...>` parts. Keep briefs short and point to files; agents read the files.

## Review brief (round 1)

```
You are reviewing the <project> repo in this folder (baseline commit <sha>). Read <README / CLAUDE.md / AGENTS.md>
first for the project rules. Review for correctness bugs, edge cases that break real use, determinism, and violations
of the project rules (<the 2-4 rules that matter most>). Priority order: <changed or riskiest files first>, then the
rest. Ignore <generated files, vendored code, data>.
Rules: code only, no Computer Use, screen, app or GUI actions. Do NOT modify any existing file and do NOT run
<expensive or outward-facing commands>. Reading code, git commands and small throwaway scripts under $TMPDIR are fine.
Write your findings to a new file <review/review-1.md> and nothing else. For each finding: id (R1, R2...), severity
(critical / high / medium / low), file:line, one-sentence defect, a concrete failing scenario (inputs or state ->
wrong result), and a fix in one or two sentences. Rank by severity, report only real, verifiable issues (no style
nits), and end with what you could not verify. When the file is written, reply with one line: DONE and the number of
findings.
```

For a feature instead of a review, the lead writes the plan directly from the requirement (step 4) and the reviewer
starts at round 2 against the baseline.

## Plan file

```markdown
# Plan: <feature or "fixes for review/review-1.md">

Lead: <you>. Reviewer: <provider, model, effort>. Baseline: <sha>.
<Which findings the lead confirmed against the code; which were dropped and why.>

## Rules for every task
- Edit only the files your task owns. Match the surrounding style.
- <project rule + how to check it, e.g. a parse check for the language version>
- Test in <scratch folder or copy per task>; delete it when done. Never touch <real data / shared outputs>.
- Never run <renders, deploys, migrations...>. Don't commit.
- Report to review/task-<x>.md: what changed (file:line), how you tested it, anything you could not verify.

## Tasks (<which can run in parallel: no two share a file>)

### A — <files>: <goal> (<finding ids>)
Owner files: <list>.
1. <step, with the finding's scenario>
Acceptance: <measurable checks>.

## Model per task
<A Opus · B Sonnet (first: A depends on it) · C Haiku ...>. <Isolation: worktrees / shared folder with scratch dirs, and why.>

## After all tasks (lead)
1. <project-wide checks> 2. <comparisons on real data> 3. One commit per task citing the ids.

## Round 2 (from review/review-2.md)
<new tasks in the same format>
```

## Worker brief

```
[lead] You are a helper agent for task <X> in the <project> repo (this folder). Read <plan file, or TASK.md in an
agent-kit worktree>: the rules for every task and task <X>, plus the findings it cites in <review file>. Do task <X>
only, editing only the files it owns. Test in <scratch folder / your worktree and test port>, delete scratch files
when done; never run <...>; do not run the lead-only checks; never commit (the lead reviews and commits).
<Any dependency note, e.g. exact signature another task calls.> When finished, write your report (what changed with
file:line, how you tested it, anything you could not verify, and any acceptance check you did not meet, with the
numbers) in <TASK.md under ## Report / review/task-<x>.md>, and reply with one line: [task-<x>] READY. Start every
message to the lead with [task-<x>]. If you need a decision, write it in the report and reply
[task-<x>] BLOCKED <one line>.
```

## Re-review brief (round 2+)

```
Review <n> of the <project> repo in this folder. Your previous review is <review file>; the fixes are the commits since
<baseline>: run git log --oneline <baseline>..HEAD and git diff <baseline>..HEAD. The plan and each agent's report are
in <plan file> and review/task-*.md. For each earlier finding, give a status (resolved / partly / not resolved) with
file:line evidence, judging the original failure scenario, not just whether code changed. Then look for NEW problems
the fixes introduced: regressions, broken callers (<new arguments or names to check>), and the project rules.
Rules: code only, no Computer Use, screen, app or GUI actions; don't modify files; don't run <...>.
Write <review/review-n.md> and nothing else: a status table, then new findings (N1, N2...) in the same format as
before, then what you could not verify. Reply with one line: DONE, the number resolved, the number of new findings.
```
