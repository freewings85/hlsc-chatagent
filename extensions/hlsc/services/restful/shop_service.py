"""商户查询服务 — 封装商户相关 API 调用。

支持三个接口：
- getLatestVisitedShops: 上次去过的商户
- getHistoryVisitedShops: 历史服务商户
- getNearbyShops: 附近门店搜索
"""

from __future__ import annotations

import os

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL = os.getenv("DATA_MANAGER_URL", "http://192.168.100.108:50400")


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
        url = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getLatestVisitedShops"
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

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
        url = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getHistoryVisitedShops"
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

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


    async def get_nearby_shops(
        self,
        lat: float,
        lng: float,
        keyword: str = "",
        top: int = 5,
        radius: int = 10000,
        order_by: str = "distance",
        commercial_type: list[int] | None = None,
        opening_hour: str | None = None,
        province_id: int | None = None,
        city_id: int | None = None,
        district_id: int | None = None,
        address_name: str | None = None,
        package_ids: str | None = None,
        min_rating: float | None = None,
        min_trading_count: int | None = None,
        session_id: str = "",
        request_id: str = "",
    ) -> dict:
        """搜索附近门店。"""
        url = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getNearbyShops"
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        payload: dict = {
            "latitude": lat,
            "longitude": lng,
            "top": top,
            "radius": radius,
        }
        if keyword:
            payload["keyword"] = keyword
        if order_by:
            payload["orderBy"] = order_by
        if commercial_type is not None:
            payload["commercialType"] = commercial_type
        if opening_hour:
            payload["openingHour"] = opening_hour
        if province_id is not None:
            payload["provinceId"] = province_id
        if city_id is not None:
            payload["cityId"] = city_id
        if district_id is not None:
            payload["districtId"] = district_id
        if address_name:
            payload["addressName"] = address_name
        if package_ids:
            payload["packageIds"] = [int(x.strip()) for x in package_ids.split(",")]
        if min_rating is not None:
            payload["rating"] = min_rating
        if min_trading_count is not None:
            payload["tradingCount"] = min_trading_count

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return data.get("result", {})
            raise RuntimeError(
                f"搜索附近门店失败: {data.get('message', '未知错误')}"
            )


shop_service = ShopService()
