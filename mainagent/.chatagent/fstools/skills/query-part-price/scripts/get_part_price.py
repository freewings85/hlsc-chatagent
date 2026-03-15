#!/usr/bin/env python3
"""查询零部件平台参考价格。

用法：python get_part_price.py --part_ids 123,456 --car_model_id CAR-001
"""

import argparse
import asyncio
import json
import os
import sys

import httpx

QUERY_PART_PRICE_URL = os.getenv("QUERY_PART_PRICE_URL", "")

REPAIR_TYPE_NAMES = {
    "INTERNATIONAL_BRAND": "国际大厂",
    "DOMESTIC_QUALITY": "国产品质",
    "ORIGINAL": "原厂",
}


async def query_price(part_ids: list[int], car_model_id: str) -> dict:
    if not QUERY_PART_PRICE_URL:
        return {"error": "QUERY_PART_PRICE_URL 未配置"}

    if not part_ids:
        return {"error": "未提供零部件 ID"}

    payload = {
        "partPrimaryIds": list(set(part_ids)),
        "carKey": car_model_id,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(QUERY_PART_PRICE_URL, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            return {"error": data.get("message", "未知错误")}

        raw_list = data.get("result", {}).get("partList") or []

        part_list = []
        for part in raw_list:
            items = []
            for item in (part.get("quotationPlanPartItemList") or []):
                items.append({
                    "ai_repair_type": item.get("aiRepairType", ""),
                    "repair_type_name": REPAIR_TYPE_NAMES.get(item.get("aiRepairType", ""), ""),
                    "price": item.get("price", 0),
                    "ware_id": item.get("wareId", 0),
                })
            part_list.append({
                "primary_part_id": part.get("primaryPartId", 0),
                "primary_part_name": part.get("primaryPartName", ""),
                "items": items,
            })

        return {"part_list": part_list}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--part_ids", required=True, help="逗号分隔的零部件 ID")
    parser.add_argument("--car_model_id", required=True)
    args = parser.parse_args()

    part_ids = [int(x.strip()) for x in args.part_ids.split(",") if x.strip()]
    result = asyncio.run(query_price(part_ids, args.car_model_id))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
