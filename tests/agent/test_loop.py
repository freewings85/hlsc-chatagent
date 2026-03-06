"""Agent Loop 测试"""

import asyncio

import pytest
from pydantic_ai.models.function import FunctionModel

from src.agent.deps import AgentDeps
from src.agent.loop import create_agent, run_agent_loop
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel
from tests.conftest import mock_simple_text, mock_weather_then_answer, mock_get_weather


class TestAgentLoop:

    @pytest.mark.asyncio
    async def test_simple_text_response(self, make_task, make_emitter) -> None:
        """无 tool call，直接返回文本"""
        model = FunctionModel(mock_simple_text)
        agent = create_agent(model=model, system_prompt="你是助手")
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps)

        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, make_task, make_emitter) -> None:
        """tool call 流程：LLM → tool → LLM"""
        model = FunctionModel(mock_weather_then_answer)
        agent = create_agent(model=model)
        deps = AgentDeps(
            available_tools=["get_weather"],
            tool_map={"get_weather": mock_get_weather},
        )
        task, _ = make_task("上海天气")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps)

        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_cancelled_task_stops_loop(self, make_task, make_emitter) -> None:
        """取消的任务应该提前退出"""
        model = FunctionModel(mock_simple_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        task.cancelled = True

        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps)

        sentinel = await event_queue.get()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_emitter_closed_on_normal_path(self, make_task, make_emitter) -> None:
        """正常路径 emitter 总是关闭"""
        model = FunctionModel(mock_simple_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_agent_loop(emitter, task, agent, deps)

        assert not event_queue.empty()
