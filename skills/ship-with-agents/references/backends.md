# Backends: starting, watching and reading agents

Pick whichever channel fits your setup. **herdr** gives a visible tab per agent and lets you relay permission prompts across harnesses; **native subagents** (e.g. Claude Code's `Agent` tool, Antigravity's `invoke_subagent`) need nothing extra installed; **headless CLIs** (`codex exec`, `claude -p`, `pi -p`, `gemini -p`, or custom `REVIEW_CMD` / `WORKER_CMD`) run one-shot jobs anywhere.

For required readiness checks, use a new conversation with the task brief and its referenced files; do not resume
the lead's transcript or pass its chat history. If the backend cannot provide a fresh context, report that limit
instead of claiming an independent check. The worker explains its understanding before edits; the lead follows
the readiness procedure in `SKILL.md` and the response format in `templates.md` before sending `[lead] PROCEED`.

**In an agent-kit project** with a `worker` target, inside herdr (`HERDR_ENV=1`), don't use the raw recipes below
for workers: run
`make worker NAME=<task> TIER=simple|medium|complex` (or `KIND=codex|claude|pi|gemini MODEL=... EFFORT=...`, or set `WORKER_CMD`) from the main
worktree. It makes the task's worktree, branch, test port and `TASK.md`, opens its herdr tab and starts the agent with
bounded worker settings. Then fill in `TASK.md` and brief it with `herdr agent prompt`. Start a reviewer with
`make review KIND=codex|claude|pi|gemini` (or `REVIEW_CMD`) where the project has it; otherwise use the headless recipes below. Outside herdr, `make worker` creates the task worktree only (prints "Not inside herdr" and exits 0): start the worker in that worktree with your harness's subagent tool or a headless CLI.

## herdr (when this session runs inside it: `HERDR_ENV=1`)

herdr talks to its socket outside the project, so run these commands with the sandbox disabled if your harness sandboxes shell commands. Output is JSON; parse it with `python3 -c`. `herdr agent wait` blocks until an agent reaches a target state, or check `herdr agent get`: `working`, `blocked` (waiting on a prompt), `unknown` (starting), anything else means settled.

```bash
# New tab (not a split) for one agent; prints its pane id
tab() { herdr tab create ${HERDR_WORKSPACE_ID:+--workspace "$HERDR_WORKSPACE_ID"} --cwd "$PWD" --label "$1" --no-focus \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])"; }

# Start a worker in its tab (examples for claude / codex / pi)
P=$(tab task-b); herdr agent start task-b --kind claude --pane "$P" --timeout 90000 -- \
  --permission-mode auto -n task-b

P=$(tab task-c); herdr agent start task-c --kind codex --pane "$P" --timeout 60000 -- \
  -s workspace-write -a on-request -c sandbox_workspace_write.network_access=true -c 'model_reasoning_effort="high"'

# Check it is alive before the real brief (also surfaces a trust prompt or a hang)
herdr agent prompt reviewer "Reply with exactly one line: READY, your model name and reasoning effort." --wait --timeout 120000
herdr agent read reviewer --source recent-unwrapped --lines 40

# Send the brief (run in background for long jobs; you are notified when it returns)
herdr agent prompt task-b "<brief>" --wait --timeout 3000000

# Answer a prompt on its screen after the user (or the rules) allow it
herdr agent send-keys task-b enter

# Close the tab when done (tab id from `herdr tab list --workspace "$HERDR_WORKSPACE_ID"`)
herdr tab close <tab-id>
```

Watch several workers from one background command that exits on the first block or when all settle:

```bash
while true; do s=""; for t in task-a task-c task-d; do
  st=$(herdr agent get "$t" 2>&1 | grep -o '"agent_status":"[a-z]*"' | cut -d'"' -f4); s="$s $t=$st"; done
  case "$s" in *blocked*) echo "BLOCKED:$s"; exit 0;; esac
  case "$s" in *working*|*unknown*) sleep 10;; *) echo "SETTLED:$s"; exit 0;; esac; done
```

When it exits on BLOCKED: `herdr agent read <name> --source recent-unwrapped --lines 40`, relay it to the user (`SKILL.md`
step 6), answer, then start the watch again for the ones still working.

## Native subagents (no herdr)

- Launch one subagent per task with worktree isolation when everything the task needs is tracked in git.
- Give the full brief (the subagent starts cold): plan file path, task id, owned files, rules, report file.
- Run subagents in the background and wait for completion notifications; don't poll.
- Permission prompts surface to the user directly, so keep briefs strictly inside the project rules.

## Headless CLIs (without herdr)

Non-interactive one-shot runs — ideal for read-only reviews (the script writes the output file so the reviewer cannot modify source files):

```bash
# Codex (read-only sandbox, writes final report to file)
codex exec -C "$PWD" -s read-only -c 'model_reasoning_effort="high"' -o .reviews/review.md "<review brief>"

# Claude Code (plan mode, stdout captured to file)
claude -p --permission-mode plan "<review brief>" > .reviews/review.md

# pi (read + bash only, no write tool)
pi -p --tools read,bash --thinking high "<review brief>" > .reviews/review.md

# Gemini CLI
gemini -p "<review brief>" > .reviews/review.md
```

## Codex quirks

- First start in a folder asks whether to trust it (saved for later sessions): ask the user, then `send-keys enter`.
- If it hangs at startup (even `codex --version`), check for an update and ask the user before upgrading.
- macOS may ask the user to allow its downloaded helper binaries (`codex-code-mode-host`, `rg`). Tell the user what they are before they click.
- It can't write git metadata from its sandbox; no worker commits anyway: the lead commits its changes with `Co-Authored-By: Codex <noreply@openai.com>`.
- With `-c` overrides it warns "Running without the shared background server" and herdr may show it as `blocked` until the warning is dismissed (`esc`). Harmless.
- Put `"Code only: no Computer Use, screen, app or GUI actions"` in every brief.
