"""push_order_to_merchant 工具：推送订单给商户（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def push_order_to_merchant(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="订单 ID")],
) -> str:
    """将预订订单推送给对应商户。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("push_order_to_merchant", sid, rid, {"order_id": order_id})
    log_tool_end("push_order_to_merchant", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "push_order_to_merchant 尚未实现"}'
