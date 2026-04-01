"""commit_order 工具：接受某商户的报价，确认成交。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.services.serviceorder_service import serviceorder_service
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("commit_order")


async def commit_order(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="服务订单 ID")],
    commercial_id: Annotated[int, Field(description="选中的商户 ID（来自报价列表的 commercial_id）")],
) -> str:
    """接受某商户的报价，确认成交。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "order_id": order_id,
        "commercial_id": commercial_id,
    }
    log_tool_start("commit_order", sid, rid, params)

    try:
        result: dict = await serviceorder_service.commit_order(
            order_id=order_id,
            commercial_id=commercial_id,
            operator_name="AI",
            session_id=sid,
            request_id=rid,
        )
        log_tool_end("commit_order", sid, rid, result)
        return json.dumps({"success": True, "result": result}, ensure_ascii=False)
    except Exception as e:
        log_tool_end("commit_order", sid, rid, exc=e)
        return f"Error: commit_order failed - {e}"


commit_order.__doc__ = _DESCRIPTION
