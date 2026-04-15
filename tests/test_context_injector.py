"""测试 context_injector 的静态/动态拆分 + tail reminder 生命周期。"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agent_sdk._agent.message.context_injector import (
    DYNAMIC_CONTEXT_TAG,
    INVOKED_SKILLS_TAG,
    build_dynamic_context_part,
    build_invoked_skills_part,
    extract_dynamic_text,
    inject_context,
    is_tail_reminder_part,
    strip_tail_reminders,
)
from agent_sdk._agent.agent_message import from_model_messages


def _make_context_msg(content: str, source: str) -> ModelRequest:
    """创建 is_meta context message。"""
    return ModelRequest(
        parts=[UserPromptPart(content=content)],
        metadata={"is_meta": True, "source": source},
    )


def _make_user_msg(content: str) -> ModelRequest:
    """创建普通 user message（不带 is_meta）。"""
    return ModelRequest(
        parts=[UserPromptPart(content=content)],
    )


# --------------------------------------------------------------------------- #
# inject_context：静态 context prepend
# --------------------------------------------------------------------------- #


class TestInjectContext:
    """测试 inject_context 的静态注入行为。"""

    def test_static_context_prepended(self) -> None:
        """静态 context（agent_md, memory）应合并 prepend 到 [0]。"""
        messages: list[ModelMessage] = [_make_user_msg("你好")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("MEMORY.md 内容", "memory"),
        ]

        inject_context(messages, context_msgs)

        assert len(messages) == 2
        first_msg: ModelRequest = messages[0]  # type: ignore[assignment]
        first_content: str = first_msg.parts[0].content  # type: ignore[assignment]
        assert "AGENT.md 内容" in first_content
        assert "MEMORY.md 内容" in first_content
        assert "<system-reminder>" in first_content

    def test_dynamic_context_not_injected_by_inject_context(self) -> None:
        """动态 context 不由 inject_context 注入（由 loop 注入到 node.request）。"""
        messages: list[ModelMessage] = [_make_user_msg("帮我找个店")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("current_car: 朗逸", "request_context"),
            _make_context_msg("[session_state]: projects=[]", "session_state"),
        ]

        inject_context(messages, context_msgs)

        last_user_content: str = messages[-1].parts[0].content  # type: ignore[assignment]
        assert DYNAMIC_CONTEXT_TAG not in last_user_content
        assert INVOKED_SKILLS_TAG not in last_user_content
        assert "帮我找个店" in last_user_content

    def test_static_and_dynamic_separated(self) -> None:
        """静态在 [0]，动态不注入到消息中。"""
        messages: list[ModelMessage] = [_make_user_msg("附近有什么修车店")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 静态内容", "agent_md"),
            _make_context_msg("位置: 浦东", "request_context"),
        ]

        inject_context(messages, context_msgs)

        first_content: str = messages[0].parts[0].content  # type: ignore[assignment]
        assert "AGENT 静态内容" in first_content
        assert "位置: 浦东" not in first_content

        last_content: str = messages[-1].parts[0].content  # type: ignore[assignment]
        assert DYNAMIC_CONTEXT_TAG not in last_content

    def test_no_static_context_no_prepend(self) -> None:
        """没有静态 context 时，不应 prepend 任何 merged context。"""
        messages: list[ModelMessage] = [_make_user_msg("你好")]
        inject_context(messages, [])
        assert len(messages) == 1
        assert "你好" in messages[0].parts[0].content  # type: ignore[union-attr]

    def test_old_merged_context_replaced(self) -> None:
        """已有 merged_context 会被替换成新的（不会叠加）。"""
        messages: list[ModelMessage] = [
            _make_context_msg("旧的 merged", "merged_context"),
            _make_user_msg("hi"),
        ]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("新的 AGENT", "agent_md"),
        ]

        inject_context(messages, context_msgs)

        merged_count: int = sum(
            1 for m in messages
            if isinstance(m, ModelRequest)
            and isinstance(m.metadata, dict)
            and m.metadata.get("source") == "merged_context"
        )
        assert merged_count == 1
        assert "新的 AGENT" in messages[0].parts[0].content  # type: ignore[union-attr]
        assert "旧的 merged" not in messages[0].parts[0].content  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# is_tail_reminder_part / strip_tail_reminders
# --------------------------------------------------------------------------- #


class TestTailReminderIdentification:
    """is_tail_reminder_part 根据 <system-reminder> 外壳识别 tail reminder。"""

    def test_dynamic_context_part_is_tail_reminder(self) -> None:
        part: UserPromptPart = build_dynamic_context_part("car=朗逸")
        assert is_tail_reminder_part(part) is True

    def test_invoked_skills_part_is_tail_reminder(self) -> None:
        part: UserPromptPart = build_invoked_skills_part("### Skill: commit\n...")
        assert is_tail_reminder_part(part) is True

    def test_regular_user_prompt_not_tail_reminder(self) -> None:
        part: UserPromptPart = UserPromptPart(content="普通用户消息")
        assert is_tail_reminder_part(part) is False

    def test_non_userprompt_part_not_tail_reminder(self) -> None:
        part: ToolReturnPart = ToolReturnPart(
            tool_name="foo", content="bar", tool_call_id="x",
        )
        assert is_tail_reminder_part(part) is False

    def test_content_that_merely_contains_system_reminder_not_tail(self) -> None:
        """内容只是包含 <system-reminder> 字样但不是外壳包裹 → 不算 tail reminder。"""
        part: UserPromptPart = UserPromptPart(content="用户说：<system-reminder> 啥意思")
        assert is_tail_reminder_part(part) is False


class TestStripTailReminders:
    """strip_tail_reminders 剥离真实 user message 上的 tail reminder parts，不动 meta ModelRequest。"""

    def test_strips_dynamic_context_part_from_user_msg(self) -> None:
        user_msg: ModelRequest = ModelRequest(parts=[
            UserPromptPart(content="用户原话"),
            build_dynamic_context_part("car=朗逸"),
        ])
        messages: list[ModelMessage] = [user_msg]

        strip_tail_reminders(messages)

        assert len(user_msg.parts) == 1
        assert user_msg.parts[0].content == "用户原话"  # type: ignore[union-attr]

    def test_strips_invoked_skills_part(self) -> None:
        user_msg: ModelRequest = ModelRequest(parts=[
            UserPromptPart(content="用户原话"),
            build_invoked_skills_part("### Skill: commit\n..."),
        ])
        messages: list[ModelMessage] = [user_msg]

        strip_tail_reminders(messages)

        assert len(user_msg.parts) == 1
        assert user_msg.parts[0].content == "用户原话"  # type: ignore[union-attr]

    def test_strips_both_dynamic_and_invoked(self) -> None:
        user_msg: ModelRequest = ModelRequest(parts=[
            UserPromptPart(content="用户"),
            build_dynamic_context_part("dyn"),
            build_invoked_skills_part("inv"),
        ])
        strip_tail_reminders([user_msg])
        assert len(user_msg.parts) == 1

    def test_skips_meta_model_request(self) -> None:
        """is_meta=True 的 ModelRequest（如 skill_listing / merged_context）不动。"""
        meta_msg: ModelRequest = ModelRequest(
            parts=[UserPromptPart(content="<system-reminder>\n## skill-listing\n...\n</system-reminder>")],
            metadata={"is_meta": True, "source": "skill_listing"},
        )
        messages: list[ModelMessage] = [meta_msg]

        strip_tail_reminders(messages)

        # meta 消息的 parts 不受影响（整条保留）
        assert len(meta_msg.parts) == 1
        assert "## skill-listing" in meta_msg.parts[0].content  # type: ignore[union-attr]

    def test_strips_across_multi_turn(self) -> None:
        """历史里所有普通 user message 上的 tail reminder 都被 strip。"""
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="msg1"),
                build_dynamic_context_part("d1"),
            ]),
            ModelResponse(parts=[TextPart(content="reply1")]),
            ModelRequest(parts=[
                UserPromptPart(content="msg2"),
                build_dynamic_context_part("d2"),
                build_invoked_skills_part("inv"),
            ]),
        ]

        strip_tail_reminders(messages)

        assert len(messages[0].parts) == 1  # type: ignore[union-attr]
        assert messages[0].parts[0].content == "msg1"  # type: ignore[union-attr]
        assert len(messages[2].parts) == 1  # type: ignore[union-attr]
        assert messages[2].parts[0].content == "msg2"  # type: ignore[union-attr]

    def test_preserves_tool_return_parts(self) -> None:
        """ToolReturnPart 不是 tail reminder，不应被删。"""
        msg: ModelRequest = ModelRequest(parts=[
            ToolReturnPart(tool_name="search", content="5 家店", tool_call_id="call_1"),
            build_dynamic_context_part("dyn"),
        ])

        strip_tail_reminders([msg])

        assert len(msg.parts) == 1
        assert isinstance(msg.parts[0], ToolReturnPart)


# --------------------------------------------------------------------------- #
# extract_dynamic_text / build_* parts
# --------------------------------------------------------------------------- #


class TestExtractDynamicText:
    def test_extract_from_request_context(self) -> None:
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("current_car: 朗逸", "request_context"),
        ]
        text: str = extract_dynamic_text(context_msgs)
        assert "current_car: 朗逸" in text
        assert "AGENT.md 内容" not in text

    def test_extract_multiple_dynamic(self) -> None:
        context_msgs: list[ModelRequest] = [
            _make_context_msg("car=朗逸", "request_context"),
            _make_context_msg("scene=guide", "session_state"),
        ]
        text: str = extract_dynamic_text(context_msgs)
        assert "car=朗逸" in text
        assert "scene=guide" in text

    def test_extract_empty_when_no_dynamic(self) -> None:
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 内容", "agent_md"),
        ]
        assert extract_dynamic_text(context_msgs) == ""


class TestBuildParts:
    def test_dynamic_context_part_structure(self) -> None:
        part: UserPromptPart = build_dynamic_context_part("car=朗逸")
        content: str = part.content  # type: ignore[assignment]
        assert content.startswith("<system-reminder>\n")
        assert content.rstrip().endswith("</system-reminder>")
        assert DYNAMIC_CONTEXT_TAG in content
        assert "car=朗逸" in content

    def test_invoked_skills_part_structure(self) -> None:
        part: UserPromptPart = build_invoked_skills_part("### Skill: commit")
        content: str = part.content  # type: ignore[assignment]
        assert content.startswith("<system-reminder>\n")
        assert content.rstrip().endswith("</system-reminder>")
        assert INVOKED_SKILLS_TAG in content
        assert "### Skill: commit" in content


# --------------------------------------------------------------------------- #
# from_model_messages 持久化剥离（防御性兜底）
# --------------------------------------------------------------------------- #


class TestFromModelMessagesStripsTail:
    """from_model_messages 防御性兜底：即使 loop 漏了 strip，持久化路径也不会写入 tail reminder。"""

    def test_dynamic_context_part_stripped_on_persist(self) -> None:
        dc_part: UserPromptPart = build_dynamic_context_part("car=朗逸")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="用户消息"),
                dc_part,
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 1
        assert result[0].content == "用户消息"
        assert DYNAMIC_CONTEXT_TAG not in result[0].content

    def test_invoked_skills_part_stripped_on_persist(self) -> None:
        part: UserPromptPart = build_invoked_skills_part("### Skill: commit")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="用户消息"),
                part,
            ]),
        ]

        result = from_model_messages(messages)

        assert result[0].content == "用户消息"
        assert INVOKED_SKILLS_TAG not in result[0].content

    def test_preserves_tool_results(self) -> None:
        dc_part: UserPromptPart = build_dynamic_context_part("session=xyz")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="search_shops",
                    content="找到 5 家店",
                    tool_call_id="call_123",
                ),
                dc_part,
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 1
        user_msg = result[0]
        assert len(user_msg.tool_results) == 1
        assert user_msg.tool_results[0].content == "找到 5 家店"
        assert DYNAMIC_CONTEXT_TAG not in user_msg.content

    def test_strip_in_multi_turn(self) -> None:
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="消息1"),
                build_dynamic_context_part("dynamic1"),
            ]),
            ModelResponse(parts=[TextPart(content="回复1")]),
            ModelRequest(parts=[
                UserPromptPart(content="消息2"),
                build_dynamic_context_part("dynamic2"),
                build_invoked_skills_part("inv"),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 3
        assert result[0].content == "消息1"
        assert result[1].content == "回复1"
        assert result[2].content == "消息2"
        for msg in result:
            assert DYNAMIC_CONTEXT_TAG not in msg.content
            assert INVOKED_SKILLS_TAG not in msg.content
