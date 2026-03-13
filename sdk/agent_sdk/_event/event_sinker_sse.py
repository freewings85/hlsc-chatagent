"""SSE Sinker 实现：将事件写入 asyncio.Queue 供 StreamingResponse 消费"""

from __future__ import annotations

import asyncio

from agent_sdk._event.event_model import EventModel


class SseSinker:
    """将事件写入 asyncio.Queue，由 SSE generator 读取。"""

    def __init__(self, queue: asyncio.Queue[EventModel | None]) -> None:
        self._queue: asyncio.Queue[EventModel | None] = queue

    async def send(self, event: EventModel) -> None:
        """将事件放入队列。"""
        await self._queue.put(event)

    async def close(self) -> None:
        """放入 None 哨兵，通知 SSE generator 结束。"""
        await self._queue.put(None)
