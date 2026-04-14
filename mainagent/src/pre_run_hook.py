"""MainAgent 前置 Hook：agent 运行前从 orchestratorContext 解包配置到 deps。

一切由 workflow 控制：scenario / instruction / tools / skills / session_state。
没有 orchestrator context 时打 warning，降级为使用默认 AGENT.md。

Prompt 分层：
- 静态前缀（scene 决定，session 内不变）：
    SYSTEM.md + SOUL.md + {scene}/AGENT.md + orchestrated/AGENT.md + {scene}/OUTPUT.md
- 动态 context（最后一条 user message 末尾）：
    activity 级别的 instruction（业务方完全拥有，框架不解析）
"""

from __future__ import annotations

import logging
from typing import Any

from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)


class PreRunHook:
    """Agent 运行前准备 deps：从 orchestratorContext 解包场景配置。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        orch_ctx: Any = _extract_orchestrator_context(deps)

        if orch_ctx is None:
            logger.warning(
                "[PreRunHook] 无 orchestratorContext，走默认配置（user=%s, session=%s）",
                user_id, session_id,
            )
            return

        # 从 orchestratorContext 解包到 deps
        deps.current_scene = orch_ctx.scenario
        deps.available_tools = list(orch_ctx.available_tools)
        deps.allowed_skills = list(orch_ctx.available_skills) if orch_ctx.available_skills else []

        deps.workflow_id = orch_ctx.workflow_id
        deps.orchestrator_url = orch_ctx.orchestrator_url
        deps.scenario_label = orch_ctx.scenario_label or ""
        deps.instruction = orch_ctx.instruction or ""

        if orch_ctx.session_state:
            deps.session_state.update(orch_ctx.session_state)

        logger.info(
            "[PreRunHook] scene=%s, tools=%s, skills=%s, instruction_len=%d",
            orch_ctx.scenario,
            orch_ctx.available_tools,
            orch_ctx.available_skills,
            len(deps.instruction),
        )


def _extract_orchestrator_context(deps: AgentDeps) -> Any:
    """从 deps.request_context 提取 OrchestratorContext。"""
    rc: Any = deps.request_context
    if rc is None:
        return None

    # 已解析的 HlscRequestContext
    orch: Any = getattr(rc, "orchestrator", None)
    if orch is not None:
        return orch

    # dict 形式（HTTP 原始传入）
    if isinstance(rc, dict):
        orch_raw: dict | None = rc.get("orchestrator")
        if orch_raw is not None and isinstance(orch_raw, dict):
            from src.hlsc_context import OrchestratorContext
            try:
                return OrchestratorContext(**orch_raw)
            except Exception:
                logger.warning("[PreRunHook] 解析 OrchestratorContext 失败", exc_info=True)
                return None

    return None
