"""search_coupon 工具：根据项目、位置、语义条件查询可用的优惠活动。

位置参数通过 LocationFilter 对象传入，支持范围搜索和区域过滤。
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

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_COUPON_SEARCH_URL: str = os.getenv("COUPON_SEARCH_URL", "")
_DEFAULT_RADIUS: int = int(os.getenv("SEARCH_COUPON_DEFAULT_RADIUS", "100000"))

_DESCRIPTION: str = load_tool_prompt("search_coupon")


async def search_coupon(
    ctx: RunContext[AgentDeps],
    location: Annotated[LocationFilter, Field(description="位置条件（必填）。至少指定一个字段：address（范围搜索）、city/district/street（区域过滤），或留空对象{}使用用户当前位置")],
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
        "location": location.model_dump() if location else None,
        "project_ids": project_ids, "shop_ids": shop_ids,
        "semantic_query": semantic_query, "sort_by": sort_by, "top_k": top_k,
    })

    try:
        # 解析位置条件
        resolved = await resolve_location_filter(ctx, location, tool_name="search_coupon")

        # 城市：LocationFilter 的 city（含 address service 自动填充）
        effective_city: str = resolved.city

        # 优先使用独立搜索服务，否则走 DataManager
        use_search_service: bool = bool(_COUPON_SEARCH_URL)
        if use_search_service:
            url: str = f"{_COUPON_SEARCH_URL.rstrip('/')}/api/coupon/search"
        elif DATA_MANAGER_URL:
            url = f"{DATA_MANAGER_URL}/service_ai_datamanager/Discount/recommend"
        else:
            return "Error: COUPON_SEARCH_URL 和 DATA_MANAGER_URL 均未配置"

        # 构建请求体
        payload: dict[str, object] = {}
        if project_ids:
            key: str = "projectIds" if use_search_service else "packageIds"
            payload[key] = [int(pid) for pid in project_ids]
        if shop_ids:
            payload["shopIds"] = [int(sid_val) for sid_val in shop_ids]
        if effective_city:
            payload["city"] = effective_city
        if resolved.has_range:
            payload["latitude"] = resolved.lat
            payload["longitude"] = resolved.lng
        # 搜索半径：LocationFilter.radius 或默认值
        actual_radius: int = resolved.radius or _DEFAULT_RADIUS
        payload["radius"] = actual_radius
        if date:
            payload["date"] = date
        if semantic_query:
            payload["semanticQuery"] = semantic_query
        if sort_by != "default":
            payload["sortBy"] = sort_by
        payload["topK"] = top_k

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
