"""事件发射器：生产者往 queue 中放事件，消费者从 queue 取"""

from __future__ import annotations

import asyncio

from src.sdk._event.event_model import EventModel


class EventEmitter:
    """事件发射器。loop 内任意深度的函数都可以通过它发出事件。

    使用 asyncio.Lock 序列化 emit/close，保证 sentinel 永远最后入队。
    """

    def __init__(self, queue: asyncio.Queue[EventModel | None]) -> None:
        self._queue: asyncio.Queue[EventModel | None] = queue
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def emit(self, event: EventModel) -> None:
        """发出一个事件。close() 后静默丢弃。"""
        async with self._lock:
            if self._closed:
                return
            await self._queue.put(event)

    async def close(self) -> None:
        """放入 None 哨兵，通知消费者结束。"""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            await self._queue.put(None)
