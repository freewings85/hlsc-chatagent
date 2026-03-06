"""HistoryMessageLoader：历史消息的加载和持久化。

职责：
- 按 (user_id, session_id) 从 messages.jsonl 加载历史消息（工作副本）
- save() 整体覆写 messages.jsonl（compact 后调用）
- append() 追加新消息到 messages.jsonl + transcript.jsonl
- 过滤 is_meta 消息（merged_context 等临时注入不持久化）

路径约定：
  /{user_id}/sessions/{session_id}/messages.jsonl    ← 工作副本，compact 后整体覆写
  /{user_id}/sessions/{session_id}/transcript.jsonl  ← 审计日志，append-only

每行一个 ModelMessage，使用 ModelMessagesTypeAdapter 序列化。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
)

if TYPE_CHECKING:
    from src.common.filesystem_backend import BackendProtocol


def _is_meta(msg: ModelMessage) -> bool:
    """判断消息是否为临时注入的 is_meta 消息。"""
    return (
        isinstance(msg, ModelRequest)
        and isinstance(msg.metadata, dict)
        and msg.metadata.get("is_meta") is True
    )


def _messages_path(user_id: str, session_id: str) -> str:
    return f"/{user_id}/sessions/{session_id}/messages.jsonl"


def _transcript_path(user_id: str, session_id: str) -> str:
    return f"/{user_id}/sessions/{session_id}/transcript.jsonl"


def _serialize_messages(messages: list[ModelMessage]) -> str:
    """将消息列表序列化为 JSONL 字符串。"""
    lines: list[str] = []
    for msg in messages:
        json_bytes = ModelMessagesTypeAdapter.dump_json([msg])
        json_str = json_bytes.decode("utf-8")
        # 去掉外层 [] 得到单条 JSON
        inner = json_str[1:-1].strip()
        lines.append(inner)
    return "\n".join(lines) + "\n" if lines else ""


def _deserialize_messages(raw: str) -> list[ModelMessage]:
    """从 JSONL 字符串解析消息列表。

    损坏的行（非法 JSON）会被跳过并记录日志，不会导致整个文件失败。
    """
    messages: list[ModelMessage] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = ModelMessagesTypeAdapter.validate_json(f"[{line}]")
            messages.extend(parsed)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("跳过损坏的 JSONL 行: %s", line[:100])
    return messages


class HistoryMessageLoader:
    """历史消息加载器。

    messages.jsonl 是工作副本，compact 后可整体覆写。
    transcript.jsonl 是审计日志，append-only。
    """

    # TODO: 内存缓存 — 按 (user_id, session_id) 缓存，避免每次都读文件

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend = backend
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def load(self, user_id: str, session_id: str) -> list[ModelMessage]:
        """从 messages.jsonl 加载历史消息。"""
        path = _messages_path(user_id, session_id)
        if not await self._backend.aexists(path):
            return []

        responses = await self._backend.adownload_files([path])
        resp = responses[0]
        if resp.error is not None or resp.content is None:  # pragma: no cover — backend 错误防御
            return []

        raw = resp.content.decode("utf-8").strip()
        if not raw:
            return []

        return _deserialize_messages(raw)

    async def save(
        self,
        user_id: str,
        session_id: str,
        messages: list[ModelMessage],
    ) -> None:
        """整体覆写 messages.jsonl（compact 后调用）。

        过滤 is_meta 消息。写入失败时抛出异常，不静默丢数据。
        """
        persist = [m for m in messages if not _is_meta(m)]
        content = _serialize_messages(persist)

        path = _messages_path(user_id, session_id)
        if await self._backend.aexists(path):
            deleted = await self._backend.adelete(path)
            if not deleted:
                raise OSError(f"无法删除旧文件: {path}")
        if content:
            result = await self._backend.awrite(path, content)
            if result.error is not None:
                raise OSError(f"写入失败: {path}: {result.error}")

    async def append(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[ModelMessage],
    ) -> None:
        """追加新消息到 messages.jsonl 和 transcript.jsonl。

        过滤 is_meta 消息。
        messages.jsonl: 工作副本，追加新消息。
        transcript.jsonl: 审计日志，append-only。
        """
        persist = [m for m in new_messages if not _is_meta(m)]
        if not persist:
            return

        append_content = _serialize_messages(persist)

        lock_key = f"{user_id}:{session_id}"
        async with self._locks[lock_key]:
            # 两个文件都追加
            for path_fn in (_messages_path, _transcript_path):
                path = path_fn(user_id, session_id)
                existing = ""
                if await self._backend.aexists(path):
                    responses = await self._backend.adownload_files([path])
                    resp = responses[0]
                    if resp.error is not None or resp.content is None:
                        raise OSError(f"读取失败，中止追加以防数据丢失: {path}")
                    existing = resp.content.decode("utf-8")
                    await self._backend.adelete(path)
                result = await self._backend.awrite(path, existing + append_content)
                if result.error is not None:
                    raise OSError(f"写入失败: {path}: {result.error}")
