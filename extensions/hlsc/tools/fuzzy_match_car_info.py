"""fuzzy_match_car_info 工具：根据车型关键词模糊匹配车型信息。

场景：用户提到一个车型名（如"卡罗拉"），需要匹配出 car_model_id。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.services.restful.fuzzy_match_car_service import fuzzy_match_car_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("fuzzy_match_car_info")


async def fuzzy_match_car_info(
    ctx: RunContext[AgentDeps],
    query: Annotated[str, Field(description="车型关键词，如'宝马X3'、'奔驰C级'、'卡罗拉'")],
) -> str:
    session_id = ctx.deps.session_id

    car_info = await fuzzy_match_car_service.match(query, session_id=session_id)

    if not car_info:
        return f"未找到匹配'{query}'的车型"

    return (
        f"匹配车型：car_model_id={car_info.car_model_id}, "
        f"car_model_name={car_info.car_model_name}"
    )


# 设置 tool description（从外部 prompt 文件加载）
fuzzy_match_car_info.__doc__ = _DESCRIPTION
