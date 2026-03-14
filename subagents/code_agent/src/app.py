"""CodeAgent Subagent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.prompt_loader import create_code_agent_prompt_loader
from src.tools import create_code_agent_tool_map


def create_agent_app() -> AgentApp:
    """创建 CodeAgent AgentApp"""
    prompt_loader = create_code_agent_prompt_loader()

    # SDK 默认工具（read/edit/write/glob/grep/bash/task）+ 业务工具（execute_code）
    tool_map = {**create_default_tool_map(), **create_code_agent_tool_map()}

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="编程查询 Agent：通过编写 Python 代码调用业务 API 回答复杂数据问题",
        ),
    )
