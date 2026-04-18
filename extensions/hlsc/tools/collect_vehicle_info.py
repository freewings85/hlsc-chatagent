"""collect_vehicle_info 工具：查询用户车库，返回车辆列表。

工具只负责查询，不做选择、不写 state。
LLM 根据用户描述从列表中判断选哪辆，确定后调 update_workflow_state 写入 car_id。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.get_my_car_service import MyCarModel, get_my_car_service
from hlsc.tools.prompt_loader import load_tool_prompt

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
    """查询用户车库，返回车辆列表。"""
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

    result: dict[str, Any] = {
        "total": len(candidates),
        "cars": candidates,
    }

    log_tool_end("collect_vehicle_info", sid, rid, {"total": len(candidates)})
    return json.dumps(result, ensure_ascii=False)


collect_vehicle_info.__doc__ = _DESCRIPTION
