"""FileMemoryMessageService：文件持久化实现。

进程内字典缓存 + 文件持久化（messages.jsonl）。

路径约定（与 HistoryMessageLoader 一致）：
  /{user_id}/sessions/{session_id}/messages.jsonl
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from src.sdk._agent.agent_message import (
    AgentMessage,
    deserialize_agent_messages,
    serialize_agent_messages,
    should_persist,
)
from src.sdk._agent.message.history_message_loader import _messages_path
from src.sdk._agent.message.message_repair import (
    find_missing_tool_call_ids,
    load_transcript,
    repair_messages,
)
from src.sdk._agent.memory.memory_message_service import MemoryMessageService

if TYPE_CHECKING:
    from src.sdk._common.filesystem_backend import BackendProtocol


class FileMemoryMessageService(MemoryMessageService):
    """会话消息工作集（进程内字典缓存 + 文件持久化）。

    职责：
    - load()         — 从缓存或文件加载工作集
    - update()       — compact 后全量替换（覆写文件 + 更新缓存）
    - insert_batch() — 追加新消息（只写 messages.jsonl，不写 transcript）
    """

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend = backend
        self._cache: dict[str, list[AgentMessage]] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _cache_key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    async def load(self, user_id: str, session_id: str) -> list[AgentMessage]:
        """加载消息工作集，优先从缓存读取。

        首次从文件加载时自动检测 tool_call/tool_result 配对问题：
        - 先从 transcript.jsonl 查找缺失的 tool_result
        - 找不到则补虚拟 tool_result（标记 is_repair）
        - 修复后覆写 messages.jsonl
        """
        key = self._cache_key(user_id, session_id)
        if key in self._cache:
            return list(self._cache[key])

        messages = await self._load_from_file(user_id, session_id)

        # 加载时修复：检测 tool_call/tool_result 配对问题
        if messages and find_missing_tool_call_ids(messages):
            transcript = await load_transcript(self._backend, user_id, session_id)
            repaired = repair_messages(messages, transcript)
            if repaired is not messages:
                messages = repaired
                await self._overwrite_file(user_id, session_id, messages)

        self._cache[key] = messages
        return list(messages)

    async def update(
        self,
        user_id: str,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        """全量替换工作集（compact 后调用）。过滤不应持久化的消息。"""
        persist = [m for m in messages if should_persist(m)]
        key = self._cache_key(user_id, session_id)
        self._cache[key] = list(persist)
        await self._overwrite_file(user_id, session_id, persist)

    async def insert_batch(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[AgentMessage],
    ) -> None:
        """追加新消息到工作集（只写 messages.jsonl，不写 transcript.jsonl）。"""
        persist = [m for m in new_messages if should_persist(m)]
        if not persist:
            return

        key = self._cache_key(user_id, session_id)
        async with self._locks[key]:
            # 更新缓存
            if key in self._cache:
                self._cache[key].extend(persist)

            # 追加到文件
            await self._append_to_file(user_id, session_id, persist)

    # ──────────────────────── 文件操作 ────────────────────────

    async def _load_from_file(self, user_id: str, session_id: str) -> list[AgentMessage]:
        path = _messages_path(user_id, session_id)
        if not await self._backend.aexists(path):
            return []
        responses = await self._backend.adownload_files([path])
        resp = responses[0]
        if resp.error is not None or resp.content is None:  # pragma: no cover
            return []
        raw = resp.content.decode("utf-8").strip()
        if not raw:
            return []
        return deserialize_agent_messages(raw)

    async def _overwrite_file(
        self,
        user_id: str,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        content = serialize_agent_messages(messages)
        path = _messages_path(user_id, session_id)
        if await self._backend.aexists(path):
            deleted = await self._backend.adelete(path)
            if not deleted:
                raise OSError(f"无法删除旧文件: {path}")
        if content:
            result = await self._backend.awrite(path, content)
            if result.error is not None:
                raise OSError(f"写入失败: {path}: {result.error}")

    async def _append_to_file(
        self,
        user_id: str,
        session_id: str,
        messages: list[AgentMessage],
    ) -> None:
        append_content = serialize_agent_messages(messages)
        path = _messages_path(user_id, session_id)
        result = await self._backend.aappend(path, append_content)
        if result.error is not None:
            raise OSError(f"写入失败: {path}: {result.error}")
