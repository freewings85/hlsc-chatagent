"""场景分类端点：/classify

由 orchestrator 调用，替代 orchestrator 直接调 BMA。
优势：mainagent 自带对话历史（memory_service），BMA 可以拿到 recent_turns，
不需要 orchestrator 侧维护一套 user_message_history 表。

请求：POST /classify
  { "user_id": "u123", "session_id": "s456", "message": "搞错了换一辆" }

响应：
  { "scenario": "insurance" }     — 分类成功
  { "scenario": null }            — BMA 返回空 / 调用失败

内部流程：
1. 用 memory_service 加载 session 的对话历史
2. 提取 recent_turns
3. 调 BMA /classify（和 StageHook 走同一条路径）
4. 返回主场景（单场景取唯一，多场景取优先级最高）
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)

# 初版固定的场景优先级（和 orchestrator 侧 bma_client 一致）
_SCENARIO_PRIORITY: list[str] = ["insurance", "platform", "searchcoupons", "searchshops"]


async def _extract_recent_turns(deps: AgentDeps, max_turns: int = 5) -> list[dict[str, str]]:
    """从 deps.memory_service 加载最近几轮对话，格式化为 BMA 需要的 recent_turns。"""
    try:
        memory_service = getattr(deps, "memory_service", None)
        if memory_service is None:
            return []

        user_id: str = deps.user_id if hasattr(deps, "user_id") else ""
        session_id: str = deps.session_id
        agent_messages = await memory_service.load(user_id, session_id)

        turns: list[dict[str, str]] = []
        for msg in agent_messages:
            role: str = getattr(msg, "role", "")
            if role not in ("user", "assistant"):
                continue
            content: str = str(getattr(msg, "content", "") or "").strip()

            if not content and role == "user":
                tool_results = getattr(msg, "tool_results", [])
                if tool_results:
                    summaries: list[str] = [
                        f"[{tr.tool_name}: {tr.content[:80]}]"
                        for tr in tool_results
                        if hasattr(tr, "tool_name") and hasattr(tr, "content")
                    ]
                    content = " ".join(summaries)

            if not content and role == "assistant":
                tool_calls = getattr(msg, "tool_calls", [])
                if tool_calls:
                    call_names: list[str] = [
                        tc.tool_name for tc in tool_calls
                        if hasattr(tc, "tool_name")
                    ]
                    content = f"[调用工具: {', '.join(call_names)}]"

            if content:
                turns.append({"role": role, "content": content})

        return turns[-max_turns * 2:]
    except Exception:
        logger.debug("提取 recent_turns 失败", exc_info=True)
        return []


async def _call_bma_classify(
    message: str, recent_turns: list[dict[str, str]] | None = None,
) -> list[str]:
    """调 BMA /classify 接口。"""
    url: str = os.getenv("BMA_CLASSIFY_URL", "")
    if not url:
        from src.config import BUSINESS_MAP_AGENT_URL
        url = f"{BUSINESS_MAP_AGENT_URL.rstrip('/')}/classify"

    payload: dict[str, Any] = {"message": message}
    if recent_turns:
        payload["recent_turns"] = recent_turns

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp: httpx.Response = await client.post(url, json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            scenes: list[str] = data.get("scenes", [])
            logger.info("BMA 场景分类: %s → %s", message[:50], scenes)
            return scenes
    except Exception:
        logger.warning("BMA 分类调用失败", exc_info=True)
        return []


class ClassifyRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ClassifyResponse(BaseModel):
    scenario: str | None = None


async def classify_scenario(
    user_id: str,
    session_id: str,
    message: str,
    memory_service_factory: Any,
) -> str | None:
    """核心分类逻辑（可复用，不依赖 HTTP 层）。

    Args:
        memory_service_factory: 能构建 MemoryMessageService 的工厂
            （从 AgentApp 注入，避免 classify 模块直接耦合 SDK 内部）
    """
    # 构建一个轻量 deps 只为了提取 recent_turns（memory_service 需要 deps）
    deps: AgentDeps = AgentDeps(
        user_id=user_id,
        session_id=session_id,
    )

    # 挂 memory_service
    if memory_service_factory is not None:
        deps.memory_service = memory_service_factory()

    recent_turns: list[dict[str, str]] = await _extract_recent_turns(deps, max_turns=5)
    logger.info(
        "[CLASSIFY] user=%s session=%s recent_turns=%d",
        user_id, session_id, len(recent_turns),
    )

    scenes: list[str] = await _call_bma_classify(message, recent_turns=recent_turns)

    if not scenes:
        return None
    if len(scenes) == 1:
        return scenes[0]

    # 多场景：按优先级取
    for prio in _SCENARIO_PRIORITY:
        if prio in scenes:
            return prio
    return scenes[0]
