"""MainAgent 前置 Hook：BMA 每轮分类路由到 6 个平等场景。

路由逻辑：
- BMA 返回 [] → guide（引导，有查询工具，无 confirm_booking）
- BMA 返回 1 个场景 → 该场景
- BMA 返回多个场景 → orchestrator（delegate 协调子 agent）
- BMA 调用失败 → guide（容错）
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from agent_sdk._agent.deps import AgentDeps
from src.scene_config import SceneConfig, SceneConfigRegistry, registry


# ============================================================
# 对话历史提取（给 BMA 做分类用）
# ============================================================


async def _extract_recent_turns(deps: AgentDeps, max_turns: int = 5) -> list[dict[str, str]]:
    """通过 deps.memory_service 加载最近几轮对话，格式化为 BMA 需要的 recent_turns。

    返回 [{"role": "user"|"assistant", "content": "..."}]，最多 max_turns 轮。
    加载失败时返回空列表（不影响分类，BMA 会退化为只看当前消息）。
    """
    try:
        memory_service = getattr(deps, "memory_service", None)
        if memory_service is None:
            logger.debug("deps 上没有 memory_service，跳过 recent_turns 提取")
            return []

        user_id: str = deps.user_id if hasattr(deps, "user_id") else ""
        session_id: str = deps.session_id

        # 用 memory_service 加载历史消息
        agent_messages = await memory_service.load(user_id, session_id)

        turns: list[dict[str, str]] = []
        for msg in agent_messages:
            role: str = getattr(msg, "role", "")
            if role not in ("user", "assistant"):
                continue

            # AgentMessage 直接有 content 属性（UserMessage/AssistantMessage）
            content: str = str(getattr(msg, "content", "") or "").strip()

            # UserMessage 可能 content 为空但有 tool_results，提取工具结果摘要
            if not content and role == "user":
                tool_results = getattr(msg, "tool_results", [])
                if tool_results:
                    summaries: list[str] = [
                        f"[{tr.tool_name}: {tr.content[:80]}]"
                        for tr in tool_results
                        if hasattr(tr, "tool_name") and hasattr(tr, "content")
                    ]
                    content = " ".join(summaries)

            # AssistantMessage 可能 content 为空但有 tool_calls
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

        # 返回最近 max_turns 轮
        return turns[-max_turns * 2:]
    except Exception:
        logger.debug("提取 recent_turns 失败，BMA 将只使用当前消息", exc_info=True)
        return []

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# 场景配置（统一由 SceneConfigRegistry 管理）
# ============================================================

# 向后兼容：SceneConfig 和 SceneConfigRegistry 均从 scene_config 导入
# SceneConfigLoader 作为 SceneConfigRegistry 的别名保留，供已有测试使用
SceneConfigLoader = SceneConfigRegistry

# 模块级单例（复用 registry）
_config_loader: SceneConfigRegistry = registry


# ============================================================
# BMA 场景分类调用
# ============================================================


async def _call_bma_classify(message: str, recent_turns: list[dict[str, str]] | None = None) -> list[str]:
    """调用 BMA /classify 接口进行场景分类。

    Args:
        message: 当前用户消息
        recent_turns: 最近几轮对话 [{"role": "user"|"assistant", "content": "..."}]
    """
    url: str = os.getenv("BMA_CLASSIFY_URL", "")
    if not url:
        # 回退到旧环境变量
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
        logger.warning("BMA 场景分类调用失败，回退到 guide", exc_info=True)
        return []


# ============================================================
# Hook 实现
# ============================================================


class StageHook:
    """MainAgent 前置 Hook：BMA 分类 → 场景路由 → 加载配置。

    两种模式：
    - **编排模式**（request_context.orchestrator 非空）：
      scenario / available_tools 由 orchestrator 提供，跳过 BMA 调用，
      把 orchestrator 元数据解包到 deps 各字段供工具使用
    - **降级模式**（request_context.orchestrator 为 None）：
      走原有 BMA 分类 + 场景粘性 + SceneConfig 加载逻辑
    """

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: AgentDeps,
        message: str,
    ) -> None:
        _config_loader.ensure_loaded()

        # ── 编排模式：一切由 orchestratorContext 决定，不读 stage_config.yaml ──
        orch_ctx = _extract_orchestrator_context(deps)
        if orch_ctx is not None:
            # 场景 + 工具 + skills + agent_md 全部由 workflow 控制
            deps.current_scene = orch_ctx.scenario
            deps.available_tools = orch_ctx.available_tools
            deps.allowed_skills = orch_ctx.available_skills if orch_ctx.available_skills else []
            deps.current_scene_agent_md = "orchestrated/AGENT.md"

            # orchestrator 元数据 → deps
            deps.workflow_id = orch_ctx.workflow_id
            deps.orchestrator_url = orch_ctx.orchestrator_url
            deps.scenario_label = orch_ctx.scenario_label or ""
            deps.current_step_detail = orch_ctx.current_step.model_dump() if hasattr(orch_ctx.current_step, "model_dump") else dict(orch_ctx.current_step)
            deps.step_pending_fields = list(orch_ctx.step_pending_fields)
            deps.step_skeleton = [
                s.model_dump() if hasattr(s, "model_dump") else dict(s)
                for s in orch_ctx.step_skeleton
            ]
            if orch_ctx.session_state:
                deps.session_state.update(orch_ctx.session_state)

            logger.info(
                "编排模式: user=%s, scene=%s, tools=%s, skills=%s, step=%s",
                user_id, orch_ctx.scenario, orch_ctx.available_tools,
                orch_ctx.available_skills,
                orch_ctx.current_step.id if hasattr(orch_ctx.current_step, "id") else "?",
            )
            return

        # ── 降级模式：走原有 BMA 分类逻辑 ─────────────────────

        # 提取最近几轮对话历史给 BMA
        max_turns: int = int(os.getenv("CLASSIFY_RECENT_TURNS", "5"))
        recent_turns: list[dict[str, str]] = await _extract_recent_turns(deps, max_turns=max_turns)
        logger.info("BMA recent_turns 数量: %d, 内容: %s", len(recent_turns), recent_turns[:4] if recent_turns else "[]")

        # 调 BMA 分类
        scenes: list[str] = await _call_bma_classify(message, recent_turns=recent_turns)

        # 路由决策（含场景粘性：BMA 返回空时，如果上一轮有明确业务场景则保持）
        if len(scenes) == 1:
            scene = scenes[0]
        elif len(scenes) > 1:
            scene = "orchestrator"
        else:
            # BMA 无法判断 → 检查场景粘性（从 session_state 读取上一轮场景）
            prev_scene: str = deps.session_state.get("_current_scene", "guide")
            has_business_state: bool = bool(
                deps.session_state.get("projects")
                or deps.session_state.get("shops")
                or deps.session_state.get("coupons")
            )
            if prev_scene not in ("guide", "orchestrator") and has_business_state:
                scene = prev_scene
                logger.info("BMA 返回空但有业务状态，保持场景粘性: %s", scene)
            else:
                scene = "guide"

        # 加载场景配置
        config = _config_loader.get_scene(scene)

        # 设置 deps
        deps.current_scene = scene
        deps.available_tools = config.tools
        deps.allowed_skills = config.skills
        deps.current_scene_agent_md = config.agent_md if config.agent_md else None

        # 持久化当前场景到 session_state（供下一轮场景粘性判断）
        deps.session_state["_current_scene"] = scene

        logger.info(
            "场景决策: user=%s, scene=%s, agent_md=%s, tools=%d, skills=%s",
            user_id, scene, config.agent_md, len(config.tools), config.skills,
        )


def _extract_orchestrator_context(deps: AgentDeps) -> Any:
    """从 deps.request_context 提取 OrchestratorContext（有就返回，没有返回 None）。

    request_context 可能是 dict（HTTP 直传）或 HlscRequestContext（已解析）。
    """
    rc: Any = deps.request_context
    if rc is None:
        return None

    # 已解析的 HlscRequestContext
    orch: Any = getattr(rc, "orchestrator", None)
    if orch is not None:
        return orch

    # dict 形式（HTTP 原始传入，未经 HlscRequestContext 解析）
    if isinstance(rc, dict):
        orch_raw: dict | None = rc.get("orchestrator")
        if orch_raw is not None and isinstance(orch_raw, dict):
            from src.hlsc_context import OrchestratorContext
            try:
                return OrchestratorContext(**orch_raw)
            except Exception:
                logger.warning("解析 OrchestratorContext 失败", exc_info=True)
                return None

    return None
