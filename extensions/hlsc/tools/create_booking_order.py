"""create_booking_order 工具：生成预订订单（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def create_booking_order(
    ctx: RunContext[AgentDeps],
    plan_mode: Annotated[str, Field(description="预订模式：transition/standard/bidding/insurance/butler/package")],
    project_id: Annotated[str, Field(description="项目 ID")],
    shop_id: Annotated[str, Field(description="商户 ID")],
    coupon_id: Annotated[str, Field(description="券 ID")] = "",
    booking_date: Annotated[str, Field(description="预订日期 YYYY-MM-DD")] = "",
) -> str:
    """生成预订订单，含完整性校验。返回 missing_fields 如有缺失。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("create_booking_order", sid, rid, {
        "plan_mode": plan_mode, "project_id": project_id,
        "shop_id": shop_id, "coupon_id": coupon_id,
    })
    log_tool_end("create_booking_order", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "create_booking_order 尚未实现，当前无法生成预订订单"}'
