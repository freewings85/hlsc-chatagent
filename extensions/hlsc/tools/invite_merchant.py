"""invite_merchant 工具：引导车主邀请老商户入驻平台（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def invite_merchant(
    ctx: RunContext[AgentDeps],
    merchant_name: Annotated[str, Field(description="商户名称")],
    merchant_phone: Annotated[str, Field(description="商户联系电话")] = "",
) -> str:
    """引导车主邀请未入驻的老商户加入话痨说车平台。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("invite_merchant", sid, rid, {
        "merchant_name": merchant_name, "merchant_phone": merchant_phone,
    })
    log_tool_end("invite_merchant", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "invite_merchant 尚未实现，请引导车主通过平台页面邀请商户入驻"}'
