"""purchase_coupon 工具：真实购券动作（stub，待实现）。仅在 T8 执行阶段调用。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def purchase_coupon(
    ctx: RunContext[AgentDeps],
    project_id: Annotated[str, Field(description="项目 ID")],
    coupon_type: Annotated[str, Field(description="券型：10yuan / 9zhe")],
    target_price: Annotated[float, Field(description="目标价格")] = 0.0,
) -> str:
    """执行真实购券动作（有副作用）。仅在车主确认方案后的 T8 阶段调用。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("purchase_coupon", sid, rid, {
        "project_id": project_id, "coupon_type": coupon_type, "target_price": target_price,
    })
    log_tool_end("purchase_coupon", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "purchase_coupon 尚未实现，当前无法执行购券"}'
