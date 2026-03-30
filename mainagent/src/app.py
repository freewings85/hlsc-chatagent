"""HLSC 主 Agent 工厂：创建配置好的 AgentApp 实例

server.py 调用 create_agent_app() 获取 AgentApp，直接启动。
"""

from __future__ import annotations

from agent_sdk import Agent, AgentApp, AgentAppConfig, ProfileTriggerHook, ToolConfig
from agent_sdk._agent.tools import create_default_tool_map
from src.hlsc_context import HlscContextFormatter
from src.prompt_loader import create_main_prompt_loader

# subagent 调用工具
from hlsc.tools.call_query_codingagent import call_query_codingagent

# extensions 业务工具
from hlsc.tools.get_representative_car_model import get_representative_car_model
from hlsc.tools.list_user_cars import list_user_cars
from hlsc.tools.ask_user_car_info import ask_user_car_info
from hlsc.tools.geocode_location import geocode_location
from hlsc.tools.ask_user_location import ask_user_location
from hlsc.tools.match_project import match_project
from hlsc.tools.get_visited_shops import get_visited_shops
from hlsc.tools.search_nearby_shops import search_shops
from hlsc.tools.confirm_booking import confirm_booking


def create_agent_app() -> AgentApp:
    """创建 HLSC 主 AgentApp"""
    prompt_loader = create_main_prompt_loader()

    # SDK 内置工具 + subagent 调用 + extensions 业务工具
    tool_map = {
        **create_default_tool_map(),
        # 项目匹配
        "match_project": match_project,
        # 车辆信息
        "get_representative_car_model": get_representative_car_model,
        "list_user_cars": list_user_cars,
        "ask_user_car_info": ask_user_car_info,
        # 位置
        "geocode_location": geocode_location,
        "ask_user_location": ask_user_location,
        # 商户
        "search_shops": search_shops,
        "get_visited_shops": get_visited_shops,
        # 下单
        "confirm_booking": confirm_booking,
        # 复杂查询
        "call_query_codingagent": call_query_codingagent,
    }

    formatter: HlscContextFormatter = HlscContextFormatter()

    agent = Agent(
        prompt_loader=prompt_loader,
        tools=ToolConfig(manual=tool_map, exclude=["write", "edit"]),
        context_formatter=formatter,
        after_run_hooks=[ProfileTriggerHook()],
    )

    return AgentApp(
        agent,
        AgentAppConfig(
            description="汽修场景主 Agent，支持工具调用、文件操作、中断确认",
        ),
    )
