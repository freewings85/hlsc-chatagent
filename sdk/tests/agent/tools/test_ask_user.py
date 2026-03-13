"""ask_user 工具测试"""

import asyncio

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from unittest.mock import MagicMock

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.ask_user import ask_user
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType


def _make_deps(
    session_id: str = "test-session",
    emitter: EventEmitter | None = None,
    temporal_client: object | None = None,
) -> AgentDeps:
    return AgentDeps(
        session_id=session_id,
        user_id="test-user",
        emitter=emitter,
        temporal_client=temporal_client,
    )


def _make_ctx(deps: AgentDeps) -> RunContext[AgentDeps]:
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx


class TestAskUserNoTemporal:
    """无 Temporal client 时抛 RuntimeError，由引擎层 wrap_tool_safe 捕获后返回给 LLM"""

    @pytest.mark.asyncio
    async def test_raises_runtime_error_without_temporal(self) -> None:
        deps = _make_deps(emitter=None, temporal_client=None)
        ctx = _make_ctx(deps)

        with pytest.raises(RuntimeError, match="Temporal"):
            await ask_user(ctx, "确认？")


class TestAskUserWithTemporal:
    """有 Temporal client 时通过 interrupt 机制暂停等待"""

    @pytest.mark.asyncio
    async def test_interrupt_emits_event_with_interrupt_id(self) -> None:
        """interrupt callback 应发出带 interrupt_id 的事件"""
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        # Mock interrupt 函数：捕获 callback 并执行它
        captured_callback = None
        captured_key = None

        async def mock_interrupt(client, key, callback, data, **kwargs):
            nonlocal captured_callback, captured_key
            captured_callback = callback
            captured_key = key
            # 执行 callback（模拟 Temporal 行为）
            await callback(data, "mock-interrupt-id-123")
            # 模拟用户回复
            return {"reply": "确认"}

        from unittest.mock import patch

        deps = _make_deps(
            session_id="sess-001",
            emitter=emitter,
            temporal_client=MagicMock(),  # non-None to trigger Temporal path
        )
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.ask_user._do_interrupt", side_effect=mock_interrupt):
            result = await ask_user(ctx, "确认订单？", type="confirm", data='{"amount": 100}')

        assert result == "确认"

        # 验证 interrupt 事件
        events = []
        while not queue.empty():
            e = queue.get_nowait()
            if e is not None:
                events.append(e)

        assert len(events) == 1
        evt = events[0]
        assert evt.type == EventType.INTERRUPT
        assert evt.data["question"] == "确认订单？"
        assert evt.data["interrupt_id"] == "mock-interrupt-id-123"
        assert evt.data["interrupt_key"] == captured_key
        assert evt.data["amount"] == 100
        assert evt.session_id == "sess-001"

    @pytest.mark.asyncio
    async def test_interrupt_returns_dict_reply_as_json(self) -> None:
        """用户回复是 dict 时返回 JSON 字符串"""
        async def mock_interrupt(client, key, callback, data, **kwargs):
            await callback(data, "id-1")
            return {"reply": {"choice": "A", "reason": "更好"}}

        from unittest.mock import patch

        deps = _make_deps(temporal_client=MagicMock())
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.ask_user._do_interrupt", side_effect=mock_interrupt):
            result = await ask_user(ctx, "选择方案")

        import json
        parsed = json.loads(result)
        assert parsed["choice"] == "A"

    @pytest.mark.asyncio
    async def test_interrupt_key_contains_session_id(self) -> None:
        """interrupt_key 应包含 session_id"""
        captured_keys = []

        async def mock_interrupt(client, key, callback, data, **kwargs):
            captured_keys.append(key)
            await callback(data, "id-1")
            return {"reply": "ok"}

        from unittest.mock import patch

        deps = _make_deps(session_id="my-session-123", temporal_client=MagicMock())
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.ask_user._do_interrupt", side_effect=mock_interrupt):
            await ask_user(ctx, "问题")

        assert len(captured_keys) == 1
        assert "my-session-123" in captured_keys[0]
