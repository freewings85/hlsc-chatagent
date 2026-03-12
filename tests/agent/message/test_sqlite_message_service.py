"""SqliteMemoryMessageService 测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.agent_message import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResult,
    UserMessage,
)
from src.agent.memory.sqlite_memory_message_service import SqliteMemoryMessageService


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
async def service(tmp_path: Path) -> SqliteMemoryMessageService:
    svc = SqliteMemoryMessageService(base_dir=str(tmp_path))
    yield svc
    await svc.close()


class TestLoad:
    async def test_load_empty_session(self, service: SqliteMemoryMessageService) -> None:
        """空会话返回空列表"""
        result = await service.load("user1", "session1")
        assert result == []

    async def test_load_returns_inserted_messages(self, service: SqliteMemoryMessageService) -> None:
        """insert 后 load 能读到"""
        msg = make_user_msg("hello")
        await service.insert_batch("u", "s", [msg])
        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "hello"

    async def test_load_from_new_instance(self, tmp_path: Path) -> None:
        """新实例能从 db 文件读到之前写入的数据"""
        svc1 = SqliteMemoryMessageService(base_dir=str(tmp_path))
        await svc1.insert_batch("u", "s", [make_user_msg("persisted")])
        await svc1.close()

        svc2 = SqliteMemoryMessageService(base_dir=str(tmp_path))
        result = await svc2.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "persisted"
        await svc2.close()


class TestInsertBatch:
    async def test_insert_batch_appends_messages(self, service: SqliteMemoryMessageService) -> None:
        """多次 insert_batch 追加消息"""
        await service.insert_batch("u", "s", [make_user_msg("msg1")])
        await service.insert_batch("u", "s", [make_assistant_msg("reply1")])

        result = await service.load("u", "s")
        assert len(result) == 2

    async def test_insert_batch_filters_is_meta(self, service: SqliteMemoryMessageService) -> None:
        """is_meta=True 的消息不被持久化"""
        meta_msg = make_meta_msg("context injection")
        real_msg = make_user_msg("real")
        await service.insert_batch("u", "s", [meta_msg, real_msg])

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "real"

    async def test_insert_batch_keeps_compact_summary(self, service: SqliteMemoryMessageService) -> None:
        """is_compact_summary=True 的消息需要持久化"""
        summary = make_meta_msg("对话摘要", is_compact_summary=True)
        await service.insert_batch("u", "s", [summary])

        result = await service.load("u", "s")
        assert len(result) == 1

    async def test_insert_batch_all_meta_no_write(self, service: SqliteMemoryMessageService) -> None:
        """全是 is_meta 消息时不写入"""
        meta_msg = make_meta_msg("context")
        await service.insert_batch("u", "s", [meta_msg])

        result = await service.load("u", "s")
        assert result == []


class TestUpdate:
    async def test_update_replaces_working_set(self, service: SqliteMemoryMessageService) -> None:
        """update 全量替换消息"""
        await service.insert_batch("u", "s", [make_user_msg("old1"), make_user_msg("old2")])

        new_msgs: list[AgentMessage] = [make_user_msg("summary")]
        await service.update("u", "s", new_msgs)

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "summary"

    async def test_update_filters_is_meta(self, service: SqliteMemoryMessageService) -> None:
        """update 时也过滤 is_meta"""
        meta_msg = make_meta_msg("attachment")
        real_msg = make_user_msg("real")
        await service.update("u", "s", [meta_msg, real_msg])

        result = await service.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "real"

    async def test_update_persists(self, tmp_path: Path) -> None:
        """update 写入 db，新实例可以读到"""
        svc1 = SqliteMemoryMessageService(base_dir=str(tmp_path))
        await svc1.update("u", "s", [make_user_msg("compacted")])
        await svc1.close()

        svc2 = SqliteMemoryMessageService(base_dir=str(tmp_path))
        result = await svc2.load("u", "s")
        assert len(result) == 1
        assert result[0].content == "compacted"
        await svc2.close()


class TestSessionIsolation:
    async def test_different_sessions_isolated(self, service: SqliteMemoryMessageService) -> None:
        """不同 session 的消息互不干扰"""
        await service.insert_batch("u", "s1", [make_user_msg("session1")])
        await service.insert_batch("u", "s2", [make_user_msg("session2")])

        r1 = await service.load("u", "s1")
        r2 = await service.load("u", "s2")

        assert len(r1) == 1
        assert r1[0].content == "session1"
        assert len(r2) == 1
        assert r2[0].content == "session2"

    async def test_different_users_isolated(self, service: SqliteMemoryMessageService) -> None:
        """不同用户使用不同 db 文件"""
        await service.insert_batch("u1", "s", [make_user_msg("user1")])
        await service.insert_batch("u2", "s", [make_user_msg("user2")])

        r1 = await service.load("u1", "s")
        r2 = await service.load("u2", "s")

        assert len(r1) == 1
        assert r1[0].content == "user1"
        assert len(r2) == 1
        assert r2[0].content == "user2"


class TestLoadTimeRepair:
    """加载时自动修复 tool_call/tool_result 配对问题。"""

    async def test_load_repairs_missing_tool_result(self, service: SqliteMemoryMessageService) -> None:
        """缺少 tool_result 时补虚拟 result。"""
        from src.agent.message.message_repair import _CANCELLED_CONTENT

        broken_msgs: list[AgentMessage] = [
            UserMessage(content="查天气"),
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(tool_name="weather", tool_call_id="c1", args="{}")],
            ),
        ]
        for msg in broken_msgs:
            await service.insert_batch("u", "s", [msg])

        result = await service.load("u", "s")

        assert len(result) == 3
        repair_msg = result[-1]
        assert isinstance(repair_msg, UserMessage)
        assert repair_msg.tool_results[0].content == _CANCELLED_CONTENT
        assert repair_msg.metadata.get("is_repair") is True

    async def test_load_no_repair_when_paired(self, service: SqliteMemoryMessageService) -> None:
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
        for msg in good_msgs:
            await service.insert_batch("u", "s", [msg])

        result = await service.load("u", "s")
        assert len(result) == 4
