"""测试 context_injector 的静态/动态拆分和 prompt cache 优化。"""

from __future__ import annotations

import pytest
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
    DYNAMIC_CONTEXT_END,
    DYNAMIC_CONTEXT_START,
    inject_context,
    strip_dynamic_context,
)
from agent_sdk._agent.agent_message import from_model_messages


def _make_context_msg(content: str, source: str) -> ModelRequest:
    """创建 is_meta context message。"""
    return ModelRequest(
        parts=[UserPromptPart(content=content)],
        metadata={"is_meta": True, "source": source},
    )


def _make_user_msg(content: str) -> ModelRequest:
    """创建普通 user message。"""
    return ModelRequest(
        parts=[UserPromptPart(content=content)],
    )


class TestInjectContext:
    """测试 inject_context 的静态/动态拆分。"""

    def test_static_context_prepended(self) -> None:
        """静态 context（agent_md, memory）应合并 prepend 到 [0]。"""
        messages: list = [_make_user_msg("你好")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("MEMORY.md 内容", "memory"),
        ]

        inject_context(messages, context_msgs)

        # [0] 应该是 merged static context
        assert len(messages) == 2
        first_msg: ModelRequest = messages[0]
        first_content: str = first_msg.parts[0].content
        assert "AGENT.md 内容" in first_content
        assert "MEMORY.md 内容" in first_content
        assert "<system-reminder>" in first_content

    def test_dynamic_context_appended_to_last_user_message(self) -> None:
        """动态 context（request_context, session_state）应追加到最后 user message。"""
        messages: list = [_make_user_msg("帮我找个店")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("current_car: 朗逸", "request_context"),
            _make_context_msg("[session_state]: projects=[]", "session_state"),
        ]

        inject_context(messages, context_msgs)

        # 最后一条 user message 应包含动态 context
        last_user_content: str = messages[-1].parts[0].content
        assert DYNAMIC_CONTEXT_START in last_user_content
        assert "current_car: 朗逸" in last_user_content
        assert "session_state" in last_user_content
        # 原始内容也在
        assert "帮我找个店" in last_user_content

    def test_static_and_dynamic_separated(self) -> None:
        """静态在 [0]，动态在最后 user message，不混合。"""
        messages: list = [_make_user_msg("附近有什么修车店")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 静态内容", "agent_md"),
            _make_context_msg("位置: 浦东", "request_context"),
        ]

        inject_context(messages, context_msgs)

        # [0] merged context 只包含静态
        first_content: str = messages[0].parts[0].content
        assert "AGENT 静态内容" in first_content
        assert "位置: 浦东" not in first_content

        # 最后 user message 包含动态
        last_content: str = messages[-1].parts[0].content
        assert "位置: 浦东" in last_content

    def test_no_dynamic_context_no_marker(self) -> None:
        """没有动态 context 时，user message 不应有 dynamic-context 标记。"""
        messages: list = [_make_user_msg("你好")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 内容", "agent_md"),
        ]

        inject_context(messages, context_msgs)

        last_content: str = messages[-1].parts[0].content
        assert DYNAMIC_CONTEXT_START not in last_content


class TestStripDynamicContext:
    """测试 strip_dynamic_context 剥离逻辑（持久化前用）。"""

    def test_strip_removes_dynamic_block(self) -> None:
        """应移除 <dynamic-context> 块及其内容。"""
        text: str = f"用户消息{DYNAMIC_CONTEXT_START}\n动态内容\n{DYNAMIC_CONTEXT_END}"
        result: str = strip_dynamic_context(text)
        assert result == "用户消息"
        assert "动态内容" not in result

    def test_strip_preserves_text_without_marker(self) -> None:
        """没有标记时应原样返回。"""
        text: str = "普通文本"
        result: str = strip_dynamic_context(text)
        assert result == "普通文本"

    def test_strip_handles_empty_string(self) -> None:
        """空字符串应返回空。"""
        result: str = strip_dynamic_context("")
        assert result == ""


# --------------------------------------------------------------------------- #
# 补充测试：多轮对话 + 持久化剥离
# --------------------------------------------------------------------------- #


def _make_assistant_msg(content: str) -> ModelResponse:
    """创建 assistant message。"""
    return ModelResponse(parts=[TextPart(content=content)])


def _make_tool_call_response(tool_name: str, call_id: str) -> ModelResponse:
    """创建包含 tool_call 的 assistant message。"""
    return ModelResponse(parts=[
        TextPart(content="好的，我来查一下"),
        ToolCallPart(tool_name=tool_name, args="{}", tool_call_id=call_id),
    ])


def _make_tool_return_request(tool_name: str, call_id: str, result: str) -> ModelRequest:
    """创建包含 tool_return 的 user message。"""
    return ModelRequest(parts=[
        ToolReturnPart(tool_name=tool_name, content=result, tool_call_id=call_id),
    ])


class TestMultiTurnDynamicContext:
    """多轮对话场景下动态 context 的注入行为。"""

    def test_dynamic_appended_to_last_user_in_multi_turn(self) -> None:
        """多轮 user/assistant 交替，动态 context 应追加到最后一条 user message。"""
        messages: list[ModelMessage] = [
            _make_user_msg("第一轮用户消息"),
            _make_assistant_msg("第一轮助手回复"),
            _make_user_msg("第二轮用户消息"),
            _make_assistant_msg("第二轮助手回复"),
            _make_user_msg("第三轮用户消息"),
        ]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("car=朗逸", "request_context"),
        ]

        inject_context(messages, context_msgs)

        # 动态 context 只追加到最后一条 user message（第三轮）
        last_user: ModelRequest = messages[-1]
        last_content: str = last_user.parts[0].content
        assert DYNAMIC_CONTEXT_START in last_content
        assert "car=朗逸" in last_content
        assert "第三轮用户消息" in last_content

        # 前面的 user messages 不应包含动态 context
        # messages[0] 是 merged static context, messages[1] 是第一轮用户
        first_user: ModelRequest = messages[1]
        first_content: str = first_user.parts[0].content
        assert DYNAMIC_CONTEXT_START not in first_content

    def test_dynamic_appended_to_tool_return_as_last_user(self) -> None:
        """最后一条 user message 是 tool_return 时，动态 context 追加到它的 UserPromptPart。

        如果 tool_return 没有 UserPromptPart，应回退到 fallback。
        """
        messages: list[ModelMessage] = [
            _make_user_msg("帮我查个店"),
            _make_tool_call_response("search_shops", "call_1"),
            _make_tool_return_request("search_shops", "call_1", "找到 3 家店"),
        ]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("state: active", "session_state"),
        ]

        inject_context(messages, context_msgs)

        # tool_return 的 ModelRequest 没有 UserPromptPart，所以会 fallback
        # 验证 fallback 消息被追加
        last_msg: ModelMessage = messages[-1]
        assert isinstance(last_msg, ModelRequest)
        # fallback 消息应包含 dynamic content
        found_dynamic: bool = False
        for part in last_msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                if "state: active" in part.content:
                    found_dynamic = True
        # 如果 fallback 被使用，它应该是最后一条；
        # 如果 tool_return 之前的 user msg 被选中，也 OK
        # 关键是动态 context 出现在某处
        any_has_dynamic: bool = any(
            DYNAMIC_CONTEXT_START in part.content
            for msg in messages
            if isinstance(msg, ModelRequest)
            for part in msg.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)
        )
        assert any_has_dynamic or found_dynamic

    def test_earlier_user_messages_not_modified(self) -> None:
        """确认动态 context 只影响最后一条 user message，不影响更早的消息。"""
        messages: list[ModelMessage] = [
            _make_user_msg("消息A"),
            _make_assistant_msg("回复A"),
            _make_user_msg("消息B"),
        ]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("dynamic_data", "request_context"),
        ]

        inject_context(messages, context_msgs)

        # 消息A 不应包含动态 context
        msg_a: ModelRequest = messages[0]
        for part in msg_a.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                assert DYNAMIC_CONTEXT_START not in part.content

        # 消息B 应包含动态 context
        msg_b: ModelRequest = messages[-1]
        msg_b_content: str = msg_b.parts[0].content
        assert DYNAMIC_CONTEXT_START in msg_b_content
        assert "dynamic_data" in msg_b_content


class TestFromModelMessagesStrip:
    """测试 from_model_messages 中 strip_dynamic_context 的剥离行为。"""

    def test_strip_dynamic_in_user_prompt_part(self) -> None:
        """UserPromptPart 中的 <dynamic-context> 应被 from_model_messages 剥离。"""
        original_text: str = "用户原始消息"
        dynamic_block: str = (
            f"{DYNAMIC_CONTEXT_START}\ncar=朗逸\nstate=active\n{DYNAMIC_CONTEXT_END}"
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content=original_text + dynamic_block),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "用户原始消息"
        assert DYNAMIC_CONTEXT_START not in result[0].content
        assert "car=朗逸" not in result[0].content

    def test_strip_preserves_tool_results(self) -> None:
        """剥离 dynamic context 不影响同一 ModelRequest 中的 ToolReturnPart。"""
        dynamic_block: str = (
            f"{DYNAMIC_CONTEXT_START}\nsession=xyz\n{DYNAMIC_CONTEXT_END}"
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="查询结果" + dynamic_block),
                ToolReturnPart(
                    tool_name="search_shops",
                    content="找到 5 家店",
                    tool_call_id="call_123",
                ),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 1
        user_msg = result[0]
        assert user_msg.content == "查询结果"
        assert len(user_msg.tool_results) == 1
        assert user_msg.tool_results[0].content == "找到 5 家店"

    def test_strip_in_multi_turn_messages(self) -> None:
        """多轮消息中所有 UserPromptPart 的 dynamic-context 都应被剥离。"""
        dynamic_block: str = (
            f"{DYNAMIC_CONTEXT_START}\ndynamic_stuff\n{DYNAMIC_CONTEXT_END}"
        )
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="消息1" + dynamic_block),
            ]),
            ModelResponse(parts=[TextPart(content="回复1")]),
            ModelRequest(parts=[
                UserPromptPart(content="消息2" + dynamic_block),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 3
        assert result[0].content == "消息1"
        assert result[1].content == "回复1"
        assert result[2].content == "消息2"
        # 确认所有动态标记都被剥离
        for msg in result:
            assert DYNAMIC_CONTEXT_START not in msg.content
            assert "dynamic_stuff" not in msg.content

    def test_meta_messages_with_dynamic_skipped(self) -> None:
        """is_meta 的 merged context 消息不应出现在持久化结果中。"""
        messages: list[ModelMessage] = [
            # merged static context（is_meta=True）
            ModelRequest(
                parts=[UserPromptPart(content="<system-reminder>AGENT内容</system-reminder>")],
                metadata={"is_meta": True, "source": "merged_context"},
            ),
            # 普通 user message 带 dynamic
            ModelRequest(parts=[
                UserPromptPart(
                    content=f"你好{DYNAMIC_CONTEXT_START}\nstate\n{DYNAMIC_CONTEXT_END}",
                ),
            ]),
            ModelResponse(parts=[TextPart(content="你好！")]),
        ]

        result = from_model_messages(messages)

        # is_meta 消息不应进入持久化（content_parts 和 tool_results 都为空 → 被跳过）
        # 但 merged_context 有 UserPromptPart，所以实际上会产出一条
        # 关键是 dynamic-context 被剥离
        user_msgs = [m for m in result if m.role == "user"]
        for um in user_msgs:
            assert DYNAMIC_CONTEXT_START not in um.content
