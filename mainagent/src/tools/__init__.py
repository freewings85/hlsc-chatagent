"""MainAgent 业务工具集。"""

from src.tools.call_demo_price_finder import call_demo_price_finder

__all__ = ["call_demo_price_finder"]


def create_main_tool_map() -> dict:
    """创建 MainAgent 的业务工具映射。"""
    return {
        "call_demo_price_finder": call_demo_price_finder,
    }
