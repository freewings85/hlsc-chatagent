"""竞价拍卖服务 — 封装 auctioneer API 调用。

支持：
- start_auction: 启动竞价工作流
- get_auction_status: 查询竞价进度
"""

from __future__ import annotations

import os

import httpx

from agent_sdk.logging import log_http_request, log_http_response

AUCTIONEER_URL: str = os.getenv("AUCTIONEER_URL")


class AuctioneerService:
    """竞价拍卖服务客户端"""

    async def start_auction(
        self,
        order_id: str,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """启动竞价工作流，返回 task_id 等信息。"""
        url: str = f"{AUCTIONEER_URL}/auction/start"
        payload: dict[str, str] = {"orderId": order_id, "sessionId": session_id}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)
            return data

    async def get_auction_status(
        self,
        task_id: str,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """查询竞价进度（轮次、已报价数、报价列表等）。"""
        url: str = f"{AUCTIONEER_URL}/auction/{task_id}/status"
        log_http_request(url, "GET", session_id, request_id)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)
            return data


auctioneer_service: AuctioneerService = AuctioneerService()
