"""ContextInjector 测试"""

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.sdk._agent.message.context_injector import (
    inject_context,
    merge_context_messages,
    wrap_system_reminder,
)


class TestWrapSystemReminder:

    def test_wrap(self) -> None:
        result = wrap_system_reminder("hello")
        assert result == "<system-reminder>\nhello\n</system-reminder>"


class TestMergeContextMessages:

    def test_empty(self) -> None:
        assert merge_context_messages([]) is None

    def test_messages_without_user_parts(self) -> None:
        """有消息但没有 UserPromptPart，返回 None"""
        msg = ModelRequest(parts=[])  # 空 parts
        assert merge_context_messages([msg]) is None

    def test_single(self) -> None:
        msg = ModelRequest(
            parts=[UserPromptPart(content="agent.md content")],
            metadata={"is_meta": True, "source": "agent_md"},
        )
        merged = merge_context_messages([msg])
        assert merged is not None
        assert "<system-reminder>" in merged.parts[0].content
        assert "agent.md content" in merged.parts[0].content
        assert merged.metadata["is_meta"] is True
        assert merged.metadata["source"] == "merged_context"

    def test_multiple_merged(self) -> None:
        msgs = [
            ModelRequest(
                parts=[UserPromptPart(content="agent rules")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
            ModelRequest(
                parts=[UserPromptPart(content="memory content")],
                metadata={"is_meta": True, "source": "memory"},
            ),
        ]
        merged = merge_context_messages(msgs)
        assert merged is not None
        content = merged.parts[0].content
        assert "agent rules" in content
        assert "memory content" in content


class TestInjectContext:

    def test_inject_into_empty(self) -> None:
        messages = []
        context = [
            ModelRequest(
                parts=[UserPromptPart(content="ctx")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        inject_context(messages, context)
        assert len(messages) == 1
        assert "<system-reminder>" in messages[0].parts[0].content

    def test_inject_prepends_before_user(self) -> None:
        messages = [
            ModelRequest(parts=[UserPromptPart(content="用户问题")]),
            ModelResponse(parts=[TextPart(content="回答")]),
        ]
        context = [
            ModelRequest(
                parts=[UserPromptPart(content="ctx")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        inject_context(messages, context)
        assert len(messages) == 3
        assert messages[0].metadata["source"] == "merged_context"
        assert messages[1].parts[0].content == "用户问题"

    def test_inject_replaces_old_merged(self) -> None:
        """重复注入应替换旧的，不累积"""
        messages = [
            ModelRequest(parts=[UserPromptPart(content="用户问题")]),
        ]
        ctx1 = [
            ModelRequest(
                parts=[UserPromptPart(content="v1")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        ctx2 = [
            ModelRequest(
                parts=[UserPromptPart(content="v2")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        inject_context(messages, ctx1)
        assert len(messages) == 2

        inject_context(messages, ctx2)
        assert len(messages) == 2  # 没有累积
        assert "v2" in messages[0].parts[0].content

    def test_inject_empty_context(self) -> None:
        """空上下文不注入"""
        messages = [
            ModelRequest(parts=[UserPromptPart(content="用户问题")]),
        ]
        inject_context(messages, [])
        assert len(messages) == 1


class TestInjectContextEdgeCases:
    """US-006: ContextInjector 边界条件"""

    def test_inject_into_response_only_messages(self) -> None:
        """inject_context 对只包含 ModelResponse 的消息列表正确处理"""
        messages = [
            ModelResponse(parts=[TextPart(content="回答1")]),
            ModelResponse(parts=[TextPart(content="回答2")]),
        ]
        context = [
            ModelRequest(
                parts=[UserPromptPart(content="ctx")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]
        inject_context(messages, context)
        # 应该在 [0] 位置注入上下文
        assert len(messages) == 3
        assert messages[0].metadata["source"] == "merged_context"
        assert messages[1].parts[0].content == "回答1"

    def test_multiple_inject_no_accumulation(self) -> None:
        """多次 inject_context 不会累积重复的 merged_context 消息"""
        messages = [
            ModelRequest(parts=[UserPromptPart(content="问题")]),
        ]
        context = [
            ModelRequest(
                parts=[UserPromptPart(content="ctx")],
                metadata={"is_meta": True, "source": "agent_md"},
            ),
        ]

        # 注入 5 次
        for _ in range(5):
            inject_context(messages, context)

        # 应该只有 1 个 merged_context + 1 个用户消息 = 2
        assert len(messages) == 2
        merged_count = sum(
            1 for m in messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == "merged_context"
        )
        assert merged_count == 1
