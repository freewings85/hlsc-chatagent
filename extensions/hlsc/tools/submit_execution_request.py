"""submit_execution_request 工具：提交执行请求（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def submit_execution_request(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="订单 ID")],
    execution_type: Annotated[str, Field(description="执行类型：simple/bidding/planner")] = "simple",
) -> str:
    """提交执行请求，含完整性校验。返回 missing_fields 如有缺失。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("submit_execution_request", sid, rid, {
        "order_id": order_id, "execution_type": execution_type,
    })
    log_tool_end("submit_execution_request", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "submit_execution_request 尚未实现"}'
