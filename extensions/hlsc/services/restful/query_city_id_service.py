"""城市 ID 查询服务

调用 datamanager /region/listCityProvinceByCityName 接口，
根据城市名称查询 cityId 和 provinceId。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")


@dataclass
class CityInfo:
    """城市信息"""

    city_id: int = 0
    city: str = ""
    province_id: int = 0
    province: str = ""

    @classmethod
    def from_api(cls, raw: dict) -> CityInfo:
        """从接口返回的 dict 构建。"""
        return cls(
            city_id=raw.get("cityId", 0),
            city=raw.get("city", ""),
            province_id=raw.get("provinceId", 0),
            province=raw.get("provinceCn", ""),
        )


class QueryCityIdService:
    """城市 ID 查询服务"""

    async def query(
        self,
        city_name: str,
        session_id: str = "",
        request_id: str = "",
    ) -> list[CityInfo]:
        """根据城市名称查询城市信息列表。

        Args:
            city_name: 城市名称，如 "无锡"、"上海"

        Raises:
            RuntimeError: DATA_MANAGER_URL 未配置或 API 返回错误状态
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/region/listCityProvinceByCityName"
        payload: dict = {"cityName": city_name}
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"城市查询失败: {data.get('message', '未知错误')}")

        return [CityInfo.from_api(item) for item in data.get("result", [])]

    async def get_city_id(
        self,
        city_name: str,
        session_id: str = "",
        request_id: str = "",
    ) -> int | None:
        """根据城市名称获取 cityId，未找到返回 None。"""
        items: list[CityInfo] = await self.query(city_name, session_id, request_id)
        return items[0].city_id if items else None


query_city_id_service: QueryCityIdService = QueryCityIdService()
