"""HistoryMessageLoader 测试"""

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.agent_message import AssistantMessage, UserMessage
from src.agent.message.history_message_loader import HistoryMessageLoader, _deserialize_messages
from src.storage.local_backend import FilesystemBackend


def make_user(content: str) -> UserMessage:
    return UserMessage(content=content)


def make_assistant(content: str) -> AssistantMessage:
    return AssistantMessage(content=content)


def make_meta(content: str, **extra: object) -> UserMessage:
    meta: dict = {"is_meta": True, **extra}
    return UserMessage(content=content, metadata=meta)


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

        msg1 = make_user("你好")
        msg2 = make_assistant("你好！")

        await loader.append("u1", "s1", [msg1, msg2])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 2
        assert messages[0].content == "你好"
        assert messages[1].content == "你好！"

    @pytest.mark.asyncio
    async def test_append_filters_is_meta(self, tmp_path) -> None:
        """is_meta 消息不持久化"""
        loader = self._make_loader(tmp_path)

        normal = make_user("用户问题")
        meta = make_meta("context", source="merged_context")

        await loader.append("u1", "s1", [meta, normal])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].content == "用户问题"

    @pytest.mark.asyncio
    async def test_append_all_meta_no_write(self, tmp_path) -> None:
        """全部都是 is_meta 时不写文件"""
        loader = self._make_loader(tmp_path)

        meta = make_meta("ctx", source="agent_md")

        await loader.append("u1", "s1", [meta])

        messages = await loader.load("u1", "s1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_append_multiple_times(self, tmp_path) -> None:
        """多次 append 是累加的"""
        loader = self._make_loader(tmp_path)

        msg1 = make_user("第一轮")
        msg2 = make_user("第二轮")

        await loader.append("u1", "s1", [msg1])
        await loader.append("u1", "s1", [msg2])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 2
        assert messages[0].content == "第一轮"
        assert messages[1].content == "第二轮"

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, tmp_path) -> None:
        """不同 session 的消息互相隔离"""
        loader = self._make_loader(tmp_path)

        msg_a = make_user("session A")
        msg_b = make_user("session B")

        await loader.append("u1", "s1", [msg_a])
        await loader.append("u1", "s2", [msg_b])

        m1 = await loader.load("u1", "s1")
        m2 = await loader.load("u1", "s2")

        assert len(m1) == 1
        assert m1[0].content == "session A"
        assert len(m2) == 1
        assert m2[0].content == "session B"


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
            await loader.append("u1", "s1", [make_user(text)])

        # save 覆写为 1 条（模拟 compact 后）
        compacted = [make_user("summary of a+b+c")]
        await loader.save("u1", "s1", compacted)

        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].content == "summary of a+b+c"

    @pytest.mark.asyncio
    async def test_save_filters_is_meta(self, tmp_path) -> None:
        """save 也过滤 is_meta"""
        loader = self._make_loader(tmp_path)

        messages = [
            make_user("real"),
            make_meta("meta", source="merged_context"),
        ]
        await loader.save("u1", "s1", messages)

        loaded = await loader.load("u1", "s1")
        assert len(loaded) == 1
        assert loaded[0].content == "real"


class TestTranscript:

    @pytest.mark.asyncio
    async def test_append_writes_transcript(self, tmp_path) -> None:
        """append 同时写入 transcript.jsonl"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        msg = make_user("hello")
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
        msg1 = make_user("first")
        msg2 = make_user("second")
        await loader.append("u1", "s1", [msg1])
        await loader.append("u1", "s1", [msg2])

        # save 覆写 messages 为 compact 版本
        await loader.save("u1", "s1", [make_user("compact")])

        # messages.jsonl 只有 1 条
        messages = await loader.load("u1", "s1")
        assert len(messages) == 1

        # transcript.jsonl 仍然有原始 2 条
        responses = await backend.adownload_files(["/u1/sessions/s1/transcript.jsonl"])
        raw = responses[0].content.decode("utf-8").strip()
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2


class TestHistoryLoaderRobustness:
    """US-003: HistoryMessageLoader 并发安全与序列化鲁棒性"""

    def _make_loader(self, tmp_path) -> HistoryMessageLoader:
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        return HistoryMessageLoader(backend)

    @pytest.mark.asyncio
    async def test_concurrent_append_no_message_loss(self, tmp_path) -> None:
        """并发 append 同一 session 不丢消息"""
        import asyncio
        loader = self._make_loader(tmp_path)

        async def append_msg(idx: int) -> None:
            msg = make_user(f"msg-{idx}")
            await loader.append("u1", "s1", [msg])

        # 并发 append 10 条
        await asyncio.gather(*[append_msg(i) for i in range(10)])

        messages = await loader.load("u1", "s1")
        assert len(messages) == 10
        contents = {m.content for m in messages}
        for i in range(10):
            assert f"msg-{i}" in contents

    @pytest.mark.asyncio
    async def test_corrupted_jsonl_line_skipped(self, tmp_path) -> None:
        """JSONL 中有损坏行（非法 JSON）时跳过该行而不是整个文件失败"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        # 先写入一条正常消息
        msg = make_user("valid")
        await loader.append("u1", "s1", [msg])

        # 手动在文件中插入损坏行
        path = "/u1/sessions/s1/messages.jsonl"
        responses = await backend.adownload_files([path])
        original = responses[0].content.decode("utf-8")
        corrupted = original.rstrip() + "\n{invalid json here}\n"
        await backend.adelete(path)
        await backend.awrite(path, corrupted)

        # load 应该跳过损坏行，返回有效消息
        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].content == "valid"

    @pytest.mark.asyncio
    async def test_empty_file_returns_empty_list(self, tmp_path) -> None:
        """空文件（0 字节）load 返回空列表"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        # 写入空文件
        path = "/u1/sessions/s1/messages.jsonl"
        await backend.awrite(path, "")

        messages = await loader.load("u1", "s1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_serialization_roundtrip(self, tmp_path) -> None:
        """save 后再 load 的消息与原始消息完全一致（序列化往返测试）"""
        loader = self._make_loader(tmp_path)

        original = [
            make_user("用户问题"),
            make_assistant("助手回答"),
            make_user("第二轮"),
            make_assistant("第二轮回答"),
        ]

        await loader.save("u1", "s1", original)
        loaded = await loader.load("u1", "s1")

        assert len(loaded) == len(original)
        for orig, load in zip(original, loaded):
            assert orig.content == load.content


class TestHistoryLoaderBackendFailure:
    """Codex Issue #2/#3: 后端失败时不静默丢数据"""

    @pytest.mark.asyncio
    async def test_append_read_failure_raises(self, tmp_path) -> None:
        """后端读取失败时 append 应抛异常，不删除旧文件"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        # 先写入一条消息
        msg = make_user("original")
        await loader.append("u1", "s1", [msg])

        # Mock adownload_files 返回错误
        original_download = backend.adownload_files

        async def failing_download(paths: list[str]) -> list:
            from src.common.filesystem_backend import FileDownloadResponse
            return [FileDownloadResponse(path=paths[0], content=None, error="read error")]

        backend.adownload_files = failing_download  # type: ignore[assignment]

        new_msg = make_user("new")
        with pytest.raises(OSError, match="读取失败"):
            await loader.append("u1", "s1", [new_msg])

        # 恢复原始方法，验证旧数据完整
        backend.adownload_files = original_download  # type: ignore[assignment]
        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].content == "original"

    @pytest.mark.asyncio
    async def test_save_write_failure_raises(self, tmp_path) -> None:
        """后端写入失败时 save 应抛异常"""
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        original_write = backend.awrite

        async def failing_write(path: str, content: str) -> object:
            from src.common.filesystem_backend import WriteResult
            return WriteResult(path=path, error="disk full")

        backend.awrite = failing_write  # type: ignore[assignment]

        msg = make_user("test")
        with pytest.raises(OSError, match="写入失败"):
            await loader.save("u1", "s1", [msg])


class TestDeserializeMessages:

    def test_skips_empty_lines(self) -> None:
        """JSONL 中的空行被跳过"""
        msg = UserMessage(content="hello")
        json_line = msg.model_dump_json()
        # 加入空行
        raw = f"{json_line}\n\n{json_line}\n"
        result = _deserialize_messages(raw)
        assert len(result) == 2



class TestSaveEdgeCases:
    """US-004: save() 中 adelete 返回 False 时抛出 OSError"""

    @pytest.mark.asyncio
    async def test_save_delete_failure_raises(self, tmp_path) -> None:
        """save 时 adelete 返回 False → 抛出 OSError"""
        from src.storage.local_backend import FilesystemBackend
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        # 先写入一条消息（让文件存在，save 才会执行 adelete）
        msg = make_user("original")
        await loader.append("u1", "s1", [msg])

        # Mock adelete 返回 False
        original_delete = backend.adelete

        async def failing_delete(path: str) -> bool:
            return False

        backend.adelete = failing_delete  # type: ignore[assignment]

        new_msg = make_user("new")
        with pytest.raises(OSError, match="无法删除旧文件"):
            await loader.save("u1", "s1", [new_msg])

        # 恢复并验证旧数据仍存在
        backend.adelete = original_delete  # type: ignore[assignment]
        messages = await loader.load("u1", "s1")
        assert len(messages) == 1
        assert messages[0].content == "original"


class TestAppendEdgeCases:
    """US-004: append() 中 awrite 失败时抛出 OSError"""

    @pytest.mark.asyncio
    async def test_append_write_failure_raises(self, tmp_path) -> None:
        """append 时 awrite 失败 → 抛出 OSError"""
        from src.storage.local_backend import FilesystemBackend
        from src.common.filesystem_backend import WriteResult
        backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
        loader = HistoryMessageLoader(backend)

        original_write = backend.awrite

        async def failing_write(path: str, content: str) -> WriteResult:
            return WriteResult(path=path, error="disk full")

        backend.awrite = failing_write  # type: ignore[assignment]

        msg = make_user("test")
        with pytest.raises(OSError, match="写入失败"):
            await loader.append("u1", "s1", [msg])
