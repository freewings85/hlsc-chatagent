"""fuzzy_match_car_info 工具：根据车型关键词模糊匹配车型信息。

场景：用户提到一个车型名（如"卡罗拉"），需要匹配出 car_model_id。
"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.services.restful.fuzzy_match_car_service import fuzzy_match_car_service


async def fuzzy_match_car_info(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """根据车型关键词模糊匹配车型信息，返回 car_model_id 和 car_model_name。

    当用户提到一个车型名称（如"宝马X3"、"卡罗拉"）但不是指自己名下的车时，
    调用此工具从车型库中匹配最接近的车型。

    Args:
        query: 车型关键词，如"宝马X3"、"奔驰C级"、"卡罗拉"。

    Returns:
        匹配结果（含 car_model_id、car_model_name），或未找到的提示。
    """
    session_id = ctx.deps.session_id

    car_info = await fuzzy_match_car_service.match(query, session_id=session_id)

    if not car_info:
        return f"未找到匹配'{query}'的车型"

    return (
        f"匹配车型：car_model_id={car_info.car_model_id}, "
        f"car_model_name={car_info.car_model_name}\n"
        f"注意：这是根据关键词匹配的车型，请在回复中告知用户按哪个车型查询，"
        f"并提示如果车型不对可以修改。"
    )
