"""报价相关 mock 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

try:
    from .mock_data import CAR_MODEL, MARKET_QUOTES, NEARBY_QUOTES, SHOPS, TIRE_QUOTES, get_project, public_shop
except ImportError:
    from routes.mock_data import CAR_MODEL, MARKET_QUOTES, NEARBY_QUOTES, SHOPS, TIRE_QUOTES, get_project, public_shop

router: APIRouter = APIRouter(tags=["quotations"])


def _ok(result: Any) -> dict[str, Any]:
    return result


@router.post("/service_ai_datamanager/quotation/quotationByCarKeyNearby")
async def quotation_by_car_key_nearby(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    project_ids = [int(value) for value in (payload.get("project_ids") or []) if value is not None]
    shop_ids = set(int(value) for value in (payload.get("shop_ids") or []))
    items: list[dict[str, Any]] = []
    for shop in SHOPS:
        if shop_ids and shop["shop_id"] not in shop_ids:
            continue
        for project_id in project_ids:
            quotation = NEARBY_QUOTES.get((shop["shop_id"], project_id))
            project = get_project(project_id)
            if quotation is None or project is None:
                continue
            items.append(
                {
                    "shop": public_shop(shop),
                    "quotation": {
                        "project_id": project_id,
                        "project_name": project["project_name"],
                        "plan_name": quotation["plan_name"],
                        "plan_type": quotation["plan_type"],
                        "total_price": quotation["total_price"],
                        "price_text": quotation["price_text"],
                    },
                }
            )
    items.sort(key=lambda item: item["quotation"]["total_price"])
    for index, item in enumerate(items, start=1):
        item["comparison_data"] = {
            "rank": index,
            "comparison_basis": "按 total_price 升序",
            "price_gap": round(item["quotation"]["total_price"] - items[0]["quotation"]["total_price"], 2),
        }
    return _ok(
        {
            "query": {
                "project_ids": project_ids,
                "car_model_id": payload.get("car_model_id", CAR_MODEL["car_model_id"]),
                "distance_km": payload.get("distance_km", 10),
            },
            "items": items,
            "summary": {"total": len(items)},
        }
    )


@router.post("/service_ai_datamanager/quotation/quotationIndustryByPackageId")
async def quotation_industry_by_package_id(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    project_ids = [int(value) for value in (payload.get("project_ids") or []) if value is not None]
    items = []
    for project_id in project_ids:
        quotation = MARKET_QUOTES.get(project_id)
        project = get_project(project_id)
        if quotation is None or project is None:
            continue
        items.append(
            {
                "quotation": {
                    "project_id": project_id,
                    "project_name": project["project_name"],
                    "plan_name": quotation["plan_name"],
                    "plan_type": quotation["plan_type"],
                    "total_price": quotation["total_price"],
                    "price_text": quotation["price_text"],
                }
            }
        )
    return _ok(
        {
            "query": {
                "project_ids": project_ids,
                "car_model_id": payload.get("car_model_id", CAR_MODEL["car_model_id"]),
            },
            "items": items,
        }
    )


@router.post("/service_ai_datamanager/quotation/findATireQuote")
async def find_a_tire_quote(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    tire_specifications = payload.get("tire_specifications") or []
    items = []
    for spec in tire_specifications:
        quotation = TIRE_QUOTES.get(spec)
        if quotation is None:
            continue
        items.append(
            {
                "tire_specification": spec,
                "quotation": quotation,
            }
        )
    return _ok({"items": items})
