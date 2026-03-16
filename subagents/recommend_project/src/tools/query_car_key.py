"""query_car_key 工具：根据 VIN 码或模糊车型描述查询 car_key。

调用 getCarModelsByQueryKey 接口，返回最匹配的车型 car_key，
供后续 recommend_projects 使用。
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end, log_http_request, log_http_response

_API_PATH: str = "/Auto/getCarModelsByQueryKey"


def _get_datamanager_url() -> str:
    """从环境变量获取 datamanager 服务地址（Nacos 会自动注入）。"""
    return os.getenv(
        "service.ai.datamanager.url",
        os.getenv("SERVICE_AI_DATAMANAGER_URL", "http://192.168.100.108:50400/service_ai_datamanager"),
    )


async def query_car_key(
    ctx: RunContext[AgentDeps],
    query_key: str,
) -> str:
    """根据 VIN 码或模糊车型描述查询车型编码（car_key）。

    当用户只提供了 VIN 码或模糊车型名称（如"宝马3系"、"大众polo"）而没有精确的 car_key 时，
    调用此工具获取最匹配的 car_key。

    Args:
        query_key: VIN 码或车型关键词，如 "LSVFA49J952001313" 或 "宝马 325Li"。

    Returns:
        最匹配的车型 car_key 和 car_name JSON。
    """
    sid, rid = ctx.deps.session_id, ctx.deps.request_id
    log_tool_start("query_car_key", sid, rid, {"query_key": query_key})

    try:
        url: str = _get_datamanager_url().rstrip("/") + _API_PATH
        payload: dict[str, Any] = {
            "queryKey": query_key,
            "limit": 1,
        }

        log_http_request(url, "POST", sid, rid, {"queryKey": query_key, "limit": 1})

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
                raise RuntimeError(f"查询车型编码接口调用失败: {exc}") from exc

        response_json: dict[str, Any] = resp.json()
        log_http_response(url, resp.status_code, sid, rid)

        status: int | None = response_json.get("status")
        if status != 0:
            message: str = response_json.get("message") or "未知错误"
            raise RuntimeError(f"查询车型编码失败: {message}")

        results: list[dict[str, Any]] = response_json.get("result") or []

        if not results:
            result = {"car_key": "", "car_name": "", "matched": False}
            log_tool_end("query_car_key", sid, rid, {"matched": False})
            return json.dumps(result, ensure_ascii=False)

        first: dict[str, Any] = results[0]
        car_key: str = first.get("car_key", "")
        car_name: str = first.get("car_name", "")

        result = {
            "car_key": car_key,
            "car_name": car_name,
            "matched": True,
        }

        log_tool_end("query_car_key", sid, rid, {"car_key": car_key, "matched": True})
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        log_tool_end("query_car_key", sid, rid, exc=e)
        return f"Error: query_car_key failed - {e}"
