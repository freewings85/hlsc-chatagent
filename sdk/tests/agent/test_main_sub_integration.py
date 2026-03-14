"""Main Agent + Sub Agent 集成测试（使用统一的 Agent.run() 入口）

验证：
1. 主 agent 通过 task 工具调用子 agent
2. 子 agent 事件 agent_name 正确
3. 主 agent 发 CHAT_REQUEST_END
4. emitter 只在主 agent 结束时关闭
"""

import asyncio

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType
from tests.conftest import make_test_agent, mock_simple_text, mock_stream_text


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    events: list[EventModel] = []
    while True:
        item = await queue.get()
        if item is None:
            break
        events.append(item)
    return events


# ── Mock Model：主 agent 调用 task 工具 ──

_TASK_CALL_ARGS = (
    '{"description": "分析代码", "prompt": "分析项目结构", "subagent_type": "plan"}'
)


def mock_main_calls_task(messages: list[ModelMessage], info: object) -> ModelResponse:
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                return ModelResponse(parts=[TextPart(
                    content=f"子 agent 报告：{str(part.content)[:100]}"
                )])
    return ModelResponse(parts=[ToolCallPart(
        tool_name="task",
        args=_TASK_CALL_ARGS,
    )])


async def mock_main_calls_task_stream(
    messages: list[ModelMessage], info: AgentInfo,
):
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                for chunk in ["子 agent ", "报告：", str(part.content)[:100]]:
                    yield chunk
                return
    yield {0: DeltaToolCall(name="task", json_args=_TASK_CALL_ARGS)}


# 子 agent 的 mock model
def mock_sub_agent_response(messages: list[ModelMessage], info: object) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content="项目结构分析完成：共 10 个模块")])


async def mock_sub_agent_stream(messages: list[ModelMessage], info: AgentInfo):
    for chunk in ["项目结构", "分析完成", "：共 10 个模块"]:
        yield chunk


class TestMainSubAgentIntegration:

    @pytest.mark.asyncio
    async def test_main_agent_calls_task_full_flow(self, make_emitter) -> None:
        from unittest.mock import patch
        from agent_sdk._agent.tools.task import task as task_tool

        main_model = FunctionModel(
            mock_main_calls_task,
            stream_function=mock_main_calls_task_stream,
        )
        sub_model = FunctionModel(
            mock_sub_agent_response,
            stream_function=mock_sub_agent_stream,
        )

        agent = make_test_agent(main_model, tools={"task": task_tool})
        event_queue, emitter = make_emitter()

        with patch("agent_sdk._agent.tools.task.create_model", return_value=sub_model):
            await agent.run("帮我分析代码", "test-user", "test-session", emitter, message_history=[])

        events = await _collect_events(event_queue)

        # 1. 应有主 agent 的 TEXT 事件
        main_text_events = [
            e for e in events
            if e.type == EventType.TEXT and e.agent_name == "main"
        ]
        assert len(main_text_events) > 0

        # 2. 应有子 agent 的 TEXT 事件
        sub_text_events = [
            e for e in events
            if e.type == EventType.TEXT and e.agent_name == "plan"
        ]
        assert len(sub_text_events) > 0

        # 3. 子 agent 的文本内容正确
        sub_text = "".join(e.data["content"] for e in sub_text_events)
        assert "项目结构" in sub_text

        # 4. 只有 1 个 CHAT_REQUEST_END
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1

    @pytest.mark.asyncio
    async def test_main_agent_alone_events_unchanged(self, make_emitter) -> None:
        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = make_test_agent(model)
        event_queue, emitter = make_emitter()

        await agent.run("你好", "test-user", "test-session", emitter, message_history=[])

        events = await _collect_events(event_queue)

        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) > 0

        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1
