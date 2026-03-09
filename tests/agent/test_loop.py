"""Agent Loop 测试"""

import asyncio

import pytest
from pydantic_ai.models.function import FunctionModel

from src.agent.deps import AgentDeps
from src.agent.loop import create_agent, run_agent_loop
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel
from src.event.event_type import EventType
from tests.conftest import (
    mock_get_weather,
    mock_simple_text,
    mock_stream_text,
    mock_stream_weather_then_answer,
    mock_weather_then_answer,
)


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    """从 queue 中收集所有事件直到 sentinel。"""
    events: list[EventModel] = []
    while True:
        item = await queue.get()
        if item is None:
            break
        events.append(item)
    return events


class TestAgentLoop:

    @pytest.mark.asyncio
    async def test_simple_text_response(self, make_task, make_emitter) -> None:
        """无 tool call，直接返回文本"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)
        # 应该有 TEXT 事件 + CHAT_REQUEST_END
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) > 0
        combined = "".join(e.data["content"] for e in text_events)
        assert "你好" in combined

        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, make_task, make_emitter) -> None:
        """tool call 流程：LLM → tool → LLM，验证事件完整"""
        model = FunctionModel(
            mock_weather_then_answer,
            stream_function=mock_stream_weather_then_answer,
        )
        agent = create_agent(model=model)
        deps = AgentDeps(
            available_tools=["get_weather"],
            tool_map={"get_weather": mock_get_weather},
        )
        task, _ = make_task("上海天气")
        event_queue, emitter = make_emitter()

        # 传入空历史，避免残留数据干扰 mock 函数的分支判断
        await run_agent_loop(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)
        event_types = [e.type for e in events]

        # 应该有 tool_call_start 和 tool_result 事件
        assert EventType.TOOL_RESULT in event_types

        # 最后应该有文本和结束事件
        assert EventType.TEXT in event_types
        assert EventType.CHAT_REQUEST_END in event_types

        # 验证 tool_result 包含正确数据
        tool_results = [e for e in events if e.type == EventType.TOOL_RESULT]
        assert any("晴天" in e.data.get("result", "") for e in tool_results)

    @pytest.mark.asyncio
    async def test_cancelled_task_stops_loop(self, make_task, make_emitter) -> None:
        """取消的任务应该提前退出"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        task.cancelled = True

        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps, message_history=[])

        # 只有结束事件和 sentinel
        events = await _collect_events(event_queue)
        # 取消时不应有 TEXT 事件（第一个 node 就被跳过）
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) == 0

    @pytest.mark.asyncio
    async def test_emitter_closed_on_normal_path(self, make_task, make_emitter) -> None:
        """正常路径 emitter 总是关闭"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps, message_history=[])

        # queue 中应该有事件（TEXT + END）+ sentinel(None)
        assert not event_queue.empty()

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self, make_task, make_emitter) -> None:
        """max_iterations 限制循环次数"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        # max_iterations=1 会在第一个迭代后退出
        await run_agent_loop(emitter, task, agent, deps, message_history=[], max_iterations=1)

        events = await _collect_events(event_queue)
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1

    @pytest.mark.asyncio
    async def test_exception_still_closes_emitter(self, make_task, make_emitter) -> None:
        """异常时 emitter 仍然关闭"""
        # 用一个会抛异常的 stream function
        async def bad_stream(messages, info):
            raise RuntimeError("test error")
            yield "never"  # type: ignore[misc]  # noqa: E501

        model = FunctionModel(stream_function=bad_stream)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        with pytest.raises(RuntimeError, match="test error"):
            await run_agent_loop(emitter, task, agent, deps, message_history=[])

        # 异常时先发 ERROR 事件，再发 CHAT_REQUEST_END，最后关闭 emitter（sentinel=None）
        error_event = await event_queue.get()
        assert error_event is not None
        assert error_event.type == EventType.ERROR
        assert "test error" in error_event.data["message"]
        end_event = await event_queue.get()
        assert end_event is not None
        assert end_event.type == EventType.CHAT_REQUEST_END
        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_load_history_from_backend(self, make_task, make_emitter) -> None:
        """message_history=None 时从后端加载"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        # 不传 message_history，让 loop 从后端加载（空的）
        await run_agent_loop(emitter, task, agent, deps, message_history=None)

        events = await _collect_events(event_queue)
        assert any(e.type == EventType.TEXT for e in events)

    @pytest.mark.asyncio
    async def test_events_have_correct_ids(self, make_task, make_emitter) -> None:
        """事件携带正确的 session_id 和 request_id"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好", session_id="sid-123")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)
        for event in events:
            assert event.conversation_id == "sid-123"
            assert event.request_id == task.request_id


class TestAgentLoopEdgeCases:
    """US-001: agent loop 异常恢复与边界条件"""

    @pytest.mark.asyncio
    async def test_empty_text_response_emitter_closes(self, make_task, make_emitter) -> None:
        """LLM 返回空文本时 pydantic-ai 抛异常，emitter 仍然关闭"""
        from pydantic_ai.messages import ModelResponse, TextPart

        def empty_response(messages, info):
            return ModelResponse(parts=[TextPart(content="")])

        async def empty_stream(messages, info):
            yield ""  # 空字符串，pydantic-ai 会拒绝并抛 UnexpectedModelBehavior

        model = FunctionModel(empty_response, stream_function=empty_stream)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        from pydantic_ai.exceptions import UnexpectedModelBehavior
        with pytest.raises(UnexpectedModelBehavior):
            await run_agent_loop(emitter, task, agent, deps, message_history=[])

        # 异常时先发 ERROR 事件，再发 CHAT_REQUEST_END，最后关闭 emitter（sentinel=None）
        error_event = await event_queue.get()
        assert error_event is not None
        assert error_event.type == EventType.ERROR
        end_event = await event_queue.get()
        assert end_event is not None
        assert end_event.type == EventType.CHAT_REQUEST_END
        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_tool_exception_emitter_still_closes(self, make_task, make_emitter) -> None:
        """工具执行抛异常时 emitter 仍能正常关闭"""
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        def tool_call_response(messages, info):
            return ModelResponse(parts=[ToolCallPart(
                tool_name="bad_tool", args={"x": 1},
            )])

        async def tool_call_stream(messages, info):
            yield {0: DeltaToolCall(name="bad_tool", json_args='{"x": 1}')}

        from pydantic_ai.models.function import DeltaToolCall

        async def bad_tool_fn(ctx, x: int) -> str:
            raise ValueError("tool exploded")

        model = FunctionModel(tool_call_response, stream_function=tool_call_stream)
        agent = create_agent(model=model)
        deps = AgentDeps(
            available_tools=["bad_tool"],
            tool_map={"bad_tool": bad_tool_fn},
        )
        task, _ = make_task("test")
        event_queue, emitter = make_emitter()

        # 工具异常被 pydantic-ai 内部捕获，不会向上抛出
        # 但 emitter 最终应关闭
        await run_agent_loop(emitter, task, agent, deps, message_history=[], max_iterations=2)

        # emitter 应该已关闭（sentinel 在 queue 中）
        events = await _collect_events(event_queue)
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1

    @pytest.mark.asyncio
    async def test_max_iterations_zero_immediate_end(self, make_task, make_emitter) -> None:
        """max_iterations=0 时立即结束，发送 CHAT_REQUEST_END"""
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps, message_history=[], max_iterations=0)

        events = await _collect_events(event_queue)
        # 不应有 TEXT 事件
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) == 0
        # 应有 CHAT_REQUEST_END
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1


class TestFormatMessagesForSummary:
    """_format_messages_for_summary 辅助函数测试"""

    def test_formats_user_and_assistant_messages(self) -> None:
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

        from src.agent.loop import _format_messages_for_summary

        messages = [
            ModelRequest(parts=[UserPromptPart(content="用户问题")]),
            ModelResponse(parts=[TextPart(content="助手回答")]),
        ]
        result = _format_messages_for_summary(messages)
        assert "用户: 用户问题" in result
        assert "助手: 助手回答" in result

    def test_truncates_long_content(self) -> None:
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        from src.agent.loop import _format_messages_for_summary

        long_content = "x" * 1000
        messages = [ModelRequest(parts=[UserPromptPart(content=long_content)])]
        result = _format_messages_for_summary(messages)
        assert len(result) <= 600  # 截断到 500 + "用户: " 前缀

    def test_skips_non_text_parts(self) -> None:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        from src.agent.loop import _format_messages_for_summary

        messages = [
            ModelRequest(parts=[ToolReturnPart(tool_name="r", content="result", tool_call_id="c1")])
        ]
        result = _format_messages_for_summary(messages)
        assert result == ""  # ToolReturnPart 不被处理

    def test_empty_messages_returns_empty_string(self) -> None:
        from src.agent.loop import _format_messages_for_summary

        result = _format_messages_for_summary([])
        assert result == ""


class TestCompactBlockIntegration:
    """US-008: loop.py compact block（line 235）集成测试"""

    @pytest.mark.asyncio
    async def test_compact_block_triggered_in_loop(self, make_task, make_emitter) -> None:
        """microcompact 触发时 compact block 执行（移除 # pragma: no cover 后覆盖此路径）"""
        from unittest.mock import patch

        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        from src.agent.compact.config import CompactConfig
        from src.agent.deps import AgentDeps

        # 大 tool result 消息（两条各 5000 字符 ≈ 2500 tokens）
        big_content = "x" * 5000
        tool_msg1 = ModelRequest(
            parts=[ToolReturnPart(tool_name="read", content=big_content, tool_call_id="c1")]
        )
        tool_msg2 = ModelRequest(
            parts=[ToolReturnPart(tool_name="read", content=big_content, tool_call_id="c2")]
        )
        message_history = [tool_msg1, tool_msg2]

        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)

        # microcompact_threshold = 1900 - 1 = 1899；2500 tokens > 1899 → 触发 microcompact
        small_config = CompactConfig(
            context_window=2000,
            output_reserve=100,
            auto_compact_enabled=True,
            microcompact_enabled=True,
            keep_recent_tool_results=1,
            min_savings_threshold=1,
        )

        # 使用独立 user/session 避免干扰其他测试的后端数据
        task, _ = make_task("继续对话", user_id="compact-test-user", session_id="compact-test-session")
        event_queue, emitter = make_emitter()
        deps = AgentDeps()

        with patch("src.agent.loop.get_compact_config", return_value=small_config):
            await run_agent_loop(emitter, task, agent, deps, message_history=message_history)

        events = await _collect_events(event_queue)
        # compact 后 loop 仍然正常完成
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1


class TestMakeSummarizeFn:
    """US-009: _make_summarize_fn 内部函数测试（移除 # pragma: no cover）"""

    @pytest.mark.asyncio
    async def test_summarize_fn_returns_str(self) -> None:
        """_make_summarize_fn 返回的闭包调用时通过 agent.run() 生成摘要字符串"""
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        from src.agent.loop import _make_summarize_fn

        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        # 使用不带 DynamicToolset 的 Agent，因为 _make_summarize_fn 内部调 agent.run() 不传 deps
        agent: Agent[None, str] = Agent(model, system_prompt="你是助手")

        fn = _make_summarize_fn(agent)  # type: ignore[arg-type]
        messages = [ModelRequest(parts=[UserPromptPart(content="对话历史内容")])]

        result = await fn(messages)
        assert isinstance(result, str)
        assert len(result) > 0
