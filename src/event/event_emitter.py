"""事件发射器：生产者往 queue 中放事件，消费者从 queue 取"""

from __future__ import annotations

import asyncio

from src.event.event_model import EventModel


class EventEmitter:
    """事件发射器。loop 内任意深度的函数都可以通过它发出事件。"""

    def __init__(self, queue: asyncio.Queue[EventModel | None]) -> None:
        self._queue: asyncio.Queue[EventModel | None] = queue

    async def emit(self, event: EventModel) -> None:
        """发出一个事件。"""
        await self._queue.put(event)

    async def close(self) -> None:
        """放入 None 哨兵，通知消费者结束。"""
        await self._queue.put(None)
