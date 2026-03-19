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
) -> str:
    """调用养车服务 subagent，处理两类场景：

    1. 推荐养车项目：用户不确定需要做什么，想根据车辆状况获取保养/维修建议。
       示例："推荐什么项目"、"该做什么保养了"、"跑了3万公里需要做什么"

    2. 故障诊断：用户描述了车辆异常现象或故障症状，需要分析原因并推荐维修项目。
       示例："刹车有异响"、"方向盘抖"、"发动机故障灯亮了"、"过减速带咚咚响"

    Args:
        query: 用户的完整需求描述，应包含用户提到的所有车辆信息（如里程、车龄、故障症状等）。
        car_model_id: 车型编码。如果上下文中已有（如 current_car），直接传入；没有则不传，subagent 会自行处理。

    Returns:
        subagent 的响应结果。
    """
    context: dict = {"car_model_id": car_model_id}
    return await call_subagent(
        ctx, url=RECOMMEND_PROJECT_URL, message=query, context=context
    )
