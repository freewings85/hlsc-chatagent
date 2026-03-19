#!/usr/bin/env python3
"""搜索附近汽修门店。

用法：python search_shops.py --lat 31.2 --lng 121.5 --keyword 刹车专修 --top 5
"""

import argparse
import asyncio
import json
import os

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
NEARBY_SHOPS_PATH: str = "/service_ai_datamanager/shop/getNearbyShops"


async def search(
    keyword: str,
    lat: float,
    lng: float,
    top: int,
    radius: int,
    order_by: str,
    commercial_type: int | None,
    opening_hour: str | None,
    province_id: int | None,
    city_id: int | None,
    district_id: int | None,
    address_name: str | None,
    package_ids: str | None,
    min_rating: float | None,
    min_trading_count: int | None,
) -> dict:
    if not DATA_MANAGER_URL:
        return {"error": "DATA_MANAGER_URL 未配置"}

    url: str = f"{DATA_MANAGER_URL}{NEARBY_SHOPS_PATH}"
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

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            return {"error": data.get("message", "未知错误")}

        result = data.get("result") or {}
        commercials = result.get("commercials") or []
        shops = []
        for item in commercials:
            distance_m = item.get("distance", 0)
            distance_km = round(distance_m / 1000, 1) if distance_m else 0

            tags = item.get("serviceScope", "")
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

            shops.append({
                "shop_id": item.get("commercialId", ""),
                "name": item.get("commercialName", ""),
                "address": item.get("address", ""),
                "province": item.get("provinceName", ""),
                "city": item.get("cityName", ""),
                "district": item.get("districtName", ""),
                "distance": f"{distance_km}km",
                "rating": item.get("rating"),
                "trading_count": item.get("tradingCount", 0),
                "phone": item.get("phone", ""),
                "tags": tag_list,
                "opening_hours": item.get("openingHours", ""),
            })

        return {"total": len(shops), "shops": shops}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--radius", type=int, default=10000)
    parser.add_argument("--order-by", default="distance")
    parser.add_argument("--commercial-type", type=int, default=None)
    parser.add_argument("--opening-hour", default=None)
    parser.add_argument("--province-id", type=int, default=None)
    parser.add_argument("--city-id", type=int, default=None)
    parser.add_argument("--district-id", type=int, default=None)
    parser.add_argument("--address-name", default=None)
    parser.add_argument("--package-ids", default=None)
    parser.add_argument("--min-rating", type=float, default=None)
    parser.add_argument("--min-trading-count", type=int, default=None)
    args = parser.parse_args()

    result = asyncio.run(search(
        args.keyword, args.lat, args.lng, args.top, args.radius, args.order_by,
        args.commercial_type, args.opening_hour,
        args.province_id, args.city_id, args.district_id, args.address_name,
        args.package_ids, args.min_rating, args.min_trading_count,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
