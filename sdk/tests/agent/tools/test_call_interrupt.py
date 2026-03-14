"""call_interrupt 工具函数测试"""

import asyncio

import pytest
from pydantic_ai import RunContext
from unittest.mock import MagicMock

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
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


class TestCallInterruptMemoryMode:
    """无 Temporal client 时走内存模式"""

    @pytest.mark.asyncio
    async def test_memory_mode_works_without_temporal(self) -> None:
        """temporal_client=None 时使用内存模式，不抛异常"""
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        deps = _make_deps(emitter=emitter, temporal_client=None)
        ctx = _make_ctx(deps)

        async def _reply_later():
            """等 interrupt 事件发出后，调用 resume_memory 回复"""
            from agent_sdk._agent.interrupt import resume_memory
            # 等待 interrupt 事件
            for _ in range(50):
                if not queue.empty():
                    evt = queue.get_nowait()
                    if evt and evt.type == EventType.INTERRUPT:
                        key = evt.data["interrupt_key"]
                        await resume_memory(key, {"reply": "内存确认"})
                        return
                await asyncio.sleep(0.02)

        result, _ = await asyncio.gather(
            call_interrupt(ctx, {"type": "confirm", "question": "确认？"}),
            _reply_later(),
        )
        assert result == "内存确认"


class TestCallInterruptWithTemporal:
    """有 Temporal client 时通过 interrupt 机制暂停等待"""

    @pytest.mark.asyncio
    async def test_emits_event_with_interrupt_id(self) -> None:
        """interrupt callback 应发出带 interrupt_id 的事件"""
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        captured_key = None

        async def mock_interrupt(client, key, callback, data, **kwargs):
            nonlocal captured_key
            captured_key = key
            await callback(data, "mock-interrupt-id-123")
            return {"reply": "确认"}

        from unittest.mock import patch

        deps = _make_deps(
            session_id="sess-001",
            emitter=emitter,
            temporal_client=MagicMock(),
        )
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt):
            result = await call_interrupt(ctx, {
                "type": "confirm",
                "question": "确认订单？",
                "amount": 100,
            })

        assert result == "确认"

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
    async def test_returns_dict_reply_as_json(self) -> None:
        """用户回复是 dict 时返回 JSON 字符串"""
        async def mock_interrupt(client, key, callback, data, **kwargs):
            await callback(data, "id-1")
            return {"reply": {"choice": "A", "reason": "更好"}}

        from unittest.mock import patch

        deps = _make_deps(temporal_client=MagicMock())
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt):
            result = await call_interrupt(ctx, {"type": "select", "question": "选择方案"})

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

        with patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt):
            await call_interrupt(ctx, {"type": "confirm", "question": "问题"})

        assert len(captured_keys) == 1
        assert "my-session-123" in captured_keys[0]

    @pytest.mark.asyncio
    async def test_data_fields_passed_to_event(self) -> None:
        """data 中的自定义字段应原样传递到 INTERRUPT 事件"""
        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)

        async def mock_interrupt(client, key, callback, data, **kwargs):
            await callback(data, "id-1")
            return {"reply": "ok"}

        from unittest.mock import patch

        deps = _make_deps(emitter=emitter, temporal_client=MagicMock())
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt):
            await call_interrupt(ctx, {
                "type": "input",
                "question": "请输入车牌号",
                "placeholder": "沪A·12345",
                "validation": "plate_number",
            })

        events = []
        while not queue.empty():
            e = queue.get_nowait()
            if e is not None:
                events.append(e)

        assert len(events) == 1
        evt = events[0]
        assert evt.data["type"] == "input"
        assert evt.data["placeholder"] == "沪A·12345"
        assert evt.data["validation"] == "plate_number"

    @pytest.mark.asyncio
    async def test_no_emitter(self) -> None:
        """无 emitter 时也应正常工作（不发事件）"""
        async def mock_interrupt(client, key, callback, data, **kwargs):
            await callback(data, "id-1")
            return {"reply": "ok"}

        from unittest.mock import patch

        deps = _make_deps(emitter=None, temporal_client=MagicMock())
        ctx = _make_ctx(deps)

        with patch("agent_sdk._agent.tools.call_interrupt._do_interrupt", side_effect=mock_interrupt):
            result = await call_interrupt(ctx, {"type": "confirm", "question": "问题"})

        assert result == "ok"
