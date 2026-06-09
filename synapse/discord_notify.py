"""Push Claude Code progress to the active Discord thread (Hermes gateway)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_ENV_FILE = os.path.expanduser("~/下载/dev/hermes/.hermes/.env")


def _read_env_file(key: str, env_file: str = DEFAULT_ENV_FILE) -> Optional[str]:
    if not os.path.isfile(env_file):
        return None
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, value = line.partition("=")
            if k.strip() == key:
                return value.strip().strip("'\"")
    return None


def _discord_channel_id() -> Optional[str]:
    """Resolve Discord channel/thread id from Hermes session env."""
    explicit = os.environ.get("SYNAPSE_DISCORD_CHANNEL_ID")
    if explicit:
        return explicit
    thread = os.environ.get("HERMES_SESSION_THREAD_ID", "").strip()
    if thread:
        return thread
    chat = os.environ.get("HERMES_SESSION_CHAT_ID", "").strip()
    if chat:
        return chat
    return None


def _discord_enabled() -> bool:
    if os.environ.get("SYNAPSE_DISCORD_NOTIFY", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    platform = os.environ.get("HERMES_SESSION_PLATFORM", "").strip().lower()
    return platform == "discord" or bool(os.environ.get("SYNAPSE_DISCORD_CHANNEL_ID"))


def post_discord(content: str) -> bool:
    """Post a short message to the current Discord thread. Returns True on success."""
    if not _discord_enabled():
        return False

    channel_id = _discord_channel_id()
    token = _read_env_file("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN")
    if not channel_id or not token:
        return False

    if len(content) > 1900:
        content = content[:1897] + "..."

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "Synapse (https://github.com/user/synapse)",
        },
        method="POST",
    )

    proxy = _read_env_file("DISCORD_PROXY") or os.environ.get("DISCORD_PROXY")
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = urllib.request.build_opener()

    try:
        with opener.open(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def notify_progress(event_type: str, tool: str, status: str, detail: str) -> None:
    """Format and send a progress line to Discord."""
    if event_type == "task":
        post_discord(f"🧠 **Claude Code 开始**\n`{detail[:200]}`")
        return
    if event_type == "progress" and status == "running":
        post_discord(f"🔧 `{detail[:500]}`")
        return
    if event_type == "result" and tool == "claude":
        mark = "✅" if status == "ok" else "❌"
        post_discord(f"{mark} **Claude Code 完成** — {detail}")
