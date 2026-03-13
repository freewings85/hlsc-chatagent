"""统一事件模型"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from agent_sdk._event.event_type import EventType


@dataclass
class EventModel:
    """Agent 输出的统一事件结构。"""

    session_id: str
    request_id: str
    type: EventType
    data: dict[str, Any]
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    finish_reason: str | None = None
    agent_name: str = "main"
    agent_path: str = "main"
    parent_tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的 dict。"""
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "finish_reason": self.finish_reason,
            "agent_name": self.agent_name,
            "agent_path": self.agent_path,
            "parent_tool_call_id": self.parent_tool_call_id,
        }

    def to_json(self) -> str:
        """转为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
