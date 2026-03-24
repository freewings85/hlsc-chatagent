"""ask_user_select_project 工具：展示项目列表给用户，等待用户选择。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt
from agent_sdk.logging import log_tool_start, log_tool_end
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("ask_user_select_project")


async def ask_user_select_project(
    ctx: RunContext[AgentDeps],
    projects: Annotated[list[dict[str, str]], Field(description="项目列表，每项含 project_id 和 project_name")],
    vehicle_info: Annotated[dict[str, Any], Field(description="当前车辆信息")],
    question: Annotated[str, Field(description="展示给用户的引导语")] = "以下是为您推荐的养车项目，请选择您感兴趣的项目：",
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("ask_user_select_project", sid, rid, {
        "project_count": len(projects),
        "question": question,
    })

    try:
        reply: str = await call_interrupt(ctx, {
            "type": "select_project",
            "question": question,
            "projects": projects,
            "vehicle_info": vehicle_info,
        })

        log_tool_end("ask_user_select_project", sid, rid, {"reply_length": len(reply)})

        # 尝试解析 JSON，提取 user_msg；否则原样返回
        try:
            data: dict[str, Any] = json.loads(reply)
            user_msg: str = str(data.get("user_msg", "")).strip()
            return user_msg if user_msg else reply
        except (json.JSONDecodeError, AttributeError):
            return reply.strip()

    except Exception as e:
        log_tool_end("ask_user_select_project", sid, rid, exc=e)
        return f"Error: ask_user_select_project failed - {e}"


ask_user_select_project.__doc__ = _DESCRIPTION
