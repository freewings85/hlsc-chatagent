"""根据故障关键词语义检索故障信息，并查询关联的项目套餐。"""

from __future__ import annotations

import os
from typing import Any

import httpx

_SEARCH_API_PATH: str = (
    "/service_ai_datamanager/projecttriggerconditions/searchprojecttriggerconditions"
)
_PACKAGE_API_PATH: str = (
    "/service_ai_datamanager/project/getProjectPackageByPrimaryNameId"
)


def _get_datamanager_url() -> str:
    """从环境变量获取 datamanager 服务地址。"""
    return os.getenv("DATAMANAGER_URL")


async def search_project_by_fault(
    search_key: str,
    top_k: int = 3,
    similarity_threshold: float = 0.3,
    vector_similarity_weight: float = 0.3,
) -> list[dict[str, Any]]:
    """根据故障关键词检索故障信息，并查询关联的项目套餐。

    流程：
    1. 语义检索匹配的故障信息
    2. 提取并去重所有 primary_project_ids
    3. 调用 getProjectPackageByPrimaryNameId 获取套餐信息
    4. 将套餐信息拼接回故障条目

    Returns:
        故障信息列表，每项包含 title、content 和关联的 projects。

    Raises:
        RuntimeError: API 返回错误。
    """
    base_url: str = _get_datamanager_url().rstrip("/")

    # Step 1: 检索故障信息
    search_url: str = base_url + _SEARCH_API_PATH
    search_payload: dict[str, Any] = {
        "searchKey": search_key,
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
        "vector_similarity_weight": vector_similarity_weight,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp: httpx.Response = await client.post(search_url, json=search_payload)
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()

    if data.get("status") != 0:
        error_msg: str = data.get("message", "未知错误")
        raise RuntimeError(f"故障信息检索失败: {error_msg}")

    raw_items: list[dict[str, Any]] = data.get("result", [])

    # 收集所有 primary_project_ids 并去重
    all_primary_name_ids: set[int] = set()
    for item in raw_items:
        project_ids: list[int] = item.get("primary_project_ids") or []
        all_primary_name_ids.update(project_ids)

    # Step 2: 查询项目套餐（如果有关联 ID）
    package_by_primary: dict[int, list[dict[str, Any]]] = {}
    if all_primary_name_ids:
        package_url: str = base_url + _PACKAGE_API_PATH
        package_payload: dict[str, Any] = {
            "primaryNameIds": list(all_primary_name_ids),
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(package_url, json=package_payload)
            resp.raise_for_status()

        package_data: dict[str, Any] = resp.json()

        if package_data.get("status") != 0:
            error_msg = package_data.get("message", "未知错误")
            raise RuntimeError(f"项目套餐查询失败: {error_msg}")

        # 按 projectId 索引套餐
        for pkg in package_data.get("result", []):
            pid: int = pkg.get("projectId", 0)
            package_by_primary.setdefault(pid, []).append({
                "project_id": str(pkg.get("packageId", "")),
                "project_name": pkg.get("packageName", ""),
            })

    # Step 3: 拼接结果
    result: list[dict[str, Any]] = []
    for item in raw_items:
        project_ids = item.get("primary_project_ids") or []
        projects: list[dict[str, Any]] = []
        for pid in project_ids:
            projects.extend(package_by_primary.get(pid, []))

        result.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "projects": projects,
        })
    return result
