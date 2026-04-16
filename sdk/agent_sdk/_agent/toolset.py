"""DynamicToolset：每步从 deps 读取工具集

工具安全包装：所有工具在注册到 Toolset 时自动包装 try/catch，
非 ModelRetry 异常会被捕获并作为错误字符串返回给 LLM，
避免单个工具的异常导致整个 agent loop 崩溃。
"""

import functools
import logging
from typing import Any, Callable

from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._utils.session_logger import log_info
from agent_sdk.exceptions import AgentLoopError

logger = logging.getLogger(__name__)


def wrap_tool_safe(func: Callable[..., Any]) -> Callable[..., Any]:
    """包装工具函数，捕获非 ModelRetry / 非 AgentLoopError 异常并返回错误字符串。

    这是引擎级的错误处理：第三方工具普通异常会被捕获转为 LLM 可读字符串，
    让 LLM 决定如何处理（重试或换路径）。

    **放行的异常**：
    - ModelRetry → pydantic-ai 内部处理（让 LLM 重试本工具）
    - AgentLoopError → sdk loop.py 的外层 except 处理（终止本轮 agent loop）
      用于业务可预期的硬终止场景（如 WorkflowUnavailableError）。
      不放行会让"硬停"机制完全失效——LLM 看到错误字符串还是会反复重试。
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except (ModelRetry, AgentLoopError):
            raise  # 透传给 pydantic-ai / sdk loop 处理
        except Exception as exc:
            logger.warning(f"工具 {func.__name__} 执行异常: {exc}", exc_info=True)
            return f"[工具执行错误] {type(exc).__name__}: {exc}"
    return wrapper


def get_tools(ctx: RunContext[AgentDeps]) -> FunctionToolset:
    """根据 deps.available_tools 和 deps.tool_map 构建当前步的工具集"""
    toolset: FunctionToolset = FunctionToolset()
    registered: list[str] = []
    for name in ctx.deps.available_tools:
        func = ctx.deps.tool_map.get(name)
        if func is not None:
            toolset.add_tool(Tool(wrap_tool_safe(func), name=name))
            registered.append(name)
    log_info(
        f"[TOOLS] registered={registered}",
        session_id=ctx.deps.session_id,
        request_id=ctx.deps.request_id,
    )
    return toolset
