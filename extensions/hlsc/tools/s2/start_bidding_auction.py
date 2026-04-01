"""start_bidding_auction 工具：启动多商户竞价，返回 task_id 供前端轮询。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.services.restful.auctioneer_service import auctioneer_service
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("start_bidding_auction")


async def start_bidding_auction(
    ctx: RunContext[AgentDeps],
    order_id: Annotated[str, Field(description="服务订单 ID")],
) -> str:
    """启动多商户竞价拍卖，返回 auction_start 卡片供前端轮询进度。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("start_bidding_auction", sid, rid, {"order_id": order_id})

    try:
        start_resp: dict = await auctioneer_service.start_auction(order_id, sid, rid)
        task_id: str = start_resp["task_id"]

        card_data: dict = {
            "task_id": task_id,
            "order_id": order_id,
            "status": "started",
            "message": "竞价已启动，前端请轮询 /auction/{task_id}/status 获取进度",
        }
        card_json: str = json.dumps(card_data, ensure_ascii=False)

        log_tool_end("start_bidding_auction", sid, rid, {
            "task_id": task_id, "status": "started",
        })

        return (
            f"<!--card:auction_start-->\n{card_json}\n<!--/card-->\n"
            f"竞价已启动（task_id={task_id}），前端正在实时展示竞价进度。"
        )

    except Exception as e:
        log_tool_end("start_bidding_auction", sid, rid, exc=e)
        return f"Error: start_bidding_auction failed - {e}"


start_bidding_auction.__doc__ = _DESCRIPTION
