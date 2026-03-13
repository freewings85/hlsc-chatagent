"""HLSC 主 Agent 工厂：创建配置好的 Agent 实例

server.py 调用 create_main_agent() 获取 Agent，再包装为 AgentApp 启动。
"""

from __future__ import annotations

import os

from src.sdk import Agent, SkillConfig, ToolConfig
from src.sdk.config import McpConfig
from src.hlsc.mainagent.prompt_loader import create_main_prompt_loader


def create_main_agent() -> Agent:
    """创建 HLSC 主 Agent"""
    from src.sdk._agent.tools import create_default_tool_map
    from src.sdk._storage.local_backend import FilesystemBackend
    from src.hlsc.mainagent.tools import create_main_tool_map

    user_fs_dir = os.getenv("USER_FS_DIR", "data")
    user_fs_backend = FilesystemBackend(root_dir=user_fs_dir, virtual_mode=True)

    prompt_loader = create_main_prompt_loader(user_fs_backend)
    tool_map = {**create_default_tool_map(), **create_main_tool_map()}

    agent_fs_dir = os.getenv("AGENT_FS_DIR", ".chatagent")
    skill_dirs = [
        os.path.join(agent_fs_dir, "skills"),
        "skills",
    ]

    return Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(
            manual=tool_map,
            mcp_config=McpConfig(config_path=".mcp.json"),
        ),
        skill_config=SkillConfig(skill_dirs=skill_dirs),
        agent_name="main",
    )
