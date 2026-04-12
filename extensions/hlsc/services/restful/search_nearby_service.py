"""附近商户搜索服务

调用 datamanager /shop/getNearbyShops 接口，支持位置、商户类型、项目、
评分、交易量、营业时间、模糊搜索、设备等多维度筛选。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


# ============================================================
# 请求 / 响应数据结构
# ============================================================


@dataclass
class NearbyShopRequest:
    """getNearbyShops 请求参数"""

    latitude: float | None = None
    longitude: float | None = None
    top: int = 5
    radius: int = 10000
    keyword: str | None = None
    commercial_type: list[int] | None = None
    commercial_ids: list[int] | None = None
    package_ids: list[int] | None = None
    province_id: int | None = None
    city_id: int | None = None
    district_id: int | None = None
    address_name: str | None = None
    opening_hour: str | None = None
    platform_activity_id: int | None = None
    rating: float | None = None
    trading_count: int | None = None
    fuzzy: list[str] | None = None
    equipment: list[int] | None = None
    commercial_name: list[str] | None = None
    address: list[str] | None = None
    is_on_activity: bool | None = None
    order_by: str = "distance"

    def to_payload(self) -> dict:
        """转为接口 JSON payload，None 字段不传。"""
        payload: dict = {
            "top": self.top,
            "radius": self.radius,
            "orderBy": self.order_by,
        }
        if self.latitude is not None:
            payload["latitude"] = self.latitude
        if self.longitude is not None:
            payload["longitude"] = self.longitude
        if self.keyword is not None:
            payload["keyword"] = self.keyword
        if self.commercial_type is not None:
            payload["commercialType"] = self.commercial_type
        if self.commercial_ids is not None:
            payload["commercialIds"] = self.commercial_ids
        if self.package_ids is not None:
            payload["packageIds"] = self.package_ids
        if self.province_id is not None:
            payload["provinceId"] = self.province_id
        if self.city_id is not None:
            payload["cityId"] = self.city_id
        if self.district_id is not None:
            payload["districtId"] = self.district_id
        if self.address_name is not None:
            payload["addressName"] = self.address_name
        if self.opening_hour is not None:
            payload["openingHour"] = self.opening_hour
        if self.platform_activity_id is not None:
            payload["platformActivityId"] = self.platform_activity_id
        if self.rating is not None:
            payload["rating"] = self.rating
        if self.trading_count is not None:
            payload["tradingCount"] = self.trading_count
        if self.fuzzy is not None:
            payload["fuzzy"] = self.fuzzy
        if self.equipment is not None:
            payload["equipment"] = self.equipment
        if self.commercial_name is not None:
            payload["commercialName"] = self.commercial_name
        if self.address is not None:
            payload["address"] = self.address
        if self.is_on_activity is not None:
            payload["isOnActivity"] = self.is_on_activity
        return payload


@dataclass
class NearbyShopItem:
    """单个商户结果"""

    commercial_id: int = 0
    commercial_name: str = ""
    image_urls: list[str] = field(default_factory=list)
    province_name: str = ""
    city_name: str = ""
    district_name: str = ""
    address: str = ""
    service_scope: str = ""
    phone: str = ""
    commercial_type: list[str] = field(default_factory=list)
    opening_hours: str = ""
    longitude: float | None = None
    latitude: float | None = None
    distance: int = 0
    rating: float = 0.0
    trading_count: int = 0
    packages: list[dict] = field(default_factory=list)

    @classmethod
    def from_api(cls, raw: dict) -> NearbyShopItem:
        """从接口返回的 dict 构建。"""
        images: list[str] = raw.get("imageObject") or []
        return cls(
            commercial_id=raw.get("commercialId", 0),
            commercial_name=raw.get("commercialName", ""),
            image_urls=images,
            province_name=raw.get("provinceName", ""),
            city_name=raw.get("cityName", ""),
            district_name=raw.get("districtName", ""),
            address=raw.get("address") or "",
            service_scope=raw.get("serviceScope") or "",
            phone=raw.get("phone") or "",
            commercial_type=raw.get("commercialType") or [],
            opening_hours=raw.get("openingHours") or "",
            longitude=raw.get("longitude"),
            latitude=raw.get("latitude"),
            distance=raw.get("distance", 0),
            rating=float(raw.get("rating") or 0),
            trading_count=int(raw.get("tradingCount") or 0),
            packages=raw.get("packages") or [],
        )


# ============================================================
# 服务实现
# ============================================================


class SearchNearbyService:
    """附近商户搜索服务"""

    async def search(
        self,
        request: NearbyShopRequest,
        session_id: str = "",
        request_id: str = "",
    ) -> list[NearbyShopItem]:
        """搜索附近门店，返回商户列表。

        Raises:
            RuntimeError: DATA_MANAGER_URL 未配置或 API 返回错误状态
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/shop/getNearbyShops"
        payload: dict = request.to_payload()
        if session_id:
            payload["sessionId"] = session_id
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"搜索附近门店失败: {data.get('message', '未知错误')}")

        raw_result = data.get("result", {})
        # result 可能是 {"commercials": [...]} 或直接是 list
        if isinstance(raw_result, list):
            commercials = raw_result
        elif isinstance(raw_result, dict):
            commercials = raw_result.get("commercials", [])
        else:
            commercials = []
        return [NearbyShopItem.from_api(c) for c in commercials]


search_nearby_service: SearchNearbyService = SearchNearbyService()
