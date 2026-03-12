"""事件输出协议（纯接口）"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.sdk._event.event_model import EventModel


class EventSinker(Protocol):
    """事件输出目标的协议定义。"""

    async def send(self, event: EventModel) -> None:
        """发送一个事件。"""
        ...

    async def close(self) -> None:
        """关闭输出，释放资源。"""
        ...
