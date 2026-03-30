"""summarize_best_offer 工具：汇总最优方案。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("summarize_best_offer")


async def summarize_best_offer(
    ctx: RunContext[AgentDeps],
    task_id: Annotated[str, Field(description="竞标任务 ID")],
    quotes: Annotated[list[dict[str, Any]], Field(description="所有商户报价列表")],
) -> str:
    """按价格排序汇总最优方案。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("summarize_best_offer", sid, rid, {"task_id": task_id, "quote_count": len(quotes)})

    # 按价格从低到高排序
    sorted_quotes: list[dict[str, Any]] = sorted(quotes, key=lambda q: float(q.get("quote_price", 999999)))

    best: dict[str, Any] | None = sorted_quotes[0] if sorted_quotes else None

    result: dict[str, object] = {
        "task_id": task_id,
        "total_quotes": len(quotes),
        "ranked_quotes": sorted_quotes,
        "best_offer": best,
        "recommendation": f"推荐选择 {best['shop_name']}，报价 {best['quote_price']} 元" if best else "暂无商户报价",
    }

    log_tool_end("summarize_best_offer", sid, rid, {"best": best})
    return json.dumps(result, ensure_ascii=False)


summarize_best_offer.__doc__ = _DESCRIPTION
