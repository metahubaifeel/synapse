"""JSON Lines protocol for agent communication over stdin/stdout.

Message types:
- task:     Dispatch a task to an agent
- progress: Agent reports progress (tool call, step, etc.)
- result:   Agent reports final result of a task
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(str, Enum):
    TASK = "task"
    PROGRESS = "progress"
    RESULT = "result"


class TaskStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class ProgressStatus(str, Enum):
    STARTED = "started"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Message:
    """Base message with common fields."""
    type: MessageType
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_json(self) -> str:
        """Serialize to a single JSON line."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization. Override in subclasses."""
        return {"type": self.type.value, "id": self.id}


@dataclass
class TaskMessage(Message):
    """Dispatch a task to an agent."""
    instruction: str = ""
    context: str = ""
    agent_id: str = ""

    def __init__(
        self,
        instruction: str,
        context: str = "",
        agent_id: str = "",
        id: Optional[str] = None,
    ):
        super().__init__(type=MessageType.TASK, id=id or uuid.uuid4().hex[:8])
        self.instruction = instruction
        self.context = context
        self.agent_id = agent_id

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "instruction": self.instruction,
            "context": self.context,
            "agent_id": self.agent_id,
        })
        return d


@dataclass
class ProgressMessage(Message):
    """Agent reports progress (tool call, step, etc.)."""
    task_id: str = ""
    tool: str = ""
    status: ProgressStatus = ProgressStatus.RUNNING
    detail: str = ""

    def __init__(
        self,
        task_id: str,
        tool: str = "",
        status: ProgressStatus = ProgressStatus.RUNNING,
        detail: str = "",
        id: Optional[str] = None,
    ):
        super().__init__(type=MessageType.PROGRESS, id=id or uuid.uuid4().hex[:8])
        self.task_id = task_id
        self.tool = tool
        self.status = status
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "task_id": self.task_id,
            "tool": self.tool,
            "status": self.status.value,
            "detail": self.detail,
        })
        return d


@dataclass
class ResultMessage(Message):
    """Agent reports final result of a task."""
    task_id: str = ""
    status: TaskStatus = TaskStatus.OK
    output: str = ""
    error: str = ""

    def __init__(
        self,
        task_id: str,
        status: TaskStatus = TaskStatus.OK,
        output: str = "",
        error: str = "",
        id: Optional[str] = None,
    ):
        super().__init__(type=MessageType.RESULT, id=id or uuid.uuid4().hex[:8])
        self.task_id = task_id
        self.status = status
        self.output = output
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
        })
        return d


def encode(msg: Message) -> str:
    """Encode a message to a JSON line string."""
    return msg.to_json() + "\n"


def decode(line: str) -> Message:
    """Decode a JSON line string into a Message object.

    Raises ValueError if the message type is unknown or the line is malformed.
    """
    data = json.loads(line.strip())
    msg_type = data.get("type", "")
    msg_id = data.get("id", uuid.uuid4().hex[:8])

    if msg_type == MessageType.TASK.value:
        return TaskMessage(
            instruction=data.get("instruction", ""),
            context=data.get("context", ""),
            agent_id=data.get("agent_id", ""),
            id=msg_id,
        )
    elif msg_type == MessageType.PROGRESS.value:
        status = ProgressStatus(data.get("status", "running"))
        return ProgressMessage(
            task_id=data.get("task_id", ""),
            tool=data.get("tool", ""),
            status=status,
            detail=data.get("detail", ""),
            id=msg_id,
        )
    elif msg_type == MessageType.RESULT.value:
        status = TaskStatus(data.get("status", "ok"))
        return ResultMessage(
            task_id=data.get("task_id", ""),
            status=status,
            output=data.get("output", ""),
            error=data.get("error", ""),
            id=msg_id,
        )
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
