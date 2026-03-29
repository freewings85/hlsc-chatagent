"""get_business_node 工具：获取指定业务节点的导航信息。"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.business_map_service import BusinessMapService

logger: logging.Logger = logging.getLogger(__name__)

# 模块级引用，由 app.py 启动时设置
_service: BusinessMapService | None = None


def set_service(service: BusinessMapService) -> None:
    """设置 BusinessMapService 实例（app.py 启动时调用）。"""
    global _service
    _service = service


def _get_service() -> BusinessMapService:
    """获取 service 实例，未初始化时抛异常。"""
    if _service is None:
        raise RuntimeError("BusinessMapService 未初始化，请先调用 set_service()")
    return _service


async def get_business_node(
    ctx: RunContext[AgentDeps],
    node_id: Annotated[str, Field(description="要查看的业务节点 ID")],
) -> str:
    """获取单个业务节点的导航详情（id、name、keywords、是否有子节点）。与 get_business_children 不同：本工具返回单个节点信息，get_business_children 返回子节点列表。当需要确认某个节点是否为叶节点时使用。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {"node_id": node_id}
    log_tool_start("get_business_node", sid, rid, params)

    try:
        service: BusinessMapService = _get_service()
        result: str = service.get_business_node_nav(node_id)
        log_tool_end("get_business_node", sid, rid, {"node_id": node_id, "result_len": len(result)})
        return result
    except KeyError:
        error_msg: str = f"节点 '{node_id}' 不存在。请检查 node_id 是否正确。"
        log_tool_end("get_business_node", sid, rid, {"error": error_msg})
        return error_msg
