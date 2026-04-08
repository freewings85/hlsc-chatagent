"""create_contact_order 工具：生成联系单，让商户主动联系用户。

调用 web_owner 的 task/submit 接口，
生成联络单后商户会收到通知并联系用户。
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

_DESCRIPTION: str = load_tool_prompt("create_contact_order")


async def create_contact_order(
    ctx: RunContext[AgentDeps],
    shop_id: Annotated[str, Field(description="商户 ID，必须来自 search_shops 返回的真实 shop_id，严禁编造")],
    shop_name: Annotated[str, Field(description="商户名称，来自 search_shops 返回")],
    visit_time: Annotated[str, Field(description="预计到店时间，支持自然语言（'上午''下午''明天下午3点'），原样传给后端转换")],
) -> str:
    """生成联系单，让商户主动联系用户。不是预订，是让商户知道用户有需求并主动联系。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("create_contact_order", sid, rid, {
        "shop_id": shop_id,
        "visit_time": visit_time,
    })

    if not DATA_MANAGER_URL:
        return "Error: DATA_MANAGER_URL 未配置"

    url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/task/submit"

    payload: dict[str, object] = {
        "conversationId": sid,
        "orderType": "contact",
        "appointmentTime": visit_time,
        "couponId": 0,
        "commercialList": [int(shop_id)],
    }

    log_http_request(url, "POST", sid, rid, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            data: dict[str, object] = response.json()
            log_http_response(response.status_code, sid, rid, data)

            if data.get("status") != 0:
                msg: str = str(data.get("message", "未知错误"))
                raise RuntimeError(f"生成联系单失败: {msg}")

            api_result: dict[str, object] = data.get("result", {})  # type: ignore[assignment]
            task_id: str = str(api_result.get("taskId", ""))

            output: dict[str, str] = {
                "order_id": task_id,
                "shop_name": shop_name,
                "visit_time": visit_time,
            }

            log_tool_end("create_contact_order", sid, rid, output)
            return json.dumps(output, ensure_ascii=False)

    except Exception as e:
        log_tool_end("create_contact_order", sid, rid, exc=e)
        return f"Error: create_contact_order failed - {e}"


create_contact_order.__doc__ = _DESCRIPTION
