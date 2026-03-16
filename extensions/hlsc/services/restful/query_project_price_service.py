"""项目门店报价查询服务 — 查询附近门店的项目报价。

支持按距离、评分过滤，按距离/评分/价格排序，可指定门店。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response

QUERY_NEARBY_URL = os.getenv("QUERY_NEARBY_URL", "")

REPAIR_TYPE_NAMES = {
    "INTERNATIONAL_BRAND": "国际大厂",
    "DOMESTIC_QUALITY": "国产品质",
    "ORIGINAL": "原厂",
}


@dataclass
class QuotationPlan:
    """报价方案"""
    name: str
    price: str
    type: str
    qa: Optional[str] = None


@dataclass
class QuotationProject:
    """门店报价项目"""
    id: int
    name: str
    plans: List[QuotationPlan] = field(default_factory=list)


@dataclass
class NearbyShop:
    """门店"""
    shop_id: str
    shop_name: str
    distance_km: float
    rating: Optional[float] = None
    address: Optional[str] = None
    projects: List[QuotationProject] = field(default_factory=list)


@dataclass
class NearbyResult:
    """门店报价查询结果"""
    shops: List[NearbyShop] = field(default_factory=list)


class QueryProjectPriceService:
    """项目门店报价查询服务"""

    async def query_nearby(
        self,
        project_ids: List[int],
        car_model_id: str,
        lat: float,
        lng: float,
        session_id: str = "",
        request_id: str = "",
        *,
        distance_km: int = 10,
        min_rating: Optional[float] = None,
        shop_ids: Optional[List[str]] = None,
        sort_by: str = "distance",
    ) -> NearbyResult:
        """查询附近门店项目报价。

        Args:
            project_ids: 项目 ID 列表
            car_model_id: 车型编码
            lat: 纬度
            lng: 经度
            distance_km: 距离范围（公里），默认 10
            min_rating: 最低评分过滤（如 4.8），None 不过滤
            shop_ids: 指定门店 ID 列表（可选），None 不限制
            sort_by: 排序方式 — distance（默认）/ rating / price

        Raises:
            RuntimeError: URL 未配置或 API 返回错误
        """
        url = QUERY_NEARBY_URL
        if not url:
            raise RuntimeError("QUERY_NEARBY_URL 未配置")

        if not project_ids:
            return NearbyResult()

        payload: dict = {
            "projectIds": list(set(project_ids)),
            "carKey": car_model_id,
            "latitude": str(lat),
            "longitude": str(lng),
            "distanceKm": distance_km,
            "sortBy": sort_by,
        }
        if min_rating is not None:
            payload["minRating"] = min_rating
        if shop_ids:
            payload["shopIds"] = shop_ids

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return _parse_nearby(data.get("result", {}))
            else:
                error_msg = data.get("message", "未知错误")
                raise RuntimeError(f"查询门店报价失败: {error_msg}")


def _parse_nearby(raw: dict) -> NearbyResult:
    shops = []
    for s in (raw.get("shops") or []):
        projects = []
        for p in (s.get("quotationProjectList") or []):
            plans = []
            for plan in (p.get("quotationPlanList") or []):
                plans.append(QuotationPlan(
                    name=plan.get("name", ""),
                    price=str(plan.get("price", "")),
                    type=plan.get("type", ""),
                    qa=plan.get("qa") or None,
                ))
            projects.append(QuotationProject(
                id=p.get("id", 0),
                name=p.get("name", ""),
                plans=plans,
            ))
        shops.append(NearbyShop(
            shop_id=str(s.get("shopId", "")),
            shop_name=s.get("shopName", ""),
            distance_km=s.get("distanceKm", 0),
            rating=s.get("rating") or None,
            address=s.get("address") or None,
            projects=projects,
        ))
    return NearbyResult(shops=shops)


query_project_price_service = QueryProjectPriceService()
