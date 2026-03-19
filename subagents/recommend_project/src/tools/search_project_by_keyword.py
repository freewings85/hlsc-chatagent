"""search_project_by_keyword 工具：根据关键词聚合检索项目。"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.services.restful.search_project_by_trigger_service import search_project_by_trigger
from src.services.restful.search_project_by_fault_service import search_project_by_fault


async def search_project_by_keyword(
    ctx: RunContext[AgentDeps],
    keyword: Annotated[str, Field(description="用户描述的故障现象或需求关键词，如'空调异味'、'刹车软'、'火花塞'")],
) -> str:
    """根据关键词同时检索触发条件和故障信息，聚合返回匹配的项目。

    并行调用两个检索服务，将结果去重合并后返回。

    Args:
        keyword: 用户描述的故障现象或需求关键词。

    Returns:
        聚合后的项目列表 JSON。
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_project_by_keyword", sid, rid, {"keyword": keyword})

    try:
        trigger_results: list[dict[str, Any]]
        fault_results: list[dict[str, Any]]
        trigger_results, fault_results = await asyncio.gather(
            search_project_by_trigger(keyword),
            search_project_by_fault(keyword),
        )

        merged: list[dict[str, Any]] = _merge_results(trigger_results, fault_results)

        log_tool_end("search_project_by_keyword", sid, rid, {"count": len(merged)})
        return json.dumps({"projects": merged}, ensure_ascii=False)

    except Exception as e:
        log_tool_end("search_project_by_keyword", sid, rid, exc=e)
        return f"Error: search_project_by_keyword failed - {e}"


def _merge_results(
    trigger_results: list[dict[str, Any]],
    fault_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并两个来源的结果，按 title 去重。"""
    seen_titles: set[str] = set()
    merged: list[dict[str, Any]] = []

    for item in trigger_results + fault_results:
        title: str = item.get("title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        merged.append(item)

    return merged
