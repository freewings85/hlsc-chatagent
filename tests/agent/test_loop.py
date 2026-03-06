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
        agent = create_agent(model=model, system_prompt="你是助手")
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

        # emitter 应该在 finally 中关闭
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
