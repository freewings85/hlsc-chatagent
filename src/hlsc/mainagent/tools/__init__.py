"""MainAgent 业务工具集。"""

from src.hlsc.mainagent.tools.call_price_finder import call_price_finder

__all__ = ["call_price_finder"]


def create_main_tool_map() -> dict:
    """创建 MainAgent 的业务工具映射。"""
    return {
        "call_price_finder": call_price_finder,
    }
