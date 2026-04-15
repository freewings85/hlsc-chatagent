"""MainAgent 前置 Hook：agent 运行前准备 deps。

职责拆分：
- scene 级静态（同 scene 期间 cache 友好）：
    tools / skills / agent_md / system_prompt ← 来自 stage_config.yaml
- activity 级动态（tail，每轮变）：
    instruction ← 来自 orch_ctx（workflow 的 AICall）

scene 切换（guide → searchcoupons 等）会破一次 cache，频率低可接受。
activity 切换只改 instruction（走 dynamic-context 尾部），不破 cache。

AICall.available_tools / available_skills 字段保留（协议层）但**不再写入 deps**，
仅作为信息传递（业务如想提示"本步建议用 X"，在 instruction 文字里自行写明）。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_sdk._agent.deps import AgentDeps
from src.scene_config import registry

logger: logging.Logger = logging.getLogger(__name__)


class PreRunHook:
    """Agent 运行前准备 deps：scene 级配置来自 stage_config.yaml，动态 instruction 来自 AICall。"""

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

        # scene 级：静态，从 stage_config.yaml 拿（session 内同 scene 稳定，cache 友好）
        scene_cfg = registry.get_scene(orch_ctx.scenario)
        deps.current_scene = orch_ctx.scenario
        deps.available_tools = list(scene_cfg.tools)
        deps.allowed_skills = list(scene_cfg.skills) if scene_cfg.skills else []

        # activity 级：动态，每轮由 AICall 驱动（通过 dynamic-context tail 注入）
        deps.instruction = orch_ctx.instruction or ""

        # 其他 session 级元信息
        deps.workflow_id = orch_ctx.workflow_id
        deps.orchestrator_url = orch_ctx.orchestrator_url
        deps.scenario_label = orch_ctx.scenario_label or ""

        if orch_ctx.session_state:
            deps.session_state.update(orch_ctx.session_state)

        logger.info(
            "[PreRunHook] scene=%s, scene.tools=%s, scene.skills=%s, instruction_len=%d",
            orch_ctx.scenario,
            scene_cfg.tools,
            scene_cfg.skills,
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
