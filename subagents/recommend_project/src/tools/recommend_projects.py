"""RecommendProject Subagent 工具集。

- recommend_projects: 根据车辆信息和推荐分类，调用 maintainProjectTreeByCarKey 获取推荐项目
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end, log_http_request, log_http_response

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
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("recommend_projects", sid, rid, {
        "car_key": vehicle_info.car_key, "mileage": vehicle_info.mileage_km,
        "age": vehicle_info.car_age_year, "categories": category_ids,
    })

    try:
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
            session_id=sid,
            request_id=rid,
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

        log_tool_end("recommend_projects", sid, rid, {"project_count": len(projects)})
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        log_tool_end("recommend_projects", sid, rid, exc=e)
        return f"Error: recommend_projects failed - {e}"


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
    session_id: str = "",
    request_id: str = "",
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

    log_http_request(url, "POST", session_id, request_id, {
        "carKey": car_key, "categoryIds": category_ids,
        "month": month, "mileage": mileage,
    })

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
            raise RuntimeError(f"查询推荐项目接口调用失败: {exc}") from exc

    response_json: dict[str, Any] = resp.json()
    log_http_response(url, resp.status_code, session_id, request_id)

    status: int | None = response_json.get("status")
    if status != 0:
        message: str = response_json.get("message") or "未知错误"
        raise RuntimeError(f"查询推荐项目失败: {message}")

    return response_json.get("result", {})


RECOMMEND_PROJECT_TOOLS: list[str] = ["recommend_projects"]


def create_recommend_project_tool_map() -> dict[str, Any]:
    """创建 recommend_project 工具映射。"""
    from src.tools.query_car_key import query_car_key

    return {
        "query_car_key": query_car_key,
        "recommend_projects": recommend_projects,
    }
