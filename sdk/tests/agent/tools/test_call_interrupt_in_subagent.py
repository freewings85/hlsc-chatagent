"""测试 call_interrupt 在 sub agent 中的完整流程。

验证：
1. sub agent tool 调用 call_interrupt → 触发 interrupt → 收到 resume → 继续执行
2. interrupt 事件的 session_id 与父 agent 一致
3. interrupt 事件包含 interrupt_key 和 question
4. sub agent 最终返回基于用户回复的结果
"""

import asyncio
import json

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from unittest.mock import MagicMock, patch

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.task import task
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


# ── 辅助函数 ────────────────────────────────────────────────────────────


# 模拟一个使用 call_interrupt 的 tool
async def mock_confirm_tool(ctx: RunContext[AgentDeps], question: str) -> str:
    """模拟需要用户确认的工具。"""
    reply = await call_interrupt(ctx, {
        "type": "confirm",
        "question": question,
    })
    return f"用户回复: {reply}"


def _make_parent_deps(
    session_id: str = "parent-session",
    emitter: EventEmitter | None = None,
    temporal_client: object | None = None,
) -> AgentDeps:
    """构建带 mock_confirm_tool 的父 deps。"""

    async def mock_read(ctx: RunContext[AgentDeps], path: str) -> str:
        return f"文件内容: {path}"

    tool_map = {
        "read": mock_read,
        "mock_confirm_tool": mock_confirm_tool,
        "task": task,
    }
    return AgentDeps(
        session_id=session_id,
        user_id="test-user",
        available_tools=list(tool_map.keys()),
        tool_map=tool_map,
        emitter=emitter,
        temporal_client=temporal_client,
    )


def _make_ctx(deps: AgentDeps) -> RunContext[AgentDeps]:
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    events: list[EventModel] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    return events


# ── 测试 ──────────────────────────────────────────────────────────────


class TestCallInterruptInSubAgent:
    """sub agent 中调用 call_interrupt 的完整流程"""

    @pytest.mark.asyncio
    async def test_subagent_memory_mode_interrupt(self) -> None:
        """sub agent 无 Temporal 时走内存模式 interrupt，
        后台 resume 后 tool 正常完成，LLM 收到结果后回复"""

        def model_fn(messages: list[ModelMessage], info: object) -> ModelResponse:
            for msg in messages:
                for part in msg.parts:
                    pk = getattr(part, "part_kind", "")
                    if pk == "tool-return":
                        return ModelResponse(parts=[TextPart(content=f"工具返回: {part.content}")])
            return ModelResponse(parts=[ToolCallPart(
                tool_name="mock_confirm_tool",
                args=json.dumps({"question": "确认操作？"}),
            )])

        async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
            for msg in messages:
                for part in msg.parts:
                    pk = getattr(part, "part_kind", "")
                    if pk == "tool-return":
                        yield f"工具返回: {part.content}"
                        return
            yield {0: DeltaToolCall(
                name="mock_confirm_tool",
                json_args=json.dumps({"question": "确认操作？"}),
            )}

        model = FunctionModel(model_fn, stream_function=stream_fn)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(
            session_id="sub-memory-mode",
            emitter=emitter,
            temporal_client=None,  # 触发内存模式
        )
        ctx = _make_ctx(deps)

        async def _auto_resume():
            """监听 interrupt 事件，自动 resume"""
            from agent_sdk._agent.interrupt import resume_memory
            for _ in range(100):
                while not queue.empty():
                    evt = queue.get_nowait()
                    if evt and evt.type == EventType.INTERRUPT:
                        key = evt.data.get("interrupt_key", "")
                        if key:
                            await resume_memory(key, {"reply": "自动确认"})
                            return
                await asyncio.sleep(0.05)

        with patch("agent_sdk._agent.tools.task.create_model", return_value=model):
            result, _ = await asyncio.gather(
                task(ctx, "测试", "调用确认工具", subagent_type="general"),
                _auto_resume(),
            )

        assert "用户回复: 自动确认" in result or "工具返回" in result

    @pytest.mark.asyncio
    async def test_subagent_with_temporal_mock(self) -> None:
        """sub agent 有 Temporal 时 call_interrupt 走 interrupt 路径（mock）"""

        captured_keys: list[str] = []

        async def mock_interrupt(client, key, callback, data, **kwargs):
            captured_keys.append(key)
            await callback(data, f"mock-id-{key}")
            return {"reply": "用户确认了"}

        def model_fn(messages: list[ModelMessage], info: object) -> ModelResponse:
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        return ModelResponse(parts=[TextPart(content=f"收到回复: {part.content}")])
            return ModelResponse(parts=[ToolCallPart(
                tool_name="mock_confirm_tool",
                args=json.dumps({"question": "选择方案"}),
            )])

        async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        yield f"收到回复: {part.content}"
                        return
            yield {0: DeltaToolCall(
                name="mock_confirm_tool",
                json_args=json.dumps({"question": "选择方案"}),
            )}

        model = FunctionModel(model_fn, stream_function=stream_fn)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(
            session_id="sub-temporal-test",
            emitter=emitter,
            temporal_client=MagicMock(),
        )
        ctx = _make_ctx(deps)

        with (
            patch("agent_sdk._agent.tools.task.create_model", return_value=model),
            patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt),
        ):
            result = await task(ctx, "选择测试", "让用户选择方案", subagent_type="general")

        assert "用户确认了" in result or "收到回复" in result

        assert len(captured_keys) >= 1
        assert "sub-temporal-test" in captured_keys[0]

        events = await _collect_events(queue)
        interrupt_events = [e for e in events if e.type == EventType.INTERRUPT]
        assert len(interrupt_events) >= 1
        ie = interrupt_events[0]
        assert ie.data["question"] == "选择方案"
        assert "interrupt_id" in ie.data
        assert "interrupt_key" in ie.data
        assert ie.session_id == "sub-temporal-test"

    @pytest.mark.asyncio
    async def test_subagent_multiple_interrupts(self) -> None:
        """sub agent 多次调用 call_interrupt，每次都能正确暂停和恢复"""

        ask_count = 0

        async def mock_interrupt(client, key, callback, data, **kwargs):
            nonlocal ask_count
            ask_count += 1
            await callback(data, f"id-{ask_count}")
            return {"reply": f"回答{ask_count}"}

        def model_fn(messages: list[ModelMessage], info: object) -> ModelResponse:
            returns = []
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        returns.append(part.content)

            if len(returns) >= 2:
                return ModelResponse(parts=[TextPart(content=f"完成：{', '.join(returns)}")])
            elif len(returns) == 1:
                return ModelResponse(parts=[ToolCallPart(
                    tool_name="mock_confirm_tool",
                    args=json.dumps({"question": "第二个问题"}),
                )])
            else:
                return ModelResponse(parts=[ToolCallPart(
                    tool_name="mock_confirm_tool",
                    args=json.dumps({"question": "第一个问题"}),
                )])

        async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
            returns = []
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        returns.append(part.content)

            if len(returns) >= 2:
                yield f"完成：{', '.join(returns)}"
            elif len(returns) == 1:
                yield {0: DeltaToolCall(
                    name="mock_confirm_tool",
                    json_args=json.dumps({"question": "第二个问题"}),
                )}
            else:
                yield {0: DeltaToolCall(
                    name="mock_confirm_tool",
                    json_args=json.dumps({"question": "第一个问题"}),
                )}

        model = FunctionModel(model_fn, stream_function=stream_fn)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(
            session_id="multi-ask-test",
            emitter=emitter,
            temporal_client=MagicMock(),
        )
        ctx = _make_ctx(deps)

        with (
            patch("agent_sdk._agent.tools.task.create_model", return_value=model),
            patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt),
        ):
            result = await task(ctx, "多次询问", "需要两次确认", subagent_type="general")

        assert ask_count == 2, f"应调用 2 次 call_interrupt，实际 {ask_count}"
        assert "回答1" in result
        assert "回答2" in result

        events = await _collect_events(queue)
        interrupt_events = [e for e in events if e.type == EventType.INTERRUPT]
        assert len(interrupt_events) == 2
        assert interrupt_events[0].data["question"] == "第一个问题"
        assert interrupt_events[1].data["question"] == "第二个问题"

    @pytest.mark.asyncio
    async def test_subagent_inherits_temporal_client(self) -> None:
        """sub agent 通过 task 工具继承父 deps 的 temporal_client"""

        temporal_mock = MagicMock()
        captured_client = None

        async def mock_interrupt(client, key, callback, data, **kwargs):
            nonlocal captured_client
            captured_client = client
            await callback(data, "id-1")
            return {"reply": "ok"}

        def model_fn(messages: list[ModelMessage], info: object) -> ModelResponse:
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        return ModelResponse(parts=[TextPart(content="done")])
            return ModelResponse(parts=[ToolCallPart(
                tool_name="mock_confirm_tool",
                args=json.dumps({"question": "确认？"}),
            )])

        async def stream_fn(messages: list[ModelMessage], info: AgentInfo):
            for msg in messages:
                for part in msg.parts:
                    if hasattr(part, "part_kind") and part.part_kind == "tool-return":
                        yield "done"
                        return
            yield {0: DeltaToolCall(
                name="mock_confirm_tool",
                json_args=json.dumps({"question": "确认？"}),
            )}

        model = FunctionModel(model_fn, stream_function=stream_fn)

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_parent_deps(
            emitter=emitter,
            temporal_client=temporal_mock,
        )
        ctx = _make_ctx(deps)

        with (
            patch("agent_sdk._agent.tools.task.create_model", return_value=model),
            patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt),
        ):
            await task(ctx, "继承测试", "确认", subagent_type="general")

        assert captured_client is temporal_mock
