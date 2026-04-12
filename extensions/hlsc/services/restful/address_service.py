"""地址解析服务

调用 address service /api/address/geocode 接口，
将地址文本转为经纬度坐标 + 行政区划信息。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from agent_sdk.logging import log_http_request, log_http_response

ADDRESS_SERVICE_URL: str = os.getenv("ADDRESS_SERVICE_URL", "")


@dataclass
class GeocodedAddress:
    """地址解析结果"""

    address: str = ""
    formatted_address: str = ""
    latitude: float | None = None
    longitude: float | None = None
    province: str = ""
    city: str = ""
    district: str = ""
    adcode: str = ""

    @classmethod
    def from_api(cls, raw: dict) -> GeocodedAddress:
        """从接口返回的 dict 构建。"""
        return cls(
            address=raw.get("address", ""),
            formatted_address=raw.get("formattedAddress", ""),
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
            province=raw.get("province", ""),
            city=raw.get("city", ""),
            district=raw.get("district", ""),
            adcode=raw.get("adcode", ""),
        )


class AddressService:
    """地址解析服务"""

    async def geocode(
        self,
        address: str,
        city: str = "",
        session_id: str = "",
        request_id: str = "",
    ) -> GeocodedAddress:
        """将地址文本转为经纬度坐标 + 行政区划信息。

        Args:
            address: 地址文本，如 "淮海中路"、"北京朝阳区"
            city: 城市限定（可选，提高解析精度）

        Raises:
            RuntimeError: ADDRESS_SERVICE_URL 未配置或 API 返回错误状态
            ValueError: 地址解析失败（status != 0）
        """
        if not ADDRESS_SERVICE_URL:
            raise RuntimeError("ADDRESS_SERVICE_URL 未配置")

        url: str = f"{ADDRESS_SERVICE_URL}/api/address/geocode"
        payload: dict = {"address": address}
        if city:
            payload["city"] = city

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise ValueError(f"地址解析失败: {data.get('message', '未知错误')}")

        return GeocodedAddress.from_api(data.get("result", {}))


address_service: AddressService = AddressService()
