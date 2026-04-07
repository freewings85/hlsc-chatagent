"""call_query_codingagent 工具：通过 A2A 协议调用 QueryCodingAgent subagent。"""

from __future__ import annotations

import logging
import os
from typing import Final
from uuid import uuid4

logger: logging.Logger = logging.getLogger(__name__)

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("call_query_codingagent")

QUERY_CODINGAGENT_URL: str = os.getenv(
    "QUERY_CODINGAGENT_URL",
    os.getenv("CODE_AGENT_URL", "http://localhost:8102"),
)

def _build_query_prefix(scene: str) -> str:
    """根据场景构建 query prefix，指向对应的 API 文档目录。"""
    if not scene:
        raise ValueError("call_query_codingagent: scene 为空，无法确定 API 文档目录")
    return f"""API docs for this task are under the `/apis/{scene}/` directory, and the index is `/apis/{scene}/index.md`.
Read the index first, then read only the docs actually needed for this task.
Use the relevant APIs and Python code to try to solve the task below.
You may use only Python standard library, `httpx`, and `numpy`.
If you cannot complete the task, return only the clear reason.

# Task
"""

_RETRY_PREFIX = """Your previous reply was invalid because you printed pseudo tool-call text instead of using tools.
Do not print tool arguments, JSON wrappers, file-path JSON, or search-pattern JSON as normal text.
Read the needed docs, run Python if needed, and return only the actual result or the clear failure reason.

# Task
"""

_PSEUDO_TOOL_MARKERS: Final[tuple[str, ...]] = (
    "tool_uses",
    "recipient_name",
    "functions.read",
    "functions.grep",
    '{"file_path":',
    '{"pattern":',
)


def _looks_like_pseudo_tool_output(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _PSEUDO_TOOL_MARKERS)


def _extract_user_context(ctx: RunContext[AgentDeps]) -> str:
    """从 request_context 和 session_state 提取用户信息，供 coding agent 使用。"""
    parts: list[str] = []

    # 位置信息
    req_ctx = ctx.deps.request_context
    if req_ctx is not None:
        loc = req_ctx.get("current_location") if isinstance(req_ctx, dict) else getattr(req_ctx, "current_location", None)
        if loc is not None:
            if isinstance(loc, dict):
                lat, lng, addr = loc.get("lat"), loc.get("lng"), loc.get("address", "")
            else:
                lat, lng, addr = getattr(loc, "lat", None), getattr(loc, "lng", None), getattr(loc, "address", "")
            if lat is not None and lng is not None:
                parts.append(f"用户位置：latitude={lat}, longitude={lng}")
                if addr:
                    parts.append(f"地址：{addr}")

        # 车型信息
        car = req_ctx.get("current_car") if isinstance(req_ctx, dict) else getattr(req_ctx, "current_car", None)
        if car is not None:
            if isinstance(car, dict):
                car_id, car_name = car.get("car_model_id", ""), car.get("car_model_name", "")
            else:
                car_id, car_name = getattr(car, "car_model_id", ""), getattr(car, "car_model_name", "")
            if car_id or car_name:
                parts.append(f"用户车型：car_model_id={car_id}, car_model_name={car_name}")

    # session_state 补充（request_context 没有时）
    state: dict = ctx.deps.session_state or {}
    if not any("车型" in p for p in parts):
        car_models: list = state.get("carModels", [])
        if car_models:
            car: dict = car_models[0]
            parts.append(f"用户车型：car_model_id={car.get('id', '')}, car_model_name={car.get('name', '')}")

    if not any("位置" in p for p in parts):
        addresses: list = state.get("addresses", [])
        if addresses:
            parts.append(f"用户地址：{addresses[0].get('name', '')}")

    return "\n".join(parts)


async def call_query_codingagent(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """通过 A2A 调用 QueryCodingAgent，执行复杂计算查询。自动根据当前场景加载对应的 API 文档。"""
    scene: str = getattr(ctx.deps, "current_scene", "") or ""
    if not scene:
        logger.error("call_query_codingagent: current_scene 为空，无法确定 API 文档目录")
        return "Error: 当前场景未知，无法执行复杂查询"
    code_task_id: str = f"code-{ctx.deps.request_id[:8]}-{uuid4().hex[:8]}"
    context: dict[str, str] = {"code_task_id": code_task_id, "scene": scene}
    clean_query: str = query.strip()
    query_prefix: str = _build_query_prefix(scene)

    # 注入用户上下文（位置 + 车型，coding agent 调 API 时需要）
    user_context: str = _extract_user_context(ctx)
    if user_context:
        clean_query = f"{user_context}\n\n{clean_query}"

    wrapped_query: str = f"{query_prefix}{clean_query}"
    result = await call_subagent(
        ctx,
        url=QUERY_CODINGAGENT_URL,
        message=wrapped_query,
        context=context,
    )
    if not _looks_like_pseudo_tool_output(result):
        return result

    retry_query = f"{_RETRY_PREFIX}{clean_query}"
    retry_result = await call_subagent(
        ctx,
        url=QUERY_CODINGAGENT_URL,
        message=retry_query,
        context=context,
    )
    if _looks_like_pseudo_tool_output(retry_result):
        return "查询编码代理未能正确执行工具或代码，暂时无法完成本次查询。"
    return retry_result


call_query_codingagent.__doc__ = _DESCRIPTION
