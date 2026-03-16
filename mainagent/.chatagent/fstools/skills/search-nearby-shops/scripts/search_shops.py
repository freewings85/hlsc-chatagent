#!/usr/bin/env python3
"""搜索附近汽修门店。

用法：python search_shops.py --lat 31.2 --lng 121.5 --keyword 刹车专修 --topk 5
"""

import argparse
import asyncio
import json
import os

import httpx

SEARCH_REPAIR_SHOPS_URL = os.getenv("SEARCH_REPAIR_SHOPS_URL", "")


async def search(keyword: str, lat: float, lng: float, topk: int) -> dict:
    if not SEARCH_REPAIR_SHOPS_URL:
        return {"error": "SEARCH_REPAIR_SHOPS_URL 未配置"}

    payload: dict = {
        "topk": topk,
    }
    if keyword:
        payload["keyword"] = keyword
    if lat and lng:
        payload["location"] = f"{lat},{lng}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(SEARCH_REPAIR_SHOPS_URL, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            return {"error": data.get("message", "未知错误")}

        items = data.get("result", {}).get("items", [])
        shops = []
        for item in items:
            shops.append({
                "shop_id": item.get("shopId", ""),
                "name": item.get("name", ""),
                "address": item.get("address", ""),
                "distance": item.get("distance", ""),
                "rating": item.get("rating"),
                "review_count": item.get("reviewCount", 0),
                "phone": item.get("phone", ""),
                "tags": item.get("tags", []),
            })

        return {"total": data.get("result", {}).get("total", 0), "shops": shops}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()

    result = asyncio.run(search(args.keyword, args.lat, args.lng, args.topk))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
