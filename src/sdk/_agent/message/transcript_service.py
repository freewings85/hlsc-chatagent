"""TranscriptService：append-only 审计日志（transcript.jsonl）。

只写 transcript.jsonl，不写 messages.jsonl（由 MemoryMessageService 负责）。

过滤规则：
- AssistantMessage 永远写入
- 非 is_meta 的 UserMessage（含 compact_boundary）永远写入
- is_meta=True 的消息：只写 is_compact_summary=True 的摘要

路径约定：/{user_id}/sessions/{session_id}/transcript.jsonl
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from src.sdk._agent.agent_message import (
    AgentMessage,
    serialize_agent_messages,
    should_persist,
)
from src.sdk._agent.message.history_message_loader import _transcript_path

if TYPE_CHECKING:
    from src.sdk._common.filesystem_backend import BackendProtocol


class TranscriptService:
    """append-only 审计日志。

    职责：本轮对话结束后，将新消息追加到 transcript.jsonl。
    永远只追加，从不删除（对应 Claude Code `Gb = appendFileSync` 设计）。
    """

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend = backend
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def append(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[AgentMessage],
    ) -> None:
        """追加新消息到 transcript.jsonl。

        过滤规则：should_persist（保留 compact_summary，排除其他 is_meta）。
        """
        persist = [m for m in new_messages if should_persist(m)]
        if not persist:
            return

        append_content = serialize_agent_messages(persist)
        path = _transcript_path(user_id, session_id)
        lock_key = f"{user_id}:{session_id}"

        async with self._locks[lock_key]:
            result = await self._backend.aappend(path, append_content)
            if result.error is not None:
                raise OSError(f"写入失败: {path}: {result.error}")
