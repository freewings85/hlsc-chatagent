"""Extensions 测试共享 fixtures。

创建自包含的测试 Agent，不依赖 mainagent 的生产代码。
- 真实 LLM（Azure）判断意图
- 真实 extension tools（skill 判断 + interrupt 流程）
- Mock service 层（不调真实 REST API）
- Mock 业务 tool（如 get_car_price，生产环境不存在）
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAINAGENT_DIR = PROJECT_ROOT / "mainagent"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
EXTENSIONS_DIR = PROJECT_ROOT / "extensions"

# ── Mock Tools（测试专用，生产环境不存在）──


async def mock_get_car_price(
    ctx: Any,
    car_model_id: Annotated[str, Field(description="车型 ID")],
    lat: Annotated[float, Field(description="纬度")],
    lng: Annotated[float, Field(description="经度")],
) -> str:
    """查询指定车型在指定位置附近的养车价格。

    需要 car_model_id 和 lat/lng 参数。
    如果 request_context 中有这些信息且用户没指定新的，直接使用。
    否则参考 confirm-car-info / confirm-location skill 获取。
    """
    from agent_sdk.logging import log_tool_start, log_tool_end
    sid = getattr(ctx.deps, "session_id", "?")
    rid = getattr(ctx.deps, "request_id", "?")
    log_tool_start("get_car_price", sid, rid, {"car_model_id": car_model_id, "lat": lat, "lng": lng})

    result = (
        f"车型 {car_model_id}（lat={lat}, lng={lng}）附近养车价格：\n"
        f"- 普洗：¥35\n"
        f"- 精洗：¥120\n"
        f"- 小保养：¥580\n"
        f"- 大保养：¥1200"
    )
    log_tool_end("get_car_price", sid, rid, {"car_model_id": car_model_id})
    return result


def _no_proxy_client(**kwargs: Any) -> httpx.Client:
    transport = httpx.HTTPTransport()
    return httpx.Client(transport=transport, **kwargs)


def _wait_for_health(url: str, timeout_secs: int = 90) -> bool:
    for _ in range(timeout_secs):
        try:
            with _no_proxy_client(timeout=2) as client:
                r = client.get(f"{url}/health")
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False
