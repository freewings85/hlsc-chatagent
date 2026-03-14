"""共享 fixtures 和 mock 工具"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._common.session_request_task import SessionRequestTask
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel


# ---- Mock Models (non-streaming) ----

def mock_simple_text(messages: list[ModelMessage], info: object) -> ModelResponse:
    """直接返回文本"""
    return ModelResponse(parts=[TextPart(content="你好，我是助手")])


def mock_weather_then_answer(messages: list[ModelMessage], info: object) -> ModelResponse:
    """第1次返回 tool call，第2次返回文本"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                return ModelResponse(parts=[TextPart(content=f"天气结果：{part.content}")])
    return ModelResponse(parts=[ToolCallPart(tool_name="get_weather", args={"city": "上海"})])


# ---- Mock Stream Functions ----

async def mock_stream_text(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    """逐 token 流式返回文本"""
    for chunk in ["你好", "，", "我是", "助手"]:
        yield chunk


async def mock_stream_weather_then_answer(
    messages: list[ModelMessage], info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """流式版本：第1次返回 tool call delta，第2次返回文本"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                for chunk in ["天气", "结果：", part.content]:
                    yield chunk
                return
    yield {0: DeltaToolCall(name="get_weather", json_args='{"city": "上海"}')}


# ---- Mock Tools ----

async def mock_get_weather(ctx: RunContext[AgentDeps], city: str) -> str:
    """获取天气"""
    ctx.deps.tool_call_count += 1
    result: str = f"{city}: 晴天 25°C"
    ctx.deps.last_tool_result = result
    return result


# ---- Mock Sinker ----

class MockSinker:
    """收集事件的 mock sinker"""

    def __init__(self) -> None:
        self.events: list[EventModel] = []
        self.closed: bool = False

    async def send(self, event: EventModel) -> None:
        self.events.append(event)

    async def close(self) -> None:
        self.closed = True


# ---- Fixtures ----

@pytest.fixture
def make_task():
    """工厂 fixture：创建 task + sinker"""
    def _make(message: str = "你好", user_id: str = "test-user", session_id: str = "test-session"):
        sinker = MockSinker()
        task = SessionRequestTask(
            session_id=session_id,
            message=message,
            user_id=user_id,
            sinker=sinker,
        )
        return task, sinker
    return _make


@pytest.fixture
def make_emitter():
    """工厂 fixture：创建 event_queue + emitter"""
    def _make():
        event_queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(event_queue)
        return event_queue, emitter
    return _make


def make_test_agent(model: FunctionModel, tools: dict | None = None, agent_name: str = "main"):
    """创建用于测试的 SDK Agent（传入 FunctionModel + 可选工具）"""
    from agent_sdk import Agent, ToolConfig
    from agent_sdk.prompt_loader import StaticPromptLoader

    tool_config = ToolConfig(manual=tools) if tools else None
    return Agent(
        prompt_loader=StaticPromptLoader("You are a test assistant."),
        tools=tool_config,
        model=model,
        agent_name=agent_name,
    )
