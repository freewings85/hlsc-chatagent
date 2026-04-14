"""话痨说车业务请求上下文 + Orchestrator 编排上下文。

HlscRequestContext 扩展 SDK 的 RequestContext，加入：
- current_car / current_location：请求级的车辆和位置信息
- orchestrator：Orchestrator 编排上下文（None = 降级模式）

OrchestratorContext 是 AICall 的载体：workflow 把 instruction + tools + skills 塞进来，
mainagent 侧 PreRunHook 解包到 deps，HlscContextFormatter 把 instruction 拼进 LLM 上下文。
框架不解析 instruction，业务在 activity 里完全拥有这段文本。
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
    """

    # ── 标识 ──
    workflow_id: str
    orchestrator_url: str

    scenario: str
    """当前业务场景标识（insurance / platform / searchshops / ...）"""

    scenario_label: str = ""
    """场景中文名（如"保险竞价"），日志/观测用"""

    # ── AICall 内容 ──
    instruction: str = ""
    """业务 activity 在 AICall 里组织好的指令文本（框架不解析）"""

    available_tools: list[str] = []
    """当前 activity 可用的工具名列表"""
    available_skills: list[str] = []
    """当前 activity 可用的 skill 名列表（空 = 不暴露 Skill 工具）"""

    # ── 业务状态 ──
    session_state: dict[str, Any] = {}
    """从 MySQL session_states 表 query 出的全量 KV"""


# ── 请求上下文 ───────────────────────────────────────────


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。

    降级模式下 orchestrator 为 None，和原来行为完全一样。
    编排模式下 orchestrator 非空，mainagent 据此注入 activity 指令 + 工具白名单。
    """

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
