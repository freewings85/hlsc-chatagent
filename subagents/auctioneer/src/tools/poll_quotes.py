"""poll_quotes 工具：轮询商户报价（mock）。"""

from __future__ import annotations

import json
import random
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.logging import log_tool_start, log_tool_end
from src.tools.prompt_loader import load_tool_prompt

_DESCRIPTION: str = load_tool_prompt("poll_quotes")

# Mock 商户数据池
_MOCK_MERCHANTS: list[dict[str, str | float]] = [
    {"shop_id": "S001", "shop_name": "朱德保修理厂", "base_price": 25.0},
    {"shop_id": "S002", "shop_name": "张记汽修连锁", "base_price": 28.0},
    {"shop_id": "S003", "shop_name": "老王精洗工作室", "base_price": 22.0},
    {"shop_id": "S004", "shop_name": "速达汽车服务", "base_price": 30.0},
    {"shop_id": "S005", "shop_name": "金牌养车中心", "base_price": 26.0},
]

# 每个 task 的已回复商户跟踪
_task_responded: dict[str, list[str]] = {}


async def poll_quotes(
    ctx: RunContext[AgentDeps],
    task_id: Annotated[str, Field(description="竞标任务 ID")],
    total_merchants: Annotated[int, Field(description="参与竞标的商户总数")] = 3,
) -> str:
    """轮询收集商户报价。"""
    sid: str = ctx.deps.session_id
    rid: str = ctx.deps.request_id
    log_tool_start("poll_quotes", sid, rid, {"task_id": task_id})

    # Mock: 每次轮询随机新增 1-2 家商户回复
    if task_id not in _task_responded:
        _task_responded[task_id] = []

    responded: list[str] = _task_responded[task_id]
    available: list[dict[str, str | float]] = [
        m for m in _MOCK_MERCHANTS if m["shop_id"] not in responded
    ]

    # 随机新增 1-2 家回复
    new_count: int = min(random.randint(1, 2), len(available), total_merchants - len(responded))
    new_respondents: list[dict[str, str | float]] = random.sample(available, new_count) if new_count > 0 else []

    quotes: list[dict[str, object]] = []
    for merchant in new_respondents:
        responded.append(str(merchant["shop_id"]))
        # 报价在 base_price 基础上随机浮动 ±15%
        base: float = float(merchant["base_price"])
        quote_price: float = round(base * random.uniform(0.85, 1.15), 1)
        quotes.append({
            "shop_id": merchant["shop_id"],
            "shop_name": merchant["shop_name"],
            "quote_price": quote_price,
            "status": "quoted",
        })

    all_done: bool = len(responded) >= total_merchants

    result: dict[str, object] = {
        "task_id": task_id,
        "new_quotes": quotes,
        "total_responded": len(responded),
        "total_merchants": total_merchants,
        "all_done": all_done,
    }

    log_tool_end("poll_quotes", sid, rid, {"responded": len(responded), "all_done": all_done})
    return json.dumps(result, ensure_ascii=False)


poll_quotes.__doc__ = _DESCRIPTION
