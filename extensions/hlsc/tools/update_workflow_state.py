"""update_workflow_state 工具：把收集到的业务字段同步写入 Workflow 状态。

**仅 orchestrator 编排模式下可用**（ctx.deps.workflow_id 非空时）。
降级模式下此工具不注册。

调用链路：
    Agent LLM 调用此工具
    → tool 从 deps 取 temporal_client + workflow_id
    → handle.execute_update("on_state_changed", StateChangeRequest(fields={...}))
    → Workflow 内部：写 MySQL + 判断是否推进 step
    → 返回 StateChangeResult（current_step / advanced / message）
    → tool 把结果返回给 LLM

**Agent 只需要传收集到的字段**，不需要知道 step 名字、不需要说推进到哪里。
Workflow 自己判断推进逻辑。

状态写入由 Workflow 的 update handler 执行（调 write_session_state_activity 写 MySQL），
不是 Agent 侧写。单一写入点，保证一致性。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end


async def update_workflow_state(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"LHGK12345\", \"register_date\": \"2020-06-15\"}"
    )],
) -> str:
    """把收集到的信息同步写入业务流程状态。写入成功后流程可能会自动推进到下一步。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("update_workflow_state", sid, rid, {"fields": list(fields.keys())})

    # 取 Temporal client 和 workflow_id
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
            StateChangeRequest(fields=fields),
            result_type=StateChangeResult,
        )

        # 同步刷新本地 session_state（后续工具调用能看到最新值）
        for k, v in fields.items():
            ctx.deps.session_state[k] = v

        summary: str
        if result.advanced:
            summary = f"ok. 已推进到 {result.current_step}"
        else:
            summary = f"ok. 当前仍在 {result.current_step}"
        if result.message:
            summary += f" ({result.message})"

        log_tool_end("update_workflow_state", sid, rid, {
            "current_step": result.current_step,
            "advanced": result.advanced,
        })
        return summary

    except Exception as e:
        log_tool_end("update_workflow_state", sid, rid, exc=e)
        return f"error: update_workflow_state failed - {e}"
