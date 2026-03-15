"""list_user_cars 工具：查询用户车库中绑定的车辆列表。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.list_user_cars_service import list_user_cars_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("list_user_cars")


async def list_user_cars(
    ctx: RunContext[AgentDeps],
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("list_user_cars", sid, rid)

    try:
        cars = await list_user_cars_service.get_user_cars(sid, request_id=rid)

        if not cars:
            log_tool_end("list_user_cars", sid, rid, {"count": 0})
            return "用户没有绑定车辆"

        log_tool_end("list_user_cars", sid, rid, {"count": len(cars)})
        lines = [
            f"- car_model_id={c.car_model_id}, car_model_name={c.car_model_name}"
            for c in cars
        ]
        return f"用户车库（共 {len(cars)} 辆）：\n" + "\n".join(lines)
    except Exception as e:
        log_tool_end("list_user_cars", sid, rid, exc=e)
        return f"Error: list_user_cars failed - {e}"


list_user_cars.__doc__ = _DESCRIPTION
