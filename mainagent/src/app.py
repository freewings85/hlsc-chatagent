"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader

# subagent 调用工具
from src.tools.call_code_agent import call_code_agent
# from src.tools.call_demo_price_finder import call_demo_price_finder
from src.tools.call_diagnose_agent import call_diagnose_agent
from src.tools.call_recommend_project import call_recommend_project

# extensions 业务工具
from hlsc.tools.fuzzy_match_car_info import fuzzy_match_car_info
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.ask_user_car_info import ask_user_car_info
from hlsc.tools.fuzzy_match_location import fuzzy_match_location
from hlsc.tools.ask_user_location import ask_user_location
from hlsc.tools.match_project import match_project
from hlsc.tools.get_project_price import get_project_price


def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + subagent 调用 + extensions 业务工具
    tool_map = {
        **create_default_tool_map(),
        # subagent 调用
        "call_code_agent": call_code_agent,
        # "call_demo_price_finder": call_demo_price_finder,
        "call_diagnose_agent": call_diagnose_agent,
        "call_recommend_project": call_recommend_project,
        # 车辆信息
        "fuzzy_match_car_info": fuzzy_match_car_info,
        "list_user_cars": list_user_cars,
        "ask_user_car_info": ask_user_car_info,
        # 位置信息
        "fuzzy_match_location": fuzzy_match_location,
        "ask_user_location": ask_user_location,
        # 项目 & 报价
        "match_project": match_project,
        "get_project_price": get_project_price,
    }

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit", "bash"]),
        context_formatter=HlscContextFormatter(),
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )
