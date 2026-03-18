#!/usr/bin/env python3
"""搜索附近汽修门店。

用法：python search_shops.py --lat 31.2 --lng 121.5 --keyword 刹车专修 --top 5
"""

import argparse
import asyncio
import json
import os

import httpx

SHOP_SERVICE_URL = os.getenv("SHOP_SERVICE_URL", "")


async def search(
    keyword: str,
    lat: float,
    lng: float,
    top: int,
    radius: int,
    order_by: str,
) -> dict:
    if not SHOP_SERVICE_URL:
        return {"error": "SHOP_SERVICE_URL 未配置"}

    url = f"{SHOP_SERVICE_URL}/shop/getNearbyShops"
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

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            return {"error": data.get("message", "未知错误")}

        commercials = data.get("result", {}).get("commercials", [])
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
    args = parser.parse_args()

    result = asyncio.run(search(args.keyword, args.lat, args.lng, args.top, args.radius, args.order_by))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
