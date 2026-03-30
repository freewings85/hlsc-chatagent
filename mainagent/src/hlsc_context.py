"""话痨说车业务请求上下文。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo

logger: logging.Logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.business_map_hook import SceneContext


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行，确保 LLM 始终能看到当前车辆、位置、业务地图切片和状态树。
    """

    def __init__(
        self,
        orchestrator: Any | None = None,
    ) -> None:
        self._orchestrator: Any | None = orchestrator

    def format(self, context: RequestContext) -> str:
        # 支持 dict（从 HTTP 请求直接传入）和 HlscRequestContext
        if isinstance(context, dict):
            try:
                context = HlscRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, HlscRequestContext):
            return ""

        parts: list[str] = []

        if context.current_car is not None:
            car: CarInfo = context.current_car
            parts.append(
                f"current_car(car_model_id={car.car_model_id}, "
                f"car_model_name={car.car_model_name}, "
                f"vin_code={car.vin_code})"
            )
        else:
            parts.append("current_car: (未设置)")

        if context.current_location is not None:
            loc: LocationInfo = context.current_location
            parts.append(
                f"current_location(address={loc.address}, "
                f"lat={loc.lat}, lng={loc.lng})"
            )
        else:
            parts.append("current_location: (未设置)")

        result: str = "[request_context]: " + ", ".join(parts)

        # 场景上下文注入
        if self._orchestrator is not None:
            sid: str = self._orchestrator.current_session_id
            scene_ctx: SceneContext | None = self._orchestrator.get_scene_context(sid)
            if scene_ctx is not None:
                result += "\n\n" + self._format_scene_context(scene_ctx)

        return result

    # ------------------------------------------------------------------
    # 场景上下文格式化（新版 SceneOrchestrator 使用）
    # ------------------------------------------------------------------

    def _format_scene_context(self, ctx: SceneContext) -> str:
        """将 SceneContext 格式化为注入 LLM 的文本块。"""
        parts: list[str] = []
        parts.append(f"[当前场景] {ctx.scene_name}")
        parts.append(f"[目标] {ctx.goal}")

        # 待办事项（target_slots 中还没有值的项）
        todo_lines: list[str] = []
        slot_name: str
        for slot_name in ctx.target_slots:
            slot_value: Any = ctx.slot_state.slots.get(slot_name)
            if slot_value is None:
                ts: Any = ctx.target_slots[slot_name]
                if isinstance(ts, dict):
                    label: str = ts.get("label", slot_name)
                    method: str = ts.get("method", "")
                else:
                    label = getattr(ts, "label", slot_name)
                    method = getattr(ts, "method", "")
                todo_lines.append(f"  - {label} — {method}")

        if todo_lines:
            parts.append("[待办事项]")
            parts.extend(todo_lines)

        # 已有信息（所有有值的 slot）
        filled_lines: list[str] = []
        for slot_name, slot_value in ctx.slot_state.slots.items():
            if slot_value is not None:
                filled_lines.append(f"  - {slot_name}: {slot_value}")

        if filled_lines:
            parts.append("[已有信息]")
            parts.extend(filled_lines)

        # 可用工具
        tools_text: str = ", ".join(ctx.tools) if ctx.tools else "(无)"
        parts.append(f"[可用工具] {tools_text}")

        # 可用 Skill（只展示当前场景允许的 skill）
        if ctx.allowed_skills:
            skills_text: str = ", ".join(ctx.allowed_skills)
            parts.append(f"[可用 Skill] {skills_text}")
        else:
            parts.append("[可用 Skill] (无)")

        return "\n".join(parts)
