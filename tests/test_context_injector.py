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
    DYNAMIC_CONTEXT_TAG,
    build_dynamic_context_part,
    extract_dynamic_text,
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
    """测试 inject_context 的静态注入 + 动态清理。"""

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

    def test_dynamic_context_not_injected_by_inject_context(self) -> None:
        """动态 context 不由 inject_context 注入（由 loop 注入到 node.request）。"""
        messages: list = [_make_user_msg("帮我找个店")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("current_car: 朗逸", "request_context"),
            _make_context_msg("[session_state]: projects=[]", "session_state"),
        ]

        inject_context(messages, context_msgs)

        # 最后一条 user message 不应包含动态 context
        last_user_content: str = messages[-1].parts[0].content
        assert DYNAMIC_CONTEXT_TAG not in last_user_content
        assert "帮我找个店" in last_user_content

    def test_static_and_dynamic_separated(self) -> None:
        """静态在 [0]，动态不注入到消息中。"""
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

        # 最后 user message 不包含动态
        last_content: str = messages[-1].parts[0].content
        assert DYNAMIC_CONTEXT_TAG not in last_content

    def test_no_dynamic_context_no_marker(self) -> None:
        """没有动态 context 时，user message 不应有 dynamic-context 标记。"""
        messages: list = [_make_user_msg("你好")]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 内容", "agent_md"),
        ]

        inject_context(messages, context_msgs)

        last_content: str = messages[-1].parts[0].content
        assert DYNAMIC_CONTEXT_TAG not in last_content

    def test_old_dynamic_context_stripped_from_history(self) -> None:
        """inject_context 应清理历史消息上残留的旧 dynamic-context。"""
        old_dynamic: str = "\n<dynamic-context>\nold_stuff\n</dynamic-context>"
        messages: list[ModelMessage] = [
            _make_user_msg("旧消息" + old_dynamic),
            ModelResponse(parts=[TextPart(content="回复")]),
            _make_user_msg("新消息"),
        ]
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 内容", "agent_md"),
        ]

        inject_context(messages, context_msgs)

        # 旧消息上的 dynamic-context 应被清理
        old_msg: ModelRequest = messages[1]  # [0] is merged context
        old_content: str = old_msg.parts[0].content
        assert DYNAMIC_CONTEXT_TAG not in old_content
        assert "旧消息" in old_content

    def test_new_format_dynamic_context_stripped(self) -> None:
        """inject_context 应清理新格式的 dynamic-context（带 system-reminder 包裹）。"""
        new_dynamic: str = (
            "\n<system-reminder>\n<dynamic-context>\nnew_stuff\n</dynamic-context>\n</system-reminder>"
        )
        messages: list[ModelMessage] = [
            _make_user_msg("消息" + new_dynamic),
        ]

        inject_context(messages, [])

        content: str = messages[0].parts[0].content
        assert DYNAMIC_CONTEXT_TAG not in content
        assert "<system-reminder>" not in content
        assert "消息" in content


class TestExtractDynamicText:
    """测试 extract_dynamic_text 提取动态上下文文本。"""

    def test_extract_from_request_context(self) -> None:
        """从 request_context 消息中提取文本。"""
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("current_car: 朗逸", "request_context"),
        ]

        text: str = extract_dynamic_text(context_msgs)

        assert "current_car: 朗逸" in text
        assert "AGENT.md 内容" not in text  # 静态不提取

    def test_extract_multiple_dynamic(self) -> None:
        """多个动态消息合并提取。"""
        context_msgs: list[ModelRequest] = [
            _make_context_msg("car=朗逸", "request_context"),
            _make_context_msg("scene=guide", "session_state"),
        ]

        text: str = extract_dynamic_text(context_msgs)

        assert "car=朗逸" in text
        assert "scene=guide" in text

    def test_extract_empty_when_no_dynamic(self) -> None:
        """没有动态消息时返回空字符串。"""
        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT 内容", "agent_md"),
        ]

        text: str = extract_dynamic_text(context_msgs)
        assert text == ""


class TestBuildDynamicContextPart:
    """测试 build_dynamic_context_part 构建。"""

    def test_builds_user_prompt_part(self) -> None:
        """应返回包含 system-reminder + ## dynamic-context 的 UserPromptPart。"""
        part: UserPromptPart = build_dynamic_context_part("car=朗逸")

        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, str)
        assert "<system-reminder>" in part.content
        assert DYNAMIC_CONTEXT_TAG in part.content
        assert "car=朗逸" in part.content
        assert "</system-reminder>" in part.content

    def test_content_structure(self) -> None:
        """验证内容结构：<system-reminder> 包裹 ## dynamic-context。"""
        part: UserPromptPart = build_dynamic_context_part("test_content")
        content: str = part.content

        # system-reminder 在外层
        sr_start: int = content.index("<system-reminder>")
        sr_end: int = content.index("</system-reminder>")
        dc_start: int = content.index("## dynamic-context")

        assert sr_start < dc_start < sr_end
        assert "test_content" in content


class TestStripDynamicContext:
    """测试 strip_dynamic_context 剥离逻辑（持久化前用）。"""

    def test_strip_old_format(self) -> None:
        """应移除旧格式 <dynamic-context> 块及其内容。"""
        text: str = "用户消息\n<dynamic-context>\n动态内容\n</dynamic-context>"
        result: str = strip_dynamic_context(text)
        assert result == "用户消息"
        assert "动态内容" not in result

    def test_strip_new_format(self) -> None:
        """应移除新格式（system-reminder 包裹）的 <dynamic-context> 块。"""
        text: str = (
            "用户消息\n"
            "<system-reminder>\n<dynamic-context>\n动态内容\n</dynamic-context>\n</system-reminder>"
        )
        result: str = strip_dynamic_context(text)
        assert result == "用户消息"
        assert "动态内容" not in result
        assert "<system-reminder>" not in result

    def test_strip_standalone_new_format(self) -> None:
        """独立的新格式（整个内容都是 dynamic-context）应被完全移除。"""
        text: str = (
            "<system-reminder>\n<dynamic-context>\n动态内容\n</dynamic-context>\n</system-reminder>"
        )
        result: str = strip_dynamic_context(text)
        assert result == ""

    def test_strip_preserves_text_without_marker(self) -> None:
        """没有标记时应原样返回。"""
        result: str = strip_dynamic_context("普通文本")
        assert result == "普通文本"

    def test_strip_handles_empty_string(self) -> None:
        """空字符串应返回空。"""
        assert strip_dynamic_context("") == ""


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


class TestInjectContextCleanup:
    """测试 inject_context 对历史消息中旧 dynamic-context 的清理。"""

    def test_old_dynamic_context_cleaned_on_new_turn(self) -> None:
        """模拟多轮对话：上一轮 user message 有 dynamic-context，inject 应清理掉。"""
        old_dynamic: str = (
            "\n<dynamic-context>\n"
            "[request_context]: current_car: (未设置)\n"
            "</dynamic-context>"
        )
        messages: list[ModelMessage] = [
            _make_user_msg("南翔医院附近有可以洗车的店吗" + old_dynamic),
            ModelResponse(parts=[
                ToolCallPart(
                    tool_name="search_shops",
                    args='{"location_text":"南翔医院"}',
                    tool_call_id="call_1",
                ),
            ]),
            ModelRequest(parts=[
                ToolReturnPart(
                    tool_name="search_shops",
                    content='{"total": 10}',
                    tool_call_id="call_1",
                ),
            ]),
            ModelResponse(parts=[TextPart(content="找到这些店…")]),
            _make_user_msg("附近有补胎的活动吗？"),
        ]

        context_msgs: list[ModelRequest] = [
            _make_context_msg("AGENT.md 内容", "agent_md"),
            _make_context_msg("car: 朗逸", "request_context"),
        ]

        inject_context(messages, context_msgs)

        # 旧 user message 上的 dynamic-context 应被清理
        # messages[0] 是 merged static context，messages[1] 是旧 user message
        old_user_msg: ModelRequest = messages[1]
        old_content: str = old_user_msg.parts[0].content  # type: ignore[union-attr]
        assert DYNAMIC_CONTEXT_TAG not in old_content
        assert "南翔医院" in old_content

        # 新 user message 也不应被 inject_context 注入（由 loop 负责）
        new_user_msg: ModelRequest = messages[-1]
        new_content: str = new_user_msg.parts[0].content  # type: ignore[union-attr]
        assert DYNAMIC_CONTEXT_TAG not in new_content
        assert "附近有补胎的活动吗？" in new_content

    def test_new_format_dynamic_context_cleaned(self) -> None:
        """新格式（system-reminder 包裹）的 dynamic-context 也应被清理。"""
        dc_part: UserPromptPart = build_dynamic_context_part("car=朗逸, scene=guide")
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="用户消息"),
                dc_part,  # 上一轮 loop 注入的 dynamic-context part
            ]),
            ModelResponse(parts=[TextPart(content="回复")]),
            _make_user_msg("新消息"),
        ]

        inject_context(messages, [])

        # 旧的 dynamic-context part 内容应被清理（变为空字符串）
        first_msg: ModelRequest = messages[0]
        for part in first_msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                assert DYNAMIC_CONTEXT_TAG not in part.content


class TestFromModelMessagesStrip:
    """测试 from_model_messages 中 strip_dynamic_context 的剥离行为。"""

    def test_strip_old_format_in_user_prompt_part(self) -> None:
        """UserPromptPart 中旧格式 <dynamic-context> 应被剥离。"""
        original_text: str = "用户原始消息"
        dynamic_block: str = "\n<dynamic-context>\ncar=朗逸\n</dynamic-context>"
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content=original_text + dynamic_block),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "用户原始消息"
        assert DYNAMIC_CONTEXT_TAG not in result[0].content

    def test_strip_new_format_standalone_part(self) -> None:
        """独立的 dynamic-context UserPromptPart（新格式）应被剥离为空。"""
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

    def test_strip_preserves_tool_results(self) -> None:
        """剥离 dynamic context 不影响同一 ModelRequest 中的 ToolReturnPart。"""
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

    def test_strip_in_multi_turn_messages(self) -> None:
        """多轮消息中所有 dynamic-context 都应被剥离。"""
        messages: list[ModelMessage] = [
            ModelRequest(parts=[
                UserPromptPart(content="消息1"),
                build_dynamic_context_part("dynamic1"),
            ]),
            ModelResponse(parts=[TextPart(content="回复1")]),
            ModelRequest(parts=[
                UserPromptPart(content="消息2"),
                build_dynamic_context_part("dynamic2"),
            ]),
        ]

        result = from_model_messages(messages)

        assert len(result) == 3
        assert result[0].content == "消息1"
        assert result[1].content == "回复1"
        assert result[2].content == "消息2"
        for msg in result:
            assert DYNAMIC_CONTEXT_TAG not in msg.content
