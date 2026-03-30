"""Auctioneer 工具集（仅 LLM 汇总阶段使用的工具）。"""

from typing import Any

from src.tools.summarize_best_offer import summarize_best_offer


def create_auctioneer_tool_map() -> dict[str, Any]:
    return {
        "summarize_best_offer": summarize_best_offer,
    }


__all__: list[str] = [
    "create_auctioneer_tool_map",
]
