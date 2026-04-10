"""search_shops 工具：通过 shop consumer 搜索商户。

调用 shop consumer 的 /api/shop/search 接口，支持语义搜索 + 结构化过滤 + 位置过滤。
位置参数通过 location_text + use_current_location + radius 传入，Java 端统一处理。
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
from hlsc.tools.prompt_loader import load_tool_prompt

SHOP_SEARCH_URL: str = os.getenv("SHOP_SEARCH_URL", "http://localhost:8093")

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
    semantic_query: Annotated[str, Field(description="语义搜索描述，如用户对商户的偏好。调用前回顾对话中用户提到的所有商户偏好，完整组装到此参数")] = "",
    project_ids: Annotated[Optional[list[str]], Field(description="项目 ID 列表，来自 classify_project。筛选能提供这些项目的商户")] = None,
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
        # 构建 shop consumer 请求
        url: str = f"{SHOP_SEARCH_URL.rstrip('/')}/api/shop/search"
        payload: dict[str, object] = {"topK": top}

        # 位置参数：透传给 Java consumer 处理
        if location_text:
            payload["locationText"] = location_text
        if radius is not None:
            payload["radius"] = radius

        # use_current_location=true 时，附带 context 的 lat/lng
        if use_current_location:
            ctx_loc: dict[str, object] | None = _extract_context_location(ctx)
            if ctx_loc:
                payload["latitude"] = ctx_loc["latitude"]
                payload["longitude"] = ctx_loc["longitude"]
                if not location_text:
                    payload["locationText"] = ctx_loc.get("locationText", "")

        # 商户名搜索
        if shop_name:
            payload["shopName"] = shop_name

        # 商户类型
        if shop_type_text:
            payload["shopTypeText"] = shop_type_text

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

        # 应用层过滤
        if min_rating is not None:
            shops_raw = [s for s in shops_raw if (s.get("rating") or 0) >= min_rating]

        # 应用层排序
        if sort_by == "distance":
            shops_raw.sort(key=lambda s: s.get("distance_km") if s.get("distance_km") is not None else float("inf"))
        elif sort_by == "rating":
            shops_raw.sort(key=lambda s: -(s.get("rating") or 0))
        elif sort_by == "trading_count":
            shops_raw.sort(key=lambda s: -(s.get("trading_count") or 0))

        if not shops_raw:
            log_tool_end("search_shops", sid, rid, {"shop_count": 0})
            return f"{location_text or '指定范围'}内未找到符合条件的门店"

        # 格式化结果
        shops: list[dict] = []
        for item in shops_raw:
            distance_km = item.get("distance_km")
            shops.append({
                "shop_id": item.get("shop_id", ""),
                "name": item.get("shop_name", ""),
                "address": item.get("address", ""),
                "distance": f"{distance_km}km" if distance_km is not None else "",
                "phone": item.get("phone", ""),
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
