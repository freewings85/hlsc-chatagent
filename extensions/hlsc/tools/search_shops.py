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

logger: logging.Logger = logging.getLogger("chatagent")

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
        return {"latitude": lat, "longitude": lng, "city": addr}
    return None


async def search_shops(
    ctx: RunContext[AgentDeps],
    location_text: Annotated[str, Field(description="仅传用户提到的具体位置（地标、路名、小区、商圈等），如'张江高科''南京西路'。不接受省/市/县/镇等行政区域名（如'上海市''嘉定区''南翔镇'），用户没提具体位置则传空")] = "",
    use_exact_location: Annotated[bool, Field(description="是否使用用户当前位置或具体位置，仅当用户希望查'附近'或'周围'等，依赖当前位置或具体位置的商户时设为 true")] = False,
    radius: Annotated[Optional[int], Field(description="搜索半径（米）。仅用户明确说了距离时传，如'3公里内'传 3000。用户说'附近'不算明确距离，不传")] = None,
    shop_name: Annotated[str, Field(description="按门店名称搜索，仅用户明确说出具体店名时传入")] = "",
    shop_type_text: Annotated[str, Field(description="商户类型，原样传入用户的描述")] = "",
    semantic_query: Annotated[list[str], Field(description="其他语义搜索描述，如用户对商户的**要求**或**偏好**，提取关键词(如服务好、实力强)，不要**地址**和**价格**相关的词。调用前回顾对话中用户提到的商户搜索需求关键词，完整组装到此参数")] = [],
    project_ids: Annotated[Optional[list[int]], Field(description="项目 ID 列表，来自 classify_project。筛选能提供这些项目的商户")] = None,
    top: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
    min_rating: Annotated[Optional[float], Field(description="最低评分，用户明确给出时传入,如果用户要求类似'评分高'或'评价好'，则固定4.0")] = None,
    is_on_activity: Annotated[bool, Field(description="是否正在搞优惠活动")] = False,
    sort_by: Annotated[str, Field(description="排序方式：default（默认相关度）/ distance（距离近优先）/ rating（评分高优先）/ trading_count（成交量高优先）")] = "default",
) -> str:
    """搜索商户，支持语义搜索 + 结构化过滤 + 位置过滤。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_shops", sid, rid, {
        "location_text": location_text, "use_exact_location": use_exact_location,
        "radius": radius, "shop_name": shop_name, "semantic_query": semantic_query, "top": top,
    })

    try:
        latitude: float | None = None
        longitude: float | None = None
        city_name: str = None
        city_id: int | None = None
        shop_name_keywords: set[str] = set()
        address_keywords: set[str] = set()
        other_keywords: set[str] = set()
        commercial_type_ids: list[int] = []

        # 1. use_current_location=true 时，附带 context 的 lat/lng
        ctx_loc: dict[str, object] | None = _extract_context_location(ctx)
        if use_exact_location:
            if ctx_loc:
                latitude = float(ctx_loc["latitude"])  # type: ignore[arg-type]
                longitude = float(ctx_loc["longitude"])  # type: ignore[arg-type]
                city_name = ctx_loc["city"]
        logger.info("[search_shops] 步骤1完成: lat=%s, lng=%s, city=%s", latitude, longitude, city_name)

        # 2. location_text 不为空 → 地址解析获取经纬度 + cityId
        if location_text:
            from hlsc.services.restful.address_service import address_service
            from hlsc.services.restful.query_city_id_service import query_city_id_service

            try:
                geocoded = await address_service.geocode(
                    address=location_text, city=city_name, session_id=sid, request_id=rid,
                )
                logger.info("[search_shops] 步骤2 geocode结果: formatted=%s, lat=%s, lng=%s, city=%s",
                            geocoded.formatted_address, geocoded.latitude, geocoded.longitude, geocoded.city)
                # 将格式化地址添加到搜索关键词
                if geocoded.formatted_address:
                    address_keywords.add(geocoded.formatted_address)
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
                    logger.info("[search_shops] 步骤2 city_id=%s", city_id)
            except Exception as e:
                logger.warning("[search_shops] 步骤2 地址解析失败: location_text='%s', error=%s", location_text, e)
            finally:
                address_keywords.add(location_text)                                                                                                                                                                             
        logger.info("[search_shops] 步骤2完成: lat=%s, lng=%s, city_id=%s, address_keywords=%s",
                    latitude, longitude, city_id, address_keywords)

        # 3. shop_name如果不为空，添加到shop_name_keywords
        if shop_name:
            shop_name_keywords.add(shop_name)

        # 4. semantic_query如果不为空，添加到other_keywords
        if semantic_query:
            other_keywords.update(semantic_query)
        logger.info("[search_shops] 步骤3-4完成: shop_name_keywords=%s, other_keywords=%s",shop_name_keywords, other_keywords)

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
        logger.info("[search_shops] 步骤5完成: commercial_type_ids=%s", commercial_type_ids)

        # 6a. address_keywords 单独调 fusionSearch，keywordType=2（地址）
        if address_keywords:
            result = await fusion_search_service.search(
                keywords=list(address_keywords),
                doc_names=[DOC_COMMERCIAL],
                metadata_filters={"keywordType": [2]},
                session_id=sid,
                request_id=rid,
            )
            expanded: list[str] = result.get_titles()
            if expanded:
                address_keywords.update(expanded)
            else:
                address_keywords = set()

        # 6b. shop_name_keywords + other_keywords 合并调 fusionSearch（不限 keywordType）
        name_other_keywords: set[str] = shop_name_keywords | other_keywords
        if name_other_keywords:
            result = await fusion_search_service.search(
                keywords=list(name_other_keywords),
                doc_names=[DOC_COMMERCIAL],
                session_id=sid,
                request_id=rid,
            )
            titles_by_kw: dict[str, list[str]] = result.get_titles_by_keyword()
            has_shop_name: bool = False
            has_other: bool = False
            for kw, titles in titles_by_kw.items():
                if kw in shop_name_keywords:
                    shop_name_keywords.update(titles)
                    has_shop_name = True
                else:
                    other_keywords.update(titles)
                    has_other = True
            if not has_shop_name:
                shop_name_keywords = set()
            if not has_other:
                other_keywords = set()
        logger.info("[search_shops] 步骤6完成: shop_name_keywords=%s, address_keywords=%s, other_keywords=%s",
                    shop_name_keywords, address_keywords, other_keywords)

        # 7. 构建请求，调用 search_nearby_service
        sort_map: dict[str, str] = {
            "default": "distance",
            "distance": "distance",
            "rating": "rating",
            "trading_count": "tradingCount",
        }
        request: NearbyShopRequest = NearbyShopRequest(
            commercial_name=list(shop_name_keywords) if shop_name_keywords else None,
            address=list(address_keywords) if address_keywords else None,
            latitude=latitude,
            longitude=longitude,
            top=top,
            radius=radius if radius is not None else 10000,
            order_by=sort_map.get(sort_by, "distance"),
            package_ids=project_ids if project_ids else None,
            city_id=city_id,
            commercial_type=commercial_type_ids if commercial_type_ids else None,
            rating=min_rating,
            fuzzy=list(other_keywords) if other_keywords else None,
            is_on_activity = is_on_activity if is_on_activity else None,
        )
        logger.info("[search_shops] 步骤7 请求参数: %s", request)

        items: list[NearbyShopItem] = await search_nearby_service.search(
            request, session_id=sid, request_id=rid,
        )
        logger.info("[search_shops] 步骤7完成: 返回 %d 条结果", len(items))

        # 8. Fallback: 带项目过滤搜索无结果时，去掉项目条件重搜
        if not items and project_ids and len(project_ids) > 0:
            logger.info("[search_shops] 步骤8 项目过滤 fallback: project_ids=%s 搜索为空，去掉项目条件重搜", project_ids)
            fallback_request: NearbyShopRequest = NearbyShopRequest(
                commercial_name=request.commercial_name,
                address=request.address,
                latitude=request.latitude,
                longitude=request.longitude,
                top=request.top,
                radius=request.radius,
                order_by=request.order_by,
                package_ids=None,
                city_id=request.city_id,
                commercial_type=request.commercial_type,
                rating=request.rating,
                fuzzy=request.fuzzy,
                is_on_activity = request.is_on_activity,
            )
            items = await search_nearby_service.search(
                fallback_request, session_id=sid, request_id=rid,
            )
            logger.info("[search_shops] 步骤8 fallback完成: 返回 %d 条结果", len(items))

        if not items:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            current_km: int = (request.radius or 10000) // 1000
            return json.dumps({
                "total": 0,
                "shops": [],
                "notice": f"当前{current_km}公里范围内未找到符合条件的门店",
                "suggest": f"是否需要扩大到{current_km * 2}公里范围搜索？请询问用户确认",
            }, ensure_ascii=False)

        # 格式化结果
        shops: list[dict] = []
        for item in items:
            shops.append({
                "shop_id": item.commercial_id,
                "name": item.commercial_name,
                "address": item.address,
                "distance": f"{item.distance}m" if item.distance else "",
                "phone": item.phone,
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
