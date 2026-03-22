"""search_nearby_shops 工具：按位置搜索附近商户（stub，待实现）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def search_nearby_shops(
    ctx: RunContext[AgentDeps],
    latitude: Annotated[float, Field(description="纬度")],
    longitude: Annotated[float, Field(description="经度")],
    project_type: Annotated[str, Field(description="项目类型，影响默认搜索距离")] = "",
    warranty_status: Annotated[str, Field(description="保修状态：in_warranty/out_warranty/unknown")] = "unknown",
) -> str:
    """按位置搜索附近商户，入参支持项目类型和保修状态以影响推荐策略。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_nearby_shops", sid, rid, {
        "lat": latitude, "lng": longitude,
        "project_type": project_type, "warranty_status": warranty_status,
    })
    log_tool_end("search_nearby_shops", sid, rid, {"status": "stub"})
    return '{"status": "error", "notice": "search_nearby_shops 尚未实现，当前可通过 get_project_price 间接获取附近门店"}'
