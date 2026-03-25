"""call_query_codingagent 工具：通过 A2A 协议调用 QueryCodingAgent subagent。"""

from __future__ import annotations

import os
from uuid import uuid4

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("call_query_codingagent")

QUERY_CODINGAGENT_URL: str = os.getenv(
    "QUERY_CODINGAGENT_URL",
    os.getenv("CODE_AGENT_URL", "http://localhost:8102"),
)


async def call_query_codingagent(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    code_task_id = f"code-{ctx.deps.request_id[:8]}-{uuid4().hex[:8]}"
    context: dict[str, str] = {"code_task_id": code_task_id}
    return await call_subagent(
        ctx,
        url=QUERY_CODINGAGENT_URL,
        message=query,
        context=context,
    )


call_query_codingagent.__doc__ = _DESCRIPTION
