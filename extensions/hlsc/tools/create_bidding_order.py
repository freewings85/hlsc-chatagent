"""create_bidding_order 工具：生成竞标抢单订单（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def create_bidding_order(
    ctx: RunContext[AgentDeps],
    project_id: Annotated[str, Field(description="项目 ID")],
    target_price: Annotated[float, Field(description="一口价价格")],
    shop_scope: Annotated[str, Field(description="商户范围描述")] = "",
) -> str:
    """生成竞标抢单订单，推送到符合条件的商户。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("create_bidding_order", sid, rid, {
        "project_id": project_id, "target_price": target_price, "shop_scope": shop_scope,
    })
    log_tool_end("create_bidding_order", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "create_bidding_order 尚未实现"}'
