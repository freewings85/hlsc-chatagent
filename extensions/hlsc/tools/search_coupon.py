"""search_coupon 工具：根据项目和商户查询可用的优惠活动。

调用 DataManager 的 Discount/recommend 接口，
返回平台优惠和门店优惠两类活动列表。
"""

from __future__ import annotations

import json
import os
from typing import Annotated

import httpx
from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end, log_http_request, log_http_response
from hlsc.tools.prompt_loader import load_tool_prompt

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "http://192.168.100.108:50400")

_DESCRIPTION: str = load_tool_prompt("search_coupon")


async def search_coupon(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[list[str], Field(description="项目 ID 列表，来自 classify_project 或 match_project 返回的 project_id")],
    shop_ids: Annotated[list[str], Field(description="商户 ID 列表，来自 search_shops 返回的 shop_id；未指定商户时传空列表")] = [],
) -> str:
    """根据项目和商户查询可用的优惠活动。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_coupon", sid, rid, {
        "project_ids": project_ids,
        "shop_ids": shop_ids,
    })

    if not DATA_MANAGER_URL:
        raise RuntimeError("DATA_MANAGER_URL 未配置")

    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/Discount/recommend"

    # 构建请求体，ID 转为 int
    payload: dict[str, list[int]] = {
        "packageIds": [int(pid) for pid in project_ids],
    }
    if shop_ids:
        payload["shopIds"] = [int(sid_val) for sid_val in shop_ids]

    log_http_request(url, "POST", sid, rid, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, sid, rid, data)

            if data.get("status") != 0:
                msg: str = data.get("message", "未知错误")
                raise RuntimeError(f"查询优惠活动失败: {msg}")

            result: dict = data.get("result", {})
            platform_activities: list[dict] = result.get("platformActivities", [])
            shop_activities: list[dict] = result.get("shopActivities", [])

            output: dict[str, list[dict]] = {
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
