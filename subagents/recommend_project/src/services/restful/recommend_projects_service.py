"""推荐项目服务 — 根据车辆信息和项目分类查询推荐项目。"""

from __future__ import annotations

import math
import os
from typing import Any

import httpx

from agent_sdk.logging import log_http_request, log_http_response

_API_PATH: str = "/service_ai_datamanager/project/maintainProjectTreeByCarKey"


def _get_datamanager_url() -> str:
    """从环境变量获取 datamanager 服务地址。"""
    return os.getenv("DATAMANAGER_URL")


async def query_recommend_projects(
    car_key: str = "",
    category_ids: list[int] | None = None,
    car_age_year: float | None = None,
    mileage_km: float | None = None,
) -> list[dict[str, Any]]:
    """查询推荐项目列表。

    Args:
        car_key: 车型编码。
        category_ids: 项目分类 ID 列表。
        car_age_year: 车龄（年），内部转换为月。
        mileage_km: 里程数（千米），内部取整。

    Returns:
        项目列表，每项包含 project_id 和 project_name。

    Raises:
        RuntimeError: API 返回错误。
    """
    month: int = 0
    if car_age_year is not None:
        month = int(math.ceil(car_age_year * 12))

    mileage: int = 0
    if mileage_km is not None:
        mileage = int(mileage_km)

    url: str = _get_datamanager_url().rstrip("/") + _API_PATH
    payload: dict[str, Any] = {
        "carKey": car_key,
        "primaryPartIds": [],
        "packageIds": [],
        "categoryIds": category_ids or [],
        "month": month,
        "mileage": mileage,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp: httpx.Response = await client.post(url, json=payload)
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()

    if data.get("status") != 0:
        error_msg: str = data.get("message") or "未知错误"
        raise RuntimeError(f"查询推荐项目失败: {error_msg}")

    raw_tree: list[dict[str, Any]] = data.get("result", {}).get("projectTree", [])
    return _extract_projects(raw_tree)


def _extract_projects(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """递归提取 dataType=project 的叶子节点，只保留 id 和 name。"""
    result: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("dataType") == "project":
            result.append({"project_id": str(node["id"]), "project_name": node["name"]})
        children: list[dict[str, Any]] | None = node.get("childList")
        if children:
            result.extend(_extract_projects(children))
    return result
