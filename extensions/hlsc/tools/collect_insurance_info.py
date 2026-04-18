"""collect_insurance_info 工具：收集用户的保险需求描述和期望返现金额。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from hlsc.tools.prompt_loader import load_tool_prompt
from hlsc.tools.update_workflow_state import update_workflow_state

_DESCRIPTION = load_tool_prompt("collect_insurance_info")


def _build_result(needs_description: str, expected_cashback: float) -> str:
    """将字段组装为返回文本。"""
    return json.dumps({
        "needs_description": needs_description,
        "expected_cashback": expected_cashback,
    }, ensure_ascii=False)


async def collect_insurance_info(
    ctx: RunContext[AgentDeps],
    needs_description: Annotated[str, Field(
        description="保险需求描述，如'交强险+商业险'、'只要交强险'",
    )],
    expected_cashback: Annotated[float, Field(
        gt=0,
        description="期望返现金额（元），必须大于0",
    )],
) -> str:
    """收集保险需求描述和期望返现金额。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("collect_insurance_info", sid, rid, {
        "needs_description": needs_description,
        "expected_cashback": expected_cashback,
    })

    await update_workflow_state(ctx, {
        "needs_description": needs_description,
        "expected_cashback": expected_cashback,
    })

    log_tool_end("collect_insurance_info", sid, rid, {
        "needs_description": needs_description,
        "expected_cashback": expected_cashback,
    })
    return _build_result(needs_description, expected_cashback)


collect_insurance_info.__doc__ = _DESCRIPTION
