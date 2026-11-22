# Choosing models by task tier

Keep model selection out of project templates so projects stay model- and harness-agnostic as models evolve.
Configure your personal tier presets once in `~/.config/agent-kit/tiers.conf` (read automatically by `scripts/start-worker.sh`, or override per project in `agent-kit.conf`):

```bash
# ~/.config/agent-kit/tiers.conf (example — set to whatever harnesses/models you use)
TIER_SIMPLE_KIND="codex"
TIER_SIMPLE_MODEL=""        # empty = harness default, or pin a fast/cheap model ID
TIER_SIMPLE_EFFORT="high"

TIER_MEDIUM_KIND="claude"
TIER_MEDIUM_MODEL=""        # e.g. a mid-tier model for contained contract + test work
TIER_MEDIUM_EFFORT="high"

TIER_COMPLEX_KIND="claude"
TIER_COMPLEX_MODEL=""       # e.g. your strongest reasoning model for open design
TIER_COMPLEX_EFFORT="high"
```

| Tier | When to use |
| --- | --- |
| `simple` | One small, mechanical change with an exact spec and no judgement: a rename, a copy edit, a config value, one function with given inputs and outputs |
| `medium` | A feature or fix of up to a few hundred lines with a written contract, tests and lead review |
| `complex` | Open design, unclear requirements, cross-cutting changes, or reasoning the contract cannot pin down |

`make worker NAME=x TIER=simple|medium|complex` applies your preset; explicit `KIND=... MODEL=... EFFORT=...` arguments always override it. A project's own model notes win over global defaults.

**Escalate on evidence:** if a worker fails its tests twice, keeps asking about the spec, or ships a correctness bug in review, restart it one tier up rather than guessing up front.
