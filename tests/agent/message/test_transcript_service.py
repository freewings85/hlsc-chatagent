"""TranscriptService 测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.agent_message import AssistantMessage, UserMessage
from src.agent.message.transcript_service import TranscriptService
from src.storage.local_backend import FilesystemBackend


def make_user_msg(content: str) -> UserMessage:
    return UserMessage(content=content)


def make_assistant_msg(content: str) -> AssistantMessage:
    return AssistantMessage(content=content)


def make_meta_msg(content: str, is_compact_summary: bool = False) -> UserMessage:
    meta: dict = {"is_meta": True}
    if is_compact_summary:
        meta["is_compact_summary"] = True
    return UserMessage(content=content, metadata=meta)


def make_boundary_msg() -> UserMessage:
    """compact_boundary 标记（is_meta=False，需要持久化）"""
    return UserMessage(
        content="[对话已压缩]",
        metadata={"is_compact_boundary": True},
    )


@pytest.fixture
def backend(tmp_path: Path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


@pytest.fixture
def service(backend: FilesystemBackend) -> TranscriptService:
    return TranscriptService(backend)


class TestAppend:
    async def test_append_creates_transcript(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """append 创建 transcript.jsonl"""
        await service.append("u", "s", [make_user_msg("hello")])

        path = "/u/sessions/s/transcript.jsonl"
        assert await backend.aexists(path)

    async def test_append_filters_is_meta(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """is_meta=True 的消息（context injection 等）不写入 transcript"""
        meta_msg = make_meta_msg("system context")
        real_msg = make_user_msg("real user message")

        await service.append("u", "s", [meta_msg, real_msg])

        path = "/u/sessions/s/transcript.jsonl"
        responses = await backend.adownload_files([path])
        content = responses[0].content.decode("utf-8")
        assert "system context" not in content
        assert "real user message" in content

    async def test_append_keeps_compact_summary(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """is_compact_summary=True 的摘要需要写入 transcript"""
        summary = make_meta_msg("对话历史摘要", is_compact_summary=True)
        await service.append("u", "s", [summary])

        path = "/u/sessions/s/transcript.jsonl"
        responses = await backend.adownload_files([path])
        content = responses[0].content.decode("utf-8")
        assert "对话历史摘要" in content

    async def test_append_keeps_compact_boundary(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """compact_boundary（is_meta=False）需要写入 transcript"""
        boundary = make_boundary_msg()
        await service.append("u", "s", [boundary])

        path = "/u/sessions/s/transcript.jsonl"
        responses = await backend.adownload_files([path])
        content = responses[0].content.decode("utf-8")
        assert "对话已压缩" in content

    async def test_append_is_append_only(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """多次 append 累积，不覆盖"""
        await service.append("u", "s", [make_user_msg("msg1")])
        await service.append("u", "s", [make_assistant_msg("reply1")])

        path = "/u/sessions/s/transcript.jsonl"
        responses = await backend.adownload_files([path])
        content = responses[0].content.decode("utf-8")
        assert "msg1" in content
        assert "reply1" in content

    async def test_append_all_meta_no_write(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """全是 is_meta 消息时不写文件"""
        await service.append("u", "s", [make_meta_msg("context")])

        path = "/u/sessions/s/transcript.jsonl"
        assert not await backend.aexists(path)

    async def test_append_assistant_always_written(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """AssistantMessage 永远写入"""
        await service.append("u", "s", [make_assistant_msg("I am the assistant")])

        path = "/u/sessions/s/transcript.jsonl"
        responses = await backend.adownload_files([path])
        content = responses[0].content.decode("utf-8")
        assert "I am the assistant" in content


class TestSessionIsolation:
    async def test_different_sessions_isolated(self, service: TranscriptService, backend: FilesystemBackend) -> None:
        """不同 session 的 transcript 互不干扰"""
        await service.append("u", "s1", [make_user_msg("session1")])
        await service.append("u", "s2", [make_user_msg("session2")])

        path1 = "/u/sessions/s1/transcript.jsonl"
        path2 = "/u/sessions/s2/transcript.jsonl"

        r1 = await backend.adownload_files([path1])
        r2 = await backend.adownload_files([path2])

        assert "session1" in r1[0].content.decode("utf-8")
        assert "session2" in r2[0].content.decode("utf-8")
        assert "session2" not in r1[0].content.decode("utf-8")


class TestErrorPaths:
    """错误路径测试"""

    async def test_append_fails_raises_os_error(
        self, backend: FilesystemBackend, service: TranscriptService
    ) -> None:
        """追加 transcript 失败时抛 OSError"""
        from unittest.mock import AsyncMock, patch
        from src.common.filesystem_backend import WriteResult

        with patch.object(
            backend, "aappend",
            new=AsyncMock(return_value=WriteResult(error="disk full"))
        ):
            with pytest.raises(OSError, match="写入失败"):
                await service.append("u", "s", [make_user_msg("new")])
