"""get_project_price 工具：查询项目在附近门店的报价。"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.query_project_price_service import (
    REPAIR_TYPE_NAMES,
    query_project_price_service,
)
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("get_project_price")


async def get_project_price(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[List[int], Field(description="项目 ID 列表")],
    car_model_id: Annotated[str, Field(description="车型编码")],
    lat: Annotated[float, Field(description="纬度")],
    lng: Annotated[float, Field(description="经度")],
    distance_km: Annotated[int, Field(description="搜索距离范围（公里）")] = 10,
    min_rating: Annotated[Optional[float], Field(description="最低评分过滤（如 4.8）")] = None,
    shop_ids: Annotated[Optional[List[str]], Field(description="指定门店 ID 列表")] = None,
    sort_by: Annotated[str, Field(description="排序方式：distance / rating / price")] = "distance",
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("get_project_price", sid, rid, {
        "project_ids": project_ids, "car_model_id": car_model_id,
        "distance_km": distance_km, "min_rating": min_rating,
        "shop_ids": shop_ids, "sort_by": sort_by,
    })

    try:
        result = await query_project_price_service.query_nearby(
            project_ids=project_ids,
            car_model_id=car_model_id,
            lat=lat,
            lng=lng,
            session_id=sid,
            request_id=rid,
            distance_km=distance_km,
            min_rating=min_rating,
            shop_ids=shop_ids,
            sort_by=sort_by,
        )

        if not result.shops:
            log_tool_end("get_project_price", sid, rid, {"shop_count": 0})
            return "附近未找到提供相关项目的门店"

        summary: str = _build_summary(result, distance_km, min_rating, sort_by)

        log_tool_end("get_project_price", sid, rid, {
            "shop_count": len(result.shops),
            "shops": [s.shop_name for s in result.shops],
        })
        return summary

    except Exception as e:
        log_tool_end("get_project_price", sid, rid, exc=e)
        return f"Error: get_project_price failed - {e}"


def _build_summary(result: object, distance_km: int, min_rating: Optional[float], sort_by: str) -> str:
    shops = result.shops  # type: ignore[attr-defined]
    filter_desc: str = f"{distance_km}km 范围内"
    if min_rating:
        filter_desc += f"、评分 {min_rating} 以上"
    sort_desc: str = {"distance": "按距离", "rating": "按评分", "price": "按价格"}.get(sort_by, "")

    lines: list[str] = [f"在{filter_desc}找到 {len(shops)} 家门店的报价（{sort_desc}排序）：", ""]

    for shop in shops:
        rating_text: str = f", 评分{shop.rating}" if shop.rating else ""
        lines.append(f"**{shop.shop_name}**(shopId={shop.shop_id}, {shop.distance_km}km{rating_text}):")

        for proj in shop.projects:
            lines.append(f"  {proj.name}(projectId={proj.id}):")
            if proj.plans:
                for plan in proj.plans:
                    type_label: str = REPAIR_TYPE_NAMES.get(plan.type, plan.type)
                    qa_text: str = f", 保质期{plan.qa}" if plan.qa else ""
                    lines.append(f"    {plan.name}(type={plan.type}): ¥{plan.price}{qa_text}")
            else:
                lines.append(f"    暂无报价")

    lines.append("")
    lines.append("[业务提示] 以上是门店项目报价（含工时和配件），可直接下单。")

    return "\n".join(lines)


get_project_price.__doc__ = _DESCRIPTION
