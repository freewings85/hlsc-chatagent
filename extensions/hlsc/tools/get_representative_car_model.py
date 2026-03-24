"""get_representative_car_model 工具：获取代表性的具体车型 car_model_id。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.fuzzy_match_car_service import fuzzy_match_car_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("get_representative_car_model")


async def get_representative_car_model(
    ctx: RunContext[AgentDeps],
    car_model_keyword: Annotated[str, Field(description="车型关键词，如'宝马X3'、'奔驰C级'、'卡罗拉'")],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("get_representative_car_model", sid, rid, {"car_model_keyword": car_model_keyword})

    try:
        car_info = await fuzzy_match_car_service.match(car_model_keyword, session_id=sid, request_id=rid)

        if not car_info:
            log_tool_end("get_representative_car_model", sid, rid, {"matched": False})
            return json.dumps({
                "matched": False,
                "car_model_keyword": car_model_keyword,
            }, ensure_ascii=False)

        result = {
            "car_model_id": car_info.car_model_id,
            "car_model_name": car_info.car_model_name,
            "notice": "仅是挑选了代表性车型，不代表精确车型。",
        }
        log_tool_end("get_representative_car_model", sid, rid, {
            "matched": True,
            "car_model_id": car_info.car_model_id,
        })
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        log_tool_end("get_representative_car_model", sid, rid, exc=e)
        return f"Error: get_representative_car_model failed - {e}"


get_representative_car_model.__doc__ = _DESCRIPTION
