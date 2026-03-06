"""共享 fixtures 和 mock 工具"""

import asyncio

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.agent.deps import AgentDeps
from src.common.session_request_task import SessionRequestTask
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel


# ---- Mock Models ----

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
