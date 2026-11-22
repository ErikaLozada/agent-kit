---
name: session-retro
description: >
  Run a measured retrospective of agent sessions (pi, Claude Code and Codex transcripts) and publish it as an
  interactive HTML page the owner can annotate. Use when the owner asks for a retro, a post-mortem, "why did this
  take so long", "where did the time go", or an independent review of a previous retrospective.
---

# Session retrospective

Source of truth: `skills/session-retro` in `agent-kit` (linked globally via `install.sh --link-skills`). Resolve the skill's folder from its real path, e.g. `RETRO=$(cd -P <this skill's folder> && pwd)`.

The output is one self-contained page, `docs/retro-<date>[-<slug>].html`, built from a data file
`docs/retro-<date>[-<slug>].json`. Every figure on it comes from `scripts/session_metrics.py`; every opinion is
labelled as one. The owner marks each claim agree / disagree / question, copies the notes as Markdown and pastes
them back; you answer and change the project docs.

## Rules that keep a retro honest

These are the mistakes earlier retros made. Do not repeat them.

1. **Measure from the transcript, never from memory.** Run the script. If a number is not in `metrics.json`, say
   how you derived it or mark it as an estimate.
2. **Fix the window before you measure.** The question is almost always "requirements → first thing the human
   could look at". Find that milestone in the timeline (the first successful deploy, publish or preview the
   human could open) and pass it as `--milestone`. Report that window first; the whole session second. Never
   mix them: a whole-session total that includes review rounds and the retro itself answers a different question.
3. **Split wall time three ways: human, model, tool.** Human = gaps that end in a user message. Model = gaps that
   end in an assistant turn (generation, including reading the context). Tool = command runtime. A sub-agent's
   time sits inside the parent's tool time; do not add it twice. A wait over `--away` minutes (default 30) is the
   human being away, reported as `away_min`, never as reading time.
4. **Look at turns, not just commands.** Report assistant turns, tool calls per turn, median turn latency early
   vs late, and context growth. A slow build with fast tools is a turn-count and context problem.
5. **For every stop, ask who required it.** Quote the instruction (AGENTS.md line, requirements checkbox, user
   message) that caused it. A stop the template mandates is a template fix, not an agent fault.
6. **For every instruction file, check whether it was read before the step it governs** (timeline order), and
   whether what the agent read was the right version (installed package vs registry `latest` or an old tag).
7. **Separate avoidable from inherent.** Give each avoidable item its minutes and the change that removes it.
   Estimate the counterfactual ("with these changes: about N min") and label it an estimate.
8. **Check where the fix has to live.** If the project was copied from a template repo, a fix made only in this
   project will not reach the next one. Say which file in which repo has to change.
9. **If you are reviewing your own session, say so on the page** and prefer a fresh session to write it. If you
   are reviewing another retro, add a "Claims checked" section: each claim, verdict
   (`holds` / `partly` / `wrong` / `unverified`), and the evidence.
10. **Do not count the retro.** Pass `--until` at the moment the retro work started.

## Steps

1. **Find the transcripts.** `--project .` finds all of these, for the project folder and every worktree
   `git worktree list` reports:
   - pi: `~/.pi/agent/sessions/--<abs path, / → ->--/*.jsonl`
   - Claude Code: `~/.claude/projects/<abs path, non-alphanumerics → ->/*.jsonl` (sub-agents are inline
     records with `isSidechain`; the script skips them)
   - Codex: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, matched on the `cwd` in its first record
   - Worktrees already removed (agent-kit's `make finish` deletes `<project>-<task>`): add `--siblings`, then check
     the printed `cwd` of each session, because an unrelated folder with the same prefix matches too.
   Sessions that run inside another session's span (reviewers and workers started by a lead) are flagged
   `inside_session`: their time overlaps the lead's, so never add them to its total.
   Transcripts can hold secrets and customer data: read them, quote only what the page needs, never copy them
   into the repo.
2. **First pass, no milestone:**
   `python3 -I "$RETRO/scripts/session_metrics.py" --project . --out .scratch/retro`
   Read `.scratch/retro/timeline-*.md` (use offsets; it is long) and note: the milestone time, when the retro
   started, every user message and what preceded it.
3. **Second pass with the window:** add `--milestone "first viewable draft=HH:MM:SS"` and `--until HH:MM:SS`, plus
   project-specific classifiers that are checked before the defaults, for example
   `--bucket "deploy / platform ops=make deploy|docker compose" --bucket "integration tests=pytest -m integration"`.
4. **Read the instructions the agent had at the time**, not as they are now: `git show <first commit>:AGENTS.md`,
   the requirements as first read (the first `read` of it in the timeline shows its original text), and the
   template repo the project came from.
5. **Answer the standard questions** (each becomes a section or finding):
   - Time to the milestone, split human / model / tool, and the stops on the way, each with its cause.
   - What the agent asked before starting, and which questions the docs or a sensible default already answered.
   - Where the model time went, by activity (`buckets`), plus turns, parallelism, latency drift and context growth.
   - What was read late, read twice, read in the wrong version, or not read at all.
   - Retries and failures (`failed_tool_results`), with the cause of each class.
   - What the human found in review that a check could have caught.
   - What was worth its time (keep it).
   - Ranked changes, with minutes saved and the file (and repo) each one lives in.
6. **Write the data file** (`references/data-schema.md`). Give a note `id` to every claim the owner might dispute.
   Keep prose short; numbers go in KPIs, bars, tables.
7. **Build and check:**
   `python3 -I "$RETRO/scripts/build_retro.py" docs/retro-<date>.json docs/retro-<date>.html`
   Then open it (or publish via `publish-brief` if installed) and check it in light and dark mode at desktop and phone width.
8. **Report in chat**: the three or four findings that matter, the counterfactual, and the path/URL to the page.
   Ask the owner to send back their notes with "Copy my notes".
9. **When the notes come back**: answer each one, correct the data file if a claim was wrong (add a visible
   "Corrections" section; never silently change a number), rebuild, and make the agreed doc changes in the
   files named on the page.

## Files

- `scripts/session_metrics.py`: transcript → `metrics.json` + `timeline-*.md`. Standard library only.
- `scripts/build_retro.py`: data JSON → page. Validates ids, types and table widths.
- `template/retro.html`: the page shell. `build_retro.py` renders the content into it as static HTML (so it reads
  in previews, print and without JavaScript); its script adds the note controls, `localStorage`, Markdown export
  and the theme switch. Do not edit it per project; change the data instead.
- `references/data-schema.md`: block types and fields. `references/example.json`: every block type once.
