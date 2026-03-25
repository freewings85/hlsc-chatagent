"""商户相关接口 — 转发到 DataManager Shop 模块。"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/shops", tags=["shops"])

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_NEARBY_SHOPS_PATH: str = "/service_ai_datamanager/shop/getNearbyShops"
_SHOPS_BY_ID_PATH: str = "/service_ai_datamanager/shop/getShopsById"


# ---------- 网关接口模型 ----------

class NearbyShopsRequest(BaseModel):
    """网关入参 — projectIds 对外，转发时改为 packageIds"""
    latitude: float
    longitude: float
    top: int = 5
    radius: int = 100000
    order_by: str = "distance"
    project_ids: Optional[list[int]] = None


class ShopsByIdRequest(BaseModel):
    """获取指定商户详情"""
    shop_ids: list[int]


# ---------- 路由 ----------

@router.post("/query-nearby")
async def nearby_shops(req: NearbyShopsRequest) -> dict[str, Any]:
    """搜索附近商户 — 转发到 DataManager 并改写字段名。"""
    if not DATA_MANAGER_URL:
        return {"status": -1, "message": "DATA_MANAGER_URL 未配置"}

    url: str = f"{DATA_MANAGER_URL}{_NEARBY_SHOPS_PATH}"

    # 入参改写：project_ids → packageIds, order_by → orderBy
    payload: dict[str, Any] = {
        "latitude": req.latitude,
        "longitude": req.longitude,
        "top": req.top,
        "radius": req.radius,
        "orderBy": req.order_by,
    }
    if req.project_ids:
        payload["packageIds"] = req.project_ids

    logger.info("-> POST %s %s", url, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
    except Exception as e:
        logger.error("转发失败: %s", e)
        return {"status": -1, "message": str(e)}

    logger.info("<- %s %s", response.status_code, data)

    # 返回值改写：packageId → projectId, packages → projects
    if data.get("status") == 0:
        result: Any = data.get("result")
        if isinstance(result, dict):
            result = _rewrite_result(result)
        return {"status": 0, "message": "执行成功", "result": result}
    else:
        return {
            "status": data.get("status", -1),
            "message": data.get("message", "未知错误"),
        }


@router.post("/query-by-ids")
async def shops_by_id(req: ShopsByIdRequest) -> dict[str, Any]:
    """获取指定商户详情 — 转发到 DataManager 并改写字段名。"""
    if not DATA_MANAGER_URL:
        return {"status": -1, "message": "DATA_MANAGER_URL 未配置"}

    url: str = f"{DATA_MANAGER_URL}{_SHOPS_BY_ID_PATH}"

    # 入参改写：shop_ids → commercialIds
    payload: dict[str, Any] = {
        "commercialIds": req.shop_ids,
    }

    logger.info("-> POST %s %s", url, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
    except Exception as e:
        logger.error("转发失败: %s", e)
        return {"status": -1, "message": str(e)}

    logger.info("<- %s %s", response.status_code, data)

    if data.get("status") == 0:
        result: Any = data.get("result")
        if isinstance(result, dict):
            result = _rewrite_result(result)
        return {"status": 0, "message": "执行成功", "result": result}
    else:
        return {
            "status": data.get("status", -1),
            "message": data.get("message", "未知错误"),
        }


def _rewrite_result(result: dict[str, Any]) -> dict[str, Any]:
    """递归改写返回值中的字段名。"""
    rewritten: dict[str, Any] = {}
    for key, value in result.items():
        new_key: str = _rewrite_key(key)
        if isinstance(value, dict):
            rewritten[new_key] = _rewrite_result(value)
        elif isinstance(value, list):
            rewritten[new_key] = [
                _rewrite_result(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            rewritten[new_key] = value
    return rewritten


# 字段名映射
_KEY_MAP: dict[str, str] = {
    "packageId": "projectId",
    "packages": "projects",
}


def _rewrite_key(key: str) -> str:
    return _KEY_MAP.get(key, key)
