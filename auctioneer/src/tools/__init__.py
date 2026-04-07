"""Auctioneer 工具集（决策阶段使用的工具）。"""

from typing import Any

from src.tools.commit_order import commit_order
from src.tools.discuss_command import discuss_command


def create_auctioneer_tool_map() -> dict[str, Any]:
    return {
        "commit_order": commit_order,
        "discuss_command": discuss_command,
    }


__all__: list[str] = [
    "create_auctioneer_tool_map",
]
