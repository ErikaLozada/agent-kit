#!/usr/bin/env python3
"""Measure where the time went in one or more agent sessions.

Reads coding-agent transcripts (pi, Claude Code and Codex JSONL), normalises them to one
event stream, and writes:

  metrics.json   numbers for the retrospective page (every figure on the page
                 should come from here)
  timeline.md    a readable, timestamped log: user turns, assistant text, tool
                 calls and the size of each tool result

Usage:
  session_metrics.py --project . --out .scratch/retro
  session_metrics.py --session path/to/a.jsonl --session b.jsonl --out .scratch/retro \
      --milestone "first viewable draft=13:42:41" --until 14:05:00 \
      --bucket "deploy=make deploy|docker compose"

Times given as HH:MM[:SS] are local time on the session's first day; give a full ISO
timestamp (2026-11-14T13:42:41+11:00) for a session that runs past midnight.
Human waits longer than --away minutes (default 30) are reported as "away", not as
human time.
Standard library only; run it with `python3 -I`.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import statistics
import sys
from pathlib import Path

# ---------------------------------------------------------------- discovery


def slug_pi(path: Path) -> str:
    return "--" + str(path).strip("/").replace("/", "-") + "--"


def slug_claude(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _worktrees(project: Path) -> list[Path]:
    """Checkouts git knows about for this repo (agent-kit's `make task` makes sibling worktrees)."""
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(project), "worktree", "list", "--porcelain"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [Path(line[9:]) for line in out.splitlines() if line.startswith("worktree ")]


def _codex_cwd(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            first = json.loads(handle.readline())
    except (OSError, json.JSONDecodeError):
        return None
    return (first.get("payload") or {}).get("cwd") if first.get("type") == "session_meta" else None


def discover(project: Path, siblings: bool = False) -> list[Path]:
    """Transcripts recorded in this project and its live worktrees, for pi, Claude Code and Codex.

    siblings=True also takes folders named <project>-<anything> (removed agent-kit task worktrees). Check the
    list it prints: an unrelated sibling project with the same prefix matches too.
    """
    project = project.resolve()
    roots = {project, *(w.resolve() for w in _worktrees(project))}
    home = Path.home()

    def wanted(cwd: str) -> bool:
        p = Path(cwd)
        return p in roots or (siblings and p.parent == project.parent and p.name.startswith(project.name + "-"))

    found: list[Path] = []
    pi_root = home / ".pi" / "agent" / "sessions"
    cc_root = home / ".claude" / "projects"
    for root in sorted(roots):
        for folder in (pi_root / slug_pi(root), cc_root / slug_claude(root)):
            if folder.is_dir():
                found += sorted(folder.glob("*.jsonl"))
    if siblings:
        for folder in sorted(pi_root.glob(slug_pi(project)[:-2] + "-*--")) if pi_root.is_dir() else []:
            found += sorted(folder.glob("*.jsonl"))
        for folder in sorted(cc_root.glob(slug_claude(project) + "-*")) if cc_root.is_dir() else []:
            found += sorted(folder.glob("*.jsonl"))
    codex_root = home / ".codex" / "sessions"
    if codex_root.is_dir():
        for rollout in sorted(codex_root.rglob("rollout-*.jsonl")):
            cwd = _codex_cwd(rollout)
            if cwd and wanted(cwd):
                found.append(rollout)
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------- parsing


def parse_ts(value) -> dt.datetime:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000).astimezone()
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for block in content or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                out.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                out.append(text_of(block.get("content")))
    return "\n".join(out)


def call_summary(name: str, args) -> str:
    if not isinstance(args, dict):
        return str(args)
    for key in ("command", "path", "file_path", "pattern", "url", "query", "prompt", "description"):
        if args.get(key):
            return str(args[key])
    return json.dumps(args)[:400]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def detect(rows: list[dict]) -> str:
    for row in rows[:20]:
        if row.get("type") == "session" and "version" in row:
            return "pi"
        if row.get("type") == "session_meta":
            return "codex"
        if row.get("type") in ("user", "assistant") and "sessionId" in row:
            return "claude-code"
    return "unknown"


def events_pi(rows: list[dict]) -> tuple[list[dict], dict]:
    events, meta = [], {"harness": "pi", "models": []}
    for row in rows:
        kind = row.get("type")
        if kind == "session":
            meta["id"] = row.get("id")
            meta["cwd"] = row.get("cwd")
            meta["start"] = parse_ts(row["timestamp"])
        elif kind == "model_change":
            meta["models"].append(f"{row.get('provider')}/{row.get('modelId')}")
        elif kind == "message":
            msg = row["message"]
            role = msg.get("role")
            ts = parse_ts(row["timestamp"])
            if role == "user":
                events.append({"kind": "user", "ts": ts, "text": text_of(msg.get("content"))})
            elif role == "assistant":
                calls = [
                    {"name": c.get("name", "?"), "summary": call_summary(c.get("name", ""), c.get("arguments"))}
                    for c in msg.get("content", []) if c.get("type") == "toolCall"
                ]
                usage = msg.get("usage") or {}
                events.append({
                    "kind": "assistant", "ts": ts, "calls": calls,
                    "text": "\n".join(c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text"),
                    "ctx": (usage.get("input") or 0) + (usage.get("cacheRead") or 0) + (usage.get("cacheWrite") or 0),
                    "out": usage.get("output") or 0,
                    "cost": ((usage.get("cost") or {}).get("total") or 0),
                    "model": msg.get("model"),
                })
            elif role == "toolResult":
                body = text_of(msg.get("content"))
                events.append({"kind": "tool_result", "ts": ts, "chars": len(body), "head": body[:240],
                               "error": bool(msg.get("isError")) or looks_failed(body)})
    return events, meta


def events_claude(rows: list[dict]) -> tuple[list[dict], dict]:
    events, meta = [], {"harness": "claude-code", "models": []}
    current = None  # merge streamed records of one assistant message
    for row in rows:
        kind = row.get("type")
        if kind not in ("user", "assistant") or "timestamp" not in row:
            continue
        if row.get("isSidechain"):
            continue  # sub-agent records: their time is inside the parent's tool call
        ts = parse_ts(row["timestamp"])
        meta.setdefault("start", ts)
        meta.setdefault("cwd", row.get("cwd"))
        meta.setdefault("id", row.get("sessionId"))
        msg = row.get("message") or {}
        if kind == "assistant":
            mid = msg.get("id")
            if current is None or current["_id"] != mid:
                current = {"kind": "assistant", "ts": ts, "calls": [], "text": "", "ctx": 0, "out": 0,
                           "cost": 0, "model": msg.get("model"), "_id": mid}
                events.append(current)
                if msg.get("model") and msg.get("model") not in meta["models"]:
                    meta["models"].append(msg.get("model"))
            current["ts"] = ts
            for block in msg.get("content") or []:
                if block.get("type") == "text":
                    current["text"] += block.get("text", "")
                elif block.get("type") == "tool_use":
                    current["calls"].append({"name": block.get("name", "?"),
                                             "summary": call_summary(block.get("name", ""), block.get("input"))})
            usage = msg.get("usage") or {}
            current["ctx"] = max(current["ctx"], (usage.get("input_tokens") or 0)
                                 + (usage.get("cache_read_input_tokens") or 0)
                                 + (usage.get("cache_creation_input_tokens") or 0))
            current["out"] = max(current["out"], usage.get("output_tokens") or 0)
            continue
        current = None
        content = msg.get("content")
        if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    body = text_of(block.get("content"))
                    events.append({"kind": "tool_result", "ts": ts, "chars": len(body), "head": body[:240],
                                   "error": bool(block.get("is_error")) or looks_failed(body)})
            continue
        text = text_of(content)
        if row.get("isMeta") or text.lstrip().startswith(("<local-command", "<command-", "<system-reminder")):
            continue
        events.append({"kind": "user", "ts": ts, "text": text})
    for event in events:
        event.pop("_id", None)
    return events, meta


def events_codex(rows: list[dict]) -> tuple[list[dict], dict]:
    """Codex rollout files: response_item records (messages, tool calls, outputs) plus token_count events."""
    events, meta = [], {"harness": "codex", "models": []}
    current = None  # consecutive model output items form one assistant turn
    has_user_items = any(r.get("type") == "event_msg" and (r.get("payload") or {}).get("type") == "item_completed"
                         and ((r["payload"].get("item") or {}).get("type") == "UserMessage") for r in rows)
    for row in rows:
        kind, payload = row.get("type"), row.get("payload") or {}
        if "timestamp" not in row:
            continue
        ts = parse_ts(row["timestamp"])
        ptype = payload.get("type")
        if kind == "session_meta":
            meta.update(id=payload.get("id"), cwd=payload.get("cwd"), start=ts)
        elif kind == "turn_context" and payload.get("model") and payload["model"] not in meta["models"]:
            meta["models"].append(payload["model"])
        elif kind == "event_msg" and ptype == "item_completed" and (payload.get("item") or {}).get("type") == "UserMessage":
            current = None
            text = "\n".join(c.get("text", "") for c in payload["item"].get("content") or [] if isinstance(c, dict))
            events.append({"kind": "user", "ts": ts, "text": text})
        elif kind == "event_msg" and ptype == "token_count" and current is not None:
            last = ((payload.get("info") or {}).get("last_token_usage") or {})
            current["ctx"] = max(current["ctx"], last.get("input_tokens") or 0)
            current["out"] = max(current["out"], last.get("output_tokens") or 0)
        elif kind == "response_item":
            role = payload.get("role")
            if ptype == "message" and role == "user":
                if has_user_items:
                    continue
                text = text_of([{"type": "text", "text": c.get("text", "")} for c in payload.get("content") or []])
                if text.lstrip().startswith("<"):
                    continue  # injected environment / instructions, not the human
                current = None
                events.append({"kind": "user", "ts": ts, "text": text})
            elif ptype in ("message", "reasoning", "function_call", "custom_tool_call", "local_shell_call") and role != "developer":
                if current is None:
                    current = {"kind": "assistant", "ts": ts, "calls": [], "text": "", "ctx": 0, "out": 0, "cost": 0, "model": None}
                    events.append(current)
                current["ts"] = ts
                if ptype == "message":
                    current["text"] += "".join(c.get("text", "") for c in payload.get("content") or [] if isinstance(c, dict))
                elif ptype != "reasoning":
                    args = payload.get("input") or payload.get("arguments") or payload.get("action") or ""
                    if isinstance(args, str):
                        try:
                            parsed = json.loads(args)
                            args = parsed if isinstance(parsed, dict) else args
                        except json.JSONDecodeError:
                            pass
                    if isinstance(args, dict) and isinstance(args.get("command"), list):
                        args = {**args, "command": " ".join(map(str, args["command"]))}
                    name = payload.get("name") or ptype
                    current["calls"].append({"name": name, "summary": call_summary(name, args if isinstance(args, dict) else {"command": str(args)})})
            elif ptype in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
                output = payload.get("output")
                body = output if isinstance(output, str) else text_of(
                    [{"type": "text", "text": c.get("text", "")} for c in output or [] if isinstance(c, dict)])
                events.append({"kind": "tool_result", "ts": ts, "chars": len(body), "head": body[:240], "error": looks_failed(body)})
                current = None
    return events, meta


FAIL_RE = re.compile(r"error TS\d|Traceback \(most recent|\"status\":\s*\"error\"|No such file or directory|"
                     r"command not found|^\s*FAIL\s|Command exited with code [1-9]|npm error", re.M)


def looks_failed(body: str) -> bool:
    return bool(FAIL_RE.search(body or ""))


# ---------------------------------------------------------------- classification

DEFAULT_BUCKETS = [
    ("sub-agent / reviewer", r"^(Task|Agent)$|\b(pi --print|claude -p|codex exec)\b"),
    ("package / registry archaeology", r"npm (pack|view)|pip download|registry\.npmjs|pypi\.org|git ls-remote"),
    ("reading package internals", r"node_modules/|site-packages/|\.d\.ts\b"),
    ("checks (types, tests, lint, build, validate)", r"\b(tsc|vitest|jest|pytest|eslint|ruff|mypy)\b|npm (run )?(test|build|lint)|validate"),
    ("install / scaffold", r"npm (install|ci|create|init)|uv tool install|pip install|brew install|install\.sh|create-"),
    ("git", r"(^|[;&|]\s*|\n)git\s"),
    ("web", r"^(WebFetch|WebSearch)$|https?://"),
]
WRITE_TOOLS = {"write", "edit", "Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"read", "Read", "Grep", "Glob", "LS", "grep", "find", "ls"}
WRITE_RE = re.compile(r"cat\s*>{1,2}|<<\s*'?EOF'?\s*>|\btee\b|open\([^)]*['\"][wa]['\"]|\.write\(|printf .*>|>\s*[\w./-]+\.(ts|tsx|js|mjs|json|dax|md|css|html)\b")
READ_RE = re.compile(r"(^|[;&]\s*)(sed -n|cat |head |tail |grep |rg |find |ls |wc |less )")


def classify(call: dict, extra: list[tuple[str, re.Pattern]]) -> str:
    name, summary = call["name"], call["summary"]
    probe = f"{name}\n{summary}" if name not in ("bash", "Bash") else summary
    for label, pattern in extra:
        if pattern.search(probe):
            return label
    if name in WRITE_TOOLS:
        return "write code / docs"
    if name in READ_TOOLS and "node_modules" not in summary:
        return "read / explore"
    for label, pattern in DEFAULT_BUCKETS:
        if re.search(pattern, probe):
            if label == "web" and name in ("bash", "Bash") and "curl" not in summary:
                continue
            return label
    if WRITE_RE.search(summary):
        return "write code / docs"
    if READ_RE.search(summary) or name in READ_TOOLS:
        return "read / explore"
    return "other"


# ---------------------------------------------------------------- analysis


def local_time(day: dt.datetime, hhmm: str) -> dt.datetime:
    if "T" in hhmm or "-" in hhmm:
        return parse_ts(hhmm)
    parts = [int(p) for p in hhmm.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return day.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)


def annotate(events: list[dict]) -> None:
    """Attach durations: human wait, model generation, tool runtime."""
    prev = None
    last_assistant = None
    for event in events:
        gap = (event["ts"] - prev["ts"]).total_seconds() if prev else 0.0
        if event["kind"] == "user":
            event["human_s"] = gap if prev else 0.0
        elif event["kind"] == "assistant":
            event["model_s"] = gap
            last_assistant = event
            event["tool_s"] = 0.0
        elif event["kind"] == "tool_result" and last_assistant is not None:
            last_assistant["tool_s"] = max(last_assistant["tool_s"],
                                           (event["ts"] - last_assistant["ts"]).total_seconds())
        prev = event


AWAY_S = 30 * 60  # a wait longer than this is the human being away, not reading; reported apart


def summarise(events: list[dict], start: dt.datetime, end: dt.datetime, extra) -> dict:
    window = [e for e in events if start <= e["ts"] <= end]
    users = [e for e in window if e["kind"] == "user"]
    turns = [e for e in window if e["kind"] == "assistant"]
    results = [e for e in window if e["kind"] == "tool_result"]
    first_user = users[0]["ts"] if users else start
    waits = [e.get("human_s", 0) for e in users[1:]]  # the first prompt has no wait before it
    human = sum(w for w in waits if w <= AWAY_S)
    away = sum(w for w in waits if w > AWAY_S)
    model = sum(e.get("model_s", 0) for e in turns)
    tool = sum(e.get("tool_s", 0) for e in turns)
    calls = [c for t in turns for c in t["calls"]]
    buckets = collections.defaultdict(lambda: {"turns": 0.0, "calls": 0, "model_s": 0.0, "tool_s": 0.0, "out_tokens": 0})
    for turn in turns:
        labels = [classify(c, extra) for c in turn["calls"]] or ["reply to human (no tool call)"]
        share = 1 / len(labels)
        for label in labels:
            b = buckets[label]
            b["turns"] += share
            b["calls"] += 1 if turn["calls"] else 0
            b["model_s"] += turn.get("model_s", 0) * share
            b["tool_s"] += turn.get("tool_s", 0) * share
            b["out_tokens"] += int(turn.get("out", 0) * share)
    lat = [t.get("model_s", 0) for t in turns if t.get("model_s", 0) > 0]
    ctx = [t.get("ctx", 0) for t in turns]
    return {
        "from": first_user.isoformat(timespec="seconds"),
        "to": end.isoformat(timespec="seconds"),
        "wall_min": round((end - first_user).total_seconds() / 60, 1),
        "human_min": round(human / 60, 1),
        "human_turns": max(len(users) - 1, 0),
        "away_min": round(away / 60, 1),
        "away_breaks": sum(1 for w in waits if w > AWAY_S),
        "model_min": round(model / 60, 1),
        "tool_min": round(tool / 60, 1),
        "assistant_turns": len(turns),
        "tool_calls": len(calls),
        "turns_with_parallel_calls": sum(1 for t in turns if len(t["calls"]) > 1),
        "failed_tool_results": sum(1 for r in results if r.get("error")),
        "tool_output_chars": sum(r.get("chars", 0) for r in results),
        "latency_median_s": {
            "first_40_turns": round(statistics.median(lat[:40]), 1) if lat else None,
            "last_40_turns": round(statistics.median(lat[-40:]), 1) if lat else None,
        },
        "context_tokens": {"first": ctx[0] if ctx else 0, "last": ctx[-1] if ctx else 0, "max": max(ctx) if ctx else 0},
        "cost_usd": round(sum(t.get("cost", 0) for t in turns), 4),
        "buckets": {k: {kk: (round(vv / 60, 1) if kk.endswith("_s") else round(vv, 1) if isinstance(vv, float) else vv)
                        for kk, vv in v.items()}
                    for k, v in sorted(buckets.items(), key=lambda kv: -(kv[1]["model_s"] + kv[1]["tool_s"]))},
    }


def phases(events: list[dict], end: dt.datetime) -> list[dict]:
    """One phase per user turn: the human's message and the agent run that followed."""
    out, current = [], None
    for event in events:
        if event["ts"] > end:
            break
        if event["kind"] == "user":
            if current:
                out.append(current)
            current = {"start": event["ts"], "end": event["ts"], "human_wait_min": round(event.get("human_s", 0) / 60, 1),
                       "prompt": event["text"][:300], "turns": 0, "calls": 0, "model_s": 0.0, "tool_s": 0.0,
                       "errors": 0, "reply": ""}
            continue
        if current is None:
            continue
        current["end"] = event["ts"]
        if event["kind"] == "assistant":
            current["turns"] += 1
            current["calls"] += len(event["calls"])
            current["model_s"] += event.get("model_s", 0)
            current["tool_s"] += event.get("tool_s", 0)
            if event["text"].strip():
                current["reply"] = event["text"][:300]
        elif event["kind"] == "tool_result" and event.get("error"):
            current["errors"] += 1
    if current:
        out.append(current)
    for p in out:
        p["agent_wall_min"] = round((p["end"] - p["start"]).total_seconds() / 60, 1)
        p["model_min"] = round(p.pop("model_s") / 60, 1)
        p["tool_min"] = round(p.pop("tool_s") / 60, 1)
        p["start"] = p["start"].strftime("%H:%M:%S")
        p["end"] = p["end"].strftime("%H:%M:%S")
    return out


READ_PATH_RE = re.compile(r"([\w./@~-]+\.(?:md|ts|tsx|mjs|js|json|yml|yaml|dax|css|py|html))\b")
SLICE_RE = re.compile(r"sed -n '?(\d+),(\d+)p'?\s+([^\s;|&'\"]+)")
CD_RE = re.compile(r"^\s*cd\s+([^;&|]+?)\s*(?:;|&&)")


def reads(events: list[dict], end: dt.datetime) -> dict:
    """Which files were read, by full path (a bare name like index.d.ts or SKILL.md exists in many folders).

    repeated: the same path read more than once. sliced: paths read as line ranges (`sed -n a,bp`), which
    cost a turn each and can stop before the part that matters (often a skill's list of references).
    """
    counter, slices = collections.Counter(), collections.defaultdict(list)
    for event in events:
        if event["ts"] > end or event["kind"] != "assistant":
            continue
        for call in event["calls"]:
            if call["name"] in WRITE_TOOLS or classify(call, []) not in ("read / explore", "reading package internals"):
                continue
            text = call["summary"]
            cd = CD_RE.match(text)
            base = cd.group(1).strip() if cd else ""

            def full(path):
                return path if path.startswith(("/", "~")) or not base else os.path.normpath(os.path.join(base, path))

            for a, b, path in SLICE_RE.findall(text):
                slices[full(path)].append(f"{a}-{b}")
            for path in set(READ_PATH_RE.findall(text)):
                counter[full(path)] += 1
    return {
        "repeated": [(p, n) for p, n in counter.most_common(15) if n > 1],
        "sliced_files": len(slices),
        "sliced_reads": sum(len(v) for v in slices.values()),
        "sliced": sorted(((p, r) for p, r in slices.items()), key=lambda kv: -len(kv[1]))[:20],
    }


def largest_outputs(events: list[dict], end: dt.datetime, n: int = 10) -> list[dict]:
    pairs, last = [], None
    for event in events:
        if event["ts"] > end:
            break
        if event["kind"] == "assistant":
            last = event
        elif event["kind"] == "tool_result":
            pairs.append({"time": event["ts"].strftime("%H:%M:%S"), "chars": event["chars"],
                          "call": (last["calls"][0]["summary"][:160] if last and last["calls"] else "")})
    return sorted(pairs, key=lambda p: -p["chars"])[:n]


def write_timeline(events: list[dict], meta: dict, path: Path) -> None:
    lines = [f"# Timeline: {meta.get('file')}", "",
             f"harness {meta['harness']} · models {', '.join(meta.get('models') or ['?'])}", ""]
    for event in events:
        t = event["ts"].strftime("%H:%M:%S")
        if event["kind"] == "user":
            lines += ["", f"## {t} USER (waited {event.get('human_s', 0) / 60:.1f} min)", "", event["text"][:4000], ""]
        elif event["kind"] == "assistant":
            ctx = f" ctx {event.get('ctx', 0) // 1000}k" if event.get("ctx") else ""
            if event["text"].strip():
                lines.append(f"{t} A ({event.get('model_s', 0):.0f}s{ctx}): {event['text'][:900]}")
            for call in event["calls"]:
                lines.append(f"{t}   -> {call['name']}: {call['summary'][:300]}".replace("\n", " ⏎ "))
            if not event["text"].strip() and not event["calls"]:
                lines.append(f"{t} A ({event.get('model_s', 0):.0f}s{ctx}): (empty)")
        else:
            flag = "ERR " if event.get("error") else ""
            lines.append(f"{t}   <- {flag}{event['chars']}ch: {event['head'][:200]}".replace("\n", " | "))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, help="project directory; finds its pi, Claude Code and Codex transcripts")
    ap.add_argument("--siblings", action="store_true", help="also <project>-* folders (removed task worktrees)")
    ap.add_argument("--session", type=Path, action="append", default=[], help="a transcript .jsonl (repeatable)")
    ap.add_argument("--out", type=Path, required=True, help="output directory, e.g. .scratch/retro")
    ap.add_argument("--milestone", action="append", default=[], help='"name=HH:MM:SS" (repeatable)')
    ap.add_argument("--until", help="ignore events after this time (e.g. the retro itself)")
    ap.add_argument("--bucket", action="append", default=[], help='extra "label=regex" classifier, checked first')
    ap.add_argument("--away", type=float, default=30, help="minutes: a longer wait for the human counts as away (default 30)")
    args = ap.parse_args(argv)

    global AWAY_S
    AWAY_S = args.away * 60
    files = list(args.session)
    if args.project:
        files += discover(args.project, args.siblings)
    if not files:
        print("No transcripts found. Pass --session <file.jsonl> or --project <dir>.", file=sys.stderr)
        return 2
    extra = []
    for spec in args.bucket:
        label, _, pattern = spec.partition("=")
        extra.append((label.strip(), re.compile(pattern)))
    args.out.mkdir(parents=True, exist_ok=True)

    sessions = []
    for file in dict.fromkeys(files):
        rows = read_jsonl(file)
        harness = detect(rows)
        if harness == "pi":
            events, meta = events_pi(rows)
        elif harness == "claude-code":
            events, meta = events_claude(rows)
        elif harness == "codex":
            events, meta = events_codex(rows)
        else:
            print(f"skip {file}: unknown transcript format", file=sys.stderr)
            continue
        if not events:
            continue
        events.sort(key=lambda e: e["ts"])
        annotate(events)
        meta["file"] = str(file)
        day = events[0]["ts"]
        end = events[-1]["ts"]
        if args.until and events[0]["ts"] < local_time(day, args.until) < end:
            end = local_time(day, args.until)
        timeline = args.out / f"timeline-{Path(file).stem[:40]}.md"
        write_timeline(events, meta, timeline)
        report = {
            "file": str(file), "harness": harness, "models": meta.get("models"), "cwd": meta.get("cwd"),
            "first_event": events[0]["ts"].isoformat(timespec="seconds"),
            "last_event": events[-1]["ts"].isoformat(timespec="seconds"),
            "timeline": str(timeline),
            "whole_session": summarise(events, events[0]["ts"], end, extra),
            "milestones": {},
            "phases": phases(events, end),
            "reads": reads(events, end),
            "largest_tool_outputs": largest_outputs(events, end),
        }
        for spec in args.milestone:
            name, _, when = spec.partition("=")
            at = local_time(day, when.strip())
            if at <= events[0]["ts"]:
                continue  # this session started after the milestone
            report["milestones"][name.strip()] = summarise(events, events[0]["ts"], min(at, events[-1]["ts"]), extra)
        sessions.append(report)

    # sessions that run inside another session's span are usually sub-agents or reviewers
    for s in sessions:
        s["inside_session"] = [o["file"] for o in sessions if o is not s
                               and o["first_event"] <= s["first_event"] and s["last_event"] <= o["last_event"]]

    out = args.out / "metrics.json"
    out.write_text(json.dumps({"generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                               "sessions": sessions}, indent=1, default=str), encoding="utf-8")
    for s in sessions:
        w = s["whole_session"]
        print(f"{Path(s['file']).name} [{s['harness']} · {s.get('cwd')}] {s['first_event'][11:19]}–{s['last_event'][11:19]} "
              f"wall {w['wall_min']}m human {w['human_min']}m away {w['away_min']}m model {w['model_min']}m tool {w['tool_min']}m "
              f"turns {w['assistant_turns']} calls {w['tool_calls']}"
              + (" (inside another session)" if s["inside_session"] else ""))
        for name, m in s["milestones"].items():
            print(f"   to '{name}': wall {m['wall_min']}m = human {m['human_min']}m + model {m['model_min']}m "
                  f"+ tool {m['tool_min']}m · turns {m['assistant_turns']} · ctx max {m['context_tokens']['max']}")
    print(f"wrote {out} and timeline-*.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
