"""recommend_projects 工具：根据车辆信息查询推荐项目。"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.recommend_context import VehicleInfo
from src.services.restful.recommend_projects_service import query_recommend_projects
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("recommend_projects")


async def recommend_projects(
    ctx: RunContext[AgentDeps],
    vehicle_info: VehicleInfo,
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start(
        "recommend_projects", sid, rid,
        {
            "car_model_id": vehicle_info.car_model_id,
            "mileage": vehicle_info.mileage_km,
            "age": vehicle_info.car_age_year,
        },
    )

    try:
        result = await query_recommend_projects(
            car_key=vehicle_info.car_model_id,
            car_age_year=vehicle_info.car_age_year if vehicle_info.car_age_year is not None else 1.0,
            mileage_km=vehicle_info.mileage_km,
            session_id=sid,
            request_id=rid,
        )

        projects: list[dict[str, str]] = [
            {"project_id": p.project_id, "project_name": p.project_name}
            for p in result.projects
        ]

        log_tool_end("recommend_projects", sid, rid, {
            "project_count": len(projects),
            "auto_text": result.vehicle_info.auto_text,
        })

        # 用 API 返回的信息补充 vehicle_info
        if result.vehicle_info.auto_text and not vehicle_info.car_model_name:
            vehicle_info.car_model_name = result.vehicle_info.auto_text
        if result.vehicle_info.vin_code and not vehicle_info.vin_code:
            vehicle_info.vin_code = result.vehicle_info.vin_code
        if vehicle_info.car_age_year is None:
            if result.vehicle_info.month > 0:
                vehicle_info.car_age_year = round(result.vehicle_info.month / 12, 1)
            else:
                vehicle_info.car_age_year = 1.0

        vehicle_dict: dict[str, Any] = vehicle_info.model_dump(exclude_none=True)
        if result.vehicle_info.auto_logo:
            vehicle_dict["auto_logo"] = result.vehicle_info.auto_logo
        vehicle_dict["random_vin"] = result.vehicle_info.random_vin

        output: dict[str, Any] = {
            "vehicle_info": vehicle_dict,
            "projects": projects,
        }
        return json.dumps(output, ensure_ascii=False)

    except Exception as e:
        log_tool_end("recommend_projects", sid, rid, exc=e)
        return f"Error: recommend_projects failed - {e}"


recommend_projects.__doc__ = _DESCRIPTION
