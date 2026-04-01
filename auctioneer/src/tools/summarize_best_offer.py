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

    # 只保留已报价的（offer_status > 0）
    responded: list[dict[str, Any]] = [
        q for q in quotes if q.get("offer_status", 0) > 0
    ]

    # 按价格从低到高排序
    sorted_quotes: list[dict[str, Any]] = sorted(
        responded, key=lambda q: float(q.get("offer_price", 999999))
    )

    best: dict[str, Any] | None = sorted_quotes[0] if sorted_quotes else None

    result: dict[str, object] = {
        "task_id": task_id,
        "total_quotes": len(responded),
        "ranked_quotes": sorted_quotes,
        "best_offer": best,
        "recommendation": (
            f"推荐选择 {best['commercial_name']}（商户ID: {best['commercial_id']}），"
            f"报价 {best['offer_price']} 元"
            if best
            else "暂无商户报价"
        ),
    }

    log_tool_end("summarize_best_offer", sid, rid, {"best": best})
    return json.dumps(result, ensure_ascii=False)


summarize_best_offer.__doc__ = _DESCRIPTION
