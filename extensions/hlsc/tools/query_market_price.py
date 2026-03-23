"""query_market_price 工具：查询项目的市场行情参考价。"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.query_project_price_service import REPAIR_TYPE_NAMES
from hlsc.services.restful.query_market_price_service import (
    MarketPriceResult,
    MarketProject,
    query_market_price_service,
)
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("query_market_price")


async def query_market_price(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[List[int], Field(description="项目 ID 列表，必须来自 match_project 返回结果")],
    car_model_id: Annotated[str, Field(description="车型编码（L2 精度：品牌+车系+年款+排量）")],
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("query_market_price", sid, rid, {
        "project_ids": project_ids, "car_model_id": car_model_id,
    })

    try:
        result: MarketPriceResult = await query_market_price_service.query(
            project_ids=project_ids,
            car_model_id=car_model_id,
            session_id=sid,
            request_id=rid,
        )

        if not result.projects:
            log_tool_end("query_market_price", sid, rid, {"project_count": 0})
            return "未找到相关项目的行情价"

        summary: str = _build_summary(result)

        log_tool_end("query_market_price", sid, rid, {
            "project_count": len(result.projects),
            "projects": [p.project_name for p in result.projects],
        })
        return summary

    except Exception as e:
        log_tool_end("query_market_price", sid, rid, exc=e)
        return f"Error: query_market_price failed - {e}"


def _build_summary(result: MarketPriceResult) -> str:
    """格式化行情价查询结果。"""
    lines: list[str] = [f"查询到 {len(result.projects)} 个项目的行情价：", ""]

    for proj in result.projects:
        lines.append(f"**{proj.project_name}**(projectId={proj.project_id}):")
        if proj.plans:
            for plan in proj.plans:
                type_label: str = REPAIR_TYPE_NAMES.get(plan.type, plan.type)
                qa_text: str = f"，保质期{plan.qa}" if plan.qa else ""
                lines.append(f"  {type_label}: ¥{plan.price}{qa_text}")
        else:
            lines.append("  暂无行情数据")

    lines.append("")
    lines.append("[业务提示] 以上是市场行情参考价，实际门店报价可能有差异。")

    return "\n".join(lines)


query_market_price.__doc__ = _DESCRIPTION
