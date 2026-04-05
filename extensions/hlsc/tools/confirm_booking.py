"""confirm_booking 工具：汇总预订参数，中断等待用户回复。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field
from pydantic_ai import RunContext

PlanMode = Literal["standard", "commission", "bidding"]

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("confirm_booking")


async def confirm_booking(
    ctx: RunContext[AgentDeps],
    plan_mode: Annotated[PlanMode, Field(description="预订模式：standard（标准预订，选择商户报价）/ commission（委托预订，车主出一口价）/ bidding（竞标预订，商户竞价）")],
    project_ids: Annotated[list[int], Field(description="项目 ID 列表（整数，严禁编造，必须来自 match_project 返回）")],
    shop_ids: Annotated[list[int], Field(description="商户 ID 列表（整数，严禁编造，必须来自 search_shops 返回）")],
    car_model_id: Annotated[str, Field(description="车型 ID（来自 collect_car_info / list_user_cars，项目不需要车型时传空字符串）")],
    booking_time: Annotated[str, Field(description="到店时间，必须先向车主确认。支持具体日期时间、时间范围、或'由商户排期'（车主明确表示灵活时）")],
    price: Annotated[str, Field(description="预订价格（bidding 模式不传，由商户竞价决定）")] = "",
    coupon_ids: Annotated[list[int], Field(description="优惠券 ID 列表（来自 search_coupon 返回，无优惠时传空列表）")] = [],
    remark: Annotated[str, Field(description="车主备注信息（用户主动提出时填写）")] = "",
) -> str:
    """汇总预订信息发给前端，等待用户回复。返回用户的原始回复文本。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "plan_mode": plan_mode,
        "project_ids": project_ids,
        "shop_ids": shop_ids,
        "car_model_id": car_model_id,
        "booking_time": booking_time,
        "upload_image": True,
    }
    if price:
        params["price"] = price
    if coupon_ids:
        params["coupon_ids"] = coupon_ids
    if remark:
        params["remark"] = remark
    log_tool_start("confirm_booking", sid, rid, params)

    try:
        reply: str = await call_interrupt(ctx, {
            "type": "confirm_booking",
            "question": "请确认以下预订信息：",
            "booking_params": params,
        })

        log_tool_end("confirm_booking", sid, rid, {"reply_length": len(reply)})

        # 提取 user_msg（JSON 格式）或原样返回纯文本
        try:
            data: dict[str, Any] = json.loads(reply)
            user_msg: str = str(data.get("user_msg", "")).strip()
            return user_msg if user_msg else reply
        except (json.JSONDecodeError, AttributeError):
            return reply.strip()

    except Exception as e:
        log_tool_end("confirm_booking", sid, rid, exc=e)
        return f"Error: confirm_booking failed - {e}"


confirm_booking.__doc__ = _DESCRIPTION
