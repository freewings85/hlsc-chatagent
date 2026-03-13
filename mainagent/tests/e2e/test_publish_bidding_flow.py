"""publish-bidding 完整流程 e2e 测试。

使用真实 LLM + mock 工具服务器。
前置条件：mock_tool_server 在 8106 端口运行。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

# 清除代理（WSL 环境）
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(v, None)

TEST_PORT: int = int(os.getenv("BIDDING_TEST_PORT", "8102"))
PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
# LLM 调用较慢，给足时间
TIMEOUT_MS: int = 180_000


@pytest.fixture(scope="module")
def server_url() -> str:  # type: ignore[return]
    env = {**os.environ, "SERVER_PORT": str(TEST_PORT)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agent_sdk._server.app:app",
         "--host", "127.0.0.1", "--port", str(TEST_PORT), "--log-level", "info"],
        env=env, cwd=str(PROJECT_ROOT),
    )
    url = f"http://127.0.0.1:{TEST_PORT}"
    for _ in range(30):
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.terminate()
        pytest.fail(f"Server failed to start on port {TEST_PORT}")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def chat(page: Page, server_url: str) -> Page:
    page.goto(server_url)
    page.wait_for_selector("#input-box", timeout=10_000)
    return page


def _wait_for_response_done(page: Page, timeout: int = TIMEOUT_MS) -> None:
    """等待 SSE 流结束（streaming 状态 → false）。

    通过检测 #input-box 从 disabled 变为 enabled 来判断。
    input-box 的 disabled 仅由 streaming 控制（不像 send-btn 还要检查 input 非空）。
    """
    page.wait_for_function(
        "() => { const el = document.getElementById('input-box'); return el && !el.disabled; }",
        timeout=timeout,
    )


class TestPublishBiddingFlow:

    def test_round1_sends_and_shows_interrupt(self, chat: Page) -> None:
        """Round 1：发送竞价请求 → 工具调用链 → interrupt 卡片出现。"""
        page = chat

        # 发送消息
        input_box = page.locator("#input-box")
        input_box.fill("帮我发起竞价，我的车是奔驰C级2023款，要换刹车片")

        # 等待 send-btn 变为可点击（React 需要一个渲染周期来响应 input 变化）
        send_btn = page.locator("#send-btn")
        send_btn.wait_for(state="attached", timeout=5_000)
        page.wait_for_function(
            "() => { const b = document.getElementById('send-btn'); return b && !b.disabled; }",
            timeout=5_000,
        )
        send_btn.click()
        print(f"消息已发送，等待 input-box 变为 disabled...")

        # 先等 input-box 变为 disabled（确认请求已发出）
        page.wait_for_function(
            "() => { const el = document.getElementById('input-box'); return el && el.disabled; }",
            timeout=10_000,
        )
        print(f"input-box 已 disabled，等待响应完成...")

        # 等待回复完成：input-box 重新变为 enabled（streaming=false）
        _wait_for_response_done(page)
        print(f"响应已完成")

        # 检查工具调用出现
        tool_names = page.locator(".tool-name").all_text_contents()
        print(f"工具调用: {tool_names}")
        assert "Skill" in tool_names, f"应该调用 Skill 工具，实际: {tool_names}"

        # 检查 interrupt 卡片
        interrupt_cards = page.locator(".interrupt-block")
        count = interrupt_cards.count()
        print(f"Interrupt 卡片数: {count}")
        assert count > 0, "应该有至少一个 interrupt 卡片"

        # 检查确认按钮
        confirm_btn = page.locator(".interrupt-block .btn-confirm").first
        expect(confirm_btn).to_be_visible()

        # ---- Round 2: 点确认 ----
        r1_tool_count = len(tool_names)
        confirm_btn.click()

        # 等待 input-box 变为 disabled（确认 round 2 的消息已发出）
        page.wait_for_function(
            "() => { const el = document.getElementById('input-box'); return el && el.disabled; }",
            timeout=10_000,
        )
        print("Round 2 消息已发出")

        # 等待第二轮完成
        _wait_for_response_done(page)

        # 验证 Round 2 产生了新的工具调用
        tool_names_after = page.locator(".tool-name").all_text_contents()
        print(f"Round 2 全部工具: {tool_names_after}")
        assert len(tool_names_after) > r1_tool_count, \
            f"Round 2 应产生新工具调用，round1={r1_tool_count}, total={len(tool_names_after)}"

        # 验证文本回复（至少有2段 text-segment，round 1 和 round 2 各一段）
        text_segments = page.locator(".text-segment").all_text_contents()
        all_text = " ".join(text_segments)
        print(f"文本段数: {len(text_segments)}, 内容: {all_text[:300]}")
        assert len(text_segments) >= 2, f"应至少有2段文本回复，实际 {len(text_segments)}"
