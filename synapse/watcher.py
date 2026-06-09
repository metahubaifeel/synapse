"""Real-time agent activity watcher using Rich Live display.

Polls ~/.synapse/synapse.db events table so synapse watch works
across terminals (Hermes in one, watch in another).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from synapse.memory import MemoryStore


class Watcher:
    """Real-time Rich Live display polling the shared event log."""

    def __init__(self, db_path: str | None = None):
        self.console = Console()
        self.events: List[Dict[str, Any]] = []
        self.max_events = 50
        self._last_id = 0
        self._store = MemoryStore(db_path=db_path)

    def _poll(self) -> None:
        """Fetch new events from SQLite since last poll."""
        rows = self._store.list_events_since(self._last_id, limit=200)
        for row in rows:
            self._last_id = max(self._last_id, row["id"])
            created = datetime.fromtimestamp(row["created_at"]).strftime("%H:%M:%S")
            self.events.append(
                {
                    "time": created,
                    "type": row["event_type"],
                    "task_id": row["task_id"],
                    "tool": row["tool"],
                    "status": row["status"],
                    "detail": row["detail"],
                }
            )
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

    def _build_table(self) -> Table:
        table = Table(
            title="Synapse — Claude Code Activity",
            title_style="bold cyan",
            expand=True,
        )
        table.add_column("Time", style="dim", width=10)
        table.add_column("Type", style="yellow", width=10)
        table.add_column("Task", style="cyan", width=10)
        table.add_column("Tool", style="green", width=12)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("Detail", style="white")

        for event in self.events[-40:]:
            status_str = event["status"]
            status_style = ""
            if status_str in ("ok", "done"):
                status_style = "green"
            elif status_str == "error":
                status_style = "red"
            elif status_str in ("running", "started"):
                status_style = "yellow"

            table.add_row(
                event["time"],
                event["type"],
                (event["task_id"] or "")[:8],
                event["tool"],
                f"[{status_style}]{status_str}[/{status_style}]" if status_style else status_str,
                (event["detail"] or "")[:100],
            )
        return table

    def run(self) -> None:
        """Run the live watcher until Ctrl-C."""
        self._store._ensure_db()

        self.console.print(
            Panel(
                "Watching Claude Code tool calls... Press [bold]Ctrl+C[/bold] to stop.\n"
                "Hermes delegates via claude-ds — watch opens automatically.\n"
                "No manual setup needed.",
                title="Synapse Watch",
                border_style="cyan",
            )
        )

        try:
            with Live(
                self._build_table(),
                console=self.console,
                refresh_per_second=4,
                screen=False,
            ) as live:
                while True:
                    self._poll()
                    live.update(self._build_table())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            self.console.print("\n[dim]Watch stopped.[/dim]")
        finally:
            self._store.close()
