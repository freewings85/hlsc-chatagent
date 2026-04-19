"""规划核心逻辑：/plan 端点的实际干活的地方。

和 classify.py 同构：纯函数，不依赖 HTTP 层；通过 memory_service_factory
参数拿 mainagent 的 session transcript，把历史塞进 LLM 的 user 消息里。

LLM 走 **pydantic-ai 原生 structured output**（`output_type=Plan`），
校验失败由 pydantic-ai 自动 retry（初版 retries=2），不用服务端手搓 JSON 校验。
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from pydantic_ai import Agent as PydanticAgent

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.model import create_model

from src.dsl_models import ActionDef, Plan
from src.plan_loader import build_plan_system_prompt

logger: logging.Logger = logging.getLogger(__name__)


_PLAN_RETRIES: int = int(os.getenv("PLAN_LLM_RETRIES", "2"))
_PLAN_HISTORY_MAX_TURNS: int = int(os.getenv("PLAN_HISTORY_MAX_TURNS", "20"))


async def _extract_recent_turns(
    deps: AgentDeps,
    max_turns: int,
) -> list[dict[str, str]]:
    """从 deps.memory_service 拉历史，压成 [{role, content}] 列表。

    逻辑和 classify.py 的 _extract_recent_turns 对齐，避免两套代码各走各的。
    """
    try:
        memory_service: Any = getattr(deps, "memory_service", None)
        if memory_service is None:
            return []

        user_id: str = deps.user_id if hasattr(deps, "user_id") else ""
        session_id: str = deps.session_id
        agent_messages: Any = await memory_service.load(user_id, session_id)

        turns: list[dict[str, str]] = []
        for msg in agent_messages:
            role: str = getattr(msg, "role", "")
            if role not in ("user", "assistant"):
                continue
            content: str = str(getattr(msg, "content", "") or "").strip()

            if not content and role == "user":
                tool_results: Any = getattr(msg, "tool_results", [])
                if tool_results:
                    summaries: list[str] = [
                        f"[{tr.tool_name}: {tr.content[:80]}]"
                        for tr in tool_results
                        if hasattr(tr, "tool_name") and hasattr(tr, "content")
                    ]
                    content = " ".join(summaries)

            if not content and role == "assistant":
                tool_calls: Any = getattr(msg, "tool_calls", [])
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
        logger.debug("提取 plan recent_turns 失败", exc_info=True)
        return []


def _render_user_message(message: str, history: list[dict[str, str]]) -> str:
    """把当前 query + 历史拼成 LLM 的 user 消息。

    走「历史嵌 user 文本」而非 pydantic-ai 的 message_history 参数：
    - planagent 是一次性调用，不是续接对话
    - 历史里的 assistant 回复是自然语言 chat 文本，不是 Plan JSON，
      当成 ModelMessage 喂回去语义上不对
    """
    if not history:
        return f"当前用户 query：\n{message}"

    history_lines: list[str] = []
    for turn in history:
        role: str = turn.get("role", "")
        content: str = turn.get("content", "")
        tag: str = "用户" if role == "user" else "助手"
        history_lines.append(f"- {tag}：{content}")

    return (
        "近期对话（旧→新）：\n"
        + "\n".join(history_lines)
        + f"\n\n当前用户 query（就本轮规划而言，语义要以这条为准）：\n{message}"
    )


async def generate_plan(
    user_id: str,
    session_id: str,
    message: str,
    scenes: list[str],
    available_actions: list[ActionDef],
    memory_service_factory: Any,
) -> Plan:
    """生成一个 Plan。

    Args:
        user_id / session_id: mainagent session 标识，用于查 memory service 拿历史
        message: 本轮用户原始 query
        scenes: BMA 返回的场景列表；长度 1 为单场景，>=2 为复合场景
        available_actions: orchestrator 传入的 action 白名单（复合场景时已 union）
        memory_service_factory: mainagent app.py 注入的 memory_service 工厂

    Returns:
        Plan —— pydantic-ai 校验过的结构化对象
    """
    # 1. 从 memory service 拉历史
    deps: AgentDeps = AgentDeps(user_id=user_id, session_id=session_id)
    if memory_service_factory is not None:
        deps.memory_service = memory_service_factory()
    history: list[dict[str, str]] = await _extract_recent_turns(deps, _PLAN_HISTORY_MAX_TURNS)

    # 2. 拼 prompts
    system_prompt: str = build_plan_system_prompt(scenes, available_actions)
    user_msg: str = _render_user_message(message, history)

    # 3. 跑 pydantic-ai（output_type=Plan，校验失败自动 retry）
    plan_agent: PydanticAgent = PydanticAgent(
        create_model(),
        output_type=Plan,
        system_prompt=system_prompt,
        retries=_PLAN_RETRIES,
    )

    logger.info(
        "[PLAN] user=%s session=%s scenes=%s history=%d actions=%d",
        user_id, session_id, scenes, len(history), len(available_actions),
    )

    result: Any = await plan_agent.run(user_msg)
    plan: Plan = result.output

    # plan_id 兜底：如果 LLM 忘了给，这里补一个
    if not plan.plan_id:
        plan.plan_id = f"p-{uuid.uuid4().hex[:8]}"
    return plan
