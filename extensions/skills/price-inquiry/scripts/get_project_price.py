#!/usr/bin/env python3
"""查询项目在指定门店或附近门店的报价。

用法：python get_project_price.py --project-ids 502 505 --car-model-id "xxx" --shop-ids S001 S002
按位置搜索：python get_project_price.py --project-ids 502 505 --car-model-id "xxx" --lat 31.23 --lng 121.47
可选：--distance-km 10 --min-rating 4.8 --sort-by distance
"""

import argparse
import asyncio
import json
import os
from typing import Any, Optional

import httpx

QUERY_NEARBY_URL: str = os.getenv("QUERY_NEARBY_URL", "")

REPAIR_TYPE_NAMES: dict[str, str] = {
    "INTERNATIONAL_BRAND": "国际大厂",
    "DOMESTIC_QUALITY": "国产品质",
    "ORIGINAL": "原厂",
}


async def query(
    project_ids: list[int],
    car_model_id: str,
    shop_ids: list[str],
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    distance_km: int = 10,
    min_rating: Optional[float] = None,
    sort_by: str = "distance",
) -> dict[str, Any]:
    """查询指定门店或附近门店的项目报价。"""
    if not QUERY_NEARBY_URL:
        return {"error": "QUERY_NEARBY_URL 未配置"}

    if not project_ids:
        return {"shops": []}

    payload: dict[str, Any] = {
        "projectIds": list(set(project_ids)),
        "carKey": car_model_id,
        "shopIds": shop_ids,
        "sortBy": sort_by,
    }
    if lat is not None and lng is not None:
        payload["latitude"] = str(lat)
        payload["longitude"] = str(lng)
        payload["distanceKm"] = distance_km
    if min_rating is not None:
        payload["minRating"] = min_rating

    async with httpx.AsyncClient(timeout=10.0) as client:
        response: httpx.Response = await client.post(QUERY_NEARBY_URL, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    if data.get("status") != 0:
        return {"error": data.get("message", "未知错误")}

    shops: list[dict[str, Any]] = []
    for s in (data.get("result", {}).get("shops") or []):
        projects: list[dict[str, Any]] = []
        for p in (s.get("quotationProjectList") or []):
            plans: list[dict[str, Any]] = []
            for plan in (p.get("quotationPlanList") or []):
                repair_type: str = plan.get("type", "")
                plans.append({
                    "name": plan.get("name", ""),
                    "type": repair_type,
                    "type_label": REPAIR_TYPE_NAMES.get(repair_type, repair_type),
                    "price": str(plan.get("price", "")),
                    "qa": plan.get("qa") or None,
                })
            projects.append({
                "project_id": p.get("id", 0),
                "project_name": p.get("name", ""),
                "plans": plans,
            })
        shops.append({
            "shop_id": str(s.get("shopId", "")),
            "shop_name": s.get("shopName", ""),
            "distance_km": s.get("distanceKm", 0),
            "rating": s.get("rating") or None,
            "address": s.get("address") or None,
            "projects": projects,
        })

    return {"shops": shops}


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--project-ids", nargs="+", type=int, required=True, help="项目 ID 列表")
    parser.add_argument("--car-model-id", required=True, help="车型编码")
    parser.add_argument("--shop-ids", nargs="+", required=True, help="门店 ID 列表")
    parser.add_argument("--lat", type=float, default=None, help="纬度（可选，按位置搜索时使用）")
    parser.add_argument("--lng", type=float, default=None, help="经度（可选，按位置搜索时使用）")
    parser.add_argument("--distance-km", type=int, default=10, help="搜索距离范围（公里）")
    parser.add_argument("--min-rating", type=float, default=None, help="最低评分过滤")
    parser.add_argument("--sort-by", default="distance", choices=["distance", "rating", "price"], help="排序方式")
    args: argparse.Namespace = parser.parse_args()

    result: dict[str, Any] = asyncio.run(query(
        project_ids=args.project_ids,
        car_model_id=args.car_model_id,
        shop_ids=args.shop_ids,
        lat=args.lat,
        lng=args.lng,
        distance_km=args.distance_km,
        min_rating=args.min_rating,
        sort_by=args.sort_by,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
