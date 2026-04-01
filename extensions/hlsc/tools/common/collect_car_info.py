"""collect_car_info 工具：触发车辆信息收集界面，按所需精度收集车辆信息。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.enums import (
    REQUIRED_PRECISION_EXACT_MODEL,
    REQUIRED_PRECISION_VIN,
    RequiredCarPrecision,
)
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("collect_car_info")


async def collect_car_info(
    ctx: RunContext[AgentDeps],
    reason: Annotated[str, Field(description="需要车辆信息的原因，如'查询报价需要知道您的车型'")],
    required_precision: Annotated[
        RequiredCarPrecision,
        Field(description="当前需要补齐到的车型精度。exact_model=精确车型，vin=VIN"),
    ] = REQUIRED_PRECISION_EXACT_MODEL,
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    allow_select: bool = required_precision == REQUIRED_PRECISION_EXACT_MODEL
    log_tool_start(
        "collect_car_info",
        sid,
        rid,
        {"reason": reason, "required_precision": required_precision, "allow_select": allow_select},
    )

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
            precision_ok: bool = (
                bool(car_model_id)
                if required_precision == REQUIRED_PRECISION_EXACT_MODEL
                else required_precision == REQUIRED_PRECISION_VIN and bool(car_model_id and vin_code)
            )
            if precision_ok:
                log_tool_end("collect_car_info", sid, rid, {
                    "car_model_id": car_model_id, "vin_code": vin_code, "required_precision": required_precision,
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
        log_tool_end("collect_car_info", sid, rid, exc=e)
        return f"Error: collect_car_info failed - {e}"


collect_car_info.__doc__ = _DESCRIPTION
