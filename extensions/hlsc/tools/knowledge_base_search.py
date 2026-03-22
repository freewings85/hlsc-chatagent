"""knowledge_base_search 工具：知识库搜索辅助意图澄清（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def knowledge_base_search(
    ctx: RunContext[AgentDeps],
    query: Annotated[str, Field(description="搜索关键词或车主描述")],
) -> str:
    """搜索知识库，辅助澄清车主模糊意图，返回相关养车项目和知识。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("knowledge_base_search", sid, rid, {"query": query})
    log_tool_end("knowledge_base_search", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "knowledge_base_search 尚未实现，请通过对话直接澄清车主意图"}'
