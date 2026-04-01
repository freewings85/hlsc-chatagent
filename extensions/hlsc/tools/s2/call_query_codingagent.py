"""call_query_codingagent 工具：通过 A2A 协议调用 QueryCodingAgent subagent。"""

from __future__ import annotations

import os
from typing import Final
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

_QUERY_PREFIX = """All available API docs are under the `/apis` directory, and the index is `/apis/index.md`.
Read the index first, then read only the docs actually needed for this task.
Use the relevant APIs and Python code to try to solve the task below.
You may use only Python standard library, `httpx`, and `numpy`.
If you cannot complete the task, return only the clear reason.

# Task
"""

_RETRY_PREFIX = """Your previous reply was invalid because you printed pseudo tool-call text instead of using tools.
Do not print tool arguments, JSON wrappers, file-path JSON, or search-pattern JSON as normal text.
Read the needed docs, run Python if needed, and return only the actual result or the clear failure reason.

# Task
"""

_PSEUDO_TOOL_MARKERS: Final[tuple[str, ...]] = (
    "tool_uses",
    "recipient_name",
    "functions.read",
    "functions.grep",
    '{"file_path":',
    '{"pattern":',
)


def _looks_like_pseudo_tool_output(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _PSEUDO_TOOL_MARKERS)


async def call_query_codingagent(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    code_task_id = f"code-{ctx.deps.request_id[:8]}-{uuid4().hex[:8]}"
    context: dict[str, str] = {"code_task_id": code_task_id}
    clean_query = query.strip()
    wrapped_query = f"{_QUERY_PREFIX}{clean_query}"
    result = await call_subagent(
        ctx,
        url=QUERY_CODINGAGENT_URL,
        message=wrapped_query,
        context=context,
    )
    if not _looks_like_pseudo_tool_output(result):
        return result

    retry_query = f"{_RETRY_PREFIX}{clean_query}"
    retry_result = await call_subagent(
        ctx,
        url=QUERY_CODINGAGENT_URL,
        message=retry_query,
        context=context,
    )
    if _looks_like_pseudo_tool_output(retry_result):
        return "查询编码代理未能正确执行工具或代码，暂时无法完成本次查询。"
    return retry_result


call_query_codingagent.__doc__ = _DESCRIPTION
