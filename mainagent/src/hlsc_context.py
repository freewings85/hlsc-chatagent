"""话痨说车业务请求上下文 + Orchestrator 编排上下文。

HlscRequestContext 扩展 SDK 的 RequestContext，加入：
- scene：场景标识（必填，stage_config.yaml 的 scene 名，两种模式共用这一字段）
- current_car / current_location：请求级的车辆和位置信息
- orchestrator：Orchestrator 编排上下文（可选，orchestrator 模式才有）

**两种模式都必须传 scene 字段**：
- orchestrator 模式：调用方在顶层 request_context.scene 传 workflow 对应的 scene 名；
  额外带 orchestrator 子字段提供 workflow_id / instruction / session_state 等 activity 级信息
- 非 orchestrator 模式：直接调 mainagent（前端直连、运维、测试等），只传 scene 即可；
  instruction 为空，工具/skill 按 scene_config.yaml 静态配置

tools 和 skills 统一由 stage_config.yaml 按 scene 决定，两种模式一视同仁（cache 友好）。
OrchestratorContext 里 instruction 这段文字由业务在 activity 里完全拥有，框架不解析。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo

logger: logging.Logger = logging.getLogger(__name__)


# ── Orchestrator 编排上下文模型 ──────────────────────────


class OrchestratorContext(BaseModel):
    """Orchestrator 编排上下文（AICall 的载体）。

    Workflow → Activity → HTTP request_context.orchestrator → mainagent

    注意：**scene 不在这里**，统一由 HlscRequestContext.scene 承载（两种模式共用一个
    scene 字段）。本 context 只放 orchestrator 模式特有的 activity 级信息。
    """

    # ── 标识 ──
    workflow_id: str
    orchestrator_url: str

    scenario_label: str = ""
    """场景中文名（如"保险竞价"），日志/观测用。scene 本身在 HlscRequestContext.scene。"""

    # ── AICall 内容 ──
    instruction: str = ""
    """业务 activity 在 AICall 里组织好的指令文本（框架不解析）"""

    # ── 业务状态 ──
    session_state: dict[str, Any] = {}
    """从 MySQL session_states 表 query 出的全量 KV"""


# ── 请求上下文 ───────────────────────────────────────────


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。

    scene 为**必填**：无论是否有 orchestrator 字段，都要在顶层带上 scene。
    """

    scene: str | None = None
    """场景标识（stage_config.yaml 的 scene 名）。两种模式都必填。"""

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None
    orchestrator: OrchestratorContext | None = None


# ── 上下文格式化（注入 LLM 的文本）────────────────────────


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行。分两部分：
    1. 原有的 current_car + current_location 信息
    2. 如果有 orchestrator 编排上下文，直接把 instruction 拼进来
    """

    def format(self, context: RequestContext, deps: Any | None = None) -> str:
        # 支持 dict（从 HTTP 请求直接传入）和 HlscRequestContext
        if isinstance(context, dict):
            try:
                context = HlscRequestContext(**context)
            except Exception:
                return ""
        if not isinstance(context, HlscRequestContext):
            return ""

        parts: list[str] = []

        # ── Part 1：车辆 + 位置 ──
        parts.append(self._format_request_info(context))

        # ── Part 2：Orchestrator 编排上下文（activity instruction）──
        # 优先用 deps.instruction（update_workflow_state 热切换后是最新的），
        # 否则回落到 context.orchestrator.instruction。
        instruction: str = ""
        if deps is not None and getattr(deps, "instruction", ""):
            instruction = deps.instruction
        elif context.orchestrator is not None:
            instruction = context.orchestrator.instruction

        if instruction:
            parts.append(self._format_orchestrator(instruction))

        return "\n\n".join(p for p in parts if p)

    def _format_request_info(self, context: HlscRequestContext) -> str:
        """格式化车辆和位置信息。"""
        info_parts: list[str] = []
        if context.current_car is not None:
            car: CarInfo = context.current_car
            info_parts.append(
                f"current_car(car_model_id={car.car_model_id}, "
                f"car_model_name={car.car_model_name}, "
                f"vin_code={car.vin_code})"
            )
        else:
            info_parts.append("current_car: (未设置)")

        if context.current_location is not None:
            loc: LocationInfo = context.current_location
            info_parts.append(f"current_location(address={loc.address})")
        else:
            info_parts.append("current_location: (未设置)")

        return "### request_context\n\n" + ", ".join(info_parts)

    def _format_orchestrator(self, instruction: str) -> str:
        """把 activity 指令文本拼进 LLM 上下文。"""
        return f"### orchestrator\n\n{instruction}"
