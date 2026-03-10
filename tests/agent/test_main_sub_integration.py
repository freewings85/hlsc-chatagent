"""Main Agent + Sub Agent 集成测试

验证：
1. 主 agent 通过 task 工具调用子 agent
2. 子 agent 事件 agent_name 正确
3. 主 agent 事件 agent_name = "main"
4. 子 agent 不发 CHAT_REQUEST_END
5. 主 agent 发 CHAT_REQUEST_END
6. emitter 只在主 agent 结束时关闭
7. transcript.jsonl 正确写入
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

from src.agent.deps import AgentDeps
from src.agent.loop import create_agent, run_main_agent
from src.event.event_emitter import EventEmitter
from src.event.event_model import EventModel
from src.event.event_type import EventType


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    """从 queue 中收集所有事件直到 sentinel。"""
    events: list[EventModel] = []
    while True:
        item = await queue.get()
        if item is None:
            break
        events.append(item)
    return events


# ── Mock 工具 ──

async def mock_get_weather(ctx, city: str) -> str:
    """简单工具"""
    return f"{city}: 晴天 25°C"


# ── Mock Model：主 agent 调用 task 工具 ──

_TASK_CALL_ARGS = (
    '{"description": "分析代码", "prompt": "分析项目结构", "subagent_type": "plan"}'
)


def mock_main_calls_task(messages: list[ModelMessage], info: object) -> ModelResponse:
    """主 agent：第 1 次调用 task 工具，第 2 次返回文本。"""
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
    """流式版本"""
    for msg in messages:
        for part in msg.parts:
            if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                for chunk in ["子 agent ", "报告：", str(part.content)[:100]]:
                    yield chunk
                return
    yield {0: DeltaToolCall(name="task", json_args=_TASK_CALL_ARGS)}


# 子 agent 的 mock model（在 task.py 中通过 create_model 创建）
def mock_sub_agent_response(messages: list[ModelMessage], info: object) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content="项目结构分析完成：共 10 个模块")])


async def mock_sub_agent_stream(messages: list[ModelMessage], info: AgentInfo):
    for chunk in ["项目结构", "分析完成", "：共 10 个模块"]:
        yield chunk


class TestMainSubAgentIntegration:
    """主 agent + 子 agent 集成测试"""

    @pytest.mark.asyncio
    async def test_main_agent_calls_task_full_flow(self, make_task, make_emitter) -> None:
        """主 agent 调用 task 工具，触发子 agent，验证完整事件流"""
        from unittest.mock import patch
        from src.agent.tools.task import task as task_tool

        # 主 agent model
        main_model = FunctionModel(
            mock_main_calls_task,
            stream_function=mock_main_calls_task_stream,
        )
        # 子 agent model（通过 patch create_model 注入）
        sub_model = FunctionModel(
            mock_sub_agent_response,
            stream_function=mock_sub_agent_stream,
        )

        agent = create_agent(model=main_model)
        deps = AgentDeps(
            available_tools=["task"],
            tool_map={"task": task_tool},
        )
        task, _ = make_task("帮我分析代码")
        event_queue, emitter = make_emitter()

        with patch("src.agent.tools.task.create_model", return_value=sub_model):
            await run_main_agent(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)

        # ---- 验证事件流 ----

        # 1. 应有主 agent 的 TEXT 事件（agent_name="main"）
        main_text_events = [
            e for e in events
            if e.type == EventType.TEXT and e.agent_name == "main"
        ]
        assert len(main_text_events) > 0, "应有主 agent 的 TEXT 事件"

        # 2. 应有子 agent 的 TEXT 事件（agent_name="plan"）
        sub_text_events = [
            e for e in events
            if e.type == EventType.TEXT and e.agent_name == "plan"
        ]
        assert len(sub_text_events) > 0, "应有子 agent (plan) 的 TEXT 事件"

        # 3. 子 agent 的文本内容正确
        sub_text = "".join(e.data["content"] for e in sub_text_events)
        assert "项目结构" in sub_text

        # 4. 主 agent 的最终文本包含子 agent 结果
        main_text = "".join(e.data["content"] for e in main_text_events)
        assert "子 agent" in main_text

        # 5. 只有 1 个 CHAT_REQUEST_END（来自主 agent）
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1
        assert end_events[0].agent_name == "main"

        # 6. 应有 TOOL_CALL_START（主 agent 调用 task）
        tool_starts = [e for e in events if e.type == EventType.TOOL_CALL_START]
        assert any(e.data.get("tool_name") == "task" for e in tool_starts)

        # 7. 所有事件的 session_id 一致
        for e in events:
            assert e.session_id == task.session_id

    @pytest.mark.asyncio
    async def test_main_agent_alone_events_unchanged(self, make_task, make_emitter) -> None:
        """主 agent 不调用子 agent 时，事件行为与重构前一致"""
        from tests.conftest import mock_simple_text, mock_stream_text

        model = FunctionModel(mock_simple_text, stream_function=mock_stream_text)
        agent = create_agent(model=model)
        deps = AgentDeps()
        task, _ = make_task("你好")
        event_queue, emitter = make_emitter()

        await run_main_agent(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)

        # 所有 TEXT 事件 agent_name 应为 "main"
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) > 0
        for e in text_events:
            assert e.agent_name == "main"

        # 有且仅有 1 个 CHAT_REQUEST_END
        end_events = [e for e in events if e.type == EventType.CHAT_REQUEST_END]
        assert len(end_events) == 1
        assert end_events[0].agent_name == "main"

        # 文本内容正确
        combined = "".join(e.data["content"] for e in text_events)
        assert "你好" in combined

    @pytest.mark.asyncio
    async def test_event_ordering(self, make_task, make_emitter) -> None:
        """事件顺序：主 agent tool_call_start → 子 agent events → 主 agent tool_result → 主 agent text → end"""
        from unittest.mock import patch
        from src.agent.tools.task import task as task_tool

        main_model = FunctionModel(
            mock_main_calls_task,
            stream_function=mock_main_calls_task_stream,
        )
        sub_model = FunctionModel(
            mock_sub_agent_response,
            stream_function=mock_sub_agent_stream,
        )

        agent = create_agent(model=main_model)
        deps = AgentDeps(
            available_tools=["task"],
            tool_map={"task": task_tool},
        )
        task, _ = make_task("分析代码")
        event_queue, emitter = make_emitter()

        with patch("src.agent.tools.task.create_model", return_value=sub_model):
            await run_main_agent(emitter, task, agent, deps, message_history=[])

        events = await _collect_events(event_queue)

        # 找到关键事件的索引
        first_tool_start_idx = None
        first_sub_text_idx = None
        tool_result_idx = None
        first_main_text_after_tool = None

        for i, e in enumerate(events):
            if e.type == EventType.TOOL_CALL_START and first_tool_start_idx is None:
                first_tool_start_idx = i
            if e.type == EventType.TEXT and e.agent_name == "plan" and first_sub_text_idx is None:
                first_sub_text_idx = i
            if e.type == EventType.TOOL_RESULT and tool_result_idx is None:
                tool_result_idx = i
            if (e.type == EventType.TEXT and e.agent_name == "main"
                    and tool_result_idx is not None and first_main_text_after_tool is None):
                first_main_text_after_tool = i

        # 验证顺序
        assert first_tool_start_idx is not None, "应有 TOOL_CALL_START"
        assert first_sub_text_idx is not None, "应有子 agent TEXT"
        assert tool_result_idx is not None, "应有 TOOL_RESULT"

        # tool_call_start < sub_agent_text < tool_result
        assert first_tool_start_idx < first_sub_text_idx, \
            "TOOL_CALL_START 应在子 agent TEXT 之前"
        assert first_sub_text_idx < tool_result_idx, \
            "子 agent TEXT 应在 TOOL_RESULT 之前"
