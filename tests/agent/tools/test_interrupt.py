"""interrupt 工具测试"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import RunContext

from src.agent.deps import AgentDeps
from src.agent.tools.interrupt import interrupt
from src.event.event_model import EventModel
from src.event.event_type import EventType


def make_ctx(emitter: AsyncMock | None = None) -> RunContext[AgentDeps]:
    deps = AgentDeps(emitter=emitter)  # type: ignore[arg-type]
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


class TestInterruptNoEmitter:
    async def test_returns_unavailable_when_no_emitter(self) -> None:
        ctx = make_ctx(emitter=None)
        result = await interrupt(ctx, "inquiry_confirm", '{"test": true}')
        assert "unavailable" in result

    async def test_no_exception_when_no_emitter(self) -> None:
        ctx = make_ctx(emitter=None)
        result = await interrupt(ctx, "test_type", "{}")
        assert isinstance(result, str)


class TestInterruptEmit:
    async def test_emits_interrupt_event(self) -> None:
        """正常调用时发出 INTERRUPT 事件"""
        emitter = AsyncMock()
        ctx = make_ctx(emitter=emitter)
        await interrupt(ctx, "inquiry_confirm", '{"project_ids": [10001]}')

        emitter.emit.assert_awaited_once()
        event: EventModel = emitter.emit.call_args[0][0]
        assert event.type == EventType.INTERRUPT
        assert event.data["type"] == "inquiry_confirm"
        assert event.data["project_ids"] == [10001]

    async def test_returns_confirmation_message(self) -> None:
        """返回值包含卡片类型"""
        emitter = AsyncMock()
        ctx = make_ctx(emitter=emitter)
        result = await interrupt(ctx, "inquiry_confirm", "{}")
        assert "inquiry_confirm" in result
        assert "卡片" in result

    async def test_invalid_json_data_handled(self) -> None:
        """非 JSON 的 data 参数不会抛异常"""
        emitter = AsyncMock()
        ctx = make_ctx(emitter=emitter)
        result = await interrupt(ctx, "test", "not valid json")

        emitter.emit.assert_awaited_once()
        event: EventModel = emitter.emit.call_args[0][0]
        assert event.data["raw"] == "not valid json"

    async def test_complex_data_preserved(self) -> None:
        """复杂 JSON 数据正确传递"""
        emitter = AsyncMock()
        ctx = make_ctx(emitter=emitter)
        data = json.dumps({
            "projects": [{"id": 1, "name": "刹车片"}],
            "car_model_name": "奔驰C级",
            "filters": {"distance_km": {"min": 0, "max": 30}},
        })
        await interrupt(ctx, "inquiry_confirm", data)

        event: EventModel = emitter.emit.call_args[0][0]
        assert event.data["type"] == "inquiry_confirm"
        assert event.data["projects"][0]["name"] == "刹车片"
        assert event.data["car_model_name"] == "奔驰C级"
