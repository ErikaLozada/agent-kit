# {{PROJECT}}

<!-- Read by every agent in every session: keep it under 3 KB. One owner per fact. -->

TODO: what this is, who it is for, what "done" looks like. Requirements: TODO (file). Decisions: `docs/decisions.md`.

## Commands

- `make test`: the tests (`TEST_CMD` in `agent-kit.conf`, else `tests/`). Pre-commit runs it on every commit. No tests yet: `ALLOW_NO_TESTS=1 git commit` (reported `NOT_EVALUATED`, never a pass).
- `make review KIND=codex|claude|pi|gemini`: independent diff review (or set `REVIEW_CMD`).
- `make deploy`: only when the user asks. Refuses dirty tree, non-`main` branch, or failing tests.
- `make setup`: once per clone, turns on `.githooks/pre-commit`.
- `make diagram`: rebuilds `docs/diagrams/*.html` from `scripts/diagrams.py` (see `feature-diagram` skill; ship major features with a diagram).
- Parallel agents (`make task`, `worker`, `status`, `finish`): see `ship-with-agents`.

## Outside the repo

- Read-only, no need to ask: TODO (APIs, consoles, folders).
- Needs a go-ahead every time: TODO (deploys, cloud/account changes, sending anything).
- Standing approvals: TODO (what, limit, date) or "none".
- Keys live in TODO; never commit, print, or send them.
- If the harness blocks something approved, stop and ask the user to run it.

## Data

TODO: what data exists and what git tracks. User-only files go under `PROTECTED` in `agent-kit.conf`.
Never read: TODO (answer keys, secrets folders).

## Gates (stop and show the user)

TODO: at most two, e.g. "the plan, before code" and "the result, before deploy".

## Defaults (do not ask)

TODO: choices to make without asking.

## Working speed

- Scaffold first, then fill in. Batch independent reads and checks in parallel.
- Read a doc whole once (grep big references first); keep notes instead of re-reading.
- Redirect output > 4 KB to `.scratch/` and grep it; run long checks in the background.
- Save questions for the next gate. A user question is not a request to edit.

## Conventions

- Match surrounding code. Stage explicit paths (avoid blind `git add -A`). Small commits explaining why, with `Co-Authored-By`. Gate a commit on a check's exit code (`check && git commit`), never on output printed in the same command.
- Test failure/edge cases (partial failures, retries, stale state); re-check the failing scenario after a fix.
- Reuse existing helpers instead of duplicating logic.
- Verify packages, APIs, and platform products are current (not deprecated) before recommending or adopting them.
- Never claim a check ran or a URL works without verifying; otherwise say "not checked".
- Rules live here, not in harness memory. Append settled choices to `docs/decisions.md`. Add a rule only after a real mistake.

## Glossary

TODO: domain terms and UI names that differ from code names.
