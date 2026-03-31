"""call_recommend_project 工具：通过 A2A 调用 RecommendProject subagent。"""

from __future__ import annotations

import os

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("call_recommend_project")

RECOMMEND_PROJECT_URL: str = os.getenv("RECOMMEND_PROJECT_URL", "http://localhost:8105")


async def call_recommend_project(
    ctx: RunContext[AgentDeps],
    query: str,
    car_model_id: str | None = None,
) -> str:
    context: dict = {"car_model_id": car_model_id}
    return await call_subagent(
        ctx, url=RECOMMEND_PROJECT_URL, message=query, context=context
    )


call_recommend_project.__doc__ = _DESCRIPTION
