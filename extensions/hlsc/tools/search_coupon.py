"""search_coupon 工具：根据项目、位置、语义条件查询可用的优惠活动。

调用 DataManager 的 Discount/recommend 接口，
返回平台优惠和门店优惠两类活动列表。

Mock 模式：设置环境变量 MOCK_SEARCH_COUPON=true 或不配置 DATA_MANAGER_URL 时
返回预置的 mock 数据，用于本地开发和测试。
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

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_MOCK_ENABLED: bool = os.getenv("MOCK_SEARCH_COUPON", "").lower() == "true" or not DATA_MANAGER_URL

_DESCRIPTION: str = load_tool_prompt("search_coupon")

# -- Mock 数据 --
_MOCK_PLATFORM_ACTIVITIES: list[dict[str, object]] = [
    {
        "activity_id": 1001,
        "activity_name": "话痨九折预订",
        "shop_id": 0,
        "shop_name": "平台",
        "activity_description": "通过话痨预订享九折优惠，适用于所有合作商户",
    },
    {
        "activity_id": 1002,
        "activity_name": "新用户首单立减30",
        "shop_id": 0,
        "shop_name": "平台",
        "activity_description": "新注册用户首次预订立减30元，不与其他优惠叠加",
    },
]

_MOCK_SHOP_ACTIVITIES: list[dict[str, object]] = [
    {
        "activity_id": 2001,
        "activity_name": "换机油满500减80",
        "shop_id": 101,
        "shop_name": "途虎养车朝阳店",
        "activity_description": "满500元减80元，支持支付宝和微信支付，赠送免费洗车一次",
    },
    {
        "activity_id": 2002,
        "activity_name": "轮胎8折优惠",
        "shop_id": 102,
        "shop_name": "小李轮胎修理",
        "activity_description": "指定品牌轮胎享8折，含免费安装和动平衡",
    },
    {
        "activity_id": 2003,
        "activity_name": "保养套餐送机油",
        "shop_id": 103,
        "shop_name": "精典汽修连锁",
        "activity_description": "做保养送全合成机油一桶，仅限周末使用，需提前预约",
    },
    {
        "activity_id": 2004,
        "activity_name": "空调清洗满200减50",
        "shop_id": 101,
        "shop_name": "途虎养车朝阳店",
        "activity_description": "空调系统深度清洗满200元减50元，含杀菌除味，仅限支付宝支付",
    },
    {
        "activity_id": 2005,
        "activity_name": "喷漆补漆送抛光",
        "shop_id": 103,
        "shop_name": "精典汽修连锁",
        "activity_description": "喷漆或补漆项目赠送全车抛光一次，需提前一天预约",
    },
]


def _get_mock_data() -> str:
    """返回 mock 优惠数据 JSON"""
    output: dict[str, list[dict[str, object]]] = {
        "platformActivities": _MOCK_PLATFORM_ACTIVITIES,
        "shopActivities": _MOCK_SHOP_ACTIVITIES,
    }
    return json.dumps(output, ensure_ascii=False)


async def search_coupon(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[list[str] | None, Field(description="项目 ID 列表，来自 classify_project 或 match_project。无明确项目时传 null")] = None,
    shop_ids: Annotated[list[str], Field(description="商户 ID 列表；未指定商户时传空列表")] = [],
    city: Annotated[str, Field(description="城市名称（如'北京'），用于按地域筛选优惠")] = "",
    semantic_query: Annotated[str, Field(description="用户对优惠的自然语言偏好描述（如'支付宝支付的满减活动、送洗车的'）。调用前回顾对话中用户提到的所有优惠偏好，完整组装到此参数")] = "",
    sort_by: Annotated[str, Field(description="排序方式：default（默认热度）/ discount_amount（优惠金额）/ validity_end（即将过期优先）")] = "default",
    top_k: Annotated[int, Field(description="返回数量上限，默认 10")] = 10,
) -> str:
    """根据项目、位置和语义条件查询可用的优惠活动。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("search_coupon", sid, rid, {
        "project_ids": project_ids,
        "shop_ids": shop_ids,
        "city": city,
        "semantic_query": semantic_query,
        "sort_by": sort_by,
        "top_k": top_k,
    })

    # Mock 模式：返回预置数据
    if _MOCK_ENABLED:
        result: str = _get_mock_data()
        log_tool_end("search_coupon", sid, rid, {"mock": True, "platform_count": 2, "shop_count": 5})
        return result

    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/Discount/recommend"

    # 构建请求体
    payload: dict[str, object] = {}
    if project_ids:
        payload["packageIds"] = [int(pid) for pid in project_ids]
    if shop_ids:
        payload["shopIds"] = [int(sid_val) for sid_val in shop_ids]
    if city:
        payload["city"] = city
    if semantic_query:
        payload["semanticQuery"] = semantic_query
    if sort_by != "default":
        payload["sortBy"] = sort_by
    if top_k != 10:
        payload["topK"] = top_k

    log_http_request(url, "POST", sid, rid, payload)

    try:
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
