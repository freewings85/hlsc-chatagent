"""query_execution_status 工具：查询执行状态（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def query_execution_status(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="订单 ID")],
) -> str:
    """查询预订执行状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("query_execution_status", sid, rid, {"order_id": order_id})
    log_tool_end("query_execution_status", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "query_execution_status 尚未实现"}'
