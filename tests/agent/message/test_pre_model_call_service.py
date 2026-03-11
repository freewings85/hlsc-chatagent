"""PreModelCallMessageService 测试"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.compact.compactor import CompactResult, Compactor
from src.agent.compact.config import CompactConfig
from src.agent.file_state import FileStateTracker
from src.agent.message.attachment_collector import AttachmentCollector, _ATTACHMENT_SOURCE
from src.agent.message.context_injector import _MERGED_META_SOURCE
from src.agent.message.pre_model_call_service import (
    PreModelCallMessageService,
    _INVOKED_SKILLS_SOURCE,
    _SKILL_LISTING_SOURCE,
)
from src.agent.skills.invoked_store import InvokedSkill, InvokedSkillStore
from src.agent.skills.registry import SkillEntry, SkillRegistry


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
        """full compact 触发时调用 summarize_fn，旧消息被摘要 + 近期消息保留"""
        config = CompactConfig(
            context_window=100,  # 极小窗口
            output_reserve=10,
            auto_compact_enabled=True,
            microcompact_enabled=False,
            min_savings_threshold=999999,  # 禁用 microcompact
            keep_recent_min_tokens=10,
            keep_recent_max_tokens=100,
            keep_recent_min_messages=1,
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

        # 构造多条消息：旧的大消息 + 近期小消息
        old_msg = make_user_msg("x" * 800)
        old_resp = ModelResponse(parts=[TextPart(content="y" * 200)])
        recent_msg = make_user_msg("最近的问题")
        result = await service.handle([old_msg, old_resp, recent_msg])

        assert result.compacted is True
        mock_summarize.assert_called_once()
        # 消息应该包含 boundary + summary + kept recent
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


# --------------------------------------------------------------------------- #
# Skill 注入测试                                                               #
# --------------------------------------------------------------------------- #

def make_skill_registry(*names: str) -> SkillRegistry:
    registry = SkillRegistry()
    for name in names:
        registry._entries[name] = SkillEntry(
            name=name,
            description=f"{name} description",
            content=f"# {name} skill content",
            when_to_use=f"Use when doing {name}.",
        )
    return registry


def make_invoked_store_with(skills: dict[str, str]) -> InvokedSkillStore:
    """创建已有记录的 InvokedSkillStore mock。"""
    store = MagicMock(spec=InvokedSkillStore)
    store.get_all.return_value = {
        name: InvokedSkill(
            name=name,
            content=content,
            invoked_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
        )
        for name, content in skills.items()
    }
    return store


class TestSkillListingInjection:
    async def test_skill_listing_injected_when_registry_provided(self) -> None:
        """提供 skill_registry 时注入 skill_listing attachment"""
        registry = make_skill_registry("commit")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            skill_registry=registry,
        )

        result = await service.handle([make_user_msg("hello")])

        sources = [
            m.metadata.get("source")
            for m in result.model_messages
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict)
        ]
        assert _SKILL_LISTING_SOURCE in sources

    async def test_skill_listing_not_injected_when_no_registry(self) -> None:
        """无 skill_registry 时不注入 skill_listing"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
        )

        result = await service.handle([make_user_msg("hello")])

        sources = [
            m.metadata.get("source")
            for m in result.model_messages
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict)
        ]
        assert _SKILL_LISTING_SOURCE not in sources

    async def test_skill_listing_content_contains_skill_names(self) -> None:
        """skill_listing attachment 内容包含 skill 名称"""
        registry = make_skill_registry("commit", "review")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            skill_registry=registry,
        )

        result = await service.handle([make_user_msg("hello")])

        listing_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        ]
        assert len(listing_msgs) == 1
        content = str(listing_msgs[0].parts[0].content)  # type: ignore[union-attr]
        assert "commit" in content
        assert "review" in content

    async def test_skill_listing_wrapped_in_system_reminder(self) -> None:
        """skill_listing 包裹在 <system-reminder> 标签中"""
        registry = make_skill_registry("commit")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            skill_registry=registry,
        )

        result = await service.handle([make_user_msg("hello")])

        listing_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        ]
        content = str(listing_msgs[0].parts[0].content)  # type: ignore[union-attr]
        assert "<system-reminder>" in content
        assert "</system-reminder>" in content

    async def test_old_skill_listing_replaced_each_call(self) -> None:
        """每次 handle 都替换旧的 skill_listing（不重复累积）"""
        registry = make_skill_registry("commit")
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            skill_registry=registry,
        )

        messages = [make_user_msg("hello")]
        result1 = await service.handle(messages)
        result2 = await service.handle(result1.model_messages)

        listing_count = sum(
            1 for m in result2.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _SKILL_LISTING_SOURCE
        )
        assert listing_count == 1


class TestInvokedSkillsInjection:
    async def test_invoked_skills_injected_when_store_has_records(self) -> None:
        """store 有记录时注入 invoked_skills attachment"""
        store = make_invoked_store_with({"commit": "# Commit\nStep 1."})
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            invoked_skill_store=store,
        )

        result = await service.handle([make_user_msg("hello")])

        sources = [
            m.metadata.get("source")
            for m in result.model_messages
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict)
        ]
        assert _INVOKED_SKILLS_SOURCE in sources

    async def test_invoked_skills_not_injected_when_store_empty(self) -> None:
        """store 为空时不注入 invoked_skills attachment"""
        store = make_invoked_store_with({})
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            invoked_skill_store=store,
        )

        result = await service.handle([make_user_msg("hello")])

        sources = [
            m.metadata.get("source")
            for m in result.model_messages
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict)
        ]
        assert _INVOKED_SKILLS_SOURCE not in sources

    async def test_invoked_skills_not_injected_when_store_none(self) -> None:
        """store 为 None 时不注入"""
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
        )

        result = await service.handle([make_user_msg("hello")])

        sources = [
            m.metadata.get("source")
            for m in result.model_messages
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict)
        ]
        assert _INVOKED_SKILLS_SOURCE not in sources

    async def test_invoked_skills_content_contains_skill_content(self) -> None:
        """invoked_skills attachment 内容包含 SKILL.md 正文"""
        store = make_invoked_store_with({"commit": "# Commit\nDo the commit."})
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            invoked_skill_store=store,
        )

        result = await service.handle([make_user_msg("hello")])

        invoked_msgs = [
            m for m in result.model_messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == _INVOKED_SKILLS_SOURCE
        ]
        assert len(invoked_msgs) == 1
        content = str(invoked_msgs[0].parts[0].content)  # type: ignore[union-attr]
        assert "# Commit" in content
        assert "Do the commit." in content


class TestSkillInjectionOrder:
    async def test_invoked_skills_before_skill_listing(self) -> None:
        """invoked_skills attachment 在 skill_listing 之前（更靠近消息开头）"""
        registry = make_skill_registry("commit")
        store = make_invoked_store_with({"commit": "# Commit"})
        tracker = FileStateTracker()
        collector = AttachmentCollector(tracker)
        compactor = make_no_compact_compactor()

        service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=[],
            attachment_collector=collector,
            skill_registry=registry,
            invoked_skill_store=store,
        )

        result = await service.handle([make_user_msg("hello")])

        positions: dict[str, int] = {}
        for i, m in enumerate(result.model_messages):
            if isinstance(m, ModelRequest) and isinstance(m.metadata, dict):
                src = m.metadata.get("source")
                if src in (_INVOKED_SKILLS_SOURCE, _SKILL_LISTING_SOURCE):
                    positions[str(src)] = i

        # invoked_skills（0a）应比 skill_listing（0b）更靠前
        assert positions.get(_INVOKED_SKILLS_SOURCE, 999) < positions.get(_SKILL_LISTING_SOURCE, 999)
