"""search_fault_symptoms 工具：从故障现象库检索已知故障模式。"""

from __future__ import annotations

from typing import Annotated, List

from pydantic import Field
from pydantic_ai import RunContext

import asyncio

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.services.restful.car_fault_retrieval_service import (
    FaultItem,
    car_fault_retrieval_service,
)
from src.services.restful.get_part_primary_service import get_main_part_ids
from src.services.restful.get_project_bycar_service import get_project_ids_by_car


async def search_fault_symptoms(
    ctx: RunContext[AgentDeps],
    car_model_id: Annotated[str, Field(description="车型编码")],
    query: Annotated[str, Field(description="故障现象描述，如'过减速带咚咚响'、'方向盘抖'")],
) -> str:
    """从故障现象库中检索与描述相关的已知故障模式。

    会根据车型的零部件和项目清单过滤结果，确保返回的故障与该车型相关。

    IMPORTANT: 故障库数据可能不全，检索结果仅作参考。应结合你自身的汽车知识综合判断。
    """
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("search_fault_symptoms", sid, rid, {"car_model_id": car_model_id, "query": query})

    try:
        # 1. 并行获取车型的零部件 ID 和项目 ID（用于过滤检索结果）
        part_ids, project_ids = await asyncio.gather(
            get_main_part_ids(car_model_id, sid, rid),
            get_project_ids_by_car(car_model_id, sid, rid),
        )

        # 2. 用车型信息过滤检索故障现象
        result = await car_fault_retrieval_service.retrieval(
            query,
            session_id=sid,
            request_id=rid,
            primary_part_ids=part_ids or None,
            primary_project_ids=project_ids or None,
        )

        if not result.items:
            log_tool_end("search_fault_symptoms", sid, rid, {"count": 0})
            return "未找到匹配的故障现象"

        formatted = _format_fault_items(result.items)
        log_tool_end("search_fault_symptoms", sid, rid, {"count": len(result.items)})
        return formatted

    except Exception as e:
        log_tool_end("search_fault_symptoms", sid, rid, exc=e)
        return f"Error: search_fault_symptoms failed - {e}"


def _format_fault_items(items: List[FaultItem]) -> str:
    blocks = []
    for i, item in enumerate(items, 1):
        lines = [f"故障{i}: {item.title}"]
        lines.append(item.content)

        if item.primary_part_ids:
            part_names = [n.strip() for n in (item.primary_part_names or "").split(",") if n.strip()]
            lines.append(f"关联零部件: {_format_id_name_pairs(item.primary_part_ids, part_names)}")

        if item.primary_project_ids:
            project_names = [n.strip() for n in (item.primary_project_names or "").split(",") if n.strip()]
            lines.append(f"关联项目: {_format_id_name_pairs(item.primary_project_ids, project_names)}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _format_id_name_pairs(ids: List[int], names: List[str]) -> str:
    pairs = []
    for j, pid in enumerate(ids):
        if j < len(names) and names[j]:
            pairs.append(f"{names[j]}(id={pid})")
        else:
            pairs.append(f"id={pid}")
    return ", ".join(pairs)


def create_diagnose_tool_map() -> dict:
    return {"search_fault_symptoms": search_fault_symptoms}
