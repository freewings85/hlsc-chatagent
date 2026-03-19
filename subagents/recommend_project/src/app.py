"""RecommendProject Subagent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from src.recommend_context import RecommendContextFormatter
from src.prompt_loader import create_recommend_project_prompt_loader
from src.tools import create_recommend_project_tool_map


def create_agent_app() -> AgentApp:
    """创建 RecommendProject AgentApp"""
    prompt_loader = create_recommend_project_prompt_loader()
    tool_map = create_recommend_project_tool_map()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
        context_formatter=RecommendContextFormatter(),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽车养车服务专家 — 推荐养车项目、诊断故障并推荐维修项目",
        ),
    )
