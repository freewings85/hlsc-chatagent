"""book_coupon 工具：为用户预约确认商户优惠，生成联系单。

调用 service_ai_datamanager 的 task/submit 接口，
生成用户与商家的联系单，返回联系单 ID（taskId）。
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

_DESCRIPTION: str = load_tool_prompt("book_coupon")


async def book_coupon(
    ctx: RunContext[AgentDeps],
    coupon_id: Annotated[str, Field(description="优惠券 ID，必须来自 search_coupon 返回的 coupon_id，严禁编造")],
    shop_id: Annotated[str, Field(description="商户 ID，必须来自 search_coupon 返回的 shop_id，严禁编造")],
    visit_time: Annotated[str, Field(description="预约到店时间，支持自然语言（'上午''下午''明天下午3点''后天上午'），原样传给后端转换")],
) -> str:
    """为用户预约确认商户优惠，生成联系单。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("book_coupon", sid, rid, {
        "coupon_id": coupon_id,
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
        "couponId": int(coupon_id),
        "commercialList": [int(shop_id)],
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }

    log_http_request(url, "POST", sid, rid, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data: dict[str, object] = response.json()
            log_http_response(response.status_code, sid, rid, data)

            if data.get("status") != 0:
                msg: str = str(data.get("message", "未知错误"))
                raise RuntimeError(f"申领优惠失败: {msg}")

            api_result: dict[str, object] = data.get("result", {})  # type: ignore[assignment]
            task_id: str = str(api_result.get("taskId", ""))

            output: dict[str, str] = {
                "order_id": task_id,
                "visit_time": visit_time,
            }

            log_tool_end("book_coupon", sid, rid, output)
            return json.dumps(output, ensure_ascii=False)

    except Exception as e:
        log_tool_end("book_coupon", sid, rid, exc=e)
        return f"Error: book_coupon failed - {e}"


book_coupon.__doc__ = _DESCRIPTION
