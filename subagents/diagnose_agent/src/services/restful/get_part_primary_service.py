"""零部件清单服务 — 根据车型获取主要零部件 ID 列表。"""

from __future__ import annotations

import os
from typing import List

import httpx

from agent_sdk.logging import log_http_request, log_http_response

GET_PART_PRIMARY_URL = os.getenv("GET_PART_PRIMARY_URL", "")


async def get_main_part_ids(
    car_model_id: str, session_id: str = "", request_id: str = "",
) -> List[int]:
    """获取车型的主要零部件 ID 列表（big=True）。

    Raises:
        RuntimeError: URL 未配置或 API 返回错误
    """
    url = GET_PART_PRIMARY_URL
    if not url:
        raise RuntimeError("GET_PART_PRIMARY_URL 未配置")

    payload = {"carKey": car_model_id}
    log_http_request(url, "POST", session_id, request_id, payload)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"获取零部件清单失败: {data.get('message', '未知错误')}")

        # 递归提取 big=True 的零部件 ID
        raw_list = data.get("result", {}).get("list", [])
        return _extract_big_ids(raw_list)


def _extract_big_ids(nodes: list) -> List[int]:
    ids = []
    for node in (nodes or []):
        if node.get("big"):
            ids.append(node.get("partCategoryId", 0))
        ids.extend(_extract_big_ids(node.get("childList") or []))
    return ids
