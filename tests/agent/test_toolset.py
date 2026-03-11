"""toolset 模块测试：验证 wrap_tool_safe 引擎级错误处理"""

import pytest
from pydantic_ai import ModelRetry, RunContext
from unittest.mock import MagicMock

from src.agent.deps import AgentDeps
from src.agent.toolset import wrap_tool_safe


class TestWrapToolSafe:
    """wrap_tool_safe 包装器测试"""

    @pytest.mark.asyncio
    async def test_normal_return_passes_through(self) -> None:
        """正常返回值直接透传"""
        async def my_tool(ctx: RunContext[AgentDeps], arg: str) -> str:
            return f"result: {arg}"

        wrapped = wrap_tool_safe(my_tool)
        result = await wrapped(MagicMock(), "hello")
        assert result == "result: hello"

    @pytest.mark.asyncio
    async def test_model_retry_propagates(self) -> None:
        """ModelRetry 不被捕获，透传给 pydantic-ai"""
        async def my_tool(ctx: RunContext[AgentDeps]) -> str:
            raise ModelRetry("请提供更多信息")

        wrapped = wrap_tool_safe(my_tool)
        with pytest.raises(ModelRetry, match="请提供更多信息"):
            await wrapped(MagicMock())

    @pytest.mark.asyncio
    async def test_runtime_error_caught_and_returned(self) -> None:
        """RuntimeError 被捕获，返回错误字符串"""
        async def my_tool(ctx: RunContext[AgentDeps]) -> str:
            raise RuntimeError("Temporal 未配置")

        wrapped = wrap_tool_safe(my_tool)
        result = await wrapped(MagicMock())
        assert "[工具执行错误]" in result
        assert "RuntimeError" in result
        assert "Temporal 未配置" in result

    @pytest.mark.asyncio
    async def test_value_error_caught_and_returned(self) -> None:
        """ValueError 被捕获，返回错误字符串"""
        async def my_tool(ctx: RunContext[AgentDeps]) -> str:
            raise ValueError("参数无效")

        wrapped = wrap_tool_safe(my_tool)
        result = await wrapped(MagicMock())
        assert "[工具执行错误]" in result
        assert "ValueError" in result

    @pytest.mark.asyncio
    async def test_connection_error_caught(self) -> None:
        """网络类异常也被捕获"""
        async def my_tool(ctx: RunContext[AgentDeps]) -> str:
            raise ConnectionError("连接超时")

        wrapped = wrap_tool_safe(my_tool)
        result = await wrapped(MagicMock())
        assert "[工具执行错误]" in result
        assert "ConnectionError" in result

    @pytest.mark.asyncio
    async def test_preserves_function_name(self) -> None:
        """包装后保留原函数名"""
        async def ask_user(ctx: RunContext[AgentDeps]) -> str:
            return "ok"

        wrapped = wrap_tool_safe(ask_user)
        assert wrapped.__name__ == "ask_user"
