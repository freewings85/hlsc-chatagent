"""search_shops 工具：按标准条件搜索商户并返回商户详情列表。

位置参数通过 LocationFilter 对象传入，支持范围搜索和区域过滤。
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.models.location_filter import LocationFilter
from hlsc.services.address_resolver import resolve_location_filter
from hlsc.services.restful.shop_service import shop_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DEFAULT_RADIUS: int = int(os.getenv("SEARCH_SHOPS_DEFAULT_RADIUS", "20000"))

_DESCRIPTION = load_tool_prompt("search_shops")


async def search_shops(
    ctx: RunContext[AgentDeps],
    location: Annotated[Optional[LocationFilter], Field(description="位置条件。address=范围搜索中心点，radius=搜索半径（米，不传默认20公里），city/district/street=区域过滤")] = None,
    shop_name: Annotated[str, Field(description="按门店名称搜索，仅用户明确说出具体店名时传入")] = "",
    top: Annotated[int, Field(description="返回数量")] = 5,
    order_by: Annotated[str, Field(description="排序方式：distance/rating/tradingCount，可组合")] = "distance",
    commercial_type: Annotated[Optional[list[int]], Field(description="商户类型列表，用户未指定时不传")] = None,
    opening_hour: Annotated[Optional[str], Field(description="营业时间筛选，格式 HH:MM")] = None,
    project_ids: Annotated[Optional[str], Field(description="服务项目ID，逗号分隔")] = None,
    min_rating: Annotated[Optional[float], Field(description="最低评分")] = None,
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_shops", sid, rid, {
        "location": location.model_dump() if location else None,
        "shop_name": shop_name, "top": top, "order_by": order_by,
    })

    try:
        # 解析位置条件
        resolved = await resolve_location_filter(ctx, location, tool_name="search_shops")

        # 搜索半径：LocationFilter.radius 或环境变量默认值
        actual_radius: int = resolved.radius if resolved.radius else _DEFAULT_RADIUS

        result = await shop_service.get_nearby_shops(
            lat=resolved.lat or 0.0,
            lng=resolved.lng or 0.0,
            keyword=shop_name,
            top=top,
            radius=actual_radius,
            order_by=order_by,
            commercial_type=commercial_type,
            opening_hour=opening_hour,
            project_ids=project_ids,
            min_rating=min_rating,
            session_id=sid,
            request_id=rid,
        )

        commercials: list[dict] = result.get("commercials", []) if isinstance(result, dict) else []

        # 区域过滤（后端 API 未支持的字段在这里补过滤）
        if resolved.has_filter:
            commercials = _apply_filter(commercials, resolved)

        if not commercials:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            desc: str = resolved.address or resolved.district or resolved.city or f"{actual_radius // 1000}km 范围"
            return f"{desc}内未找到符合条件的门店"

        shops: list[dict] = []
        for item in commercials:
            distance_m: int = item.get("distance", 0)
            distance_km: float = round(distance_m / 1000, 1) if distance_m else 0

            svc: str = item.get("serviceScope", "")
            tag_list: list[str] = [t.strip() for t in svc.split(",") if t.strip()] if svc else []

            shops.append({
                "shop_id": item.get("commercialId", ""),
                "name": item.get("commercialName", ""),
                "address": item.get("address", ""),
                "province": item.get("provinceName", ""),
                "city": item.get("cityName", ""),
                "district": item.get("districtName", ""),
                "commercial_type": item.get("commercialType"),
                "distance_m": distance_m,
                "distance": f"{distance_km}km",
                "rating": item.get("rating"),
                "trading_count": item.get("tradingCount", 0),
                "phone": item.get("phone", ""),
                "tags": tag_list,
                "images": item.get("imageObject", []),
                "opening_hours": item.get("openingHours", ""),
            })

        log_tool_end("search_shops", sid, rid, {
            "shop_count": len(shops),
            "shops": [s["name"] for s in shops],
        })
        return json.dumps({"total": len(shops), "shops": shops}, ensure_ascii=False)

    except Exception as e:
        log_tool_end("search_shops", sid, rid, exc=e)
        return f"Error: search_shops failed - {e}"


def _apply_filter(commercials: list[dict], resolved: object) -> list[dict]:
    """按区域过滤条件筛选商户列表。"""
    filtered: list[dict] = []
    city: str = getattr(resolved, "city", "")
    district: str = getattr(resolved, "district", "")
    street: str = getattr(resolved, "street", "")

    for item in commercials:
        if city and city not in (item.get("cityName", "") or ""):
            continue
        if district and district not in (item.get("districtName", "") or ""):
            continue
        if street and street not in (item.get("address", "") or ""):
            continue
        filtered.append(item)

    return filtered


search_shops.__doc__ = _DESCRIPTION
