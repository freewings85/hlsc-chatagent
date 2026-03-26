"""商户相关 mock 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

try:
    from .mock_data import SHOP_HISTORY_BY_USER, SHOP_TYPES, SHOPS, get_shop, public_shop
except ImportError:
    from routes.mock_data import SHOP_HISTORY_BY_USER, SHOP_TYPES, SHOPS, get_shop, public_shop

router: APIRouter = APIRouter(tags=["shops"])


def _ok(result: Any) -> dict[str, Any]:
    return result


@router.post("/service_ai_datamanager/shop/getNearbyShops")
async def get_nearby_shops(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    shop_ids = set(payload.get("shop_ids") or [])
    project_ids = set(payload.get("project_ids") or [])
    shop_type_ids = set(payload.get("shop_type_ids") or [])
    keyword = (payload.get("keyword") or "").strip().lower()
    min_rating = payload.get("min_rating")
    min_trading_count = payload.get("min_trading_count")
    top = int(payload.get("top", 5))
    order_by = payload.get("order_by", "distance")

    items = SHOPS[:]
    if shop_ids:
        items = [shop for shop in items if shop["shop_id"] in shop_ids]
    if project_ids:
        items = [
            shop for shop in items
            if set(shop["project_ids"]).intersection(project_ids)
        ]
    if shop_type_ids:
        items = [shop for shop in items if shop["shop_type_id"] in shop_type_ids]
    if keyword:
        items = [
            shop for shop in items
            if keyword in shop["shop_name"].lower()
            or any(keyword in tag.lower() for tag in shop["tags"])
        ]
    if min_rating is not None:
        items = [shop for shop in items if shop["rating"] >= float(min_rating)]
    if min_trading_count is not None:
        items = [shop for shop in items if shop["trading_count"] >= int(min_trading_count)]

    for key in reversed([part.strip() for part in order_by.split(",") if part.strip()]):
        reverse = key in {"rating", "trading_count"}
        if key == "distance":
            items.sort(key=lambda x: x["distance_m"], reverse=False)
        elif key == "rating":
            items.sort(key=lambda x: x["rating"], reverse=True)
        elif key == "trading_count":
            items.sort(key=lambda x: x["trading_count"], reverse=True)

    items = items[:top]
    result = {
        "query": {
            "project_ids": list(project_ids),
            "shop_type_ids": list(shop_type_ids),
            "keyword": payload.get("keyword"),
            "order_by": [part.strip() for part in order_by.split(",") if part.strip()],
        },
        "items": [{"shop": public_shop(shop)} for shop in items],
        "summary": {"total": len(items)},
    }
    return _ok(result)


@router.post("/service_ai_datamanager/shop/getShopsById")
async def get_shops_by_id(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    shop_ids = payload.get("shop_ids") or []
    items = []
    for shop_id in shop_ids:
        shop = get_shop(int(shop_id))
        if shop is not None:
            items.append({"shop": public_shop(shop)})
    return _ok({"items": items, "summary": {"total": len(items)}})


@router.post("/service_ai_datamanager/shop/getLatestVisitedShops")
async def get_latest_visited_shops(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user_id = str(payload.get("user_id", ""))
    top = int(payload.get("top", 1))
    rows = SHOP_HISTORY_BY_USER.get(user_id, {}).get("latest", [])[:top]
    items = []
    for row in rows:
        shop = get_shop(row["shop_id"])
        if shop is None:
            continue
        items.append(
            {
                "shop": public_shop(shop),
                "relation_data": {
                    "last_order_code": row["last_order_code"],
                    "last_order_time": row["last_order_time"],
                },
            }
        )
    return _ok({"query": {"user_id": user_id, "mode": "latest"}, "items": items})


@router.post("/service_ai_datamanager/shop/getHistoryVisitedShops")
async def get_history_visited_shops(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    user_id = str(payload.get("user_id", ""))
    top = int(payload.get("top", 5))
    rows = SHOP_HISTORY_BY_USER.get(user_id, {}).get("history", [])[:top]
    items = []
    for row in rows:
        shop = get_shop(row["shop_id"])
        if shop is None:
            continue
        items.append({"shop": public_shop(shop)})
    return _ok({"query": {"user_id": user_id, "mode": "history"}, "items": items})


@router.get("/service_ai_datamanager/shop/getAllShopType")
@router.post("/service_ai_datamanager/shop/getAllShopType")
async def get_all_shop_type() -> dict[str, Any]:
    return _ok({"items": SHOP_TYPES})
