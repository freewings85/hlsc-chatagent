"""ask_user_car_info 工具：让用户提供车辆信息。

场景：需要 car_model_id 但 request_context 中未设置，用户也未提到任何车型。
通过 interrupt 弹框让用户选择/录入车型。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("ask_user_car_info")


async def ask_user_car_info(
    ctx: RunContext[AgentDeps],
    reason: Annotated[str, Field(description="需要车辆信息的原因，如'查询报价需要知道您的车型'")],
    allow_select: Annotated[bool, Field(description="是否允许从车库选择。True=需要精确车型(L2)，False=需要VIN码(L3)")] = True,
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("ask_user_car_info", sid, rid, {"reason": reason, "allow_select": allow_select})

    try:
        reply = await call_interrupt(ctx, {
            "type": "select_car",
            "question": reason,
            "allowSelect": allow_select,
        })

        # 前端回复格式：JSON 字符串 {"car_model_id": "xxx", "car_model_name": "xxx", "vin_code": "xxx"}
        import json
        try:
            data = json.loads(reply)
            car_model_id: str = data.get("car_model_id", "")
            car_model_name: str = data.get("car_model_name", "")
            vin_code: str = data.get("vin_code", "")
            if car_model_id:
                log_tool_end("ask_user_car_info", sid, rid, {
                    "car_model_id": car_model_id, "vin_code": vin_code,
                })
                result: str = f"用户选择车型：car_model_id={car_model_id}, car_model_name={car_model_name}"
                if vin_code:
                    result += f", vin_code={vin_code}"
                return result
        except (json.JSONDecodeError, AttributeError):
            pass

        # 前端可能直接返回纯文本
        if reply:
            return f"用户回复：{reply}"

        return "用户未提供车辆信息"

    except Exception as e:
        log_tool_end("ask_user_car_info", sid, rid, exc=e)
        return f"Error: ask_user_car_info failed - {e}"


ask_user_car_info.__doc__ = _DESCRIPTION
