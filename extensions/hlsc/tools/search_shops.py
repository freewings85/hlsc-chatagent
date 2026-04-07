"""search_shops 工具：通过 shop consumer 搜索商户。

调用 shop consumer 的 /api/shop/search 接口，支持语义搜索 + 结构化过滤 + 位置过滤。
位置参数通过 LocationFilter 对象传入。
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Optional

import httpx
from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end, log_http_request, log_http_response
from hlsc.models.location_filter import LocationFilter
from hlsc.services.address_resolver import resolve_location_filter
from hlsc.tools.prompt_loader import load_tool_prompt

SHOP_SEARCH_URL: str = os.getenv("SHOP_SEARCH_URL", "http://localhost:8093")

_DESCRIPTION: str = load_tool_prompt("search_shops")


async def search_shops(
    ctx: RunContext[AgentDeps],
    location: Annotated[Optional[LocationFilter], Field(description="位置条件。address=范围搜索中心点，radius=搜索半径（米，用户没指定距离时不要传），city/district/street=区域过滤")] = None,
    shop_name: Annotated[str, Field(description="按门店名称搜索，仅用户明确说出具体店名时传入")] = "",
    semantic_query: Annotated[str, Field(description="语义搜索描述，如用户对商户的偏好。调用前回顾对话中用户提到的所有商户偏好，完整组装到此参数")] = "",
    project_ids: Annotated[Optional[list[str]], Field(description="项目 ID 列表，来自 classify_project。筛选能提供这些项目的商户")] = None,
    top: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
    min_rating: Annotated[Optional[float], Field(description="最低评分，仅用户明确给出时传入")] = None,
    shop_type: Annotated[Optional[str], Field(description="商户类型筛选，如'4S店'、'综合修理厂'")] = None,
    opening_time: Annotated[Optional[str], Field(description="营业时间筛选，格式 HH:MM，筛选该时间点还在营业的商户")] = None,
    sort_by: Annotated[str, Field(description="排序方式：default（默认相关度）/ distance（距离近优先）/ rating（评分高优先）/ trading_count（成交量高优先）")] = "default",
) -> str:
    """搜索商户，支持语义搜索 + 结构化过滤 + 位置过滤。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_shops", sid, rid, {
        "location": location.model_dump() if location else None,
        "shop_name": shop_name, "semantic_query": semantic_query, "top": top,
    })

    try:
        # 解析位置条件
        resolved = await resolve_location_filter(ctx, location, tool_name="search_shops")

        # 构建 shop consumer 请求
        url: str = f"{SHOP_SEARCH_URL.rstrip('/')}/api/shop/search"
        payload: dict[str, object] = {"topK": top}

        # 位置范围
        if resolved.has_range:
            payload["latitude"] = resolved.lat
            payload["longitude"] = resolved.lng
            if resolved.radius:
                payload["radius"] = resolved.radius

        # 城市过滤
        if resolved.city:
            payload["city"] = resolved.city

        # 商户名搜索
        if shop_name:
            payload["shopName"] = shop_name

        # 语义搜索
        if semantic_query:
            payload["semanticQuery"] = semantic_query

        # 项目过滤
        if project_ids:
            payload["projectIds"] = [int(pid) for pid in project_ids]

        log_http_request(url, "POST", sid, rid, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, sid, rid, data)

        if data.get("status") != 0:
            raise RuntimeError(f"商户搜索失败: {data.get('message', '未知错误')}")

        shops_raw: list[dict] = data.get("result", {}).get("shops", [])

        # 应用层过滤（shop consumer 不直接支持的条件）
        if resolved.district:
            shops_raw = [s for s in shops_raw if resolved.district in (s.get("district", "") or "")]
        if resolved.street:
            shops_raw = [s for s in shops_raw if resolved.street in (s.get("address", "") or "")]
        if min_rating is not None:
            shops_raw = [s for s in shops_raw if (s.get("rating") or 0) >= min_rating]
        if shop_type:
            shops_raw = [s for s in shops_raw if shop_type in (s.get("shop_type", "") or "")]
        if opening_time:
            shops_raw = [s for s in shops_raw
                         if (s.get("opening_start", "") or "") <= opening_time <= (s.get("opening_end", "") or "23:59")]

        # 应用层排序
        if sort_by == "distance":
            shops_raw.sort(key=lambda s: s.get("distance_km") if s.get("distance_km") is not None else float("inf"))
        elif sort_by == "rating":
            shops_raw.sort(key=lambda s: -(s.get("rating") or 0))
        elif sort_by == "trading_count":
            shops_raw.sort(key=lambda s: -(s.get("trading_count") or 0))

        if not shops_raw:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            desc: str = resolved.address or resolved.district or resolved.city or "指定范围"
            return f"{desc}内未找到符合条件的门店"

        # 格式化结果
        shops: list[dict] = []
        for item in shops_raw:
            svc: str = item.get("service_scope", "")
            tag_list: list[str] = [t.strip() for t in svc.split(",") if t.strip()] if svc else []
            distance_km = item.get("distance_km")

            shops.append({
                "shop_id": item.get("shop_id", ""),
                "name": item.get("shop_name", ""),
                "short_name": item.get("short_name", ""),
                "address": item.get("address", ""),
                "province": item.get("province", ""),
                "city": item.get("city_name", ""),
                "district": item.get("district", ""),
                "shop_type": item.get("shop_type", ""),
                "licensing": item.get("licensing", ""),
                "specialty": item.get("specialty", ""),
                "guarantee": item.get("guarantee", ""),
                "distance": f"{distance_km}km" if distance_km is not None else "",
                "rating": item.get("rating"),
                "trading_count": item.get("trading_count", 0),
                "phone": item.get("phone", ""),
                "tags": tag_list,
                "opening_start": item.get("opening_start", ""),
                "opening_end": item.get("opening_end", ""),
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
