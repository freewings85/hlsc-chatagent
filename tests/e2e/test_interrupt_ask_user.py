"""ask_user interrupt 前端 E2E 测试（Playwright）。

验证完整流程：
1. 发送消息 → agent 调用 ask_user → 前端出现 interrupt 卡片
2. 用户点击确认/输入回复 → 调用 /chat/interrupt-reply API
3. agent 继续执行 → 最终完成

需要：
- Temporal server 运行在 localhost:7233
- TEMPORAL_ENABLED=true 启动服务器
- web/dist/ 已构建（npx vite build）

使用 Playwright 浏览器测试。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

# 清除代理
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_proxy_var, None)

# 端口（避免与其他测试冲突）
INTERRUPT_TEST_PORT: int = int(os.getenv("INTERRUPT_TEST_PORT", "8198"))
PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
TEST_DATA_DIR: Path = PROJECT_ROOT / "data" / "interrupt_tests"

# 超时
INTERRUPT_APPEAR_MS: int = 60_000  # interrupt 卡片出现
RESPONSE_COMPLETE_MS: int = 120_000  # 整个对话完成


def _temporal_available() -> bool:
    """检查 Temporal server 是否可用。"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("localhost", 7233))
        s.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def interrupt_server_url():
    """启动带 Temporal 的服务器。"""
    if not _temporal_available():
        pytest.skip("Temporal server not available at localhost:7233")

    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 构建前端（如果 dist 不存在）
    dist_dir = PROJECT_ROOT / "web" / "dist"
    if not dist_dir.exists():
        subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(PROJECT_ROOT / "web"),
            check=True,
            timeout=60,
        )

    clean_env = {k: v for k, v in os.environ.items()
                 if k.lower() not in ("http_proxy", "https_proxy")}
    env = {
        **clean_env,
        "SERVER_PORT": str(INTERRUPT_TEST_PORT),
        "DATA_DIR": str(TEST_DATA_DIR),
        "USE_NACOS": "FALSE",
        "TEMPORAL_ENABLED": "true",
        "TEMPORAL_HOST": "localhost:7233",
        "TEMPORAL_INTERRUPT_QUEUE": f"test-interrupt-e2e-{os.getpid()}",
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.sdk._server.app:app",
         "--host", "127.0.0.1",
         "--port", str(INTERRUPT_TEST_PORT),
         "--log-level", "warning"],
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    url = f"http://127.0.0.1:{INTERRUPT_TEST_PORT}"

    for i in range(30):
        try:
            r = httpx.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.terminate()
        pytest.fail(f"Server failed to start on port {INTERRUPT_TEST_PORT}")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(autouse=True)
def clean_test_data():
    import shutil
    if TEST_DATA_DIR.exists():
        for child in TEST_DATA_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def chat_page(page: Page, interrupt_server_url: str) -> Page:
    page.goto(interrupt_server_url)
    page.wait_for_selector("#input-box", timeout=10_000)
    return page


class TestInterruptUIFlow:
    """Playwright 测试：interrupt 卡片 UI 交互"""

    def test_interrupt_card_appears_and_reply(self, chat_page: Page) -> None:
        """发送会触发 ask_user 的消息 → interrupt 卡片出现 → 点击确认 → agent 继续。

        注意：此测试需要 LLM 能理解请求并调用 ask_user 工具。
        如果 LLM 不可用或行为不确定，测试可能跳过。
        """
        page = chat_page

        # 发送消息（需要 LLM 触发 ask_user）
        input_box = page.locator("#input-box")
        input_box.fill("请使用 ask_user 工具向我确认是否继续操作，type 用 confirm")
        page.locator("#send-btn").click()

        # 等待 interrupt 卡片出现
        try:
            interrupt_block = page.locator(".interrupt-block")
            interrupt_block.first.wait_for(timeout=INTERRUPT_APPEAR_MS)
        except Exception:
            # LLM 可能没触发 ask_user，检查是否有文本回复
            if page.locator(".text-segment").count() > 0:
                pytest.skip("LLM did not trigger ask_user tool")
            raise

        # 验证卡片内容
        expect(interrupt_block.first).to_be_visible()

        # 应有暂停图标（表示 Temporal interrupt）
        icon = interrupt_block.first.locator(".interrupt-icon")
        expect(icon).to_have_text("⏸️")

        # 点击确认按钮
        confirm_btn = interrupt_block.first.locator(".btn-confirm")
        confirm_btn.click()

        # 应显示"已回复"
        replied_badge = interrupt_block.first.locator(".interrupt-replied")
        expect(replied_badge).to_be_visible()
        expect(replied_badge).to_have_text("已回复")

        # 等待 agent 继续执行完成（streaming 结束，send-btn 重新出现）
        page.wait_for_selector("#send-btn", timeout=RESPONSE_COMPLETE_MS)

        # 最终应有文本回复（agent 在 interrupt 后继续生成的文本）
        text_segments = page.locator(".text-segment")
        assert text_segments.count() > 0, "agent 应在 interrupt 恢复后生成文本"


class TestInterruptAPIFlow:
    """通过 httpx 直接测试 SSE + interrupt-reply API 流程（不需要浏览器）。"""

    def test_sse_interrupt_and_reply(self, interrupt_server_url: str) -> None:
        """SSE 流中 interrupt 事件 → API reply → agent 继续。"""
        import threading

        session_id = f"api-test-{os.getpid()}"
        interrupt_key_holder: list[str] = []
        all_events: list[dict] = []
        stream_done = threading.Event()

        def read_sse():
            """在线程中读取 SSE 流。"""
            try:
                with httpx.Client(timeout=120, proxy=None) as client:
                    with client.stream(
                        "POST",
                        f"{interrupt_server_url}/chat/stream",
                        json={
                            "session_id": session_id,
                            "message": "请使用 ask_user 工具问我一个确认问题，type 用 confirm，问题是'是否继续？'",
                            "user_id": "test-user",
                        },
                    ) as resp:
                        buffer = ""
                        for chunk in resp.iter_text():
                            buffer += chunk
                            while "\n\n" in buffer:
                                block, buffer = buffer.split("\n\n", 1)
                                event = _parse_sse_block(block)
                                if event:
                                    all_events.append(event)
                                    if event["type"] == "interrupt":
                                        data = event["data"].get("data", event["data"])
                                        key = data.get("interrupt_key", "")
                                        if key:
                                            interrupt_key_holder.append(key)
            except Exception as e:
                all_events.append({"type": "error", "data": {"error": str(e)}})
            finally:
                stream_done.set()

        # 启动 SSE 读取线程
        t = threading.Thread(target=read_sse, daemon=True)
        t.start()

        # 等待 interrupt 事件出现（最多 60 秒）
        for _ in range(600):
            if interrupt_key_holder:
                break
            time.sleep(0.1)

        if not interrupt_key_holder:
            stream_done.wait(timeout=10)
            event_types = [e["type"] for e in all_events]
            # 如果 LLM 没触发 ask_user，跳过
            if "tool_call_start" not in event_types or "interrupt" not in event_types:
                pytest.skip(
                    f"LLM did not trigger ask_user. Events: {event_types}"
                )
            pytest.fail(f"没有收到 interrupt_key. Events: {event_types}")

        key = interrupt_key_holder[0]

        # 发送 interrupt-reply
        with httpx.Client(timeout=10, proxy=None) as client:
            resp = client.post(
                f"{interrupt_server_url}/chat/interrupt-reply",
                json={"interrupt_key": key, "reply": "确认"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

        # 等待 SSE 流完成
        stream_done.wait(timeout=60)

        event_types = [e["type"] for e in all_events]
        assert "chat_request_end" in event_types, (
            f"SSE 流未正常结束. Events: {event_types}"
        )

        # interrupt 后应有 tool_result（ask_user 返回值）
        assert "tool_result" in event_types

        # 应有文本内容（agent 继续生成）
        text_content = ""
        for e in all_events:
            if e["type"] == "text":
                d = e["data"].get("data", e["data"])
                text_content += d.get("content", "")
        assert len(text_content) > 0, "agent 应在 interrupt 恢复后生成文本"

    def test_interrupt_reply_without_temporal_returns_503(self) -> None:
        """无 Temporal 时 interrupt-reply 返回 503。

        使用临时无 Temporal 的服务器（直接测 app 逻辑）。
        """
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        # 临时 patch _temporal_client 为 None
        import src.sdk._server.app as app_mod
        original = app_mod._temporal_client
        app_mod._temporal_client = None
        try:
            client = TestClient(app_mod.app, raise_server_exceptions=False)
            resp = client.post(
                "/chat/interrupt-reply",
                json={"interrupt_key": "fake-key", "reply": "hello"},
            )
            assert resp.status_code == 503
            assert "Temporal" in resp.json()["error"]
        finally:
            app_mod._temporal_client = original


def _parse_sse_block(block: str) -> dict | None:
    """解析单个 SSE block。"""
    event_type = "message"
    data = ""
    for line in block.strip().split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:].strip()
    if data:
        try:
            return {"type": event_type, "data": json.loads(data)}
        except json.JSONDecodeError:
            pass
    return None
