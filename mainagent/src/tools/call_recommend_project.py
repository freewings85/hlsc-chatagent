"""call_recommend_project 工具：通过 A2A 调用 RecommendProject subagent。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent

from src.config import RECOMMEND_PROJECT_URL


async def call_recommend_project(
    ctx: RunContext[AgentDeps],
    query: str,
    vin_code: str = "",
    car_model_name: str = "",
    mileage_km: float = 0.0,
    car_age_year: float = 0.0,
) -> str:
    """调用 RecommendProject subagent，根据车辆里程数、车龄、车型推荐养车项目。

    根据车辆的实际状况（里程、车龄、车型），智能推荐需要做的维修保养项目。
    当推荐多个项目时，subagent 会中断返回项目列表让用户选择。

    Args:
        query: 用户的需求描述，如"我的车该做什么保养了"、"推荐养车项目"。
        vin_code: 车辆 VIN 码。
        car_model_name: 车型名称，如"2024款 宝马 325Li"。
        mileage_km: 当前里程数（千米）。
        car_age_year: 车龄（年）。

    Returns:
        推荐的养车项目信息 JSON。
    """
    # 车辆信息通过 context 传递，subagent 的 ContextFormatter 负责注入 LLM
    context = {
        "vehicle_info": {
            "vin_code": vin_code,
            "car_model_name": car_model_name,
            "mileage_km": mileage_km,
            "car_age_year": car_age_year,
        },
    }

    return await call_subagent(ctx, url=RECOMMEND_PROJECT_URL, message=query, context=context)
