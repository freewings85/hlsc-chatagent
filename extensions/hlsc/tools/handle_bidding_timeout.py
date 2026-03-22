"""handle_bidding_timeout 工具：竞标超时处理/重新议价（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def handle_bidding_timeout(
    ctx: RunContext[AgentDeps],
    bidding_order_id: Annotated[str, Field(description="竞标订单 ID")],
    new_price: Annotated[float, Field(description="新的一口价（0 表示放弃）")] = 0.0,
) -> str:
    """处理竞标超时，支持重新议价或放弃。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("handle_bidding_timeout", sid, rid, {
        "bidding_order_id": bidding_order_id, "new_price": new_price,
    })
    log_tool_end("handle_bidding_timeout", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "handle_bidding_timeout 尚未实现"}'
