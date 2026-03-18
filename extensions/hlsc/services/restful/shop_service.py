"""商户查询服务 — 封装商户相关 API 调用。

支持两个接口：
- getLatestVisitedShops: 上次去过的商户
- getHistoryVisitedShops: 历史服务商户
"""

from __future__ import annotations

import os

import httpx

from agent_sdk.logging import log_http_request, log_http_response

SHOP_SERVICE_URL = os.getenv("SHOP_SERVICE_URL", "")


class ShopService:
    """商户查询服务"""

    async def get_latest_visited_shops(
        self,
        owner_id: str,
        top: int = 1,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """获取上次去过的商户。"""
        url = f"{SHOP_SERVICE_URL}/shop/getLatestVisitedShops"
        if not SHOP_SERVICE_URL:
            raise RuntimeError("SHOP_SERVICE_URL 未配置")

        payload = {"ownerId": int(owner_id), "top": top}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"获取上次去过的商户失败: {data.get('message', '未知错误')}"
            )

    async def get_history_visited_shops(
        self,
        owner_id: str,
        top: int = 5,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """获取历史服务商户。"""
        url = f"{SHOP_SERVICE_URL}/shop/getHistoryVisitedShops"
        if not SHOP_SERVICE_URL:
            raise RuntimeError("SHOP_SERVICE_URL 未配置")

        payload = {"ownerId": int(owner_id), "top": top}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"获取历史服务商户失败: {data.get('message', '未知错误')}"
            )


shop_service = ShopService()
