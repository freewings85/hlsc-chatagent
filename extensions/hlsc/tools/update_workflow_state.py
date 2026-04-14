"""update_workflow_state 工具：把收集到的业务字段写入 Workflow 状态。

调用链路：
    LLM → update_workflow_state(fields)
    → Temporal execute_update("on_state_changed", StateChangeRequest)
    → Workflow: 写 MySQL → on_session_state_change（业务逻辑）
    → 返回 StateChangeResult：
        - tool_result_message + tool_result_data → 本轮 LLM 看到
        - next_activity_* → 下一轮 agent 的 deps 热切换
    → Tool 返回给 LLM：tool_result_message + tool_result_data
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

        # 同步刷新本地 session_state（给本轮后续工具调用看）
        for k, v in fields.items():
            if v is None:
                ctx.deps.session_state.pop(k, None)
            else:
                ctx.deps.session_state[k] = v
        if result.new_session_state:
            ctx.deps.session_state.update(result.new_session_state)

        # ── 热切换下一轮 agent 的 deps（如果 workflow 指定了新 AICall）──
        if result.next_activity_id:
            ctx.deps.available_tools = list(result.next_tools)
            ctx.deps.allowed_skills = list(result.next_skills)
            if result.next_skills and "Skill" not in ctx.deps.available_tools:
                ctx.deps.available_tools.append("Skill")
            ctx.deps.current_step_detail = {
                "id": result.next_activity_id,
                "name": result.next_activity_name or result.next_activity_id,
                "goal": result.next_activity_goal,
                "expected_fields": result.next_expected_fields,
            }
            ctx.deps.step_skeleton = list(result.new_activity_skeleton)
            ctx.deps.step_pending_fields = _calc_pending(
                result.next_expected_fields, ctx.deps.session_state,
            )
            # prompt 不需要工具手动覆盖：下一轮 mainagent 会基于新 deps 自动重渲

        # ── 构造给 LLM 的 tool result 文本 ──
        parts: list[str] = []
        if result.tool_result_message:
            parts.append(result.tool_result_message)
        else:
            parts.append("ok")
        if result.tool_result_data:
            parts.append(f"数据：{json.dumps(result.tool_result_data, ensure_ascii=False)}")
        if result.next_activity_goal:
            parts.append(f"接下来：{result.next_activity_goal}")

        log_tool_end("update_workflow_state", sid, rid, {
            "activity": result.current_activity,
            "next_activity": result.next_activity_id,
        })
        return "\n".join(parts)

    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        return f"error: update_workflow_state failed - {e}"


def _calc_pending(
    expected_fields: list[dict[str, str]], session_state: dict[str, Any],
) -> list[str]:
    required: set[str] = {f["name"] for f in expected_fields}
    return sorted(required - set(session_state.keys()))


update_workflow_state.__doc__ = _DESCRIPTION
