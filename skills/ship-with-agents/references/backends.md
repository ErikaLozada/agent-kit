# Backends: starting, watching and reading agents

Pick one. herdr gives the user a visible tab per agent and lets you relay permission prompts; the Agent tool needs
nothing installed; `codex exec` runs a Codex reviewer or worker without herdr.

**In an agent-kit project** with a `worker` target, don't use the raw recipes below for workers: run
`make worker NAME=<task> TIER=simple|medium|complex` (or `KIND=codex|claude MODEL=... EFFORT=...`) from the main
worktree. It makes the task's worktree, branch, test port and `TASK.md`, opens its herdr tab and starts the agent with
the worker settings below. Then fill in `TASK.md` and brief it with `herdr agent prompt`. The reviewer still starts
with the recipe below.

## herdr (preferred when `HERDR_ENV=1` or `herdr` is on PATH)

herdr talks to its socket outside the project, so run these Bash commands with the sandbox disabled. Output is JSON;
parse it with `python3 -c`. Statuses from `herdr agent get`: `working`, `blocked` (waiting on a prompt), `unknown`
(starting), anything else means settled.

```bash
# New tab (not a split) for one agent; prints its pane id
tab() { herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --label "$1" --no-focus \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])"; }

# Claude worker (optional --effort low|medium|high)
P=$(tab task-b); herdr agent start task-b --kind claude --pane "$P" --timeout 90000 -- \
  --model sonnet --permission-mode auto -n task-b

# Codex worker: writes only its folder, may use the network (local test server, herdr), asks for anything else
P=$(tab task-c); herdr agent start task-c --kind codex --pane "$P" --timeout 60000 -- \
  -s workspace-write -a on-request -c sandbox_workspace_write.network_access=true -c 'model_reasoning_effort="high"'

# Codex reviewer: high reasoning, writes only its review file, never stops for approvals
P=$(tab reviewer); herdr agent start reviewer --kind codex --pane "$P" --timeout 60000 -- \
  -c 'model_reasoning_effort="high"' -s workspace-write -a never

# Check it is alive before the real brief (also surfaces a trust prompt or a hang)
herdr agent prompt reviewer "Reply with exactly one line: READY, your model name and reasoning effort." --wait --timeout 120000
herdr agent read reviewer --source recent-unwrapped --lines 40

# Send the brief (run_in_background for long jobs; you are notified when it returns)
herdr agent prompt task-b "<brief>" --wait --timeout 3000000

# Answer a prompt on its screen after the user (or the rules) allow it
herdr agent send-keys task-b enter

# Close the tab when done (tab id from `herdr tab list --workspace "$HERDR_WORKSPACE_ID"`)
herdr tab close <tab-id>
```

Watch several workers from one background command that exits on the first block or when all settle:

```bash
while true; do s=""; for t in task-a task-c task-d; do
  st=$(herdr agent get $t 2>&1 | grep -o '"agent_status":"[a-z]*"' | cut -d'"' -f4); s="$s $t=$st"; done
  case "$s" in *blocked*) echo "BLOCKED:$s"; exit 0;; esac
  case "$s" in *working*|*unknown*) sleep 10;; *) echo "SETTLED:$s"; exit 0;; esac; done
```

When it exits on BLOCKED: `herdr agent read <name> --source recent-unwrapped --lines 40`, relay it to the user (SKILL
step 6), answer, then start the watch again for the ones still working.

## Agent tool (no herdr)

- One `Agent` call per task with `subagent_type: "general-purpose"` (or a project agent type), `model` per the plan
  (`opus`, `sonnet`, `haiku`), and `isolation: "worktree"` when everything the task needs is tracked in git.
- The prompt is the full brief (the agent starts cold): plan file path, task id, owned files, rules, report file.
- Agents run in the background and you are notified when each finishes; don't poll. Continue one with `SendMessage`.
- Permission prompts surface to the user directly; you can't relay them, so keep briefs inside the project rules.

## codex exec (Codex without herdr)

Non-interactive; run it with `run_in_background` and the sandbox disabled (Codex keeps state in `~/.codex`).

```bash
codex exec -C "$PWD" -s workspace-write -c 'model_reasoning_effort="high"' \
  -o "$TMPDIR/codex-last.txt" "<review brief>"
```

`-o` saves its final message; the review itself goes to the file the brief names. `codex exec review` is Codex's own
review of the current repository, a quicker alternative to a written brief.

For an interactive Codex session the user already has open outside herdr, agent-kit projects ship
`python3 scripts/watch-codex.py --send "..."`: it queues the message and prints Codex's reply when its turn ends.

## Codex quirks

- First start in a folder asks whether to trust it (saved for later sessions): ask the user, then `send-keys enter`.
- If it hangs at startup (even `codex --version`), check for an update (`brew upgrade --cask codex` on Homebrew) and
  ask the user before upgrading.
- macOS may ask the user to allow its downloaded helper binaries (`codex-code-mode-host`, `rg`). Tell the user what
  they are (part of the Codex package) before they click.
- It can't write git metadata from its sandbox; no worker commits anyway: the lead commits its changes with
  `Co-Authored-By: Codex <noreply@openai.com>`.
- With `-c` overrides it warns "Running without the shared background server" and herdr may show it as `blocked`
  until the warning is dismissed (`esc`). Harmless.
- Put "code only, no Computer Use, screen, app or GUI actions" in every brief.
