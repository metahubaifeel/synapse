"""synapse-wrap — drop-in wrapper for claude-ds with live tool-call visibility.

Runs Claude Code with stream-json, logs each tool call to ~/.synapse/synapse.db,
and prints human-readable progress to stdout (for Hermes terminal output).

Usage (replaces claude-ds):
    synapse-wrap "write a Flask health check API"
    synapse-wrap -p "task description"
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from typing import Any, Dict, Iterator, Optional, TextIO

from synapse.memory import MemoryStore
from synapse.autowatch import ensure_watch_terminal
from synapse.discord_notify import notify_progress

DEFAULT_ENV_FILE = os.path.expanduser("~/下载/dev/hermes/.hermes/.env")
DEFAULT_CLAUDE_BIN = os.path.expanduser(
    "~/.npm/_npx/becf7b9e49303068/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
)


def _load_hermes_env(env_file: str) -> None:
    """Source Hermes .env without clobbering PATH (same pattern as claude-ds)."""
    if not os.path.isfile(env_file):
        return
    old_path = os.environ.get("PATH", "")
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    os.environ["PATH"] = old_path


def _find_claude_bin() -> str:
    explicit = os.environ.get("SYNAPSE_CLAUDE_BIN")
    if explicit and os.path.isfile(explicit):
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    if os.path.isfile(DEFAULT_CLAUDE_BIN):
        return DEFAULT_CLAUDE_BIN
    raise FileNotFoundError(
        "claude binary not found. Set SYNAPSE_CLAUDE_BIN or install @anthropic-ai/claude-code."
    )


def _truncate(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _tool_detail(name: str, inp: Any) -> str:
    if isinstance(inp, dict):
        for key in ("command", "file_path", "path", "pattern", "url", "query"):
            if key in inp and inp[key]:
                return f"{name} {inp[key]}"
        desc = json.dumps(inp, ensure_ascii=False)
        return f"{name} {_truncate(desc)}"
    return name


def _parse_stream_event(ev: Dict[str, Any]) -> Iterator[tuple[str, str, str, str]]:
    """Yield (event_type, tool, status, detail) tuples from one JSON line."""
    ev_type = ev.get("type", "")
    subtype = ev.get("subtype", "")

    if ev_type == "system" and subtype == "init":
        version = ev.get("claude_code_version", "?")
        model = ev.get("model", "?")
        tools = len(ev.get("tools", []))
        yield ("system", "init", "started", f"Claude Code v{version} model={model} tools={tools}")
        return

    if ev_type == "tool_use":
        name = ev.get("name", "?")
        inp = ev.get("input", {})
        yield ("progress", name, "running", _tool_detail(name, inp))
        return

    if ev_type == "tool_result":
        name = ev.get("name", "?")
        res = ev.get("result", "")
        if isinstance(res, str):
            detail = _truncate(res, 100)
        else:
            detail = _truncate(json.dumps(res, ensure_ascii=False), 100)
        yield ("progress", name, "done", detail)
        return

    if ev_type == "assistant":
        content = ev.get("message", {}).get("content", [])
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    yield ("assistant", "", "text", _truncate(text, 200))
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                yield ("progress", name, "running", _tool_detail(name, inp))
        return

    if ev_type == "result":
        status = "ok" if subtype in ("", "success") else subtype
        cost = ev.get("total_cost_usd", 0)
        turns = ev.get("num_turns", 0)
        duration = ev.get("duration_ms", 0)
        detail = f"${cost:.4f} | {turns} turns | {duration}ms"
        yield ("result", "claude", status, detail)
        return

    if ev_type == "stream_event":
        inner = ev.get("event", {})
        if isinstance(inner, dict):
            yield from _parse_stream_event(inner)
        return

    if ev_type == "error":
        yield ("result", "claude", "error", ev.get("message", str(ev)))


def _format_stdout(event_type: str, tool: str, status: str, detail: str) -> Optional[str]:
    """Human-readable line for Hermes terminal output."""
    if event_type == "system":
        return f"[Claude Code] {detail}"
    if event_type == "progress" and status == "running":
        return f"🔧 {detail}"
    if event_type == "progress" and status == "done":
        return f"  ✅ {tool} {detail}"
    if event_type == "assistant":
        return detail
    if event_type == "result":
        mark = "✅ DONE" if status == "ok" else f"❌ {status.upper()}"
        return f"{mark} {detail}"
    return None


def _build_claude_cmd(claude_bin: str, user_args: list[str]) -> list[str]:
    """Build claude command with stream-json unless user already specified format."""
    args = list(user_args)
    has_print = "-p" in args or "--print" in args
    has_format = any(a.startswith("--output-format") for a in args)

    base = [claude_bin]
    if not has_print:
        base.append("-p")
    if "--dangerously-skip-permissions" not in args:
        base.append("--dangerously-skip-permissions")
    if not has_format:
        base.extend(["--output-format", "stream-json", "--verbose"])
    base.extend(args)
    return base


def run_wrap(
    argv: list[str],
    *,
    store: Optional[MemoryStore] = None,
    stdout: TextIO = sys.stdout,
) -> int:
    """Run Claude Code wrapped with event logging. Returns exit code."""
    env_file = os.environ.get("SYNAPSE_ENV_FILE", DEFAULT_ENV_FILE)
    _load_hermes_env(env_file)

    claude_bin = _find_claude_bin()
    task_id = uuid.uuid4().hex[:8]
    cmd = _build_claude_cmd(claude_bin, argv)

    own_store = store is None
    if own_store:
        store = MemoryStore()
        store._ensure_db()

    store.append_event(
        task_id=task_id,
        event_type="task",
        tool="synapse-wrap",
        status="started",
        detail=" ".join(argv)[:500],
    )

    stdout.write(f"[synapse] task_id={task_id}\n")
    stdout.flush()
    notify_progress("task", "synapse-wrap", "started", " ".join(argv)[:200])

    if ensure_watch_terminal():
        stdout.write("[synapse] Watch window opened automatically.\n")
        stdout.flush()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                stdout.write(line + "\n")
                stdout.flush()
                continue

            for event_type, tool, status, detail in _parse_stream_event(ev):
                store.append_event(
                    task_id=task_id,
                    event_type=event_type,
                    tool=tool,
                    status=status,
                    detail=detail,
                )
                if event_type == "progress" and status == "running":
                    notify_progress(event_type, tool, status, detail)
                elif event_type == "result" and tool == "claude":
                    notify_progress(event_type, tool, status, detail)
                formatted = _format_stdout(event_type, tool, status, detail)
                if formatted:
                    stdout.write(formatted + "\n")
                    stdout.flush()
    finally:
        exit_code = proc.wait()

    final_status = "ok" if exit_code == 0 else "error"
    store.append_event(
        task_id=task_id,
        event_type="result",
        tool="synapse-wrap",
        status=final_status,
        detail=f"exit code {exit_code}",
    )
    if own_store:
        store.close()

    return exit_code


def main() -> None:
    if not sys.argv[1:]:
        print("Usage: synapse-wrap [-p] \"task description\"", file=sys.stderr)
        print("  Drop-in replacement for claude-ds with live visibility.", file=sys.stderr)
        print("  Opens synapse watch automatically (set SYNAPSE_AUTO_WATCH=0 to disable).", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_wrap(sys.argv[1:]))
