"""recommend_projects_api 工具：根据车辆信息和推荐分类获取推荐项目。"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.recommend_context import VehicleInfo
from src.services.restful.recommend_projects_service import query_recommend_projects


async def recommend_projects_api(
    ctx: RunContext[AgentDeps],
    vehicle_info: VehicleInfo,
    category_ids: list[int] = [],
) -> str:
    """根据车辆信息和推荐分类，调用项目推荐接口获取推荐养车项目。

    调用前置规则：
    1. car_age_year 必须有值。用户未提及车龄时先询问。
    2. category_ids 根据 car_age_year 确定（严格按以下规则，不可自行编造）：
       - car_age_year < 3 → category_ids = [5]
       - 3 <= car_age_year < 6 → category_ids = [3,4]
       - car_age_year >= 6 → category_ids = [2]
    3. car_model_id 可选但建议获取：
       - 上下文中已有 car_model_id → 直接填入 vehicle_info
       - 用户提到了车型信息（如品牌、车系） → 先调用 fuzzy_match_car_info 获取，再填入
       - 都没有 → 留空即可，不影响推荐

    Args:
        vehicle_info: 车辆信息，包含车型编码、里程数、车龄等。
        category_ids: 项目分类 ID 列表，按上述规则确定。

    Returns:
        推荐的养车项目 JSON。
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start(
        "recommend_projects_api", sid, rid,
        {
            "car_model_id": vehicle_info.car_model_id,
            "mileage": vehicle_info.mileage_km,
            "age": vehicle_info.car_age_year,
            "categories": category_ids,
        },
    )

    try:
        projects: list[dict[str, Any]] = await query_recommend_projects(
            car_key=vehicle_info.car_model_id,
            category_ids=category_ids,
            car_age_year=vehicle_info.car_age_year,
            mileage_km=vehicle_info.mileage_km,
        )

        log_tool_end("recommend_projects_api", sid, rid, {"project_count": len(projects)})
        return json.dumps({
            "vehicle_info": vehicle_info.model_dump(exclude_none=True),
            "projects": projects,
        }, ensure_ascii=False)

    except Exception as e:
        log_tool_end("recommend_projects_api", sid, rid, exc=e)
        return f"Error: recommend_projects_api failed - {e}"
