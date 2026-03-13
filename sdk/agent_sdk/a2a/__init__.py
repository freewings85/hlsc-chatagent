"""A2A 客户端工具集：简化 mainagent 调用 subagent 的开发体验。

使用方式：

    # 最简（一行）
    from agent_sdk.a2a import call_subagent

    async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
        return await call_subagent(ctx, url="http://subagent:8101", message=query)

    # 展开（可介入 A2A 过程）
    async with call_subagent(ctx, url=..., message=...) as session:
        async for event in session:
            if event.state == "input-required":
                event.question = f"[前缀] {event.question}"
        return session.result
"""

from agent_sdk.a2a.call_subagent import (
    SubagentEvent,
    SubagentSession,
    call_subagent,
    call_subagent_session,
)

__all__ = [
    "call_subagent",
    "call_subagent_session",
    "SubagentSession",
    "SubagentEvent",
]
