"""fuzzy_match_car_info 工具：根据车型关键词模糊匹配车型信息。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.fuzzy_match_car_service import fuzzy_match_car_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("fuzzy_match_car_info")


async def fuzzy_match_car_info(
    ctx: RunContext[AgentDeps],
    query: Annotated[str, Field(description="车型关键词，如'宝马X3'、'奔驰C级'、'卡罗拉'")],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("fuzzy_match_car_info", sid, rid, {"query": query})

    try:
        car_info = await fuzzy_match_car_service.match(query, session_id=sid, request_id=rid)

        if not car_info:
            log_tool_end("fuzzy_match_car_info", sid, rid, {"matched": False})
            return f"未找到匹配'{query}'的车型"

        log_tool_end("fuzzy_match_car_info", sid, rid, {
            "matched": True, "car_model_id": car_info.car_model_id,
        })
        return (
            f"匹配车型：car_model_id={car_info.car_model_id}, "
            f"car_model_name={car_info.car_model_name}"
        )
    except Exception as e:
        log_tool_end("fuzzy_match_car_info", sid, rid, exc=e)
        return f"Error: fuzzy_match_car_info failed - {e}"


fuzzy_match_car_info.__doc__ = _DESCRIPTION
