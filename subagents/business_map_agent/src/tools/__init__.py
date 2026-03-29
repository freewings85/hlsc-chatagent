"""BusinessMapAgent 工具集。"""

from typing import Any

from src.tools.get_business_children import get_business_children
from src.tools.get_business_node import get_business_node


def create_bm_tool_map() -> dict[str, Any]:
    """创建业务地图导航工具映射。"""
    return {
        "get_business_children": get_business_children,
        "get_business_node": get_business_node,
    }


__all__: list[str] = [
    "create_bm_tool_map",
]
