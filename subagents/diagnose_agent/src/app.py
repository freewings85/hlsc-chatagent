"""DiagnoseAgent Subagent 工厂"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from src.prompt_loader import create_diagnose_prompt_loader
from src.tools import create_diagnose_tool_map


def create_agent_app() -> AgentApp:
    """创建 DiagnoseAgent AgentApp"""
    prompt_loader = create_diagnose_prompt_loader()
    tool_map = create_diagnose_tool_map()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽车故障诊断 Agent — 从故障知识库检索并分析故障原因",
        ),
    )
