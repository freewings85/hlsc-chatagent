"""search_shops 工具：搜索附近商户。

调用 datamanager getNearbyShops 接口，支持位置过滤 + 结构化过滤 + 模糊搜索。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Optional
from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.search_nearby_service import (
    NearbyShopItem,
    NearbyShopRequest,
    search_nearby_service,
)
from hlsc.tools.prompt_loader import load_tool_prompt

logger: logging.Logger = logging.getLogger(__name__)

_DESCRIPTION: str = load_tool_prompt("search_shops")


def _extract_context_location(ctx: RunContext[AgentDeps]) -> dict[str, object] | None:
    """从 request_context 提取用户当前位置信息。"""
    req_ctx = ctx.deps.request_context
    if req_ctx is None:
        return None
    loc = req_ctx.get("current_location") if isinstance(req_ctx, dict) else getattr(req_ctx, "current_location", None)
    if loc is None:
        return None
    if isinstance(loc, dict):
        lat = loc.get("lat")
        lng = loc.get("lng")
        addr = loc.get("address", "")
    else:
        lat = getattr(loc, "lat", None)
        lng = getattr(loc, "lng", None)
        addr = getattr(loc, "address", "")
    if lat is not None and lng is not None:
        return {"latitude": lat, "longitude": lng, "locationText": addr}
    return None


async def search_shops(
    ctx: RunContext[AgentDeps],
    location_text: Annotated[str, Field(description="用户提到的位置，原样传入，如'上海''嘉定区''张江高科附近''南京西路'。若用户未提及位置但 context 中有当前位置，使用 context 中的位置并设 use_current_location=true。若均无则先调 collect_user_location")] = "",
    use_current_location: Annotated[bool, Field(description="是否使用用户当前位置。当 location_text 来自 context 中的用户定位时设为 true")] = False,
    radius: Annotated[Optional[int], Field(description="搜索半径（米）。仅用户明确说了距离时传，如'3公里内'传 3000。用户说'附近'不算明确距离，不传")] = None,
    shop_name: Annotated[str, Field(description="按门店名称搜索，仅用户明确说出具体店名时传入")] = "",
    shop_type_text: Annotated[str, Field(description="商户类型，原样传入用户的描述")] = "",
    semantic_query: Annotated[list[str], Field(description="其他语义搜索描述，如用户对商户的要求或偏好，提取关键词。调用前回顾对话中用户提到的商户搜索需求关键词，完整组装到此参数")] = [],
    project_ids: Annotated[Optional[list[int]], Field(description="项目 ID 列表，来自 classify_project。筛选能提供这些项目的商户")] = None,
    top: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
    min_rating: Annotated[Optional[float], Field(description="最低评分，仅用户明确给出时传入")] = None,
    sort_by: Annotated[str, Field(description="排序方式：default（默认相关度）/ distance（距离近优先）/ rating（评分高优先）/ trading_count（成交量高优先）")] = "default",
) -> str:
    """搜索商户，支持语义搜索 + 结构化过滤 + 位置过滤。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_shops", sid, rid, {
        "location_text": location_text, "use_current_location": use_current_location,
        "radius": radius, "shop_name": shop_name, "semantic_query": semantic_query, "top": top,
    })

    try:
        latitude: float | None = None
        longitude: float | None = None
        city_id: int | None = None
        commercial_keywords: list[str] = []
        commercial_type_ids: list[int] = []
        fuzzy: list[str] = []
        # 1. use_current_location=true 时，附带 context 的 lat/lng
        if use_current_location:
            ctx_loc: dict[str, object] | None = _extract_context_location(ctx)
            if ctx_loc:
                latitude = float(ctx_loc["latitude"])  # type: ignore[arg-type]
                longitude = float(ctx_loc["longitude"])  # type: ignore[arg-type]

        # 2. location_text 不为空 → 地址解析获取经纬度 + cityId
        if location_text:
            from hlsc.services.restful.address_service import address_service
            from hlsc.services.restful.query_city_id_service import query_city_id_service

            try:
                geocoded = await address_service.geocode(
                    address=location_text, session_id=sid, request_id=rid,
                )
                # 将格式化地址添加到搜索关键词
                if geocoded.formatted_address:
                    commercial_keywords.append(geocoded.formatted_address)
                # 补充经纬度（context 定位优先，地址解析兜底）
                if latitude is None and geocoded.latitude is not None:
                    latitude = geocoded.latitude
                if longitude is None and geocoded.longitude is not None:
                    longitude = geocoded.longitude
                # 根据 city 查询 cityId
                if geocoded.city:
                    city_id = await query_city_id_service.get_city_id(
                        city_name=geocoded.city, session_id=sid, request_id=rid,
                    )
            except Exception as e:
                logger.warning("地址解析失败: location_text='%s', error=%s", location_text, e)
            finally:
                commercial_keywords.append(location_text)
        
        # 3. shop_name如果不为空，添加到commercial_keywords
        if shop_name:
            commercial_keywords.append(shop_name)
        
        # 4. semantic_query如果不为空，添加到commercial_keywords
        if semantic_query:
            commercial_keywords.extend(semantic_query)

        # 5. 调用fusion_search_service, 获取commercial_type_ids
        from hlsc.services.restful.fusion_search_service import (
            fusion_search_service, DOC_COMMERCIAL_TYPE, DOC_COMMERCIAL,
        )
        if shop_type_text:
            result = await fusion_search_service.search(
                keywords=[shop_type_text],
                doc_names=[DOC_COMMERCIAL_TYPE],
                session_id=sid,
                request_id=rid,
            )
            commercial_type_ids = result.get_source_ids(DOC_COMMERCIAL_TYPE)

        # 6. 调用fusion_search_service, 获取fuzzy
        if commercial_keywords:
            result = await fusion_search_service.search(
                keywords=commercial_keywords,
                doc_names=[DOC_COMMERCIAL],
                session_id=sid,
                request_id=rid,
            )
            fuzzy = result.get_titles(DOC_COMMERCIAL)

        # 7. 构建请求，调用 search_nearby_service
        sort_map: dict[str, str] = {
            "default": "distance",
            "distance": "distance",
            "rating": "rating",
            "trading_count": "tradingCount",
        }
        request: NearbyShopRequest = NearbyShopRequest(
            latitude=latitude,
            longitude=longitude,
            top=top,
            radius=radius if radius is not None else 10000,
            order_by=sort_map.get(sort_by, "distance"),
            package_ids=project_ids if project_ids else None,
            city_id=city_id,
            commercial_type=commercial_type_ids,
            rating=min_rating,
            fuzzy=fuzzy
        )

        items: list[NearbyShopItem] = await search_nearby_service.search(
            request, session_id=sid, request_id=rid,
        )

        if not items:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            return f"{location_text or '指定范围'}内未找到符合条件的门店"

        # 格式化结果
        shops: list[dict] = []
        for item in items:
            svc: str = item.service_scope
            tag_list: list[str] = [t.strip() for t in svc.split(",") if t.strip()] if svc else []
            opening_parts: list[str] = item.opening_hours.split("-") if item.opening_hours else []

            shops.append({
                "shop_id": item.commercial_id,
                "name": item.commercial_name,
                "address": item.address,
                "province": item.province_name,
                "city": item.city_name,
                "district": item.district_name,
                "shop_type": item.commercial_type,
                "distance": f"{item.distance}m" if item.distance else "",
                "rating": item.rating,
                "trading_count": item.trading_count,
                "phone": item.phone,
                "tags": tag_list,
                "opening_start": opening_parts[0].strip() if len(opening_parts) >= 1 else "",
                "opening_end": opening_parts[1].strip() if len(opening_parts) >= 2 else "",
                "packages": item.packages,
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
