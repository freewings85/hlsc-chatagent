#!/usr/bin/env python3
"""查询项目的市场行情参考价（不依赖门店和位置）。

用法：python query_market_price.py --project-ids 502 505 --car-model-id "xxx"
"""

import argparse
import asyncio
import json
import os
from typing import Any

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_MARKET_PRICE_PATH: str = "/service_ai_datamanager/quotation/quotationIndustryByPackageId"


async def query(project_ids: list[int], car_model_id: str) -> dict[str, Any]:
    """查询项目行情价，每个项目取第一个有 price 的方案价格。"""
    if not DATA_MANAGER_URL:
        return {"error": "DATA_MANAGER_URL 未配置"}

    if not project_ids:
        return {"projects": []}

    url: str = f"{DATA_MANAGER_URL}{_MARKET_PRICE_PATH}"
    payload: dict[str, Any] = {
        "carKey": car_model_id,
        "projectPackageIds": list(set(project_ids)),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response: httpx.Response = await client.post(url, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    if data.get("status") != 0:
        return {"error": data.get("message", "未知错误")}

    projects: list[dict[str, Any]] = []
    for p in (data.get("result", {}).get("quotationProjectList") or []):
        price: str = ""
        for plan in (p.get("quotationPlanList") or []):
            plan_price: str = str(plan.get("price", "")).strip()
            if plan_price:
                price = plan_price
                break
        projects.append({
            "project_id": p.get("id", 0),
            "market_price": price or None,
        })

    return {"projects": projects}


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--project-ids", nargs="+", type=int, required=True, help="项目 ID 列表")
    parser.add_argument("--car-model-id", required=True, help="车型编码（L2 精度）")
    args: argparse.Namespace = parser.parse_args()

    result: dict[str, Any] = asyncio.run(query(
        project_ids=args.project_ids,
        car_model_id=args.car_model_id,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
