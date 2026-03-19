#!/usr/bin/env python3
"""查询项目门店报价。

用法：python get_project_price.py --project_ids 101,102 --car_model_id CAR-001 --shop_ids S001,S002
"""

import argparse
import asyncio
import os

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
QUOTATION_NEARBY_PATH: str = "/service_ai_datamanager/quotation/quotationByCarKeyNearby"

REPAIR_TYPE_NAMES: dict[str, str] = {
    "INTERNATIONAL_BRAND": "国际大厂",
    "DOMESTIC_QUALITY": "国产品质",
    "ORIGINAL": "原厂",
}


async def query_project_price(
    project_ids: list[int],
    car_model_id: str,
    shop_ids: list[str],
    sort_by: str = "distance",
) -> str:
    """调用 DATA_MANAGER_URL 查询项目门店报价，返回格式化文本。"""
    if not DATA_MANAGER_URL:
        return "Error: DATA_MANAGER_URL 未配置"

    if not project_ids:
        return "Error: 未提供项目 ID"

    if not shop_ids:
        return "Error: 未提供门店 ID"

    payload: dict = {
        "projectIds": list(set(project_ids)),
        "carKey": car_model_id,
        "sortBy": sort_by,
        "shopIds": shop_ids,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        url: str = f"{DATA_MANAGER_URL}{QUOTATION_NEARBY_PATH}"
        response: httpx.Response = await client.post(url, json=payload)
        response.raise_for_status()
        data: dict = response.json()

        if data.get("status") != 0:
            return f"Error: {data.get('message', '未知错误')}"

        raw_shops: list[dict] = data.get("result", {}).get("shops") or []
        shops: list[dict] = _merge_shops(raw_shops)

        if not shops:
            return "未找到提供相关项目的门店"

        return _build_summary(shops, sort_by)


def _merge_shops(raw_shops: list[dict]) -> list[dict]:
    """将 API 返回的重复门店（同 shopId 不同项目）合并为一个门店多个项目。"""
    shop_map: dict[str, dict] = {}
    seen_projects: dict[str, set[int]] = {}

    for s in raw_shops:
        shop_id: str = str(s.get("shopId", ""))
        if shop_id not in shop_map:
            shop_map[shop_id] = {
                "shop_id": shop_id,
                "shop_name": s.get("shopName", ""),
                "distance_km": s.get("distanceKm", 0),
                "rating": s.get("rating") or None,
                "address": s.get("address") or None,
                "projects": [],
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
                    "price": str(plan.get("price", "")),
                    "type": plan.get("type", ""),
                    "type_name": REPAIR_TYPE_NAMES.get(plan.get("type", ""), plan.get("type", "")),
                    "qa": plan.get("qa") or None,
                })
            shop_map[shop_id]["projects"].append({
                "project_id": project_id,
                "project_name": p.get("name", ""),
                "plans": plans,
            })

    return list(shop_map.values())


def _build_summary(shops: list[dict], sort_by: str) -> str:
    """构建格式化文本摘要，与 get_project_price 工具输出格式一致。"""
    sort_desc: str = {"distance": "按距离", "rating": "按评分", "price": "按价格"}.get(sort_by, "")
    lines: list[str] = [f"找到 {len(shops)} 家门店的报价（{sort_desc}排序）：", ""]

    for shop in shops:
        rating_text: str = f", 评分{shop['rating']}" if shop["rating"] else ""
        lines.append(f"**{shop['shop_name']}**(shopId={shop['shop_id']}, {shop['distance_km']}km{rating_text}):")

        for proj in shop["projects"]:
            lines.append(f"  {proj['project_name']}(projectId={proj['project_id']}):")
            if proj["plans"]:
                for plan in proj["plans"]:
                    qa_text: str = f", 保质期{plan['qa']}" if plan["qa"] else ""
                    price_text: str = f"¥{plan['price']}" if plan["price"] else "价格待定"
                    lines.append(f"    {plan['name']}(type={plan['type']}): {price_text}{qa_text}")
            else:
                lines.append("    暂无报价")

    lines.append("")
    lines.append("[业务提示] 以上是门店项目报价（含工时和配件），可直接下单。")

    return "\n".join(lines)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--project_ids", required=True, help="逗号分隔的项目 ID")
    parser.add_argument("--car_model_id", required=True, help="车型编码")
    parser.add_argument("--shop_ids", required=True, help="逗号分隔的门店 ID")
    parser.add_argument("--sort_by", default="distance", help="排序方式：distance/rating/price")
    args: argparse.Namespace = parser.parse_args()

    project_ids: list[int] = [int(x.strip()) for x in args.project_ids.split(",") if x.strip()]
    shop_ids: list[str] = [x.strip() for x in args.shop_ids.split(",") if x.strip()]

    result: str = asyncio.run(query_project_price(
        project_ids=project_ids,
        car_model_id=args.car_model_id,
        shop_ids=shop_ids,
        sort_by=args.sort_by,
    ))
    print(result)


if __name__ == "__main__":
    main()
