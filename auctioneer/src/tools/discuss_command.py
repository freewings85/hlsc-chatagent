"""discuss_command 工具：询价途中发出指令（广播 / 要求重新报价）。"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.services.serviceorder_service import serviceorder_service
from src.tools.prompt_loader import load_tool_prompt

CommandType = Literal["broadcast_only", "require_requote"]

_DESCRIPTION: str = load_tool_prompt("discuss_command")


async def discuss_command(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="服务订单 ID")],
    command: Annotated[CommandType, Field(description="指令类型：broadcast_only（仅广播）/ require_requote（要求商户重新报价）")],
    content: Annotated[str, Field(description="附言内容，说明指令原因或补充信息")],
) -> str:
    """发出讨论指令：仅广播或要求商户重新报价。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "order_id": order_id,
        "command": command,
        "content": content,
    }
    log_tool_start("discuss_command", sid, rid, params)

    try:
        result: dict = await serviceorder_service.discuss_command(
            order_id=order_id,
            command=command,
            content=content,
            session_id=sid,
            request_id=rid,
        )
        log_tool_end("discuss_command", sid, rid, result)
        return json.dumps({"success": True, "result": result}, ensure_ascii=False)
    except Exception as e:
        log_tool_end("discuss_command", sid, rid, exc=e)
        return f"Error: discuss_command failed - {e}"


discuss_command.__doc__ = _DESCRIPTION
