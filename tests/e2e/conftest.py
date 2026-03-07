"""Playwright 测试 fixtures：启动真实服务器，准备测试数据。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

# 测试用服务器端口（避免与开发服务器 8100 冲突）
PLAYWRIGHT_PORT: int = int(os.getenv("PLAYWRIGHT_PORT", "8199"))

# 项目根目录
PROJECT_ROOT: Path = Path(__file__).parent.parent.parent

# 测试数据目录（虚拟模式根目录）
TEST_DATA_DIR: Path = PROJECT_ROOT / "data" / "playwright_tests"

# 每次工具调用最长等待时间（秒）- LLM 调用较慢
TOOL_TIMEOUT_MS: int = 90_000
RESPONSE_TIMEOUT_MS: int = 120_000


@pytest.fixture(scope="session")
def base_url() -> str:  # type: ignore[return]
    """启动服务器并返回 base URL，session 结束时停止服务器。"""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "SERVER_PORT": str(PLAYWRIGHT_PORT),
        "DATA_DIR": str(TEST_DATA_DIR),
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.server.app:app",
         "--host", "127.0.0.1",
         "--port", str(PLAYWRIGHT_PORT),
         "--log-level", "warning"],
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    url = f"http://127.0.0.1:{PLAYWRIGHT_PORT}"

    # 等待服务器就绪（最多 30 秒）
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
        pytest.fail(f"Server failed to start on port {PLAYWRIGHT_PORT}")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def chat_page(page: Page, base_url: str) -> Page:
    """打开聊天测试页面，返回 Page 对象。"""
    page.goto(base_url)
    page.wait_for_selector("#input-box")
    return page


def send_and_wait(page: Page, message: str) -> None:
    """发送消息并等待 Agent 回复完成（send-btn 重新变为可用）。"""
    input_box = page.locator("#input-box")
    input_box.fill(message)
    page.locator("#send-btn").click()

    # 等待流式响应结束（send-btn 不再 disabled）
    page.wait_for_function(
        "() => !document.getElementById('send-btn').disabled",
        timeout=RESPONSE_TIMEOUT_MS,
    )


def wait_for_tool(page: Page, tool_name: str) -> None:
    """等待指定工具名的工具块出现。"""
    page.wait_for_selector(
        f".tool-name:text-is('{tool_name}')",
        timeout=TOOL_TIMEOUT_MS,
    )
