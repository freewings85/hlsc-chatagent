"""update_workflow_state 工具：把用户给出的业务字段静默写入 workflow 状态。

调用链路：
    LLM → update_workflow_state(fields)
    → Temporal execute_update("on_state_changed", StateChangeRequest)
    → Workflow: 写 MySQL → on_session_state_change（业务逻辑）
    → 返回 StateChangeResult：
        - tool_result_message  → 本轮 LLM 看到的 tool result 文本
        - next_instruction     → 下一轮 agent 的 instruction 热切换（tail dynamic-context）
    → Tool 返回给 LLM：tool_result_message

**失败处理**：任何失败（无 client、超时、Temporal 异常）直接 raise
WorkflowUnavailableError，sdk loop 会专门 catch，终止本轮 agent。
不再返回错误字符串给 LLM——LLM 看到错误字符串依旧会反复重试同一工具
（已知 LLM 行为：retry path 不重读 conversation 上的"不要重试"指令）。
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.exceptions import WorkflowUnavailableError
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("update_workflow_state")

# Agent 等 workflow update 返回的墙钟超时（秒）
# Temporal 的 rpc_timeout 只管单次 poll，execute_update 会一直循环 poll 直到 handler 返回。
# 这个墙钟上限防止 tool 阻塞 agent 太久。调试时可以调大。
_CALL_WORKFLOW_TIMEOUT: float = float(os.getenv("CALL_WORKFLOW_TIMEOUT", "120"))


async def update_workflow_state(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"xxxxxx\", \"register_date\": \"xxxxx\"}"
    )],
) -> str:
    """静默把收集到的事实写入会话状态。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_workflow_state", sid, rid, {"fields": list(fields.keys())})

    temporal_client = ctx.deps.temporal_client
    workflow_id: str | None = ctx.deps.workflow_id

    if temporal_client is None or workflow_id is None:
        log_tool_end("update_workflow_state", sid, rid, exc=RuntimeError("not in orchestrator mode"))
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
            log_tool_end("update_workflow_state", sid, rid, exc=TimeoutError(f">{_CALL_WORKFLOW_TIMEOUT}s"))
            raise WorkflowUnavailableError(
                f"工作流响应超时（>{_CALL_WORKFLOW_TIMEOUT}s）"
            )

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
                    "tool_name": ctx.tool_name or "update_workflow_state",
                    "tool_call_id": ctx.tool_call_id or "",
                    "detail_type": "workflow_result",
                    "data": result.tool_result_raw,
                },
            ))

        log_tool_end("update_workflow_state", sid, rid, {
            "has_next_instruction": bool(result.next_instruction),
            "has_tool_result_raw": result.tool_result_raw is not None,
        })
        return result.tool_result_message

    except WorkflowUnavailableError:
        # 内部 try 已经 log_tool_end 过了，往外抛
        raise
    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        # 任何其它异常一律转 WorkflowUnavailableError，让 agent loop 终止本轮
        raise WorkflowUnavailableError(
            f"工作流调用出错（{type(e).__name__}: {e}）"
        ) from e


update_workflow_state.__doc__ = _DESCRIPTION
