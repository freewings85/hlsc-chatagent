"""RecommendProject Subagent 工具集。

- recommend_projects: 根据车辆信息和推荐分类，调用 maintainProjectTreeByCarKey 获取推荐项目
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps

logger = logging.getLogger(__name__)

_API_PATH: str = "/project/maintainProjectTreeByCarKey"


def _get_datamanager_url() -> str:
    """从环境变量获取 datamanager 服务地址（Nacos 会自动注入）。"""
    return os.getenv(
        "service.ai.datamanager.url",
        os.getenv("SERVICE_AI_DATAMANAGER_URL", "http://192.168.100.108:50400/service_ai_datamanager"),
    )


class VehicleInfo(BaseModel):
    """车辆信息"""
    car_model_name: str = Field(default="", description="车型名称，如 2024款 宝马 325Li")
    car_key: str = Field(default="", description="车型编码（carKey），用于精确匹配项目")
    vin_code: str = Field(default="", description="VIN 码，如 WBAJB1105MCJ12345")
    mileage_km: Optional[float] = Field(default=None, description="当前里程数（千米），如 35000.0")
    car_age_year: Optional[float] = Field(default=None, description="车龄（年），如 2.5")


async def recommend_projects(
    ctx: RunContext[AgentDeps],
    vehicle_info: VehicleInfo,
    category_ids: list[int] = [],
) -> str:
    """根据车辆信息和推荐分类，调用项目推荐接口获取推荐养车项目。

    调用前应先通过 recommend_policy skill 根据车龄确定 category_ids。

    Args:
        vehicle_info: 车辆信息，包含车型编码、里程数、车龄等。
        category_ids: 项目分类 ID 列表，由 recommend_policy skill 确定。
            如 [3] 改装升级、[2] 美容养护、[1] 维修保养。为空则不限分类。

    Returns:
        推荐的养车项目树 JSON。
    """
    logger.info(
        "推荐养车项目: car_key=%s, car=%s, mileage=%s, age=%s, categories=%s",
        vehicle_info.car_key, vehicle_info.car_model_name,
        vehicle_info.mileage_km, vehicle_info.car_age_year, category_ids,
    )

    # 将车龄（年）转换为月
    month: int = 0
    if vehicle_info.car_age_year is not None:
        month = int(math.ceil(vehicle_info.car_age_year * 12))

    # 里程取整
    mileage: int = 0
    if vehicle_info.mileage_km is not None:
        mileage = int(vehicle_info.mileage_km)

    # 调用 maintainProjectTreeByCarKey 接口
    tree: dict[str, Any] = await _query_maintain_project_tree(
        car_key=vehicle_info.car_key,
        category_ids=category_ids,
        month=month,
        mileage=mileage,
    )

    # 从项目树中提取 dataType=project 的叶子节点，只保留 id 和 name
    projects: list[dict[str, Any]] = _extract_projects(tree.get("projectTree", []))

    # 组装推荐理由
    reasons: list[str] = []
    if vehicle_info.mileage_km is not None:
        reasons.append(f"当前里程 {vehicle_info.mileage_km:.0f} 公里")
    if vehicle_info.car_age_year is not None:
        reasons.append(f"车龄 {vehicle_info.car_age_year:.1f} 年")
    if vehicle_info.car_model_name:
        reasons.append(f"车型 {vehicle_info.car_model_name}")

    result: dict[str, Any] = {
        "vehicle_info": vehicle_info.model_dump(exclude_none=True),
        "category_ids": category_ids,
        "recommend_reason": "、".join(reasons) if reasons else "通用推荐",
        "projects": projects,
    }
    return json.dumps(result, ensure_ascii=False)


def _extract_projects(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """递归提取 dataType=project 的叶子节点，只保留 id 和 name。"""
    result: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("dataType") == "project":
            result.append({"project_id": node["id"], "project_name": node["name"]})
        children: list[dict[str, Any]] | None = node.get("childList")
        if children:
            result.extend(_extract_projects(children))
    return result


async def _query_maintain_project_tree(
    car_key: str,
    category_ids: list[int],
    month: int,
    mileage: int,
) -> dict[str, Any]:
    """调用 maintainProjectTreeByCarKey 接口获取推荐项目树。"""
    url: str = _get_datamanager_url().rstrip("/") + _API_PATH
    payload: dict[str, Any] = {
        "carKey": car_key,
        "primaryPartIds": [],
        "packageIds": [],
        "categoryIds": category_ids,
        "month": month,
        "mileage": mileage,
    }

    logger.info(
        "查询推荐项目树: url=%s, carKey=%s, categoryIds=%s, month=%d, mileage=%d",
        url, car_key, category_ids, month, mileage,
    )

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            resp: httpx.Response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "hlsc-recommend-project/1.0",
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("推荐项目接口调用失败: carKey=%s", car_key)
            raise RuntimeError(f"查询推荐项目接口调用失败: {exc}") from exc

    response_json: dict[str, Any] = resp.json()

    status: int | None = response_json.get("status")
    if status != 0:
        message: str = response_json.get("message") or "未知错误"
        raise RuntimeError(f"查询推荐项目失败: {message}")

    logger.info("查询推荐项目完成: carKey=%s", car_key)
    return response_json.get("result", {})


RECOMMEND_PROJECT_TOOLS: list[str] = ["recommend_projects"]


def create_recommend_project_tool_map() -> dict[str, Any]:
    """创建 recommend_project 工具映射。"""
    from src.tools.query_car_key import query_car_key

    return {
        "query_car_key": query_car_key,
        "recommend_projects": recommend_projects,
    }
