"""Coder agent — wraps CLI coding tools like Claude Code.

In v0.1 this is a stub agent that demonstrates the agent protocol.
Future versions will integrate with Claude Code / Codex for real code generation.
"""

from __future__ import annotations

from typing import Iterator

from synapse.protocol import (
    Message,
    ProgressMessage,
    ProgressStatus,
    ResultMessage,
    TaskMessage,
    TaskStatus,
)


class CoderAgent:
    """Code generation agent (placeholder for v0.1).

    Accepts coding tasks and returns placeholder results.
    Will integrate with Claude Code / Codex in future versions.
    """

    def __init__(self, name: str = "coder"):
        self.name = name

    def run(self, task: TaskMessage) -> Iterator[Message]:
        """Handle a coding task (stub implementation).

        Yields:
            ProgressMessage: Simulated coding steps.
            ResultMessage: Placeholder code output.
        """
        instruction = task.instruction

        yield ProgressMessage(
            task_id=task.id,
            tool="Read",
            status=ProgressStatus.STARTED,
            detail="Reading project structure...",
        )

        yield ProgressMessage(
            task_id=task.id,
            tool="Write",
            status=ProgressStatus.RUNNING,
            detail="Generating code...",
        )

        yield ProgressMessage(
            task_id=task.id,
            tool="Bash",
            status=ProgressStatus.RUNNING,
            detail="Running tests...",
        )

        yield ProgressMessage(
            task_id=task.id,
            tool="Write",
            status=ProgressStatus.DONE,
            detail="Code generation complete",
        )

        yield ResultMessage(
            task_id=task.id,
            status=TaskStatus.OK,
            output=(
                f"[Coder stub] Task: {instruction}\n"
                "Code generation will be available in a future version.\n"
                "This agent currently demonstrates the Synapse protocol."
            ),
        )

    def __repr__(self) -> str:
        return f"<CoderAgent(name={self.name!r})>"
