"""notify_merchant 工具：通知/催促商户（mock）。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("notify_merchant")


async def notify_merchant(
    ctx: RunContext[AgentDeps],
    task_id: Annotated[str, Field(description="竞标任务 ID")],
    shop_id: Annotated[str, Field(description="要通知的商户 ID")],
) -> str:
    """通知指定商户尽快回复报价。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("notify_merchant", sid, rid, {"task_id": task_id, "shop_id": shop_id})

    # Mock: 通知成功
    result: dict[str, str] = {
        "status": "notified",
        "notice": f"已向商户 {shop_id} 发送催促通知",
    }

    log_tool_end("notify_merchant", sid, rid, result)
    return json.dumps(result, ensure_ascii=False)


notify_merchant.__doc__ = _DESCRIPTION
