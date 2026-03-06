"""统一事件模型"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.event.event_type import EventType


@dataclass
class EventModel:
    """Agent 输出的统一事件结构。"""

    conversation_id: str
    request_id: str
    type: EventType
    data: dict[str, Any]
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    finish_reason: str | None = None
    agent_name: str = "main"

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的 dict。"""
        return {
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "finish_reason": self.finish_reason,
            "agent_name": self.agent_name,
        }

    def to_json(self) -> str:
        """转为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
