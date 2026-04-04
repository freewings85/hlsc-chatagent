"""search_coupon 工具：根据项目、位置、语义条件查询可用的优惠活动。

地址参数说明：
- address=None（不传）→ 使用用户当前位置（从 request_context 取，没有则 interrupt 让用户选点）
- address="南京西路" → 调 address service 转经纬度后搜索
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
from hlsc.services.address_resolver import resolve_location
from hlsc.tools.prompt_loader import load_tool_prompt

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_COUPON_SEARCH_URL: str = os.getenv("COUPON_SEARCH_URL", "")
_DEFAULT_RADIUS: int = int(os.getenv("SEARCH_COUPON_DEFAULT_RADIUS", "100000"))

_DESCRIPTION: str = load_tool_prompt("search_coupon")


async def search_coupon(
    ctx: RunContext[AgentDeps],
    address: Annotated[Optional[str], Field(description="目标地址，如'静安区南京西路'。不传则使用用户当前位置")] = None,
    project_ids: Annotated[Optional[list[str]], Field(description="项目 ID 列表，来自 classify_project。无明确项目时传 null")] = None,
    shop_ids: Annotated[list[str], Field(description="商户 ID 列表；未指定商户时传空列表")] = [],
    city: Annotated[str, Field(description="城市名称（如'北京'），用于按地域筛选优惠")] = "",
    radius: Annotated[int, Field(description="搜索半径（米）。用户没有明确指定距离时不要传此参数")] = 0,
    date: Annotated[str, Field(description="查询日期（YYYY-MM-DD），用于过滤该日期有效的优惠。默认当天")] = "",
    semantic_query: Annotated[str, Field(description="用户对优惠的自然语言偏好描述（如'支付宝支付的满减活动、送洗车的'）。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数")] = "",
    sort_by: Annotated[str, Field(description="排序方式：default（默认热度）/ discount_amount（优惠金额）/ validity_end（即将过期优先）")] = "default",
    top_k: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
) -> str:
    """根据项目、位置和语义条件查询可用的优惠活动。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_coupon", sid, rid, {
        "address": address, "project_ids": project_ids,
        "shop_ids": shop_ids, "city": city, "radius": radius,
        "semantic_query": semantic_query, "sort_by": sort_by, "top_k": top_k,
    })

    try:
        # 解析地址 → 经纬度
        location = await resolve_location(ctx, address, tool_name="search_coupon")

        # 如果 address service 返回了城市信息且用户没指定 city，自动填充
        if not city and location.city:
            city = location.city

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
        if city:
            payload["city"] = city
        payload["latitude"] = location.lat
        payload["longitude"] = location.lng
        actual_radius: int = radius if radius > 0 else _DEFAULT_RADIUS
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
