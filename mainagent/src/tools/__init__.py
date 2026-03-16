"""MainAgent 业务工具集。"""

from src.tools.call_code_agent import call_code_agent
from src.tools.call_demo_price_finder import call_demo_price_finder
from src.tools.call_diagnose_agent import call_diagnose_agent
from src.tools.call_recommend_project import call_recommend_project

__all__ = [
    "call_code_agent",
    "call_demo_price_finder",
    "call_diagnose_agent",
    "call_recommend_project",
]


def create_main_tool_map() -> dict:
    """创建 MainAgent 的业务工具映射。"""
    return {
        "call_code_agent": call_code_agent,
        "call_demo_price_finder": call_demo_price_finder,
        "call_diagnose_agent": call_diagnose_agent,
        "call_recommend_project": call_recommend_project,
    }
