"""项目清单服务 — 根据车型获取全部项目 ID 列表。"""

from __future__ import annotations

import os
from typing import List

import httpx

from agent_sdk.logging import log_http_request, log_http_response

GET_PROJECT_BYCAR_URL = os.getenv("GET_PROJECT_BYCAR_URL", "")


async def get_project_ids_by_car(
    car_model_id: str, session_id: str = "", request_id: str = "",
) -> List[int]:
    """获取车型的全部项目 ID 列表。

    Raises:
        RuntimeError: URL 未配置或 API 返回错误
    """
    url = GET_PROJECT_BYCAR_URL
    if not url:
        raise RuntimeError("GET_PROJECT_BYCAR_URL 未配置")

    payload = {"carKey": car_model_id}
    log_http_request(url, "POST", session_id, request_id, payload)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"获取项目清单失败: {data.get('message', '未知错误')}")

        raw_tree = data.get("result", {}).get("projectTree", [])
        return _extract_project_ids(raw_tree)


def _extract_project_ids(nodes: list) -> List[int]:
    ids = []
    for node in (nodes or []):
        if node.get("dataType") == "project":
            ids.append(node.get("id", 0))
        ids.extend(_extract_project_ids(node.get("childList") or []))
    return ids
