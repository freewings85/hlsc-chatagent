"""DemoPriceFinder Subagent 工具集。"""

from __future__ import annotations

from pydantic_ai import RunContext

from agent_sdk._agent.deps import AgentDeps
from agent_sdk._agent.tools.call_interrupt import call_interrupt


async def find_best_price_of_project(
    ctx: RunContext[AgentDeps],
    project_name: str,
) -> str:
    """Find the best (cheapest) price for a car repair project across all shops.

    This tool searches for the best price and asks the user to confirm before
    returning the final result.

    Args:
        project_name: The name of the car repair project to search for.

    Returns:
        The best price result as a string.
    """
    # 模拟：查找到最低价
    mock_price = 500
    mock_shop = "张江汽修中心"

    user_reply = await call_interrupt(ctx, {
        "type": "confirm",
        "question": (
            f"找到项目「{project_name}」的最低报价：\n"
            f"门店：{mock_shop}\n"
            f"价格：{mock_price} 元\n\n"
            f"确认选择此方案吗？"
        ),
    })

    if user_reply in ("确认", "yes", "确定", "ok"):
        return (
            f"用户已确认。项目「{project_name}」最优方案：\n"
            f"门店：{mock_shop}\n"
            f"价格：{mock_price} 元"
        )
    else:
        return f"用户取消了项目「{project_name}」的询价。"


# 工具列表
DEMO_PRICE_FINDER_TOOLS: list[str] = ["find_best_price_of_project"]


def create_demo_price_finder_tool_map() -> dict:
    """创建 demo_price_finder 工具映射。"""
    return {
        "find_best_price_of_project": find_best_price_of_project,
    }
