---
name: wrap-up
description: End-of-session hygiene and lesson capture ("finish for the day") - check git state, mine real friction and settled decisions from this session, filter ruthlessly against bloat, route each lesson to its one owning file (docs/decisions.md, AGENTS.md, a stack overlay, or agent-kit), and apply only what the user approves. Use when the user wraps up a session or asks what lessons to capture.
---

# Wrap up for the day

A fast, 2-minute end-of-session check and learning loop — lighter than `session-retro` (which measures full project timelines) and run while context is still hot. Works in any harness.

## 1. Check workspace state

- Run `git status --short` and today's commits (`git log --since="midnight" --oneline`).
- If the repo has `Makefile` with `status`, check `make status` for dirty worktrees or unfinished tasks.
- Note any uncommitted changes, failing tests, or open threads to hand off to tomorrow's session.

## 2. Mine real friction from this session

Review this conversation (and today's git diffs; only inspect closed local transcripts if the user asks to include earlier tabs). Look strictly for events that caused wasted time, rework, or explicit decisions:
- **User corrections:** anything the user had to steer, undo, or clarify.
- **Tool / CLI / platform traps:** commands, flags, permissions, or environment quirks that failed unexpectedly.
- **Missed checks or edge cases:** bugs found manually or in review that a test or guard should have caught.
- **Settled decisions:** architectural, UX, or scope choices finalized today.

## 3. Filter ruthlessly (prevent bloat)

Drop one-off typos, transient hiccups, and rules already covered by existing docs. Keep **only** items that would genuinely change future agent behavior. Aim for **0 to 5** concrete items; "no new rules needed today" is a great outcome.

Format each candidate in 1–3 sentences: **trigger/scope → action → reason** (plus evidence link/commit if helpful).

## 4. Route each lesson to its ONE owning source

Never duplicate a lesson across multiple files. Route each candidate to the single place that owns it:

| Kind of lesson | Owning destination |
| --- | --- |
| Settled project choice | This project's `docs/decisions.md` (append with today's date) |
| Project-specific rule or trap | This project's `AGENTS.md` (refine an existing rule if possible; keep total file `< 3 KB`) |
| Stack- or domain-specific recurring trap | Your domain/stack kit or overlay (keep generic `agent-kit` free of stack specifics) |
| Universal guardrail, script bug, or workflow fix | `agent-kit` (`template/` or `skills/`) |

## 5. Propose and wait for approval

Present a short summary:
1. **Repo state:** clean/dirty summary and any open follow-ups for next session.
2. **Proposed updates** as one numbered list (target file, exact 1–2 line addition or edit, and why).

Never silently edit `AGENTS.md`, `docs/decisions.md`, an overlay, or `agent-kit` without user confirmation. Apply only the numbered items the user approves (e.g., `1, 3 yes; skip 2`).
