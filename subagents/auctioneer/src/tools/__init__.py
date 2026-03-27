"""Auctioneer 工具集。"""

from typing import Any

from src.tools.submit_inquiry import submit_inquiry
from src.tools.poll_quotes import poll_quotes
from src.tools.notify_merchant import notify_merchant
from src.tools.summarize_best_offer import summarize_best_offer


def create_auctioneer_tool_map() -> dict[str, Any]:
    return {
        "submit_inquiry": submit_inquiry,
        "poll_quotes": poll_quotes,
        "notify_merchant": notify_merchant,
        "summarize_best_offer": summarize_best_offer,
    }


__all__: list[str] = [
    "create_auctioneer_tool_map",
]
