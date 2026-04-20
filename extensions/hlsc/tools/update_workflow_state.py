"""update_workflow_state 工具：把用户给出的业务字段静默写入 workflow 状态。

这是一个通用工具，仅给还没迁到 Validate-Loop 模式的场景（insurance /
searchcoupons）兜底用。已迁移的场景（searchshops / debug 沙盒）用场景级
专用工具（submit_shop_search_criteria 等）。

调用链路：
    LLM → update_workflow_state(fields)
    → _submit_helper.submit_workflow_fields
    → Temporal on_state_changed → StateChangeResult
    → 返回 tool_result_message 给 LLM

任何失败直接 raise WorkflowUnavailableError，agent loop 专门 catch 终止本轮。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from hlsc.tools._submit_helper import submit_workflow_fields
from hlsc.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("update_workflow_state")


async def update_workflow_state(
    ctx: RunContext[AgentDeps],
    fields: Annotated[dict[str, Any], Field(
        description="本次收集到的业务字段。key 是字段名，value 是字段值。"
        "例如 {\"vin\": \"xxxxxx\", \"register_date\": \"xxxxx\"}"
    )],
) -> str:
    """静默把收集到的事实写入会话状态。"""
    return await submit_workflow_fields(ctx, fields, tool_name="update_workflow_state")


update_workflow_state.__doc__ = _DESCRIPTION
