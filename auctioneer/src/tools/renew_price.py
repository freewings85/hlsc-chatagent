"""renew_price 工具：提高报价，创建新订单重新竞标。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.services.serviceorder_service import serviceorder_service
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("renew_price")


async def renew_price(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="当前服务订单 ID")],
    new_price: Annotated[float, Field(description="新的报价金额（必须高于当前价格）")],
) -> str:
    """提高报价，创建新订单重新竞标。注意：会产生新的 orderId。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "order_id": order_id,
        "new_price": new_price,
    }
    log_tool_start("renew_price", sid, rid, params)

    try:
        result: dict = await serviceorder_service.renew_price(
            order_id=order_id,
            new_price=new_price,
            operator_name="AI",
            session_id=sid,
            request_id=rid,
        )
        log_tool_end("renew_price", sid, rid, result)
        return json.dumps({"success": True, "result": result}, ensure_ascii=False)
    except Exception as e:
        log_tool_end("renew_price", sid, rid, exc=e)
        return f"Error: renew_price failed - {e}"


renew_price.__doc__ = _DESCRIPTION
