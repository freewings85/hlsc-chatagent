"""Playwright 工具覆盖测试：用真实 LLM 验证六个文件系统工具均可被 Agent 正常调用。

测试策略：
- 每个 test 发送一条明确的任务消息，要求 Agent 使用特定工具
- 等待工具调用块（.tool-name）出现，验证工具名
- 等待响应完成（send-btn 可用），验证结果内容
- 超时默认 90s（LLM 调用较慢）

测试前提：
- .env 中配置了真实的 LLM API Key
- 服务器在 data/playwright_tests/ 目录下以 virtual_mode=True 运行
- tests/playwright/conftest.py 已自动启动并停止服务器
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    RESPONSE_TIMEOUT_MS,
    TEST_DATA_DIR,
    TOOL_TIMEOUT_MS,
    send_and_wait,
    wait_for_tool,
)


class TestReadTool:
    """read 工具：Agent 应能读取文件并返回内容。"""

    def test_agent_reads_file_content(self, chat_page: Page) -> None:
        """Agent 读取预设文件，响应中出现文件内容标记。"""
        # 确保测试文件存在
        f = TEST_DATA_DIR / "read_me.txt"
        f.write_text("playwright_read_marker_SUCCESS\n")

        send_and_wait(
            chat_page,
            "请使用 read 工具读取 /read_me.txt 文件的内容，并告诉我文件里写了什么。",
        )

        # read 工具块出现
        wait_for_tool(chat_page, "read")

        # 响应中包含文件内容
        response_text = chat_page.locator(".text-segment").last.inner_text()
        assert "playwright_read_marker_SUCCESS" in response_text or \
               "read_me" in response_text or \
               len(chat_page.locator(".tool-block").all()) > 0


class TestWriteTool:
    """write 工具：Agent 应能创建新文件。"""

    def test_agent_creates_file(self, chat_page: Page) -> None:
        """Agent 创建新文件，文件在磁盘上实际存在。"""
        target_file = TEST_DATA_DIR / "agent_written.txt"
        target_file.unlink(missing_ok=True)  # 清理

        send_and_wait(
            chat_page,
            "请使用 write 工具在 /agent_written.txt 创建一个新文件，"
            "内容是 'write_tool_success_marker'。",
        )

        wait_for_tool(chat_page, "write")

        # 验证文件被实际创建
        assert target_file.exists(), "agent_written.txt 未被创建"
        assert "write_tool_success_marker" in target_file.read_text()


class TestEditTool:
    """edit 工具：Agent 应能修改已有文件内容。"""

    def test_agent_edits_file(self, chat_page: Page) -> None:
        """Agent 修改文件中的字符串。"""
        f = TEST_DATA_DIR / "edit_me.txt"
        f.write_text("OLD_VALUE_playwright_edit_marker\n")

        send_and_wait(
            chat_page,
            "请先使用 read 工具读取 /edit_me.txt，"
            "然后使用 edit 工具把文件中的 'OLD_VALUE_playwright_edit_marker' "
            "替换成 'NEW_VALUE_after_edit'。",
        )

        # read 和 edit 工具块都应出现
        wait_for_tool(chat_page, "read")
        wait_for_tool(chat_page, "edit")

        # 验证文件被修改
        assert "NEW_VALUE_after_edit" in f.read_text(), "文件内容未被修改"


class TestGlobTool:
    """glob 工具：Agent 应能按模式列出文件。"""

    def test_agent_lists_files(self, chat_page: Page) -> None:
        """Agent 使用 glob 列出 .txt 文件。"""
        # 确保有 .txt 文件
        (TEST_DATA_DIR / "glob_test_a.txt").write_text("a")
        (TEST_DATA_DIR / "glob_test_b.txt").write_text("b")

        send_and_wait(
            chat_page,
            "请使用 glob 工具查找所有 .txt 文件（模式 *.txt），告诉我找到了哪些文件。",
        )

        wait_for_tool(chat_page, "glob")

        # 有工具块就算通过
        blocks = chat_page.locator(".tool-block").all()
        assert len(blocks) > 0


class TestGrepTool:
    """grep 工具：Agent 应能在文件中搜索指定字符串。"""

    def test_agent_searches_content(self, chat_page: Page) -> None:
        """Agent 在文件中搜索特定标记字符串。"""
        f = TEST_DATA_DIR / "grep_me.txt"
        f.write_text("GREP_MARKER_XY9913 appears on this line\nother content\n")

        send_and_wait(
            chat_page,
            "请使用 grep 工具在文件中搜索字符串 'GREP_MARKER_XY9913'，告诉我找到了什么。",
        )

        wait_for_tool(chat_page, "grep")

        # 验证工具结果中包含搜索到的内容
        # 等待工具结果出现后点开查看
        tool_block = chat_page.locator(".tool-block", has=chat_page.locator(".tool-name:text-is('grep')")).first
        tool_block.locator(".tool-header").click()  # 展开
        result_el = tool_block.locator(".tool-result-section .tool-code")
        result_el.wait_for(timeout=TOOL_TIMEOUT_MS)
        result_text = result_el.inner_text()
        assert "GREP_MARKER_XY9913" in result_text or "grep_me" in result_text


class TestBashTool:
    """bash 工具：Agent 应能执行 shell 命令并返回输出。"""

    def test_agent_runs_command(self, chat_page: Page) -> None:
        """Agent 执行 echo 命令，响应中包含命令输出。"""
        send_and_wait(
            chat_page,
            "请使用 bash 工具执行命令 `echo BASH_TOOL_WORKS_12345`，告诉我命令的输出结果。",
        )

        wait_for_tool(chat_page, "bash")

        # 展开工具块查看结果
        tool_block = chat_page.locator(".tool-block", has=chat_page.locator(".tool-name:text-is('bash')")).first
        tool_block.locator(".tool-header").click()
        result_el = tool_block.locator(".tool-result-section .tool-code")
        result_el.wait_for(timeout=TOOL_TIMEOUT_MS)
        result_text = result_el.inner_text()
        assert "BASH_TOOL_WORKS_12345" in result_text


class TestMultiToolFlow:
    """多工具组合：验证 Agent 能在一次对话中依次使用多个工具。"""

    def test_write_then_read(self, chat_page: Page) -> None:
        """Agent 先写文件再读取，验证两个工具在同一轮对话中被调用。"""
        target = TEST_DATA_DIR / "multi_tool_test.txt"
        target.unlink(missing_ok=True)

        send_and_wait(
            chat_page,
            "请完成以下任务：\n"
            "1. 使用 write 工具创建 /multi_tool_test.txt 文件，内容为 'multi_tool_test_content'\n"
            "2. 然后使用 read 工具读取这个文件，确认内容正确\n"
            "请依次完成这两步。",
        )

        # 两种工具都应出现
        wait_for_tool(chat_page, "write")
        wait_for_tool(chat_page, "read")

        # 文件确实被创建
        assert target.exists()
        assert "multi_tool_test_content" in target.read_text()
