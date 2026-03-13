"""DemoPriceFinder Subagent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from src.prompt_loader import create_demo_price_finder_prompt_loader
from src.tools import create_demo_price_finder_tool_map


def create_agent_app() -> AgentApp:
    """创建 DemoPriceFinder AgentApp"""
    prompt_loader = create_demo_price_finder_prompt_loader()
    tool_map = create_demo_price_finder_tool_map()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽车维修项目最低价查询 Demo Agent，展示如何编写 Subagent",
        ),
    )
