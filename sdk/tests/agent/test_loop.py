"""Agent Loop 测试（使用统一的 Agent.run() 入口）"""

import asyncio

import pytest
from pydantic_ai.models.function import FunctionModel

from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType
from tests.conftest import (
    make_test_agent,
    mock_get_weather,
    mock_simple_text,
    mock_stream_text,
    mock_stream_weather_then_answer,
    mock_weather_then_answer,
)


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    events: list[EventModel] = []
    while True:
        item = await queue.get()
        if item is None:
            break
        events.append(item)
    return events


class TestAgentLoop:

    @pytest.mark.asyncio
    async def test_simple_text_response(self, make_emitter) -> None:
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        await agent.run("你好", "test-user", "test-session", emitter, message_history=[])

        events = await _collect_events(event_queue)
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) > 0
        combined = "".join(e.data["content"] for e in text_events)
        assert "你好" in combined

        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, make_emitter) -> None:
        model = FunctionModel(
            mock_weather_then_answer,
            stream_function=mock_stream_weather_then_answer,
        )
        agent = make_test_agent(model, tools={"get_weather": mock_get_weather})
        event_queue, emitter = make_emitter()

        await agent.run("上海天气", "test-user", "test-session", emitter, message_history=[])

        events = await _collect_events(event_queue)
        event_types = [e.type for e in events]

        assert EventType.TOOL_RESULT in event_types
        assert EventType.TEXT in event_types
        assert EventType.CHAT_REQUEST_END in event_types

        tool_results = [e for e in events if e.type == EventType.TOOL_RESULT]
        assert any("晴天" in e.data.get("result", "") for e in tool_results)

    @pytest.mark.asyncio
    async def test_emitter_closed_on_normal_path(self, make_emitter) -> None:
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        await agent.run("你好", "test-user", "test-session", emitter, message_history=[])

        assert not event_queue.empty()

    @pytest.mark.asyncio
    async def test_exception_still_closes_emitter(self, make_emitter) -> None:
        async def bad_stream(messages, info):
            raise RuntimeError("test error")
            yield "never"  # type: ignore[misc]

        model = FunctionModel(stream_function=bad_stream)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        with pytest.raises(RuntimeError, match="test error"):
            await agent.run("你好", "test-user", "test-session", emitter, message_history=[])

        error_event = await event_queue.get()
        assert error_event is not None
        assert error_event.type == EventType.ERROR
        end_event = await event_queue.get()
        assert end_event is not None
        assert end_event.type == EventType.CHAT_REQUEST_END
        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_load_history_from_backend(self, make_emitter) -> None:
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        await agent.run("你好", "test-user", "test-session", emitter, message_history=None)

        events = await _collect_events(event_queue)
        assert any(e.type == EventType.TEXT for e in events)

    @pytest.mark.asyncio
    async def test_events_have_correct_ids(self, make_emitter) -> None:
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        await agent.run("你好", "test-user", "sid-123", emitter, message_history=[])

        events = await _collect_events(event_queue)
        for event in events:
            assert event.session_id == "sid-123"


class TestAgentLoopEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_text_response_emitter_closes(self, make_emitter) -> None:
        from pydantic_ai.messages import ModelResponse, TextPart

        def empty_response(messages, info):
            return ModelResponse(parts=[TextPart(content="")])

        async def empty_stream(messages, info):
            yield ""

        model = FunctionModel(empty_response, stream_function=empty_stream)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        from pydantic_ai.exceptions import UnexpectedModelBehavior
        with pytest.raises(UnexpectedModelBehavior):
            await agent.run("你好", "test-user", "test-session", emitter, message_history=[])

        error_event = await event_queue.get()
        assert error_event is not None
        assert error_event.type == EventType.ERROR
        end_event = await event_queue.get()
        assert end_event is not None
        assert end_event.type == EventType.CHAT_REQUEST_END
        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_tool_exception_emitter_still_closes(self, make_emitter) -> None:
        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.models.function import DeltaToolCall

        def tool_call_response(messages, info):
            return ModelResponse(parts=[ToolCallPart(
                tool_name="bad_tool", args={"x": 1},
            )])

        async def tool_call_stream(messages, info):
            yield {0: DeltaToolCall(name="bad_tool", json_args='{"x": 1}')}

        async def bad_tool_fn(ctx, x: int) -> str:
            raise ValueError("tool exploded")

        model = FunctionModel(tool_call_response, stream_function=tool_call_stream)
        agent = make_test_agent(model, tools={"bad_tool": bad_tool_fn})
        agent._max_iterations = 2
        event_queue, emitter = make_emitter()

        await agent.run("test", "test-user", "test-session", emitter, message_history=[])

        events = await _collect_events(event_queue)
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1


class TestFormatMessagesForSummary:

    def test_formats_user_and_assistant_messages(self) -> None:
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

        from agent_sdk._agent.loop import _format_messages_for_summary

        messages = [
            ModelRequest(parts=[UserPromptPart(content="用户问题")]),
            ModelResponse(parts=[TextPart(content="助手回答")]),
        ]
        result = _format_messages_for_summary(messages)
        assert "用户: 用户问题" in result
        assert "助手: 助手回答" in result

    def test_truncates_long_content(self) -> None:
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        from agent_sdk._agent.loop import _format_messages_for_summary

        long_content = "x" * 1000
        messages = [ModelRequest(parts=[UserPromptPart(content=long_content)])]
        result = _format_messages_for_summary(messages)
        assert len(result) <= 600

    def test_skips_non_text_parts(self) -> None:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        from agent_sdk._agent.loop import _format_messages_for_summary

        messages = [
            ModelRequest(parts=[ToolReturnPart(tool_name="r", content="result", tool_call_id="c1")])
        ]
        result = _format_messages_for_summary(messages)
        assert result == ""

    def test_empty_messages_returns_empty_string(self) -> None:
        from agent_sdk._agent.loop import _format_messages_for_summary

        result = _format_messages_for_summary([])
        assert result == ""


class TestMakeSummarizeFn:

    @pytest.mark.asyncio
    async def test_summarize_fn_returns_str(self) -> None:
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        from agent_sdk._agent.loop import _make_summarize_fn

        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent: Agent[None, str] = Agent(model, system_prompt="你是助手")

        fn = _make_summarize_fn(agent)  # type: ignore[arg-type]
        messages = [ModelRequest(parts=[UserPromptPart(content="对话历史内容")])]

        result = await fn(messages)
        assert isinstance(result, str)
        assert len(result) > 0
