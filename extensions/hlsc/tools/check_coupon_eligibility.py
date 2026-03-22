"""check_coupon_eligibility 工具：只读校验券型适用性（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def check_coupon_eligibility(
    ctx: RunContext[AgentDeps],
    project_id: Annotated[str, Field(description="项目 ID")],
    coupon_type: Annotated[str, Field(description="券型：10yuan / 9zhe")] = "9zhe",
    booking_date: Annotated[str, Field(description="预订日期 YYYY-MM-DD")] = "",
) -> str:
    """只读校验券型适用性，返回 eligibility 和 plan_mode_hint。不产生任何业务副作用。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("check_coupon_eligibility", sid, rid, {
        "project_id": project_id, "coupon_type": coupon_type, "booking_date": booking_date,
    })
    log_tool_end("check_coupon_eligibility", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "check_coupon_eligibility 尚未实现，当前无法校验券型适用性"}'
