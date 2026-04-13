"""update_workflow_state 工具：把收集到的业务字段写入 Workflow 状态。

调用链路：
    Agent LLM 调用此工具
    → tool 从 deps 取 temporal_client + workflow_id
    → handle.execute_update("on_state_changed", StateChangeRequest(fields={...}))
    → Workflow 内部：写 MySQL + 判断字段是否齐了
    → 返回 StateChangeResult
    → tool 把结果返回给 LLM
"""

from __future__ import annotations

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

        # 如果 workflow 返回了最新 session_state，合并
        if result.new_session_state:
            ctx.deps.session_state.update(result.new_session_state)

        summary: str = "ok. 已写入"
        if result.message:
            summary += f"（{result.message}）"

        log_tool_end("update_workflow_state", sid, rid, {
            "current_step": result.current_step,
            "advanced": result.advanced,
        })
        return summary

    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        return f"error: update_workflow_state failed - {e}"


update_workflow_state.__doc__ = _DESCRIPTION
