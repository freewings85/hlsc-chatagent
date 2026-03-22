#!/usr/bin/env python3
"""根据关键词聚合检索故障诊断项目。

用法：python search_project_by_keyword.py --keyword "刹车异响"
"""

import argparse
import asyncio
import json
import os
from typing import Any

import httpx

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")

_TRIGGER_SEARCH_PATH: str = (
    "/service_ai_datamanager/projecttriggerconditions/searchprojecttriggerconditions"
)
_TRIGGER_PACKAGE_PATH: str = (
    "/service_ai_datamanager/project/getProjectPackageByProjectId"
)
_FAULT_SEARCH_PATH: str = (
    "/service_ai_datamanager/faultphenomenon/searchfaultphenomenon"
)
_FAULT_PACKAGE_PATH: str = (
    "/service_ai_datamanager/project/getProjectPackageByPrimaryNameId"
)


async def _search_by_trigger(
    base_url: str,
    search_key: str,
    top_k: int,
    similarity_threshold: float,
    vector_similarity_weight: float,
) -> list[dict[str, Any]]:
    """根据触发条件检索项目并查询关联套餐。"""
    search_payload: dict[str, Any] = {
        "searchKey": search_key,
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
        "vector_similarity_weight": vector_similarity_weight,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp: httpx.Response = await client.post(
            base_url + _TRIGGER_SEARCH_PATH, json=search_payload,
        )
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()
    if data.get("status") != 0:
        raise RuntimeError(f"触发条件检索失败: {data.get('message', '未知错误')}")

    raw_items: list[dict[str, Any]] = data.get("result", [])

    items_with_projects: list[dict[str, Any]] = []
    all_project_ids: set[int] = set()
    for item in raw_items:
        project_ids: list[int] = item.get("primary_project_ids") or []
        if not project_ids:
            continue
        items_with_projects.append(item)
        all_project_ids.update(project_ids)

    if not all_project_ids:
        return []

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(
            base_url + _TRIGGER_PACKAGE_PATH,
            json={"projectIds": list(all_project_ids)},
        )
        resp.raise_for_status()

    package_data: dict[str, Any] = resp.json()
    if package_data.get("status") != 0:
        raise RuntimeError(f"项目套餐查询失败: {package_data.get('message', '未知错误')}")

    package_by_project: dict[int, list[dict[str, Any]]] = {}
    for pkg in package_data.get("result", []):
        pid: int = pkg.get("projectId", 0)
        package_by_project.setdefault(pid, []).append({
            "project_id": str(pkg.get("packageId", "")),
            "project_name": pkg.get("packageName", ""),
        })

    result: list[dict[str, Any]] = []
    for item in items_with_projects:
        project_ids = item.get("primary_project_ids") or []
        projects: list[dict[str, Any]] = []
        for pid in project_ids:
            projects.extend(package_by_project.get(pid, []))
        result.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "projects": projects,
        })
    return result


async def _search_by_fault(
    base_url: str,
    search_key: str,
    top_k: int,
    similarity_threshold: float,
    vector_similarity_weight: float,
) -> list[dict[str, Any]]:
    """根据故障关键词检索故障信息并查询关联套餐。"""
    search_payload: dict[str, Any] = {
        "searchKey": search_key,
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
        "vector_similarity_weight": vector_similarity_weight,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp: httpx.Response = await client.post(
            base_url + _FAULT_SEARCH_PATH, json=search_payload,
        )
        resp.raise_for_status()

    data: dict[str, Any] = resp.json()
    if data.get("status") != 0:
        raise RuntimeError(f"故障信息检索失败: {data.get('message', '未知错误')}")

    raw_items: list[dict[str, Any]] = data.get("result", [])

    all_primary_part_ids: set[int] = set()
    for item in raw_items:
        part_ids: list[int] = item.get("primary_part_ids") or []
        all_primary_part_ids.update(part_ids)

    package_by_primary: dict[int, list[dict[str, Any]]] = {}
    if all_primary_part_ids:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(
                base_url + _FAULT_PACKAGE_PATH,
                json={"primaryNameIds": list(all_primary_part_ids)},
            )
            resp.raise_for_status()

        package_data: dict[str, Any] = resp.json()
        if package_data.get("status") != 0:
            raise RuntimeError(f"项目套餐查询失败: {package_data.get('message', '未知错误')}")

        for pkg in package_data.get("result", []):
            pid: int = pkg.get("projectId", 0)
            package_by_primary.setdefault(pid, []).append({
                "project_id": str(pkg.get("packageId", "")),
                "project_name": pkg.get("packageName", ""),
            })

    result: list[dict[str, Any]] = []
    for item in raw_items:
        part_ids = item.get("primary_part_ids") or []
        projects: list[dict[str, Any]] = []
        for pid in part_ids:
            projects.extend(package_by_primary.get(pid, []))
        result.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "projects": projects,
        })
    return result


def _merge_results(
    trigger_results: list[dict[str, Any]],
    fault_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并两个来源的结果，按 title 去重。"""
    seen_titles: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in trigger_results + fault_results:
        title: str = item.get("title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        merged.append(item)
    return merged


async def search(
    keyword: str,
    top_k: int = 3,
    similarity_threshold: float = 0.3,
    vector_similarity_weight: float = 0.3,
) -> dict[str, Any]:
    """并行检索触发条件和故障信息，聚合返回诊断结果。"""
    if not DATA_MANAGER_URL:
        return {"error": "DATA_MANAGER_URL 未配置"}

    base_url: str = DATA_MANAGER_URL.rstrip("/")

    trigger_results: list[dict[str, Any]]
    fault_results: list[dict[str, Any]]
    trigger_results, fault_results = await asyncio.gather(
        _search_by_trigger(base_url, keyword, top_k, similarity_threshold, vector_similarity_weight),
        _search_by_fault(base_url, keyword, top_k, similarity_threshold, vector_similarity_weight),
    )

    merged: list[dict[str, Any]] = _merge_results(trigger_results, fault_results)
    return {"diagnoses": merged}


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True, help="故障现象或需求关键词")
    parser.add_argument("--top-k", type=int, default=3, help="检索条数")
    parser.add_argument("--similarity-threshold", type=float, default=0.3)
    parser.add_argument("--vector-similarity-weight", type=float, default=0.3)
    args: argparse.Namespace = parser.parse_args()

    result: dict[str, Any] = asyncio.run(search(
        keyword=args.keyword,
        top_k=args.top_k,
        similarity_threshold=args.similarity_threshold,
        vector_similarity_weight=args.vector_similarity_weight,
    ))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
