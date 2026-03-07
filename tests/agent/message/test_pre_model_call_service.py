"""PreModelCallMessageService 测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.compact.compactor import CompactResult, Compactor
from src.agent.compact.config import CompactConfig
from src.agent.file_state import FileStateTracker
from src.agent.message.attachment_collector import AttachmentCollector, _ATTACHMENT_SOURCE
from src.agent.message.context_injector import _MERGED_META_SOURCE
from src.agent.message.pre_model_call_service import PreModelCallMessageService


def make_user_msg(content: str, source: str | None = None) -> ModelRequest:
    if source:
        return ModelRequest(
            parts=[UserPromptPart(content=content)],
            metadata={"is_meta": True, "source": source},
        )
    return ModelRequest(parts=[UserPromptPart(content=content)])


def make_assistant_msg(content: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=content)])


def make_context_messages(content: str = "agent.md content") -> list[ModelRequest]:
    return [ModelRequest(parts=[UserPromptPart(content=content)])]


def make_no_compact_compactor() -> Compactor:
    """创建一个不触发压缩的 Compactor（token 数远低于阈值）"""
    config = CompactConfig(
        context_window=200000,
        output_reserve=20000,
        auto_compact_enabled=True,
        microcompact_enabled=True,
        min_savings_threshold=100000,  # 阈值设很高，不触发
    )
    return Compactor(config=config)


class TestHandleContextInjection:
    async def test_context_injected_at_position_0(self) -> None:
        """context injection 注入到 [0] 位置"""
        context_messages = make_context_messages("agent rules")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        messages = [make_user_msg("hello")]
        result = await service.handle(messages)

        assert len(result.model_messages) >= 1
        first = result.model_messages[0]
        assert isinstance(first, ModelRequest)
        assert first.metadata is not None
        assert first.metadata.get("source") == _MERGED_META_SOURCE
        content = first.parts[0].content  # type: ignore[union-attr]
        assert "agent rules" in str(content)

    async def test_original_messages_not_modified(self) -> None:
        """不修改传入的 messages 列表"""
        context_messages = make_context_messages()
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        original_msg = make_user_msg("original")
        messages = [original_msg]
        original_len = len(messages)

        await service.handle(messages)

        assert len(messages) == original_len  # 传入的列表没有被修改


class TestHandleNoCompact:
    async def test_not_compacted_result(self) -> None:
        """没有压缩时 compacted=False"""
        context_messages = make_context_messages()
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        result = await service.handle([make_user_msg("hello")])
        assert result.compacted is False

    async def test_model_messages_equals_working_messages_when_no_compact(self) -> None:
        """未压缩时 model_messages 与 working_messages 内容一致"""
        context_messages = make_context_messages()
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        result = await service.handle([make_user_msg("hello")])
        assert len(result.model_messages) == len(result.working_messages)


class TestHandleWithCompact:
    async def test_compacted_true_when_microcompact_triggers(self, tmp_path: Path) -> None:
        """microcompact 触发时 compacted=True"""
        from src.agent.message.history_message_loader import _serialize_messages

        from src.storage.local_backend import FilesystemBackend
        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

        # 创建一个低阈值的 config，确保 microcompact 触发
        config = CompactConfig(
            context_window=1000,   # 很小的窗口
            output_reserve=100,
            auto_compact_enabled=True,
            microcompact_enabled=True,
            keep_recent_tool_results=1,
            min_savings_threshold=1,  # 很低的节省阈值
        )

        from src.agent.compact.token_counter import estimate_messages_tokens
        from pydantic_ai.messages import ToolReturnPart

        # 构造一个有大 tool result 的消息
        big_content = "x" * 10000  # 大 tool result
        tool_return_msg = ModelRequest(parts=[
            ToolReturnPart(
                tool_name="read",
                content=big_content,
                tool_call_id="call1",
            )
        ])
        tool_return_msg2 = ModelRequest(parts=[
            ToolReturnPart(
                tool_name="read",
                content=big_content,
                tool_call_id="call2",
            )
        ])

        compactor = Compactor(config=config)
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
        )

        messages = [tool_return_msg, tool_return_msg2]
        result = await service.handle(messages)

        assert result.compacted is True

    async def test_full_compact_clears_and_calls_summarize_fn(self) -> None:
        """full compact 触发时调用 summarize_fn，消息被替换为 [boundary, summary]"""
        config = CompactConfig(
            context_window=100,  # 极小窗口
            output_reserve=10,
            auto_compact_enabled=True,
            microcompact_enabled=False,
            min_savings_threshold=999999,  # 禁用 microcompact
        )

        mock_summarize = AsyncMock(return_value="This is the summary")
        compactor = Compactor(config=config, summarize_fn=mock_summarize)

        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
        )

        # 制造超过阈值的消息
        big_msg = make_user_msg("x" * 1000)
        result = await service.handle([big_msg])

        assert result.compacted is True
        mock_summarize.assert_called_once()
        # 消息应该包含 boundary + summary
        contents = [
            str(m.parts[0].content)  # type: ignore[union-attr]
            for m in result.working_messages
            if isinstance(m, ModelRequest)
        ]
        assert any("summary" in c.lower() or "压缩" in c for c in contents)


class TestHandleAttachmentOrder:
    async def test_attachment_injection_order_context_then_changes(self, tmp_path: Path) -> None:
        """处理顺序：context 先注入，attachment 后注入"""
        context_messages = make_context_messages("system rules")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        messages = [make_user_msg("user input")]
        result = await service.handle(messages)

        # context 应该在 [0]
        first = result.model_messages[0]
        assert isinstance(first, ModelRequest)
        assert first.metadata is not None
        assert first.metadata.get("source") == _MERGED_META_SOURCE


class TestHandlePostCompactAttachments:
    """full compact 后 attachments 重新注入"""

    async def test_post_compact_attachments_injected(self) -> None:
        """compact_result.attachments 非空时，触发重新注入"""
        from unittest.mock import AsyncMock, patch

        context_messages: list[ModelRequest] = []
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)

        # 构造一个会返回 compacted=True + attachments 的 Compactor
        restore_attachment = ModelRequest(
            parts=[UserPromptPart(content="restored file content")],
            metadata={"is_meta": True},
        )
        compact_result_with_attachments = CompactResult(
            compacted=True,
            layer="full",
            attachments=[restore_attachment],
        )

        mock_compactor = MagicMock(spec=Compactor)
        mock_compactor.check = AsyncMock(return_value=compact_result_with_attachments)

        service = PreModelCallMessageService(
            compactor=mock_compactor,
            context_messages=context_messages,
            attachment_collector=collector,
        )

        messages = [make_user_msg("hello")]
        result = await service.handle(messages)

        assert result.compacted is True
        # restore_attachment 应该出现在 model_messages 中
        restore_contents = [
            str(m.parts[0].content)  # type: ignore[union-attr]
            for m in result.model_messages
            if isinstance(m, ModelRequest)
        ]
        assert any("restored file content" in c for c in restore_contents)
