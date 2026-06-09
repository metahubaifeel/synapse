"""Auto-launch synapse watch so the user never opens a second terminal manually."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _synapse_bin() -> str:
    explicit = os.environ.get("SYNAPSE_BIN")
    if explicit and os.path.isfile(explicit):
        return explicit

    # synapse-wrap runs from .venv/bin/python — sibling is synapse CLI
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    sibling = os.path.join(exe_dir, "synapse")
    if os.path.isfile(sibling):
        return sibling

    # synapse/synapse/autowatch.py → project root is two levels up
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv = os.path.join(project_root, ".venv", "bin", "synapse")
    if os.path.isfile(venv):
        return venv

    found = shutil.which("synapse")
    if found:
        return found

    return venv


def _watch_already_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", r"synapse watch"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _auto_watch_enabled() -> bool:
    val = os.environ.get("SYNAPSE_AUTO_WATCH", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def ensure_watch_terminal() -> bool:
    """Open synapse watch in a new terminal if not already running.

    Returns True if a new watch window was launched.
    """
    if not _auto_watch_enabled():
        return False
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    if _watch_already_running():
        return False

    synapse = _synapse_bin()
    # Quote path — project dir may contain spaces or non-ASCII chars
    inner = f'"{synapse}" watch; exec bash'
    launchers = [
        ["gnome-terminal", "--title=Synapse Watch", "--", "bash", "-c", inner],
        ["konsole", "--title", "Synapse Watch", "-e", "bash", "-c", inner],
        ["xfce4-terminal", "--title=Synapse Watch", "-e", f"bash -c '{inner}'"],
        ["xterm", "-title", "Synapse Watch", "-e", "bash", "-c", inner],
    ]

    for cmd in launchers:
        bin_path = shutil.which(cmd[0])
        if not bin_path:
            continue
        try:
            subprocess.Popen(
                [bin_path, *cmd[1:]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    return False
