"""list_user_cars 工具：查询用户车库中绑定的车辆列表。

场景：用户说"我的帕萨特"、"帮我那辆车查查"等指代自己名下的车辆。
"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.services.restful.list_user_cars_service import list_user_cars_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("list_user_cars")


async def list_user_cars(
    ctx: RunContext[AgentDeps],
) -> str:
    session_id = ctx.deps.session_id

    cars = await list_user_cars_service.get_user_cars(session_id)

    if not cars:
        return "用户没有绑定车辆"

    lines = [
        f"- car_model_id={c.car_model_id}, car_model_name={c.car_model_name}"
        for c in cars
    ]
    return f"用户车库（共 {len(cars)} 辆）：\n" + "\n".join(lines)


list_user_cars.__doc__ = _DESCRIPTION
