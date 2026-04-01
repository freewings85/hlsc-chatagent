"""Auctioneer 工具集（LLM 汇总 + 决策阶段使用的工具）。"""

from typing import Any

from src.tools.commit_order import commit_order
from src.tools.discuss_command import discuss_command
from src.tools.renew_price import renew_price
from src.tools.summarize_best_offer import summarize_best_offer


def create_auctioneer_tool_map() -> dict[str, Any]:
    return {
        "summarize_best_offer": summarize_best_offer,
        "commit_order": commit_order,
        "discuss_command": discuss_command,
        "renew_price": renew_price,
    }


__all__: list[str] = [
    "create_auctioneer_tool_map",
]
