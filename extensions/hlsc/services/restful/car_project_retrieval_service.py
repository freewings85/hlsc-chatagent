"""项目融合检索服务 — 精确匹配 + 模糊匹配 + RAG 语义检索。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response

CAR_PROJECT_RETRIEVAL_URL = os.getenv("CAR_PROJECT_RETRIEVAL_URL", "")
CAR_PROJECT_DATASET_ID = os.getenv("CAR_PROJECT_DATASET_ID", "default")


@dataclass
class ProjectMatch:
    """项目匹配项"""
    project_id: int
    project_name: str


@dataclass
class ProjectRetrievalResult:
    """项目检索结果"""
    exact: List[ProjectMatch] = field(default_factory=list)
    fuzzy: List[ProjectMatch] = field(default_factory=list)


class CarProjectRetrievalService:
    """项目融合检索服务"""

    async def retrieval(
        self,
        keyword: str,
        session_id: str = "",
        request_id: str = "",
        primary_project_ids: Optional[List[int]] = None,
    ) -> ProjectRetrievalResult:
        """检索项目。

        Raises:
            RuntimeError: URL 未配置或 API 返回错误
        """
        url = CAR_PROJECT_RETRIEVAL_URL
        if not url:
            raise RuntimeError("CAR_PROJECT_RETRIEVAL_URL 未配置")

        payload: dict = {
            "dataset_id": CAR_PROJECT_DATASET_ID,
            "project_names": [keyword],
            "top_k": 5,
            "similarity_threshold": 0.2,
            "vector_similarity_weight": 0.3,
        }
        if primary_project_ids:
            payload["primary_project_ids"] = primary_project_ids

        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

            if data.get("status") == 0:
                return _parse_result(data.get("result", {}))
            else:
                error_msg = data.get("message", "未知错误")
                raise RuntimeError(f"项目检索失败: {error_msg}")


def _parse_result(raw: dict) -> ProjectRetrievalResult:
    exact = [
        ProjectMatch(project_id=m.get("primary_project_id", 0), project_name=m.get("project_name", ""))
        for m in (raw.get("exact_matched") or [])
    ]

    fuzzy = [
        ProjectMatch(project_id=m.get("primary_project_id", 0), project_name=m.get("project_name", ""))
        for m in (raw.get("fuzzy_matched") or [])
    ]

    # RAG 匹配归入 fuzzy
    for group in (raw.get("rag_matched") or []):
        for c in (group.get("candidates") or []):
            fuzzy.append(ProjectMatch(
                project_id=c.get("primary_project_id", 0),
                project_name=c.get("project_name", ""),
            ))

    # 去重
    seen = set()
    deduped_fuzzy = []
    for p in fuzzy:
        if p.project_id and p.project_id not in seen:
            seen.add(p.project_id)
            deduped_fuzzy.append(p)

    return ProjectRetrievalResult(exact=exact, fuzzy=deduped_fuzzy)


car_project_retrieval_service = CarProjectRetrievalService()
