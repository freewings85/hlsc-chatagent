"""update_workflow_state 工具：把收集到的业务字段写入 Workflow 状态。

调用链路：
    Agent LLM 调用此工具
    → tool 从 deps 取 temporal_client + workflow_id
    → handle.execute_update("on_state_changed", StateChangeRequest(fields={...}))
    → Workflow 内部：写 MySQL → 调业务 transition → 可能切换 activity
    → 返回 StateChangeResult
    → tool 如果切换了且有新 AICall → 热切换 context
    → tool 把结果返回给 LLM
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("update_workflow_state")


async def update_workflow_state(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"xxxxxx\", \"register_date\": \"xxxxx\"}"
    )],
) -> str:
    """把收集到的信息写入流程状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_workflow_state", sid, rid, {"fields": list(fields.keys())})

    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end("update_workflow_state", sid, rid, exc=RuntimeError("not in orchestrator mode"))
        return "error: 当前不在编排模式下，无法更新 workflow 状态"

    try:
        from orchestrator_protocol import StateChangeRequest, StateChangeResult

        handle = temporal_client.get_workflow_handle(workflow_id)
        result: StateChangeResult = await handle.execute_update(
            "on_state_changed",
            StateChangeRequest(
                user_id=ctx.deps.user_id,
                session_id=ctx.deps.session_id,
                fields=fields,
            ),
            result_type=StateChangeResult,
            rpc_timeout=timedelta(seconds=60),
        )

        # 同步刷新本地 session_state
        for k, v in fields.items():
            if v is None:
                ctx.deps.session_state.pop(k, None)
            else:
                ctx.deps.session_state[k] = v

        # 合并 workflow 返回的最新 session_state
        if result.new_session_state:
            ctx.deps.session_state.update(result.new_session_state)

        if not result.advanced:
            # 没切换 activity，返回确认
            log_tool_end("update_workflow_state", sid, rid, {
                "activity": result.current_step, "advanced": False,
            })
            return "ok. 已写入"

        # ── activity 切换了 ──

        # 热切换 tools / skills / prompt（如果新 activity 返回了 AICall）
        if result.new_available_tools:
            ctx.deps.available_tools = list(result.new_available_tools)
        if result.new_available_skills:
            new_skills: list[str] = list(result.new_available_skills)
            ctx.deps.allowed_skills = new_skills
            if new_skills and "Skill" not in ctx.deps.available_tools:
                ctx.deps.available_tools.append("Skill")

        if result.new_step_detail:
            ctx.deps.current_step_detail = result.new_step_detail
            ctx.deps.step_skeleton = result.new_step_skeleton or None
            ctx.deps.step_pending_fields = _calc_pending(
                result.new_step_detail, ctx.deps.session_state,
            )
            _update_prompt(ctx.deps, result)

        # 构造返回给 LLM 的文本
        summary: str = "ok. 已写入"
        if result.business_result:
            summary += f"\n业务数据：{json.dumps(result.business_result, ensure_ascii=False)}"
        new_goal: str = (result.new_step_detail or {}).get("goal", "")
        if new_goal:
            summary += f"\n接下来：{new_goal}"

        log_tool_end("update_workflow_state", sid, rid, {
            "activity": result.current_step, "advanced": True,
        })
        return summary

    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        return f"error: update_workflow_state failed - {e}"


def _calc_pending(step_detail: dict[str, Any], session_state: dict[str, Any]) -> list[str]:
    expected: list[dict[str, str]] = step_detail.get("expected_fields", [])
    required: set[str] = {f["name"] for f in expected}
    return sorted(required - set(session_state.keys()))


def _update_prompt(deps: AgentDeps, result: Any) -> None:
    """热切换 orchestrator prompt。"""
    try:
        from agent_sdk._agent.orchestrator_prompt import render_orchestrator_prompt
        deps.system_prompt_override = render_orchestrator_prompt(
            step_skeleton=result.new_step_skeleton or [],
            current_step=result.new_step_detail or {},
            session_state=deps.session_state,
            step_pending_fields=deps.step_pending_fields or [],
            scenario_label=getattr(deps, "scenario_label", ""),
        )
    except Exception:
        pass


update_workflow_state.__doc__ = _DESCRIPTION
