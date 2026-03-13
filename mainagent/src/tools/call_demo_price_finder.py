"""call_demo_price_finder 工具：通过 A2A 协议调用 DemoPriceFinder subagent。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk.a2a import call_subagent

from src.config import DEMO_PRICE_FINDER_URL


async def call_demo_price_finder(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """Call the DemoPriceFinder subagent to find the best price for a car repair project.

    This tool communicates with a remote DemoPriceFinder agent via A2A protocol.
    The subagent may ask the user for confirmation during execution.

    触发示例 — 当用户表达以下意图时应调用此工具：
    - 询价类："更换刹车片多少钱？"、"油漆维修哪家便宜？"、"帮我查一下换轮胎的价格"
    - 比价类："哪家店做保养最划算？"、"找个最便宜的地方修空调"
    - 维修项目 + 价格关键词组合："变速箱维修报个价"、"发动机大修费用"

    Args:
        query: 维修项目描述（e.g. "更换刹车片"、"油漆维修"、"空调维修"）。

    Returns:
        The subagent's final response.
    """
    return await call_subagent(ctx, url=DEMO_PRICE_FINDER_URL, message=query)
