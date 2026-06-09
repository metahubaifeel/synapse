"""Researcher agent — web search and content extraction placeholder.

In v0.1 this is a stub agent that demonstrates the agent protocol.
Future versions will integrate web search APIs and content extraction.
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


class ResearcherAgent:
    """Web research agent (placeholder for v0.1).

    Accepts research queries and returns placeholder results.
    Will integrate with web search APIs in future versions.
    """

    def __init__(self, name: str = "researcher"):
        self.name = name

    def run(self, task: TaskMessage) -> Iterator[Message]:
        """Handle a research task (stub implementation).

        Yields:
            ProgressMessage: Simulated research steps.
            ResultMessage: Placeholder research results.
        """
        instruction = task.instruction

        yield ProgressMessage(
            task_id=task.id,
            tool="WebSearch",
            status=ProgressStatus.STARTED,
            detail=f"Searching: {instruction[:80]}",
        )

        yield ProgressMessage(
            task_id=task.id,
            tool="WebFetch",
            status=ProgressStatus.RUNNING,
            detail="Extracting content from top results...",
        )

        yield ProgressMessage(
            task_id=task.id,
            tool="WebSearch",
            status=ProgressStatus.DONE,
            detail="Research complete",
        )

        yield ResultMessage(
            task_id=task.id,
            status=TaskStatus.OK,
            output=(
                f"[Researcher stub] Query: {instruction}\n"
                "Research results will be available in a future version.\n"
                "This agent currently demonstrates the Synapse protocol."
            ),
        )

    def __repr__(self) -> str:
        return f"<ResearcherAgent(name={self.name!r})>"
