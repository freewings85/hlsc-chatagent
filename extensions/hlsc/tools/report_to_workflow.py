"""report_to_workflow 工具：把用户给出的业务字段上报给 workflow（记账）。

调用链路：
    LLM → report_to_workflow(fields)
    → Temporal execute_update("on_state_changed", StateChangeRequest)
    → Workflow: 写 MySQL → on_session_state_change（业务逻辑）
    → 返回 StateChangeResult：
        - tool_result_message  → 本轮 LLM 看到的 tool result 文本
        - next_instruction     → 下一轮 agent 的 instruction 热切换（tail dynamic-context）
    → Tool 返回给 LLM：tool_result_message
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("report_to_workflow")

# Agent 等 workflow update 返回的墙钟超时（秒）
# Temporal 的 rpc_timeout 只管单次 poll，execute_update 会一直循环 poll 直到 handler 返回。
# 这个墙钟上限防止 tool 阻塞 agent 太久。调试时可以调大。
_CALL_WORKFLOW_TIMEOUT: float = float(os.getenv("CALL_WORKFLOW_TIMEOUT", "120"))


async def report_to_workflow(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"xxxxxx\", \"register_date\": \"xxxxx\"}"
    )],
) -> str:
    """把收集到的信息写入流程状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("report_to_workflow", sid, rid, {"fields": list(fields.keys())})

    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end("report_to_workflow", sid, rid, exc=RuntimeError("not in orchestrator mode"))
        return "error: 当前不在编排模式下，无法更新 workflow 状态"

    try:
        from orchestrator_protocol import StateChangeRequest, StateChangeResult

        handle = temporal_client.get_workflow_handle(workflow_id)
        try:
            async with asyncio.timeout(_CALL_WORKFLOW_TIMEOUT):
                result: StateChangeResult = await handle.execute_update(
                    "on_state_changed",
                    StateChangeRequest(
                        user_id=ctx.deps.user_id,
                        session_id=ctx.deps.session_id,
                        fields=fields,
                    ),
                    result_type=StateChangeResult,
                )
        except asyncio.TimeoutError:
            log_tool_end("report_to_workflow", sid, rid, exc=TimeoutError(f">{_CALL_WORKFLOW_TIMEOUT}s"))
            return (
                f"error: workflow update 超时（>{_CALL_WORKFLOW_TIMEOUT}s）。"
                f"请告知用户系统繁忙，稍后再试。"
            )

        # 同步刷新本地 session_state（给本轮后续工具调用看）
        for k, v in fields.items():
            if v is None:
                ctx.deps.session_state.pop(k, None)
            else:
                ctx.deps.session_state[k] = v
        if result.new_session_state:
            ctx.deps.session_state.update(result.new_session_state)

        # ── 热切换下一轮 agent 的 instruction（tail dynamic-context，每轮变）──
        # 注意：不再 mutate available_tools / allowed_skills（cache 稳定考虑，
        # 工具集由 stage_config.yaml 的 scene 级配置在 PreRunHook 里定死）。
        # AICall.next_tools / next_skills 降级为软提醒——业务如需引导 LLM，
        # 在 result.next_instruction 文字里写明即可。
        if result.next_instruction:
            ctx.deps.instruction = result.next_instruction

        log_tool_end("report_to_workflow", sid, rid, {
            "activity": result.current_activity,
            "has_next_instruction": bool(result.next_instruction),
        })
        return result.tool_result_message

    except Exception as e:
        log_tool_end("report_to_workflow", sid, rid, exc=e)
        return f"error: report_to_workflow failed - {e}"


report_to_workflow.__doc__ = _DESCRIPTION
