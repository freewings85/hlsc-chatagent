"""MainAgent 前置 Hook：agent 运行前准备 deps。

两种请求来源：
- orchestrator 模式：request_context 里带 orchestrator 子字段，提供 workflow_id /
  instruction / session_state 等 activity 级动态信息
- 非 orchestrator 模式：直接调 mainagent（测试、直连前端等），只传 request_context.scene

**scene 字段必填**（两种模式都在顶层 request_context.scene），PreRunHook 按这个
scene 从 stage_config.yaml 加载 tools / skills（session 内同 scene 稳定，cache 友好）。

activity 级动态只有 instruction（orchestrator 模式才有），走 dynamic-context 尾部注入。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_sdk._agent.deps import AgentDeps
from src.hlsc_context import OrchestratorContext
from src.scene_config import registry

logger: logging.Logger = logging.getLogger(__name__)


class PreRunHook:
    """Agent 运行前准备 deps：按 scene 从 stage_config.yaml 加载配置，按 orchestrator 解包动态 instruction。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        scene: str | None = _extract_scene(deps)
        if not scene:
            raise RuntimeError(
                f"PreRunHook: 请求上下文里没有 scene 字段，无法确定场景"
                f"（user={user_id}, session={session_id}）"
            )

        # scene 级：从 stage_config.yaml 静态加载（cache 友好）
        scene_cfg = registry.get_scene(scene)
        deps.current_scene = scene
        deps.available_tools = list(scene_cfg.tools)
        deps.allowed_skills = list(scene_cfg.skills) if scene_cfg.skills else []

        # orchestrator 模式特有字段：activity 级动态 instruction、workflow 标识、session_state
        orch_ctx: OrchestratorContext | None = _extract_orchestrator_context(deps)
        if orch_ctx is not None:
            deps.instruction = orch_ctx.instruction or ""
            deps.workflow_id = orch_ctx.workflow_id
            deps.orchestrator_url = orch_ctx.orchestrator_url
            deps.scenario_label = orch_ctx.scenario_label or ""
            if orch_ctx.session_state:
                deps.session_state.update(orch_ctx.session_state)
            logger.info(
                "[PreRunHook] mode=orchestrator scene=%s tools=%s skills=%s instruction_len=%d",
                scene, scene_cfg.tools, scene_cfg.skills, len(deps.instruction),
            )
        else:
            logger.info(
                "[PreRunHook] mode=direct scene=%s tools=%s skills=%s",
                scene, scene_cfg.tools, scene_cfg.skills,
            )


def _extract_scene(deps: AgentDeps) -> str | None:
    """从 request_context 顶层拿 scene 字段。"""
    rc: Any = deps.request_context
    if rc is None:
        return None
    scene: Any = getattr(rc, "scene", None)
    if isinstance(scene, str) and scene:
        return scene
    if isinstance(rc, dict):
        raw: Any = rc.get("scene")
        if isinstance(raw, str) and raw:
            return raw
    return None


def _extract_orchestrator_context(deps: AgentDeps) -> OrchestratorContext | None:
    """从 deps.request_context 提取 OrchestratorContext（orchestrator 模式用）。"""
    rc: Any = deps.request_context
    if rc is None:
        return None

    orch: Any = getattr(rc, "orchestrator", None)
    if orch is not None:
        return orch

    if isinstance(rc, dict):
        orch_raw: dict | None = rc.get("orchestrator")
        if orch_raw is not None and isinstance(orch_raw, dict):
            try:
                return OrchestratorContext(**orch_raw)
            except Exception:
                logger.warning("[PreRunHook] 解析 OrchestratorContext 失败", exc_info=True)
                return None

    return None
