"""事件发射器：生产者往 queue 中放事件，消费者从 queue 取"""

from __future__ import annotations

import asyncio

from agent_sdk._event.event_model import EventModel


class EventEmitter:
    """事件发射器。loop 内任意深度的函数都可以通过它发出事件。

    使用 asyncio.Lock 序列化 emit/close，保证 sentinel 永远最后入队。

    suppress_output：设为 True 后所有事件静默丢弃。
    用于 workflow 跃迁场景——agent 调 update_workflow_state 触发 step 推进后，
    该轮 agent 的文字输出不应到达用户，由 workflow 再调一次 agent 输出最终结果。
    """

    def __init__(self, queue: asyncio.Queue[EventModel | None]) -> None:
        self._queue: asyncio.Queue[EventModel | None] = queue
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self.suppress_output: bool = False

    async def emit(self, event: EventModel) -> None:
        """发出一个事件。suppress_output=True 或 close() 后静默丢弃。"""
        async with self._lock:
            if self._closed or self.suppress_output:
                return
            await self._queue.put(event)

    async def close(self) -> None:
        """放入 None 哨兵，通知消费者结束。"""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            await self._queue.put(None)
