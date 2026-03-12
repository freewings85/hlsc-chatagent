"""HLSC 主 Agent 入口：使用 SDK Agent + AgentApp

这是 server.py 的 SDK 版替代。展示如何用 SDK 构建完整的主 Agent。

启动方式：
    uv run python -m src.hlsc.mainagent.app [--port 8100]
"""

from __future__ import annotations

import argparse
import logging
import os

from src.sdk import (
    Agent,
    AgentApp,
    AgentAppConfig,
    SkillConfig,
    ToolConfig,
)
from src.sdk.config import McpConfig
from src.hlsc.mainagent.prompt_loader import create_main_prompt_loader

logger = logging.getLogger(__name__)


def create_main_agent() -> Agent:
    """创建 HLSC 主 Agent"""
    from src.agent.tools import create_default_tool_map
    from src.storage.local_backend import FilesystemBackend

    user_fs_dir = os.getenv("USER_FS_DIR", "data")
    user_fs_backend = FilesystemBackend(root_dir=user_fs_dir, virtual_mode=True)

    prompt_loader = create_main_prompt_loader(user_fs_backend)
    tool_map = create_default_tool_map()

    # Skill 目录
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


def main() -> None:
    parser = argparse.ArgumentParser(description="HLSC Main Agent (SDK)")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    agent = create_main_agent()
    app = AgentApp(
        agent,
        AgentAppConfig(
            name="HLSC-MainAgent",
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
            host=args.host,
            port=args.port,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
