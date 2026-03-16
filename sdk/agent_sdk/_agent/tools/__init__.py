"""文件系统工具集导出。

使用示例：
    from agent_sdk._agent.tools import create_default_tool_map, ALL_FS_TOOLS

    deps = AgentDeps(
        available_tools=ALL_FS_TOOLS,
        tool_map=create_default_tool_map(),
    )
"""

from agent_sdk._agent.tools.bash import bash
from agent_sdk._agent.file_state import ChangedFile, FileEntry, FileStateTracker
from agent_sdk._agent.tools.fs import edit, glob, grep, read, write
from agent_sdk._agent.tools.task import task

__all__ = [
    # FileStateTracker
    "FileStateTracker",
    "FileEntry",
    "ChangedFile",
    # 工具函数（LLM 可调用的 tool）
    "read",
    "edit",
    "write",
    "glob",
    "grep",
    "bash",
    "task",
    # 便捷工厂
    "ALL_FS_TOOLS",
    "create_default_tool_map",
]

ALL_FS_TOOLS: list[str] = [
    "read", "edit", "write", "glob", "grep", "bash", "task",
]


def create_default_tool_map() -> dict:
    """创建 SDK 内置工具的 tool_map。业务工具由各 Agent 自行注册。"""
    return {
        "read": read,
        "edit": edit,
        "write": write,
        "glob": glob,
        "grep": grep,
        "bash": bash,
        "task": task,
    }
