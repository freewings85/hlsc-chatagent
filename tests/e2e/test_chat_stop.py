"""Playwright + API 测试：验证 /chat/stop 和 chat_request_start 事件。

测试策略：
1. API 级：发 /chat/stream，验证首条 SSE 事件是 chat_request_start 且包含 task_id
2. API 级：用 task_id 调 /chat/stop，验证返回 cancelled
3. Playwright：发送消息后 UI 出现停止按钮，点击后流终止
"""

from __future__ import annotations

import json

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import RESPONSE_TIMEOUT_MS


class TestChatRequestStartEvent:
    """SSE 流的第一条事件应该是 chat_request_start，包含 task_id。"""

    def test_first_sse_event_is_chat_request_start(self, base_url: str) -> None:
        """发起 /chat/stream，验证首条 SSE 事件格式。"""
        with httpx.Client(timeout=30) as client:
            with client.stream(
                "POST",
                f"{base_url}/chat/stream",
                json={
                    "session_id": "test-stop-sess",
                    "message": "你好",
                    "user_id": "test-user",
                },
            ) as resp:
                assert resp.status_code == 200

                # 读取第一个完整的 SSE block
                buffer = ""
                for chunk in resp.iter_text():
                    buffer += chunk
                    if "\n\n" in buffer:
                        break

                # 解析第一个 SSE 事件
                first_block = buffer.split("\n\n")[0]
                lines = first_block.strip().split("\n")

                event_type = ""
                event_data = ""
                for line in lines:
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        event_data = line[6:].strip()

                assert event_type == "chat_request_start"
                data = json.loads(event_data)
                assert "task_id" in (data.get("data") or data)


class TestChatStop:
    """POST /chat/stop 应能取消运行中的任务。"""

    def test_stop_running_task(self, base_url: str) -> None:
        """发起 stream，拿到 task_id，调 stop，验证 cancelled 或已结束（404）。

        注意：LLM 可能在 stop 请求到达前就完成了，此时 task 已不在注册表中。
        两种结果都是正确行为。
        """
        stream_client = httpx.Client(timeout=30)
        stop_client = httpx.Client(timeout=10)
        try:
            with stream_client.stream(
                "POST",
                f"{base_url}/chat/stream",
                json={
                    "session_id": "test-stop-sess-2",
                    "message": "请使用 read 工具读取 /nonexistent_file.txt 的内容，然后再读取 /another_file.txt",
                    "user_id": "test-user",
                },
            ) as resp:
                assert resp.status_code == 200

                # 读取首条事件获取 task_id
                buffer = ""
                for chunk in resp.iter_text():
                    buffer += chunk
                    if "\n\n" in buffer:
                        break

                first_block = buffer.split("\n\n")[0]
                event_data = ""
                for line in first_block.strip().split("\n"):
                    if line.startswith("data: "):
                        event_data = line[6:].strip()

                data = json.loads(event_data)
                task_id = (data.get("data") or data).get("task_id")
                assert task_id

                # 用独立 client 调 /chat/stop（stream 连接仍活跃）
                stop_resp = stop_client.post(
                    f"{base_url}/chat/stop",
                    json={"task_id": task_id},
                )
                # 200 = 成功取消；404 = task 已自然结束（LLM 响应太快）
                assert stop_resp.status_code in (200, 404)
                if stop_resp.status_code == 200:
                    assert stop_resp.json()["status"] == "cancelled"
        finally:
            stream_client.close()
            stop_client.close()

    def test_stop_nonexistent_task(self, base_url: str) -> None:
        """停止不存在的 task_id 返回 404。"""
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{base_url}/chat/stop",
                json={"task_id": "nonexistent-task-id"},
            )
            assert resp.status_code == 404


class TestStopButtonUI:
    """Playwright UI 测试：streaming 时显示停止按钮。"""

    def test_stop_button_appears_during_streaming(self, chat_page: Page) -> None:
        """发送消息后，停止按钮出现；流结束后，发送按钮恢复。"""
        input_box = chat_page.locator("#input-box")
        input_box.fill("你好")
        chat_page.locator("#send-btn").click()

        # streaming 期间应出现停止按钮
        stop_btn = chat_page.locator(".btn-stop")
        stop_btn.wait_for(state="visible", timeout=5000)

        # 点击停止
        stop_btn.click()

        # 流结束后，发送按钮应恢复（停止按钮消失或发送按钮出现）
        send_btn = chat_page.locator("#send-btn")
        send_btn.wait_for(state="visible", timeout=RESPONSE_TIMEOUT_MS)
