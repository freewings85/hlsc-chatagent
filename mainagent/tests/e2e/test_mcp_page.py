"""Playwright E2E 测试：MCP 页面添加 + 探测 MCP 服务器。

前置条件：
- mainagent 运行在 8100
- mock MCP server 运行在 8199
- web 前端运行在 3100
"""

from __future__ import annotations

import os

# 清除代理
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_v, None)

from playwright.sync_api import sync_playwright


def test_mcp_add_and_probe() -> None:
    """测试：添加 MCP 服务器 → 探测工具列表 → 验证工具显示 → 移除"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 1. 打开 MCP 设置页
            page.goto("http://127.0.0.1:3100/settings/mcp")
            page.wait_for_selector("h2:has-text('添加 MCP 服务器')", timeout=10000)
            print("[1] MCP 页面加载成功")

            # 2. 填写表单添加 weather 服务器
            page.fill("#mcp-name", "weather")
            page.fill("#mcp-url", "http://127.0.0.1:8199/mcp")
            page.click("#mcp-add-btn")

            # 等待成功消息
            page.wait_for_selector(".msg.success", timeout=10000)
            msg = page.text_content(".msg.success")
            print(f"[2] 添加成功: {msg}")

            # 3. 验证服务器出现在列表中
            page.wait_for_selector("[data-server-name='weather']", timeout=5000)
            print("[3] weather 服务器出现在列表中")

            # 4. 点击探测按钮
            probe_btn = page.locator("[data-server-name='weather'] .mcp-probe-btn")
            probe_btn.click()

            # 等待探测完成（按钮文字从"探测中..."变回"探测"）
            page.wait_for_function(
                """() => {
                    const btn = document.querySelector("[data-server-name='weather'] .mcp-probe-btn");
                    return btn && btn.textContent === '探测';
                }""",
                timeout=15000,
            )

            # 验证成功消息
            success_msg = page.text_content(".msg.success")
            print(f"[4] 探测结果: {success_msg}")

            # 5. 验证工具列表显示
            tools_area = page.locator("[data-server-name='weather'] .mcp-tools-list")
            tools_area.wait_for(timeout=5000)
            tools_text = tools_area.text_content()
            print(f"[5] 工具列表: {tools_text}")

            assert "get_weather" in tools_text, f"应包含 get_weather 工具，实际: {tools_text}"
            assert "get_forecast" in tools_text, f"应包含 get_forecast 工具，实际: {tools_text}"

            # 6. 点击工具 chip 查看描述
            page.click(".mcp-tool-chip:has-text('get_weather')")
            detail = page.wait_for_selector(".mcp-tool-detail", timeout=5000)
            detail_text = detail.text_content()
            print(f"[6] 工具详情: {detail_text}")
            assert "天气" in detail_text or "weather" in detail_text.lower()

            # 7. 移除服务器
            page.on("dialog", lambda dialog: dialog.accept())
            page.click("[data-server-name='weather'] .btn-danger")
            page.wait_for_selector(".msg.success", timeout=5000)

            # 验证列表为空
            page.wait_for_selector(".empty", timeout=5000)
            print("[7] 移除成功，列表为空")

            print("\n=== MCP 页面 E2E 测试全部通过 ===")

        finally:
            page.screenshot(path="mcp_test_screenshot.png")
            browser.close()


if __name__ == "__main__":
    test_mcp_add_and_probe()
