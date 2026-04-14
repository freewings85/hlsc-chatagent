"""MainAgent 前置 Hook：agent 运行前从 orchestratorContext 解包配置到 deps。

一切由 workflow 控制：scenario / tools / skills / agent_md / session_state。
没有 orchestrator context 时打 warning，降级为使用默认 AGENT.md（不预设工具）。

Prompt 分层（cache 优化）：
- 静态前缀（所有 session 相同）：SYSTEM.md + SOUL.md + orchestrated/AGENT.md
- 动态内容（dynamic-context，最后一条 user message 末尾）：
  - 场景相关：{scene}/AGENT.md + {scene}/OUTPUT.md（从文件加载）
  - activity 相关：goal / checklist / tools / business_data
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_sdk._agent.deps import AgentDeps

logger: logging.Logger = logging.getLogger(__name__)

# 场景特定 prompt 文件目录
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "prompts" / "templates"


def _load_scene_prompt(scene: str) -> str:
    """加载 {scene}/AGENT.md + {scene}/OUTPUT.md 内容，拼接返回。"""
    parts: list[str] = []
    for filename in [f"{scene}/AGENT.md", f"{scene}/OUTPUT.md"]:
        path: Path = _TEMPLATES_DIR / filename
        if path.exists():
            content: str = path.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
    return "\n\n".join(parts)


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
                "[PreRunHook] 无 orchestratorContext，走默认 AGENT.md（user=%s, session=%s）",
                user_id, session_id,
            )
            return

        # 从 orchestratorContext 解包到 deps
        deps.current_scene = orch_ctx.scenario
        deps.available_tools = list(orch_ctx.available_tools)
        deps.allowed_skills = list(orch_ctx.available_skills) if orch_ctx.available_skills else []
        # 静态前缀用通用 AGENT.md（所有场景一样，cache 友好）
        deps.current_scene_agent_md = "orchestrated/AGENT.md"
        # 场景特定 prompt 放 dynamic-context（每个 scene 不同的业务说明）
        deps.scene_prompt = _load_scene_prompt(orch_ctx.scenario)

        deps.workflow_id = orch_ctx.workflow_id
        deps.orchestrator_url = orch_ctx.orchestrator_url
        deps.scenario_label = orch_ctx.scenario_label or ""

        current_step: Any = orch_ctx.current_step
        deps.current_step_detail = (
            current_step.model_dump() if hasattr(current_step, "model_dump") else dict(current_step)
        )
        deps.step_pending_fields = list(orch_ctx.step_pending_fields)
        deps.step_skeleton = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s)
            for s in orch_ctx.step_skeleton
        ]
        if orch_ctx.session_state:
            deps.session_state.update(orch_ctx.session_state)

        logger.info(
            "[PreRunHook] scene=%s, activity=%s, tools=%s, skills=%s",
            orch_ctx.scenario,
            current_step.id if hasattr(current_step, "id") else "?",
            orch_ctx.available_tools,
            orch_ctx.available_skills,
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
