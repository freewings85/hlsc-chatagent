"""文件系统工具集导出。

使用示例：
    from src.agent.tools import create_default_tool_map, ALL_FS_TOOLS

    deps = AgentDeps(
        available_tools=ALL_FS_TOOLS,
        tool_map=create_default_tool_map(),
    )
"""

from src.agent.tools.ask_user import ask_user
from src.agent.tools.bash import bash
from src.agent.tools.call_price_finder import call_price_finder
from src.agent.file_state import ChangedFile, FileEntry, FileStateTracker
from src.agent.tools.fs import edit, glob, grep, read, write
from src.agent.tools.task import task

__all__ = [
    # FileStateTracker
    "FileStateTracker",
    "FileEntry",
    "ChangedFile",
    # 工具函数
    "read",
    "edit",
    "write",
    "glob",
    "grep",
    "bash",
    "task",
    "ask_user",
    "call_price_finder",
    # 便捷工厂
    "ALL_FS_TOOLS",
    "create_default_tool_map",
]

ALL_FS_TOOLS: list[str] = [
    "read", "edit", "write", "glob", "grep", "bash", "task", "ask_user",
    "call_price_finder",
]


def create_default_tool_map() -> dict:
    """创建包含所有工具的 tool_map，用于初始化 AgentDeps。"""
    return {
        "read": read,
        "edit": edit,
        "write": write,
        "glob": glob,
        "grep": grep,
        "bash": bash,
        "task": task,
        "ask_user": ask_user,
        "call_price_finder": call_price_finder,
    }
