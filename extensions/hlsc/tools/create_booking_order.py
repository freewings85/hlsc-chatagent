"""create_booking_order 工具：汇总预订参数，中断等待用户回复。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("create_booking_order")


async def create_booking_order(
    ctx: RunContext[AgentDeps],
    plan_mode: Annotated[str, Field(description="预订模式：transition/standard/bidding/insurance/butler/package")],
    project_ids: Annotated[list[str], Field(description="项目 ID 列表")],
    shop_ids: Annotated[list[str], Field(description="商户 ID 列表")],
    car_model_id: Annotated[str, Field(description="车型 ID")],
    price: Annotated[str, Field(description="预订价格")],
    booking_time: Annotated[str, Field(description="到店时间（必填），必须先向车主确认。支持具体日期时间、时间范围、或'由商户排期'（车主明确表示灵活时）")],
) -> str:
    """汇总预订信息发给前端，等待用户回复。返回用户的原始回复文本。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "plan_mode": plan_mode,
        "project_ids": project_ids,
        "shop_ids": shop_ids,
        "car_model_id": car_model_id,
        "price": price,
        "booking_time": booking_time,
        "remark": "",
        "upload_image": True,
    }
    log_tool_start("create_booking_order", sid, rid, params)

    try:
        reply: str = await call_interrupt(ctx, {
            "type": "confirm_booking",
            "question": "请确认以下预订信息：",
            "booking_params": params,
        })

        log_tool_end("create_booking_order", sid, rid, {"reply_length": len(reply)})

        # 提取 user_msg（JSON 格式）或原样返回纯文本
        try:
            data: dict[str, Any] = json.loads(reply)
            user_msg: str = str(data.get("user_msg", "")).strip()
            return user_msg if user_msg else reply
        except (json.JSONDecodeError, AttributeError):
            return reply.strip()

    except Exception as e:
        log_tool_end("create_booking_order", sid, rid, exc=e)
        return f"Error: create_booking_order failed - {e}"


create_booking_order.__doc__ = _DESCRIPTION
