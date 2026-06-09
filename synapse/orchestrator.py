"""Agent orchestrator — registry, task dispatch, and message bus.

Stores agent definitions in the shared memory DB so registrations
survive restarts. Dispatches tasks to agents via subprocess with
JSON Lines protocol over stdin/stdout.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from synapse.memory import MemoryStore
from synapse.protocol import (
    Message,
    MessageType,
    ProgressMessage,
    ProgressStatus,
    ResultMessage,
    TaskMessage,
    TaskStatus,
    decode,
    encode,
)


@dataclass
class Agent:
    """A registered agent that can receive and execute tasks."""
    name: str
    cmd: str
    description: str = ""
    status: str = "registered"


class MessageBus:
    """Simple pub/sub message bus for agent progress events."""

    def __init__(self):
        self._subscribers: List[Callable[[Message], None]] = []

    def subscribe(self, callback: Callable[[Message], None]) -> None:
        """Register a callback to receive all messages."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Message], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, message: Message) -> None:
        """Publish a message to all subscribers."""
        for subscriber in self._subscribers:
            try:
                subscriber(message)
            except Exception:
                pass  # Don't let one bad subscriber break others


class Orchestrator:
    """Central orchestrator for Synapse.

    Manages agent registry (persisted in SQLite), dispatches tasks to agents
    via subprocess with JSON Lines protocol, and broadcasts progress on the
    message bus.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._store = MemoryStore(db_path=db_path)
        self._store._ensure_db()
        self.bus = MessageBus()
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._running = False

    @property
    def agents(self) -> List[Dict[str, Any]]:
        """List all registered agents."""
        return self._store.list_agents()

    def register_agent(
        self, name: str, cmd: str, description: str = ""
    ) -> None:
        """Register an agent in the persistent registry."""
        self._store.register_agent(name, cmd, description)
        self.bus.publish(
            ResultMessage(
                task_id="",
                status=TaskStatus.OK,
                output=f"Agent '{name}' registered with cmd: {cmd}",
            )
        )

    def remove_agent(self, name: str) -> bool:
        """Remove an agent from the registry."""
        removed = self._store.remove_agent(name)
        if removed:
            self.bus.publish(
                ResultMessage(
                    task_id="",
                    status=TaskStatus.OK,
                    output=f"Agent '{name}' removed",
                )
            )
        return removed

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an agent by name."""
        return self._store.get_agent(name)

    def dispatch_task(self, instruction: str, context: str = "") -> str:
        """Dispatch a task to the first available agent synchronously.

        Returns the task ID so progress can be tracked.
        """
        task_id = uuid.uuid4().hex[:8]
        agents = self._store.list_agents()

        if not agents:
            msg = ResultMessage(
                task_id=task_id,
                status=TaskStatus.ERROR,
                error="No agents registered. Use 'synapse agent add' first.",
            )
            self.bus.publish(msg)
            return task_id

        # Pick the first agent
        agent = agents[0]
        task_msg = TaskMessage(
            instruction=instruction,
            context=context,
            agent_id=agent["name"],
            id=task_id,
        )

        # Emit progress: task dispatched
        self.bus.publish(
            ProgressMessage(
                task_id=task_id,
                tool="dispatch",
                status=ProgressStatus.STARTED,
                detail=f"Dispatching to {agent['name']}: {instruction}",
            )
        )

        # Run the agent command synchronously
        try:
            result = subprocess.run(
                agent["cmd"],
                input=encode(task_msg),
                capture_output=True,
                text=True,
                timeout=120,
                shell=True,
            )

            if result.returncode == 0:
                output = result.stdout.strip() or "Task completed"
                result_msg = ResultMessage(
                    task_id=task_id,
                    status=TaskStatus.OK,
                    output=output,
                )
            else:
                error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                result_msg = ResultMessage(
                    task_id=task_id,
                    status=TaskStatus.ERROR,
                    error=error,
                )

        except subprocess.TimeoutExpired:
            result_msg = ResultMessage(
                task_id=task_id,
                status=TaskStatus.TIMEOUT,
                error="Task timed out after 120s",
            )
        except Exception as e:
            result_msg = ResultMessage(
                task_id=task_id,
                status=TaskStatus.ERROR,
                error=str(e),
            )

        self.bus.publish(result_msg)
        return task_id

    def start(self) -> None:
        """Start the orchestrator (loads agents, no persistent daemon for v0.1)."""
        self._running = True
        agents = self._store.list_agents()
        agent_count = len(agents)
        print(f"🧠 Synapse orchestrator started. {agent_count} agent(s) loaded.")

    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
        self._store.close()

    def close(self) -> None:
        """Close resources."""
        self._store.close()
