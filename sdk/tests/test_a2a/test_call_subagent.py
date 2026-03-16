"""call_subagent 单元测试

测试 A2A 协议通信、事件转发、interrupt 中继的封装逻辑。
使用 respx mock HTTP 请求，不需要真实 subagent 服务。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import respx

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._event.event_emitter import EventEmitter
from agent_sdk._event.event_model import EventModel
from agent_sdk._event.event_type import EventType
from agent_sdk.a2a.call_subagent import (
    SubagentEvent,
    SubagentSession,
    _a2a_send,
    _agent_card_cache,
    _extract_text,
    _fetch_agent_name,
    call_subagent,
    call_subagent_session,
)


# ---- Helpers ----


def _make_ctx(
    emitter: EventEmitter | None = None,
    temporal_client: Any = None,
    session_id: str = "test-session",
) -> MagicMock:
    """创建模拟的 RunContext[AgentDeps]。"""
    deps = AgentDeps(
        session_id=session_id,
        user_id="test-user",
        emitter=emitter,
        temporal_client=temporal_client,
    )
    ctx = MagicMock()
    ctx.deps = deps
    ctx.tool_call_id = "tool-123"
    ctx.agent_path = "main"
    return ctx


def _a2a_response(
    state: str = "completed",
    text: str = "结果文本",
    task_id: str = "task-1",
    artifacts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 A2A JSON-RPC 响应。"""
    message: dict[str, Any] = {
        "parts": [{"kind": "text", "text": text}],
    }
    if metadata:
        message["metadata"] = metadata

    result: dict[str, Any] = {
        "id": task_id,
        "status": {
            "state": state,
            "message": message,
        },
    }
    if artifacts is not None:
        result["artifacts"] = artifacts
    else:
        result["artifacts"] = []
    return {"jsonrpc": "2.0", "id": "1", "result": result}


def _agent_card_response(name: str = "DemoPriceFinder") -> dict[str, Any]:
    return {"name": name, "description": "test", "url": "http://subagent:8101"}


async def _collect_events(queue: asyncio.Queue[EventModel | None]) -> list[EventModel]:
    """从队列收集所有事件。"""
    events: list[EventModel] = []
    while not queue.empty():
        ev = queue.get_nowait()
        if ev is not None:
            events.append(ev)
    return events


# ---- Tests: _extract_text ----


class TestExtractText:
    def test_string(self) -> None:
        assert _extract_text("hello") == "hello"

    def test_dict_with_parts(self) -> None:
        msg = {"parts": [{"kind": "text", "text": "foo"}, {"kind": "text", "text": "bar"}]}
        assert _extract_text(msg) == "foo\nbar"

    def test_dict_no_parts(self) -> None:
        msg = {"something": "else"}
        result = _extract_text(msg)
        assert "something" in result

    def test_other_type(self) -> None:
        assert _extract_text(123) == "123"


# ---- Tests: _fetch_agent_name ----


class TestFetchAgentName:
    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        _agent_card_cache.clear()

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_success(self) -> None:
        url = "http://subagent:8101"
        respx.get(f"{url}/.well-known/agent.json").respond(
            json=_agent_card_response("MyAgent"),
        )
        name = await _fetch_agent_name(url)
        assert name == "MyAgent"
        # 应该被缓存
        assert _agent_card_cache[url] == "MyAgent"

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_cached(self) -> None:
        url = "http://subagent:8101"
        _agent_card_cache[url] = "CachedAgent"
        # 不设置 respx mock — 如果发起请求会报错
        name = await _fetch_agent_name(url)
        assert name == "CachedAgent"

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_failure_fallback(self) -> None:
        url = "http://subagent:8101"
        respx.get(f"{url}/.well-known/agent.json").respond(status_code=500)
        name = await _fetch_agent_name(url)
        assert name == "subagent"


# ---- Tests: _a2a_send ----


class TestA2aSend:
    @respx.mock
    @pytest.mark.anyio
    async def test_send_success(self) -> None:
        url = "http://subagent:8101"
        expected_result = {"id": "task-1", "status": {"state": "completed"}}
        respx.post(f"{url}/a2a").respond(
            json={"jsonrpc": "2.0", "id": "1", "result": expected_result},
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            result = await _a2a_send(client, url, "ctx-1", "hello")
        assert result["id"] == "task-1"

    @respx.mock
    @pytest.mark.anyio
    async def test_send_with_task_id(self) -> None:
        url = "http://subagent:8101"
        respx.post(f"{url}/a2a").respond(
            json={"jsonrpc": "2.0", "id": "1", "result": {"id": "task-1"}},
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            result = await _a2a_send(client, url, "ctx-1", "reply", task_id="task-1")
        assert result["id"] == "task-1"
        # 验证请求包含 taskId
        req = respx.calls.last.request
        body = json.loads(req.content)
        assert body["params"]["message"]["taskId"] == "task-1"

    @respx.mock
    @pytest.mark.anyio
    async def test_send_a2a_error(self) -> None:
        url = "http://subagent:8101"
        respx.post(f"{url}/a2a").respond(
            json={"jsonrpc": "2.0", "id": "1", "error": {"code": -1, "message": "bad"}},
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            with pytest.raises(RuntimeError, match="A2A error"):
                await _a2a_send(client, url, "ctx-1", "hello")


# ---- Tests: call_subagent (one-line mode) ----


class TestCallSubagentOneLine:
    @respx.mock
    @pytest.mark.anyio
    async def test_completed(self) -> None:
        """subagent 直接完成，返回结果文本。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="最低价500元",
        ))

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        ctx = _make_ctx(emitter=emitter)

        result = await call_subagent(ctx, url=url, message="查刹车片价格")
        assert "500" in result

        events = await _collect_events(queue)
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) >= 1
        assert text_events[0].agent_path == "main|TestAgent"
        assert text_events[0].parent_tool_call_id == "tool-123"

    @respx.mock
    @pytest.mark.anyio
    async def test_failed(self) -> None:
        """subagent 失败，返回错误信息。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="failed", text="内部错误",
        ))

        ctx = _make_ctx()
        result = await call_subagent(ctx, url=url, message="query")
        assert "失败" in result
        assert "内部错误" in result

    @respx.mock
    @pytest.mark.anyio
    async def test_no_emitter(self) -> None:
        """无 emitter 时也应正常工作。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="ok",
        ))

        ctx = _make_ctx(emitter=None)
        result = await call_subagent(ctx, url=url, message="query")
        assert "ok" in result

    @respx.mock
    @pytest.mark.anyio
    async def test_artifacts_text(self) -> None:
        """A2A response 带 text artifact，应转发为 TEXT 事件。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        artifacts = [{
            "artifactId": "art-1",
            "parts": [{"kind": "text", "text": "artifact 文本"}],
        }]
        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="最终结果", artifacts=artifacts,
        ))

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        ctx = _make_ctx(emitter=emitter)

        result = await call_subagent(ctx, url=url, message="query")
        assert "artifact 文本" in result

        events = await _collect_events(queue)
        text_events = [e for e in events if e.type == EventType.TEXT]
        assert len(text_events) >= 1

    @respx.mock
    @pytest.mark.anyio
    async def test_artifacts_dedup(self) -> None:
        """同一 artifactId 不应重复发送。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        artifacts = [
            {"artifactId": "art-1", "parts": [{"kind": "text", "text": "dup"}]},
            {"artifactId": "art-1", "parts": [{"kind": "text", "text": "dup"}]},
        ]
        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="done", artifacts=artifacts,
        ))

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        ctx = _make_ctx(emitter=emitter)

        await call_subagent(ctx, url=url, message="query")
        events = await _collect_events(queue)
        text_events = [e for e in events if e.type == EventType.TEXT and e.data.get("content") == "dup"]
        assert len(text_events) == 1

    @respx.mock
    @pytest.mark.anyio
    async def test_artifacts_tool_events(self) -> None:
        """data artifacts 中的 tool_call_start / tool_result 应转为对应事件类型。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        artifacts = [{
            "artifactId": "art-2",
            "parts": [
                {"kind": "data", "data": {
                    "event_type": "tool_call_start",
                    "tool_name": "find_price",
                    "tool_call_id": "tc-1",
                }},
                {"kind": "data", "data": {
                    "event_type": "tool_result",
                    "tool_name": "find_price",
                    "tool_call_id": "tc-1",
                    "result": "500",
                }},
            ],
        }]
        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="done", artifacts=artifacts,
        ))

        queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
        emitter = EventEmitter(queue)
        ctx = _make_ctx(emitter=emitter)

        await call_subagent(ctx, url=url, message="query")
        events = await _collect_events(queue)

        tool_start = [e for e in events if e.type == EventType.TOOL_CALL_START]
        tool_result = [e for e in events if e.type == EventType.TOOL_RESULT]
        assert len(tool_start) == 1
        assert tool_start[0].data["tool_name"] == "find_price"
        assert len(tool_result) == 1


# ---- Tests: call_subagent (stream mode — async with / async for) ----


class TestCallSubagentStream:
    @respx.mock
    @pytest.mark.anyio
    async def test_stream_completed(self) -> None:
        """展开模式：subagent 直接完成。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="stream result",
        ))

        ctx = _make_ctx()
        async with call_subagent_session(ctx, url=url, message="q") as session:
            events_seen: list[SubagentEvent] = []
            async for event in session:
                events_seen.append(event)

        assert session.result
        assert "stream result" in session.result
        assert session.agent_name == "TestAgent"
        assert len(events_seen) == 1
        assert events_seen[0].state == "completed"

    @respx.mock
    @pytest.mark.anyio
    async def test_stream_empty_loop_is_correct(self) -> None:
        """展开模式：async for 循环体为空也是正确的。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="auto result",
        ))

        ctx = _make_ctx()
        async with call_subagent_session(ctx, url=url, message="q") as session:
            async for _event in session:
                pass  # 不写任何代码也是正确的

        assert "auto result" in session.result

    @respx.mock
    @pytest.mark.anyio
    async def test_stream_modify_question(self) -> None:
        """展开模式：开发者可修改 event.question。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        # 第一次返回 input-required，第二次返回 completed
        route = respx.post(f"{url}/a2a")
        route.side_effect = [
            httpx.Response(200, json=_a2a_response(
                state="input-required", text="确认吗？",
            )),
            httpx.Response(200, json=_a2a_response(
                state="completed", text="已确认",
            )),
        ]

        # Mock interrupt — 调用 callback 后返回 reply
        async def mock_interrupt_fn(
            client: Any, *, key: str, callback: Any, data: Any, task_queue: str = "",
        ) -> dict[str, Any]:
            await callback(data, "mock-id")
            return {"reply": "确认"}

        with patch("agent_sdk.a2a.call_subagent._do_interrupt", side_effect=mock_interrupt_fn):
            ctx = _make_ctx(temporal_client=MagicMock())
            async with call_subagent_session(ctx, url=url, message="q") as session:
                async for event in session:
                    if event.state == "input-required":
                        # 开发者修改 question（用于自定义 interrupt 文案）
                        event.question = f"[价格] {event.question}"

            assert "已确认" in session.result


# ---- Tests: interrupt relay ----


class TestInterruptRelay:
    @respx.mock
    @pytest.mark.anyio
    async def test_interrupt_relay(self) -> None:
        """input-required 状态时，应中继 interrupt 并用 reply 继续 A2A。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        route = respx.post(f"{url}/a2a")
        route.side_effect = [
            httpx.Response(200, json=_a2a_response(
                state="input-required", text="确认选择？",
            )),
            httpx.Response(200, json=_a2a_response(
                state="completed", text="已确认，500元",
            )),
        ]

        async def mock_interrupt_side_effect(
            client: Any, *, key: str, callback: Any, data: Any, task_queue: str = "",
        ) -> dict[str, Any]:
            # 模拟 Temporal interrupt：先调 callback（发事件），再返回 reply
            await callback(data, "mock-interrupt-id")
            return {"reply": "确认"}

        with patch("agent_sdk.a2a.call_subagent._do_interrupt", side_effect=mock_interrupt_side_effect):
            queue: asyncio.Queue[EventModel | None] = asyncio.Queue()
            emitter = EventEmitter(queue)
            ctx = _make_ctx(emitter=emitter, temporal_client=MagicMock())

            result = await call_subagent(ctx, url=url, message="查价格")

        assert "500" in result

        # 验证发了 INTERRUPT 事件
        events = await _collect_events(queue)
        interrupt_events = [e for e in events if e.type == EventType.INTERRUPT]
        assert len(interrupt_events) == 1
        assert interrupt_events[0].data["source"] == "TestAgent"
        assert interrupt_events[0].agent_path == "main|TestAgent"

        # 验证 A2A 被调用了两次（首次 + resume）
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.anyio
    async def test_multiple_interrupts(self) -> None:
        """多轮 interrupt 场景。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        route = respx.post(f"{url}/a2a")
        route.side_effect = [
            httpx.Response(200, json=_a2a_response(
                state="input-required", text="第一个问题？",
            )),
            httpx.Response(200, json=_a2a_response(
                state="input-required", text="第二个问题？",
            )),
            httpx.Response(200, json=_a2a_response(
                state="completed", text="全部完成",
            )),
        ]

        call_count = 0

        async def mock_interrupt_fn(
            client: Any, *, key: str, callback: Any, data: Any, task_queue: str = "",
        ) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            await callback(data, f"mock-interrupt-{call_count}")
            return {"reply": f"回复{call_count}"}

        with patch("agent_sdk.a2a.call_subagent._do_interrupt", side_effect=mock_interrupt_fn):
            ctx = _make_ctx(temporal_client=MagicMock())
            result = await call_subagent(ctx, url=url, message="query")

        assert "全部完成" in result
        assert call_count == 2
        assert route.call_count == 3


# ---- Tests: SubagentEvent / SubagentSession dataclasses ----


class TestDataclasses:
    def test_subagent_event_defaults(self) -> None:
        event = SubagentEvent(state="completed", task_id="t-1")
        assert event.question is None
        assert event.result_text is None
        assert event.artifacts == []
        assert event.raw == {}

    def test_subagent_event_with_values(self) -> None:
        event = SubagentEvent(
            state="input-required",
            task_id="t-1",
            question="确认？",
            artifacts=[{"id": "a1"}],
        )
        assert event.question == "确认？"
        assert len(event.artifacts) == 1


# ---- Tests: context 传递 ----


class TestContextPassing:
    @respx.mock
    @pytest.mark.anyio
    async def test_a2a_send_with_metadata(self) -> None:
        """_a2a_send 传入 metadata 时，请求体应包含 metadata 字段。"""
        url = "http://subagent:8101"
        respx.post(f"{url}/a2a").respond(
            json={"jsonrpc": "2.0", "id": "1", "result": {"id": "task-1"}},
        )
        metadata = {"request_context": {"vehicle_info": {"car_model_name": "宝马 325Li"}}}
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            await _a2a_send(client, url, "ctx-1", "推荐保养", metadata=metadata)

        req = respx.calls.last.request
        body = json.loads(req.content)
        msg = body["params"]["message"]
        assert msg["metadata"] == metadata

    @respx.mock
    @pytest.mark.anyio
    async def test_a2a_send_without_metadata(self) -> None:
        """_a2a_send 不传 metadata 时，请求体不应有 metadata 字段。"""
        url = "http://subagent:8101"
        respx.post(f"{url}/a2a").respond(
            json={"jsonrpc": "2.0", "id": "1", "result": {"id": "task-1"}},
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            await _a2a_send(client, url, "ctx-1", "hello")

        req = respx.calls.last.request
        body = json.loads(req.content)
        msg = body["params"]["message"]
        assert "metadata" not in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_call_subagent_passes_context_in_first_request(self) -> None:
        """call_subagent 传入 context 时，首次 A2A 请求应在 metadata 中携带 request_context。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "RecommendProject"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="推荐结果",
        ))

        ctx = _make_ctx()
        vehicle_context = {
            "vehicle_info": {
                "car_model_name": "宝马 325Li",
                "vin_code": "WBAJB1105MCJ12345",
                "mileage_km": 35000.0,
                "car_age_year": 2.5,
            },
        }
        result = await call_subagent(
            ctx, url=url, message="我的车该做什么保养", context=vehicle_context,
        )
        assert "推荐结果" in result

        # 验证 A2A 请求体中包含 context
        req = respx.calls.last.request
        body = json.loads(req.content)
        msg = body["params"]["message"]
        assert "metadata" in msg
        assert msg["metadata"]["request_context"] == vehicle_context

    @respx.mock
    @pytest.mark.anyio
    async def test_call_subagent_no_context(self) -> None:
        """call_subagent 不传 context 时，A2A 请求不应有 metadata。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "TestAgent"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="ok",
        ))

        ctx = _make_ctx()
        await call_subagent(ctx, url=url, message="query")

        req = respx.calls.last.request
        body = json.loads(req.content)
        msg = body["params"]["message"]
        assert "metadata" not in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_call_subagent_session_passes_context(self) -> None:
        """call_subagent_session 展开模式也应传递 context。"""
        url = "http://subagent:8101"
        _agent_card_cache[url] = "RecommendProject"

        respx.post(f"{url}/a2a").respond(json=_a2a_response(
            state="completed", text="推荐完成",
        ))

        ctx = _make_ctx()
        vehicle_context = {"vehicle_info": {"car_model_name": "大众 Polo"}}
        async with call_subagent_session(
            ctx, url=url, message="推荐保养", context=vehicle_context,
        ) as session:
            async for _event in session:
                pass

        assert "推荐完成" in session.result

        req = respx.calls.last.request
        body = json.loads(req.content)
        msg = body["params"]["message"]
        assert msg["metadata"]["request_context"] == vehicle_context
