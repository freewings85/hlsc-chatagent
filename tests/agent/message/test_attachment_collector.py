"""AttachmentCollector 测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.compact.compactor import CompactResult
from src.agent.file_state import FileStateTracker
from src.agent.message.attachment_collector import (
    AttachmentCollector,
    _ATTACHMENT_SOURCE,
)


def make_user_msg(content: str, is_meta: bool = False) -> ModelRequest:
    return ModelRequest(
        parts=[UserPromptPart(content=content)],
        metadata={"is_meta": is_meta} if is_meta else None,
    )


def make_assistant_msg(content: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=content)])


class TestAttachmentCollectorNoChanges:
    """没有 changed_files 时的行为"""

    def test_inject_no_changes_no_effect(self) -> None:
        """没有 changed_files 时不注入任何 attachment"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        messages = [make_user_msg("hello")]

        collector.inject(messages, CompactResult())

        assert len(messages) == 1  # 没有新增

    def test_removes_old_attachment_even_if_no_new_changes(self) -> None:
        """即使没有新 changed_files，也会清除旧 attachment"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)

        old_attachment = ModelRequest(
            parts=[UserPromptPart(content="old")],
            metadata={"is_meta": True, "source": _ATTACHMENT_SOURCE},
        )
        messages = [make_user_msg("hello"), old_attachment]

        collector.inject(messages, CompactResult())

        assert len(messages) == 1
        assert messages[0].parts[0].content == "hello"  # type: ignore[union-attr]


class TestAttachmentCollectorWithChanges:
    """有 changed_files 时的行为"""

    def test_inject_changed_file_appends_meta_message(self, tmp_path: Path) -> None:
        """changed_files 时追加 is_meta attachment"""
        target = tmp_path / "foo.py"
        target.write_text("original")

        tracker = FileStateTracker()
        tracker.on_read(str(target), "original", 0.0, None, None)

        collector = AttachmentCollector(tracker)
        messages = [make_user_msg("hello")]

        # 模拟文件 mtime 已改变
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_mtime = 999.0
            collector.inject(messages, CompactResult())

        assert len(messages) == 2
        attachment = messages[1]
        assert isinstance(attachment, ModelRequest)
        assert attachment.metadata is not None
        assert attachment.metadata.get("is_meta") is True
        assert attachment.metadata.get("source") == _ATTACHMENT_SOURCE
        content = attachment.parts[0].content  # type: ignore[union-attr]
        assert isinstance(content, str)
        assert "外部修改" in content
        assert str(target) in content

    def test_inject_replaces_old_attachment_with_new(self, tmp_path: Path) -> None:
        """每次 inject 先清除旧的 attachment，再注入新的"""
        target = tmp_path / "bar.py"
        target.write_text("v1")

        tracker = FileStateTracker()
        tracker.on_read(str(target), "v1", 0.0, None, None)

        collector = AttachmentCollector(tracker)

        old_attachment = ModelRequest(
            parts=[UserPromptPart(content="old attachment")],
            metadata={"is_meta": True, "source": _ATTACHMENT_SOURCE},
        )
        messages = [make_user_msg("msg"), old_attachment]

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_mtime = 999.0
            collector.inject(messages, CompactResult())

        # 旧的被替换，有且只有一个 attachment
        attachments = [
            m for m in messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _ATTACHMENT_SOURCE
        ]
        assert len(attachments) == 1
        content = attachments[0].parts[0].content  # type: ignore[union-attr]
        assert "old attachment" not in str(content)


class TestAttachmentCollectorCompactAttachments:
    """compact_result.attachments 的处理"""

    def test_compact_attachments_inserted_after_context(self) -> None:
        """compact_result.attachments 插入到 [1] 位置"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)

        context_msg = ModelRequest(
            parts=[UserPromptPart(content="context")],
            metadata={"is_meta": True, "source": "merged_context"},
        )
        user_msg = make_user_msg("hello")
        messages = [context_msg, user_msg]

        compact_attach = ModelRequest(
            parts=[UserPromptPart(content="restore file content")],
            metadata={"is_meta": True},
        )
        compact_result = CompactResult(
            compacted=True,
            layer="full",
            attachments=[compact_attach],
        )

        collector.inject(messages, compact_result)

        # compact attachment 应插在 [1]，context 在 [0]，user_msg 在 [2]
        assert messages[0] is context_msg
        assert messages[1] is compact_attach
        assert messages[2] is user_msg

    def test_empty_messages_compact_attachments_at_start(self) -> None:
        """空消息列表时 compact attachments 从 [0] 开始插入"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        messages: list = []

        compact_attach = ModelRequest(
            parts=[UserPromptPart(content="restore")],
            metadata={"is_meta": True},
        )
        compact_result = CompactResult(
            compacted=True,
            layer="full",
            attachments=[compact_attach],
        )

        collector.inject(messages, compact_result)

        assert len(messages) == 1
        assert messages[0] is compact_attach


class TestAttachmentCollectorSystemReminderFormat:
    """attachment 格式验证"""

    def test_changed_files_wrapped_in_system_reminder(self, tmp_path: Path) -> None:
        """attachment 内容包裹在 <system-reminder> 标签中"""
        target = tmp_path / "test.txt"
        target.write_text("content")

        tracker = FileStateTracker()
        tracker.on_read(str(target), "content", 0.0, None, None)

        collector = AttachmentCollector(tracker)
        messages: list = []

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_mtime = 999.0
            collector.inject(messages, CompactResult())

        assert len(messages) == 1
        content = messages[0].parts[0].content  # type: ignore[union-attr]
        assert "<system-reminder>" in content
        assert "</system-reminder>" in content
