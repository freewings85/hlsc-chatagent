"""search_shops 工具：按标准条件搜索商户并返回商户详情列表。

地址参数说明：
- address=None（不传）→ 使用用户当前位置（从 request_context 取，没有则 interrupt 让用户选点）
- address="南京西路" → 调 address service 转经纬度后搜索
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.address_resolver import resolve_location
from hlsc.services.restful.shop_service import shop_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("search_shops")


async def search_shops(
    ctx: RunContext[AgentDeps],
    address: Annotated[Optional[str], Field(description="目标地址，如'静安区南京西路'。不传则使用用户当前位置")] = None,
    shop_name: Annotated[str, Field(description="按门店名称搜索，仅用户明确说出具体店名时传入，描述性词语（如'技术好'、'口碑好'）不能传入")] = "",
    top: Annotated[int, Field(description="返回数量")] = 5,
    radius: Annotated[int, Field(description="搜索半径（米）")] = 10000,
    order_by: Annotated[str, Field(description="排序方式：distance/rating/tradingCount，可组合")] = "distance",
    commercial_type: Annotated[Optional[list[int]], Field(description="商户类型列表，用户未指定时不传")] = None,
    opening_hour: Annotated[Optional[str], Field(description="营业时间筛选，格式 HH:MM")] = None,
    project_ids: Annotated[Optional[str], Field(description="服务项目ID，逗号分隔")] = None,
    min_rating: Annotated[Optional[float], Field(description="最低评分")] = None,
    min_trading_count: Annotated[Optional[int], Field(description="最低成交量")] = None,
) -> str:
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_shops", sid, rid, {
        "address": address, "shop_name": shop_name,
        "top": top, "radius": radius, "order_by": order_by,
    })

    try:
        # 解析地址 → 经纬度
        location = await resolve_location(ctx, address, tool_name="search_shops")

        result = await shop_service.get_nearby_shops(
            lat=location.lat,
            lng=location.lng,
            keyword=shop_name,
            top=top,
            radius=radius,
            order_by=order_by,
            commercial_type=commercial_type,
            opening_hour=opening_hour,
            package_ids=project_ids,
            min_rating=min_rating,
            min_trading_count=min_trading_count,
            session_id=sid,
            request_id=rid,
        )

        commercials: list[dict] = result.get("commercials", []) if isinstance(result, dict) else []
        if not commercials:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            return f"{radius // 1000}km 范围内未找到符合条件的门店，建议扩大搜索范围"

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


search_shops.__doc__ = _DESCRIPTION
