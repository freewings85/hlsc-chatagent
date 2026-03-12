"""InMemoryContextService：进程内存实现。

使用 dict 缓存，按 (user_id, session_id) 隔离。
进程重启后丢失，首次请求会重新注入一次完整 context。
"""

from __future__ import annotations

from src.sdk._agent.memory.memory_context_service import ContextFormatter, MemoryContextService
from src.sdk._common.request_context import RequestContext


class InMemoryContextService(MemoryContextService):
    """进程内存实现的上下文工作集。"""

    def __init__(self, formatter: ContextFormatter | None = None) -> None:
        super().__init__(formatter=formatter)
        self._store: dict[str, RequestContext] = {}

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    async def get(self, user_id: str, session_id: str) -> RequestContext | None:
        ctx = self._store.get(self._key(user_id, session_id))
        return ctx.model_copy() if ctx else None

    async def set(
        self,
        user_id: str,
        session_id: str,
        context: RequestContext,
    ) -> None:
        self._store[self._key(user_id, session_id)] = context.model_copy()
