"""Abstract base class for Synapse agents.

Any agent must implement the run() method which receives a TaskMessage
and yields ProgressMessage / ResultMessage objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from synapse.protocol import Message, TaskMessage


class BaseAgent(ABC):
    """Abstract agent that can execute tasks.

    Subclasses implement run() to process a task and yield messages.
    """

    def __init__(self, name: str = "base"):
        self.name = name

    @abstractmethod
    def run(self, task: TaskMessage) -> Iterator[Message]:
        """Execute a task and yield progress/result messages.

        Args:
            task: The task message with instruction and context.

        Yields:
            ProgressMessage for status updates, ResultMessage for final output.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"
