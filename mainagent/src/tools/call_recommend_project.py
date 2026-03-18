"""call_recommend_project 工具：通过 A2A 调用 RecommendProject subagent。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent

from src.config import RECOMMEND_PROJECT_URL


async def call_recommend_project(
    ctx: RunContext[AgentDeps],
    query: str,
    car_model_id: str | None = None,
    vin_code: str | None = None,
    car_model_name: str | None = None,
    mileage_km: float | None = None,
    car_age_year: float = 0.0,
) -> str:
    """调用 RecommendProject subagent，根据车辆里程数、车龄、车型推荐养车项目。

    当用户想知道车辆需要做什么保养/维修项目时（如"推荐什么项目"、"该做什么保养了"、"跑了xx公里需要做什么"），根据车辆状况智能推荐养车项目。

    调用前置条件：
    - car_model_id 不是必填项。仅当用户主动提到车型相关信息（品牌、车系、车型）时，
      先通过 fuzzy_match_car_info 获取 car_model_id 后传入。
    - car_age_year 必填。用户提到车龄则直接换算后传入；未提及则先向用户询问。

    Args:
        query: 用户的需求描述，如"我的车该做什么保养了"、"推荐养车项目"。
        car_model_id: 车型编码。用户未提及车型信息时不传。
        vin_code: 车辆 VIN 码。用户未提及时不传。
        car_model_name: 车型名称，如"2024款 宝马 325Li"。用户未提及时不传。
        mileage_km: 当前里程数（千米）。用户未提及时不传。
        car_age_year: 车龄（年），必填。

    Returns:
        推荐的养车项目信息 JSON。
    """
    # 车辆信息通过 context 传递，subagent 的 ContextFormatter 负责注入 LLM
    context = {
        "vehicle_info": {
            "car_model_id": car_model_id,
            "vin_code": vin_code,
            "car_model_name": car_model_name,
            "mileage_km": mileage_km,
            "car_age_year": car_age_year,
        },
    }
    return await call_subagent(ctx, url=RECOMMEND_PROJECT_URL, message=query, context=context)
