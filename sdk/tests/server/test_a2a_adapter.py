"""A2A 适配层测试：验证 AgentCard 发现 + send/sendSubscribe 基本流程。"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_sdk._server.a2a_adapter import ChatAgentExecutor, _build_agent_card, mount_a2a


@pytest.fixture
def a2a_app():
    """创建带 A2A 端点的最小 FastAPI 应用。"""
    from fastapi import FastAPI

    app = FastAPI()
    mount_a2a(app, temporal_client_getter=lambda: None)
    return app


@pytest.fixture
async def client(a2a_app) -> AsyncClient:
    transport = ASGITransport(app=a2a_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAgentCard:
    """AgentCard 发现端点"""

    async def test_well_known_agent_json(self, client: AsyncClient) -> None:
        resp = await client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "ChatAgent"
        assert card["capabilities"]["streaming"] is True
        assert len(card["skills"]) >= 1

    def test_build_agent_card(self) -> None:
        card = _build_agent_card("http://example.com")
        assert card.url == "http://example.com"
        assert card.name == "ChatAgent"
        assert card.capabilities.streaming is True


class TestA2ABasicFlow:
    """A2A JSON-RPC 基本调用"""

    async def test_send_message(self, client: AsyncClient, monkeypatch) -> None:
        """验证 message/send 返回有效的 A2A 响应。"""
        # Mock agent loop 使其立即返回
        from agent_sdk._server import a2a_adapter

        async def _mock_execute(self, context, event_queue):
            from a2a.server.tasks import TaskUpdater
            from a2a.types import Part, TextPart

            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.start_work()
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text="Hello from mock agent"))]
            )
            await updater.complete(message=msg)

        monkeypatch.setattr(ChatAgentExecutor, "execute", _mock_execute)

        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "hello"}],
                    "messageId": uuid4().hex,
                },
            },
        }
        resp = await client.post("/a2a", json=request_body)
        assert resp.status_code == 200
        result = resp.json()
        assert "result" in result
        task_result = result["result"]
        # Task 应该是 completed
        assert task_result["status"]["state"] == "completed"

    async def test_send_subscribe_streaming(self, client: AsyncClient, monkeypatch) -> None:
        """验证 message/stream (sendSubscribe) 返回 SSE 流。"""
        from agent_sdk._server import a2a_adapter

        async def _mock_execute(self, context, event_queue):
            from a2a.server.tasks import TaskUpdater
            from a2a.types import Part, TextPart

            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.start_work()
            await updater.add_artifact(
                parts=[Part(root=TextPart(text="streaming chunk 1"))],
                append=True,
            )
            await updater.add_artifact(
                parts=[Part(root=TextPart(text="streaming chunk 2"))],
                append=True,
            )
            msg = updater.new_agent_message(
                parts=[Part(root=TextPart(text="done"))]
            )
            await updater.complete(message=msg)

        monkeypatch.setattr(ChatAgentExecutor, "execute", _mock_execute)

        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "stream test"}],
                    "messageId": uuid4().hex,
                },
            },
        }
        # sendSubscribe 返回 SSE
        resp = await client.post("/a2a", json=request_body)
        assert resp.status_code == 200
        # SSE 内容应包含 data 行
        content = resp.text
        assert "data:" in content or "event:" in content

    async def test_input_required_flow(self, client: AsyncClient, monkeypatch) -> None:
        """验证 HITL：agent 返回 input-required 状态。"""
        from agent_sdk._server import a2a_adapter

        async def _mock_execute(self, context, event_queue):
            from a2a.server.tasks import TaskUpdater
            from a2a.types import Part, TextPart

            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.start_work()

            # 检查是否是续传（有历史消息）
            if context.current_task and context.current_task.status.state.value == "input-required":
                # 收到回复后完成
                user_reply = context.get_user_input()
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Got reply: {user_reply}"))]
                )
                await updater.complete(message=msg)
            else:
                # 首次调用：请求用户输入
                msg = updater.new_agent_message(
                    parts=[Part(root=TextPart(text="Please confirm"))]
                )
                await updater.requires_input(message=msg)

        monkeypatch.setattr(ChatAgentExecutor, "execute", _mock_execute)

        # 第一次调用 → input-required
        msg_id = uuid4().hex
        context_id = uuid4().hex
        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "start inquiry"}],
                    "messageId": msg_id,
                    "contextId": context_id,
                },
            },
        }
        resp = await client.post("/a2a", json=request_body)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["status"]["state"] == "input-required"
        task_id = result["id"]

        # 第二次调用（带 reply）→ completed
        request_body2 = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "yes, confirmed"}],
                    "messageId": uuid4().hex,
                    "contextId": context_id,
                    "taskId": task_id,
                },
            },
        }
        resp2 = await client.post("/a2a", json=request_body2)
        assert resp2.status_code == 200
        result2 = resp2.json()["result"]
        assert result2["status"]["state"] == "completed"
