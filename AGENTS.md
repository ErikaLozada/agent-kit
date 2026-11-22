# agent-kit

<!-- Read by every agent in every session: keep it under 3 KB. One owner per fact. -->

A lightweight, harness- and model-agnostic starter kit that boots any project with shared instructions, enforceable git/test guardrails, and learned lessons from previous sessions — scaling from a solo agent to a parallel team.

## Commands

- `make test`: runs the full kit test suite (`tests/test_*.py`), including installer, test runner, session-retro, interactive-html-brief, and public-repo hygiene checks.

## Scope & Hygiene (Public Repository)

- **Public and generic:** never commit personal paths (`/home/...`, `/Users/...`), private hostnames, Tailscale domains/IPs, secrets, machine nicknames, or stack/domain-specific tool references. Domain/stack starter packs belong in external `--overlay` folders, not here.
- **Keep `template/` featherweight:** global tools and workflows belong in `skills/` (linked once per machine via `install.sh --link-skills`), never copied into every project's git repo.
- **Keep `template/AGENTS.md` under 3 KB and harness-neutral** (enforced by tests).
- **Keep scripts model-agnostic:** never hardcode vendor model IDs in `template/`; user tier preferences live in `~/.config/agent-kit/tiers.conf` or `agent-kit.conf`.

## Promoting Lessons into agent-kit

Promote a lesson here only after a real observed issue that changes future behavior across projects:
- Must always happen → enforce in code (`template/.githooks/`, `template/scripts/`).
- Needs judgement across sessions → put in a global skill (`skills/`).
- Universal short fact/rule → refine an existing bullet in `template/AGENTS.md` (respecting the 3 KB budget).

## Conventions

- Every behavior change to `install.sh`, `template/`, or `skills/` ships with a test in `tests/`.
- Scripts must work on both Linux and macOS (avoid GNU-only `sed -i`, `ss`, or Linux-only `systemctl` assumptions without fallbacks).
- Never push, rewrite public git history, or modify external repositories without explicit user approval.
