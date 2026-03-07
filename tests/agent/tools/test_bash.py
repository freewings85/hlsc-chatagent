"""Bash 工具测试。"""

from unittest.mock import MagicMock

import pytest

from src.agent.deps import AgentDeps
from src.agent.tools.bash import MAX_OUTPUT_BYTES, bash


def make_ctx() -> MagicMock:
    deps = AgentDeps()
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


class TestBashTool:
    @pytest.mark.asyncio
    async def test_simple_command(self) -> None:
        """echo 命令返回预期输出"""
        ctx = make_ctx()
        result = await bash(ctx, "echo hello_world")
        assert "hello_world" in result

    @pytest.mark.asyncio
    async def test_exit_code_nonzero(self) -> None:
        """非零退出码时标注 [exit N]"""
        ctx = make_ctx()
        result = await bash(ctx, "exit 1", timeout=5)
        assert "[exit 1]" in result

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """超时时返回超时提示"""
        ctx = make_ctx()
        result = await bash(ctx, "sleep 10", timeout=1)
        assert "超时" in result or "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_stderr_captured(self) -> None:
        """stderr 输出被捕获"""
        ctx = make_ctx()
        result = await bash(ctx, "echo error_msg >&2")
        assert "error_msg" in result

    @pytest.mark.asyncio
    async def test_output_truncation(self) -> None:
        """输出超过限制时被截断"""
        ctx = make_ctx()
        # 生成超过 30KB 的输出
        large_cmd = f"python3 -c \"print('x' * {MAX_OUTPUT_BYTES + 5000})\""
        result = await bash(ctx, large_cmd)
        assert "截断" in result or "truncated" in result.lower()

    @pytest.mark.asyncio
    async def test_multiline_output(self) -> None:
        """多行输出正常返回"""
        ctx = make_ctx()
        result = await bash(ctx, "printf 'line1\\nline2\\nline3\\n'")
        assert "line1" in result
        assert "line3" in result
