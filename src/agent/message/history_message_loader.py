"""HistoryMessageLoader：历史消息的加载和持久化。

职责：
- 按 (user_id, session_id) 从 messages.jsonl 加载历史消息（工作副本）
- save() 整体覆写 messages.jsonl（compact 后调用）
- append() 追加新消息到 messages.jsonl + transcript.jsonl
- 过滤 is_meta 消息（merged_context 等临时注入不持久化）

路径约定：
  /{user_id}/sessions/{session_id}/messages.jsonl    ← 工作副本，compact 后整体覆写
  /{user_id}/sessions/{session_id}/transcript.jsonl  ← 审计日志，append-only

每行一个 AgentMessage，使用 AgentMessage 序列化（向后兼容旧 ModelMessage 格式）。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
)

from src.agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    UserMessage,
    deserialize_agent_messages,
    from_model_messages,
    serialize_agent_messages,
    should_persist,
)

if TYPE_CHECKING:
    from src.common.filesystem_backend import BackendProtocol


def _is_meta(msg: ModelMessage) -> bool:
    """判断 ModelMessage 是否为临时注入的 is_meta 消息。

    保留供服务层（context_injector 等）使用，它们仍操作 ModelMessage。
    """
    return (
        isinstance(msg, ModelRequest)
        and isinstance(msg.metadata, dict)
        and msg.metadata.get("is_meta") is True
    )


def _has_system_prompt(msg: ModelMessage) -> bool:
    """判断消息是否包含 SystemPromptPart（由 Pydantic AI 自动注入，不应持久化）。

    保留供服务层使用。
    """
    if not isinstance(msg, ModelRequest):
        return False
    return any(isinstance(p, SystemPromptPart) for p in msg.parts)


def _should_persist(msg: ModelMessage) -> bool:
    """判断 ModelMessage 是否需要写入持久化存储。

    保留供服务层使用（compact 等直接操作 ModelMessage 的模块）。
    AgentMessage 版本请用 agent_message.should_persist()。
    """
    if _has_system_prompt(msg):
        return False
    if not isinstance(msg, ModelRequest):
        return True
    meta = msg.metadata or {}
    if not meta.get("is_meta"):
        return True
    return bool(meta.get("is_compact_summary", False))


def _messages_path(user_id: str, session_id: str) -> str:
    return f"/{user_id}/sessions/{session_id}/messages.jsonl"


def _transcript_path(user_id: str, session_id: str) -> str:
    return f"/{user_id}/sessions/{session_id}/transcript.jsonl"


def _serialize_messages(messages: list[AgentMessage] | list[ModelMessage]) -> str:  # type: ignore[type-arg]
    """将消息列表序列化为 JSONL 字符串。

    接受 AgentMessage 或 ModelMessage（自动转换）。
    """
    if messages and not isinstance(messages[0], (UserMessage, AssistantMessage)):
        messages = from_model_messages(messages)  # type: ignore[arg-type]
    return serialize_agent_messages(messages)  # type: ignore[arg-type]


def _deserialize_messages(raw: str) -> list[AgentMessage]:
    """从 JSONL 字符串解析 AgentMessage 列表。

    自动兼容旧格式（ModelMessage JSON）和新格式（AgentMessage JSON）。
    委托给 agent_message.deserialize_agent_messages。
    """
    return deserialize_agent_messages(raw)


class HistoryMessageLoader:
    """历史消息加载器。

    messages.jsonl 是工作副本，compact 后可整体覆写。
    transcript.jsonl 是审计日志，append-only。
    """

    # TODO: 内存缓存 — 按 (user_id, session_id) 缓存，避免每次都读文件

    def __init__(self, backend: BackendProtocol) -> None:
        self._backend = backend
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def load(self, user_id: str, session_id: str) -> list[AgentMessage]:
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
        messages: list[AgentMessage] | list[ModelMessage],  # type: ignore[type-arg]
    ) -> None:
        """整体覆写 messages.jsonl（compact 后调用）。

        接受 AgentMessage 或 ModelMessage（自动转换后过滤和序列化）。
        过滤 is_meta 消息。写入失败时抛出异常，不静默丢数据。

        注意：当前 BackendProtocol.write() 不支持原子覆写（先删后写），
        写入失败时旧数据可能已被删除。生产环境需要后端支持 overwrite/rename。
        """
        # 自动转换 ModelMessage → AgentMessage
        agent_msgs: list[AgentMessage]
        if messages and not isinstance(messages[0], (UserMessage, AssistantMessage)):
            agent_msgs = from_model_messages(messages)  # type: ignore[arg-type]
        else:
            agent_msgs = messages  # type: ignore[assignment]
        persist = [m for m in agent_msgs if should_persist(m)]
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
        new_messages: list[AgentMessage] | list[ModelMessage],  # type: ignore[type-arg]
    ) -> None:
        """追加新消息到 messages.jsonl 和 transcript.jsonl。

        接受 AgentMessage 或 ModelMessage（自动转换后过滤和序列化）。
        """
        # 自动转换 ModelMessage → AgentMessage
        agent_msgs: list[AgentMessage]
        if new_messages and not isinstance(new_messages[0], (UserMessage, AssistantMessage)):
            agent_msgs = from_model_messages(new_messages)  # type: ignore[arg-type]
        else:
            agent_msgs = new_messages  # type: ignore[assignment]
        persist = [m for m in agent_msgs if should_persist(m)]
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
