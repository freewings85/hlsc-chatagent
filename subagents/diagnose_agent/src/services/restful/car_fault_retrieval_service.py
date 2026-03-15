"""故障现象检索服务

基于 RAG 语义检索故障现象数据。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from agent_sdk.logging import log_http_request, log_http_response

CAR_FAULT_RETRIEVAL_URL = os.getenv("CAR_FAULT_RETRIEVAL_URL", "")
CAR_FAULT_DATASET_IDS = os.getenv("CAR_FAULT_DATASET_IDS", "default")


@dataclass
class FaultItem:
    """故障现象条目"""

    title: str
    content: str
    primary_part_ids: List[int] = field(default_factory=list)
    primary_part_names: Optional[str] = None
    primary_project_ids: List[int] = field(default_factory=list)
    primary_project_names: Optional[str] = None


@dataclass
class FaultRetrievalResult:
    """故障现象检索结果"""

    total: int = 0
    items: List[FaultItem] = field(default_factory=list)


class CarFaultRetrievalService:
    """故障现象检索服务"""

    async def retrieval(
        self,
        query: str,
        session_id: str = "",
        request_id: str = "",
        primary_part_ids: list[int] | None = None,
        primary_project_ids: list[int] | None = None,
    ) -> FaultRetrievalResult:
        """检索故障现象（支持按车型零部件/项目过滤）。

        Raises:
            RuntimeError: URL 未配置或 API 返回错误
        """
        url = CAR_FAULT_RETRIEVAL_URL
        if not url:
            raise RuntimeError("CAR_FAULT_RETRIEVAL_URL 未配置")

        dataset_ids = [d.strip() for d in CAR_FAULT_DATASET_IDS.split(",") if d.strip()]
        payload: dict = {
            "dataset_ids": dataset_ids,
            "query": query,
            "top_k": 5,
            "similarity_threshold": 0.2,
            "vector_similarity_weight": 0.3,
        }
        if primary_part_ids:
            payload["primary_part_ids"] = primary_part_ids
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
                raise RuntimeError(f"故障检索失败: {error_msg}")


def _parse_result(raw: dict) -> FaultRetrievalResult:
    items = []
    for item in (raw.get("items") or []):
        items.append(FaultItem(
            title=item.get("title", ""),
            content=item.get("content", ""),
            primary_part_ids=item.get("primary_part_ids") or [],
            primary_part_names=item.get("primary_part_names") or None,
            primary_project_ids=item.get("primary_project_ids") or [],
            primary_project_names=item.get("primary_project_names") or None,
        ))
    return FaultRetrievalResult(total=raw.get("total", 0), items=items)


car_fault_retrieval_service = CarFaultRetrievalService()
