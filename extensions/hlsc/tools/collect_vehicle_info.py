"""collect_vehicle_info 工具：查询用户车库并确定 car_id。

- 0 辆 → 自动写 car_id=""，返回 no_cars
- 1 辆 → 自动写 car_id，返回 auto_selected
- 多辆 → 返回候选列表，LLM 判断后调 update_workflow_state 写入
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.get_my_car_service import MyCarModel, get_my_car_service
from hlsc.tools.prompt_loader import load_tool_prompt
from hlsc.tools.update_workflow_state import update_workflow_state

_DESCRIPTION = load_tool_prompt("collect_vehicle_info")
_CAR_KEY_PREFIX: str = "my_"


def _extract_car_id(car_key: str | None) -> str | None:
    """从 car_key（如 my_3483）去掉 my_ 前缀，得到 car_id（如 3483）。"""
    if not car_key:
        return None
    if car_key.startswith(_CAR_KEY_PREFIX):
        return car_key[len(_CAR_KEY_PREFIX):]
    return car_key


def _build_candidate(car: MyCarModel) -> dict[str, str]:
    """从 MyCarModel 抽取展示给 LLM 的字段。"""
    return {
        "car_id": _extract_car_id(car.car_key) or "",
        "car_name": car.car_name or "",
    }


async def collect_vehicle_info(
    ctx: RunContext[AgentDeps],
) -> str:
    """查询用户车库并确定 car_id。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    user_id_str: str = ctx.deps.user_id
    log_tool_start("collect_vehicle_info", sid, rid)

    try:
        user_id_int: int = int(user_id_str)
        cars: list[MyCarModel] = await get_my_car_service.get_my_cars(
            session_id=sid, user_id=user_id_int, request_id=rid,
        )
    except (ValueError, RuntimeError):
        cars = []

    candidates: list[dict[str, str]] = [_build_candidate(c) for c in cars]

    if not candidates:
        await update_workflow_state(ctx, {"car_id": ""})
        result: dict[str, Any] = {"status": "no_cars"}
    elif len(candidates) == 1:
        picked_id: str = candidates[0]["car_id"]
        await update_workflow_state(ctx, {"car_id": picked_id})
        result = {"status": "auto_selected", "car_id": picked_id, "car_name": candidates[0]["car_name"]}
    else:
        # 多辆 → 先写空 car_id（不卡 workflow），返回列表让 LLM 反问用户
        await update_workflow_state(ctx, {"car_id": ""})
        result = {"status": "need_selection", "cars": candidates}

    log_tool_end("collect_vehicle_info", sid, rid, result)
    return json.dumps(result, ensure_ascii=False)


collect_vehicle_info.__doc__ = _DESCRIPTION
