"""MainAgent 工具：按需查看业务地图节点的完整定义。

当切片中 description 引用了其他节点时，MainAgent 调用此工具获取该节点的
完整业务定义（description、checklist、output、depends_on、cancel_directions）。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.business_map_service import business_map_service


async def read_business_node(
    ctx: RunContext[AgentDeps],
    node_id: Annotated[str, Field(description="要查看的业务节点 ID（如 confirm_project、fuzzy_intent）")],
) -> str:
    """查看指定业务节点的完整业务定义。

    返回该节点的 description、checklist、output、depends_on、cancel_directions 等内容。
    当切片中提到某个节点需要进一步了解、或需要查看某节点的具体 checklist 和取消走向时使用。
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("read_business_node", sid, rid, {"node_id": node_id})

    try:
        result: str = business_map_service.get_business_node_detail(node_id)
    except KeyError:
        result = f"节点 '{node_id}' 不存在于业务地图中。"
    except RuntimeError as e:
        result = f"业务地图服务未加载: {e}"

    log_tool_end("read_business_node", sid, rid, {"length": len(result)})
    return result
