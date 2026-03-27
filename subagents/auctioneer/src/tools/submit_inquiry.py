"""submit_inquiry 工具：发布竞标请求（mock）。"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("submit_inquiry")


async def submit_inquiry(
    ctx: RunContext[AgentDeps],
    project_ids: Annotated[list[str], Field(description="项目 ID 列表")],
    shop_ids: Annotated[list[str], Field(description="参与竞标的商户 ID 列表")],
    car_model_id: Annotated[str, Field(description="车型 ID")],
    price: Annotated[str, Field(description="车主出的一口价")],
) -> str:
    """发布竞标请求到商户。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    params: dict[str, object] = {
        "project_ids": project_ids,
        "shop_ids": shop_ids,
        "car_model_id": car_model_id,
        "price": price,
    }
    log_tool_start("submit_inquiry", sid, rid, params)

    # Mock: 返回竞标任务 ID
    result: dict[str, object] = {
        "task_id": f"mock-task-{sid[:8]}",
        "status": "published",
        "merchant_count": len(shop_ids),
        "notice": f"竞标已发布，共通知 {len(shop_ids)} 家商户",
    }

    log_tool_end("submit_inquiry", sid, rid, result)
    return json.dumps(result, ensure_ascii=False)


submit_inquiry.__doc__ = _DESCRIPTION
