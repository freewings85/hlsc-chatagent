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
        return (
            "FATAL: 后端工作流连接不可用（系统配置问题，不是调用参数问题）。"
            "**不要重试本工具**，也不要改参数再调。"
            "直接用自然语言告诉用户系统暂时不可用，请稍后再试，然后结束本轮。"
        )

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
                f"FATAL: 工作流响应超时（>{_CALL_WORKFLOW_TIMEOUT}s，后端可能繁忙或卡住）。"
                f"**不要重试本工具**，直接用自然语言告诉用户系统繁忙、请稍后再试，然后结束本轮。"
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
        if result.next_instruction:
            ctx.deps.instruction = result.next_instruction

        # ── 结构化数据推给前端（TOOL_RESULT_DETAIL 事件）──
        # LLM 看不到 tool_result_raw（只看 tool_result_message）；
        # 前端通过 SSE/Kafka 拿到这个事件后可以直接渲染卡片/列表。
        if result.tool_result_raw is not None and ctx.deps.emitter is not None:
            from agent_sdk._event.event_model import EventModel
            from agent_sdk._event.event_type import EventType
            await ctx.deps.emitter.emit(EventModel(
                session_id=sid,
                request_id=rid,
                type=EventType.TOOL_RESULT_DETAIL,
                data={
                    "tool_name": ctx.tool_name or "report_to_workflow",
                    "tool_call_id": ctx.tool_call_id or "",
                    "detail_type": "workflow_result",
                    "data": result.tool_result_raw,
                },
            ))

        log_tool_end("report_to_workflow", sid, rid, {
            "activity": result.current_activity,
            "has_next_instruction": bool(result.next_instruction),
            "has_tool_result_raw": result.tool_result_raw is not None,
        })
        return result.tool_result_message

    except Exception as e:
        log_tool_end("report_to_workflow", sid, rid, exc=e)
        # 其它异常（网络抖动、序列化问题等）也先让 LLM 不要死循环重试；
        # 交给用户看完再决定要不要继续
        return (
            f"FATAL: 工作流调用出错（{type(e).__name__}: {e}）。"
            f"**不要重试本工具**，用自然语言向用户说明系统异常、稍后再试，然后结束本轮。"
        )


report_to_workflow.__doc__ = _DESCRIPTION
