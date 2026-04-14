"""话痨说车业务请求上下文 + Orchestrator 编排上下文。

HlscRequestContext 扩展 SDK 的 RequestContext，加入：
- current_car / current_location：请求级的车辆和位置信息
- orchestrator：Orchestrator 编排上下文（None = 降级模式）

OrchestratorContext 包含 workflow 骨架状态、当前 step 详情、会话状态等，
由 orchestrator 的 Activity 在调 mainagent 时填充到 request_context.orchestrator。
mainagent 侧据此注入 step 引导 prompt 并让 update_session_state 工具走编排分支。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from agent_sdk._common.request_context import ContextFormatter, RequestContext
from hlsc.models import CarInfo, LocationInfo

logger: logging.Logger = logging.getLogger(__name__)


# ── Orchestrator 编排上下文模型 ──────────────────────────


class StepFieldSpec(BaseModel):
    """expected_fields 条目"""

    name: str
    type: str
    label: str = ""
    """中文显示名，如"车架号 VIN"。空则 Checklist 中只显示 name"""


class StepBrief(BaseModel):
    """全局骨架中的 step 条目（轻量）"""

    id: str
    name: str
    goal_short: str
    status: str  # "done" / "current" / "pending"


class CurrentStepDetail(BaseModel):
    """当前 step 的详细信息"""

    id: str
    name: str
    goal: str
    expected_fields: list[StepFieldSpec]
    success_criteria: str = ""
    skip_hint: str | None = None
    repeatable: bool = False


class OrchestratorContext(BaseModel):
    """Orchestrator 编排上下文。

    仅在 orchestrator 编排模式下非空。降级模式（ChatManager 直连 mainagent）时为 None。
    mainagent 根据此字段是否存在决定走编排路径还是自驱路径。

    传输路径：Orchestrator Activity → HTTP request_context.orchestrator → mainagent
    """

    # ── 标识 ──
    workflow_id: str
    """update_session_state 工具回调 /internal/advance_step 时的 opaque token"""

    orchestrator_url: str
    """/internal/advance_step 和 /internal/revert_step 的 base URL"""

    scenario: str
    """当前业务场景标识（insurance / platform / searchshops / ...）"""

    scenario_label: str = ""
    """场景中文名（如"保险竞价"），Checklist 进度条显示用"""

    # 注意：callback_url 不在这里。它是 HTTP 层通信机制，放在 AsyncChatRequest 顶层。

    # ── Workflow 骨架状态 ──
    step_skeleton: list[StepBrief]
    """全局 step 列表 + 各自的 done/current/pending 状态"""

    current_step: CurrentStepDetail
    """当前聚焦 step 的完整细节"""

    completed_steps: list[str]
    """已完成的 step id 列表"""

    # ── 业务状态 ──
    session_state: dict[str, Any]
    """从 MySQL session_states 表 query 出的全量 KV"""

    step_pending_fields: list[str]
    """当前 step 的 expected_fields 中还没收集的字段名（派生数据）"""

    # ── 工具 & Skill 白名单 ──
    available_tools: list[str]
    """当前 step 可用的工具名列表"""
    available_skills: list[str] = []
    """当前 step 可用的 skill 名列表（空 = 不暴露 Skill 工具）"""


# ── 请求上下文 ───────────────────────────────────────────


class HlscRequestContext(RequestContext):
    """话痨说车请求上下文。

    降级模式下 orchestrator 为 None，和原来行为完全一样。
    编排模式下 orchestrator 非空，mainagent 据此注入 step prompt + 工具路由。
    """

    current_car: CarInfo | None = None
    current_location: LocationInfo | None = None
    orchestrator: OrchestratorContext | None = None


# ── 上下文格式化（注入 LLM 的文本）────────────────────────


class HlscContextFormatter(ContextFormatter):
    """将 HlscRequestContext 格式化为注入 LLM 的文本。

    每次 LLM 调用前执行。分两部分：
    1. 原有的 current_car + current_location 信息
    2. 如果有 orchestrator 编排上下文，渲染 step_skeleton + step_detail + pending_fields
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

        # ── Part 1：场景特定 prompt（从 {scene}/AGENT.md + {scene}/OUTPUT.md 加载）──
        # 放最前面，让 LLM 先看到业务上下文
        scene_prompt: str = getattr(deps, "scene_prompt", "") if deps is not None else ""
        if scene_prompt:
            parts.append(scene_prompt)

        # ── Part 2：车辆 + 位置 ──
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

        parts.append("### request_context\n\n" + ", ".join(info_parts))

        # ── Part 3：Orchestrator 编排上下文（activity 级别的动态数据）──
        if context.orchestrator is not None:
            from agent_sdk._agent.orchestrator_prompt import render_orchestrator_prompt

            orch: OrchestratorContext = context.orchestrator
            orch_text: str = render_orchestrator_prompt(
                step_skeleton=[s.model_dump() for s in orch.step_skeleton],
                current_step=orch.current_step.model_dump(),
                session_state=orch.session_state,
                step_pending_fields=orch.step_pending_fields,
                scenario_label=orch.scenario_label,
            )
            parts.append(orch_text)

        return "\n\n".join(parts)
