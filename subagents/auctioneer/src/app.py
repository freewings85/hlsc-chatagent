"""Auctioneer Subagent 工厂：创建配置好的 AgentApp 实例"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from src.auctioneer_context import AuctioneerContextFormatter
from src.prompt_loader import create_auctioneer_prompt_loader
from src.tools import create_auctioneer_tool_map


def create_agent_app() -> AgentApp:
    """创建 Auctioneer AgentApp"""
    prompt_loader: object = create_auctioneer_prompt_loader()
    tool_map: dict[str, object] = create_auctioneer_tool_map()

    agent: Agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map),
        context_formatter=AuctioneerContextFormatter(),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="拍卖师 — 替车主向商户发起竞标、收集报价、汇总最优方案",
        ),
    )
