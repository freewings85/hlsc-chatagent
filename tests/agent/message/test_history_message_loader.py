"""HistoryMessageLoader 测试"""

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.message.history_message_loader import HistoryMessageLoader
from src.storage.local_backend import FilesystemBackend


class TestHistoryMessageLoader:

    def _make_loader(self, tmp_path) -> HistoryMessageLoader:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        return HistoryMessageLoader(backend)

    @pytest.mark.asyncio
    async def test_load_empty_session(self, tmp_path) -> None:
        """不存在的 session 返回空列表"""
        loader = self._make_loader(tmp_path)
        messages = await loader.load("u1", "s1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_append_and_load(self, tmp_path) -> None:
        """append 后 load 能拿到消息"""
        loader = self._make_loader(tmp_path)

        msg1 = ModelRequest(parts=[UserPromptPart(content="你好")])
        msg2 = ModelResponse(parts=[TextPart(content="你好！")])

        await loader.append("u1", "s1", [msg1, msg2])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 2
        assert messages[0].parts[0].content == "你好"
        assert messages[1].parts[0].content == "你好！"

    @pytest.mark.asyncio
    async def test_append_filters_is_meta(self, tmp_path) -> None:
        """is_meta 消息不持久化"""
        loader = self._make_loader(tmp_path)

        normal = ModelRequest(parts=[UserPromptPart(content="用户问题")])
        meta = ModelRequest(
            parts=[UserPromptPart(content="context")],
            metadata={"is_meta": True, "source": "merged_context"},
        )

        await loader.append("u1", "s1", [meta, normal])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].parts[0].content == "用户问题"

    @pytest.mark.asyncio
    async def test_append_all_meta_no_write(self, tmp_path) -> None:
        """全部都是 is_meta 时不写文件"""
        loader = self._make_loader(tmp_path)

        meta = ModelRequest(
            parts=[UserPromptPart(content="ctx")],
            metadata={"is_meta": True, "source": "agent_md"},
        )

        await loader.append("u1", "s1", [meta])

        messages = await loader.load("u1", "s1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_append_multiple_times(self, tmp_path) -> None:
        """多次 append 是累加的"""
        loader = self._make_loader(tmp_path)

        msg1 = ModelRequest(parts=[UserPromptPart(content="第一轮")])
        msg2 = ModelRequest(parts=[UserPromptPart(content="第二轮")])

        await loader.append("u1", "s1", [msg1])
        await loader.append("u1", "s1", [msg2])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 2
        assert messages[0].parts[0].content == "第一轮"
        assert messages[1].parts[0].content == "第二轮"

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, tmp_path) -> None:
        """不同 session 的消息互相隔离"""
        loader = self._make_loader(tmp_path)

        msg_a = ModelRequest(parts=[UserPromptPart(content="session A")])
        msg_b = ModelRequest(parts=[UserPromptPart(content="session B")])

        await loader.append("u1", "s1", [msg_a])
        await loader.append("u1", "s2", [msg_b])

        m1 = await loader.load("u1", "s1")
        m2 = await loader.load("u1", "s2")

        assert len(m1) == 1
        assert m1[0].parts[0].content == "session A"
        assert len(m2) == 1
        assert m2[0].parts[0].content == "session B"


class TestSave:

    def _make_loader(self, tmp_path) -> HistoryMessageLoader:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        return HistoryMessageLoader(backend)

    @pytest.mark.asyncio
    async def test_save_overwrites(self, tmp_path) -> None:
        """save 整体覆写 messages.jsonl"""
        loader = self._make_loader(tmp_path)

        # 先 append 3 条
        for text in ["a", "b", "c"]:
            await loader.append("u1", "s1", [ModelRequest(parts=[UserPromptPart(content=text)])])

        # save 覆写为 1 条（模拟 compact 后）
        compacted = [ModelRequest(parts=[UserPromptPart(content="summary of a+b+c")])]
        await loader.save("u1", "s1", compacted)

        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].parts[0].content == "summary of a+b+c"

    @pytest.mark.asyncio
    async def test_save_filters_is_meta(self, tmp_path) -> None:
        """save 也过滤 is_meta"""
        loader = self._make_loader(tmp_path)

        messages = [
            ModelRequest(parts=[UserPromptPart(content="real")]),
            ModelRequest(
                parts=[UserPromptPart(content="meta")],
                metadata={"is_meta": True, "source": "merged_context"},
            ),
        ]
        await loader.save("u1", "s1", messages)

        loaded = await loader.load("u1", "s1")
        assert len(loaded) == 1
        assert loaded[0].parts[0].content == "real"


class TestTranscript:

    @pytest.mark.asyncio
    async def test_append_writes_transcript(self, tmp_path) -> None:
        """append 同时写入 transcript.jsonl"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        msg = ModelRequest(parts=[UserPromptPart(content="hello")])
        await loader.append("u1", "s1", [msg])

        # transcript 文件应该存在
        transcript_path = "/u1/sessions/s1/transcript.jsonl"
        assert backend.exists(transcript_path)

    @pytest.mark.asyncio
    async def test_save_does_not_affect_transcript(self, tmp_path) -> None:
        """save 覆写 messages.jsonl 但不影响 transcript.jsonl"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        # append 2 条（写入 messages + transcript）
        msg1 = ModelRequest(parts=[UserPromptPart(content="first")])
        msg2 = ModelRequest(parts=[UserPromptPart(content="second")])
        await loader.append("u1", "s1", [msg1])
        await loader.append("u1", "s1", [msg2])

        # save 覆写 messages 为 compact 版本
        await loader.save("u1", "s1", [ModelRequest(parts=[UserPromptPart(content="compact")])])

        # messages.jsonl 只有 1 条
        messages = await loader.load("u1", "s1")
        assert len(messages) == 1

        # transcript.jsonl 仍然有原始 2 条
        responses = await backend.adownload_files(["/u1/sessions/s1/transcript.jsonl"])
        raw = responses[0].content.decode("utf-8").strip()
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2
