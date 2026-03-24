"""推荐项目服务 — 根据车辆信息查询推荐养车项目。"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response

_API_PATH: str = "/service_ai_datamanager/project/getSampleVinProjects"


def _get_datamanager_url() -> str:
    """从环境变量获取 datamanager 服务地址。"""
    url: str | None = os.getenv("DATA_MANAGER_URL")
    if not url:
        raise RuntimeError("DATA_MANAGER_URL 未配置")
    return url


@dataclass
class RecommendVehicleInfo:
    """API 返回的车辆信息"""
    auto_text: str = ""
    vin_code: Optional[str] = None
    month: int = 0


@dataclass
class RecommendProject:
    """推荐项目"""
    project_id: str = ""
    project_name: str = ""


@dataclass
class RecommendResult:
    """推荐项目查询结果"""
    vehicle_info: RecommendVehicleInfo = field(default_factory=RecommendVehicleInfo)
    projects: List[RecommendProject] = field(default_factory=list)


async def query_recommend_projects(
    car_key: str = "",
    car_age_year: float | None = None,
    mileage_km: float | None = None,
    session_id: str = "",
    request_id: str = "",
) -> RecommendResult:
    """查询推荐项目列表。

    Args:
        car_key: 车型编码，为空时使用样本 VIN。
        car_age_year: 车龄（年），内部转换为月。
        mileage_km: 里程数（千米），内部取整。
        session_id: 会话 ID。
        request_id: 请求 ID。

    Returns:
        推荐结果，包含车辆信息和去重后的项目列表。

    Raises:
        RuntimeError: URL 未配置或 API 返回错误。
    """
    month: int = 0
    if car_age_year is not None:
        month = int(math.ceil(car_age_year * 12))

    mileage: int = 0
    if mileage_km is not None:
        mileage = int(mileage_km)

    random_vin: bool = not car_key
    url: str = _get_datamanager_url().rstrip("/") + _API_PATH
    payload: dict[str, Any] = {
        "randomVin": random_vin,
        "carKey": car_key,
        "month": month,
        "mileage": mileage,
    }

    log_http_request(url, "POST", session_id, request_id, payload)

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp: httpx.Response = await client.post(url, json=payload)
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()
    log_http_response(resp.status_code, session_id, request_id, data)

    if data.get("status") != 0:
        error_msg: str = data.get("message") or "未知错误"
        raise RuntimeError(f"查询推荐项目失败: {error_msg}")

    return _parse_result(data.get("result", {}))


def _parse_result(raw: dict[str, Any]) -> RecommendResult:
    """解析 API 响应。"""
    # 解析车辆信息
    raw_vehicle: dict[str, Any] = raw.get("vehicleInfo") or {}
    vehicle_info: RecommendVehicleInfo = RecommendVehicleInfo(
        auto_text=raw_vehicle.get("autoText", ""),
        vin_code=raw_vehicle.get("vinCode") or None,
        month=raw_vehicle.get("month", 0),
    )

    # 解析项目列表并去重
    seen: set[str] = set()
    projects: List[RecommendProject] = []
    for p in (raw.get("packages") or []):
        pid: str = str(p.get("packageId", ""))
        if pid and pid not in seen:
            seen.add(pid)
            projects.append(RecommendProject(
                project_id=pid,
                project_name=p.get("packageName", ""),
            ))

    return RecommendResult(vehicle_info=vehicle_info, projects=projects)
