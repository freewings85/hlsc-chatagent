"""search_coupon 工具：根据项目、位置、语义条件查询可用的优惠活动。

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

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_COUPON_SEARCH_URL: str = os.getenv("COUPON_SEARCH_URL", "")

_DESCRIPTION: str = load_tool_prompt("search_coupon")


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


async def search_coupon(
    ctx: RunContext[AgentDeps],
    location_text: Annotated[str, Field(description="用户提到的位置，原样传入，如'上海''嘉定区''张江高科附近'。若用户未提及位置但 context 中有当前位置，使用 context 中的位置并设 use_current_location=true。若均无则先调 collect_user_location")] = "",
    use_current_location: Annotated[bool, Field(description="是否使用用户当前位置。当 location_text 来自 context 中的用户定位时设为 true")] = False,
    radius: Annotated[Optional[int], Field(description="搜索半径（米）。仅用户明确说了距离时传，如'3公里内'传 3000。用户说'附近'不算明确距离，不传")] = None,
    project_ids: Annotated[Optional[list[str]], Field(description="项目 ID 列表，来自 classify_project。无明确项目时传 null")] = None,
    shop_ids: Annotated[list[str], Field(description="商户 ID 列表；未指定商户时传空列表")] = [],
    date: Annotated[str, Field(description="查询日期（YYYY-MM-DD），用于过滤该日期有效的优惠。默认当天")] = "",
    semantic_query: Annotated[str, Field(description="用户对优惠的自然语言偏好描述。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数")] = "",
    sort_by: Annotated[str, Field(description="排序方式：default / promo_value / validity_end")] = "default",
    top_k: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
) -> str:
    """根据项目、位置和语义条件查询可用的优惠活动。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_coupon", sid, rid, {
        "location_text": location_text, "use_current_location": use_current_location,
        "radius": radius, "project_ids": project_ids, "shop_ids": shop_ids,
        "semantic_query": semantic_query, "sort_by": sort_by, "top_k": top_k,
    })

    try:
        # 选择搜索服务
        use_search_service: bool = bool(_COUPON_SEARCH_URL)
        if use_search_service:
            url: str = f"{_COUPON_SEARCH_URL.rstrip('/')}/api/coupon/search"
        elif DATA_MANAGER_URL:
            url = f"{DATA_MANAGER_URL}/service_ai_datamanager/Discount/recommend"
        else:
            return "Error: COUPON_SEARCH_URL 和 DATA_MANAGER_URL 均未配置"

        # 构建请求体
        payload: dict[str, object] = {"topK": top_k}

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

        if project_ids:
            payload["projectIds"] = [int(pid) for pid in project_ids]
        if shop_ids:
            payload["shopIds"] = [int(sid_val) for sid_val in shop_ids]
        if date:
            payload["date"] = date
        if semantic_query:
            payload["semanticQuery"] = semantic_query
        if sort_by != "default":
            payload["sortBy"] = sort_by

        log_http_request(url, "POST", sid, rid, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict[str, object] = response.json()
            log_http_response(response.status_code, sid, rid, data)

            if data.get("status") != 0:
                msg: str = str(data.get("message", "未知错误"))
                raise RuntimeError(f"查询优惠活动失败: {msg}")

            api_result: dict[str, object] = data.get("result", {})  # type: ignore[assignment]
            platform_activities: list[dict[str, object]] = api_result.get("platformActivities", [])  # type: ignore[assignment]
            shop_activities: list[dict[str, object]] = api_result.get("shopActivities", [])  # type: ignore[assignment]

            output: dict[str, list[dict[str, object]]] = {
                "platformActivities": platform_activities,
                "shopActivities": shop_activities,
            }

            log_tool_end("search_coupon", sid, rid, {
                "platform_count": len(platform_activities),
                "shop_count": len(shop_activities),
            })
            return json.dumps(output, ensure_ascii=False)

    except Exception as e:
        log_tool_end("search_coupon", sid, rid, exc=e)
        return f"Error: search_coupon failed - {e}"


search_coupon.__doc__ = _DESCRIPTION
