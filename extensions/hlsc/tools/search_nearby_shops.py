"""search_nearby_shops 工具：按位置搜索附近商户。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.shop_service import shop_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION = load_tool_prompt("search_nearby_shops")


async def search_nearby_shops(
    ctx: RunContext[AgentDeps],
    latitude: Annotated[float, Field(description="纬度")],
    longitude: Annotated[float, Field(description="经度")],
    keyword: Annotated[str, Field(description="搜索关键词，如门店名称、品牌、服务类型")] = "",
    top: Annotated[int, Field(description="返回数量")] = 5,
    radius: Annotated[int, Field(description="搜索半径（米）")] = 10000,
    order_by: Annotated[str, Field(description="排序方式：distance/rating/tradingCount，可组合")] = "distance",
    commercial_type: Annotated[list[int] | None, Field(description="商户类型列表，用户未指定时不传")] = None,
    opening_hour: Annotated[str | None, Field(description="营业时间筛选，格式 HH:MM")] = None,
    province_id: Annotated[int | None, Field(description="省份ID")] = None,
    city_id: Annotated[int | None, Field(description="城市ID")] = None,
    district_id: Annotated[int | None, Field(description="区县ID")] = None,
    address_name: Annotated[str | None, Field(description="地址名称搜索")] = None,
    package_ids: Annotated[str | None, Field(description="服务项目ID，逗号分隔")] = None,
    min_rating: Annotated[float | None, Field(description="最低评分")] = None,
    min_trading_count: Annotated[int | None, Field(description="最低成交量")] = None,
) -> str:
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("search_nearby_shops", sid, rid, {
        "lat": latitude, "lng": longitude, "keyword": keyword,
        "top": top, "radius": radius, "order_by": order_by,
    })

    try:
        result = await shop_service.get_nearby_shops(
            lat=latitude,
            lng=longitude,
            keyword=keyword,
            top=top,
            radius=radius,
            order_by=order_by,
            commercial_type=commercial_type,
            opening_hour=opening_hour,
            province_id=province_id,
            city_id=city_id,
            district_id=district_id,
            address_name=address_name,
            package_ids=package_ids,
            min_rating=min_rating,
            min_trading_count=min_trading_count,
            session_id=sid,
            request_id=rid,
        )

        commercials = result.get("commercials", []) if isinstance(result, dict) else []
        if not commercials:
            log_tool_end("search_nearby_shops", sid, rid, {"shop_count": 0})
            return "未找到附近的门店，建议扩大搜索范围或调整关键词"

        shops = []
        for item in commercials:
            distance_m = item.get("distance", 0)
            distance_km = round(distance_m / 1000, 1) if distance_m else 0

            svc = item.get("serviceScope", "")
            tag_list = [t.strip() for t in svc.split(",") if t.strip()] if svc else []

            shops.append({
                "shop_id": item.get("commercialId", ""),
                "name": item.get("commercialName", ""),
                "address": item.get("address", ""),
                "province": item.get("provinceName", ""),
                "city": item.get("cityName", ""),
                "district": item.get("districtName", ""),
                "distance": f"{distance_km}km",
                "rating": item.get("rating"),
                "trading_count": item.get("tradingCount", 0),
                "phone": item.get("phone", ""),
                "tags": tag_list,
                "opening_hours": item.get("openingHours", ""),
            })

        log_tool_end("search_nearby_shops", sid, rid, {
            "shop_count": len(shops),
            "shops": [s["name"] for s in shops],
        })
        return json.dumps({"total": len(shops), "shops": shops}, ensure_ascii=False)

    except Exception as e:
        log_tool_end("search_nearby_shops", sid, rid, exc=e)
        return f"Error: search_nearby_shops failed - {e}"


search_nearby_shops.__doc__ = _DESCRIPTION
