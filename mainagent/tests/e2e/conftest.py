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

# 清除代理环境变量（WSL 下 HTTP_PROXY 会让 httpx 将 localhost 请求路由到代理）
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_proxy_var, None)

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

    # 清除代理（WSL 下 HTTP_PROXY 会干扰 localhost 请求）
    clean_env = {k: v for k, v in os.environ.items()
                 if k.lower() not in ("http_proxy", "https_proxy")}
    env = {
        **clean_env,
        "SERVER_PORT": str(PLAYWRIGHT_PORT),
        "DATA_DIR": str(TEST_DATA_DIR),
        "USE_NACOS": "FALSE",
        # E2E 使用 20k compact 阈值（接近真实使用场景）
        # effective_window = 20000 - 2000 = 18000
        # microcompact_threshold = 18000 - 2000 = 16000 tokens
        # full_compact_threshold = max(18000-1300, 16001) = 16700 tokens
        # 4 轮读取 16k-char 文件（~4000 tokens/轮）→ 总计 ~18000 tokens → 触发 microcompact
        "COMPACT_CONTEXT_WINDOW": "20000",
        "COMPACT_OUTPUT_RESERVE": "2000",
        "COMPACT_MIN_SAVINGS_THRESHOLD": "2000",
        "COMPACT_AUTO_BUFFER": "1300",
        "COMPACT_KEEP_RECENT_TOOL_RESULTS": "1",
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agent_sdk._server.app:app",
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


@pytest.fixture(autouse=True)
def clean_test_data_dir() -> None:
    """每个测试函数开始前清空 TEST_DATA_DIR 内容（保留目录本身），避免测试间数据污染。"""
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
