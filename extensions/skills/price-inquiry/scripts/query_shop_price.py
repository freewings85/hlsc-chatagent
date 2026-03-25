#!/usr/bin/env python3
"""查询项目在指定门店的报价。

用法：python query_shop_price.py --project-ids 502 505 --car-model-id 56 --shop-ids 54
"""

import argparse
import asyncio
import json
import os
from typing import Any

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_SHOP_PRICE_PATH: str = "/service_ai_datamanager/quotation/quotationByCarKeyNearby"

REPAIR_TYPE_NAMES: dict[str, str] = {
    "INTERNATIONAL_BRAND": "国际大厂",
    "DOMESTIC_QUALITY": "国产品质",
    "ORIGINAL": "原厂",
}


async def query(
    project_ids: list[int],
    car_model_id: str,
    shop_ids: list[str],
) -> dict[str, Any]:
    """查询指定门店的项目报价。"""
    if not DATA_MANAGER_URL:
        return {"error": "DATA_MANAGER_URL 未配置"}

    if not project_ids:
        return {"shops": []}

    url: str = f"{DATA_MANAGER_URL}{_SHOP_PRICE_PATH}"
    payload: dict[str, Any] = {
        "carKey": car_model_id,
        "packageIds": list(set(project_ids)),
        "shopIds": [int(sid) for sid in shop_ids],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response: httpx.Response = await client.post(url, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    if data.get("status") != 0:
        return {"error": data.get("message", "未知错误")}

    # API 返回同一 shop 重复多条（每条含一个项目），按 shopId 聚合
    shop_map: dict[str, dict[str, Any]] = {}
    for s in (data.get("result", {}).get("shops") or []):
        shop_id: str = str(s.get("shopId", ""))
        if shop_id not in shop_map:
            shop_map[shop_id] = {
                "shop_id": shop_id,
                "shop_name": s.get("shopName", ""),
                "projects": [],
            }

        for p in (s.get("quotationProjectList") or []):
            plans: list[dict[str, Any]] = []
            for plan in (p.get("quotationPlanList") or []):
                repair_type: str = plan.get("type", "")
                price: str = str(plan.get("price", "")).strip()
                if not price:
                    continue
                plans.append({
                    "name": plan.get("name", ""),
                    "type": repair_type,
                    "type_label": REPAIR_TYPE_NAMES.get(repair_type, repair_type),
                    "price": price,
                })
            shop_map[shop_id]["projects"].append({
                "project_id": p.get("id", 0),
                "project_name": p.get("name", ""),
                "plans": plans,
            })

    return {"shops": list(shop_map.values())}


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--project-ids", nargs="+", type=int, required=True, help="项目 ID 列表")
    parser.add_argument("--car-model-id", required=True, help="车型编码")
    parser.add_argument("--shop-ids", nargs="+", required=True, help="门店 ID 列表")
    args: argparse.Namespace = parser.parse_args()

    result: dict[str, Any] = asyncio.run(query(
        project_ids=args.project_ids,
        car_model_id=args.car_model_id,
        shop_ids=args.shop_ids,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
