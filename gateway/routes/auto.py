"""车型相关接口 — 转发到 DataManager Auto 模块。"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

logger: logging.Logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/car-model", tags=["car-model"])

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")
_MATCH_CAR_PATH: str = "/service_ai_datamanager/Auto/getCarModelByQueryKey"


# ---------- 网关接口模型 ----------

class MatchCarModelRequest(BaseModel):
    """网关入参"""
    query: str
    session_id: str = ""


class CarModelResult(BaseModel):
    """改写后的返回结果"""
    car_model_id: str
    car_model_name: str
    vin_code: Optional[str] = None


class MatchCarModelResponse(BaseModel):
    """网关出参"""
    status: int
    message: str = ""
    result: Optional[CarModelResult] = None


# ---------- 路由 ----------

@router.post("/match", response_model=MatchCarModelResponse)
async def match_car_model(req: MatchCarModelRequest) -> MatchCarModelResponse:
    """模糊匹配车型 — 转发到 DataManager 并改写字段名。"""
    if not DATA_MANAGER_URL:
        return MatchCarModelResponse(status=-1, message="DATA_MANAGER_URL 未配置")

    url: str = f"{DATA_MANAGER_URL}{_MATCH_CAR_PATH}"

    # 入参改写：网关字段 → datamanager 字段
    payload: dict[str, Any] = {
        "queryKey": req.query,
        "conversationId": req.session_id,
    }

    logger.info("-> POST %s %s", url, payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
    except Exception as e:
        logger.error("转发失败: %s", e)
        return MatchCarModelResponse(status=-1, message=str(e))

    logger.info("<- %s %s", response.status_code, data)

    # 返回值改写：datamanager 字段 → 网关字段
    if data.get("status") == 0:
        raw_result: dict[str, Any] | None = data.get("result")
        result: CarModelResult | None = None
        if raw_result and raw_result.get("car_key"):
            result = CarModelResult(
                car_model_id=raw_result["car_key"],
                car_model_name=raw_result.get("car_name", ""),
                vin_code=raw_result.get("vin_code") or None,
            )
        return MatchCarModelResponse(status=0, message="执行成功", result=result)
    else:
        return MatchCarModelResponse(
            status=data.get("status", -1),
            message=data.get("message", "未知错误"),
        )
