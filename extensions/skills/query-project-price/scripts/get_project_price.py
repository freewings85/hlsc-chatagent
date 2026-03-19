#!/usr/bin/env python3
"""查询项目门店报价。

用法：python get_project_price.py --project_ids 101,102 --car_model_id CAR-001 --shop_ids S001,S002
"""

import argparse
import asyncio
import json
import os

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
QUOTATION_NEARBY_PATH: str = "/service_ai_datamanager/quotation/quotationByCarKeyNearby"


async def query_project_price(
    project_ids: list[int],
    car_model_id: str,
    shop_ids: list[int],
    sort_by: str = "distance",
) -> str:
    """调用 DATA_MANAGER_URL 查询项目门店报价，返回简化 JSON。"""
    if not DATA_MANAGER_URL:
        return "Error: DATA_MANAGER_URL 未配置"

    if not project_ids:
        return "Error: 未提供项目 ID"

    if not shop_ids:
        return "Error: 未提供门店 ID"

    payload: dict = {
        "packageIds": list(set(project_ids)),
        "carKey": car_model_id,
        "sortBy": sort_by,
        "shopIds": shop_ids,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        url: str = f"{DATA_MANAGER_URL}{QUOTATION_NEARBY_PATH}"
        response: httpx.Response = await client.post(url, json=payload)
        response.raise_for_status()
        data: dict = response.json()
        print(f"[DEBUG] url={url}, payload={json.dumps(payload, ensure_ascii=False)}")
        print(f"[DEBUG] response={json.dumps(data, ensure_ascii=False)}")

        if data.get("status") != 0:
            return f"Error: {data.get('message', '未知错误')}"

        raw_shops: list[dict] = data.get("result", {}).get("shops") or []
        shops: list[dict] = _simplify_shops(raw_shops)

        if not shops:
            return "未找到提供相关项目的门店"

        return json.dumps({"shops": shops}, ensure_ascii=False)


def _simplify_shops(raw_shops: list[dict]) -> list[dict]:
    """从 API 响应中提取关键字段，返回简化的门店报价结构。"""
    shop_map: dict[str, dict] = {}
    seen_projects: dict[str, set[int]] = {}

    for s in raw_shops:
        shop_id: str = str(s.get("shopId", ""))
        if shop_id not in shop_map:
            shop_map[shop_id] = {
                "shopId": shop_id,
                "shopName": s.get("shopName", ""),
                "distanceKm": s.get("distanceKm", 0),
                "rating": s.get("rating") or None,
                "address": s.get("address") or None,
                "quotationProjectList": [],
            }
            seen_projects[shop_id] = set()

        for p in s.get("quotationProjectList") or []:
            project_id: int = p.get("id", 0)
            if project_id in seen_projects[shop_id]:
                continue
            seen_projects[shop_id].add(project_id)

            plans: list[dict] = []
            for plan in p.get("quotationPlanList") or []:
                plans.append({
                    "name": plan.get("name", ""),
                    "price": plan.get("price", ""),
                })
            shop_map[shop_id]["quotationProjectList"].append({
                "id": project_id,
                "name": p.get("name", ""),
                "quotationPlanList": plans,
            })

    return list(shop_map.values())


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--project_ids", required=True, help="逗号分隔的项目 ID")
    parser.add_argument("--car_model_id", required=True, help="车型编码")
    parser.add_argument("--shop_ids", required=True, help="逗号分隔的门店 ID")
    parser.add_argument("--sort_by", default="distance", help="排序方式：distance/rating/price")
    args: argparse.Namespace = parser.parse_args()

    project_ids: list[int] = [int(x.strip()) for x in args.project_ids.split(",") if x.strip()]
    shop_ids: list[int] = [int(x.strip()) for x in args.shop_ids.split(",") if x.strip()]

    result: str = asyncio.run(query_project_price(
        project_ids=project_ids,
        car_model_id=args.car_model_id,
        shop_ids=shop_ids,
        sort_by=args.sort_by,
    ))
    print(result)


if __name__ == "__main__":
    main()
