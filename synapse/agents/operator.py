"""Operator agent — executes shell commands and filesystem operations.

This is the simplest built-in agent. It receives a task instruction,
runs it as a bash command via subprocess, and returns the output.
"""

from __future__ import annotations

import subprocess
from typing import Iterator

from synapse.protocol import (
    Message,
    ProgressMessage,
    ProgressStatus,
    ResultMessage,
    TaskMessage,
    TaskStatus,
)


class OperatorAgent:
    """Shell agent that runs bash commands.

    Receives task instructions and executes them as shell commands.
    Yields progress messages for each step and a result message on completion.
    """

    def __init__(self, name: str = "operator"):
        self.name = name

    def run(self, task: TaskMessage) -> Iterator[Message]:
        """Execute a shell command specified in the task instruction.

        Yields:
            ProgressMessage: When the command starts and finishes.
            ResultMessage: With stdout/stderr and exit status.
        """
        instruction = task.instruction

        yield ProgressMessage(
            task_id=task.id,
            tool="Bash",
            status=ProgressStatus.STARTED,
            detail=f"Running: {instruction[:80]}",
        )

        try:
            result = subprocess.run(
                instruction,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout.strip()
            error = result.stderr.strip()

            if result.returncode == 0:
                yield ProgressMessage(
                    task_id=task.id,
                    tool="Bash",
                    status=ProgressStatus.DONE,
                    detail=f"Completed (exit {result.returncode})",
                )
                yield ResultMessage(
                    task_id=task.id,
                    status=TaskStatus.OK,
                    output=output or f"Command completed with exit code 0",
                )
            else:
                yield ProgressMessage(
                    task_id=task.id,
                    tool="Bash",
                    status=ProgressStatus.ERROR,
                    detail=f"Failed (exit {result.returncode})",
                )
                yield ResultMessage(
                    task_id=task.id,
                    status=TaskStatus.ERROR,
                    output=output,
                    error=error or f"Exit code: {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            yield ResultMessage(
                task_id=task.id,
                status=TaskStatus.TIMEOUT,
                error=f"Command timed out after 60s: {instruction[:80]}",
            )
        except Exception as e:
            yield ResultMessage(
                task_id=task.id,
                status=TaskStatus.ERROR,
                error=str(e),
            )

    def __repr__(self) -> str:
        return f"<OperatorAgent(name={self.name!r})>"
