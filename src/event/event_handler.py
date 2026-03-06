"""事件处理中枢：接收原始事件，转换为 EventModel，派发到 Sinker"""

from __future__ import annotations

from src.common.event_sinker import EventSinker
from src.event.event_model import EventModel


class EventHandler:
    """接收 Agent 原始事件，转换后派发到 sinker。"""

    def __init__(self, sinker: EventSinker) -> None:
        self._sinker: EventSinker = sinker

    async def handle(self, event: EventModel) -> None:
        """接收一个事件，派发到 sinker。"""
        await self._sinker.send(event)

    async def close(self) -> None:
        """通知 sinker 关闭。"""
        await self._sinker.close()
