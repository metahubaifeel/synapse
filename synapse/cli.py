"""Synapse CLI — Rich terminal UI for the agent operating system.

Commands:
    synapse start                  Start the orchestrator
    synapse agent add <name> ...   Register an agent
    synapse agent list             List registered agents
    synapse agent remove <name>    Remove an agent
    synapse task <instruction>     Dispatch a task
    synapse memory set <key> <val> Set a shared memory entry
    synapse memory get <key>       Get a memory value
    synapse memory list            List all memory entries
    synapse watch                  Watch Claude Code tool calls (cross-terminal)
"""

from __future__ import annotations

import sys
import time
from typing import Optional

import rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from synapse import __version__
from synapse.memory import MemoryStore
from synapse.orchestrator import Orchestrator
from synapse.watcher import Watcher

console = Console()


def print_banner() -> None:
    """Print the Synapse ASCII banner."""
    banner = Text(
        r"""
╔══════════════════════════════════════╗
║   🧠  S Y N A P S E  v{version}        ║
║   Make Your AI Agents Work Together  ║
╚══════════════════════════════════════╝
""".format(version=__version__),
        style="bold cyan",
    )
    console.print(banner)


def cmd_start(orchestrator: Orchestrator, args: list) -> None:
    """Start the Synapse orchestrator."""
    print_banner()
    orchestrator.start()
    agents = orchestrator.agents
    if agents:
        table = Table(title="Registered Agents")
        table.add_column("Name", style="cyan")
        table.add_column("Command", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Status", style="yellow")
        for agent in agents:
            table.add_row(
                agent["name"],
                agent["cmd"],
                agent.get("description", ""),
                agent.get("status", "registered"),
            )
        console.print(table)
    else:
        console.print("[dim]No agents registered yet. Use 'synapse agent add' to register one.[/dim]")
    console.print("\n[green]✓[/green] Orchestrator ready. Use [bold]synapse task[/bold] to dispatch work.")


def cmd_agent_add(orchestrator: Orchestrator, args: list) -> None:
    """Register a new agent: synapse agent add <name> --cmd <command> [--desc <description>]"""
    import argparse
    parser = argparse.ArgumentParser(prog="synapse agent add", add_help=False)
    parser.add_argument("name")
    parser.add_argument("--cmd", required=True)
    parser.add_argument("--desc", default="")
    try:
        parsed, _ = parser.parse_known_args(args)
    except SystemExit:
        console.print("[red]Usage: synapse agent add <name> --cmd <command> [--desc <description>][/red]")
        return

    orchestrator.register_agent(parsed.name, parsed.cmd, parsed.desc)
    console.print(f"[green]✓[/green] Agent '[bold]{parsed.name}[/bold]' registered (cmd: {parsed.cmd})")


def cmd_agent_list(orchestrator: Orchestrator, args: list) -> None:
    """List all registered agents."""
    agents = orchestrator.agents
    if not agents:
        console.print("[dim]No agents registered.[/dim]")
        return
    table = Table(title="Registered Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Command", style="green")
    table.add_column("Description", style="dim")
    table.add_column("Status", style="yellow")
    for agent in agents:
        table.add_row(
            agent["name"],
            agent["cmd"],
            agent.get("description", ""),
            agent.get("status", "registered"),
        )
    console.print(table)


def cmd_agent_remove(orchestrator: Orchestrator, args: list) -> None:
    """Remove an agent: synapse agent remove <name>"""
    if not args:
        console.print("[red]Usage: synapse agent remove <name>[/red]")
        return
    name = args[0]
    if orchestrator.remove_agent(name):
        console.print(f"[green]✓[/green] Agent '[bold]{name}[/bold]' removed.")
    else:
        console.print(f"[red]✗[/red] Agent '[bold]{name}[/bold]' not found.")


def cmd_task(orchestrator: Orchestrator, args: list) -> None:
    """Dispatch a task: synapse task <instruction>"""
    if not args:
        console.print("[red]Usage: synapse task <instruction>[/red]")
        return
    instruction = " ".join(args)

    # Subscribe to progress events so we can show them
    def on_message(msg):
        from synapse.protocol import MessageType
        if hasattr(msg, 'type'):
            msg_type = msg.type
            if hasattr(msg, 'type') and str(msg.type) == "progress":
                detail = getattr(msg, 'detail', '')
                tool = getattr(msg, 'tool', '')
                console.print(f"  [dim]⏳[/dim] [{tool or '...'}] {detail}")
            elif hasattr(msg, 'type') and str(msg.type) == "result":
                status = getattr(msg, 'status', 'ok')
                style = "green" if str(status) == "ok" else "red"
                output = getattr(msg, 'output', '') or getattr(msg, 'error', '')
                console.print(f"  [{style}]●[/{style}] {output}")

    orchestrator.bus.subscribe(on_message)

    console.print(f"[bold]Dispatching task:[/bold] {instruction}")
    task_id = orchestrator.dispatch_task(instruction)
    console.print(f"[dim]Task ID: {task_id}[/dim]")


def cmd_memory_set(orchestrator: Orchestrator, args: list) -> None:
    """Set a memory entry: synapse memory set <key> <value>"""
    if len(args) < 2:
        console.print("[red]Usage: synapse memory set <key> <value>[/red]")
        return
    key = args[0]
    value = " ".join(args[1:])
    with MemoryStore() as store:
        store.set(key, value)
    console.print(f"[green]✓[/green] Memory set: [bold]{key}[/bold] = {value}")


def cmd_memory_get(orchestrator: Orchestrator, args: list) -> None:
    """Get a memory entry: synapse memory get <key>"""
    if not args:
        console.print("[red]Usage: synapse memory get <key>[/red]")
        return
    key = args[0]
    with MemoryStore() as store:
        value = store.get(key)
    if value is not None:
        console.print(f"[bold]{key}[/bold] = {value}")
    else:
        console.print(f"[dim]No value found for key '{key}'[/dim]")


def cmd_memory_list(orchestrator: Orchestrator, args: list) -> None:
    """List all memory entries."""
    with MemoryStore() as store:
        items = store.list()
    if not items:
        console.print("[dim]No memories stored.[/dim]")
        return
    table = Table(title="Shared Memory")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    for key, value in items:
        table.add_row(key, value[:120])
    console.print(table)


def cmd_watch(orchestrator: Orchestrator, args: list) -> None:
    """Watch Claude Code tool calls in real-time (polls shared SQLite events)."""
    watcher = Watcher()
    watcher.run()


def cmd_events_tail(orchestrator: Orchestrator, args: list) -> None:
    """Tail activity events: synapse events tail [-f] [--plain]"""
    follow = "-f" in args or "--follow" in args
    plain = "--plain" in args
    last_id = 0
    with MemoryStore() as store:
        while True:
            rows = store.list_events_since(last_id, limit=100)
            for row in rows:
                last_id = max(last_id, row["id"])
                if plain:
                    if row["event_type"] == "progress":
                        console.print(f"🔧 {row['tool']} {row['detail']}")
                    elif row["event_type"] == "result":
                        console.print(f"● {row['tool']} {row['status']}: {row['detail']}")
                    else:
                        console.print(f"[{row['event_type']}] {row['detail']}")
                else:
                    console.print(
                        f"[dim]{row['id']}[/dim] "
                        f"[cyan]{row['task_id'][:8]}[/cyan] "
                        f"[yellow]{row['event_type']}[/yellow] "
                        f"{row['tool']} {row['detail'][:80]}"
                    )
            if not follow:
                break
            time.sleep(0.5)


def main() -> None:
    """Main entry point for the Synapse CLI."""
    if len(sys.argv) < 2:
        print_banner()
        console.print(
            Panel(
                "Usage:\n"
                "  synapse start                  Start the orchestrator\n"
                "  synapse agent add <name> ...   Register an agent\n"
                "  synapse agent list             List agents\n"
                "  synapse agent remove <name>    Remove an agent\n"
                "  synapse task <instruction>     Dispatch a task\n"
                "  synapse memory set <k> <v>     Set memory\n"
                "  synapse memory get <k>         Get memory\n"
                "  synapse memory list            List memory\n"
                "  synapse watch                  Watch Claude Code activity (auto-opens on delegate)\n"
                "  synapse events tail [-f]         Tail tool-call events\n"
                "  synapse-wrap \"task\"            Run Claude Code with live visibility\n"
                "  synapse --version              Show version",
                title="🧠 Synapse",
                border_style="cyan",
            )
        )
        return

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "--version" or command == "-V":
        console.print(f"Synapse v{__version__}")
        return

    orchestrator = Orchestrator()

    try:
        if command == "start":
            cmd_start(orchestrator, args)
        elif command == "agent":
            if not args:
                console.print("[red]Usage: synapse agent <add|list|remove> ...[/red]")
                return
            subcmd = args[0]
            subargs = args[1:]
            if subcmd == "add":
                cmd_agent_add(orchestrator, subargs)
            elif subcmd == "list":
                cmd_agent_list(orchestrator, subargs)
            elif subcmd == "remove":
                cmd_agent_remove(orchestrator, subargs)
            else:
                console.print(f"[red]Unknown agent command: {subcmd}[/red]")
        elif command == "task":
            cmd_task(orchestrator, args)
        elif command == "memory":
            if not args:
                console.print("[red]Usage: synapse memory <set|get|list> ...[/red]")
                return
            subcmd = args[0]
            subargs = args[1:]
            if subcmd == "set":
                cmd_memory_set(orchestrator, subargs)
            elif subcmd == "get":
                cmd_memory_get(orchestrator, subargs)
            elif subcmd == "list":
                cmd_memory_list(orchestrator, subargs)
            else:
                console.print(f"[red]Unknown memory command: {subcmd}[/red]")
        elif command == "watch":
            cmd_watch(orchestrator, args)
        elif command == "events":
            if args and args[0] == "tail":
                cmd_events_tail(orchestrator, args[1:])
            else:
                console.print("[red]Usage: synapse events tail [-f] [--plain][/red]")
        else:
            console.print(f"[red]Unknown command: {command}[/red]")
            console.print("[dim]Run 'synapse' without arguments for help.[/dim]")
    finally:
        orchestrator.close()
