"""FileMemoryMessageService 测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_sdk._agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
    serialize_agent_messages,
)
from agent_sdk._agent.message.history_message_loader import _transcript_path
from agent_sdk._agent.memory.file_memory_message_service import FileMemoryMessageService
from agent_sdk._agent.message.message_repair import _CANCELLED_CONTENT
from agent_sdk._storage.local_backend import FilesystemBackend


def make_user_msg(content: str) -> UserMessage:
    return UserMessage(content=content)


def make_assistant_msg(content: str) -> AssistantMessage:
    return AssistantMessage(content=content)


def make_meta_msg(content: str, is_compact_summary: bool = False) -> UserMessage:
    meta: dict = {"is_meta": True}
    if is_compact_summary:
        meta["is_compact_summary"] = True
    return UserMessage(content=content, metadata=meta)


@pytest.fixture
def backend(tmp_path: Path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


@pytest.fixture
def service(backend: FilesystemBackend) -> FileMemoryMessageService:
    return FileMemoryMessageService(backend)


class TestLoad:
    async def test_load_empty_session(self, service: FileMemoryMessageService) -> None:
        """空会话返回空列表"""
        result = await service.load("user1", "session1")
        assert result == []

    async def test_load_from_file_on_cache_miss(
        self, backend: FilesystemBackend, tmp_path: Path
    ) -> None:
        """缓存 miss 时从文件加载"""
        svc1 = FileMemoryMessageService(backend)
        msg = make_user_msg("hello")
        await svc1.insert_batch("u", "s", [msg])

        # 新实例（无缓存）
        svc2 = FileMemoryMessageService(backend)
        result = await svc2.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "hello"

    async def test_load_uses_cache_on_second_call(self, service: FileMemoryMessageService) -> None:
        """第二次 load 使用缓存"""
        msg = make_user_msg("first")
        await service.insert_batch("u", "s", [msg])

        result1 = await service.load("u", "s")
        result2 = await service.load("u", "s")
        assert len(result1) == len(result2)

    async def test_load_returns_copy_not_cache_reference(self, service: FileMemoryMessageService) -> None:
        """load 返回缓存的副本，外部修改不影响缓存"""
        await service.insert_batch("u", "s", [make_user_msg("msg")])
        result = await service.load("u", "s")
        result.append(make_user_msg("extra"))

        result2 = await service.load("u", "s")
        assert len(result2) == 1  # 缓存未被污染


class TestInsertBatch:
    async def test_insert_batch_appends_messages(self, service: FileMemoryMessageService) -> None:
        """insert_batch 追加消息"""
        await service.insert_batch("u", "s", [make_user_msg("msg1")])
        await service.insert_batch("u", "s", [make_assistant_msg("reply1")])

        result = await service.load("u", "s")
        assert len(result) == 2

    async def test_insert_batch_filters_is_meta(self, service: FileMemoryMessageService) -> None:
        """is_meta=True 的消息不被持久化（除非 is_compact_summary）"""
        meta_msg = make_meta_msg("context injection")
        real_msg = make_user_msg("real")
        await service.insert_batch("u", "s", [meta_msg, real_msg])

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "real"

    async def test_insert_batch_keeps_compact_summary(self, service: FileMemoryMessageService) -> None:
        """is_compact_summary=True 的消息需要持久化"""
        summary = make_meta_msg("对话摘要", is_compact_summary=True)
        await service.insert_batch("u", "s", [summary])

        result = await service.load("u", "s")
        assert len(result) == 1

    async def test_insert_batch_all_meta_no_write(self, service: FileMemoryMessageService) -> None:
        """全是 is_meta 消息时不写文件"""
        meta_msg = make_meta_msg("context")
        await service.insert_batch("u", "s", [meta_msg])

        # load 返回空（meta 被过滤，未写入文件）
        svc2 = FileMemoryMessageService(service._backend)
        result = await svc2.load("u", "s")
        assert result == []

    async def test_insert_batch_updates_cache(self, service: FileMemoryMessageService) -> None:
        """insert_batch 后缓存同步更新"""
        await service.load("u", "s")  # 初始化缓存

        msg = make_user_msg("new")
        await service.insert_batch("u", "s", [msg])

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "new"


class TestUpdate:
    async def test_update_replaces_working_set(self, service: FileMemoryMessageService) -> None:
        """update 全量替换消息（compact 后调用）"""
        await service.insert_batch("u", "s", [make_user_msg("old1"), make_user_msg("old2")])

        new_msgs: list[AgentMessage] = [make_user_msg("summary")]
        await service.update("u", "s", new_msgs)

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "summary"

    async def test_update_filters_is_meta(self, service: FileMemoryMessageService) -> None:
        """update 时也过滤 is_meta"""
        meta_msg = make_meta_msg("attachment")
        real_msg = make_user_msg("real")
        await service.update("u", "s", [meta_msg, real_msg])

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "real"

    async def test_update_persists_to_file(
        self, service: FileMemoryMessageService, backend: FilesystemBackend
    ) -> None:
        """update 写入文件，新实例可以读到"""
        await service.update("u", "s", [make_user_msg("compacted")])

        svc2 = FileMemoryMessageService(backend)
        result = await svc2.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "compacted"


class TestSessionIsolation:
    async def test_different_sessions_isolated(self, service: FileMemoryMessageService) -> None:
        """不同 session 的消息互不干扰"""
        await service.insert_batch("u", "s1", [make_user_msg("session1")])
        await service.insert_batch("u", "s2", [make_user_msg("session2")])

        r1 = await service.load("u", "s1")
        r2 = await service.load("u", "s2")

        assert len(r1) == 1
        assert r1[0].content == "session1"
        assert len(r2) == 1
        assert r2[0].content == "session2"


class TestLoadTimeRepair:
    """加载时自动修复 tool_call/tool_result 配对问题。"""

    async def test_load_repairs_missing_tool_result_from_transcript(
        self, backend: FilesystemBackend,
    ) -> None:
        """messages 缺少 tool_result，从 transcript 找回并修复。"""
        # messages.jsonl：有 tool_call 但没有 tool_result
        broken_msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        msgs_content = serialize_agent_messages(broken_msgs)
        await backend.awrite("/u/sessions/s/messages.jsonl", msgs_content)

        # transcript.jsonl：包含完整的 tool_result
        transcript_msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
            AssistantMessage(content="今天是晴天"),
        ]
        transcript_content = serialize_agent_messages(transcript_msgs)
        await backend.awrite(_transcript_path("u", "s"), transcript_content)

        svc = FileMemoryMessageService(backend)
        result = await svc.load("u", "s")

        # 修复后应有 3 条消息（原 2 + 补齐 1）
        assert len(result) == 3
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert repair_msg.tool_results[0].tool_call_id == "c1"
        assert repair_msg.tool_results[0].content == "晴天"
        assert repair_msg.metadata.get("is_repair") is True

    async def test_load_repairs_with_virtual_when_transcript_missing(
        self, backend: FilesystemBackend,
    ) -> None:
        """transcript 不存在时，补虚拟 tool_result。"""
        broken_msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        msgs_content = serialize_agent_messages(broken_msgs)
        await backend.awrite("/u/sessions/s/messages.jsonl", msgs_content)

        svc = FileMemoryMessageService(backend)
        result = await svc.load("u", "s")

        assert len(result) == 3
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert repair_msg.tool_results[0].content == _CANCELLED_CONTENT

    async def test_load_no_repair_when_paired(
        self, backend: FilesystemBackend,
    ) -> None:
        """配对完整时不触发修复。"""
        good_msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
            UserMessage(
                content="",
                tool_results=[ToolResult(tool_name="weather", tool_call_id="c1", content="晴天")],
            ),
            AssistantMessage(content="今天是晴天"),
        ]
        msgs_content = serialize_agent_messages(good_msgs)
        await backend.awrite("/u/sessions/s/messages.jsonl", msgs_content)

        svc = FileMemoryMessageService(backend)
        result = await svc.load("u", "s")

        assert len(result) == 4  # 无修复

    async def test_load_repair_persisted_to_file(
        self, backend: FilesystemBackend,
    ) -> None:
        """修复后的 messages.jsonl 被覆写，第二次加载不需要再修复。"""
        broken_msgs: list[AgentMessage] = [
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="t1", tool_call_id="c1", args="{}")],
            ),
        ]
        await backend.awrite("/u/sessions/s/messages.jsonl", serialize_agent_messages(broken_msgs))

        svc = FileMemoryMessageService(backend)
        result1 = await svc.load("u", "s")
        assert len(result1) == 2  # repaired

        # 新实例，从文件加载（不经过缓存）
        svc2 = FileMemoryMessageService(backend)
        result2 = await svc2.load("u", "s")
        assert len(result2) == 2  # 文件已修复，直接加载

    async def test_load_repairs_multiple_tool_calls(
        self, backend: FilesystemBackend,
    ) -> None:
        """一条 assistant 有多个 tool_calls 全部缺失，全部补齐。"""
        broken_msgs: list[AgentMessage] = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCall(tool_name="t1", tool_call_id="c1", args="{}"),
                    ToolCall(tool_name="t2", tool_call_id="c2", args="{}"),
                ],
            ),
        ]
        await backend.awrite("/u/sessions/s/messages.jsonl", serialize_agent_messages(broken_msgs))

        svc = FileMemoryMessageService(backend)
        result = await svc.load("u", "s")

        assert len(result) == 2
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert len(repair_msg.tool_results) == 2
        ids = {tr.tool_call_id for tr in repair_msg.tool_results}
        assert ids == {"c1", "c2"}


class TestErrorPaths:
    """错误路径测试"""

    async def test_load_empty_file_returns_empty(self, service: FileMemoryMessageService, backend: FilesystemBackend) -> None:
        """文件存在但内容为空时返回空列表"""
        # 写一个空文件
        path = "/u/sessions/s/messages.jsonl"
        result_write = await backend.awrite(path, "")
        assert result_write.error is None

        svc2 = FileMemoryMessageService(backend)
        result = await svc2.load("u", "s")
        assert result == []

    async def test_overwrite_delete_fails_raises_os_error(
        self, backend: FilesystemBackend
    ) -> None:
        """覆写时 adelete 失败抛 OSError"""
        from unittest.mock import AsyncMock, patch

        svc = FileMemoryMessageService(backend)
        # 先写一个文件
        await svc.insert_batch("u", "s", [make_user_msg("existing")])

        with patch.object(backend, "adelete", new=AsyncMock(return_value=False)):
            with pytest.raises(OSError, match="无法删除旧文件"):
                await svc.update("u", "s", [make_user_msg("new")])

    async def test_overwrite_write_fails_raises_os_error(
        self, backend: FilesystemBackend
    ) -> None:
        """覆写时 awrite 失败抛 OSError"""
        from unittest.mock import AsyncMock, patch
        from agent_sdk._common.filesystem_backend import WriteResult

        svc = FileMemoryMessageService(backend)

        with patch.object(
            backend, "awrite",
            new=AsyncMock(return_value=WriteResult(error="disk full"))
        ):
            with pytest.raises(OSError, match="写入失败"):
                await svc.update("u", "s", [make_user_msg("new")])

    async def test_append_write_fails_raises_os_error(
        self, backend: FilesystemBackend
    ) -> None:
        """追加时写入失败抛 OSError"""
        from unittest.mock import AsyncMock, patch
        from agent_sdk._common.filesystem_backend import WriteResult

        svc = FileMemoryMessageService(backend)

        with patch.object(
            backend, "aappend",
            new=AsyncMock(return_value=WriteResult(error="disk full"))
        ):
            with pytest.raises(OSError, match="写入失败"):
                await svc.insert_batch("u", "s", [make_user_msg("new")])
