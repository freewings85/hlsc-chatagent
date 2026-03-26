"""invite_merchant 工具：引导车主邀请老商户入驻平台（stub，待实现）。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("invite_merchant")


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
    result = {
        "status": "guide_user",
        "shop_name": merchant_name,
        "message": "请使用 invite_shop action 围栏，引导车主在前端完成邀请操作",
    }
    log_tool_end("invite_merchant", sid, rid, result)
    return json.dumps(result, ensure_ascii=False)


invite_merchant.__doc__ = _DESCRIPTION
