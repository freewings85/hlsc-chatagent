"""场景级「提交事实到 workflow」工具的共享底座。

所有 submit_*/report_* 类工具（按 scene 命名）都共用这套流程：
  LLM → scene 工具 → _submit_workflow_fields(fields, tool_name)
    → Temporal execute_update("on_state_changed", StateChangeRequest)
    → Workflow validate loop → StateChangeResult
    → 发 TOOL_RESULT_DETAIL 事件（前端渲染用）
    → 热切换 next_instruction
    → 返回 tool_result_message（LLM 可见）

任何失败统一 raise WorkflowUnavailableError，agent loop 会捕获终止本轮——
不给 LLM 看错误字符串，避免重试同一工具。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.exceptions import WorkflowUnavailableError
from agent_sdk.logging import log_tool_start, log_tool_end

_CALL_WORKFLOW_TIMEOUT: float = float(os.getenv("CALL_WORKFLOW_TIMEOUT", "120"))


async def submit_workflow_fields(
    ctx: RunContext[AgentDeps],
    fields: dict[str, Any],
    tool_name: str,
) -> str:
    """把 fields 提交给 workflow 的 on_state_changed，返回 tool_result_message。

    Args:
        ctx: Pydantic AI RunContext
        fields: 要登记到 workflow 状态的字段字典
        tool_name: 调用方工具名（日志 / TOOL_RESULT_DETAIL 事件用）

    Raises:
        WorkflowUnavailableError: temporal_client 缺失、超时、任何异常
    """
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start(tool_name, sid, rid, {"fields": list(fields.keys())})

    if not fields:
        log_tool_end(tool_name, sid, rid, {"skipped": "empty_fields"})
        return "本次未提交任何字段，已忽略。"

    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end(tool_name, sid, rid, exc=RuntimeError("not in orchestrator mode"))
        raise WorkflowUnavailableError(
            "后端工作流连接不可用（temporal_client 或 workflow_id 缺失）"
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
            log_tool_end(tool_name, sid, rid, exc=TimeoutError(f">{_CALL_WORKFLOW_TIMEOUT}s"))
            raise WorkflowUnavailableError(
                f"工作流响应超时（>{_CALL_WORKFLOW_TIMEOUT}s）"
            )

        if result.next_instruction:
            ctx.deps.instruction = result.next_instruction

        if result.tool_result_raw is not None and ctx.deps.emitter is not None:
            from agent_sdk._event.event_model import EventModel
            from agent_sdk._event.event_type import EventType
            await ctx.deps.emitter.emit(EventModel(
                session_id=sid,
                request_id=rid,
                type=EventType.TOOL_RESULT_DETAIL,
                data={
                    "tool_name": ctx.tool_name or tool_name,
                    "tool_call_id": ctx.tool_call_id or "",
                    "detail_type": "workflow_result",
                    "data": result.tool_result_raw,
                },
            ))

        log_tool_end(tool_name, sid, rid, {
            "has_next_instruction": bool(result.next_instruction),
            "has_tool_result_raw": result.tool_result_raw is not None,
        })
        # activity 显式传空串时兜底，避免 LLM 拿到 "" 不知所措
        return result.tool_result_message or "已记录。"

    except WorkflowUnavailableError:
        raise
    except Exception as e:
        log_tool_end(tool_name, sid, rid, exc=e)
        raise WorkflowUnavailableError(
            f"工作流调用出错（{type(e).__name__}: {e}）"
        ) from e
