"""DynamicToolset：每步从 deps 读取工具集

工具安全包装：所有工具在注册到 Toolset 时自动包装 try/catch，
非 ModelRetry 异常会被捕获并作为错误字符串返回给 LLM，
避免单个工具的异常导致整个 agent loop 崩溃。

此外包装层做"相同 tool + 相同 args"去重——LLM 被训练成"error-recovery"，
tool 返回任何模糊的错误都可能触发它**立即用相同参数再调一次**。导致整轮
token 烧穿。策略：

  1 次：正常执行
  2 次相同调用：**短路**，不真的再跑 tool，合成一段陈述式 result 回给 LLM
                （"本轮已用相同参数调过，结果同上"）。LLM 看到无 recovery
                信号的陈述式文本会自然换策略 / 回复用户。
  3+ 次相同调用：raise AgentLoopError，loop.py 的外层 catch 终止本轮。
"""

import functools
import hashlib
import json
import logging
from typing import Any, Callable

from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._utils.session_logger import log_info
from agent_sdk.exceptions import AgentLoopError

logger = logging.getLogger(__name__)


# 同 turn 内同 (tool, args) 允许实际执行的次数
_DEDUP_EXECUTE_LIMIT: int = 1
# 超过 _DEDUP_HARD_LIMIT 直接 raise 终止整轮
_DEDUP_HARD_LIMIT: int = 3


def _hash_tool_args(tool_name: str, kwargs: dict[str, Any]) -> str:
    """对工具参数做稳定 hash。忽略 ctx（RunContext），只取业务 kwargs。"""
    # 过滤 RunContext 类参数（位于 ctx / args[0]，不在 kwargs）
    serializable: dict[str, Any] = {
        k: v for k, v in kwargs.items() if not isinstance(v, RunContext)
    }
    try:
        payload: str = json.dumps(serializable, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        payload = repr(sorted(serializable.items()))
    digest: str = hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]
    return f"{tool_name}:{digest}"


def wrap_tool_safe(func: Callable[..., Any]) -> Callable[..., Any]:
    """包装工具函数：异常处理 + 相同调用去重。

    **异常处理**：
    - ModelRetry → pydantic-ai 内部处理（让 LLM 重试本工具，框架级重试）
    - AgentLoopError → sdk loop.py 的外层 except 处理（终止本轮 agent loop）
    - 其他 Exception → 捕获转为 LLM 可读字符串，让 LLM 决定如何处理

    **去重（本 turn 内相同 tool+相同 args）**：
    - 第 1 次：正常执行
    - 第 2 次：短路，不执行 tool，合成陈述式结果给 LLM
    - 第 3+ 次：raise AgentLoopError 终止本轮
    """
    tool_name: str = func.__name__

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 取 ctx.deps 做 dedup bookkeeping。ctx 是第一个位置参数。
        ctx: RunContext[AgentDeps] | None = args[0] if args and isinstance(args[0], RunContext) else None
        deps: AgentDeps | None = ctx.deps if ctx else None

        if deps is not None:
            fingerprint: str = _hash_tool_args(tool_name, kwargs)
            count: int = deps.tool_call_dedup.get(fingerprint, 0) + 1
            deps.tool_call_dedup[fingerprint] = count

            if count >= _DEDUP_HARD_LIMIT:
                logger.error(
                    f"[TOOL_DEDUP] {tool_name} 本轮已第 {count} 次相同参数调用，终止本轮"
                )
                raise AgentLoopError(
                    f"tool {tool_name} 本轮内已反复调用 {count} 次相同参数，终止以避免死循环"
                )

            if count > _DEDUP_EXECUTE_LIMIT:
                logger.warning(
                    f"[TOOL_DEDUP] {tool_name} 本轮已第 {count} 次相同参数调用，短路返回"
                )
                return (
                    f"本轮内已用相同参数调用过 {tool_name}，结果同上次。"
                    "不要再用这些参数调同一个工具——请基于已有信息回复用户，或换别的工具/参数。"
                )

        try:
            return await func(*args, **kwargs)
        except (ModelRetry, AgentLoopError):
            raise  # 透传给 pydantic-ai / sdk loop 处理
        except Exception as exc:
            logger.warning(f"工具 {tool_name} 执行异常: {exc}", exc_info=True)
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
