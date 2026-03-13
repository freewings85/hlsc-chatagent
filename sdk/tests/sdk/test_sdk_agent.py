"""SDK Agent 集成测试：验证 Agent + AgentApp 基本流程"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk import Agent, StaticPromptLoader, ToolConfig
from agent_sdk.config import MemoryConfig, TranscriptConfig, CompactConfig


def _make_text_model(text: str) -> FunctionModel:
    """创建始终返回指定文本的 FunctionModel（支持流式）"""
    def handler(messages: list[Any], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=text)])

    async def stream_handler(messages: list[Any], info: AgentInfo):  # type: ignore[no-untyped-def]
        from pydantic_ai.models.function import DeltaToolCall, DeltaToolCalls
        yield text

    return FunctionModel(handler, stream_function=stream_handler)


class TestStaticPromptLoader:
    """StaticPromptLoader 单测"""

    @pytest.mark.asyncio
    async def test_load_returns_static_prompt(self) -> None:
        loader = StaticPromptLoader("你是测试 Agent")
        result = await loader.load(user_id="u1", session_id="s1")
        assert result.system_prompt == "你是测试 Agent"
        assert result.context_messages == []


class TestAgentInit:
    """Agent 初始化测试"""

    def test_init_with_dict_tools(self) -> None:
        """直接传 dict 工具"""
        async def dummy_tool(ctx: Any) -> str:
            return "ok"

        agent = Agent(
            prompt_loader=StaticPromptLoader("test"),
            tools={"dummy": dummy_tool},
        )
        available, tool_map = agent._build_tool_map()
        assert available == ["dummy"]
        assert "dummy" in tool_map

    def test_init_with_tool_config(self) -> None:
        """使用 ToolConfig"""
        async def tool_a(ctx: Any) -> str:
            return "a"

        async def tool_b(ctx: Any) -> str:
            return "b"

        agent = Agent(
            prompt_loader=StaticPromptLoader("test"),
            tools=ToolConfig(
                manual={"tool_a": tool_a, "tool_b": tool_b},
                include=["tool_a"],
            ),
        )
        available, tool_map = agent._build_tool_map()
        assert available == ["tool_a"]
        assert "tool_a" in tool_map
        assert "tool_b" in tool_map  # tool_map 有，但 available 只有 tool_a

    def test_init_with_model_instance(self) -> None:
        """直接传入 Model 实例"""
        model = _make_text_model("hello")
        agent = Agent(
            prompt_loader=StaticPromptLoader("test"),
            model=model,
        )
        built = agent._build_model()
        assert built is model

    def test_init_with_no_tools(self) -> None:
        """无工具"""
        agent = Agent(
            prompt_loader=StaticPromptLoader("test"),
        )
        available, tool_map = agent._build_tool_map()
        assert available == []
        assert tool_map == {}


class TestAgentRun:
    """Agent.run() 集成测试"""

    @pytest.mark.asyncio
    async def test_run_simple_text(self, tmp_path: Any) -> None:
        """最简流程：Agent 直接返回文本"""
        model = _make_text_model("你好，我是测试助手")
        data_dir = str(tmp_path / "data")

        agent = Agent(
            prompt_loader=StaticPromptLoader("你是一个测试助手"),
            model=model,
            memory_config=MemoryConfig(data_dir=data_dir),
            transcript_config=TranscriptConfig(data_dir=data_dir),
        )

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        result = await agent.run(
            "你好",
            user_id="test_user",
            session_id="test_session",
            emitter=emitter,
        )

        assert result is not None
        assert "测试助手" in result

        # 验证事件队列收到了事件
        events: list[EventModel] = []
        while not queue.empty():
            ev = queue.get_nowait()
            if ev is not None:
                events.append(ev)

        # 应该有 TEXT 事件和 CHAT_REQUEST_END 事件
        event_types = [e.type.value for e in events]
        assert "text" in event_types
        assert "chat_request_end" in event_types


class TestAgentAppInit:
    """AgentApp 初始化测试"""

    def test_creates_fastapi_app(self) -> None:
        """AgentApp 能创建 FastAPI 应用"""
        from agent_sdk import AgentApp, AgentAppConfig

        agent = Agent(
            prompt_loader=StaticPromptLoader("test"),
            model=_make_text_model("ok"),
        )
        app_config = AgentAppConfig(
            name="TestAgent",
            port=9999,
            temporal_enabled=False,
        )
        agent_app = AgentApp(agent, app_config)

        # 验证 FastAPI app 已创建
        assert agent_app.app is not None
        # 验证路由包含 /health
        routes = [r.path for r in agent_app.app.routes if hasattr(r, 'path')]
        assert "/health" in routes
